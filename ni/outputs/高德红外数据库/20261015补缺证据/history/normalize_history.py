import sqlite3,json,hashlib,collections
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/'requests.json').read_text())
byname={x['name']:x for x in m}
def raw(name):return json.loads(Path(byname[name]['raw_path']).read_text())
def sha(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
c=sqlite3.connect('file:outputs/高德红外数据库/高德红外_2023起.sqlite?mode=ro',uri=True)
rows=raw('top10_total_history')['result']['data']
latest=raw('top10_total_latest')['sdgd']
hc=raw('holder_count_all')['result']['data']
cs=raw('capital_structure_all')['result']['data']
hc_candidate=collections.defaultdict(list);float_candidate=collections.defaultdict(list)
for r in hc: hc_candidate[r['END_DATE'][:10]].append(r['HOLD_NOTICE_DATE'][:10])
for d,p in c.execute("select reference_date,payload_json from current_source_records where dataset='top10_float'"):
 r=json.loads(p);float_candidate[r['END_DATE'][:10]].append(d)
normalized=[]
for r in rows:
 day=r['END_DATE'][:10]
 normalized.append({'row_hash':sha(r),'symbol':'002414.SZ','holder_scope':'total','reference_date':day,'date_field':'END_DATE','publication_time':None,'historical_input_eligible':False,'source_sha256':byname['top10_total_history']['sha256'],'source_snapshot':'top10_total_history:'+byname['top10_total_history']['sha256'],'reported_periodic':r.get('IS_REPORT')=='1','observation_scope':'periodic_top10' if r.get('IS_REPORT')=='1' else 'nonperiodic_partial_holders_only','within_observation_window':day>='2023-01-01','availability_status':'no_notice_date_in_source_first_publication_unverified','disclosure_date_candidates':{'holder_count_same_period':sorted(set(hc_candidate[day])),'top10_float_same_period':sorted(set(float_candidate[day]))},'disclosure_date_candidates_are_certified':False,'payload':r})
(ROOT/'top10_total_normalized.json').write_text(json.dumps(normalized,ensure_ascii=False,indent=2))
fields=['SECUCODE','SECURITY_CODE','END_DATE','HOLDER_RANK','HOLDER_NAME','SHARES_TYPE','HOLD_NUM','HOLD_NUM_RATIO','HOLD_NUM_CHANGE','CHANGE_RATIO']
main_latest=sorted([{k:r.get(k) for k in fields} for r in rows if r['END_DATE'][:10]=='2026-06-30'],key=lambda x:x['HOLDER_RANK'])
other_latest=sorted([{k:r.get(k) for k in fields} for r in latest],key=lambda x:x['HOLDER_RANK'])
periodic=[r for r in rows if r['IS_REPORT']=='1'];partial=[r for r in rows if r['IS_REPORT']!='1']
counts=collections.Counter(r['END_DATE'][:10] for r in periodic)
checks={
 'all_raw_sha256_match':all(hashlib.sha256(Path(x['raw_path']).read_bytes()).hexdigest()==x['sha256'] for x in m if x.get('raw_path')),
 'top10_one_page_complete_reported_count':len(rows)==raw('top10_total_history')['result']['count'] and raw('top10_total_history')['result']['pages']==1,
 'issuer_all_002414':all(r['SECUCODE']=='002414.SZ' for r in rows),
 'unique_period_rank_name':len(rows)==len({(r['END_DATE'],r['HOLDER_RANK'],r['HOLDER_NAME']) for r in rows}),
 'periodic_15_by_10':len(counts)==15 and all(v==10 for v in counts.values()),
 'partial_20_are_not_full_top10':len(partial)==20 and len({r['END_DATE'][:10] for r in partial})==10,
 'pageSDGD_latest_10_all_selected_fields_match':main_latest==other_latest,
 'holder_count_60_rows_single_page_complete':len(hc)==60 and raw('holder_count_all')['result']['pages']==1,
 'capital_41_rows_single_page_complete':len(cs)==41 and raw('capital_structure_all')['result']['pages']==1,
 'historical_features_all_unapproved':all(not r['historical_input_eligible'] and r['publication_time'] is None for r in normalized),
 'holder_percent_rounding_within_0_005_pct':all(abs(Decimal(str(r['HOLD_NUM']))/Decimal(str(r['TOTAL_SHARES_NUM']))*100-Decimal(str(r['HOLD_NUM_RATIO'])))<=Decimal('0.00501') for r in rows),
}
# Values are tied to already stored extracted original text. This does not certify a full original table or its first publication time.
evidence=[]
for art,day,holder,value,needle in [
 ('AN202601081816849670','2026-01-07','黄立',1134418061,'113,441.8061'),
 ('AN202603101820462832','2026-02-25','黄立',1094583514,'109,458.3514'),
 ('AN202603101820462832','2026-02-25','武汉市高德电气有限公司',1554198364,'155,419.8364')]:
 pages=c.execute('select page_number,text,source_sha256 from announcement_pages where art_code=?',(art,)).fetchall()
 matches=[(p,t,h) for p,t,h in pages if needle in t]
 doc=c.execute('select notice_date,url,sha256 from announcement_documents where art_code=?',(art,)).fetchone()
 rr=[r for r in normalized if r['reference_date']==day and r['payload']['HOLDER_NAME']==holder]
 assert len(rr)==1 and rr[0]['payload']['HOLD_NUM']==value and matches
 p,t,h=matches[0];pos=t.index(needle)
 evidence.append({'row_hash':rr[0]['row_hash'],'reference_date':day,'holder':holder,'provider_holding_shares':value,'art_code':art,'pdf_page':p,'source_sha256':h,'source_url':doc[1],'provider_notice_date':doc[0],'evidence_kind':'stored_original_text_exact_numeric_token_match_not_visual_table_certification','evidence_token_in_10k_shares':needle,'excerpt':t[max(0,pos-100):pos+150],'historical_input_eligible':False,'first_publication_time':'unverified','warning':'Report date/signature date and provider notice date must remain separate; trade/end date does not establish publication.'})
(ROOT/'nonperiodic_original_text_links.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
summary={'checked_at_date':'2026-10-15','requests':len(m),'checks':checks,'all_checks_passed':all(checks.values()),'top10_total':{'rows':len(rows),'observation_dates':len({r['END_DATE'][:10] for r in rows}),'periodic_rows':len(periodic),'periodic_dates':len(counts),'baseline_2022_12_31_rows':sum(r['END_DATE'][:10]=='2022-12-31' for r in rows),'within_2023_onward_observation_rows':sum(r['END_DATE'][:10]>='2023-01-01' for r in rows),'partial_nonperiodic_rows':len(partial),'partial_nonperiodic_dates':len({r['END_DATE'][:10] for r in partial}),'min_observation_date':min(r['END_DATE'][:10] for r in rows),'max_observation_date':max(r['END_DATE'][:10] for r in rows),'source_has_notice_date':any('NOTICE_DATE' in r for r in rows),'selected_latest_cross_endpoint_rows':len(latest),'original_text_links_only':len(evidence)},'holder_count':{'provider_rows':len(hc),'disclosure_2023_onward':sum(r['HOLD_NOTICE_DATE'][:10]>='2023-01-01' for r in hc),'latest_period':max(r['END_DATE'][:10] for r in hc),'latest_provider_disclosure':max(r['HOLD_NOTICE_DATE'][:10] for r in hc),'finer_interval_found_2023_onward':False,'new_rows_vs_existing_2023_onward':0},'capital':{'provider_rows':len(cs),'latest_period':max(r['END_DATE'][:10] for r in cs),'new_provider_periods_vs_existing':0},'suspension':{'daily_market_schema_example_rows':15,'code_exact_today_error':byname['suspension_code_equality'].get('message'),'without_datetime_error':byname['suspension_code_without_datetime'].get('message'),'history_complete':False,'no_event_certified':False}}
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))
