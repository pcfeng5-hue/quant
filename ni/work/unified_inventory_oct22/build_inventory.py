#!/usr/bin/env python3
"""Read-only inventory of the existing source databases; no network or model inputs."""
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent
DBS = {
    'main': ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite',
    'chip_observations': ROOT/'outputs/高德红外数据库/历史筹码采集_20261017/筹码网页原始观察.sqlite',
    'five_priority_observations': ROOT/'outputs/五项数据补缺_20261022/五项补缺原始观察.sqlite',
}
LATEST_WORK = [
    ROOT/'work/market_warmup_finalize_oct22',
    ROOT/'work/conditions_finish_oct22',
    ROOT/'work/events_publication_oct22',
]
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:$|[T ])')
TEMPORAL_NAME = re.compile(r'(?:^|_)(?:dates?|times?|timestamp|period|published|publication|effective|retrieved|extracted|applied|observed)(?:_|$)|_at(?:_|$)', re.I)
FLAG_NAME = re.compile(r'eligible|accepted|verified|certified|complete|availability|status|authorization|licen[cs]|permission', re.I)

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def qi(s): return '"'+s.replace('"','""')+'"'
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
    c.execute('PRAGMA query_only=ON')
    c.row_factory=sqlite3.Row
    return c
def rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args)]
def temporal_profile(values):
    nn=[x for x in values if x is not None and x!='']
    dates=[x for x in nn if isinstance(x,str) and DATE_RE.match(x)]
    return {'total':len(values),'nonempty':len(nn),'iso_date_or_timestamp_count':len(dates),
            'distinct_nonempty':len(set(map(str,nn))),
            'min_iso':min(dates) if dates else None,'max_iso':max(dates) if dates else None,
            'role_caution':'Column name and ISO shape do not establish first-publication or point-in-time availability.'}

def scalar_profiles(records):
    keys=sorted(set().union(*(r.keys() for r in records))) if records else []
    result={}
    for k in keys:
        if not (TEMPORAL_NAME.search(k) or FLAG_NAME.search(k)):
            continue
        vals=[r.get(k) for r in records]
        if any(isinstance(x,(dict,list)) for x in vals):
            result[k]={'present':sum(k in r for r in records),'nonempty':sum(x not in (None,'',{},[]) for x in vals),'nested_values_preserved_in_source':True}
        else:
            v=temporal_profile(vals) if TEMPORAL_NAME.search(k) else {'total':len(vals),'nonempty':sum(x not in (None,'') for x in vals)}
            counts=collections.Counter(json.dumps(x,ensure_ascii=False,sort_keys=True) for x in vals)
            if len(counts)<=30:
                v['value_counts']={k:v for k,v in sorted(counts.items())}
            else:
                v['distinct_values']=len(counts)
            result[k]=v
    return result

def database_inventory(label,p):
    before=digest(p)
    c=ro(p)
    schema=rows(c,"SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")
    objects=[]
    for s in schema:
        if s['type'] not in ('table','view'):
            continue
        table=s['name']; cols=rows(c,'PRAGMA table_info('+qi(table)+')')
        item={'type':s['type'],'name':table,'schema_sql':s['sql'],'columns':cols,
              'row_count':c.execute('SELECT COUNT(*) FROM '+qi(table)).fetchone()[0],
              'temporal_columns':{},'flag_columns':{}}
        for col in cols:
            k=col['name']
            if TEMPORAL_NAME.search(k):
                item['temporal_columns'][k]=temporal_profile([r[0] for r in c.execute('SELECT '+qi(k)+' FROM '+qi(table))])
            if FLAG_NAME.search(k):
                agg=rows(c,'SELECT '+qi(k)+' AS value,COUNT(*) AS rows FROM '+qi(table)+' GROUP BY '+qi(k)+' ORDER BY COUNT(*) DESC')
                item['flag_columns'][k]={'distinct_values':len(agg),'value_counts':agg if len(agg)<=30 else None}
        objects.append(item)
    info={'label':label,'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256_before':before,
          'quick_check':c.execute('PRAGMA quick_check').fetchone()[0],'schema':schema,'objects':objects,
          'table_count':sum(x['type']=='table' for x in schema),'view_count':sum(x['type']=='view' for x in schema)}
    c.close()
    info['sha256_after']=digest(p);info['unchanged']=info['sha256_before']==info['sha256_after']
    return info

def group_json(records,keys,date_key):
    groups=collections.defaultdict(list)
    for r in records: groups[tuple(r.get(k) for k in keys)].append(r)
    out=[]
    for k,rs in sorted(groups.items(),key=lambda x:str(x[0])):
        dates=[r.get(date_key) for r in rs if r.get(date_key)]
        out.append({'group':dict(zip(keys,k)),'rows':len(rs),'distinct_dates':len(set(dates)),
                    'min_date':min(dates) if dates else None,'max_date':max(dates) if dates else None,
                    'warmup_dates_before_2023':len({d for d in dates if d<'2023-01-01'}),
                    'research_dates_since_2023':len({d for d in dates if d>='2023-01-01'})})
    return out

def load_work_directory(p):
    files=[]
    for f in sorted(p.rglob('*')):
        if f.is_file(): files.append({'path':str(f.relative_to(ROOT)),'bytes':f.stat().st_size,'sha256':digest(f)})
    summary=json.loads((p/'summary.json').read_text())
    data=[]
    # These are concrete source-entry files, rather than trusting reported row totals.
    names={
      'market_warmup_finalize_oct22':['market_rows_all_endpoints.json','market_rows.json','tencent_new_market_rows.json'],
      'conditions_finish_oct22':['daily_trade_conditions_915.json','rule_regimes.json','fee_schedule.json','monthly_report_observations.json'],
      'events_publication_oct22':['announcement_time_ledger_current.json','normalized_events.json','new_official_policy_samples.json'],
    }[p.name]
    for name in names:
        q=p/name
        if not q.exists():
            data.append({'path':str(q.relative_to(ROOT)),'exists':False});continue
        v=json.loads(q.read_text())
        if isinstance(v,list):
            recs=[x for x in v if isinstance(x,dict)]
            profile=scalar_profiles(recs)
            data.append({'path':str(q.relative_to(ROOT)),'exists':True,'container_type':'array','actual_rows':len(v),'scalar_field_profiles':profile})
        else:
            data.append({'path':str(q.relative_to(ROOT)),'exists':True,'container_type':type(v).__name__,'keys':list(v) if isinstance(v,dict) else None})
    return {'path':str(p.relative_to(ROOT)),'file_count':len(files),'files':files,'current_summary_as_stored':summary,'source_entry_actual_counts':data}

def main():
    inventory={'schema_version':'1.0','as_of_client_date':'2026-10-22',
       'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
       'scope':'Local read-only actual inventory; no network, no source modification, no new eligibility or forecasts.',
       'databases':[database_inventory(k,p) for k,p in DBS.items()],
       'latest_work_directories':[load_work_directory(p) for p in LATEST_WORK]}
    c=ro(DBS['main'])
    inventory['main_current_bars_by_source']=rows(c,'SELECT source,symbol,adjustment,COUNT(*) rows,COUNT(DISTINCT trade_date) distinct_dates,MIN(trade_date) min_date,MAX(trade_date) max_date FROM current_daily_bars GROUP BY source,symbol,adjustment')
    inventory['main_versioned_bars_by_source']=rows(c,'SELECT source,symbol,adjustment,COUNT(*) rows,COUNT(DISTINCT snapshot_id) snapshots,COUNT(DISTINCT trade_date) distinct_dates,MIN(trade_date) min_date,MAX(trade_date) max_date FROM daily_bars GROUP BY source,symbol,adjustment')
    inventory['main_source_records_by_dataset']=rows(c,'SELECT dataset,COUNT(*) rows,COUNT(DISTINCT row_hash) distinct_payload_hashes,COUNT(DISTINCT reference_date) distinct_reference_dates,MIN(reference_date) min_reference_date,MAX(reference_date) max_reference_date,SUM(publication_time IS NOT NULL AND publication_time!=\'\') publication_field_present FROM current_source_records GROUP BY dataset')
    inventory['main_settings']=rows(c,'SELECT * FROM database_settings')
    inventory['main_coverage_gaps_historical_not_current_overlay']=rows(c,'SELECT * FROM coverage_gaps')
    inventory['main_restricted_source_fields']=rows(c,'SELECT * FROM restricted_source_fields ORDER BY reason,dataset,field_name')
    payloads=collections.defaultdict(list)
    for r in c.execute('SELECT dataset,payload_json FROM current_source_records'):
        payloads[r['dataset']].append(json.loads(r['payload_json']))
    restricted=[]
    for f in inventory['main_restricted_source_fields']:
        p=payloads[f['dataset']]
        restricted.append({**f,'current_rows':len(p),'current_field_present':sum(f['field_name'] in x for x in p),
                           'current_nonnull_actual':sum(x.get(f['field_name']) is not None for x in p),
                           'prohibited_as_historical_feature':True})
    inventory['restricted_field_actual_current_counts']=restricted
    inventory['main_reconciliation_and_version_groups']={
      'fund_flow_all_rows':c.execute('SELECT COUNT(*) FROM normalized_fund_flow').fetchone()[0],
      'fund_flow_distinct_dates':c.execute('SELECT COUNT(DISTINCT trade_date) FROM normalized_fund_flow').fetchone()[0],
      'fund_flow_latest_rows':c.execute('SELECT COUNT(*) FROM latest_available_fund_flow').fetchone()[0],
      'announcement_documents':c.execute('SELECT COUNT(*) FROM announcement_documents').fetchone()[0],
      'announcement_reconciliation_all_versions':c.execute('SELECT COUNT(*) FROM announcement_reconciliation').fetchone()[0],
      'announcement_reconciliation_current':c.execute('SELECT COUNT(*) FROM current_announcement_reconciliation').fetchone()[0],
      'reviewed_historical_source_records':c.execute('SELECT COUNT(*) FROM reviewed_historical_source_records').fetchone()[0],
      'source_records_availability':rows(c,'SELECT availability_status,evidence_type,COUNT(*) rows FROM current_source_records GROUP BY availability_status,evidence_type'),
      'temporal_audit_eligibility':rows(c,'SELECT audit_version,historical_input_eligible,COUNT(*) rows FROM record_temporal_audit GROUP BY audit_version,historical_input_eligible'),
    }
    c.close()
    chip=ro(DBS['chip_observations'])
    inventory['chip_actual_coverage']={
      'observation_groups':rows(chip,'SELECT source_accepted,audit_accepted,COUNT(*) observations,COUNT(DISTINCT actual_date) distinct_actual_dates,MIN(actual_date) min_date,MAX(actual_date) max_date FROM observations GROUP BY source_accepted,audit_accepted'),
      'accepted_repeat_dates':rows(chip,'SELECT actual_date,COUNT(*) observations,COUNT(DISTINCT profit_ratio_pct||\'|\'||average_cost||\'|\'||cost90_low||\'|\'||cost90_high||\'|\'||concentration90_pct||\'|\'||cost70_low||\'|\'||cost70_high||\'|\'||concentration70_pct) distinct_summary_value_sets FROM observations WHERE audit_accepted=1 GROUP BY actual_date HAVING COUNT(*)>1'),
      'complete_bin_rows':chip.execute('SELECT SUM(complete_price_bins) FROM observations').fetchone()[0],
      'historical_input_eligible_rows':chip.execute('SELECT SUM(historical_input_eligible) FROM observations').fetchone()[0],
      'accepted_dates_missing_vs_expected':rows(chip,'SELECT trade_date FROM expected_dates EXCEPT SELECT actual_date FROM observations WHERE audit_accepted=1'),
    }
    chip.close()
    five=ro(DBS['five_priority_observations'])
    source_entries=rows(five,'SELECT * FROM datasets ORDER BY name')
    inventory['five_source_entry_integrity']=[]
    for x in source_entries:
        p=ROOT/x['source_path'];exists=p.exists();sha=digest(p) if exists else None
        actual=five.execute('SELECT COUNT(*) FROM records WHERE dataset=?',(x['name'],)).fetchone()[0]
        inventory['five_source_entry_integrity'].append({**x,'source_exists':exists,'current_source_sha256':sha,'hash_matches':sha==x['source_sha256'],'actual_sqlite_rows':actual,'declared_rows_match':x['rows']==actual})
    groups={}
    allp={}
    for d, in five.execute('SELECT DISTINCT dataset FROM records ORDER BY dataset'):
        ps=[json.loads(r[0]) for r in five.execute('SELECT payload_json FROM records WHERE dataset=? ORDER BY seq',(d,))]
        allp[d]=ps
        groups[d]={'actual_rows':len(ps),'scalar_field_profiles':scalar_profiles(ps)}
    groups['market_industry_snapshots']['source_groups']=group_json(allp['market_industry_snapshots'],['symbol','source','adjustment'],'trade_date')
    groups['market_warmup_snapshots']['source_groups']=group_json(allp['market_warmup_snapshots'],['provider','endpoint','adjustment_flag'],'date')
    e=allp['events']
    groups['events']['event_type_counts']=dict(collections.Counter(r['event_type'] for r in e))
    groups['events']['distinct_economic_episode_ids']=len({r.get('economic_episode_id') for r in e})
    groups['events']['corporate_action_economic_episodes']=len({r.get('economic_episode_id') for r in e if r['event_type']=='corporate_action_date'})
    inventory['five_payload_actual_profiles']=groups
    inventory['five_input_gates']=rows(five,'SELECT * FROM input_gates ORDER BY feature_group')
    five.close()
    inventory['authoritative_entry_points']=[
      {'data_class':'stock_market_latest_20261021','entry':'outputs/五项数据补缺_20261022/五项补缺原始观察.sqlite::records(dataset=market_industry_snapshots, symbol=002414.SZ)','source_file':'work/market_industry_oct22/market_rows_unique.json','date_scope':'2022-01-04..2026-10-21, 1160 dates (242 warmup + 918 research)','boundary':'EM/Tencent, unadjusted/forward modes only; separate source variants; no proof of executability or historical adjustment availability'},
      {'data_class':'stock_market_enriched_until_20261016','entry':'work/market_warmup_finalize_oct22/market_rows_all_endpoints.json','sqlite_copy':'outputs/五项数据补缺_20261022/五项补缺原始观察.sqlite::records(dataset=market_warmup_snapshots)','boundary':'1157 dates, 9 endpoint/adjustment variants, 10413 rows; new Tencent amount/turnover and 58 volume/8 amount/1 turnover strict exceptions retained; no formal PIT factors'},
      {'data_class':'chip_summary_history','entry':'outputs/高德红外数据库/历史筹码采集_20261017/筹码网页原始观察.sqlite::observations WHERE audit_accepted=1','boundary':'923 accepted observations, 915 dates, summaries only; complete bins0; historical_input_eligible0; repeat values do not prove algorithm identity'},
      {'data_class':'chip_repeatability','entry':'work/chip_audit_oct22/records.json','sqlite_copy':'outputs/五项数据补缺_20261022/五项补缺原始观察.sqlite::records(dataset=chip_repeatability_oct22)','boundary':'6 new sessions/window observations over2 dates; versioned evidence, not6 independent forecast samples'},
      {'data_class':'corporate_actions','entry':'work/corporate_actions_refine_oct17/corporate_actions.json','sqlite_copy':'outputs/五项数据补缺_20261022/五项补缺原始观察.sqlite::records(dataset=corporate_actions)','boundary':'3 implementation economic episodes, multiple roles per date; personal receipt/first publication unknown'},
      {'data_class':'non_distribution_decisions','entry':'work/corporate_actions_refine_oct17/non_distribution_decisions.json','boundary':'2 approved annual decisions; not dividend episodes and not proof no other distribution in calendar year'},
      {'data_class':'historical_trade_conditions','entry':'work/conditions_finish_oct22/daily_trade_conditions_915.json','boundary':'915 rows through10/16; monthly evidence only908 dates; actual daily normal/ST0; official limits0; account cost complete0; execution eligible0'},
      {'data_class':'market_and_industry','entry':'work/market_industry_oct22/market_rows_unique.json','boundary':'3 index proxies + stock, 1160dates; sources/adjustments separate; not PIT membership or market breadth'},
      {'data_class':'announcement_catalogue_and_times','entry':'work/events_publication_oct22/announcement_time_ledger_current.json','boundary':'312 identities, current display metadata;80 provider display times changed; first-public certified0; no new PDF in last refresh'},
      {'data_class':'announcement_originals','entry':'outputs/高德红外数据库/高德红外_2023起.sqlite::announcement_documents / announcement_pages / available_announcement_text','boundary':'312 PDFs,4253pages; PDF text/OCR unverified; native+OCR are representations not separate announcement events'},
      {'data_class':'official_policy_and_calendar_samples','entry':'work/events_publication_oct22/normalized_events.json','boundary':'67 role/event rows,59 economic_episode_id values;46 expiry months only5 official month notices+41 derived;3corporate episodes occupy11 date-role rows; policy samples not complete archive'},
      {'data_class':'financial_and_shareholder_provenance','entry':'outputs/高德红外数据库/高德红外_2023起.sqlite::original_report_observations / supplemental_disclosure_observations / shareholder_history_observations / current_source_records','boundary':'Disclosure/report/end dates differ; revisions retained; first-public timing not certified; do not upgrade entire table from selected verified facts'},
      {'data_class':'fund_flow','entry':'outputs/高德红外数据库/高德红外_2023起.sqlite::latest_available_fund_flow','boundary':'122 dates vs240version rows, partial rolling coverage; large/small order buckets not institution identity'},
    ]
    inventory['duplicate_and_sampling_boundaries']=[
      'Source endpoint, adjustment mode, retrieval snapshot and file format are evidence versions, not additional independent market outcomes.',
      'Market-industry11600 =10 source/symbol/adjustment series ×1160days; includes same stock four times and each index twice.',
      'Warmup10413 =9 endpoint/adjustment series ×1157days; newest enriched cutoff10/16 differs from market-series cutoff10/21.',
      'Chip932 attempts include9rejected and923accepted; accepted dates915, excess8 repeats. Five-priority store copies these same932 observations, not new data.',
      'Announcement312 PDFs plus provenance/provider catalogue/page/OCR records refer to same underlying identities; 624 reconciliation version rows currently312.',
      'Corporate-action11 date-role rows refer to3 economic episodes;46derivative dates jointly represent several same-calendar contracts, not six independent events/month.',
      '242 dates before2023 are warmup observations, not extra target research samples. Consecutive/horizon-overlapping returns are not independent.',
      'All versions and rejected evidence remain preserved; choose eligibility with explicit gates rather than deleting history.',
    ]
    inventory['authorization_and_temporal_boundaries']={
      'task_authorization':'User authorized research collection, local organization and preservation; does not authorize purchases, brokerage use, trading, messages or redistribution.',
      'provider_licensing':'No machine-verifiable licensing entitlement or formal vendor data-use contract found in reviewed schemas; public accessibility/source presence does not grant redistribution rights.',
      'retrieved_at':'When locally obtained, not when market participants first could know it.',
      'publication_time':'Present field may be provider display/date normalization; not certified first-publication timestamp.',
      'historical_input_eligible':'Explicit zero flags remain zero. Tables lacking an eligibility column are unreviewed, not implicitly eligible.',
      'reviewed_historical_source_records':'Zero is specific to audited current-source-record view, not a claim every market table has a zero flag or that no raw data exists.',
      'asof_20261022':'No automatic claim all datasets current through10/22; each entry retains actual dates. Conditions/chips through10/16, market through10/21, announcement identity max9/15.',
      'future_return_columns':'Existing forward-return statistics are prohibited feature inputs. Preserve in raw storage only; labels require separate reviewed computation at future horizons.',
      'no_analysis':'No new indicators, probabilities, returns, trading rules or model eligibility calculated by this inventory.',
    }
    for db in inventory['databases']:
        db['sha256_final_after_all_queries']=digest(ROOT/db['path'])
        db['unchanged_after_all_queries']=db['sha256_final_after_all_queries']==db['sha256_before']
    inventory['all_source_databases_unchanged']=all(x['unchanged_after_all_queries'] for x in inventory['databases'])
    assert inventory['all_source_databases_unchanged']
    assert all(x['hash_matches'] and x['declared_rows_match'] for x in inventory['five_source_entry_integrity'])
    (OUT/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
    md=['# 本地数据实际盘点（2026-10-22）','',
        '只读查询三个正式 SQLite，并对三条最新补缺目录逐文件计算 SHA-256。未联网、未操作浏览器、未改已有数据库，未新增历史输入资格。','',
        '| 数据库 | 表 / 视图 | 实际情况 |','|---|---:|---|']
    for x in inventory['databases']:
        md.append(f"| `{x['path']}` | {x['table_count']} / {x['view_count']} | quick_check={x['quick_check']}，SHA-256 前后一致 |")
    md += ['', '当前行情应分两条入口：市场行业快照有1,160日（242预热、918研究），截至10月21日；补充单位与腾讯新端点的行情有1,157日（242预热、915研究），截至10月16日。10,413和11,600均为来源、品种、复权或端点版本行数，不能当独立样本量。','',
      '筹码原库932次尝试，其中923次通过采集验收，覆盖915日；9次失败保留。完整价格档位为0，历史输入资格为0。五项原始库复刻这932次，不是又新增932个样本。六次10月22日复核也只是同日版本观察。','',
      '915行交易条件全未取得执行资格：逐日ST/停复牌未认证、官方日限价0、完整账户成本0。月报正常名称与有成交量均不能替代当日交易状态。','',
      '公告时间账312条，历史最早公开时间认证0；80条供应商展示时间相较旧快照变化。67个事件/日期角色行含59个经济episode标识，其中三次分配占11个角色行。46个到期月份仅5个有逐月官方通知，41个仍是规则推导。','',
      '主库 current_source_records 中，11个已标记的未来收益字段合计318个非空值，禁止作为历史输入。另7个公式/可得性不明字段的当前值逐一列在机器清单，不能擅自解释为已知历史特征。','',
      '源时间、研究日期、公告日、报告期与检索时间分别保留。无资格列的表不是自动通过；来源可访问也不是取得再分发许可。本盘点没有认定任何付费渠道权限。','',
      '全部模式、实际行数、日期列覆盖、资格分布、源快照、重复边界、逐文件哈希和当前权威入口，见同目录 inventory.json。','']
    (OUT/'inventory.md').write_text('\n'.join(md))
    print(json.dumps({'inventory':str(OUT/'inventory.json'),'databases_unchanged':True,'five_source_entries_verified':len(source_entries),'current_forward_return_nonnull_total':sum(x['current_nonnull_actual'] for x in restricted if x['reason']=='forward_return_statistic')},ensure_ascii=False))

if __name__=='__main__': main()
