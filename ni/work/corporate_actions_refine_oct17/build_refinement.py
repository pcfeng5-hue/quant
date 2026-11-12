"""Normalize primary disclosure facts without mutating the research database."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from functools import lru_cache
import csv, hashlib, json, re, sqlite3
from pypdf import PdfReader

BASE=Path(__file__).resolve().parents[2]
ROOT=BASE/'outputs/高德红外数据库'
OUT=Path(__file__).resolve().parent
DB=ROOT/'高德红外_2023起.sqlite'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
before=sha(DB)
c=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
def write(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
def compact(t):return re.sub(r'[\s,，]','',t)
checks=[]
def check(name,passed,details=None):
 checks.append(dict(name=name,passed=bool(passed),details=details))
 if not passed: raise AssertionError(name)
meta=[]
for p in sorted((BASE/'work/refresh_oct15_disclosures/raw').glob('cninfo_announcements_page*.json')):
 for x in json.loads(p.read_text()).get('announcements') or []:meta.append((x,p,sha(p)))
def norm(s):return re.sub(r'[\s:：()（）]','',s).replace('高德红外','')
old_cross={r['art_code']:r for r in json.loads((ROOT/'巨潮原件交叉核对.json').read_text())}
new_cross={r['art_code']:r for r in json.loads((OUT/'official_crosscheck.json').read_text())}
sources={};evidence={}
@lru_cache(None)
def doc(art):
 d=dict(c.execute('select * from announcement_documents where art_code=?',(art,)).fetchone())
 path=ROOT/d['relative_path'];check(art+':PDF hash',sha(path)==d['sha256'])
 hits=[(x,p,h) for x,p,h in meta if norm(x['announcementTitle'])==norm(d['title']) and x['adjunctUrl'].split('/')[1]==d['notice_date'][:10]]
 check(art+':one official directory match',len(hits)==1,len(hits));x,p,h=hits[0]
 stamp=datetime.fromtimestamp(x['announcementTime']/1000,ZoneInfo('Asia/Shanghai')).isoformat()
 check(art+':official date agrees with vendor date',stamp[:10]==d['notice_date'][:10])
 cross=new_cross.get(art) or old_cross.get(art)
 cross_ok=bool(cross and (cross.get('identical_to_existing_vendor_pdf') or cross.get('comparison')=='identical_bytes'))
 cross_path=cross.get('path') if cross and 'path' in cross else (str(ROOT/cross['relative_path']) if cross else None)
 if cross_ok:check(art+':official copy hash',bool(cross_path and sha(cross_path)==d['sha256']))
 sources[art]=dict(art_code=art,title=d['title'],pdf_path=str(path),pdf_sha256=d['sha256'],provider_url=d['url'],provider_notice_date=d['notice_date'][:10],official_url='https://static.cninfo.com.cn/'+x['adjunctUrl'],official_announcement_id=x['announcementId'],official_directory_timestamp_raw_ms=x['announcementTime'],official_directory_timestamp_rendered_asia_shanghai=stamp,official_directory_date=stamp[:10],official_timestamp_precision='calendar_date_midnight_marker_exact_release_time_unverified',official_storage_time=x.get('storageTime'),exact_first_publication_timestamp=None,exact_first_publication_verified=False,metadata_source_path=str(p),metadata_source_sha256=h,official_metadata_row=x,official_pdf_identical_bytes_verified=cross_ok,official_pdf_path=cross_path if cross_ok else None)
 return d,PdfReader(path)
def ev(art,page,quote,label):
 d,reader=doc(art)
 key=f'{art}:{page}'
 if key not in evidence:
  row=c.execute('select text from announcement_pages where art_code=? and page_number=? and source_sha256=?',(art,page,d['sha256'])).fetchone()
  check(key+':database native page exists',row is not None)
  native=reader.pages[page-1].extract_text() or ''
  evidence[key]=dict(art_code=art,page_number_1_based=page,pdf_sha256=d['sha256'],existing_page_text=row[0],existing_page_text_sha256=hashlib.sha256(row[0].encode()).hexdigest(),fresh_pypdf_text=native,fresh_pypdf_text_sha256=hashlib.sha256(native.encode()).hexdigest())
 check(key+':'+label+' existing page token',compact(quote) in compact(evidence[key]['existing_page_text']))
 check(key+':'+label+' fresh PDF token',compact(quote) in compact(evidence[key]['fresh_pypdf_text']))
 return dict(evidence_id=key,field=label,quote_compacted=compact(quote))

previous=json.loads((BASE/'work/dividend_event_dates_oct15/event_dates.json').read_text())
capital_old=json.loads((ROOT/'股本与过户原件核对.json').read_text())
actions=[]
for old in previous['corporate_actions']:
 art=old['art_code'];d,_=doc(art)
 row={k:old[k] for k in ['symbol','art_code','attributable_period','report_period_end','implementation_signature_date','record_date','ex_date','official_delegated_cash_distribution_date','capital_transfer_account_credit_date','transferred_unrestricted_shares_first_trading_date','cash_cny_per_10_shares_gross','transfer_shares_per_10']}
 row.update(event_id='002414.SZ_distribution_'+old['ex_date'].replace('-',''),event_type='cash_dividend_and_capital_reserve_transfer' if old['transfer_shares_per_10']=='3' else 'cash_dividend',economic_event_already_in_main_database=True,is_new_economic_event=False,first_publication_timestamp=None,historical_feature_input_eligible=False,trade_settlement_or_personal_receipt_verified=False,user_actual_cash_receipt_date=None,self_distributed_holder_payment_date=None,self_distributed_holders=['武汉市高德电气有限公司','黄立'],official_delegated_payment_scope=old['official_cash_distribution_scope'],field_evidence=[])
 for item in old['field_evidence']:
  row['field_evidence'].append(ev(art,item['page_number'],item['text_quote_compacted'],item['field']))
 # A missing personalized holding period must not turn a gross dividend into net cash.
 tax={'1.3':['0.26','0.13'],'0.14':['0.028','0.014'],'1':['0.2','0.1']}[row['cash_cny_per_10_shares_gross']]
 row['disclosed_tax_terms']=dict(scope='公告所列首发后限售股、股权激励限售股及无限售股个人股东；仅记录原件条件，不认证用户税务身份或未来适用性',holding_period_basis='FIFO_by_securities_account',initial_personal_tax_withholding='暂不扣缴；转让时按持有期限补税',holding_up_to_1_month_additional_tax_cny_per_10=tax[0],holding_over_1_month_up_to_1_year_additional_tax_cny_per_10=tax[1],holding_over_1_year_additional_tax='原件写不需补缴税款',user_applicable_treatment=None)
 for val in tax:row['field_evidence'].append(ev(art,2,'每10股补缴税款'+val+'元','disclosed_tax_term_'+val))
 row['field_evidence'].append(ev(art,2,'以投资者证券账户为单位计算持股期限','tax_holding_period_unit'))
 if row['transfer_shares_per_10']=='3':
  row.update(total_shares_before=3285181622,total_shares_after=4270736108,actual_added_shares=985554486,capital_change_effective_date='2023-06-20',capital_change_effective_date_role='announcement_scheduled_account_credit_and_listed_unrestricted_transfer_trading_start_confirmed_implemented_in_subsequent_report')
  row['field_evidence'] += [ev(art,3,'985554486','disclosed_integer_added_shares'),ev(art,3,'最终股本变动情况以中国结算深圳分公司登记的股本结构为准','implementation_structure_final_registration_caveat'),ev('AN202404151630235965',79,'公司已于2023年6月20日实施完毕权益分派','subsequent_completion_confirmation_page_start'),ev('AN202404151630235965',80,'方案，具体内容详见巨潮资讯网','subsequent_completion_confirmation_page_continuation')]
 else:row.update(total_shares_before=4270736108,total_shares_after=4270736108,actual_added_shares=0,capital_change_effective_date=None,capital_change_effective_date_role='not_applicable_no_transfer_or_bonus_shares')
 row['source_id']=art;actions.append(row)
write('corporate_actions.json',actions)

transfers=[]
for old in capital_old['new_ownership_transfer_events']:
 art=old['evidence'][0]['art_code'];doc(art)
 row={k:v for k,v in old.items() if k!='evidence'}
 row.update(source_id=art,total_capital_change=None,unlimited_share_change=None,first_publication_timestamp=None,official_directory_date=sources[art]['official_directory_date'],is_new_this_round=False,field_evidence=[])
 date=old['completion_date']; y,m,day=map(int,date.split('-'))
 row['field_evidence'] += [ev(art,1,f'{y}年{m}月{day}日办理完成','completion_date'),ev(art,1,old['shares_original']+'万股','shares'),ev(art,2,old['registration_confirmation_received_date'].replace('-','年',1).replace('-','月',1).replace('月0','月').replace('年0','年')+'日','confirmation_received_date')]
 transfers.append(row)
write('nontrade_transfers.json',transfers)

decisions=[]
for period,proposal,approval,proposal_date,approval_date,page in [
 ('2024年度','AN202504241661802971','AN202505201676081145','2025-04-24','2025-05-20',4),
 ('2025年度','AN202604141821191382','AN202605081822079377','2026-04-14','2026-05-08',3)]:
 for a in [proposal,approval]:doc(a)
 terms='不派发现金红利、不进行资本公积金转增股本、不送红股'
 evidence_rows=[ev(proposal,1,terms,'non_distribution_proposal'),ev(approval,page,terms,'non_distribution_shareholder_approval')]
 py,pm,pd=map(int,proposal_date.split('-'))
 evidence_rows.append(ev(proposal,1,f'{py}年{pm}月{pd}日召开','proposal_board_meeting_date'))
 # Meeting date is separately checked on its first page rather than inferred from its title.
 y,m,d=map(int,approval_date.split('-'))
 evidence_rows.append(ev(approval,1,f'现场会议：{y}年{m}月{d}日','shareholder_meeting_date'))
 decisions.append(dict(decision_id='002414.SZ_no_distribution_'+period[:4],symbol='002414.SZ',attributable_period=period,event_type='annual_no_distribution_decision',proposal_board_meeting_date=proposal_date,shareholder_approval_date=approval_date,cash_dividend_cny_per_10_shares='0',capital_reserve_transfer_shares_per_10='0',bonus_shares_per_10='0',record_date=None,ex_date=None,payment_date=None,no_ex_or_payment_date_reason='not_applicable_approved_no_distribution_plan',scope='只认证本年度利润分配议案及其最终审议，不推断该自然年所有中期或特别分配均不存在',proposal_source_id=proposal,approval_source_id=approval,official_approval_directory_date=sources[approval]['official_directory_date'],exact_first_publication_timestamp=None,historical_feature_input_eligible=False,is_cash_or_share_distribution_event=False,field_evidence=evidence_rows))
write('non_distribution_decisions.json',decisions)

snapshots=[]
for old in capital_old['capital_period_observations']:
 row={k:v for k,v in old.items() if k!='evidence'}
 art=old['evidence'][0]['art_code'];page=old['evidence'][0]['page_numbers'][0]
 doc(art)
 row.update(source_id=art,daily_effective_date=None,first_publication_timestamp=None,field_evidence=[])
 for key in ['total_shares','limited_shares','unlimited_shares']:
  row['field_evidence'].append(ev(art,page,str(row[key]),key))
 check(row['period_end']+':share classes sum',row['limited_shares']+row['unlimited_shares']==row['total_shares'])
 snapshots.append(row)
write('capital_period_observations.json',snapshots)

registration=dict(event_id='002414.SZ_2023_capital_registration',event_type='administrative_registration_of_same_capital_transfer',same_economic_event_id=actions[0]['event_id'],administrative_registration_date='2023-06-26',date_source_type='later_annual_report_retrospective_explicit_statement',source_id='AN202404151630235965',source_notice_date='2024-04-16',exact_first_publication_timestamp=None,known_on_2023_06_26_certified=False,equity_market_effective_date='2023-06-20',is_new_capital_issuance=False,field_evidence=[ev('AN202404151630235965',114,'2023年6月20日，公司以资本公积转增股本98555.45万元，并于2023年6月26日在武汉市市场监督管理局办理了变更手续。','capital_and_administrative_dates'),ev('AN202306281591781833',1,'近日，公司已完成注册资本变更','contemporaneous_notice_only_says_recently')])
write('registration_date_refinement.json',registration)

bridges=[]
for left,right in zip(snapshots,snapshots[1:]):
 total_delta=right['total_shares']-left['total_shares']
 known_added=985554486 if left['period_end']=='2022-12-31' else 0
 bridges.append(dict(bridge_id=left['period_end']+'_'+right['period_end'],from_period_end=left['period_end'],to_period_end=right['period_end'],observed_total_share_change=total_delta,known_total_capital_action_shares=known_added,known_total_action_id=actions[0]['event_id'] if known_added else None,total_arithmetic_residual=total_delta-known_added,total_arithmetic_reconciled=total_delta==known_added,observed_limited_share_change=right['limited_shares']-left['limited_shares'],observed_unlimited_share_change=right['unlimited_shares']-left['unlimited_shares'],share_nature_event_date_inferred=False,daily_total_share_curve_certified=False,daily_free_float_curve_certified=False,from_source_id=left['source_id'],to_source_id=right['source_id'],interpretation='两期总股本可算术核对；不等于期间每一日股份性质及流通股变更已认证'))
check('all adjacent total capital bridges reconcile',all(x['total_arithmetic_reconciled'] for x in bridges))
write('capital_bridges.json',bridges)
issues=capital_old['unresolved_capital_issues']
for x in issues:x.update(rechecked_this_round=True,status_after_this_round=x['status'],closed_this_round=False,do_not_backfill_effective_date=True)
write('unresolved_capital_issues.json',issues)

# Preserve the cash total discrepancy without equating a future reported aggregate to a planned total.
cash_check=dict(issue_id='2023annual_distribution_planned_vs_later_reported_total',status='different_measurement_contexts_cause_unverified',planned_gross_total_cny='59790305.51',calculated_gross_before_rounding_cny=str(Decimal(4270736108)*Decimal('0.14')/Decimal(10)),later_2024_cash_dividend_total_reported_in_2024annual_plan_cny='59790145.29',difference_cny='160.22',do_not_overwrite_per_share_terms=True,do_not_treat_as_user_net_cash_or_account_receipt=True,field_evidence=[ev('AN202405151633180433',1,'59790305.51','planned_aggregate_cash'),ev('AN202504241661802971',1,'59790145.29','later_reported_2024_cash_aggregate')])
write('cash_total_scope_difference.json',cash_check)
write('publication_evidence.json',list(sources.values()))
write('evidence_pages.json',list(evidence.values()))

with (OUT/'corporate_action_dates.csv').open('w',newline='',encoding='utf-8-sig') as f:
 fields=['symbol','attributable_period','implementation_signature_date','record_date','ex_date','official_delegated_cash_distribution_date','capital_transfer_account_credit_date','transferred_unrestricted_shares_first_trading_date','cash_cny_per_10_shares_gross','transfer_shares_per_10','capital_change_effective_date','art_code']
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(actions)
check('no exact first publication time manufactured',all(x['exact_first_publication_timestamp'] is None for x in sources.values()))
check('all main historic feature gates retained',all(x['historical_feature_input_eligible'] is False for x in actions+decisions))
check('no period end used as daily share-nature change date',all(x['daily_effective_date'] is None for x in snapshots))
check('nontrade transfers not counted as added capital',all(x['total_capital_change'] is None and x['unlimited_share_change'] is None for x in transfers))
check('zero new economic dividend events',all(x['is_new_economic_event'] is False for x in actions))
c.close();after=sha(DB);check('main database byte unchanged',before==after)
summary=dict(version='corporate_action_refinement_20261017_v1',built_at_utc=datetime.now(timezone.utc).isoformat(),symbol='002414.SZ',main_database_read_only=True,main_database_sha256_before=before,main_database_sha256_after=after,existing_distribution_events=3,new_distribution_events=0,approved_annual_non_distribution_decisions_added=2,existing_nontrade_transfer_events_rechecked=3,period_end_capital_snapshots_rechecked=8,adjacent_total_capital_arithmetic_bridges=7,new_explicit_administrative_registration_date='2023-06-26',administrative_date_known_at_event_time_certified=False,unresolved_share_nature_issues=len(issues),exact_first_publication_times_verified=0,daily_free_float_curve_certified=False,new_official_pdf_downloads=sum(x.get('http_status')==200 for x in new_cross.values()),new_official_pdfs_identical_to_prior=sum(bool(x.get('identical_to_existing_vendor_pdf')) for x in new_cross.values()),official_metadata_records=len(sources),evidence_pages=len(evidence),checks=len(checks),all_checks_passed=all(x['passed'] for x in checks),missing_values_filled_with_zero=False,remaining_limits=['三处股份性质衔接仍无原因及精确生效日','首次公开精确时刻未认证；官方目录时间为日期零点标记','期末无限售股份不等同供应商自由流通股本；不认证逐日分母','未取得用户实际派息到账凭证和个性化税务条件','不分配决议仅覆盖2024及2025年度议案，不能证明所有中期或特别分配均已逐项排除','2024分红拟派总额与后续报告披露额存在160.22元口径差异，原因待核，不覆盖每股条款','不认证ST、停复牌或全部历史公司行动闭合；不运行指标、收益或概率分析'])
write('validation.json',dict(checks=checks,all_passed=summary['all_checks_passed']))
write('summary.json',summary)
report=f'''# 高德红外公司行动与股本底座细化核对（2026-10-17）

本轮只读主库，复用已有原件并新下载 8 份巨潮官方 PDF，均与已有公告原件逐字节一致。没有更新行情、计算指标或产生买卖概率。

## 本轮补实的旧缺口

1. **2024、2025 年度不分配方案有最终股东会批准证据。** 不再只记为董事会预案：2025-05-20 股东大会和 2026-05-08 股东会均明确审议通过本年度不派发现金、不转增、不送红股。单列 2 条不分配决议，除权、支付等日期为“不适用”的 null；不会制造 2 次权益实施事件，也不代表所有中期或特别分配已全量排除。
2. **2023 年工商变更日期可补为 2023-06-26。** 当时工商公告仅写“近日”，但后来的 2023 年报 PDF 第 114 页明确写出该日。这个日期与 2023-06-20 转增记账、无限售转增股起始交易日期分开保存。这是 2024-04-16 披露的追溯证据，不能假定在 2023-06-26 当时已经知道，更不新增一次股份发行。
3. **官方来源链加固。** 8 份员工非交易过户、不分配预案及批准、工商公告从巨潮官方站下载，全部与原件哈希相同；原有 3 次分派及 8 期末股本的官方副本也重新核对哈希。公告目录日、PDF 落款日、会议日和生效相关日期分别记录。官方目录的零点时间标记不能认证准确首次发布时间。

## 三次已有分派

| 归属期间 | 登记日 | 除权除息日 | 公告约定中国结算代派现金日 | 每 10 股税前现金 | 每 10 股转增 | 转增记账 / 所转无限售股起始交易 |
|---|---|---|---|---:|---:|---|
| 2022 年度 | 2023-06-19 | 2023-06-20 | 2023-06-20 | 1.3 元 | 3 股 | 2023-06-20 / 2023-06-20 |
| 2023 年度 | 2024-05-23 | 2024-05-24 | 2024-05-24 | 0.14 元 | 0 股 | 不适用 |
| 2026 半年度 | 2026-09-21 | 2026-09-22 | 2026-09-22 | 1 元 | 0 股 | 不适用 |

这是既有 3 个经济事件，不是新增 3 个。代派日期适用于原件所述中国结算代派范围；原件另列两名公司自派股东，其日期仍未知。用户个人实际到账日仍为 null。税务条件逐项保留原件所述持有期限及补缴税款，不根据用户所在加拿大推断税务身份。2023 年转增 985,554,486 股，3,285,181,622 + 985,554,486 = 4,270,736,108；整数总数以公告为准，不使用 30% 的小数理论结果重写登记总股本。

## 股本桥接与边界

8 个期末观测的限售加无限售均等于总股本；相邻 7 段总股本算术衔接均一致。2023 年增加的总股本能够与转增事件对应，其后各期末总股本一致。这不等于已经认证期间每一日的股份性质、自由流通分母或全部股份事件。

仍保留三处股份性质缺口：2022 期末到分派前 9,748 股；实施公告预计结构与 2023 中报期末 1 股；2023 年报期末与 2024 中报期初 2 股。不能把差值当新增发行或擅自填入解锁日。另保留 2023 中报到年报的限售/无限售期末差值供追溯，不给差值制造事件原因。

2024 年度不分配预案引用 2024 年现金分红 59,790,145.29 元，而 2023 年度实施公告拟派总额为 59,790,305.51 元，相差 160.22 元。两个数的时点和披露上下文不同，本轮不把差额直接解释成税、手续费或更正，也不覆盖每 10 股 0.14 元条款。

全部精确首次发布时间仍未认证；历史特征准入继续为 false。没有把财务报告修订处理成全历史 PIT 认证，也没有把非交易过户当股本增加。主库 SHA-256 前后相同。

## 文件与校验

- `corporate_actions.json` / `corporate_action_dates.csv`：3 个已有分派规范化记录。
- `non_distribution_decisions.json`：2 个最终批准的不分配决议。
- `capital_period_observations.json` / `capital_bridges.json`：8 期末观测与 7 段算术桥接。
- `nontrade_transfers.json`：3 个已有非交易过户事件，非新增资本。
- `registration_date_refinement.json`：工商日期及追溯信息可得性边界。
- `unresolved_capital_issues.json` / `cash_total_scope_difference.json`：未决差异。
- `publication_evidence.json` / `evidence_pages.json`：原始官方元数据、原件哈希、完整相关页文字及逐字段定位。
- `official_crosscheck.json` / `official/`：本轮官方原件、采集时间、URL、哈希与比较结果；首次沙箱 DNS 失败记录另存，没有伪装成成功响应。
- `summary.json` / `validation.json`：{len(checks)} 项检查全部通过；这只证明本轮字段、原件、算术与边界检查，不是数据全量认证。
'''
(OUT/'核对报告.md').write_text(report)
print(json.dumps(summary,ensure_ascii=False,indent=2))
