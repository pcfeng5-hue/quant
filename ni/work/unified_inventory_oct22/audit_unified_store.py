#!/usr/bin/env python3
"""Independent, read-only source-to-store QA; compare original facts, not build assertions."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import urllib.parse

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=pathlib.Path(__file__).resolve().parent
DB=ROOT/'outputs/统一数据底座_20261022/统一数据底座.sqlite'
QDB=DB.with_name('受限字段隔离.sqlite')
MAIN=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON');return c
def read(p):return json.loads((ROOT/p).read_text())
def canon(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def scalar(c,q,args=()):return c.execute(q,args).fetchone()[0]
def dicts(c,q,args=()):return [dict(r) for r in c.execute(q,args)]
def walk(o,blocked,path='$',decode_strings=False):
    if isinstance(o,dict):
        for k,v in o.items():
            if k in blocked:yield (path+'.'+k,k,v)
            else:yield from walk(v,blocked,path+'.'+k,decode_strings)
    elif isinstance(o,list):
        for i,v in enumerate(o):yield from walk(v,blocked,path+f'[{i}]',decode_strings)
    elif decode_strings and isinstance(o,str) and o[:1] in '{[':
        try:v=json.loads(o)
        except (ValueError,TypeError):return
        yield from walk(v,blocked,path+'<encoded_json>',decode_strings)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output-prefix',default='unified_store_audit');args=ap.parse_args()
    before={str(p.relative_to(ROOT)):sha(p) for p in [DB,QDB,MAIN]}
    c=ro(DB);q=ro(QDB);old=ro(MAIN)
    result={'audit_scope':'independent local source comparison; read-only; no browser, network, model approval or modifications',
        'as_of_client_date':'2026-10-22','created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'sha256_before':before,'checks':[],'findings':[],'semantics':[]}
    def check(name,passed,details=None):result['checks'].append({'check':name,'passed':bool(passed),'details':details})
    check('all_databases_quick_check_ok',all(scalar(z,'PRAGMA quick_check')=='ok' for z in [c,q,old]))
    meta={r['key']:json.loads(r['value_json']) for r in c.execute('SELECT * FROM metadata')}
    result['build_metadata']=meta
    check('market_total_37714',scalar(c,'SELECT COUNT(*) FROM market_daily')==37714)
    collection_counts=dict((r[0],r[1]) for r in c.execute('SELECT collection,COUNT(*) FROM market_daily GROUP BY collection'))
    check('market_collection_accounting',collection_counts=={'legacy_main':15701,'warmup_oct16':10413,'market_industry_oct21':11600},collection_counts)
    old_rows=[dict(r) for r in old.execute('SELECT * FROM daily_bars')]
    warm=read('work/market_warmup_finalize_oct22/market_rows_all_endpoints.json')
    latest=read('work/market_industry_oct22/market_rows_unique.json')
    sources={'legacy_main':old_rows,'warmup_oct16':warm,'market_industry_oct21':latest}
    errors=[]
    count=0
    for r in c.execute('SELECT * FROM market_daily'):
        a=sources[r['collection']][r['input_row_index']]
        expected={k:a[k] for k in ['symbol','open','high','low','close']}
        expected['trade_date']=a.get('trade_date',a.get('date'))
        expected['adjustment']=str(a.get('adjustment_flag',a.get('adjustment')))
        expected['volume_native']=a.get('volume',a.get('volume_provider_native',a.get('volume_raw')))
        expected['amount_cny']=a.get('amount',a.get('amount_cny',a.get('amount_raw')))
        expected['turnover_pct']=a.get('turnover',a.get('turnover_percent',a.get('turnover_raw')))
        for k,v in expected.items():
            count+=1
            if r[k]!=v:errors.append({'observation_id':r['observation_id'],'field':k,'source':v,'typed':r[k]})
    check('all_market_source_values_exact',not errors,{'field_comparisons':count,'errors':errors[:30],'error_count':len(errors)})
    identifiers=dicts(c,'SELECT * FROM instrument_identifiers')
    expected_ids={'002414.SZ':'002414.SZ','1.000001':'000001.SH','0.399001':'399001.SZ','000001.SH':'000001.SH','399001.SZ':'399001.SZ','399967.SZ':'399967.SZ'}
    check('all_original_symbols_have_correct_canonical_and_price_unit',all(r['symbol'] in expected_ids and r['canonical_symbol']==expected_ids[r['symbol']] and r['price_unit']==('CNY_per_share' if r['canonical_symbol']=='002414.SZ' else 'index_points') for r in c.execute('SELECT symbol,canonical_symbol,price_unit FROM market_daily')) and {r['provider_symbol']:r['canonical_symbol'] for r in identifiers}==expected_ids,identifiers)
    snapshots={r['snapshot_id']:dict(r) for r in old.execute('SELECT * FROM source_snapshots')}
    legacy_index=list(c.execute("SELECT * FROM market_daily WHERE collection='legacy_main' AND symbol IN ('1.000001','0.399001')"))
    check('legacy_index_provider_correct_by_original_url_domain',all(r['provider']==('eastmoney' if urllib.parse.urlparse(snapshots[r['snapshot_key']]['url']).hostname.endswith('eastmoney.com') else 'tencent') for r in legacy_index),{'legacy_index_source_rows':len(legacy_index),'endpoint_and_symbol_preserved':True})
    latest_em_raw={r['trade_date']:r for r in latest if r['symbol']=='002414.SZ' and r['source']=='eastmoney' and r['adjustment']=='0'}
    ref=[dict(r) for r in c.execute('SELECT * FROM stock_raw_reference ORDER BY trade_date')]
    check('stock_raw_reference_exact_dates_and_close',len(ref)==1160 and all(r['trade_date'] in latest_em_raw and r['close']==latest_em_raw[r['trade_date']]['close'] for r in ref))
    check('reference_split_918_research_242_warmup',sum(r['trade_date']<'2023-01-01' for r in ref)==242 and sum(r['trade_date']>='2023-01-01' for r in ref)==918)
    check('market_reference_preserves_explicit_source',scalar(c,"SELECT COUNT(*) FROM market_reference WHERE collection!='market_industry_oct21' OR provider!='eastmoney'")==0)
    approved=scalar(c,'SELECT COUNT(*) FROM approved_market_inputs')+scalar(c,'SELECT COUNT(*) FROM approved_chip_inputs')
    check('reference_not_model_approval',approved==0 and scalar(c,'SELECT COUNT(*) FROM market_reference WHERE model_input_approved!=0')==0)
    old_cond={r['trade_date']:r for r in read('work/conditions_finish_oct22/daily_trade_conditions_915.json')}
    conditions=[dict(r) for r in c.execute('SELECT * FROM trade_conditions ORDER BY trade_date')]
    check('conditions_915_payloads_unchanged',len(conditions)==915 and all(json.loads(r['payload_json'])==old_cond[r['trade_date']] for r in conditions))
    check('conditions_all_current_bars_available',all(r['current_bar_available']==1 for r in conditions))
    last=next(r for r in conditions if r['trade_date']=='2026-10-16')
    check('oct16_context_supplement_preserves_original',last['current_bar_available']==1 and last['original_bar_available']==0 and json.loads(last['payload_json'])['unadjusted_daily_bar_available'] is False)
    first=conditions[0]
    check('first_previous_close_matches_warmup',first['trade_date']=='2023-01-03' and first['previous_close_date']=='2022-12-30' and first['previous_close_unadjusted_candidate']==latest_em_raw['2022-12-30']['close'],{k:first[k] for k in ['trade_date','previous_close_date','previous_close_unadjusted_candidate','limit_reference_price']})
    check('conditions_no_upgrade_to_official_limits_or_executability',all(r['official_upper_limit'] is None and r['official_lower_limit'] is None and r['limit_reference_price'] is None and r['official_normal_state'] is None and r['execution_eligible']==0 and r['cost_model_complete']==0 for r in conditions))
    check('exdate_reference_not_naively_computed',all(r['limit_reference_price'] is None for r in conditions if r['ex_rights_date']))
    restricted=meta['restricted_field_definitions'];blocked={r['field_name'] for r in restricted}
    remaining=[]
    for r in c.execute('SELECT dataset_id,seq,payload_json FROM source_records'):
        for hit in walk(json.loads(r['payload_json']),blocked,decode_strings=True):
            remaining.append({'dataset_id':r['dataset_id'],'seq':r['seq'],'path':hit[0]})
    check('blocked_field_keys_absent_even_in_encoded_source_json',not remaining,{'hits':remaining[:20],'rows_scanned':scalar(c,'SELECT COUNT(*) FROM source_records')})
    exp=collections.Counter()
    expected_clean={}
    def remove(o):
        if isinstance(o,dict):return {k:remove(v) for k,v in o.items() if k not in blocked}
        if isinstance(o,list):return [remove(v) for v in o]
        return o
    for i,r in enumerate(old.execute('SELECT * FROM source_records')):
        row=dict(r);p=json.loads(row.pop('payload_json'))
        for path,k,v in walk(p,blocked):
            exp[(r['dataset'],r['row_hash'],path,k,canon(v),'outputs/高德红外数据库/高德红外_2023起.sqlite')]+=1
        expected_clean[i]={**row,'payload':remove(p)}
    actual=collections.Counter((r['dataset'],r['source_record_id'],r['json_path'],r['field_name'],canon(json.loads(r['value_json'])),r['source_input']) for r in q.execute('SELECT * FROM restricted_values'))
    check('all_restricted_cells_recoverable_exact_multiset',exp==actual,{'expected_cells':sum(exp.values()),'actual_cells':sum(actual.values()),'missing_cells':sum((exp-actual).values()),'unexpected_cells':sum((actual-exp).values())})
    legacy_records=list(c.execute("SELECT seq,payload_json FROM source_records WHERE dataset_id='legacy_auxiliary' ORDER BY seq"))
    check('legacy4094_clean_payloads_and_wrapper_exact',len(legacy_records)==4094 and all(json.loads(r['payload_json'])==expected_clean[r['seq']] for r in legacy_records))
    qstats=dicts(q,"SELECT reason,COUNT(*) cells,SUM(value_json='null') null_cells FROM restricted_values GROUP BY reason")
    result['quarantine_cell_counts']=qstats
    result['quarantine_distinct_cell_tuples']=len(actual)
    result['quarantine_duplicate_cells']=sum(actual.values())-len(actual)
    check('quarantine6133_is_cells_not_labels',sum(x['cells'] for x in qstats)==6133)
    check('filings312_pages4253_finance135',scalar(c,'SELECT COUNT(*) FROM filings')==312 and scalar(c,'SELECT COUNT(*) FROM document_pages')==4253 and scalar(c,'SELECT COUNT(*) FROM financial_report_observations')==135)
    old_pages={tuple(r) for r in old.execute('SELECT * FROM announcement_pages')}
    new_pages={tuple(r) for r in c.execute('SELECT * FROM document_pages')}
    check('all_document_page_records_exact',old_pages==new_pages)
    check('all_financial_original_observations_exact',{tuple(r) for r in old.execute('SELECT * FROM original_report_observations')}=={tuple(r) for r in c.execute('SELECT * FROM financial_report_observations')})
    ev=[dict(r) for r in c.execute('SELECT * FROM events')]
    ev_orig={r['event_id']:r for r in read('work/events_publication_oct22/normalized_events.json')}
    check('events67_episode59_original_payloads_exact',len(ev)==67 and len({r['economic_episode_id'] for r in ev})==59 and all(json.loads(r['payload_json'])==ev_orig[r['event_id']] for r in ev))
    check('event_first_publication_and_model_gates_preserved',all(r['first_publication_time'] is None and r['earliest_model_use_time'] is None and r['model_input_approved']==0 for r in ev))
    check('three_distributions_not11_distinct_episodes',len({r['economic_episode_id'] for r in ev if r['event_type']=='corporate_action_date'})==3 and sum(r['event_type']=='corporate_action_date' for r in ev)==11)
    # Check concrete local files and their hashes rather than relying on previous summaries.
    assets=[dict(r) for r in c.execute('SELECT * FROM file_assets')]
    missing=[];changed=[]
    for r in assets:
        p=ROOT/r['project_relative_path']
        if not p.is_file():missing.append(r['project_relative_path'])
        elif p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:changed.append(r['project_relative_path'])
    check('all_indexed_file_assets_exist_and_match_current_hash',not missing and not changed,{'files':len(assets),'missing':missing,'changed':changed})
    result['assets_changed_since_prior_audit']=[{'path':r['project_relative_path'],'before_sha256':r['prior_audit_sha256'],'indexed_sha256':r['sha256']} for r in assets if r['prior_audit_sha256']!=r['sha256']]
    # Typed market references must all retain an exact local source and recoverable timestamp.
    reqs=collections.defaultdict(list)
    for r in c.execute('SELECT * FROM source_requests'):reqs[r['source_sha256']].append(dict(r))
    temporal=[]
    for collection in collection_counts:
        rs=list(c.execute('SELECT * FROM market_daily WHERE collection=?',(collection,)))
        sha_missing=sum(r['source_sha256'] not in reqs for r in rs)
        typed_missing=sum(r['retrieved_at'] is None for r in rs)
        recoverable=sum(r['retrieved_at'] is None and any(s['retrieved_at'] for s in reqs[r['source_sha256']]) for r in rs)
        unknown=sum(r['retrieved_at'] is None and not any(s['retrieved_at'] for s in reqs[r['source_sha256']]) for r in rs)
        temporal.append({'collection':collection,'rows':len(rs),'no_request_sha_reference':sha_missing,'typed_retrieved_at_missing':typed_missing,'missing_but_recoverable_from_request':recoverable,'time_unrecoverable':unknown})
    result['market_temporal_reference_checks']=temporal
    check('all_market_source_sha_references_resolve',all(r['no_request_sha_reference']==0 for r in temporal))
    check('all_market_typed_retrieval_timestamps_populated',all(r['typed_retrieved_at_missing']==0 for r in temporal),temporal)
    market_manifest_requests=[]
    for name in ['work/market_industry_oct22/manifest.json','work/market_industry_oct22/qfq_supplement_manifest.json']:
        market_manifest_requests.extend(read(name)['results'])
    finished_by_key={(r['id'],r['sha256']):r.get('finished_at_utc') for r in market_manifest_requests if r.get('sha256')}
    latest_time_errors=[]
    for r in c.execute("SELECT observation_id,source_request_id,source_sha256,retrieved_at FROM market_daily WHERE collection='market_industry_oct21'"):
        expected=finished_by_key.get((r['source_request_id'],r['source_sha256']))
        if expected is None or r['retrieved_at']!=expected:latest_time_errors.append(dict(r,expected=expected))
    check('latest11600_retrieval_is_manifest_finished_time',not latest_time_errors,{'errors':latest_time_errors[:10],'error_count':len(latest_time_errors)})
    warm_time_errors=[]
    for r in c.execute("SELECT input_row_index,retrieved_at FROM market_daily WHERE collection='warmup_oct16'"):
        if r['retrieved_at']!=warm[r['input_row_index']]['retrieved_at_utc']:warm_time_errors.append(dict(r))
    check('warmup10413_retrieval_exact_source_literal',not warm_time_errors)
    check('all_request_retrieval_times_present',scalar(c,'SELECT COUNT(*) FROM source_requests WHERE retrieved_at IS NULL')==0)
    # All typed chips must reference their original observation, including rejected attempts.
    chips=[dict(r) for r in c.execute('SELECT * FROM chip_observations')]
    check('chip_accepted_dates_and_gates',len({r['actual_date'] for r in chips if r['collection']=='full_capture' and r['accepted_capture']})==915 and all(r['complete_price_bins']==0 and r['model_input_approved']==0 for r in chips))
    check('chip_accepted_capture_dates_synchronized',all(r['actual_date']==r['kline_date'] for r in chips if r['accepted_capture']))
    expected_chip_payloads=[]
    for collection,path,key in [('full_capture','work/chip_full_capture_oct17/records.json',None),('round2','work/chip_repeatability_round2_oct16/ui/records.json','records'),('refine_oct17','work/chip_refine_first3_oct17/records.json',None),('repeat_oct22','work/chip_audit_oct22/records.json',None)]:
        content=read(path);rr=content[key] if key else content
        expected_chip_payloads.extend(canon(r) for r in rr)
    round1=read('outputs/高德红外数据库/网页筹码核验_20261016/核验记录.json')['observations']
    stored_payloads=collections.Counter(canon(json.loads(r['payload_json'])) for r in chips)
    base_expected=collections.Counter(expected_chip_payloads)
    check('all950_standard_chip_attempt_payloads_preserved',not (base_expected-stored_payloads),{'base_source_observations':sum(base_expected.values())})
    round1_typed=[json.loads(r['payload_json']) for r in chips if r['collection']=='round1']
    round1_originals_preserved=all(any(all(p.get(k)==v for k,v in r.items()) and set(p)-set(r)<=set(['id','expected','accepted','values']) for p in round1_typed) for r in round1)
    check('round1_four_original_field_sets_preserved_with_normalization',round1_originals_preserved and len(round1_typed)==4,{'round1_source_count':len(round1),'typed_rows':len(round1_typed),'extra_derived_fields':['id','expected','accepted','values']})
    chip_numeric_errors=[]
    for r in chips:
        p=json.loads(r['payload_json']);v=p['values']
        l90,h90=map(float,v[3].split('-'));l70,h70=map(float,v[5].split('-'))
        expected={'actual_date':p.get('date',v[0]),'profit_ratio_pct':float(v[1].rstrip('%')),'average_cost_display':float(v[2]),'cost90_low':l90,'cost90_high':h90,'concentration90_pct':float(v[4].rstrip('%')),'cost70_low':l70,'cost70_high':h70,'concentration70_pct':float(v[6].rstrip('%'))}
        for k,value in expected.items():
            if r[k]!=value:chip_numeric_errors.append({'observation_id':r['observation_id'],'field':k,'expected':value,'typed':r[k]})
    check('all954_chip_typed_values_exact_payload',len(chips)==954 and not chip_numeric_errors,{'typed_rows':len(chips),'errors':chip_numeric_errors[:10]})
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'chip_evidence_files' not in tables:
        check('dedicated_chip_evidence_files_table_present',False)
        result['findings'].append({'severity':'needs_fix','topic':'chip_file_lineage','details':'v1 round2 evidence_directory is flat filename stem, not directory; dedicated exact file paths needed. Round1 remains generic only.'})
    else:
        schema=dicts(c,'PRAGMA table_info(chip_evidence_files)')
        evidence=[dict(r) for r in c.execute('SELECT * FROM chip_evidence_files')]
        result['chip_evidence_files_schema']=schema
        result['chip_evidence_files_count']=len(evidence)
        check('dedicated_chip_evidence_files_table_present',len(evidence)>0)
        evidence_errors=[];missing_files=[]
        chip_by_id={r['observation_id']:r for r in chips}
        for e in evidence:
            p=ROOT/e['project_relative_path']
            if e['exists_locally']:
                if not p.is_file() or sha(p)!=e['sha256']:
                    evidence_errors.append(e)
            else:
                missing_files.append(e)
                if p.exists() or e['sha256'] is not None or chip_by_id[e['observation_id']]['accepted_capture']:
                    evidence_errors.append(e)
        check('chip_evidence_paths_and_hashes_exact',not evidence_errors,{'errors':evidence_errors[:20],'present_files':len(evidence)-len(missing_files),'missing_marked_files':missing_files})
        check('accepted_chips_have_linked_evidence',all(any(e['observation_id']==r['observation_id'] and e['exists_locally'] for e in evidence) for r in chips if r['accepted_capture']))
        check('only_rejected_round2_attempt_has_missing_evidence',len(missing_files)==3 and {e['observation_id'] for e in missing_files}=={'round2:R1_pan_later'})
    # Units must be preserved without silently turning unknown scope into validation.
    result['market_unit_profiles']=dicts(c,'SELECT collection,symbol,volume_unit,amount_unit,turnover_unit,COUNT(*) rows FROM market_daily GROUP BY collection,symbol,volume_unit,amount_unit,turnover_unit')
    check('nonempty_market_unit_labels',scalar(c,"SELECT COUNT(*) FROM market_daily WHERE volume_unit IS NULL OR (amount_cny IS NOT NULL AND amount_unit IS NULL) OR (turnover_pct IS NOT NULL AND turnover_unit IS NULL)")==0)
    actual_counts={r[0]:scalar(c,'SELECT COUNT(*) FROM "'+r[0]+'"') for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check('metadata_table_counts_match_actual',meta['build']['table_counts']==actual_counts,{'stored':meta['build']['table_counts'],'actual':actual_counts})
    gate_errors=[]
    for t in actual_counts:
        names={r['name'] for r in c.execute('PRAGMA table_info("'+t+'")')}
        if 'model_input_approved' in names and scalar(c,'SELECT COUNT(*) FROM "'+t+'" WHERE model_input_approved IS NULL OR model_input_approved!=0'):
            gate_errors.append(t)
    check('all_explicit_typed_model_gates_remain_zero',not gate_errors)
    check('all_foreign_key_references_valid',not list(c.execute('PRAGMA foreign_key_check')))
    result['semantics']=[
      'market_reference and stock references are explicit browsing selections; model_input_approved remains0. Source conflict flags are not recommendations.',
      '37714 is version/source rows, not independent outcomes. 1160dates include242warmup; research dates918, not918 independent trials.',
      'previous_close_unadjusted_candidate is raw previous close only; ex-rights exchange reference and official daily limits remain null.',
      '6133 quarantined cells include3054 duplicated tuples, unknown-formula fields, and one null; not6133 result labels or independent samples.',
      'retrieved_at is acquisition metadata, not first publication. Current official notice existence does not prove a historical pre-event timestamp.',
      'Names amount_cny/turnover_pct express normalized locations; accompanying source unit labels keep unverified index scope/definitions visible.',
      '5390file index verifies its registered scope, not a proof every project file or all historical market data is covered.',
      'Financial numeric facts and page/OCR text retain existing verification boundaries; no whole-dataset historical input approval follows from exact copying.',
    ]
    c.close();q.close();old.close()
    after={str(p.relative_to(ROOT)):sha(p) for p in [DB,QDB,MAIN]}
    result['sha256_after']=after
    check('all_audited_databases_unchanged_during_audit',before==after)
    result['checks_passed']=sum(r['passed'] for r in result['checks'])
    result['checks_total']=len(result['checks'])
    result['all_checks_passed']=all(r['passed'] for r in result['checks'])
    (OUT/(args.output_prefix+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    md=['# 统一数据底座独立只读核验','',f"核验日期：2026-10-22。通过 {result['checks_passed']} / {result['checks_total']} 项。",'',
        f"主统一库 SHA-256：`{before[str(DB.relative_to(ROOT))]}`",'',
        '逐行与原数据库/JSON核对行情价格、成交量、成交额、换手率；独立核对条件原载荷、历史页面、财务事实、事件与受限字段隔离的全量多重集合。未联网，未改数据库。','',
        '| 检查 | 结果 |','|---|---|']
    for r in result['checks']:md.append('| '+r['check']+' | '+('通过' if r['passed'] else '待修复')+' |')
    md+=['','语义边界：','']+['- '+s for s in result['semantics']]
    (OUT/(args.output_prefix+'.md')).write_text('\n'.join(md)+'\n')
    print(json.dumps({'audit':str(OUT/(args.output_prefix+'.json')),'checks_passed':result['checks_passed'],'checks_total':result['checks_total'],'failed':[r['check'] for r in result['checks'] if not r['passed']],'hashes_unchanged':before==after},ensure_ascii=False))
if __name__=='__main__':main()
