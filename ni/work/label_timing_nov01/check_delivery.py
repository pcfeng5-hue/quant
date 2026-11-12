"""Independent delivery correspondence review for timing/rules/confirmation."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/预测问题与标签适用性审查_20261101'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
 names=['预测问题与标签适用性审查_v1.md','预测事件字典_v1.json','状态与资格字典.json','审查范围与设计合同.json','本次用户确认与待定参数.json','来源与版本索引.json','合成案例与精确计算.json']
 before={n:sha(OUT/n) for n in names}
 report=(OUT/names[0]).read_text();events=read(OUT/names[1]);states=read(OUT/names[2]);cfg=read(OUT/names[3]);confirm=read(OUT/names[4]);source=read(OUT/names[5]);synth=read(OUT/names[6])
 event={r['id']:r for r in events['events']};cases={r['case_id']:r for r in synth['cases']};own=read(WORK/'来源与设计审查.json')
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details))
  if not ok:raise AssertionError(name)
 ck('user_first_question_exact_and_not_funds_authorization',cfg['user_confirmed']['first_use_case']=='收盘后判断回落时该买入还是继续等待' and cfg['user_confirmed']['is_trading_or_capital_authorization'] is False)
 ck('flat_comparison_is_design_assumption_not_user_confirmation','starting_comparison_state' not in cfg['user_confirmed'] and not any('空仓' in text for text in confirm['confirmed']) and 'flat' in json.dumps(cfg['assistant_design_recommendations_not_frozen'],ensure_ascii=False))
 ck('all_pending_fields_null_and_not_user_frozen',len(cfg['pending_freeze'])==15 and all(v is None for v in cfg['pending_freeze'].values()),'15 grouped parameter fields; not a count of every sub-parameter')
 ck('pending_parameters_identical_in_dictionary_and_confirmation',events['pending_freeze']==cfg['pending_freeze'] and confirm['not_confirmed']==list(cfg['pending_freeze']))
 ck('old_horizon_only_engineering_and_clock_preserved',cfg['existing_engineering_label']['horizon']==5 and cfg['existing_engineering_label']['clock']=='observed_stock_bars_not_certified_planned_exchange_sessions' and event['L00']['formula']=='C[t+5]/O[t+1]-1' and event['L00']['clock']=='observed_stock_bars')
 ck('5_planned_sessions_only_discussion_not_confirmation','5 planned exchange sessions is an option for discussion, not confirmed' in cfg['assistant_design_recommendations_not_frozen']['horizon_discussion_example'])
 ck('decision_and_information_cutoff_not_fixed_1500',cfg['pending_freeze']['decision_datetime_and_information_cutoff'] is None and '收盘后不等于一切日数据都已齐' in report and '实际已可得' in report)
 ck('afterhours_channel_explicit_without_fill_guarantee','15:05—15:30' in report and '不能笼统说收盘后绝无' in report and '并未认证用户渠道、字段可得或排队成交' in report)
 ck('full_daily_volume_available_only_after_afterhours_plus_delay','盘后量额在结束后并入当日总量' in report and '不能默认15:00已拥有完整日量' in report and '实际数据到达可能晚于交易所结束时刻' in report)
 ck('planned_clock_differs_from_observed_and_calendar_not_approved',cfg['pending_freeze']['validated_exchange_planned_calendar'] is None and '自然日、计划交易日和股票实际有观察记录' in report and not cases['S20']['result']['same_horizon'])
 ck('single_common_T_no_late_entry_extension',cfg['primary_comparison']['common_terminal_time_required'] and cfg['primary_comparison']['late_confirmation_cannot_extend_terminal_time'] and not cases['S16']['result']['extend_T'])
 ck('last_day_new_purchase_not_assumed_liquidated',not cases['S16']['result']['can_finish_cash_round_trip'] and 'd4收盘确认、d5买入，不能默认d5已能卖出' in report)
 ck('cash_equity_new_purchase_and_T_sellable_lots_separate','普通A股新买数量不能默认当日卖出' in report and '须核已有可卖批次与账户状态' in report and cases['S10']['result']['blocked'])
 ck('ordinary_price_print_and_daily_volume_not_specific_fill','开/收盘记录、日内触价或有成交量都不能证明特定订单成交' in report and cfg['primary_comparison']['counterfactual_fills_identified_from_daily_prices'] is False)
 ck('intraday_T_deferred_not_inferred_from_daily_bars',event['L11']['status']=='deferred_not_identifiable_from_current_daily_inputs' and event['L10']['status']=='later_separate_question_not_this_primary_scope')
 ck('NAV_not_cash_and_liquidation_unknown_explicit',cfg['wealth_conventions']['NAV_is_realized_profit'] is False and cases['S18']['result']['liquidation_cash'] is None and '事件结果不能偷换成NAV' in report)
 ck('missing_unfilled_and_partial_fill_not_zero',states['unknown_is_not_zero'] and states['missing_or_unfilled_trade_return'] is None and cases['S11']['result']['trade_return'] is None and 'PARTIAL_FILL' in states['independent_axes']['execution'])
 ck('maturity_requires_actual_result_availability','结果成熟后' in report and '不能只看名义T日期' in report and 'NOT_MATURE' in states['independent_axes']['maturity'])
 ck('corporate_action_and_receivables_not_cash','应收现金不自动等于可用现金' in report and '机械除权价格下落不能直接当财富损失' in report and '股息税' in report)
 ck('costs_taxes_slippage_and_portfolio_limits_remain_pending',cfg['pending_freeze']['fees_slippage_and_dividend_tax'] is None and cfg['pending_freeze']['user_risk_limits_beyond_existing_realized_pause'] is None and '不能将已含佣金的项目再加一遍' in report)
 ck('OHLC_order_unknown_and_touch_not_fill',event['L08']['touch_equals_fill'] is False and cases['S09']['result']['OHLC_only_first_hit'] is None and '同日高低都跨线时先后不明' in report)
 ck('history_rule_chain_not_backfilled_from_2026',source['rules_not_certified_for_every_historical_date'] is True and '2026制度不能回填2023—2024' in report and '规则链及实际费用仍未全部认证' in report)
 ck('new_parsed_sources_separate_from_saved_originals',source['public_sources']==own['public_sources'] and source['new_web_observation_sha256']==own['new_web_observation_sha256'] and 'not a newly downloaded binary PDF' in source['root_web_response']['kind'])
 ck('all_public_observation_and_old_selected_hashes_unchanged',all(sha(ROOT/p)==v for p,v in source['new_web_observation_sha256'].items()) and all(sha(ROOT/p)==v for p,v in source['old_official_source_sha256'].items()) and sha(ROOT/source['root_web_response']['path'])==source['root_web_response']['sha256'])
 ck('known_official_pdf_urls_match_successful_parsed_provenance','https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf' in (ROOT/source['root_web_response']['path']).read_text() and 'https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf'==source['public_sources'][1]['url'])
 ck('all_examples_fictional_no_real_market_observations',synth['all_examples_are_fictional'] and synth['real_market_observations_used']==0 and len(cases)==21 and all(r['all_inputs_are_synthetic'] and r['not_a_market_forecast'] for r in cases.values()))
 ck('hypothetical_future_available_information_rejected',cases['S19']['result']['eligible_at_old_cutoff'] is False and cases['S19']['result']['new_prediction_requires_new_cutoff'])
 ck('confirmed_realized_pause_and_floating_distinction_retained','累计已实现亏损2000元暂停新增买入并复核、浮亏单列不变' in report and '不因本步完成使用资金' in report)
 ck('no_new_market_label_score_or_later_target_opening',all(cfg['guardrails'][k] is False for k in ['new_real_target_labels','new_models_or_real_probability_scores','outcomes_2025_2026_opened','old_forecast_draft_modified','confirmed_risk_settings_modified','formal_input_approved','runtime_usable','current_forecast_generated']) and cfg['guardrails']['cumulative_research_variants_unchanged']==16)
 ck('old_draft_hash_matches_registered_original',sha(ROOT/'outputs/首版预测协议草案_20261016.json')=='f9035be2c22e906eebd6a04f1563021284f18d377450b4b10e0590a4639183ee')
 for name in ['build_review.py','synthetic_examples.py']:
  tree=ast.parse((ROOT/'work/label_review_nov01'/name).read_text())
  imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
  ck('no_market_DB_query_or_network_library_'+name,not any((i or '').split('.')[0] in ['sqlite3','duckdb','pandas','requests','akshare','tushare'] for i in imports),imports)
 build=read(OUT/'本轮构建核验.json')
 ck('all_old_protected_files_unchanged_since_build',all(sha(ROOT/p)==v for p,v in build['protected_source_sha256'].items()))
 after={n:sha(OUT/n) for n in names};ck('audited_delivery_files_unchanged_during_review',before==after)
 result=dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,delivery_sha256=after,pending_grouped_parameter_count=15,scope='Timing, selected A-share rules, confirmation boundary and source correspondence; no new market targets or model computations',old_sources_sha256=source['old_official_source_sha256'],new_market_labels_generated=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False)
 write(WORK/'交付对应核验.json',result)
 (WORK/'交付对应核验.md').write_text(f'''# 时间与制度交付对应核验

2026年11月1日。{len(checks)}/{len(checks)}项通过。用户确认只保留首版“收盘后回落买入vs等待”；空仓初始状态另列为设计假设。15个合并参数字段继续为NULL，没有把5日、下一窗口、等待上限、费用或仓位锁定成用户参数。

共同计划终点、观察日区别、实际可得截止、2026盘后通道及全日量完整时点、可卖批次、晚确认、NAV与变现、未成交/缺失/未成熟、权益和税费未知均对应。正式历史规则链仍未知，不将2026条款回填2023/2024。新官方解析响应与旧二进制原件分别保留且SHA一致。

检查的是定义和交付对应，不认证真实成交、历史PIT、预测优势或账户功能。未查询实际目标表、未生成新标签、模型或评分，2025/2026结果继续隔离。7份被审主文件SHA在JSON中锁定。完成后停止项目写入，供根冻结归档。
''')
 print(json.dumps(dict(saved=True,passed=len(checks),total=len(checks),audited_files=7),ensure_ascii=False))

if __name__=='__main__':main()
