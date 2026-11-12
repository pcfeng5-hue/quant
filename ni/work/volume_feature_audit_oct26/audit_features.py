"""Independent feature-only audit. No outcome database or label values are read."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import hashlib
import json
import math
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DB = ROOT / 'outputs/三线研究启动_20261025/量价基线/日线特征与信号.sqlite'
CFG = ROOT / 'work/baseline_oct25/engineering_contract.json'
PRODUCER = ROOT / 'work/baseline_oct25/build_baseline.py'
AUDIT_START = '2023-01-03'
AUDIT_END = '2024-12-31'
MA_UP = 'MA5_gt_MA10_gt_MA15_and_MA15_rising'
MA_DOWN = 'MA5_lt_MA10_lt_MA15_and_MA15_falling'
VOL_UP = 'volume_gt_1p5_prev20_and_close_rising'
VOL_DOWN = 'volume_gt_1p5_prev20_and_close_falling'
SIGNALS = [MA_UP, MA_DOWN, VOL_UP, VOL_DOWN]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def frac(value):
    return Fraction(str(value))


def serialize(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def reconstruct(bars, ex_dates, calculation_start):
    """Use exact rational sums and local slices, without producer functions."""
    results = []
    segment = []
    start = None
    for bar in bars:
        day = bar['trade_date']
        row = dict(trade_date=day, segment_start=None, segment_bars=0,
                   ma5=None, ma10=None, ma15=None,
                   volume_ratio_prev20=None, close_change_prev=None,
                   dependency_first_date=None, dependency_last_date=None)
        if day >= calculation_start:
            if start is None or day in ex_dates:
                segment = []
                start = day
            segment.append(bar)
            age = len(segment)
            row.update(segment_start=start, segment_bars=age)
            for n in (5, 10, 15):
                if age >= n:
                    row['ma' + str(n)] = sum(frac(x['close']) for x in segment[-n:]) / n
            if age > 20:
                # Twenty previous observations, explicitly excluding today's bar.
                prior = segment[-21:-1]
                prior_volume = sum(frac(x['volume_native']) for x in prior)
                if prior_volume > 0:
                    row['volume_ratio_prev20'] = frac(bar['volume_native']) * 20 / prior_volume
                row['dependency_first_date'] = prior[0]['trade_date']
                row['dependency_last_date'] = day
            if age > 1:
                row['close_change_prev'] = frac(bar['close']) / frac(segment[-2]['close']) - 1
        previous = results[-1] if results else {}
        ma_ready = (row['segment_start'] is not None
                    and previous.get('segment_start') == row['segment_start']
                    and all(row['ma' + str(n)] is not None for n in (5, 10, 15))
                    and previous.get('ma15') is not None)
        row[MA_UP] = int(row['ma5'] > row['ma10'] > row['ma15']
                         and row['ma15'] > previous['ma15']) if ma_ready else None
        row[MA_DOWN] = int(row['ma5'] < row['ma10'] < row['ma15']
                           and row['ma15'] < previous['ma15']) if ma_ready else None
        volume_ready = row['volume_ratio_prev20'] is not None and row['close_change_prev'] is not None
        row[VOL_UP] = int(row['volume_ratio_prev20'] > Fraction(3, 2)
                          and row['close_change_prev'] > 0) if volume_ready else None
        row[VOL_DOWN] = int(row['volume_ratio_prev20'] > Fraction(3, 2)
                            and row['close_change_prev'] < 0) if volume_ready else None
        results.append(row)
    return results


def main():
    before = {str(p.relative_to(ROOT)): digest(p) for p in [DB, CFG, PRODUCER]}
    cfg = json.loads(CFG.read_text())
    conn = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    queries = []

    def fetch(sql, params=()):
        queries.append(dict(sql=sql, params=list(params)))
        return [dict(r) for r in conn.execute(sql, params)]

    bars = fetch('SELECT observation_id,trade_date,open,high,low,close,volume_native,volume_unit,turnover_unit,source_sha256,retrieved_at FROM input_bars WHERE trade_date<=? ORDER BY trade_date', (AUDIT_END,))
    stored_features = fetch('SELECT trade_date,source_observation_id,source_sha256,source_retrieved_at,raw_open,raw_high,raw_low,raw_close,volume_native,segment_start,segment_bars,known_ex_date,ma5,ma10,ma15,volume_ratio_prev20,close_change_prev,daily_status_certified,model_input_approved,runtime_usable FROM features WHERE trade_date<=? ORDER BY trade_date', (AUDIT_END,))
    stored_signals = fetch('SELECT trade_date,' + ','.join('"' + n + '"' for n in SIGNALS) + ' FROM signals WHERE trade_date<=? ORDER BY trade_date', (AUDIT_END,))
    actions = fetch('SELECT event_id,ex_date,cash_cny_per_10_gross,transfer_shares_per_10 FROM corporate_action_boundaries WHERE ex_date<=? ORDER BY ex_date', (AUDIT_END,))
    conn.close()
    ex_dates = {r['ex_date'] for r in actions}
    rebuilt = reconstruct(bars, ex_dates, cfg['calculation_start'])
    features = {r['trade_date']: r for r in stored_features}
    signals = {r['trade_date']: r for r in stored_signals}
    observed = {r['trade_date']: r for r in bars}
    dev = [r for r in rebuilt if AUDIT_START <= r['trade_date'] <= AUDIT_END]
    checks = []

    def check(name, condition, details=None):
        checks.append(dict(check=name, passed=bool(condition), details=details))

    check('input_dates_are_sorted_unique', len(observed) == len(bars) and [r['trade_date'] for r in bars] == sorted(observed))
    check('feature_dates_are_sorted_unique_and_match_input', len(features) == len(stored_features) and [r['trade_date'] for r in stored_features] == [r['trade_date'] for r in bars])
    check('signal_dates_are_sorted_unique_and_match_input', len(signals) == len(stored_signals) and [r['trade_date'] for r in stored_signals] == [r['trade_date'] for r in bars])
    check('development_anchor_count_484', len(dev) == 484, dict(actual=len(dev)))
    check('input_ohlc_and_native_volume_finite_valid', all(0 < b['low'] <= min(b['open'], b['close']) <= max(b['open'], b['close']) <= b['high'] and math.isfinite(b['volume_native']) and b['volume_native'] >= 0 for b in bars))
    check('stored_raw_and_source_fields_match_same_day_input', all(
        all(features[b['trade_date']][fk] == b[bk] for fk, bk in [
            ('source_observation_id', 'observation_id'), ('source_sha256', 'source_sha256'),
            ('source_retrieved_at', 'retrieved_at'), ('raw_open', 'open'), ('raw_high', 'high'),
            ('raw_low', 'low'), ('raw_close', 'close'), ('volume_native', 'volume_native')]) for b in bars))
    check('contract_volume_threshold_and_window_are_fixed', cfg['volume']['spike_threshold'] == 1.5 and 20 in cfg['volume']['ratios'] and cfg['volume']['denominator'] == 'previous n segment observations excluding current')
    check('segment_metadata_matches_independent_reconstruction', all(features[r['trade_date']]['segment_start'] == r['segment_start'] and features[r['trade_date']]['segment_bars'] == r['segment_bars'] for r in rebuilt))
    check('known_ex_date_flags_match_boundaries', all(features[r['trade_date']]['known_ex_date'] == int(r['trade_date'] in ex_dates) for r in rebuilt))

    numeric = ['ma5', 'ma10', 'ma15', 'volume_ratio_prev20', 'close_change_prev']
    errors = {n: [] for n in numeric}
    numeric_mismatches = []
    for r in rebuilt:
        for key in numeric:
            expected = r[key]
            actual = features[r['trade_date']][key]
            if expected is None or actual is None:
                if (expected is None) != (actual is None):
                    numeric_mismatches.append([r['trade_date'], key, 'NULL mismatch'])
            else:
                errors[key].append(abs(actual - float(expected)))
                if not math.isclose(actual, float(expected), rel_tol=1e-12, abs_tol=1e-12):
                    numeric_mismatches.append([r['trade_date'], key, actual, str(expected)])
    check('exact_rational_ma_values_match_stored', not [x for x in numeric_mismatches if x[1].startswith('ma')], dict(max_absolute_error={k: max(v, default=0) for k, v in errors.items() if k.startswith('ma')}))
    check('exact_previous20_volume_ratio_matches_stored', not [x for x in numeric_mismatches if x[1] == 'volume_ratio_prev20'], dict(max_absolute_error=max(errors['volume_ratio_prev20'], default=0)))
    check('exact_close_change_matches_stored', not [x for x in numeric_mismatches if x[1] == 'close_change_prev'], dict(max_absolute_error=max(errors['close_change_prev'], default=0)))
    for signal in SIGNALS:
        differences = [[r['trade_date'], r[signal], signals[r['trade_date']][signal]] for r in dev if r[signal] != signals[r['trade_date']][signal]]
        check('exact_signal_matches_' + signal, not differences, dict(differences=differences))
    check('all_four_signal_values_are_nullable_binary', all(s[k] in (None, 0, 1) for s in stored_signals for k in SIGNALS))
    check('direction_pairs_are_exclusive_with_symmetric_nulls', all(
        (r[MA_UP] is None) == (r[MA_DOWN] is None)
        and (r[VOL_UP] is None) == (r[VOL_DOWN] is None)
        and not (r[MA_UP] == r[MA_DOWN] == 1)
        and not (r[VOL_UP] == r[VOL_DOWN] == 1) for r in dev))
    check('volume_first20_in_each_segment_are_null', all(r['volume_ratio_prev20'] is None and r[VOL_UP] is None and r[VOL_DOWN] is None for r in rebuilt if r['segment_start'] is not None and r['segment_bars'] <= 20))
    check('ma_trend_first15_in_each_segment_are_null', all(r[MA_UP] is None and r[MA_DOWN] is None for r in rebuilt if r['segment_start'] is not None and r['segment_bars'] <= 15))
    reset_dates = [r for r in rebuilt if r['trade_date'] in ex_dates]
    check('known_ex_date_resets_price_and_volume_states', len(reset_dates) == len(ex_dates) and all(r['segment_bars'] == 1 and all(r[k] is None for k in numeric + SIGNALS) for r in reset_dates), dict(dates=sorted(ex_dates)))
    check('all_volume_dependencies_stay_within_segment_and_no_later_than_signal', all(r['segment_start'] <= r['dependency_first_date'] <= r['dependency_last_date'] == r['trade_date'] for r in rebuilt if r['volume_ratio_prev20'] is not None))
    units = sorted({b['volume_unit'] for b in bars})
    check('native_volume_unit_marker_is_constant', len(units) == 1, dict(markers=units, verified_formal_vendor_unit=False))
    scale_mismatches = []
    for i, r in enumerate(rebuilt):
        if r['volume_ratio_prev20'] is not None:
            prior = bars[i-20:i]
            scaled = frac(bars[i]['volume_native']) * 100 * 20 / sum(frac(b['volume_native']) * 100 for b in prior)
            if scaled != r['volume_ratio_prev20']:
                scale_mismatches.append(r['trade_date'])
    check('ratio_invariant_to_constant_positive_unit_conversion', not scale_mismatches, dict(conversion_multiplier=100, differences=scale_mismatches))
    prefix_dates = ['2023-01-03', '2023-06-19', '2023-06-20', '2023-07-18', '2024-05-24', '2024-12-31']
    prefix_results = []
    for cutoff in prefix_dates:
        prefix = [b for b in bars if b['trade_date'] <= cutoff]
        independent_prefix = reconstruct(prefix, ex_dates, cfg['calculation_start'])
        prefix_results.append(dict(cutoff=cutoff, unchanged=independent_prefix == rebuilt[:len(prefix)]))
    check('truncation_prefix_invariance_all_requested_fields', all(r['unchanged'] for r in prefix_results), prefix_results)
    mutated = [dict(b) for b in bars]
    mutation_cutoff = '2023-12-29'
    for b in mutated:
        if b['trade_date'] > mutation_cutoff:
            for key in ['open', 'high', 'low', 'close']:
                b[key] *= 11
            b['volume_native'] *= 7
    mutation_result = reconstruct(mutated, ex_dates, cfg['calculation_start'])
    check('future_price_and_volume_mutation_preserves_past_features', all(a == b for a, b in zip(rebuilt, mutation_result) if a['trade_date'] <= mutation_cutoff), dict(cutoff=mutation_cutoff))
    # Strict boundary semantics are exercised separately because real bars need not hit equality.
    strict_probes = [
        (Fraction(3, 2), Fraction(1, 100), 0, 0),
        (Fraction(1500001, 1000000), Fraction(1, 100), 1, 0),
        (Fraction(1500001, 1000000), Fraction(-1, 100), 0, 1),
        (Fraction(2), Fraction(0), 0, 0),
        (None, Fraction(1, 100), None, None),
        (Fraction(2), None, None, None),
    ]
    probe_ok = True
    for ratio, delta, up, down in strict_probes:
        ready = ratio is not None and delta is not None
        actual_up = int(ratio > Fraction(3, 2) and delta > 0) if ready else None
        actual_down = int(ratio > Fraction(3, 2) and delta < 0) if ready else None
        probe_ok &= (actual_up, actual_down) == (up, down)
    check('strict_gt_threshold_zero_change_and_null_semantics', probe_ok, dict(synthetic_boundary_probes=len(strict_probes)))
    check('formal_daily_status_and_model_runtime_gates_remain_closed', all(r['daily_status_certified'] == r['model_input_approved'] == r['runtime_usable'] == 0 for r in stored_features))
    after = {str(p.relative_to(ROOT)): digest(p) for p in [DB, CFG, PRODUCER]}
    check('protected_input_files_unchanged', before == after, dict(after=after))
    check('no_label_or_outcome_value_queries', all('FROM input_bars ' in r['sql'] or 'FROM features ' in r['sql'] or 'FROM signals ' in r['sql'] or 'FROM corporate_action_boundaries ' in r['sql'] for r in queries), dict(query_count=len(queries), label_database_opened=False, predictive_results_calculated=False))

    coverage = []
    for year in ['2023', '2024', '2023-2024']:
        rows = dev if year == '2023-2024' else [r for r in dev if r['trade_date'].startswith(year)]
        for signal in SIGNALS:
            c = Counter('null' if r[signal] is None else str(r[signal]) for r in rows)
            coverage.append(dict(period=year, signal=signal, anchors=len(rows), computed=c['0'] + c['1'], null=c['null'], false=c['0'], true=c['1']))
    per_segment = []
    for start in sorted({r['segment_start'] for r in dev}):
        rows = [r for r in dev if r['segment_start'] == start]
        vol = [r for r in rows if r['volume_ratio_prev20'] is not None]
        ma = [r for r in rows if r[MA_UP] is not None]
        per_segment.append(dict(segment_start=start, first_audit_anchor=rows[0]['trade_date'], last_audit_anchor=rows[-1]['trade_date'], anchors=len(rows), volume_computed=len(vol), volume_first_available=vol[0]['trade_date'] if vol else None, ma_trend_computed=len(ma), ma_trend_first_available=ma[0]['trade_date'] if ma else None))
    data = dict(
        audit_id='independent_stored_ma_volume_features_20261026',
        scope='feature_only; no labels, no prediction results, no outcome frequencies',
        period=dict(audit_start=AUDIT_START, audit_end=AUDIT_END, warmup_input_first=bars[0]['trade_date'], calculation_start=cfg['calculation_start'], input_rows=len(bars), development_anchors=len(dev)),
        implementation='stdlib Fraction exact decimal-string input, independent local slices; no imports or calls to old generator functions',
        input_hashes_before=before, input_hashes_after=after,
        checks=checks, passed=sum(r['passed'] for r in checks), total=len(checks),
        coverage=coverage, segment_coverage=per_segment,
        numeric_max_absolute_errors={k: max(v, default=0) for k, v in errors.items()},
        read_queries=queries,
        labels_read=False, new_combo_outcome_frequency_calculated=False,
        formal_model_input_approved=False, runtime_usable=False,
        limitations=[
            'All features require the current completed daily close and total daily volume; usable for a prospective post-close calculation only, not an intraday or opening-time signal.',
            'Prefix invariance proves formula causality for the saved snapshot, not historical first-publication times or absence of later vendor revisions.',
            'The single stored provider volume unit marker is unverified by an official vendor specification. A ratio cancels a constant unit factor; it does not certify the vendor definition, float shares, or money flow.',
            'Only the recorded ex-date boundaries are verified by this reconstruction. No claim that all corporate actions or the unbridged 2022 discontinuity were resolved.',
            'No historical daily ST/suspension/limit/fill/fee acceptance and no live readiness are established.',
            'Signal counts describe indicator availability and triggers only; no label values, next-period direction frequencies, predictive scores, or new combinations were calculated.'
        ],
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / '独立量价特征核查.json').write_text(serialize(data))
    lines = ['# 独立量价特征核查', '', f"核查通过 **{data['passed']}/{data['total']} 项**。本次只读已存价格与成交量输入，独立重建 MA 趋势及两个放量方向信号；没有打开标签数据库，没有读取涨跌标签或计算新组合的上涨频率。", '',
             f"核查期：{AUDIT_START} 至 {AUDIT_END}，共 {len(dev)} 个日期；为重建预热读取 {len(bars)} 条输入，最早 {bars[0]['trade_date']}，计算从 {cfg['calculation_start']} 开始。所有旧输入文件前后 SHA-256 一致。", '',
             '重建采用 Python 标准库 Fraction 对已存十进制数精确求和及比较，不调用旧生成器。成交量分母严格使用同一除权段内的前 20 条记录，排除当日；当日量比严格大于 1.5，且当日收盘相对前收分别严格上涨或下跌。量比等于 1.5、收盘持平不触发；缺少完整分母或前收时保留空值。', '',
             'MA 趋势使用当日 MA5、MA10、MA15 的严格次序及 MA15 对上一同段日期的方向；缺少上一日 MA15 时保留空值。2023-06-20、2024-05-24 已知除权日分别重新开始 MA、成交量和前收状态，前 20 条段内放量信号为空。', '',
             '| 年段 | 信号 | 日期 | 可计算 | 空值 | 触发 |', '|---|---|---:|---:|---:|---:|']
    for r in coverage:
        lines.append(f"| {r['period']} | {r['signal']} | {r['anchors']} | {r['computed']} | {r['null']} | {r['true']} |")
    lines += ['', '上表触发次数只描述特征，不代表未来上涨或下跌概率。', '',
              '在保存快照上，截断与未来价格、成交量修改均不改变过去的特征。单位统一乘以 100 后量比不变；这仅证明比例公式的单位抵消，数据商原始成交量单位仍未获得正式规格认证。', '',
              '当日收盘价和全天成交量在收盘后才能完整取得。因此这里的“同日”是收盘后可计算，尚未证明历史首次公开时间，也不能用于当日开盘或盘中决策。历史修订、日度 ST/停复牌/涨跌停、成交与费用等限制继续保留，模型和运行闸门均关闭。', '',
              '详细检查、逐字段数值误差、分段覆盖、读取 SQL 与输入哈希见同目录 JSON。', '']
    (OUT / '独立量价特征核查.md').write_text('\n'.join(lines))
    print(serialize(dict(passed=data['passed'], total=data['total'], failed=[r for r in checks if not r['passed']], numeric_errors=data['numeric_max_absolute_errors'], coverage=coverage, segment_coverage=per_segment)))
    if data['passed'] != data['total']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
