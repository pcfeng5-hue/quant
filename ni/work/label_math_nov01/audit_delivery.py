"""Independent Fraction audit of fictional cases and design correspondence.

Only local design documents and fictional-case JSON are read. Production helpers
are imported solely for adversarial input tests, never as expected-value oracles;
their main is never executed. No market database or actual outcome row is read.
"""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal
from copy import deepcopy
import ast, hashlib, importlib.util, json

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/预测问题与标签适用性审查_20261101'
NAMES=['预测问题与标签适用性审查_v1.md','预测事件字典_v1.json','状态与资格字典.json','审查范围与设计合同.json','本次用户确认与待定参数.json','合成案例与精确计算.json','合成案例核验.json','合成案例说明.md']
OLD=['outputs/概率预测引擎详细方案_20261016.md','outputs/首版预测协议草案_20261016.json','work/baseline_oct25/engineering_contract.json']
CODE=ROOT/'work/label_review_nov01/synthetic_examples.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
    checked={str((OUT/name).relative_to(ROOT)):sha(OUT/name) for name in NAMES}
    checked[str(CODE.relative_to(ROOT))]=sha(CODE)
    old_before={rel:sha(ROOT/rel) for rel in OLD}
    checks=[]
    def ck(name,ok,detail=None):
        checks.append(dict(check=name,passed=bool(ok),detail=detail))
        if not ok:raise AssertionError(name)
    examples=read(OUT/'合成案例与精确计算.json')
    cases={r['case_id']:r for r in examples['cases']}
    ck('all_21_cases_unique_and_explicitly_fictional',len(cases)==21 and list(cases)==[f'S{i:02}' for i in range(1,22)] and examples['all_examples_are_fictional'] and examples['real_market_observations_used']==0 and all(r['all_inputs_are_synthetic'] and r['not_a_market_forecast'] for r in cases.values()))
    numeric_comparisons=[]
    def close(actual,expected,path):
        # Saved Decimal strings may round recurring fractions at 28 digits.
        # This tolerance concerns print precision, never event/sign thresholds.
        got=F(str(actual));expected=F(expected);difference=abs(got-expected)
        numeric_comparisons.append(dict(path=path,actual=str(actual),expected_fraction=str(expected),absolute_error_fraction=str(difference)))
        return difference<=F(1,10**26)
    def expected_round(B,q,entry,exit,bf=5,sf=5,T=5):
        B,q,entry,exit,bf,sf=map(lambda v:F(str(v)),[B,q,entry,exit,bf,sf])
        # Derive wealth from incremental cash P&L rather than invoking producer.
        change=q*(exit-entry)-bf-sf
        return dict(initial_wealth=B,terminal_day=T,terminal_wealth=B+change,net_change=change,raw_price_change=(exit-entry)/entry,filled_quantity=q,trade_return=change/(q*entry+bf))
    def round_matches(actual,expected,path):
        return all(close(actual[k],v,path+'.'+k) for k,v in expected.items()) and actual['terminal_basis']=='explicit_synthetic_filled_cash'
    def result(k):return cases[k]['result']
    for key,entry1,entry2,exit,delta in [('S01',10,9,'10.5',100),('S02',10,'10.8',11,-80)]:
        r=result(key)
        ck(key+'_independent_now_wait_wealth_and_trade_return',round_matches(r['now'],expected_round(2000,100,entry1,exit),key+'.now') and round_matches(r['wait'],expected_round(2000,100,entry2,exit),key+'.wait') and close(r['wait_minus_now'],delta,key+'.delta'))
    for key,exit,delta in [('S03',12,-190),('S04',8,210)]:
        r=result(key);w=r['wait']
        ck(key+'_cash_policy_not_zero_return_trade',round_matches(r['now'],expected_round(2000,100,10,exit),key+'.now') and close(w['initial_wealth'],2000,key+'.cash_B') and close(w['terminal_wealth'],2000,key+'.cash_W') and close(w['net_change'],0,key+'.cash_change') and w['trade_return'] is None and w['execution_status']=='NO_POSITION_NO_TRANSACTION' and close(r['wait_minus_now'],delta,key+'.delta'))
    ck('S05_raw_up_net_loss_five',round_matches(result('S05'),expected_round(2000,100,10,'10.05'),'S05') and F(result('S05')['raw_price_change'])>0 and F(result('S05')['net_change'])<0)
    ck('S06_exact_zero_raw_still_net_loss_ten',round_matches(result('S06'),expected_round(2000,100,10,10),'S06') and result('S06')['raw_price_change']=='0')
    expect=F(7,10)*F(1,100)+F(3,10)*F(-3,100)
    ck('S07_seventy_percent_winrate_negative_point_two_percent',close(result('S07')['expected_return'],expect,'S07.expected_return') and expect==F(-1,500))
    ck('S08_price_up_and_minus_thirty_percent_MAE',round_matches(result('S08')['terminal'],expected_round(2000,100,10,11),'S08.terminal') and close(result('S08')['raw_price_MAE'],F(7,10)-1,'S08.MAE') and result('S08')['MAE_is_realized_loss'] is False)
    a=cases['S09']['inputs']['pathA'];b=cases['S09']['inputs']['pathB']
    # Independent extrema and first crossing among the explicitly ordered nodes.
    hit=lambda path:next(('upper_first' if p>=11 else 'lower_first' for p in path if p>=11 or p<=9),'none')
    ck('S09_same_OHLC_cannot_determine_first_crossing', [a[0],max(a),min(a),a[-1]]==[b[0],max(b),min(b),b[-1]]==[10,12,8,11] and hit(a)=='upper_first' and hit(b)=='lower_first' and result('S09')['pathA_first']==hit(a) and result('S09')['pathB_first']==hit(b) and result('S09')['OHLC_only_first_hit'] is None and result('S09')['fill_guaranteed'] is False)
    ck('S10_same_day_sale_explicitly_blocked_not_realized',result('S10')['blocked'] and result('S10')['realized_trade_return'] is None and result('S10')['barrier_touch_is_not_sale'])
    ck('S11_known_no_fill_separate_cash_wealth_and_NULL_trade',result('S11')['execution_status']=='KNOWN_UNFILLED' and result('S11')['terminal_wealth']==2000 and result('S11')['trade_return'] is None and result('S11')['actual_trade_fee']==0 and 'no cash interest' in result('S11')['cash_path_assumptions'])
    ck('S12_partial_forty_shares_independent_wealth_2030',round_matches(result('S12'),expected_round(2000,40,10,11),'S12') and cases['S12']['inputs']['requested_quantity']==100)
    ck('S13_unknown_fees_or_fill_not_zero_imputation',close(result('S13')['raw_price_change'],F(1,10),'S13.raw') and result('S13')['net_profit_event'] is None and result('S13')['terminal_realized_cash'] is None and cases['S13']['inputs']['fees'] is None and cases['S13']['inputs']['fill_status']=='UNKNOWN')
    ck('S14_mechanical_price_halving_preserves_share_wealth',result('S14')['wealth_before']==100*10 and result('S14')['wealth_after']==100*2*5 and close(result('S14')['raw_price_change'],F(-1,2),'S14.raw'))
    ck('S15_complement_includes_zero_and_sell_event_unknown',close(result('S15')['nonpositive_probability'],1-F(3,5),'S15.nonpositive') and close(result('S15')['strict_negative_probability'],1-F(3,5)-F(1,10),'S15.negative') and result('S15')['sell_better_than_hold_probability'] is None)
    s16=cases['S16'];i=s16['inputs'];r=s16['result']
    ck('S16_confirmation_four_entry_five_earliest_sale_six',i['confirmation_day']+1==i['earliest_entry_day'] and i['earliest_entry_day']+i['example_minimum_sale_delay_sessions']>i['common_T'] and r['can_finish_cash_round_trip'] is False and r['keep_cash_or_separate_NAV_protocol'] is True and r['extend_T'] is False)
    ck('S17_all_mismatches_explicitly_rejected',set(cases['S17']['inputs']['mismatches'])=={'initial_wealth','terminal_day','terminal_basis'} and result('S17')['rejected_count']==3)
    s18=cases['S18'];i=s18['inputs'];r=s18['result'];nav=F(i['B'])-F(i['q'])*F(i['entry'])-F(i['entry_fee'])+F(i['q'])*F(i['terminal_mark'])
    ck('S18_NAV_2095_not_unfilled_liquidation_cash',close(r['terminal_NAV'],nav,'S18.NAV') and nav==2095 and r['realized_sale_profit'] is None and r['liquidation_cash'] is None and r['hypothetical_filled_cash_if_later_verified']==nav-5)
    ck('S19_later_information_not_in_earlier_forecast',cases['S19']['inputs']['information_cutoff']=='d0 15:01 Asia/Shanghai' and cases['S19']['inputs']['actual_available']=='d0 15:31 Asia/Shanghai' and result('S19')['eligible_at_old_cutoff'] is False and result('S19')['new_prediction_requires_new_cutoff'] is True)
    i=cases['S20']['inputs'];r=result('S20')
    ck('S20_planned_calendar_not_observed_bar_index',i['planned_sessions'][-1]==i['planned_T']=='d5' and i['observed_stock_bars'][4]==r['fifth_observed_bar']=='d6' and r['same_horizon'] is False and r['terminal_missing_valuation_or_fill_requires_explicit_status'] is True)
    i=cases['S21']['inputs'];r=result('S21');B=F(i['B']);qnow=B//10;qwait=B//11
    now=B+qnow*(9-10);wait=B+qwait*(9-11);late=B+qwait*(12-11)
    ck('S21_unit_one_wealth_8910_8100_not_unit100_example',qnow==990 and qwait==900 and close(r['now_at_common_day5'],now,'S21.now') and close(r['wait_at_common_day5'],wait,'S21.wait') and close(r['correct_wait_minus_now'],wait-now,'S21.delta') and close(r['wrong_wait_at_day7'],late,'S21.wrong_late') and wait<now<late and r['wrong_cross_time_comparison_forbidden'] is True and 'whole-unit' in i['synthetic_allocation_rule'])
    spec=importlib.util.spec_from_file_location('audited_teaching_helpers',CODE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def rejected(fn,*args,**kwargs):
        try:fn(*args,**kwargs)
        except ValueError:return True
        return False
    for value in ['NaN','Infinity','-Infinity',None,{},True]:
        ck('money_rejects_'+str(value),rejected(module.money,value))
    for key,args,kw in [
      ('zero_start',(0,100,10,11),{}),('negative_start',(-1,100,10,11),{}),('zero_quantity',(2000,0,10,11),{}),('negative_quantity',(2000,-1,10,11),{}),('fractional_quantity',(2000,'1.5',10,11),{}),('zero_entry',(2000,100,0,11),{}),('zero_exit',(2000,100,10,0),{}),('negative_fee',(2000,100,10,11),{'buy_fee':-1}),('unknown_fee',(2000,100,10,11),{'buy_fee':None}),('minimum_fee_exceeds_cash',(1004,100,10,11),{}),('same_day_exit',(2000,100,10,11),{'entry_day':1,'exit_day':1}),('negative_day',(2000,100,10,11),{'entry_day':-1}),('fractional_day',(2000,100,10,11),{'exit_day':5.5}),('boolean_day',(2000,100,10,11),{'entry_day':True})]:
        ck('round_trip_rejects_'+key,rejected(module.round_trip,*args,**kw))
    valid=module.round_trip(1005,100,10,'10.1')
    ck('exact_minimum_fee_budget_is_accepted',close(valid['terminal_wealth'],1005,'guard.exact_budget_terminal'))
    for key,B,T in [('zero_B',0,5),('negative_B',-1,5),('unknown_B',None,5),('zero_T',2000,0),('negative_T',2000,-1),('fractional_T',2000,1.5),('boolean_T',2000,True)]:
        ck('cash_path_rejects_'+key,rejected(module.cash_path,B,T))
    base=dict(initial_wealth=Decimal(2000),terminal_day=5,terminal_basis='explicit_synthetic_filled_cash',terminal_wealth=Decimal(2090))
    for key,value in [('initial_wealth',Decimal(3000)),('terminal_day',6),('terminal_basis','mark_to_market_NAV')]:
        bad=dict(base,**{key:value});ck('compare_rejects_mismatch_'+key,rejected(module.compare,base,bad))
    for key,value in [('initial_wealth',Decimal(0)),('initial_wealth',Decimal(-1)),('terminal_wealth',Decimal('NaN')),('terminal_wealth',Decimal('Infinity')),('terminal_day',0),('terminal_day',True),('terminal_basis','')]:
        a=dict(base,**{key:value});b=dict(a)
        ck('compare_rejects_invalid_shared_'+key+'_'+str(value),rejected(module.compare,a,b))
    ck('matching_cash_and_position_policies_allow_cash_wealth_comparison',module.compare(module.round_trip(2000,100,10,11),module.cash_path())==Decimal(-90))
    ck('latest_confirmation_policy_boundary_four_fails_three_passes',not module.can_complete_by_T(4,5) and module.can_complete_by_T(3,5))
    report=(OUT/'预测问题与标签适用性审查_v1.md').read_text();dictionary=read(OUT/'预测事件字典_v1.json');contract=read(OUT/'审查范围与设计合同.json');status=read(OUT/'状态与资格字典.json');confirm=read(OUT/'本次用户确认与待定参数.json');producer_qa=read(OUT/'合成案例核验.json')
    ck('report_all_nine_example_amount_rows_and_meaning',all(s in report for s in ['立即终值2040、等待2140','立即2090、等待2010','立即2190、持币2000','立即1790、持币2000','价格正0.5%，净亏5','期望−0.2%','终点净赚90，价格MAE−30%','共同d5终值8910、8100','终值10800会反转结论']))
    ck('producer_qa_corresponds_without_claiming_market_validity',producer_qa['all_checks_passed'] and producer_qa['passed']==producer_qa['total']==len(producer_qa['checks']) and all(r['passed'] for r in producer_qa['checks']) and f"{producer_qa['total']}项算术/边界检查通过只证明示例一致" in report)
    ck('user_priority_only_confirmed_horizon_and_policy_pending',confirm['user_original_answer']=='收盘后判断回落时该买入还是继续等待' and contract['user_confirmed']['first_use_case']==confirm['user_original_answer'] and all(v is None for v in contract['pending_freeze'].values()) and contract['pending_freeze']==dictionary['pending_freeze'] and 'starting_comparison_state' not in contract['user_confirmed'])
    ck('twelve_event_ids_and_unchanged_old_label',[e['id'] for e in dictionary['events']]==[f'L{i:02}' for i in range(12)] and dictionary['events'][0]['formula']=='C[t+5]/O[t+1]-1' and dictionary['events'][0]['clock']=='observed_stock_bars')
    ck('wealth_and_delta_definitions_same_T_and_positive_wait_sign',contract['primary_comparison']['advantage_formula']=='Delta_W = W_wait(T) - W_now(T)' and contract['primary_comparison']['initial_wealth_equal'] and contract['primary_comparison']['common_terminal_time_required'] and contract['primary_comparison']['late_confirmation_cannot_extend_terminal_time'] and not contract['primary_comparison']['counterfactual_fills_identified_from_daily_prices'])
    ck('NAV_liabilities_and_receivable_no_double_counting_explicit',all(token in report for token in ['未付','负债','应收']) and '到账' in report and ('减' in contract['wealth_conventions']['terminal_NAV'] or '-' in contract['wealth_conventions']['terminal_NAV'] or '−' in contract['wealth_conventions']['terminal_NAV']))
    ck('five_orthogonal_status_axes_and_NULL_unknowns',set(status['independent_axes'])=={'data','policy','execution','maturity','terminal'} and status['missing_or_unfilled_trade_return'] is None and status['unknown_is_not_zero'] and 'FILL_UNKNOWN' in status['independent_axes']['execution'] and 'NOT_MATURE' in status['independent_axes']['maturity'])
    ck('no_new_real_targets_fits_or_forecast_or_permission',not any(contract['guardrails'][k] for k in ['new_real_target_labels','new_models_or_real_probability_scores','outcomes_2025_2026_opened','old_forecast_draft_modified','confirmed_risk_settings_modified','formal_input_approved','runtime_usable','current_forecast_generated']) and contract['guardrails']['cumulative_research_variants_unchanged']==16 and dictionary['new_real_labels_generated'] is False and status['runtime_usable'] is False)
    ck('old_design_sources_unchanged',old_before=={rel:sha(ROOT/rel) for rel in OLD})
    after={rel:sha(ROOT/rel) for rel in checked}
    ck('all_reviewed_delivery_hashes_unchanged_during_audit',checked==after)
    result=dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,audit_method='Independent exact Fraction reconstruction from fictional-case inputs and explicit fixture assumptions; producer functions imported only for adversarial guard tests',synthetic_cases_independently_reviewed=21,numeric_cells_compared=len(numeric_comparisons),numeric_comparisons=numeric_comparisons,rounding_tolerance_fraction=str(F(1,10**26)),rounding_tolerance_not_event_threshold=True,delivery_sha256=checked,old_source_sha256=old_before,new_real_targets_generated=False,actual_result_tables_read=False,new_models_fitted=0,new_market_scores_calculated=0,outcomes_2025_2026_opened=False,independent_execution_evidence_or_probability_validity_claim=False,advisories=['S21 uses fictional whole-unit full-cash allocation: now 990 units, value 8910. Earlier design illustration used 100-unit lot rounding, now 900 units plus 900 residual cash, value 9000. Both are arithmetically valid under different explicit allocation assumptions; never mix them.','Teaching helpers demonstrate money and shared-endpoint guardrails; they are not a complete broker order, accounting, dividend or production execution engine.','All producer synthetic cases explicitly assume their stated fills; no fill was inferred from real prices.'])
    (WORK/'交付独立复核.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    doc=f'''# 数学与合成案例交付独立复核

2026-11-01。{len(checks)}/{len(checks)}项通过。以Fraction从虚构输入独立重建21例，核对{len(numeric_comparisons)}个数字单元；未调用生产算式生成期望值。只在输入拒绝、共同资金/终点/口径等负例中调用生产辅助函数，不执行其main。没有读取真实结果表、生成真实标签、拟合或评分，也未打开2025/2026目标。

终值、交易投入收益率、等待相对差额、低点风险和概率补数对应。有限十进制输出对循环有理数的比较容差为1e-26，仅用于打印精度核对，不改变零或方向阈值。微涨费后亏、70%正收益频率但负期望、NAV与未成交清算、缺失与零、晚入场不能当日清算、计划日历与实际股票观察日分别保留。

S21采用虚构单位1全现金：9900/10=990单位，共同d5为8910；等待900单位于11买入，共同d5为8100，差−810。若错误延到d7价格12，等待终值10800造成假优势。早期数学设计中的9000来自单位100、900单位及900剩余现金，是另一已明确分配假设；不能与本例混用。

输入负例覆盖非有限/未知金额、非正初始资金、非整数或无效数量/日期、费用超预算、同日退出、现金路径非法参数；共同比较拒绝不同B、T、NAV/现金口径、非有限终值和无效共享字段。已知未成交的现金财富仍可比较，交易收益保持NULL。结果是示例和定义对应证据，不是生产执行或市场预测有效性认证。

12个事件定义、5个独立状态轴及全部待冻结null字段与主报告一致。用户只确认首版优先问题，H、确认、等待上限、费用和仓位未被默填；初始空仓现金为研究设计假设，非用户账户状态核验。NAV已明确扣未付费用/负债且到账股息不再重复计应收。

原设计来源及被审交付前后SHA一致，完整指纹和逐项核验见交付独立复核.json。完成后停止项目写入，供根任务冻结归档。
'''
    (WORK/'交付独立复核.md').write_text(doc)
    print(json.dumps(dict(all_checks_passed=True,checks=len(checks),cases=21,numeric_cells=len(numeric_comparisons)),ensure_ascii=False))

if __name__=='__main__':main()
