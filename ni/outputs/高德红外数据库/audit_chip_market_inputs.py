"""Read-only unit/coherence diagnostics for future chip inputs, never signal analysis."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from scope_config import read_scope

ROOT=Path(__file__).resolve().parent


def num(value):return Decimal(str(value))


def main():
    c=sqlite3.connect((ROOT/'高德红外_2023起.sqlite').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    scope=read_scope(c)
    expected_days=c.execute('SELECT COUNT(*) FROM trading_calendar WHERE is_scheduled_open=1').fetchone()[0]
    bars=list(c.execute("SELECT * FROM current_daily_bars WHERE source='em_daily_0' ORDER BY trade_date"))
    by_date={r['trade_date']:r for r in bars}
    daily=[]
    for r in bars:
        shares=num(r['volume'])*100
        avg=num(r['amount'])/shares if shares>0 and r['amount'] is not None else None
        within=avg is not None and num(r['low'])<=avg<=num(r['high'])
        display_compatible=avg is not None and num(r['low'])-Decimal('0.005')<=avg<=num(r['high'])+Decimal('0.005')
        wrong_share_avg=num(r['amount'])/num(r['volume']) if num(r['volume'])>0 else None
        wrong_unit_detected=wrong_share_avg is not None and not num(r['low'])<=wrong_share_avg<=num(r['high'])
        daily.append(dict(trade_date=r['trade_date'],snapshot_id=r['snapshot_id'],
            source_volume_hands=str(num(r['volume'])),source_amount_cny=str(num(r['amount'])),
            implied_average_for_unit_check=str(avg) if avg is not None else None,
            unadjusted_low=str(num(r['low'])),unadjusted_high=str(num(r['high'])),
            strict_range_consistent=within,within_half_cent_display_sensitivity=display_compatible,
            precision_difference_cause='unverified' if not within else None,
            wrong_share_multiplier_1_detected=wrong_unit_detected))
    adjustment_comparisons={}
    for source in ('em_daily_1','em_daily_2'):
        adjusted=list(c.execute('SELECT * FROM current_daily_bars WHERE source=?',(source,)))
        mismatch=[];wrong_price_comparison=[]
        for r in adjusted:
            unadj=by_date[r['trade_date']]
            if any(r[k]!=unadj[k] for k in ('volume','amount','turnover')):mismatch.append(r['trade_date'])
            avg=num(unadj['amount'])/(num(unadj['volume'])*100)
            if not num(r['low'])<=avg<=num(r['high']):wrong_price_comparison.append(r['trade_date'])
        adjustment_comparisons[source]=dict(rows=len(adjusted),quantity_amount_turnover_mismatch_dates=mismatch,
            raw_average_outside_adjusted_price_range_dates=wrong_price_comparison,
            interpretation='Adjusted price ranges cannot be assumed to share raw monetary trade units; this is not a supplier-price-error flag')
    capital_checks=[];closed_dates=[]
    for row in c.execute("SELECT payload_json FROM supplemental_disclosure_observations WHERE kind='capital_period'"):
        r=json.loads(row[0]);d=r['period_end']
        if d not in by_date:
            closed_dates.append(d);continue
        bar=by_date[d]
        expected=num(bar['volume'])*Decimal('10000')/num(r['unlimited_shares'])
        reported=num(bar['turnover']);delta=expected-reported
        capital_checks.append(dict(period_end=d,capital_observation_id=r['observation_id'],
            raw_bar_snapshot_id=bar['snapshot_id'],reported_turnover_percentage_points=str(reported),
            period_unlimited_shares=r['unlimited_shares'],turnover_if_period_unlimited_denominator=str(expected),
            rounding_tolerance_percentage_points='0.005',within_display_rounding_tolerance=abs(delta)<=Decimal('0.005'),
            interpretation='Same-date diagnostic only; does not certify provider denominator, daily float-share history or historical availability',
            historical_input_eligible=False))
    checks=dict(stock_dates_match_validated_calendar=len(bars)==expected_days,
        hand100_and_cny_implied_average_in_raw_range=all(r['strict_range_consistent'] for r in daily),
        half_cent_display_sensitivity_compatible=all(r['within_half_cent_display_sensitivity'] for r in daily),
        wrong_share_unit_detected_on_all_dates=all(r['wrong_share_multiplier_1_detected'] for r in daily),
        adjusted_bars_keep_raw_quantity_amount_turnover=all(not r['quantity_amount_turnover_mismatch_dates'] for r in adjustment_comparisons.values()),
        capital_same_date_examples_consistent=bool(capital_checks) and all(r['within_display_rounding_tolerance'] for r in capital_checks))
    report=dict(audit_version='chip-market-input-audit-v1',checked_at=datetime.now(timezone.utc).isoformat(),
        source_snapshot_ids=sorted({r['snapshot_id'] for r in bars}),requested_cutoff=scope['end'],
        checks=checks,failed_checks=[k for k,v in checks.items() if not v],daily_unit_diagnostics=daily,
        adjustment_diagnostics=adjustment_comparisons,capital_same_date_diagnostics=capital_checks,
        capital_periods_without_same_date_stock_bar=sorted(closed_dates),
        assumptions=['Volume multiplier 100 shares per provider hand; monetary amount tested as CNY',
                     'Turnover display tested as rounding to 0.01 percentage points; rounding algorithm not separately certified',
                     '0.005 CNY sensitivity is half a displayed cent, not a rule that resolves or erases strict range exceptions'],
        limitations=['Coherence checks are not independent official volume/amount verification or proof of tick-level execution',
            'No forward/backward fill of report capital; no synthetic daily float created',
            'No chip data, indicators, trading pattern, return or signal calculated'],
        input_vintage_historical_certified=False)
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    (ROOT/'筹码基础行情口径核对.json').write_text(encoded,encoding='utf-8')
    print(json.dumps(dict(checks=checks,capital_same_dates=len(capital_checks),
        raw_range_failures=sum(not r['strict_range_consistent'] for r in daily),
        adjusted_raw_average_range_counts={k:len(v['raw_average_outside_adjusted_price_range_dates']) for k,v in adjustment_comparisons.items()},
        report_sha256=hashlib.sha256(encoded.encode()).hexdigest()),ensure_ascii=False,indent=2))
    c.close()


if __name__=='__main__':main()
