"""Deterministic teaching cases, not market labels, forecasts or a backtester.

Every amount, probability and path is invented. This module cannot open a market
database, obtain quotes or submit orders. Example q=100 and B=2000 are arithmetic
inputs only, never portfolio/fee recommendations or a pilot configuration.
"""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

D=Decimal
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/预测问题与标签适用性审查_20261101'

def money(x):
    try:v=D(str(x))
    except (InvalidOperation,ValueError,TypeError) as exc:raise ValueError('Invalid example money') from exc
    if not v.is_finite():raise ValueError('Nonfinite example input')
    return v

def round_trip(B,q,entry,exit,buy_fee='5',sell_fee='5',entry_day=1,exit_day=5):
    B,q,entry,exit,buy_fee,sell_fee=map(money,[B,q,entry,exit,buy_fee,sell_fee])
    if B<=0 or q<=0 or q!=q.to_integral_value() or min(entry,exit)<=0 or min(buy_fee,sell_fee)<0:raise ValueError('Invalid synthetic quantity/price/fee')
    if type(entry_day) is not int or type(exit_day) is not int or entry_day<1 or exit_day<=entry_day:raise ValueError('Example ordinary-stock sale must follow entry session')
    remaining=B-q*entry-buy_fee
    if remaining<0:raise ValueError('Insufficient starting example cash')
    W=remaining+q*exit-sell_fee
    return dict(initial_wealth=B,terminal_day=exit_day,terminal_basis='explicit_synthetic_filled_cash',terminal_wealth=W,net_change=W-B,raw_price_change=exit/entry-1,filled_quantity=q,trade_return=(W-B)/(q*entry+buy_fee))

def compare(a,b):
    A,B=money(a['initial_wealth']),money(b['initial_wealth'])
    if min(A,B)<=0 or A!=B:raise ValueError('Unmatched or invalid initial wealth')
    for row in [a,b]:
        if type(row['terminal_day']) is not int or row['terminal_day']<1:raise ValueError('Invalid terminal session')
        if type(row['terminal_basis']) is not str or not row['terminal_basis']:raise ValueError('Invalid terminal basis')
    for field in ['terminal_day','terminal_basis']:
        if a[field]!=b[field]:raise ValueError('Unmatched comparison '+field)
    return money(b['terminal_wealth'])-money(a['terminal_wealth'])

def cash_path(B=2000,T=5):
    B=money(B)
    if B<=0 or type(T) is not int or T<1:raise ValueError('Invalid cash-only example initial wealth or terminal session')
    return dict(initial_wealth=B,terminal_day=T,terminal_basis='explicit_synthetic_filled_cash',terminal_wealth=B,net_change=D(0),trade_return=None,execution_status='NO_POSITION_NO_TRANSACTION',cash_interest_assumed=0)

def earliest_entry(confirmation_day):return confirmation_day+1
def can_complete_by_T(confirmation_day,T):return earliest_entry(confirmation_day)+1<=T

def first_hit(path,lower=9,upper=11):
    for p in path:
        if p>=upper:return 'upper_first'
        if p<=lower:return 'lower_first'
    return 'none'

def main():
    cases=[];checks=[]
    def add(key,purpose,inputs,result):cases.append(dict(case_id=key,purpose=purpose,all_inputs_are_synthetic=True,not_a_market_forecast=True,inputs=inputs,result=result))
    def ck(name,ok):checks.append(dict(check=name,passed=bool(ok)));assert ok,name
    now=round_trip(2000,100,10,'10.5');wait=round_trip(2000,100,9,'10.5',entry_day=3)
    add('S01','等待较低价格入场，在共同终点更好，不是事后最低价规则',dict(now_entry=10,prespecified_wait_entry=9,common_exit='10.5',B=2000,q=100,buy_fee=5,sell_fee=5),dict(now=now,wait=wait,wait_minus_now=compare(now,wait)))
    ck('S01_exact_common_wealth_2040_2140_delta100',now['terminal_wealth']==2040 and wait['terminal_wealth']==2140 and compare(now,wait)==100)
    now=round_trip(2000,100,10,11);wait=round_trip(2000,100,'10.8',11,entry_day=3)
    add('S02','等待确认也可能买贵，不能预设等待一定改善',dict(common_exit=11,now_entry=10,wait_entry='10.8'),dict(now=now,wait=wait,wait_minus_now=compare(now,wait)))
    ck('S02_wait_costs_80',compare(now,wait)==-80)
    now=round_trip(2000,100,10,12);wait=cash_path()
    add('S03','未触发而错过上涨，现金路径仍要保留',dict(no_confirmation=True,now_entry=10,common_exit=12),dict(now=now,wait=wait,wait_minus_now=compare(now,wait)))
    ck('S03_cash_path_not_zero_return_trade',compare(now,wait)==-190 and wait['trade_return'] is None)
    now=round_trip(2000,100,10,8)
    add('S04','未触发时空仓避免损失，也必须保留同一比较分母',dict(no_confirmation=True,now_entry=10,common_exit=8),dict(now=now,wait=wait,wait_minus_now=compare(now,wait)))
    ck('S04_cash_preserves_210',compare(now,wait)==210)
    x=round_trip(2000,100,10,'10.05')
    add('S05','价格微涨并不等于费用后盈利',dict(entry=10,exit='10.05',q=100,each_side_synthetic_fee=5),x)
    ck('S05_price_positive_net_negative',x['raw_price_change']>0 and x['net_change']==-5)
    x=round_trip(2000,100,10,10)
    add('S06','价格零变动单列，费后仍会亏损',dict(entry=10,exit=10,each_side_synthetic_fee=5),x)
    ck('S06_zero_is_not_strict_price_fall',x['raw_price_change']==0 and x['net_change']==-10)
    expected=D('.7')*D('.01')+D('.3')*D('-.03')
    add('S07','高正收益频率可能伴随负期望',dict(hypothetical_up_probability='.7',up_return='.01',hypothetical_down_probability='.3',down_return='-.03',fees=0),dict(expected_return=expected))
    ck('S07_negative_expected_return_point002',expected==D('-.002'))
    x=round_trip(2000,100,10,11);mae=D(7)/10-1
    add('S08','终点上涨并不表示期间安全',dict(entry=10,post_entry_low=7,exit=11),dict(terminal=x,raw_price_MAE=mae,MAE_is_realized_loss=False))
    ck('S08_profitable_end_and_30pct_price_MAE',x['net_change']==90 and mae==D('-.3'))
    a=[10,12,8,11];b=[10,8,12,11]
    add('S09','相同日OHLC不能识别上下风险线先后或保证成交',dict(pathA=a,pathB=b,OHLC=[10,12,8,11],barriers=[9,11]),dict(pathA_first=first_hit(a),pathB_first=first_hit(b),OHLC_only_first_hit=None,fill_guaranteed=False))
    ck('S09_same_OHLC_opposite_first_hit',min(a)==min(b) and max(a)==max(b) and a[0]==b[0] and a[-1]==b[-1] and first_hit(a)!=first_hit(b))
    rejected=False
    try:round_trip(2000,100,10,11,entry_day=1,exit_day=1)
    except ValueError:rejected=True
    add('S10','新买普通股票不能在合成T+1约束下同日假设卖出',dict(entry_day=1,attempted_exit_day=1),dict(blocked=rejected,realized_trade_return=None,barrier_touch_is_not_sale=True))
    ck('S10_same_day_exit_rejected',rejected)
    status=dict(execution_status='KNOWN_UNFILLED',terminal_wealth=2000,trade_return=None,actual_trade_fee=0,cash_path_assumptions='known no fills, no order charges, no cash interest; not a general broker assertion')
    add('S11','已确认未成交可有现金财富，但不是零收益成交',dict(requested_quantity=100,filled_quantity=0),status)
    ck('S11_unfilled_trade_return_NULL',status['trade_return'] is None)
    x=round_trip(2000,40,10,11)
    add('S12','部分成交按实际40股和剩余现金计算，不按请求100股',dict(requested_quantity=100,filled_quantity=40),x)
    ck('S12_partial_fill_net30',x['net_change']==30 and x['filled_quantity']==40)
    add('S13','费用或成交未知不能填零',dict(raw_entry=10,raw_exit=11,fees=None,fill_status='UNKNOWN'),dict(raw_price_change='.1',net_profit_event=None,terminal_realized_cash=None))
    ck('S13_unidentified_result_kept_NULL',cases[-1]['result']['net_profit_event'] is None)
    add('S14','转增/拆分会改变价格而未必改变财富',dict(old_shares=100,old_price=10,synthetic_share_factor=2,new_price=5,fees_and_taxes=0),dict(raw_price_change=D(5)/10-1,wealth_before=100*10,wealth_after=200*5))
    ck('S14_mechanical_price_drop_not_wealth_loss',cases[-1]['result']['wealth_before']==cases[-1]['result']['wealth_after'])
    add('S15','上涨概率补数包含零，不等于严格下跌或卖出成功概率',dict(synthetic_positive_probability='.6',synthetic_zero_probability='.1'),dict(nonpositive_probability=D(1)-D('.6'),strict_negative_probability=D(1)-D('.6')-D('.1'),sell_better_than_hold_probability=None))
    ck('S15_complement_point4_is_not_point3',cases[-1]['result']['nonpositive_probability']==D('.4') and cases[-1]['result']['strict_negative_probability']==D('.3'))
    same_T=not can_complete_by_T(4,5)
    add('S16','晚确认不能把等待方案终点顺延；到T清算还须考虑可卖日',dict(confirmation_day=4,earliest_entry_day=5,common_T=5,example_minimum_sale_delay_sessions=1),dict(can_finish_cash_round_trip=not same_T,keep_cash_or_separate_NAV_protocol=True,extend_T=False))
    ck('S16_confirmation_day4_not_liquidatable_by_T5',same_T and can_complete_by_T(3,5))
    mismatch_rejected=0
    base=round_trip(2000,100,10,11)
    for bad in [dict(base,initial_wealth=D(3000)),dict(base,terminal_day=6),dict(base,terminal_basis='mark_to_market_NAV')]:
        try:compare(base,bad)
        except ValueError:mismatch_rejected+=1
    add('S17','不同资金、不同终点或现金/NAV口径不能直接配对',dict(mismatches=['initial_wealth','terminal_day','terminal_basis']),dict(rejected_count=mismatch_rejected))
    ck('S17_all_three_mismatches_rejected',mismatch_rejected==3)
    nav=D(2000)-100*10-5+100*11
    add('S18','终点有估值但卖不掉时，不得记录为已实现收益',dict(B=2000,q=100,entry=10,entry_fee=5,terminal_mark=11,sell_fill=False,unpaid_liabilities=0,rights_receivables=0),dict(terminal_NAV=nav,realized_sale_profit=None,liquidation_cash=None,hypothetical_filled_cash_if_later_verified=2090))
    ck('S18_NAV2095_not_realized_cash2090',nav==2095 and cases[-1]['result']['realized_sale_profit'] is None)
    add('S19','预测时点尚未公开的信息不能提前使用',dict(information_cutoff='d0 15:01 Asia/Shanghai',actual_available='d0 15:31 Asia/Shanghai'),dict(eligible_at_old_cutoff=False,new_prediction_requires_new_cutoff=True))
    ck('S19_later_information_excluded',not cases[-1]['result']['eligible_at_old_cutoff'])
    add('S20','未来真实停牌/缺失日不得悄悄把计划终点后移',dict(planned_sessions=['d1','d2','d3','d4','d5'],observed_stock_bars=['d1','d3','d4','d5','d6'],planned_T='d5'),dict(fifth_observed_bar='d6',same_horizon=False,terminal_missing_valuation_or_fill_requires_explicit_status=True))
    ck('S20_observed_and_planned_clock_distinct',cases[-1]['result']['fifth_observed_bar']!=cases[-1]['inputs']['planned_T'])
    early=round_trip(9900,990,10,9,buy_fee=0,sell_fee=0)
    ontime=round_trip(9900,900,11,9,buy_fee=0,sell_fee=0,entry_day=3)
    late=round_trip(9900,900,11,12,buy_fee=0,sell_fee=0,entry_day=3,exit_day=7)
    add('S21','把等待方案多给两天会反转结论，因此必须共同终点',dict(B=9900,synthetic_allocation_rule='whole-unit full cash, fee=0; not a lot or portfolio recommendation',now_entry_day1_price10=True,wait_entry_day3_price11=True,day5_price=9,day7_price=12),dict(now_at_common_day5=early['terminal_wealth'],wait_at_common_day5=ontime['terminal_wealth'],correct_wait_minus_now=compare(early,ontime),wrong_wait_at_day7=late['terminal_wealth'],wrong_cross_time_comparison_forbidden=True))
    ck('S21_common_T_keeps_wait_worse_and_wrong_later_endpoint_flips_ranking',early['terminal_wealth']==8910 and ontime['terminal_wealth']==8100 and late['terminal_wealth']==10800 and compare(early,ontime)==-810)
    bad_count=0
    for bad in [('NaN',100,10,11),(2000,100,0,11),(2000,'1.5',10,11),(100,100,10,11)]:
        try:round_trip(*bad)
        except ValueError:bad_count+=1
    ck('invalid_synthetic_money_quantity_price_and_budget_rejected',bad_count==4)
    ck('all_cases_explicitly_synthetic',len(cases)==21 and all(r['all_inputs_are_synthetic'] and r['not_a_market_forecast'] for r in cases))
    OUT.mkdir(parents=True,exist_ok=True)
    enc=lambda x:json.dumps(x,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n'
    (OUT/'合成案例与精确计算.json').write_text(enc(dict(all_examples_are_fictional=True,real_market_observations_used=0,cases=cases)))
    (OUT/'合成案例核验.json').write_text(enc(dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,synthetic_case_count=len(cases),new_real_market_targets=0,new_models=0)))
    print(enc(dict(cases=len(cases),checks=len(checks),real_market_observations_used=0)))

if __name__=='__main__':main()
