from pathlib import Path
from html.parser import HTMLParser
import json,hashlib,datetime,sqlite3
r=Path(__file__).resolve().parent
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[]
 def handle_data(self,d):self.parts.append(d)
def read_text(name):
 p=r/name;t=Text();t.feed(p.read_text());return '\n'.join(t.parts)
for stem in ['tushare_distribution_doc','tushare_summary_doc','tushare_permission_doc','quantcoda_docs','quantcoda_methodology','quantcoda_terms']:
 (r/(stem+'_text.txt')).write_text(read_text(stem+'.html'))
req=[x for x in json.loads((r/'requests.json').read_text()) if not x['id'].startswith('bigquant_')]
b=r/'bigquant_chips.html';bh=(r/'bigquant_headers.txt').read_text()
req.insert(0,{'id':'bigquant_chips_doc','url':'https://bigquant.com/data/datasources/cn_stock_chips_distribution','method':'GET','retrieved_at_response_date':'2026-10-15T18:49:55+00:00','http_status':200,'raw_path':b.name,'sha256':hashlib.sha256(b.read_bytes()).hexdigest(),'bytes':b.stat().st_size,'response_headers_raw':'bigquant_headers.txt','authentication_used':False})
req.extend([{'id':'bigquant_web_reader_attempt_'+str(i),'url':'https://bigquant.com/data/datasources/cn_stock_chips_distribution','method':'web.open','error':'Timeout fetching (tool returned 400)','raw_response_saved':False,'authentication_used':False} for i in (1,2)])
(r/'requests.json').write_text(json.dumps(req,ensure_ascii=False,indent=2))
(r/'bigquant_anonymous_ui_observation.json').write_text(json.dumps({'observed_at':'2026-10-15T18:50:00+00:00','url':req[0]['url'],'surface':'Codex in-app browser; anonymous; no login or registration','visible_title':'数据平台 - BigQuant人工智能','dataset':'cn_stock_chips_distribution','table_fields_count':12,'visible_access_label':'订阅数据','tabs':['Table Structure','Document','Use Case','更新记录'],'use_case_tab_opened':True,'use_case_content':'empty in returned accessibility state','actual_002414_values_seen':False,'stock_or_date_query_control_seen':False,'download_control_seen':False,'login_or_purchase_performed':False,'tab_closed':True,'observation_limit':'Anonymous public page only; cannot conclude no paid sample or trial can be supplied.'},ensure_ascii=False,indent=2))
qc=json.loads((r/'quantcoda_capabilities.json').read_text())
endpoint=next(x for x in qc['capabilities'] if x['id']=='distribution')
(r/'supplier_candidates.json').write_text(json.dumps({'as_of':'2026-10-15','symbol':'002414.SZ','start':'2023-01-01','end':'2026-10-15','target_trading_dates':914,'acquired_provider_chip_dates':0,'actual_rows_inserted_to_market_database':0,'supplier_inquiry_status':'unknown; no email read or sent','credentials_used':False,'purchase_made':False,'local_chip_reconstruction_computed':False,'candidates':[
 {'id':'TUSHARE','state':'documented_candidate_no_actual_002414_sample','distribution_url':'https://tushare.pro/document/2?doc_id=294','summary_url':'https://tushare.pro/document/2?doc_id=293','permission_url':'https://tushare.pro/document/1?doc_id=290','estimated_not_account_holdings':True,'claimed_start_year':2018,'full_price_bins_documented':True,'document_example_symbol':'600000.SH','points_conflict':{'api_docs_minimum':5000,'permission_table_tier':10000,'resolved':False},'actual_002414_coverage':None,'anonymous_sample_obtained':False,'next_gate':'Official sample and clarification of permission, local storage, adjustment, algorithm version and historical revisions before any purchase.'},
 {'id':'BIGQUANT','state':'new_native_vendor_estimate_candidate_subscription_no_actual_sample','url':req[0]['url'],'estimated_not_account_holdings':True,'claimed_start_year':2006,'full_price_bins_documented':True,'document_example_symbol':'000002.SZ','document_example_date':'2025-06-23','actual_002414_coverage':None,'anonymous_page_access_label':'订阅数据','algorithm_scope':'Provider estimate using daily unadjusted prices, turnover decay, free-float base; corporate actions considered; maximum 200 price bins; low-weight cutoff uses 0.001% of free float; model not recreated locally.','start_metadata_not_coverage_certification':'Document says 2006 origin; page metadata start timestamp 2025-07-29 is not evidence of earliest 002414 trading date.','anonymous_sample_obtained':False,'price_permission_and_local_sdk_access':None,'next_gate':'Ask supplier for two full-price-bin 002414 samples on 2023-01-03 and 2026-10-15, effective algorithm version, adjustments and 914-date coverage; independently clarify cloud and local SDK rights. No account created.'},
 {'id':'QUANTCODA','state':'summary_only_trial_requires_api_key_not_full_price_distribution','url':'https://quantcoda.com/docs','capability':endpoint,'estimated_not_account_holdings':'not independently certified; upstream and chip algorithm not identified on checked methodology page','full_price_bins_documented':False,'documented_output_fields':['symbol','trade_date','his_low','his_high','cost_5pct','cost_15pct','cost_50pct','cost_85pct','cost_95pct','weight_avg','winner_rate'],'actual_002414_coverage':None,'anonymous_sample_http_status':401,'anonymous_sample_obtained':False,'trial_documentation':'Each unavailable plan endpoint may be tried twice daily with real data, but valid account API Key required. No trial account created.','next_gate':'Only an optional summary source after official account and provenance/coverage clarification; does not close price-bin distribution gap.'}
 ]},ensure_ascii=False,indent=2))
# Evidence checks; these check documentation and access results, never claim market data accuracy.
checks=[]
def ck(name,ok,**details):checks.append(dict(name=name,passed=bool(ok),**details))
for row in req:
 if row.get('raw_path'):
  p=r/row['raw_path'];ck('raw_sha256_'+row['id'],p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'])
t=read_text('tushare_distribution_doc.html');ck('tushare_fields_and_wrong_symbol_sample',all(x in t for x in ['price','percent','600000.SH','2018','5000']))
t=read_text('tushare_permission_doc.html');ck('tushare_points_conflict_still_documented','10000' in t and '筹码' in t)
t=(r/'bigquant_chips_text.txt').read_text();ck('bigquant_native_estimate_doc_not_002414_sample',all(x in t for x in ['2006-01-01','200个价格区间','0.001%','cn_stock_real_bar1d','000002.SZ']) and '002414' not in t)
t=read_text('quantcoda_docs.html');start=t.index('/v1/chips/distribution');end=t.index('/v1/indices/daily',start);section=t[start:end];ck('quantcoda_endpoint_is_summary_not_price_bins',all(x in section for x in ['cost_5pct','cost_95pct','weight_avg','winner_rate']) and 'percent' not in section and 'price' not in section)
qreq=next(x for x in req if x['id']=='quantcoda_anonymous_002414_sample');body=json.loads((r/qreq['raw_path']).read_text());ck('anonymous_002414_request_did_not_bypass_key',qreq['http_status']==401 and 'Missing API key' in body['detail'])
p=Path('outputs/高德红外数据库/高德红外_2023起.sqlite');c=sqlite3.connect('file:'+str(p.resolve())+'?mode=ro',uri=True);count=c.execute('select count(*) from chip_estimates').fetchone()[0];ck('main_chip_table_remains_empty',count==0,rows=count)
result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'all_passed':all(x['passed'] for x in checks),'acquired_002414_chip_dates':0,'target_trading_dates':914,'purpose':'Source/access evidence checks, not certification of market completeness, values, license or strategy.'}
(r/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'checks':len(checks),'passed':sum(x['passed'] for x in checks),'acquired_002414_chip_dates':0},ensure_ascii=False))
