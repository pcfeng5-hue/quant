"""Read-only historical trading-condition audit. Never authorizes a trade."""
from pathlib import Path
from html.parser import HTMLParser
from decimal import Decimal, ROUND_HALF_UP
import csv, collections, datetime, hashlib, html, json, re, sqlite3, unicodedata
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
OLD=ROOT/'work/historical_trade_conditions_oct17'
DB=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
CHIPS=ROOT/'outputs/高德红外数据库/历史筹码采集_20261017/每日筹码摘要_915日.csv'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,obj):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');return p
def writecsv(name,rows):
 p=OUT/name
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
class Rows(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=='tr':self.row=[]
  if tag in ('td','th') and self.row is not None:self.cell=''
 def handle_data(self,data):
  if self.cell is not None:self.cell+=data
 def handle_endtag(self,tag):
  if tag in ('td','th') and self.cell is not None:self.row.append(re.sub(r'\s+',' ',self.cell).strip());self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
def text_html(p):
 b=p.read_bytes();s=b.decode('gb18030' if b'<style>' in b[:30] else 'utf-8',errors='replace')
 return s,re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',re.sub(r'<style.*?</style>|<script.*?</script>',' ',s,flags=re.S))))

before=sha(DB)
con=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
assert con.execute('pragma quick_check').fetchone()[0]=='ok'
dates=[r['trade_date'] for r in csv.DictReader(CHIPS.open(encoding='utf-8-sig'))]
assert len(dates)==len(set(dates))==915 and dates==sorted(dates)
assert dates[0]=='2023-01-03' and dates[-1]=='2026-10-16'
bars={}
for row in con.execute("select * from daily_bars where symbol='002414.SZ' and source='em_daily_0' order by trade_date,snapshot_id"):
 r=dict(row);d=r['trade_date']
 if d in bars:
  assert tuple(r[k] for k in ['open','high','low','close','volume'])==tuple(bars[d][k] for k in ['open','high','low','close','volume'])
 bars[d]=r
actions=[dict(r) for r in con.execute('select art_code,record_date,ex_date,cash_cny_per_10_shares,transfer_shares_per_10,source_sha256,availability_status from corporate_action_observations')]
exdates={r['ex_date'] for r in actions}
save('corporate_actions_readonly_copy.json',actions)

requests=[]
for f in OLD.glob('*requests*.json'):
 try:requests.extend(json.loads(f.read_text()))
 except (ValueError,TypeError):pass
url_by_path={r['raw_path']:r for r in requests if isinstance(r,dict) and r.get('raw_path')}
monthly=[]
for prefix,title in [('suspension_','证券停牌情况'),('security_stats_','证券成交统计')]:
 for p in sorted((OLD/'raw').glob(prefix+'*')):
  month=re.search(r'_(\d{4}-\d\d)_',p.name).group(1)
  s,t=text_html(p);n=unicodedata.normalize('NFKC',t)
  assert month.replace('-','.') in n,(p.name,'header_month_not_matched')
  parser=Rows();parser.feed(s)
  rows=[r for r in parser.rows if r and r[0]=='002414']
  security_rows=[r for r in parser.rows if r and re.fullmatch(r'\d{6}',r[0])]
  assert title in t and security_rows,(p.name,'not_a_valid_monthly_table')
  monthly.append({'month':month,'report_type':prefix.rstrip('_'),'header_month_checked':True,'parsed_security_rows':len(security_rows),'target_rows':rows,'target_row_count':len(rows),'observed_name':rows[0][1] if rows else None,'evidence_path':str(p),'evidence_sha256':sha(p),'source_url':url_by_path.get(str(p),{}).get('url'),'retrieved_at':url_by_path.get(str(p),{}).get('retrieved_at'),'scope':'monthly_report_rows_only_not_daily_status_certification','available_at_month_start':False})
save('monthly_report_observations.json',monthly)
writecsv('monthly_report_inventory.csv',[{k:v for k,v in r.items() if k!='target_rows'} for r in monthly])
susp={r['month']:r for r in monthly if r['report_type']=='suspension'}
stats={r['month']:r for r in monthly if r['report_type']=='security_stats'}
assert len(susp)==len(stats)==45 and sum(r['target_row_count'] for r in susp.values())==0
assert all(r['target_row_count']==1 and r['observed_name']=='高德红外' for r in stats.values())

# Preserve extracted pages without relying on misleading legacy filenames.
pdf_files=[next((OLD/'raw').glob(glob)) for glob in ['rules_2021_pdf_*.pdf','rules_2026_pdf_*.pdf','chinaclear_fees_2026_*.pdf','rules_2023_pdf_repeal_*.pdf']]
pdf_pages={}
for p in pdf_files:
 rows=[{'page_number':i+1,'text':page.extract_text() or ''} for i,page in enumerate(PdfReader(p).pages)]
 save('extracted/'+p.stem+'_pages.json',rows);pdf_pages[p.name]=rows
mislabel=next(p for p in pdf_files if p.name.startswith('rules_2023_pdf_repeal'))
assert '2021' in pdf_pages[mislabel.name][0]['text'] and '337' in pdf_pages[mislabel.name][0]['text']
save('source_identity_corrections.json',[{'path':str(mislabel),'legacy_name_claim':'2023','actual_identity':'深证上〔2021〕337号通知及2021年3月修订交易规则','excluded_as_2023_rule':True,'original_preserved':True},{'source_name':'chinaclear_original_publisher_transfer_notice','host':'finance.sina.cn','primary_host':False,'attributed_author':'中国结算','classification':'publisher-attributed republication; not original ChinaClear-hosted notice'}])
web=OUT/'web_official_rule_search.json'
assert web.exists()
rules=[
 {'rule_id':'SZSE_2021_SELECTED_A_SHARE_PROVISIONS','published_date':'2021-03-31','effective_date':'2021-04-06','research_period_from':'2023-01-03','research_period_to':'2023-04-07','evidence':'rules_2021_pdf original pp6,10-12,25,38','normal_mainboard_limit_pct':10,'mainboard_st_limit_pct':5,'buy_lot':100,'price_tick_cny':0.01,'same_day_newly_bought_shares_resale':False,'status':'selected_provisions_checked_not_complete_rule_change_audit','caveat':'其他修订和暂缓条文不能仅由该基线推定；本表仅选用普通主板A股的基础限制'},
 {'rule_id':'SZSE_2023','published_date':'2023-02-17','effective_date':'2023-04-10','research_period_from':'2023-04-10','research_period_to':'2026-07-03','evidence':'官方发布通知（检索响应）+首批主板注册制上市日（已下载官方网页）+官方2023年大事记检索；2023规则PDF只取得检索内容，原件下载失败','normal_mainboard_limit_pct':10,'mainboard_st_limit_pct':5,'buy_lot':100,'price_tick_cny':0.01,'same_day_newly_bought_shares_resale':False,'status':'effective_date_cross_checked_2023_original_pdf_missing','caveat':'2023文本原件及2023-2026中间修订完整链仍待补核；不是将现行规则回填全历史'},
 {'rule_id':'SZSE_2026','published_date':'2026-04-24','effective_date':'2026-07-06','research_period_from':'2026-07-06','research_period_to':'2026-10-16','evidence':'rules_2026_notice_retry original + rules_2026_pdf original pp7-8,12-14,26-27','normal_mainboard_limit_pct':10,'mainboard_st_limit_pct':10,'buy_lot':100,'price_tick_cny':0.01,'same_day_newly_bought_shares_resale':False,'status':'selected_provisions_original_checked','caveat':'2026原文3.3.13统一主板10%，不再沿用旧4.5.5的ST5%；用户禁入ST规则保持不变'}]
save('rule_regimes.json',rules)
fee_schedule=[
 {'fee':'stamp_tax_sell','effective_date':'2022-07-01','research_from':'2023-01-03','research_to':'2023-08-25','buy_rate':0,'sell_rate':0.001,'evidence':'stamp_law_2021原件转载的印花税法税目表；出让方1‰','status':'law_and_2023_reduction_notice_checked'},
 {'fee':'stamp_tax_sell','effective_date':'2023-08-28','research_from':'2023-08-28','research_to':'2026-10-16','buy_rate':0,'sell_rate':0.0005,'evidence':'stamp_reduction_2023税务机关原件；2026中国结算表p7','status':'effective_date_original_checked'},
 {'fee':'exchange_handling','effective_date':None,'research_from':'2023-01-03','research_to':'2023-08-25','buy_rate':0.0000487,'sell_rate':0.0000487,'evidence':'fee_reduction_2023深交所通知明确旧费率；旧费率最初生效日未补核','status':'old_rate_original_confirmed_origin_date_unknown'},
 {'fee':'exchange_handling','effective_date':'2023-08-28','research_from':'2023-08-28','research_to':'2026-10-16','buy_rate':0.0000341,'sell_rate':0.0000341,'evidence':'fee_reduction_2023原件；2026中国结算表p8','status':'effective_date_original_checked'},
 {'fee':'regulatory','effective_date':None,'research_from':'2023-01-03','research_to':'2026-10-16','buy_rate':0.00002,'sell_rate':0.00002,'evidence':'2026中国结算表p7；起始生效日及更早历史完整链未补','status':'2026_original_confirmed_historical_continuity_pending'},
 {'fee':'transfer','effective_date':'2022-04-29','research_from':'2023-01-03','research_to':'2026-10-16','buy_rate':0.00001,'sell_rate':0.00001,'evidence':'中国结算署名新浪转载通知+中国结算大事记；2026中国结算原表p3','status':'2022_origin_republication_not_original_host_2026_original_confirmed'},
 {'fee':'broker_commission','effective_date':None,'research_from':'2023-01-03','research_to':'2026-10-16','buy_rate':None,'sell_rate':None,'evidence':None,'status':'account_specific_unknown_inclusion_unknown_minimum_unknown'}]
save('fee_schedule.json',fee_schedule)
save('commission_accounting_contract.json',{'default_mode':'unknown','account_rate':None,'minimum_per_order_cny':None,'contains_exchange_fee':None,'contains_regulatory_fee':None,'contains_transfer_fee':None,'rounding_and_order_aggregation':None,'total_cost_may_be_calculated':False,'inclusive_mode':'若确认券商报出的全佣包含经手费/证管费，只计一次全佣；过户费是否包含仍须单独确认','net_mode':'仅在确认净佣时，将净佣、经手费、证管费及未包含的过户费相加；印花税另按卖出日期计算','unknown_mode':'账户佣金与包费范围未知时，保留费率组件，不输出精确净收益','dividend_tax':'个人身份/持股期限/跨境税务状态未确认，红利税不设默认0；不在每笔交易费用中机械计提'})

daily=[]
for d in dates:
 regime=next(r for r in rules if r['research_period_from']<=d<=r['research_period_to'])
 b=bars.get(d);m=d[:7];ms=susp.get(m);mt=stats.get(m)
 prev_dates=[x for x in bars if x<d];prev=bars[max(prev_dates)] if prev_dates else None
 ref=None if d in exdates else (prev['close'] if prev else None)
 def price(mult):return float((Decimal(str(ref))*Decimal(mult)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)) if ref is not None else None
 row={'trade_date':d,'symbol':'002414.SZ','exchange_timezone':'Asia/Shanghai','rule_id':regime['rule_id'],'rule_effective_date':regime['effective_date'],'buy_lot_shares':100,'price_tick_cny':0.01,'newly_bought_same_day_resale_allowed':False,'default_normal_mainboard_limit_pct':10,'st_regime_limit_pct':regime['mainboard_st_limit_pct'],'user_st_buy_prohibited':True,'historical_st_status':'unknown_daily_status_not_certified','month_report_name':mt['observed_name'] if mt else None,'month_report_name_scope':'monthly_snapshot_not_daily_or_point_in_time','monthly_suspension_evidence':'absent_in_covered_month_report_not_daily_no_event_proof' if ms and not ms['target_row_count'] else 'month_report_not_acquired','suspension_month_source_sha256':ms['evidence_sha256'] if ms else None,'observed_positive_day_volume':bool(b and b['volume'] and b['volume']>0),'unadjusted_daily_bar_available':bool(b),'intraday_suspension_status':'unknown','ex_rights_date_from_existing_original_terms':d in exdates,'conditional_reference_close':ref,'candidate_normal_upper_limit':price('1.10'),'candidate_normal_lower_limit':price('0.90'),'candidate_limit_status':'not_computed_ex_date_needs_exchange_reference' if d in exdates else ('conditional_only_no_official_daily_limit_or_st_verification' if ref else 'not_computed_previous_close_missing'),'official_daily_upper_limit':None,'official_daily_lower_limit':None,'limit_up_queue_or_fillability':'unknown_requires_intraday_orderbook','stamp_tax_sell_rate':0.001 if d<'2023-08-28' else 0.0005,'exchange_handling_each_side_rate':0.0000487 if d<'2023-08-28' else 0.0000341,'regulatory_each_side_rate_candidate':0.00002,'transfer_each_side_rate_candidate':0.00001,'broker_commission_rate':None,'commission_package_mode':'unknown','cost_model_complete':False,'execution_eligible':False,'daily_status_verified_normal':False,'continuous_limit_order_cage':'reference_price_102pct_or_plus_10ticks_max_buy_98pct_or_minus_10ticks_min_sell_requires_intraday' if d>='2023-04-10' else '2021_baseline_rules_selected_other_revisions_pending'}
 daily.append(row)
writecsv('daily_trade_conditions_915.csv',daily);save('daily_trade_conditions_915.json',daily)
assert all(not r['daily_status_verified_normal'] and not r['execution_eligible'] and not r['cost_model_complete'] for r in daily)
assert next(r for r in daily if r['trade_date']=='2026-07-03')['st_regime_limit_pct']==5
assert next(r for r in daily if r['trade_date']=='2026-07-06')['st_regime_limit_pct']==10
assert next(r for r in daily if r['trade_date']=='2023-08-25')['stamp_tax_sell_rate']==0.001
assert next(r for r in daily if r['trade_date']=='2023-08-28')['stamp_tax_sell_rate']==0.0005
assert len([r for r in daily if r['ex_rights_date_from_existing_original_terms']])==3
assert all(r['candidate_normal_upper_limit'] is None for r in daily if r['ex_rights_date_from_existing_original_terms'])
after=sha(DB);assert before==after
pending=[{'date':f'2026-10-{day}','status':'not_collected_or_verified_this_round','market_open_status':'pending_official_calendar_check'} for day in ['19','20','21','22']]
save('post_cutoff_pending.json',pending)
summary={'as_of_client_date':'2026-10-22','research_cutoff':'2026-10-16','scope':'third_priority_historical_trade_conditions_only','daily_rows':len(daily),'monthly_suspension_reports':len(susp),'monthly_stats_reports':len(stats),'monthly_suspension_target_rows':sum(r['target_row_count'] for r in susp.values()),'monthly_stats_target_rows':sum(r['target_row_count'] for r in stats.values()),'monthly_names_all_normal':True,'months_first':'2023-01','months_last':'2026-09','days_with_monthly_scope_evidence':sum(r['trade_date'][:7] in susp for r in daily),'days_with_unadjusted_bars':sum(r['unadjusted_daily_bar_available'] for r in daily),'actual_daily_verified_normal_count':0,'official_daily_limit_price_count':0,'execution_eligible_count':0,'complete_account_cost_model_count':0,'rule_regimes':3,'ex_dates_protected_from_naive_limit_calculation':sorted(exdates),'source_identity_corrections':2,'main_database_readonly':True,'main_database_sha256_before':before,'main_database_sha256_after':after,'main_database_quick_check':'ok','tests':['915_dates_exact_unique_sorted','45_monthly_tables_each_type_header_and_rows_valid','suspension_no_002414_rows_not_upgraded_to_daily_status','45_monthly_names_高德红外_not_carried_as_daily_st_proof','2026_07_06_ST_boundary_5_to_10','2023_08_28_stamp_and_exchange_fee_boundary','three_ex_dates_no_naive_limit_prices','all_915_execution_eligible_false_and_total_cost_incomplete','main_database_hash_unchanged'],'unresolved':['2023规则原始PDF及中间修订完整链','逐日ST/特殊状态及停复牌事件原始清单','官方逐日涨跌停价格与除权参考价','2026年10月停牌和证券统计月报尚未取得','账户佣金、包费内容、最低收费及成交级舍入','历史证管费连续性及2022过户费原始发布件','分红税所需持仓与个人税务信息','研究截止后2026-10-19至22日另列待补，不混入915日']}
save('summary.json',summary)
evidence=[]
for p in sorted((OLD/'raw').glob('*')):
 meta=url_by_path.get(str(p),{});url=meta.get('url')
 evidence.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'url':url,'retrieved_at':meta.get('retrieved_at'),'original_preserved':True,'classification_override':'ChinaClear-attributed republication on Sina; not official-host primary' if 'sina.' in (url or '') else None})
for p in [DB,CHIPS,web]:evidence.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'classification':'database_readonly_input' if p==DB else 'input'})
save('evidence_manifest.json',evidence)
report=f'''# 高德红外历史交易条件补核（2026-10-22）

本轮只读主数据库，复用已取得官方原件，产出915行逐日条件表。截止仍为2026-10-16；10月19—22日单列待补。没有买卖概率、交易建议或可执行授权。

## 已完成及证据边界

- 解析2023-01至2026-09共45份深交所停牌月报、45份证券成交统计，逐份核对表头月份和证券代码列。停牌表没有002414行；成交统计45个月均找到“高德红外”。覆盖915日中的{summary['days_with_monthly_scope_evidence']}日。月报排除记录只证明该表没有记录，不能证明逐日全天正常、无临时停牌或无ST，也不能把月末名称回填为当时已知状态。
- 原主库914日存在正成交量；10月16日主库未补，不把网页前复权显示当未复权行情。正成交量只说明当日至少发生交易，不能证明整日可成交或排队订单可成交。
- 规则选取基础条款并按生效时间分段：2021版2021-04-06生效；2023版依官方通知“首只主板注册制上市日”及官方2023-04-10上市报道交叉核对；2026版2026-07-06生效。2026版主板ST涨跌幅从旧5%变为10%，用户“不碰ST”的限制不变。
- 查出一份旧文件虽命名rules_2023_pdf_repeal，内容却是2021年337号通知和2021年3月规则。原件保留、错误2023归属排除。2023 PDF原件下载未成功，已保留官方检索响应；不能把检索文本说成已取得原件。
- 2023-08-28前后分别记录卖出印花税1‰/0.5‰、经手费双边0.0487‰/0.0341‰。过户费候选双边0.01‰、证管费候选双边0.02‰保留证据等级和历史连续性缺口。

## 逐日表如何使用

daily_trade_conditions_915.csv/json分别保存规则制度、月报实际观察、行情观察、候选涨跌停和unknown字段。普通主板10%仅为条件假设；历史ST状态、特殊交易状态、官方日限价未确认，因此915日 execution_eligible、daily_status_verified_normal 全部为false。3个除权日不直接用前收盘价乘1.1/0.9。其他日期候选限价也不是官方核准值。

账户佣金、最低佣金、包费范围和逐笔舍入未知，因此915日 cost_model_complete 全部为false。经手费、证管费可能已含全佣，深市过户费也可能包含；先确认包费，再选择全佣或净佣分解模式，禁止把所有组件机械相加。印花税按卖出日期单列；红利税依持股及税务身份另算，不能默认0。

## 检验与待补

边界检验已覆盖2023-08-28税费、2026-07-06主板ST制度、三次除权日保护及915日未授权状态。主库quick_check=ok；生成前后SHA256相同：{before}。

仍缺2023完整规则原件与中间修订链、逐日ST/停复牌事件、官方逐日涨跌停与除权参考价、2026年10月月报、账户实际佣金和费用口径。没有用“未查到”填“正常”。

来源逐文件URL、取得时间、SHA256见evidence_manifest.json；网络新取件失败见retrievals.json；官方检索响应见web_official_rule_search.json。旧原件未移动或覆盖。

关键官方链接：[2026规则通知](https://www.szse.cn/lawrules/rule/trade/t20260424_620190.html)、[2023规则通知](https://investor.szse.cn/lawrules/index/rule/t20230217_598773.html)、[2023首批上市](https://www.szse.cn/aboutus/trends/news/t20230410_599854.html)、[经手费调整](https://www.szse.cn/disclosure/notice/t20230818_602805.html)、[印花税减半](https://shanxi.chinatax.gov.cn/web/detail/sx-11400-545-1780448)。
'''
(OUT/'历史交易条件补核报告.md').write_text(report)
print(json.dumps(summary,ensure_ascii=False,indent=2))
