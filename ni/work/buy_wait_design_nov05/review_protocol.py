"""Independent, metadata-only BW17 definition review; no market values or DBs."""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/输入证据合库与验证设计_20261105'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol_path = OUT / '买入还是等待_研究候选BW17_冻结v1.json'
    prose_path = OUT / '买入还是等待_研究候选BW17_冻结说明.md'
    registry_path = OUT / '累计研究选择登记_增补BW17.json'
    params_path = OUT / '本轮用户确认与参数状态.json'
    freeze_path = OUT / '设计冻结与来源指纹.json'
    paths = [protocol_path, prose_path, registry_path, params_path, freeze_path]
    initial_hashes = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    p, registry, params, freeze = map(read, [protocol_path, registry_path, params_path, freeze_path])
    prose = prose_path.read_text()
    checks = []

    def ck(name, ok, detail):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    ck('protocol_identity_and_definition_status',
       p['protocol_id'] == 'BW17_002414_buy_vs_wait_H10_W2_v1'
       and p['definition_only'] is True
       and p['status'] == 'candidate_definition_frozen_evidence_bindings_missing_not_executable',
       'Single frozen candidate definition, explicitly not executable prediction.')
    ck('user_H10_research_H10_same',
       p['user_binding']['H_planned_sessions'] == p['research_constants']['H_planned_sessions']
       == params['confirmed_value'] == params['latest_user_parameter_state']['main_horizon_planned_exchange_sessions'] == 10,
       'Future tenth planned session from decision, not from delayed entry.')
    ck('exactly_one_user_group_confirmed_14_remain_null',
       len(params['latest_user_parameter_state']) == 15
       and sum(v is None for v in params['latest_user_parameter_state'].values()) == 14
       and params['confirmed_groups'] == 1 and params['pending_groups'] == 14,
       'Research design assumptions are not silently promoted to user preferences.')
    ck('protocol_unbound_14_groups_match_parameter_state',
       p['unbound_user_groups'] == {k: v for k, v in params['latest_user_parameter_state'].items()
                                   if k != 'main_horizon_planned_exchange_sessions'}
       and all(v is None for v in p['unbound_user_groups'].values()),
       'Only confirmed H is omitted from unbound set.')
    old_path = ROOT / 'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json'
    old = read(old_path)
    ck('old_15_null_contract_unchanged',
       sha(old_path) == params['old_15_null_contract_sha256'] == freeze['source_hashes'][str(old_path.relative_to(ROOT))]
       and len(old['pending_freeze']) == 15
       and all(v is None for v in old['pending_freeze'].values()),
       'Old contract preserved; current confirmation is an append-only newer state.')
    ck('registration_16_plus_one_equals17_no_models_labels_scores',
       registry['old_registered_choices'] == 16 and registry['total_registered_choices'] == 17
       and registry['new_choice']['id'] == p['research_selection_id'] == 17
       and registry['new_choice']['definition_id'] == p['protocol_id']
       and registry['new_choice']['models_fitted'] == registry['new_choice']['real_labels']
       == registry['new_choice']['scores'] == registry['new_evaluated_choices'] == 0,
       'New policy definition counted once before any outcome calculation.')
    ck('H5_not_treated_as_frozen_or_scored_alternative',
       p['registration_basis']['H5_was_discussion_only_never_frozen_or_scored'] is True,
       'No phantom scored H5 choice or selective H comparison.')
    ck('common_cash_sleeve_not_actual_account_claim',
       p['paths']['all_paths']['same_initial_cash_and_allocation_algorithm'] is True
       and p['research_constants']['starting_cash_CNY'] == 10000
       and 'actual account state unknown' in p['scope']['starting_research_sleeve']
       and params['actual_account_flat_confirmed'] is False,
       'A/B/C comparison starts with hypothetical equal cash; actual account state is unknown.')
    ck('cutoff_timezone_no_automatic_availability',
       p['research_constants']['decision_cutoff_local'] == '18:00:00'
       and p['research_constants']['decision_timezone'] == 'Asia/Shanghai'
       and 'Late arrival after18:00 cannot become same-day input' in p['time_and_population']['no_late_data_backfill'],
       'Clock is a research convention; late versions cannot be backfilled into same-day information.')
    ck('planned_adjacent_session_not_stock_bar_clock',
       'planned adjacent-session' in p['time_and_population']['eligibility']
       and 'missing/suspended stock bars do not shift' in p['time_and_population']['session_clock']
       and 'do not substitute prior observed stock bar' in p['time_and_population']['first_date_missing_previous_session'],
       'Missing observations do not change d0, predecessor, or T.')
    ck('false_versus_unknown_eligibility',
       'FALSE with reason' in p['time_and_population']['false_vs_unknown']
       and 'UNKNOWN, never FALSE' in p['time_and_population']['false_vs_unknown'],
       'Evidence gaps do not become an apparently successful no-signal result.')
    ck('future_actions_not_retrospective_population_filter',
       'Do not use any future d1..d10 event to exclude d0 retrospectively' in p['time_and_population']['mechanical_action_rule'],
       'Future actions affect policy wealth; missing terms remain unknown with coverage disclosed.')
    ck('asof_versions_and_actual_label_maturity_required',
       'version_first_available_at <=' in p['time_and_population']['input_asof']
       and 'unknown maturity remains unknown' in p['time_and_population']['label_maturity']
       and 'all necessary validation timestamps' in p['time_and_population']['label_maturity'],
       'Version/fetch times are not confused; all outcome prerequisites must have matured.')
    ck('A_next_session_B_first_confirmation_1_or2',
       p['paths']['A_now']['attempt_session'] == 'd1'
       and p['paths']['B_wait']['confirmation_scan_sessions'] == [1 and 'd1', 'd2']
       and p['research_constants']['max_confirmation_sessions'] == 2
       and p['paths']['B_wait']['last_possible_entry_session'] == 'd3',
       'A enters no earlier than next window; B confirms after observed close then uses next window.')
    ck('earlier_unknown_confirmation_not_skipped',
       'any earlier UNKNOWN makes first-confirmation history unresolved' in p['paths']['B_wait']['confirmation'],
       'No later convenient signal substitutes for unresolved first confirmation.')
    ck('one_attempt_no_chasing_or_topups',
       p['paths']['A_now']['attempts'] == p['paths']['B_wait']['attempts'] == 1
       and p['paths']['all_paths']['no_chasing_no_retry_no_topups'] is True,
       'Research action policy is finite and not a discretionary retry strategy.')
    ck('fixed_common_terminal_d10',
       p['paths']['all_paths']['common_terminal'] == 'T=d10 close, fixed from d0, never reset from later buy',
       'The later B entry cannot obtain a later endpoint.')
    ck('future_confirmation_not_d0_feature',
       p['paths']['all_paths']['future_B_confirmation_is_a_policy_action_input_not_a_d0_forecast_feature'] is True,
       'Future information only drives the waiting policy at the future decision time.')
    ck('quantity_fee_lot_unknown_not_zero',
       'certified_order_time_fee_upper_bound' in p['order_and_wealth_contract']['quantity_formula']
       and 'if lot rule or fee bound is unknown then UNKNOWN, not q=0' in p['order_and_wealth_contract']['quantity_formula']
       and p['research_constants']['assumed_buy_lot_shares'] == 100,
       'Cash-constrained quantity is undefined until lot applicability and fee bound are certified.')
    ck('counterfactual_fill_not_claimed_actual',
       p['order_and_wealth_contract']['daily_open_or_touch_proves_fill'] is False
       and 'MODEL_BASED_COUNTERFACTUAL' in p['order_and_wealth_contract']['counterfactual_fill_status']
       and 'never actual realized fills' in p['order_and_wealth_contract']['counterfactual_fill_status'],
       'OHLC observations cannot establish both counterfactual executions.')
    ck('three_required_bindings_remain_null',
       all(p['order_and_wealth_contract'][k] is None for k in [
           'execution_binding', 'fee_and_tax_binding', 'corporate_action_and_liability_binding']),
       'No fee, fill, or rights assumption is silently certified.')
    ck('partial_fills_remaining_cash_and_cancellation',
       'record each fill' in p['order_and_wealth_contract']['partial_and_remaining']
       and 'confirmed valid cancellation, otherwise unresolved' in p['order_and_wealth_contract']['partial_and_remaining'],
       'Actual filled quantities and residual cash are needed; unresolved cancellations stay unresolved.')
    ck('NAV_complete_and_not_liquidation',
       p['order_and_wealth_contract']['NAV_formula'] == 'cash_T + shares_T*validated_mark_T + supported_rights_and_receivables_T - unpaid_taxes_fees_other_liabilities_T'
       and p['order_and_wealth_contract']['NAV_not_realized_profit_or_executable_cash'] is True,
       'Terminal wealth is marked NAV and cannot be described as realized tradable cash.')
    ck('no_double_fees_or_dividends',
       'do not subtract twice' in p['order_and_wealth_contract']['paid_fees_rule']
       and 'cannot both remain counted' in p['order_and_wealth_contract']['dividend_rule']
       and 'not a fictitious liquidating trade fee' in p['order_and_wealth_contract']['future_sale_fees'],
       'Paid charges, dividends/receivables, and hypothetical sell fees are treated consistently.')
    ck('positive_position_missing_mark_or_execution_makes_label_null',
       'wealth and paired target NULL' in p['order_and_wealth_contract']['unknown_end_mark_with_positive_position']
       and 'affected wealth and paired target NULL' in p['order_and_wealth_contract']['unknown_execution_fee_or_rights'],
       'Unknown prerequisites do not become zero P&L or a certified stale mark.')
    ck('Tplus1_and_halt_rules_require_historical_evidence',
       'no universal2026 rule backfill' in p['order_and_wealth_contract']['T_plus_1_and_halts']
       and 'no assumption that fresh buys can be sold same-day' in p['order_and_wealth_contract']['sellability'],
       'Tradeability is a separate historical state, not inferred from net position or marks.')
    ck('paired_delta_and_strict_three_signs',
       p['labels_and_reporting']['paired_primary_delta'] == 'delta=(NAV_B(T)-NAV_A(T))/initial_cash'
       and all(s in p['labels_and_reporting']['strict_paired_event'] for s in [
           'delta>0', 'delta=0', 'delta<0', 'UNKNOWN', 'never hidden epsilon'])
       and p['labels_and_reporting']['economic_neutral_band'] is None,
       'Strict mathematical ties are separate; no unapproved economic threshold is invented.')
    ck('marginals_not_subtracted_into_paired_probability',
       p['labels_and_reporting']['paired_probability_not_difference_of_marginals'] is True
       and 'can lose money even if it wins' in p['labels_and_reporting']['per_path_cash_relative'],
       'Relative policy advantage is different from profitability or difference of marginal probabilities.')
    ck('nontrade_return_null_state_axes_separate',
       'trade return itself remainsNULL when no trade' in p['labels_and_reporting']['nontrades']
       and 'independent eligibility, confirmation, order, terminal, label-maturity states' in p['labels_and_reporting']['unknown_vs_censored_vs_immature'],
       'Known cash policy wealth is meaningful; nonexistent trade return is not zero.')
    ck('complete_population_and_coverage_denominators',
       'keep all planned d0 dates' in p['labels_and_reporting']['denominators']
       and 'E=TRUE and both terminal paths identified' in p['labels_and_reporting']['denominators']
       and 'missingness selection' in p['labels_and_reporting']['denominators'],
       'Identifiable paired subset is not presented as the entire eligible population.')
    ck('development_and_later_outcome_isolation',
       p['scope']['data_dates_for_future_development_only'] == ['2023-01-03', '2024-12-31']
       and p['scope']['these_dates_are_previously_seen_development_not_independent_test'] is True
       and p['scope']['targets_2025_2026_isolated'] is True
       and p['scope']['no_cross_2024_endpoint_or_outcome_read'] is True,
       '2023/24 are seen development; later targets cannot complete right-censored events.')
    reqs = p['labels_and_reporting']['time_order_requirements']
    ck('maturity_purge_overlap_and_shared_cohort_requirements',
       any('label_mature_at earlier' in x for x in reqs)
       and any('purge all training outcome windows' in x for x in reqs)
       and any('never count them as independent' in x for x in reqs)
       and any('shared paired cohort' in x for x in reqs),
       'Future train/evaluation procedure must respect delayed labels and dependent overlapping outcomes.')
    ck('descriptive_only_predictive_acceptance_not_claimed_frozen',
       'no success threshold, model promotion or current action' in p['labels_and_reporting']['phase1_acceptance']
       and 'Separate preregistration' in p['labels_and_reporting']['future_predictive_acceptance']
       and p['gates']['predictive_model_protocol_frozen'] is False,
       'Candidate freezing does not solve estimator, sample size, calibration or promotion acceptance.')
    ck('only_definition_gate_open_all_runtime_gates_closed',
       p['gates']['definition_frozen'] is True
       and all(v is False for k, v in p['gates'].items() if k != 'definition_frozen'),
       'No real labels, fitting, scores, forecast, simulation or funds follow automatically.')
    ck('prior_risk_and_capital_authorization_preserved',
       p['confirmed_risk_preservation']['existing_pause_realized_loss_CNY'] == 2000
       and p['confirmed_risk_preservation']['floating_PnL_reported_separately'] is True
       and p['confirmed_risk_preservation']['this_is_not_capital_authorization'] is True
       and params['capital_or_trading_authorized'] is False
       and params['risk_setting_modified'] is False,
       'The existing conditional realized-loss pause is not loosened or activated as a trading mandate.')
    ck('frozen_protocol_file_and_canonical_hash',
       sha(protocol_path) == freeze['file_sha256']
       and hashlib.sha256(json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
       == freeze['canonical_json_sha256'],
       'Both original file and canonical JSON body hash agree with the frozen manifest.')
    ck('user_confirmation_file_hash',
       sha(params_path) == freeze['new_user_confirmation_file_sha256'],
       'Explicit user horizon confirmation corresponds to the frozen parameter record.')
    ck('five_source_fingerprints_unchanged',
       len(freeze['source_hashes']) == 5
       and all(sha(ROOT / path) == digest for path, digest in freeze['source_hashes'].items()),
       'Only existing allowed metadata sources are fingerprinted; no raw responses or outcomes read.')
    ck('explanatory_prose_matches_H10_and17_and_gated_status',
       all(s in prose for s in ['第10个计划交易日', '第17项研究选择', '其余14组待定', '真实标签生成、拟合、评分、当前预测、模拟和资金使用全部关闭']),
       'Human-readable explanation does not overstate the machine-readable protocol.')

    # Independent arithmetic/timeline examples; all values are invented and are
    # not stock prices, frozen policy executions, market labels, or probabilities.
    T, W = 10, 2
    entries = [j + 1 for j in range(1, W + 1)]
    ck('synthetic_timeline_first_confirmation_entry2or3_terminal10',
       entries == [2, 3] and all(e < T for e in entries),
       'Two possible delayed entry sessions both retain d10 rather than d12/d13.')
    D = Decimal
    B = D('10000')
    now_cash = B - D('100') * D('10') - D('5')
    wait_cash = B - D('100') * D('9') - D('5')
    now_nav = now_cash + D('100') * D('11')
    wait_nav = wait_cash + D('100') * D('11')
    ck('synthetic_NAV_paid_fee_once_and_paired_delta',
       now_nav == D('10095') and wait_nav == D('10195')
       and (wait_nav - now_nav) / B == D('0.01'),
       'Accounting identity only, not a full-policy quantity simulation or a market result.')
    ck('synthetic_dividend_receivable_to_cash_conserves_NAV',
       (D('9000') + D('200') + D('100') * D('10'))
       == (D('9200') + D('0') + D('100') * D('10')),
       'When dividend receivable is paid, cash rises as receivable falls; no double counting.')
    ck('synthetic_paired_winner_may_still_lose_to_cash',
       D('9950') > D('9900') and D('9950') < B and D('9900') < B,
       'WAIT_HIGHER is not a guaranteed profitable policy.')
    ck('review_did_not_mutate_five_main_deliverables',
       initial_hashes == {str(p.relative_to(ROOT)): sha(p) for p in paths},
       'This independent review writes only its own work directory.')

    failed = [c for c in checks if not c['passed']]
    result = {
        'review_id': 'BW17_definition_math_state_independent_review_20261105_v1',
        'reviewer': '/root/buy_wait_design_nov05',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Frozen definition metadata, mathematical identities and state/timeline review only',
        'all_checks_passed': not failed,
        'passed': sum(c['passed'] for c in checks),
        'total': len(checks),
        'checks': checks,
        'main_artifact_hashes': initial_hashes,
        'critical_findings': failed,
        'nonblocking_limits': [
            'H10 is interpreted as the tenth planned session known at d0, not the tenth later observed stock bar. Unexpected closures or missing certified terminal marks cannot silently shift T; a positive-position terminal wealth then stays unknown.',
            'The one opening-auction attempt and cancellation are design intentions, not certified execution. Historical rules and a separately frozen model must instantiate them; no assumed fill is approved.',
            'Only a single policy definition is frozen. Fees, execution, rights, predictive estimator, minimum sample, uncertainty and promotion thresholds remain unbound; no executable probability-forecast protocol is approved.',
            'Conditional identifiable-sample frequencies can be biased by missingness; the frozen coverage ledger is essential and does not make empirical frequency a current forecast.'
        ],
        'new_market_or_database_reads': False,
        'raw_price_or_outcome_content_read': False,
        'new_real_labels': 0,
        'new_models_or_scores': 0,
        'outcomes_2025_2026_opened': False,
        'synthetic_examples_only': True,
        'does_not_certify_PIT_execution_costs_or_predictive_ability': True,
        'recommendation': 'Accept definition freeze and selection registration only; keep all evidence, label, predictive and runtime gates closed.' if not failed else 'Resolve failed independent checks before publishing a passed review.'
    }
    (WORK / '复核.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    report = f'''# BW17定义的数学与状态独立复核

复核对象为2026年11月5日冻结的 `BW17_002414_buy_vs_wait_H10_W2_v1`，只读五份主交付及所列元数据来源；没有查询数据库、原始行情、真实结果或后期目标。

结果：**{result['passed']}/{result['total']}项通过**。没有发现需要修改冻结版本的重大数学、时序或NULL状态问题。核验对象是候选定义与其来源对应，不是预测有效性或数据准入。

- 主期限来自本轮用户确认：d0之后第10个计划交易日为共同T。等待仅观察d1/d2，最迟d3尝试入场，不能从晚入场另数10天。
- 当前参数记录仅H10被确认，其余14组NULL；旧15组NULL合同及指纹保持不变。研究常数没有回填为用户偏好。
- 新候选作为第17项定义登记；旧16项和否定结果保留，没有把未冻结的H5讨论另算已评分变体。
- 已知未触发/未成交的现金政策、无交易的NULL交易收益、未知成交、缺费用/权益、未成熟与右删失分别记录；日K不被当作订单成交证据。
- NAV、已付费用、应收与到账股息、未付负债及无真实卖出时的费用口径一致。未来公司行动不事后用于筛除d0人口。
- 2023—2024仅为已见开发期，结果跨年右删失；2025/2026继续隔离。成熟时点、跨界结果窗口和重叠依赖已有约束。

四个完全虚构的数学/时间检查只验证共同终点与账本恒等式，不产生股票标签、策略收益或概率。

仍有必要限制：计划日历遇临时休市或缺失终点不能静默顺延T；开盘窗口和撤销尚待历史规则及模型实例化；费用、成交、权益、预测估计器和统计/经济晋级标准仍未绑定。当前全部真实标签、模型、评分、预测、模拟及资金门关闭。因此可接受**候选定义冻结**，不能宣布完整可执行预测协议已冻结。

逐项机器核验与主文件指纹见[复核.json](./复核.json)，独立代码见[review_protocol.py](./review_protocol.py)。本次未修改五份主交付。
'''
    (WORK / '复核.md').write_text(report)
    print(json.dumps({'passed': result['passed'], 'total': result['total'], 'all_checks_passed': not failed, 'failed': [c['check'] for c in failed]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
