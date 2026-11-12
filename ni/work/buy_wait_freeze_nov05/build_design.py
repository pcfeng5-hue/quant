from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/输入证据合库与验证设计_20261105'
def read(p):return json.loads((ROOT/p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def write(name,x):
 p=OUT/name
 if p.exists():raise FileExistsError(p)
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
oldpath='outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json'
routepath='outputs/下一阶段路线决策_20261104/路线选择与准入门.json'
old=read(oldpath);route=read(routepath)
assert len(old['pending_freeze'])==15 and all(x is None for x in old['pending_freeze'].values())
latest=dict(old['pending_freeze']);latest['main_horizon_planned_exchange_sessions']=10
confirmation={
 'client_date':'2026-11-05','timezone':'America/Toronto',
 'source_kind':'explicit_user_reply_in_this_chat','question':'首版“回落时买入还是等待”，你最关心从作出判断起多长时间内的结果？',
 'verbatim_answer':'未来10个交易日',
 'interpretation':'T is the close of the tenth planned SZSE session after d0, under an as-of validated exchange calendar; not10 stock bars after the later entry',
 'confirmed_field':'main_horizon_planned_exchange_sessions','confirmed_value':10,
 'latest_user_parameter_state':latest,'confirmed_groups':1,'pending_groups':14,
 'actual_account_flat_confirmed':False,'capital_or_trading_authorized':False,
 'old_15_null_contract_sha256':sha(ROOT/oldpath),'old_contract_modified':False,
 'existing_realized_loss_pause_CNY':2000,'floating_loss_counted_in_that_trigger':False,
 'risk_setting_modified':False,
 'research_constants_are_not_user_preferences':['W=2','B=10000','18:00 Asia/Shanghai','one opening-auction limit attempt','100-share assumed lot','zero nominal cash return scenario'],
}
write('本轮用户确认与参数状态.json',confirmation)
protocol={
 'protocol_id':'BW17_002414_buy_vs_wait_H10_W2_v1',
 'client_date':'2026-11-05','status':'candidate_definition_frozen_evidence_bindings_missing_not_executable',
 'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
 'purpose':'Study one predeclared cash-entry policy comparison for the confirmed after-close pullback question; this is not a current forecast or a claim of profitable timing',
 'definition_only':True,'scientific_stage':'paired_policy_definition_and_data_admission_before_any_real_labels',
 'research_selection_id':17,
 'registration_basis':{'old_choices':16,'new_policy_definitions':1,'new_models':0,'new_scores':0,'no_pre_freeze_market_or_target_queries':True,'H5_was_discussion_only_never_frozen_or_scored':True,'source_rationale':'One observable down-close and one observable up-close directly operationalize the user’s premature re-entry/wait question with minimal new thresholds. W2 and other constants are design assumptions, not learned optima or evidence of advantage.'},
 'user_binding':{'first_use_case':'收盘后判断回落时该买入还是继续等待','H_planned_sessions':10,'latest_parameter_state_file':'本轮用户确认与参数状态.json','other_14_user_groups_unconfirmed':True},
 'scope':{'symbol':'002414.SZ','starting_research_sleeve':'hypothetical flat cash sleeve only; actual account state unknown','data_dates_for_future_development_only':['2023-01-03','2024-12-31'],'these_dates_are_previously_seen_development_not_independent_test':True,'targets_2025_2026_isolated':True,'no_cross_2024_endpoint_or_outcome_read':True,'right_boundary_event_status':'RIGHT_CENSORED_DEVELOPMENT_BOUNDARY','optional_features_not_selected':['chip_estimates_or_summaries','MACD','KDJ','MA_groups','volume_groups','news_or_policy_sentiment','current_industry_membership','large_order_or_institutional_identity_proxies'],'selected_input_families':['raw_close','asof_planned_SZSE_calendar','asof_individual_stock_status','asof_corporate_action_effective_dates','historically_applicable_order_and_quantity_rules','fee_and_execution_model_evidence']},
 'research_constants':{'H_planned_sessions':10,'max_confirmation_sessions':2,'starting_cash_CNY':10000,'decision_cutoff_local':'18:00:00','decision_timezone':'Asia/Shanghai','assumed_buy_lot_shares':100,'cash_return_model':'zero nominal return, explicitly a research scenario not actual interest certification','no_reinvestment_or_position_additions':True,'research_constants_do_not_change_account_risk':True},
 'time_and_population':{
  'session_clock':'d0 is a planned SZSE open date known at its18:00 cutoff; d_j is the jth subsequent as-of planned session; missing/suspended stock bars do not shift the clock or T',
  'eligibility':'E(d0)=TRUE iff raw_close(d0)<raw_close(d_minus1), both field versions were available by d0_cutoff, both planned adjacent-session observations have certified comparable units and complete contemporaneous status/action evidence, no mechanical action distorts this adjacent-day comparison, and stock eligibility is certified',
  'false_vs_unknown':'Known non-pullback or known disallowed status is FALSE with reason; missing time/unit/status/action/previous-session price or uncertain eligibility is UNKNOWN, never FALSE',
  'first_date_missing_previous_session':'retain UNKNOWN; do not substitute prior observed stock bar or silently drop',
  'mechanical_action_rule':'Do not use any future d1..d10 event to exclude d0 retrospectively. Future corporate actions belong in the policy ledger; unknown required terms make affected wealth/targets unknown and coverage explicit',
  'input_asof':'version_first_available_at <= each policy decision_cutoff, and revised versions only after their actual availability; fetch timestamps in2026 are not historical availability',
  'no_late_data_backfill':'Late arrival after18:00 cannot become same-day input; preserve the original unknown/abstention and log later versions separately',
  'label_maturity':'label_mature_at=max(required realized/modelled fills, terminal mark, rights, accrued liabilities and all necessary validation timestamps); never train before actual maturity; unknown maturity remains unknown'
 },
 'paths':{
  'A_now':{'attempt_session':'d1','limit_price':'certified raw_close(d0), known at d0 cutoff','attempts':1,'entry_when_no_order_eligibility':'known barred=NO_ATTEMPT_BARRED; missing evidence=UNKNOWN_EXECUTION_QUALIFICATION'},
  'B_wait':{'confirmation_scan_sessions':['d1','d2'],'confirmation':'first j in{1,2} with certified comparable raw_close(dj)>raw_close(dj_minus1), known eligible status and no mechanical-action distortion at dj18:00; any earlier UNKNOWN makes first-confirmation history unresolved, never skip to a convenient later signal','attempt_session':'d_(j+1) after the first certified confirmation','limit_price':'certified raw_close(dj), known at dj18:00','attempts':1,'last_possible_entry_session':'d3','known_no_confirmation':'cash path; status NO_TRIGGER, not a zero-return trade','after_one_attempt_no_fill':'cash path only if no-fill/cancellation certified; do not try again'},
  'C_cash':{'entry':'none','wealth':'same initial10000 under declared nominal-zero-cash-return scenario'},
  'all_paths':{'common_terminal':'T=d10 close, fixed from d0, never reset from later buy','same_initial_cash_and_allocation_algorithm':True,'no_chasing_no_retry_no_topups':True,'future_B_confirmation_is_a_policy_action_input_not_a_d0_forecast_feature':True}
 },
 'order_and_wealth_contract':{
  'intended_order_window':'one opening-auction limit attempt on the designated planned session, only if historical applicable venue/channel/order and cancellation rules are bound; no same-close or after-hours assumption',
  'quantity_formula':'q_requested=max{100*k:k>=0, 100*k*limit_price+certified_order_time_fee_upper_bound(100*k,limit_price)<=available_cash}; if lot rule or fee bound is unknown then UNKNOWN, not q=0',
  'lot_rule_status':'100 is a research assumption; validate its historical applicability or fail the gate, never silently substitute',
  'partial_and_remaining':'record each fill q_i,p_i,fees_i; remaining cash stays in the sleeve; remaining order cancellation requires a confirmed valid cancellation, otherwise unresolved; no overspend or repeat use of reserved cash',
  'counterfactual_fill_status':'A/B fills cannot both be identified from daily bars or one actual account trade. A separately frozen and validated execution model must describe price/queue/no-fill/partial-fill/cancellation and label the result MODEL_BASED_COUNTERFACTUAL, never actual realized fills',
  'daily_open_or_touch_proves_fill':False,
  'execution_binding':None,'fee_and_tax_binding':None,'corporate_action_and_liability_binding':None,
  'NAV_formula':'cash_T + shares_T*validated_mark_T + supported_rights_and_receivables_T - unpaid_taxes_fees_other_liabilities_T',
  'paid_fees_rule':'cash already reflects paid charges; do not subtract twice',
  'dividend_rule':'cash received and its receivable cannot both remain counted; receivables are not spendable cash before availability',
  'future_sale_fees':'NAV endpoint has no invented sale; include only applicable accrued/unpaid liabilities, not a fictitious liquidating trade fee',
  'NAV_not_realized_profit_or_executable_cash':True,
  'sellability':'record historically lawful sellable quantity and restrictions separately; no assumption that fresh buys can be sold same-day; no purported guaranteed stops',
  'unknown_end_mark_with_positive_position':'wealth and paired target NULL; do not forward-fill stale mark and certify it',
  'unknown_execution_fee_or_rights':'affected wealth and paired target NULL, even if one path value is known',
  'T_plus_1_and_halts':'use certified historical restrictions; no universal2026 rule backfill',
 },
 'labels_and_reporting':{
  'paired_primary_delta':'delta=(NAV_B(T)-NAV_A(T))/initial_cash',
  'strict_paired_event':'WAIT_HIGHER if delta>0; TIE if delta=0; NOW_HIGHER if delta<0; UNKNOWN if comparison unresolved; exact arithmetic/fee rounding follows validated money conventions, never hidden epsilon',
  'economic_neutral_band':None,
  'per_path_cash_relative':'NAV_A/B(T)-NAV_C(T), with strict sign and amount; can lose money even if it wins the paired comparison',
  'nontrades':'NO_TRIGGER/NO_ATTEMPT_BARRED/KNOWN_UNFILLED/KNOWN_ZERO_AFFORDABLE_QUANTITY are identified cash policies if every necessary condition is known; trade return itself remainsNULL when no trade',
  'unknown_vs_censored_vs_immature':'store independent eligibility, confirmation, order, terminal, label-maturity states; no single0 code',
  'denominators':'keep all planned d0 dates, eligibility false/unknown, entered/not-triggered/barred/unfilled/partial/unresolved/censored/immature counts; main paired frequency denominator is only E=TRUE and both terminal paths identified under the declared execution model; disclose loss of coverage and missingness selection',
  'empirical_frequencies_not_current_forecast':True,
  'paired_probability_not_difference_of_marginals':True,
  'required_outputs':['full cohort and exclusion/unknown ledger','A/B/C terminal NAV and relative-to-cash amounts','paired delta signs and distribution','daily close-mark NAV downside and drawdown only if each mark certified; not intraday guaranteed risk','exposure days and sellable quantities','coverage by date/month and each unresolved reason','all negative/zero/missing results; no winner-quarter selection'],
  'phase1_acceptance':'This first candidate is definition-only now. Any later phase1 run is descriptive paired-policy research only; no success threshold, model promotion or current action can follow from selecting a positive development mean',
  'future_predictive_acceptance':'Separate preregistration must fix the predictive model/estimator, training schedule, sample minimum, clustered uncertainty, economic margin, calibration and promotion criteria before any real forecast fitting/scoring. Until that binding, do not claim a fully executable prediction protocol',
  'time_order_requirements':['training contains only targets with label_mature_at earlier than its training cutoff','purge all training outcome windows crossing evaluation starts','overlapping outcomes are dependent; never count them as independent trials','shared paired cohort and missingness disclosed','2023/2024 already seen; no fresh independent-test claim','2025/2026 stay closed until separately registered later-stage agreement']
 },
 'gates':{'definition_frozen':True,'research_evidence_complete':False,'real_target_generation_authorized':False,'predictive_model_protocol_frozen':False,'model_fit_authorized':False,'real_scores_authorized':False,'formal_historical_input_approved':False,'current_decision_approved':False,'runtime_usable':False,'forecast_generated':False,'simulation_started':False,'capital_use_authorized':False},
 'required_before_any_real_target':['selected raw_close mapping/unit/version/historical availability bound with actual source evidence','as-of calendar, adjacent-session observations and individual stock eligibility/status certified','history-applicable quantity, venue, order and cancellation model bound','counterfactual execution model frozen with assumptions and independent validation','fees, rights, cash/receivables/liabilities fully bound for declared use','population/entry/terminal/maturity states and full missingness ledger implemented and independently reviewed','explicit separately saved experimental run registration and permission gate before label calculation; no automatic run on design completion'],
 'unbound_user_groups':{k:v for k,v in latest.items() if v is None},
 'confirmed_risk_preservation':{'old_protocol_and_risk_files_not_modified':True,'existing_conditional_pilot_CNY':10000,'existing_pause_realized_loss_CNY':2000,'floating_PnL_reported_separately':True,'this_is_not_capital_authorization':True},
 'change_control':'Protocol body and canonical SHA frozen before labels. Any H/W/cohort/confirmation/order/endpoint/estimator change gets a new version and research-choice entry, preserves negatives, and cannot be chosen from same-batch outcomes.'
}
write('买入还是等待_研究候选BW17_冻结v1.json',protocol)
register={'client_date':'2026-11-05','old_registered_choices':16,'old_registry_reference':'outputs/研究证据与覆盖审查_20261101/研究证据与覆盖审查_v1.md','old_failures_retained':True,'new_choice':{'id':17,'definition_id':protocol['protocol_id'],'kind':'paired_action_policy_definition_not_probability_model','status':'frozen_unrun_evidence_blocked','H':10,'W':2,'models_fitted':0,'real_labels':0,'scores':0},'total_registered_choices':17,'new_evaluated_choices':0,'legacy_model_definitions':4,'old_16_evaluation_status_unchanged':True,'old14_prepared_columns_still_not_scanned':True,'future_label_population_and_counterfactual_model_selection_are_research_choices':True}
write('累计研究选择登记_增补BW17.json',register)
rows=[]
field=read('outputs/输入证据合库与验证设计_20261105/字段时点与版本台账.json')
for r in field['field_provider_rows']:
 rows.append({'item':r['evidence_id'],'history_metadata_traceable':True,'old_restricted_snapshot_engineering':'existing scope only, do not newly certify retrospective PIT or execute a new experiment','new_formal_historical_action_input':False,'current_or_runtime_input':False,'selected_for_BW17':r['field_family']=='raw_close','evidence_available':['saved request/completion stamps','saved manifest and project-definition references','recorded raw-path/SHA, not rehashed'],'missing':['historical first-availability and revision chain','native field position/code mapping','provider or equivalent independently validated unit evidence'],'minimum_next_proof':['versioned original with per-field mapping and validated units','proof of version availability at each selected historical decision time, or explicitly limited retrospective scenario only under a new protocol'],'reference':r['snapshot_source_reference']})
rows.extend([
 {'item':'planned_calendar_2023_2024','history_metadata_traceable':True,'scope':'729 natural dates;484 planned open;245 planned closed;2 contextual dates separate','permitted':'planned calendar provenance and old scope engineering comparison','new_formal_historical_action_input':False,'current_or_runtime_input':False,'missing':['proof calendar version known at decision time','exceptional closures/revisions history','not a stock-observation calendar'],'minimum_next_proof':['archive applicable SZSE notice originals and revisions with publication/receipt evidence','separately document exceptional closures and do not shift T on missing stock bars']},
 {'item':'daily_stock_status_and_rules','history_metadata_traceable':True,'scope':'484 existing condition links;0 newly certified normal/official-limit/executable rows','permitted':'trace saved condition flags and unknowns','new_formal_historical_action_input':False,'current_or_runtime_input':False,'missing':['daily ST/halt and applicable rules chain','official daily limit/quantity references and time availability','queue/order/partial/cancel execution model'],'minimum_next_proof':['date-specific evidence with validity/publication versions','explicit validated counterfactual execution assumptions; never infer fills fromOHLC']},
 {'item':'corporate_actions_fees_and_execution','history_metadata_traceable':True,'scope':'2 corporate-action date indexes;not full cash/stock/rights ledger','permitted':'event date provenance only; existing reports retain prior scope','new_formal_historical_action_input':False,'current_or_runtime_input':False,'missing':['share/cash rights terms, available dates and tax liabilities','fee package/minimum/rounding/upper bound','counterfactual fill/cancel specification'],'minimum_next_proof':['complete date-sensitive ledger rules and source terms','bounded validated fee/execution model for declared study; actual account costs needed only if making account-specific claims']},
 {'item':'optional_chips_news_industry_and_large_orders','history_metadata_traceable':None,'scope':'not selected forBW17, older provenance limits retained','permitted':'existing source evidence/estimated-vs-native labels only','new_formal_historical_action_input':False,'current_or_runtime_input':False,'missing':['no new optional-feature review attempted'],'minimum_next_proof':['only if selected later, register new definition and independently close its use-specific gaps'],'not_an_additional_gate_on_independent_core_evidence_work':True}
])
admission={'client_date':'2026-11-05','status':'use_specific_inventory_not_new_market_data_or_formal_promotion','bounded_source_pass_finished':True,'content_reextracted':False,'extra_domain_source_paths':0,'row_count':len(rows),'rows':rows,'new_formal_data_gaps_closed':0,'original_36_gap_inventory_preserved':True,'what_can_be_done_now':['query and reproduce metadata/source lineage','inspect saved engineering/snapshot research with its old limitations; preserve negative results','design future first-receipt evidence without calling it historical PIT','define/freeze this unrun single candidate'], 'what_is_not_authorized':['new true historical policy labels without admission','2025/2026 target generation or read','model fitting/scoring orcurrent forecasts','simulation clock, account use or trading'], 'one_pass_conclusion':'The fixed local source set does not establish the missing time/units/execution evidence; this is not proof that every external archive could never recover it. End repeated broad search over these same unchanged files.'}
write('历史研究用途与缺证据矩阵.json',admission)
prospective={
 'design_id':'first_receipt_evidence_spec_20261105_v1','design_only':True,'collector_started':False,'scheduled_job_created':False,
 'selected_scope':'raw_close and its necessary calendar/status/rules/rights dependencies only; otherOHLCV may be stored later only under declared scope',
 'required_record_columns':['symbol','provider','native_field_id_or_position','raw_value_and_unit_when_future_collection_authorized','observation_time_with_timezone','source_event_time_if_known','source_publication_time_candidate_and_precision','request_start_utc','response_end_utc','first_project_received_at_utc','source_version_id','supersedes_version_id','immutable_raw_path','raw_sha256','adapter_version','validation_status','rejection_reason','eligible_for_declared_decision_at'],
 'distinctions':['first_project_received_at is a verifiable local receipt, not proof of global first publication','future first receipt cannot certify old2023/2024 versions','new revision append-only, never overwrite old decision snapshot','if only a date is known, use independently supported time bound or keep unknown; no guessed fixed lag'],
 'quality_rejections':['missing time/zone or invalid ordering','unknown mapping/unit or wrong symbol','source conflict beyond frozen tolerance','version or action discontinuity unresolved','late data after fixed cutoff','missing daily status/rules or incomplete cost/right evidence for action use'],
 'capture_manifest_policy':'save authorized URL, UTC request/receipt times, original bytes/version, units, adapter andSHA; immutable append-only; credentials not stored; permission/network failure logged once with bounded retry, no bypass',
 'no_market_or_prediction_promotion':'Design or later collection alone does not open historical PIT, targets, forecasting, simulation or an observation-day clock',
 'next_batch':'Implement an offline first-receipt manifest schema and synthetic rejection checks, then propose one bounded authorized public-source capture; no automatic schedule'
}
write('前向首收与版本补证设计.json',prospective)
bodyhash=hashlib.sha256(enc(protocol).encode()).hexdigest()
refs=[oldpath,routepath,'outputs/下一阶段路线决策_20261104/下一批有限工程任务书.json','outputs/输入证据合库与验证设计_20261105/字段时点与版本台账.json','outputs/输入证据合库与验证设计_20261105/计划日与状态来源索引.json']
write('设计冻结与来源指纹.json',{'protocol_file':'买入还是等待_研究候选BW17_冻结v1.json','canonical_json_sha256':bodyhash,'file_sha256':sha(OUT/'买入还是等待_研究候选BW17_冻结v1.json'),'source_hashes':{p:sha(ROOT/p) for p in refs},'new_user_confirmation_file_sha256':sha(OUT/'本轮用户确认与参数状态.json'),'frozen_before_real_labels_models_scores':True,'fully_executable_prediction_protocol':False,'future_changes_require_new_registration':True})
report='''# 历史研究用途与缺证据结论

2026年11月5日，多伦多。本轮合并的是来源、时点、版本和状态的证据台账，不是新增行情数据库或把旧字段全部改成合格预测输入。

|数据|现在能用于什么|尚不能据此证明什么|最小补证|
|---|---|---|---|
|O/H/L/C/成交量×两个旧来源，共10组|查快照、请求/取得时间、项目单位约定和旧版本；保留既有受限回顾工程结果|2023—2024决策时已拥有这个版本；供应商原字段/单位已认证|原件映射和单位复核、历史版本与可得时间链|
|729自然日，484计划开市、245计划休市|查计划日与官方通知线索，辅助核对旧工程|异常闭市全集、历史当时已知日历、个股每天正常|当期通知/修订原件和时点、临时闭市及个股日状态|
|484日旧交易条件链接|定位旧状态与规则及未知|日级正常、官方限价、特定订单能成交；本轮新增认证均0|逐日状态、适用规则链、订单/排队/部分成交/撤单模型|
|2个公司行动日期索引|查登记/除权日期来源|完整权益现金流、税负、费用后结果|股数/现金条款、权益可用日、费用包费/最低额/舍入及负债|
|筹码、新闻、行业、机构大单等|保留各自旧范围和估计/原生边界|本轮没有放行这些可选特征|BW17未选用，后续确需时另登记补证|

因此，旧资料仍可支持已声明假设的快照回顾、工程复现与来源核对；这不等于真实历史时点预测能力或账户可实现收益已获认证。本轮没有执行新的市场统计、读取结果库或把回顾频率当当前上涨概率。

固定本地来源的一遍整理到此结束。未找到历史版本证据不意味着世界上所有档案都无法恢复，但不能继续反复扫同一组不变文件并记作新进展。下一项可独立推进的工程是前向首收/版本留存与质量拒绝；未来接收日志只证明未来实际取得，不能倒签过去。

新协议的期限已由用户确认是未来10个计划交易日；其余14组使用偏好仍待定。既有36项缺口清单保留，本轮新增正式缺口关闭数为0；“合库完成”“候选定义冻结”和“实际预测/模拟通过”分别记账。
'''
(OUT/'历史研究用途与缺证据结论.md').write_text(report)
md='''# 买入还是等待：BW17研究候选冻结 v1

2026年11月5日。**冻结的是一个具体、尚未运行的研究候选；历史数据、执行与费用证据尚不允许生成真实结果，更没有冻结可用的概率预测模型。** 用户本轮确认“未来10个交易日”。原15项待定记录原样保留；本轮最新状态为主期限10、其余14组待定。

## 单一比较

|项目|冻结定义|
|---|---|
|研究对象|002414.SZ，一笔假设未投入的现金研究袖套；不声明真实账户空仓|
|研究观察期|d0判断后第10个计划交易日收盘为共同T；等待后买入不顺延|
|决策截止|每个相关日上海18:00，仅用此前已可得且版本可核验的数据；并不假定18点一切数据必已到齐|
|回落人口|当日收盘低于前一计划交易日收盘，两日状态/单位/行动比较可核；未知记UNKNOWN|
|A：下一窗口买入|d1开盘集合竞价一次限价意向，限价为d0已知收盘|
|B：等确认|只看d1/d2，首次收盘严格回升且比较可核后，次日开盘同一规则尝试一次；最迟d3。无确认则持币；若更早确认状态未知，不能跳过去挑后来有利信号|
|C：持币参考|全程持币|
|研究金额/数量|研究常数10000元；按已知限价、已认证费用上界及100股假设整数单位算最大可买数，真实适用性未核则不得运行|
|追价与补仓|不追价、不再尝试、不加钱；未成交余单只有合法撤销已确认才算终止|
|终点|NAV估值，另记可卖数量；不假装已卖出、不虚扣一次并未发生的卖出费|

等待2日、18点、1万元及数量/订单设计是本候选的研究设定，不是用户已确认的14项偏好或账户风控变更；这些设定没有根据旧分数挑选，亦无最优性主张。本轮只冻结这一份，不扫描不同期限、阈值或组合。新的政策定义计入**第17项研究选择**；旧16项及全部失败保留，新拟合模型、真实标签和评分仍为0。

## 比较什么

主量为 delta=(NAV等待−NAV立即)/共同起始现金。严格大于0、等于0、小于0分别记录，未知为NULL。另报告A/B相对C是否盈利、幅度、期间收盘估值下行、暴露天数、无法卖出和缺值覆盖；等待胜出仍可能双方都亏。经济中性带和实际行动阈值尚未确认，不能用“delta大于0”直接给买卖建议。

NAV=现金+持股×核验估值+有证据的权益/应收−未付负债。已付费用不重复扣，已到账股息不再同时列应收，应收未到账不作为可用现金。终点NAV不是已实现盈利或保证能变现。

已证实没有确认/未成交是持币政策结果，交易收益本身仍为空；成交/部分成交/撤单/费用或权益未知时，相关NAV及配对结果保留NULL。日K开盘价、触及限价或有成交量不证明A/B两条反事实订单都成交。未来执行模型必须单独冻结、验证并明确为模型假设结果，不能冒充真实双路径成交。

## 时间与缺失规则

共同T来自当时可知的计划日历，缺一根股票K线不顺延。未来d1—d10公司行动不能用于事后挑掉d0人口，应进入财富账本；必要条款缺失时结果不可评估并公开覆盖。研究范围暂限已见2023—2024开发期；d10越过2024年末的起点标记右删失，不读取2025/2026结果来补齐。未来首收日志不得追认过去PIT。

每个结果必须等所需成交/估值/费用/权益与验证时间全部成熟；成熟未知则不能训练。以后时间顺序训练须清除跨评估边界的结果窗口；重叠观察不能冒充独立样本；比较使用共同日期并报告全部未知、失败和弃答。

## 放行门与本轮不完成的部分

现有来源未证明历史首可得/修订链、原生字段/单位及完整状态/执行/费用，所以真实标签生成、拟合、评分、当前预测、模拟和资金使用全部关闭。预测估计器、最小样本、时序折、依赖稳健区间、经济优势门槛及晋级标准，须在任何新预测实验之前另行预登记；本文件不把它们冒充已冻结。即使以后描述期平均delta为正，也不能据此宣布预测有效。

当前完成：候选人口、动作、共同期限、目标公式、缺失/成熟状态及停止规则的定义冻结。当前未完成：证据绑定、真实配对验证和可执行预测协议。原条件性1万元试验与2000元已实现亏损暂停口径、浮亏另列不变；本轮没有资金授权。自动任务已取消，只保留手动推进。
'''
(OUT/'买入还是等待_研究候选BW17_冻结说明.md').write_text(md)
checks=[('old15nullpreserved',len(old['pending_freeze'])==15 and all(v is None for v in read(oldpath)['pending_freeze'].values())),('oneconfirmed14pending',confirmation['confirmed_groups']==1 and len(protocol['unbound_user_groups'])==14 and all(v is None for v in protocol['unbound_user_groups'].values())),('H10commonendpoint',protocol['research_constants']['H_planned_sessions']==10 and protocol['user_binding']['H_planned_sessions']==10),('16plus1registered17',register['old_registered_choices']+register['new_choice']['id']-16==17),('noexperimentsallowed',not any(v for k,v in protocol['gates'].items() if k!='definition_frozen')),('originalcontracthashunchanged',sha(ROOT/oldpath)==confirmation['old_15_null_contract_sha256']),('strictnonexecutable',protocol['order_and_wealth_contract']['execution_binding'] is None and protocol['order_and_wealth_contract']['fee_and_tax_binding'] is None),('matrix14rows',len(rows)==14)]
assert all(v for _,v in checks)
write('设计构建核验.json',{'all_checks_passed':True,'passed':len(checks),'total':len(checks),'checks':[{'check':k,'passed':v} for k,v in checks],'protocol_canonical_sha256':bodyhash,'no_labels_models_or_scores_computed':True})
print(json.dumps({'design_frozen':True,'fully_executable':False,'H':10,'pending_user_groups':14,'cumulative_choices':17,'new_labels_models_scores':0,'checks':len(checks)},ensure_ascii=False))
