"""Source and timing design review only; no market/target database is queried."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
 localsources=[
  'outputs/首版预测协议草案_20261016.json',
  'outputs/概率预测引擎详细方案_20261016.md',
  'work/baseline_oct25/engineering_contract.json',
  'work/conditions_finish_oct22/rule_regimes.json',
  'work/conditions_finish_oct22/历史交易条件补核报告.md',
  'outputs/五项数据补缺_20261022/历史交易条件核对.md',
  'work/conditions_finish_oct22/extracted/rules_2026_pdf_9b66f8b0db70f84a_pages.json',
  'work/historical_trade_conditions_oct17/raw/rules_2026_pdf_9b66f8b0db70f84a.pdf',
  'work/historical_trade_conditions_oct17/raw/rules_2026_notice_retry_0dcb0971ac96123f.html']
 before={p:sha(ROOT/p) for p in localsources}
 draft=read(ROOT/localsources[0]);contract=read(ROOT/localsources[2]);regimes=read(ROOT/localsources[3]);pages=read(ROOT/localsources[6])
 text='\n'.join(r['text'] for r in pages)
 bypage={r['page_number']:r['text'] for r in pages}
 checks=[]
 def ck(name,ok):
  checks.append(dict(check=name,passed=bool(ok)))
  if not ok:raise AssertionError(name)
 ck('old_forecast_protocol_still_draft_not_frozen',draft['status']=='draft_not_frozen' and draft['runtime_usable'] is False)
 ck('five_day_horizon_not_user_frozen',draft['pending_freeze']['primary_horizon_trading_days'] is None and contract['horizon_observed_sessions']==5 and contract['horizon_is_engineering_example_not_final_user_freeze'])
 ck('confirmation_rule_and_wait_window_still_pending',draft['pending_freeze']['confirmation_rule'] is None and draft['pending_freeze']['maximum_wait'] is None)
 ck('realized_pause_and_floating_distinction_unchanged',draft['confirmed_requirements']['pilot_realized_loss_pause_cny']==2000 and draft['confirmed_requirements']['floating_pnl_in_this_trigger'] is False)
 ck('2026_rule_version_and_effective_regime_separate',any(r['rule_id']=='SZSE_2026' and r['effective_date']=='2026-07-06' for r in regimes) and '（2026 年修订）' in text)
 ck('ordinary_equity_settlement_restriction_in_rule_3_1_4','3.1.4' in bypage[7] and '在交收前不得卖出' in bypage[7])
 ck('exceptions_separately_listed_not_ordinary_cash_A_shares','3.1.5' in bypage[7] and '债券交易型开放式基金' in bypage[8] and 'B 股实行次交易日起回转交易' in bypage[8])
 ck('member_must_confirm_securities_and_cash','具备相应证券或资金' in bypage[7])
 ck('normal_buy_lot_and_price_tick_selected_provisions','100' in bypage[12] and '3.3.8' in bypage[12] and '0.01' in bypage[12])
 ck('unfilled_orders_and_price_time_priority_are_explicit','3.3.21' in bypage[15] and '未成交部分' in bypage[15] and '价格优先、时间优先' in bypage[15])
 ck('opening_print_is_not_investor_specific_fill','第一笔' in bypage[24] and '4.2.1' in bypage[24])
 ck('no_trade_close_may_be_prior_close','当日无成交的，以前收盘价为当日收盘价' in bypage[24])
 ck('afterhours_cash_equity_scope_is_present','3.6.1' in bypage[20] and '买卖 A' in bypage[20] and '股、交易型开放式基金' in bypage[20])
 ck('afterhours_close_price_matching_is_not_blanket_impossible','3.6.2' in bypage[20] and '以当日收盘价' in bypage[20] and '15:05 至 15:30' in bypage[20])
 ck('still_suspended_at_close_has_no_afterhours_matching','当日 15:00' in bypage[20] and '不进行盘后固定价格交易' in bypage[20])
 ck('afterhours_full_day_volume_finalized_after_session','3.6.10' in bypage[22] and '结束后计入' in bypage[22])
 ck('corporate_action_reference_not_raw_previous_close','4.4.1' in bypage[26] and '除权（息）参考价' in bypage[26] and '4.4.3' in bypage[26])
 ck('historical_rule_chain_remains_incomplete',any('missing' in r['status'] for r in regimes))
 rawfiles=sorted((OUT/'raw').glob('*.json'));ck('fresh_web_observation_files_exist',len(rawfiles)==3 and all(p.stat().st_size>100 for p in rawfiles))
 fresh='\n'.join(json.dumps(read(p),ensure_ascii=False) for p in rawfiles)
 ck('official_current_notice_and_pdf_reobserved','https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html' in fresh and 'https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf' in fresh)
 ck('fresh_parsed_rules_cover_afterhours_and_corporate_actions','3.6.10' in fresh and '4.4.3' in fresh and '2026年7月6日' in fresh)
 sources=[dict(id='SZSE_2026_NOTICE',url='https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html',publisher='深圳证券交易所',published_date='2026-04-24',effective_date='2026-07-06',evidence_kind='Fresh web parsed observation plus previously saved original HTML',saved_raw_files=[str(p.relative_to(ROOT)) for p in rawfiles],original_saved_file=localsources[8]),
 dict(id='SZSE_2026_RULE_PDF',url='https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf',publisher='深圳证券交易所',version='2026年修订',published_date='2026-04-24',effective_date='2026-07-06',selected_pages=[7,8,12,15,20,21,22,24,25,26],evidence_kind='Fresh parsed PDF observation, selected provisions matched to saved original; not a newly downloaded binary or full change-chain certificate',original_saved_file=localsources[7],original_saved_sha256=before[localsources[7]])]
 findings=[
 dict(id='TIME01',kind='design_requirement',finding='区分信号归属日、特征真实首次可得时间、决策生成时间、委托/成交窗口和结果成熟时间。source_trade_date不等于available_at。',application='t_signal_date仅作归属；decision_at必须晚于全部必需输入可得时间，未认证时不宣称正式历史可用。'),
 dict(id='TIME02',kind='design_requirement',finding='旧5观察日按已保存行情行号取样；若停牌/数据缺失可能跳过计划交易日。它不等于5个计划交易日，更不等于5自然日。',application='建议正式动作比较用在t时可知的官方计划交易日历固定共同终点；不能用未来是否有成交来决定终点。期限H仍待确认。'),
 dict(id='TIME03',kind='source_supported_and_design_inference',finding='普通现金A股不能假设当日新买数量马上可卖；底仓做T需实际可卖量、持仓批次和在途订单。',source_id='SZSE_2026_RULE_PDF',articles=['3.1.1','3.1.4','3.1.5'],application='做T另立问题，不由日线买入vs等待推导；不把T+1口号替代账户available_to_sell和停牌/冻结校验。'),
 dict(id='TIME04',kind='source_supported_and_design_inference',finding='开盘价是该证券首笔竞价成交价；价格/时间队列与对手方决定投资者成交，OHLC价不保证该订单可成交。',source_id='SZSE_2026_RULE_PDF',articles=['3.3.21','3.4.2','4.2.1'],application='下一计划交易日开盘价可作为明示理想化参考，但不能标已成交；计划窗口不可成交需记录未成交、部分成交、过期等状态，保留现金。'),
 dict(id='TIME05',kind='material_rule_boundary',finding='2026-07-06生效规则允许A股盘后固定价格交易，15:05—15:30以当日收盘价时间优先撮合，不能写收盘后绝不可能以当日收盘价成交。',source_id='SZSE_2026_RULE_PDF',articles=['3.6.1','3.6.2','3.6.3','3.6.8'],application='本项目未核券商渠道、可得性、排队与成交，仍不得默认同收盘价成交；首版建议下一计划交易窗口，盘后模式另立协议且不回填2023/24。'),
 dict(id='TIME06',kind='material_information_cutoff',finding='盘后成交量/额在该阶段结束后才计入当日总量；含完整日量的特征不能默认为15:00已知，可能需要15:30后并加供应商延迟。',source_id='SZSE_2026_RULE_PDF',articles=['3.6.10'],application='信息截止需逐字段定义；若15:05作决策只能用已认证的局部成交量版本，不能事后拿完整日量回填。'),
 dict(id='TIME07',kind='design_inference',finding='日OHLC未保存盘内高低先后；同一日同时触及止盈止损不能默认有利顺序。',application='记录路径顺序不明；允许保守/区间/排除敏感性，但处理须事先固定。持有首日开盘前的日内高低也不可计入真实持仓MAE。'),
 dict(id='TIME08',kind='source_supported_and_design_requirement',finding='除权除息参考价改变价格标尺，股数与现金权利可能变化；原价下降不等于同额财富损失。',source_id='SZSE_2026_RULE_PDF',articles=['4.4.1','4.4.2','4.4.3'],application='先固定毛财富含现金/股份/应收权益及实际可用现金的区别；股息税、权利到账/锁定、配股选择与成本另列未知，不默认红利税0。'),
 dict(id='TIME09',kind='source_supported_and_design_requirement',finding='无成交时收盘价可沿用前收盘价；有价格字段不证明新成交、可买卖或可退出。',source_id='SZSE_2026_RULE_PDF',articles=['4.2.3','4.3.3'],application='共同终点如无法退出，分别报告市值估值和未平仓/价格陈旧状态，不能把估值当已实现现金。'),
 dict(id='TIME10',kind='scope_requirement',finding='用户已确认首版优先收盘后买入vs等待；这次确认不冻结H、最大等待、确认条件、费用、仓位或真实交易许可。',application='现有草案保持不改；新确认另存需求变更，所有未定阈值继续NULL，不因审查完成就开放真实标签或资金。')]
 after={p:sha(ROOT/p) for p in localsources};ck('all_old_sources_unchanged',before==after)
 result=dict(audit_id='label_timing_and_A_share_rule_design_review_20261101',client_date='2026-11-01',retrieved_at_utc=datetime.now(timezone.utc).isoformat(),scope='Definition/source review only; no price-outcome database opened, target generated, model fit or probability scoring',all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_sha256_before=before,source_sha256_after=after,public_sources=sources,new_web_observation_sha256={str(p.relative_to(ROOT)):sha(p) for p in rawfiles},findings=findings,new_labels_generated=False,new_model_fits=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,formal_input_approved=False,runtime_usable=False,old_forecast_or_risk_modified=False,limitations=['Selected provisions, not complete legal, historical or account eligibility certification','2026 rule snapshot cannot be used to fill 2023/2024 original execution status','No new binary download; fresh web parsed records and old originals separately identified','Daily broker costs, actual cash/security availability, dividend tax and full rule amendment chain remain unknown'])
 write(OUT/'来源与设计审查.json',result)
 md='''# 预测标签：信息时点与A股制度适配审查

2026年11月1日。仅审查定义、已存来源与新公开规则观察；没有查询真实价格结果数据库、生成标签或训练模型。用户本次只确认首版优先“收盘后判断回落时买入还是继续等待”，没有确认期限、等待上限、确认信号或仓位。

## 必须进入主交付的时间线

信号归属日 → 必需字段真正可得 → 决策生成 → 下一预定执行窗口 → 委托/部分或全部成交 → 共同终点评价 → 结果成熟。每个阶段分别记录时间和时区。原始行情标记某日，不能认证它在该日收盘一刻就已完整到达。建议业务时间使用Asia/Shanghai，保存UTC；加拿大时区只用于用户显示和研究排程。

旧标签的“第5观察日”是行情行号规则，停牌、缺记录时可能跨越不同数量的计划交易日。正式买入/等待比较应先固定在决策时可知的官方计划交易日终点，且两策略使用同一终点；H仍待确认。实际不可成交不能靠跳到下一有价格日抹去。无交易时收盘字段可能沿用旧价，须区分新成交、估值和实际平仓。

## 规则核对与关键例外

2026深交所通知确认为7月6日生效。规则3.1.4与3.1.5分别规定交收前出售限制和回转例外；普通现金A股不能假设把刚买入数量立即卖出。做T需要原有可卖数量及批次、资金、在途订单，和首版空仓买入/等待分开。价格、时间队列和对手方决定成交；开盘印记不保证用户买到。[官方通知](https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html)、[规则PDF](https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf)。

**不能把“完成收盘信号后绝无当日收盘价成交途径”写成普遍事实。** 现行版本3.6.1—3.6.3允许A股盘后固定价格交易，15:05—15:30按收盘价、时间优先撮合；停牌至15:00的证券不参与。这里仍未认证券商渠道、历史可得、排队或实际成交，所以本项目不能默认同价成交，建议首版使用下一计划执行窗口；盘后方式须另立协议，不回填2023—2024。[规则3.6节](https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf)。

同章3.6.10要求盘后量额在该阶段结束后计入当日总量。因此以完整日量计算的特征可能需要15:30之后及供应商延迟，不能把后来的全日量当15:00已知。若另做15:05决策，必须保存当时局部量快照并独立定义，而不能和完整日量混用。[规则3.6.10](https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf)。

## 价格、权益与风险口径

除权除息改变参考价，财富评价需分开股票数量、剩余现金、已付或应收股息/股份及税费。应收权益不是可直接使用的现金，原价下跌不等于同额财富损失。股息税、到账和锁定及配股行为仍未确定，不能默认0或无条件计入。[规则4.4节](https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf)。

日OHLC无法辨别盘中高低先后。同日同时触及上下风险线，记为先后未知，不默认有利路径；实际买入前的盘内高低不得计入持仓MAE。到共同终点无法卖出时，保留市值估值、报价陈旧与未平仓状态；不能把按收盘估值当成已实现现金。这些是数据/方法推论，不是规则原文给出的成交保证。

本次仍保留原草案NULL字段、1万元条件性意向和2000元已实现亏损暂停口径，浮亏另列；不修改风险配置，不开证券账户或真实订单。2023规则原件和中间修订链、逐日历史状态、真实佣金与包费、精确交收/账户可卖量尚有缺口。这里只核选定条款，不宣称完整制度准入。

## 来源保存

本地旧规则PDF、提取页、通知HTML和既有报告只读，源前后SHA列于来源与设计审查.json。新增保存的是web.run公开检索/解析观察JSON，带官方URL、日期和SHA；没有把解析响应说成新取得的原始PDF。旧本地原件和新观察分开，2026生效条款不作2023/2024回填。
'''
 (OUT/'来源与设计审查.md').write_text(md)
 print(json.dumps(dict(saved=True,checks=len(checks),important_boundary='2026 afterhours and complete daily-volume availability',old_sources_unchanged=True),ensure_ascii=False))

if __name__=='__main__':main()
