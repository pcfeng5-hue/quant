import pathlib,json,re,html,hashlib,datetime,calendar
P=pathlib.Path(__file__).resolve().parent
ROOT=P.parents[1]
CUTOFF='2026-10-15'
def save(n,x):(P/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def text(x):
 s=(P/x['raw_path']).read_text(encoding='utf-8',errors='replace');s=re.sub(r'<script\b.*?</script>',' ',s,flags=re.S|re.I);s=html.unescape(re.sub('<[^>]+>',' ',s));return re.sub(r'\s+',' ',s)
ss=[]
for fn in ['products_manifest.json','final_manifest.json','mechanism_manifest.json','probe_cn_results.json']:
 for x in json.load(open(P/fn)):
  x=dict(x);x['accepted']=bool(x.get('accepted','error_page/' not in x.get('final_url','')) and x.get('sha256'))
  if x.get('raw_path') and not x['raw_path'].startswith('raw/'):
   old=P/x['raw_path'];new='raw/'+x['sha256']+'.html';(P/new).write_bytes(old.read_bytes());x['raw_path']=new
  ss.append(x)
save('source_manifest.json',ss)
products=dict(zip(['hs300','sz50gzqh','zz500','zz1000','hs300gzqq','zz1000gzqq','sz50gzqq'],['IF','IH','IC','IM','IO','MO','HO']))
rules=[]
for x in ss:
 slug=x['url'].split('/')[-1].removesuffix('.html')
 if slug not in products or not x['accepted']:continue
 t=text(x);code=products[slug]
 assert '最后交易日' in t and '第三个' in t and '现金交割' in t and '国家法定假日顺延' in t
 rules.append({'instrument':code,'market':'CFFEX','instrument_type':'index_futures' if code in ['IF','IH','IC','IM'] else 'index_options','rule':'third_friday_of_expiry_month_next_trading_day_if_holiday_or_no_trading','settlement_method':'cash','delivery_or_expiry_same_as_last_trade_date':True,'source_level':'official_current_contract_html','source_url':x['url'],'source_sha256':x['sha256'],'raw_path':x['raw_path'],'retrieved_at':x['retrieved_at'],'rule_publication_date':None,'effective_from':None,'effective_date_verified':False,'historical_rule_change_audit_complete':False,'notes':'Current HTML contract fields verified. Effective date not stated on this page; do not claim complete historical rule-version audit. Abnormal no-trading postponement also stated in acquired monthly notice.'})
save('contract_rules.json',rules)
notices=[]
for x in ss:
 if '/cn/jystz/20' not in x['url'] or not x['accepted']:continue
 t=text(x)
 if not all(re.search(code+r'\d{4}',t) for code in ['IF','IH','IC','IM','IO','MO','HO']):continue
 match=re.search(r'最后交易日为(\d{4})年(\d{1,2})月(\d{1,2})日',t)
 subtype='advance_reminder'
 if not match:match=re.search(r'合约于(\d{4})年(\d{1,2})月(\d{1,2})日进行交割',t);subtype='actual_delivery_result'
 assert match,x['url']
 y,m,d=map(int,match.groups());dt=datetime.date(y,m,d).isoformat();month=dt[:7];pt=re.search(r'<div class="fxleft"><a>(\d{4}-\d{2}-\d{2})</a>',(P/x['raw_path']).read_text()).group(1)
 notices.append({'month':month,'event_date':dt,'event_type':'CFFEX_index_derivatives_expiry_delivery','applicable_instruments':['IF','IH','IC','IM','IO','MO','HO'],'contract_month_code':f'{y%100:02d}{m:02d}','notice_kind':subtype,'source_level':'official_monthly_notice','source_url':x['url'],'publication_date':pt,'publication_time':None,'first_publication_time_certified':False,'retrieved_at':x['retrieved_at'],'source_sha256':x['sha256'],'raw_path':x['raw_path'],'event_occurred_by_cutoff':dt<=CUTOFF,'historical_input_eligible':False})
notices.sort(key=lambda x:x['month']);save('verified_monthly_notices.json',notices)
cal_path=ROOT/'outputs/高德红外数据库/official_calendar_2023_to_20261015.json';cal_bytes=cal_path.read_bytes();days=json.loads(cal_bytes);cal={x['trade_date']:x for x in days};opendays=sorted(k for k,v in cal.items() if v['is_scheduled_open'])
by={x['month']:x for x in notices};events=[];future=[]
for y in range(2023,2027):
 for m in range(1,13):
  if y==2026 and m>10:break
  third=datetime.date(y,m,1);third+=datetime.timedelta(days=(4-third.weekday())%7+14);date0=third.isoformat();month=date0[:7];covered=date0 in cal
  if covered:
   following=next((k for k in opendays if k>=date0),None)
   if not following:raise ValueError('No covered next scheduled open '+date0)
  else:following=date0
  rec={'event_id':'CFFEX-index-expiry-'+month,'month':month,'event_type':'CFFEX_index_derivatives_expiry_delivery','instruments':['IF','IH','IC','IM','IO','MO','HO'],'contract_codes':[code+f'{y%100:02d}{m:02d}' for code in ['IF','IH','IC','IM','IO','MO','HO']],'third_friday_formula_date':date0,'event_date_candidate':following,'holiday_roll_candidate':following!=date0,'source_level':'rule_derived_candidate','official_monthly_notice_verified':False,'exchange_holiday_calendar_verified':False,'underlying_equity_calendar_covered':covered,'calendar_source_path':str(cal_path),'calendar_sha256':hashlib.sha256(cal_bytes).hexdigest(),'calendar_scope':'SSE,SZSE scheduled holidays; CFFEX-specific historical emergency exceptions not certified','rule_sources':[r['source_url'] for r in rules],'historical_input_eligible':False,'event_occurred_by_cutoff':following<=CUTOFF,'price_or_flow_analysis_performed':False}
  if month in by:
   n=by[month];rec.update(event_date=n['event_date'],source_level='official_monthly_notice',official_monthly_notice_verified=True,notice_source=n['source_url'],notice_sha256=n['source_sha256'],notice_publication_date=n['publication_date'],notice_kind=n['notice_kind']);assert n['event_date']==following
  if rec['event_occurred_by_cutoff']:events.append(rec)
  else:future.append(rec)
save('historical_expiry_calendar_candidates.json',events);save('future_expiry_calendar_candidates.json',future)
checks=[]
def ck(n,v,d=None):checks.append({'name':n,'passed':bool(v),'detail':d})
ck('seven_contract_rules',len(rules)==7)
ck('all_acquired_raw_hashes_match',all(hashlib.sha256((P/x['raw_path']).read_bytes()).hexdigest()==x['sha256'] for x in ss if x.get('raw_path')))
ck('four_official_verified_months',len(notices)==4)
ck('45_historical_months_unique',len(events)==45 and len({x['month'] for x in events})==45)
ck('official_rules_not_mislabeled_as_monthly_notices',sum(x['source_level']=='official_monthly_notice' for x in events)==4)
ck('future_separate',len(future)==1 and future[0]['month']=='2026-10' and future[0]['event_date_candidate']=='2026-10-16')
ck('holiday_roll_candidates_kept_unverified',[(x['month'],x['event_date_candidate']) for x in events if x['holiday_roll_candidate']]==[('2024-02','2024-02-19'),('2026-02','2026-02-24'),('2026-06','2026-06-22')])
ck('no_historical_input_approval',not any(x['historical_input_eligible'] for x in events+future+notices))
ck('formula_dates_match_notices',all(x.get('event_date',x['event_date_candidate'])==x['event_date_candidate'] for x in events))
save('validation.json',{'checks':checks,'all_passed':all(x['passed'] for x in checks)})
summary={'cutoff':CUTOFF,'user_facing_date':'2026-10-15','generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'official_contract_rules':7,'historical_months':45,'official_monthly_notice_verified_months':4,'rule_derived_only_historical_months':41,'future_candidate_months':1,'holiday_roll_candidates': [{'month':x['month'],'date':x['event_date_candidate']} for x in events if x['holiday_roll_candidate']],'strategy_or_return_analysis_performed':False,'main_database_modified':False,'checks_passed':sum(x['passed'] for x in checks),'checks_total':len(checks),'mechanism_urls':[x['url'] for x in ss if '/hs300wd/20' in x['url']],'remaining':['41个月尚未逐月官方核验；三处节假日顺延为规则候选','7个当前合约HTML没有生效日期，历史规则变更审计不完整','到期现金交割不等同现货股票必然巨额交易；流量/净流量/波动有无异常尚未统计','本轮仅事件原始数据，不生成事件前后收益/买卖信号','2026-10-16为截至10月15日未发生候选；未核当月官方通知，不混入已发生样本']}
save('summary.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
