"""Read-only expansion of three existing action records; no returns or indicators."""
from pathlib import Path
import sqlite3,json,re,hashlib
from datetime import datetime,timezone
from decimal import Decimal

BASE=Path(__file__).resolve().parents[2]
ROOT=BASE/'outputs/高德红外数据库'
OUT=Path(__file__).resolve().parent
c=sqlite3.connect('file:'+str(ROOT/'高德红外_2023起.sqlite')+'?mode=ro',uri=True); c.row_factory=sqlite3.Row
specs=[
 dict(art_code='AN202306121590866740',attributable_period='2022年度',report_period_end='2022-12-31',implementation_signature_date='2023-06-12',provider_implementation_notice_date_candidate='2023-06-13',record_date='2023-06-19',ex_date='2023-06-20',official_delegated_cash_distribution_date='2023-06-20',capital_transfer_account_credit_date='2023-06-20',transferred_unrestricted_shares_first_trading_date='2023-06-20',cash_cny_per_10_shares_gross='1.3',transfer_shares_per_10='3',signature_token='二〇二三年六月十二日'),
 dict(art_code='AN202405151633180433',attributable_period='2023年度',report_period_end='2023-12-31',implementation_signature_date='2024-05-15',provider_implementation_notice_date_candidate='2024-05-16',record_date='2024-05-23',ex_date='2024-05-24',official_delegated_cash_distribution_date='2024-05-24',capital_transfer_account_credit_date=None,transferred_unrestricted_shares_first_trading_date=None,cash_cny_per_10_shares_gross='0.14',transfer_shares_per_10='0',signature_token='二〇二四年五月十五日'),
 dict(art_code='AN202609141829372726',attributable_period='2026半年度',report_period_end='2026-06-30',implementation_signature_date='2026-09-14',provider_implementation_notice_date_candidate='2026-09-15',record_date='2026-09-21',ex_date='2026-09-22',official_delegated_cash_distribution_date='2026-09-22',capital_transfer_account_credit_date=None,transferred_unrestricted_shares_first_trading_date=None,cash_cny_per_10_shares_gross='1',transfer_shares_per_10='0',signature_token='二〇二六年九月十四日'),
]
def compact(t):return re.sub(r'[\s,，]','',t)
def tok(d):
 y,m,day=map(int,d.split('-'));return f'{y}年{m}月{day}日'
def canon(o):return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'))
checks=[]
def check(name,ok,details=None):
 checks.append(dict(name=name,passed=bool(ok),details=details))
 if not ok:raise AssertionError(name)
rows=[]
providers=[json.loads(x[0]) for x in c.execute("select payload_json from current_source_records where dataset='dividends'")]
for s in specs:
 a=s['art_code'];old=dict(c.execute('select * from corporate_action_observations where art_code=?',(a,)).fetchone())
 d=dict(c.execute('select * from announcement_documents where art_code=?',(a,)).fetchone());p=ROOT/d['relative_path']
 pdfhash=hashlib.sha256(p.read_bytes()).hexdigest();check(a+': original PDF hash',pdfhash==d['sha256']==old['source_sha256'])
 pages={r['page_number']:r['text'] for r in c.execute('select page_number,text from announcement_pages where art_code=? and source_sha256=? order by page_number',(a,pdfhash))}
 check(a+': page count',len(pages)==3,len(pages));alltext=compact(''.join(pages.values()))
 evidence=[]
 def ev(field,val,pg,token,scope='original_text_and_rendered_page_checked'):
  check(a+': '+field+' original token',compact(token) in compact(pages[pg]))
  evidence.append(dict(field=field,value=val,page_number=pg,text_quote_compacted=compact(token),page_text_sha256=hashlib.sha256(pages[pg].encode()).hexdigest(),verification_scope=scope))
 ev('attributable_period',s['attributable_period'],1,{'2022年度':'2022年年度','2023年度':'2023年年度','2026半年度':'2026年半年度'}[s['attributable_period']]+'权益分派实施公告')
 ev('implementation_signature_date',s['implementation_signature_date'],3,s['signature_token'])
 ev('record_date',s['record_date'],2,'本次权益分派股权登记日为：'+tok(s['record_date']))
 ev('ex_date',s['ex_date'],2,'除权除息日为：'+tok(s['ex_date']))
 # Exact complete delegated-payment sentence includes the account-credit route and its scope.
 cash_start=compact(pages[2]).index('本公司此次委托中国结算深圳分公司代派的A股股东现金红利将于')
 cash_end=compact(pages[2]).index('直接划入其资金账户。',cash_start)+len('直接划入其资金账户。')
 cash_quote=compact(pages[2])[cash_start:cash_end]
 check(a+': cash date context',tok(s['official_delegated_cash_distribution_date']) in cash_quote)
 ev('official_delegated_cash_distribution_date',s['official_delegated_cash_distribution_date'],2,cash_quote)
 cashpg=1 if a!='AN202609141829372726' else 2
 ev('cash_cny_per_10_shares_gross',s['cash_cny_per_10_shares_gross'],cashpg,'每10股派'+s['cash_cny_per_10_shares_gross']+'元人民币现金')
 if s['transfer_shares_per_10']=='3':
  ev('transfer_shares_per_10','3',1,'每10股转增3股')
  ev('capital_transfer_account_credit_date',s['capital_transfer_account_credit_date'],2,'本次所转股于'+tok(s['capital_transfer_account_credit_date'])+'直接记入股东证券账户')
  ev('transferred_unrestricted_shares_first_trading_date',s['transferred_unrestricted_shares_first_trading_date'],3,'本次所转的无限售条件流通股的起始交易日为'+tok(s['transferred_unrestricted_shares_first_trading_date']))
 else:
  ev('transfer_shares_per_10','0',1,'不以资本公积金转增股本')
 for field in ['record_date','ex_date','transfer_shares_per_10']:
  check(a+': existing primary observation '+field,str(old[field])==str(s[field]))
 check(a+': existing cash matches',Decimal(old['cash_cny_per_10_shares'])==Decimal(s['cash_cny_per_10_shares_gross']))
 check(a+': directory notice candidate',d['notice_date'][:10]==s['provider_implementation_notice_date_candidate'])
 candidates=[r for r in providers if r['EX_DIVIDEND_DATE'][:10]==s['ex_date']];check(a+': one provider action',len(candidates)==1)
 prov=candidates[0]
 check(a+': provider terms',prov['EQUITY_RECORD_DATE'][:10]==s['record_date'] and Decimal(str(prov['PRETAX_BONUS_RMB']))==Decimal(s['cash_cny_per_10_shares_gross']) and prov['REPORT_DATE'][:10]==s['report_period_end'])
 for date_field in ['record_date','ex_date','official_delegated_cash_distribution_date','capital_transfer_account_credit_date','transferred_unrestricted_shares_first_trading_date']:
  if s[date_field]:
   x=c.execute('select is_scheduled_open from trading_calendar where trade_date=?',(s[date_field],)).fetchone()
   # Calendar schema is inspected by the caller; no manufactured open flag if absent.
   check(a+': calendar '+date_field,bool(x and x[0]==1))
 rec={k:v for k,v in s.items() if k!='signature_token'}
 rec.update(symbol='002414.SZ',existing_main_database_corporate_action=True,is_new_economic_action=False,
  source_sha256=pdfhash,source_url=d['url'],source_pdf_path=str(p),source_notice_title=d['title'],
  provider_plan_notice_date_candidate=(prov.get('PLAN_NOTICE_DATE') or '')[:10] or None,
  plan_notice_date_candidate_certified_from_original=False,
  official_cash_distribution_scope='中国结算深圳分公司代派 A 股股东；原件另列两名公司自行派发股东，不将代派日期套用于自派股东',
  self_distributed_cash_payment_date=None,user_account_actual_cash_receipt_date=None,user_account_actual_cash_receipt_verified=False,
  first_publication_timestamp=None,first_publication_timezone='Asia/Shanghai',first_publication_certified=False,historical_feature_input_eligible=False,
  timing_status='implementation_terms_verified_exact_first_publication_unverified',
  amount_basis='CNY per 10 pre-distribution shares, gross before tax; no personalized tax estimate',
  null_transfer_dates_reason=None if s['transfer_shares_per_10']=='3' else 'not_applicable_no_capital_reserve_transfer_in_this_action',
  field_evidence=evidence,all_original_pages_reused_and_visually_checked=[1,2,3])
 rec['observation_sha256']=hashlib.sha256(canon(rec).encode()).hexdigest();rows.append(rec)
check('all three economic actions already existed',len(rows)==3 and all(r['existing_main_database_corporate_action'] for r in rows))
check('2026 action explicitly semiannual',rows[2]['attributable_period']=='2026半年度' and rows[2]['report_period_end']=='2026-06-30')
check('actual account receipt left unknown',all(r['user_account_actual_cash_receipt_date'] is None and not r['user_account_actual_cash_receipt_verified'] for r in rows))
check('first publication gating retained',all(r['first_publication_timestamp'] is None and not r['historical_feature_input_eligible'] for r in rows))
check('no dividend forward-return fields copied',all(not any(k in r for k in ['D10_CLOSE_ADJCHRATE','D30_CLOSE_ADJCHRATE','BD10_CLOSE_ADJCHRATE']) for r in rows))
check('event identities unique',len({(r['art_code'],r['source_sha256']) for r in rows})==3)
c.close()
now=datetime.now(timezone.utc).isoformat()
result=dict(schema_version='dividend-events-v1',built_at_utc=now,scope_start='2023-01-01',scope_end='2026-10-15',read_only_main_database=True,
 summary=dict(existing_economic_actions=3,new_economic_actions=0,dated_event_fields=11,verified_new_field_types=['official_delegated_cash_distribution_date','capital_transfer_account_credit_date','transferred_unrestricted_shares_first_trading_date'],exact_first_publication_times_certified=0,user_account_receipts_verified=0),
 controls=['Dates are event metadata, not proof of predictive effect.','Mechanical ex-right/ex-dividend adjustments must not be interpreted as market selloff or forecast.','Use date-specific availability gates before historical feature research.','Three actions do not certify that every no-distribution year has been independently audited.','The three cash payment dates equal their ex-dividend dates, so there are 3 overlapping economic action episodes, not 6 independent event samples.','Capital reserve share transfer is not a cash inflow; a dividend distribution is not proof of secondary-market institutional buying or selling.','No price, volume or flow event effect has been estimated; 3 existing actions do not establish significant volatility or fund-flow effects.'],corporate_actions=rows)
(OUT/'event_dates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
(OUT/'validation.json').write_text(json.dumps(dict(built_at_utc=now,check_count=len(checks),passed_count=sum(x['passed'] for x in checks),all_passed=all(x['passed'] for x in checks),main_database_mutated=False,checks=checks),ensure_ascii=False,indent=2))
print('Saved',len(rows),'existing actions,',len(checks),'checks')
