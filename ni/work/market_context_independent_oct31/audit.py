"""Independent Fraction oracle plus producer negative/synthetic probes.

Expected values and dependencies are built without importing the producer.
Only source market_daily/corporate_actions and the new engineering DB are read.
No outcomes, labels or restricted tables are queried.
"""
import csv
import hashlib
import importlib.util
import json
import math
import sqlite3
from collections import Counter, defaultdict
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
WORK = ROOT / 'work/market_context_oct31'
DELIVERY = ROOT / 'outputs/市场环境输入准备_20261031'
DATABASE = DELIVERY / '市场环境工程输入.sqlite'
SOURCE = ROOT / 'outputs/统一数据底座_20261022/统一数据底座.sqlite'
CODE, CONTRACT, RECEIPT = [WORK / n for n in ('build_context.py', 'contract.json', 'registration_receipt.json')]
INDEXES = ('000001.SH', '399001.SZ', '399967.SZ')
STOCK = '002414.SZ'
CALC_START = '2022-06-01'
LAGS = (1, 5, 20)
CHECKS = []


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(2 ** 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def check(name, ok, detail=None):
    CHECKS.append(dict(name=name, passed=bool(ok), detail=detail))


def ro(path):
    c = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    return c


def rows(c, table):
    return [dict(r) for r in c.execute('SELECT * FROM "' + table + '"')]


def exact(value):
    return Fraction(str(value))


def ref_build(source, ex_dates):
    """Hard-coded independent definitions, no production code/dispatch calls."""
    by = defaultdict(dict)
    for r in source:
        by[r['canonical_symbol'], r['provider']][r['trade_date']] = r
    dates = sorted(by[STOCK, 'eastmoney'])
    bad = {by[s, 'eastmoney'][d]['observation_id']
           for s in (STOCK, *INDEXES) for d in dates
           if exact(by[s, 'eastmoney'][d]['close']) != exact(by[s, 'tencent'][d]['close'])}
    raw_expect, segments = {}, []
    for s in INDEXES:
        available = [d for d in dates if d >= CALC_START]
        positions = {d: i for i, d in enumerate(available)}
        for d in dates:
            for lag in LAGS:
                fid = f'{s}:past_return_{lag}'
                if d < CALC_START:
                    raw_expect[d, fid] = (None, [], 'BEFORE_CALCULATION_START')
                elif positions[d] < lag:
                    raw_expect[d, fid] = (None, [], 'INSUFFICIENT_INDEX_HISTORY')
                else:
                    dep = [by[s, 'eastmoney'][available[positions[d] - lag]], by[s, 'eastmoney'][d]]
                    raw_expect[d, fid] = (exact(dep[1]['close']) / exact(dep[0]['close']) - 1, dep, None)
            fid = f'{s}:close_over_ma20_minus_one'
            if d < CALC_START:
                raw_expect[d, fid] = (None, [], 'BEFORE_CALCULATION_START')
            elif positions[d] < 19:
                raw_expect[d, fid] = (None, [], 'INSUFFICIENT_INDEX_HISTORY')
            else:
                dep = [by[s, 'eastmoney'][x] for x in available[positions[d] - 19:positions[d] + 1]]
                mean = sum((exact(x['close']) for x in dep), Fraction(0)) / 20
                raw_expect[d, fid] = (exact(dep[-1]['close']) / mean - 1, dep, None)
    aux = f'{STOCK}:past_return_5_aux'
    segment_days, segment_start = [], None
    for d in dates:
        if d < CALC_START:
            raw_expect[d, aux] = (None, [], 'BEFORE_CALCULATION_START')
            segments.append(dict(trade_date=d, segment_start=None, segment_bars=0))
            continue
        if not segment_days or d in ex_dates:
            segment_days, segment_start = [], d
        segment_days.append(d)
        segments.append(dict(trade_date=d, segment_start=segment_start, segment_bars=len(segment_days)))
        if len(segment_days) < 6:
            raw_expect[d, aux] = (None, [], 'INSUFFICIENT_SAME_SEGMENT_STOCK_HISTORY')
        else:
            dep = [by[STOCK, 'eastmoney'][segment_days[-6]], by[STOCK, 'eastmoney'][d]]
            raw_expect[d, aux] = (exact(dep[1]['close']) / exact(dep[0]['close']) - 1, dep, None)
    for s in INDEXES:
        for d in dates:
            a, b = raw_expect[d, aux], raw_expect[d, f'{s}:past_return_5']
            fid = f'{STOCK}:minus_{s}:past_return_5'
            if a[0] is None or b[0] is None:
                raw_expect[d, fid] = (None, [], 'BEFORE_CALCULATION_START' if d < CALC_START else 'COMPONENT_HISTORY_NOT_READY')
            else:
                raw_expect[d, fid] = (a[0] - b[0], a[1] + b[1], None)
    expected, expected_dep = {}, []
    for (d, fid), (value, dep, reason) in sorted(raw_expect.items()):
        dep = sorted({r['observation_id']: r for r in dep}.values(), key=lambda r: (r['trade_date'], r['canonical_symbol']))
        conflicts = sum(r['observation_id'] in bad for r in dep)
        ready = value is not None and reason is None and conflicts == 0
        role = 'auxiliary_calculation' if fid == aux else 'candidate_context_feature'
        expected[d, fid] = dict(signal_date=d, feature_id=fid, role=role,
            diagnostic_value=value, engineering_value=value if ready else None,
            engineering_ready=int(ready), status=reason or ('CLOSE_SOURCE_CONFLICT' if conflicts else 'ENGINEERING_READY_NOT_FORMAL_PIT'),
            dependency_n=len(dep), dependency_first_date=min((r['trade_date'] for r in dep), default=None),
            max_dependency_date=max((r['trade_date'] for r in dep), default=None), close_source_conflict_n=conflicts,
            historical_first_availability_certified=0, model_input_approved=0, runtime_usable=0)
        for j, r in enumerate(dep):
            expected_dep.append(dict(signal_date=d, feature_id=fid, dependency_order=j,
                dependency_symbol=r['canonical_symbol'], dependency_date=r['trade_date'],
                observation_id=r['observation_id'], source_close=r['close'], source_sha256=r['source_sha256'],
                source_close_conflict=int(r['observation_id'] in bad)))
    return expected, expected_dep, segments, bad, dates


def main():
    cfg, receipt = read(CONTRACT), read(RECEIPT)
    protected = [ROOT / p for p in receipt['protected_source_sha256']] + [CODE, CONTRACT, RECEIPT, DATABASE]
    before = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    check('receipt_matches_final_code_and_contract', sha(CODE) == receipt['producer_code_sha256'] and sha(CONTRACT) == receipt['contract_sha256'])
    check('all_registered_protected_sources_match', all(before[p] == h for p, h in receipt['protected_source_sha256'].items()))
    with ro(SOURCE) as c:
        source = [dict(r) for r in c.execute("SELECT observation_id,collection,canonical_symbol,provider,adjustment,trade_date,close,price_unit,source_sha256,source_request_id,retrieved_at,input_path,input_row_index FROM market_daily WHERE collection='market_industry_oct21' AND adjustment='0' AND provider IN ('eastmoney','tencent') AND canonical_symbol IN ('000001.SH','399001.SZ','399967.SZ','002414.SZ') ORDER BY provider,canonical_symbol,trade_date")]
        actions = [dict(r) for r in c.execute("SELECT event_id,symbol,ex_date FROM corporate_actions WHERE symbol='002414.SZ' ORDER BY ex_date")]
    ex_dates = {r['ex_date'] for r in actions}
    check('frozen_known_stock_boundary_set', ex_dates == {'2023-06-20', '2024-05-24', '2026-09-22'})
    expected, expected_dep, segments, bad, dates = ref_build(source, ex_dates)
    with ro(DATABASE) as c:
        actual = {n: rows(c, n) for n in ('input_closes', 'feature_catalog', 'features', 'feature_dependencies', 'stock_segments',
                                         'wide_engineering_values', 'coverage', 'close_source_conflicts', 'metadata')}
        schema = {r['name']: r['sql'] for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        view_names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        approved_n = c.execute('SELECT count(*) FROM approved_market_context_inputs').fetchone()[0]
        quick = c.execute('PRAGMA quick_check').fetchone()[0]
    check('sqlite_integrity_and_empty_approved_view', quick == 'ok' and approved_n == 0)
    check('exact_eight_series_saved_input_rows', actual['input_closes'] == source and len(source) == 9280)
    check('all_sixteen_definitions_and_dates', len(expected) == len(actual['features']) == 18560 and
          len({(r['signal_date'], r['feature_id']) for r in actual['features']}) == 18560 and len(dates) == 1160 and
          len(actual['feature_catalog']) == 16 and sum(r['role'] == 'candidate_context_feature' for r in actual['feature_catalog']) == 15)
    feature_differences, max_error = [], 0.0
    compared_numeric, compared_structural = 0, 0
    for a in actual['features']:
        key = a['signal_date'], a['feature_id']
        e = expected[key]
        for field in e:
            if field in ('diagnostic_value', 'engineering_value'):
                compared_numeric += 1
                av, ev = a[field], e[field]
                ok = (av is None) == (ev is None)
                if av is not None and ev is not None:
                    error = abs(av - float(ev))
                    max_error = max(max_error, error)
                    ok = math.isfinite(av) and error <= 8e-16 * (1 + abs(float(ev)))
            else:
                compared_structural += 1
                ok = a[field] == e[field]
            if not ok:
                feature_differences.append(dict(date=key[0], feature=key[1], field=field, saved=a[field], expected=str(e[field])))
    check('all_feature_values_null_masks_status_and_gates_match_fraction_oracle', not feature_differences,
          dict(numeric_cells=compared_numeric, structural_cells=compared_structural, max_absolute_error=max_error, differences=feature_differences[:10]))
    check('all_96312_dependency_rows_exact', actual['feature_dependencies'] == expected_dep and len(expected_dep) == 96312)
    check('stock_segments_exact_and_no_known_ex_date_bridge', actual['stock_segments'] == segments)
    conflict_cells = [r for r in expected.values() if r['status'] == 'CLOSE_SOURCE_CONFLICT']
    conflict_dates = sorted({r['signal_date'] for r in conflict_cells})
    conflict_by_feature = dict(sorted(Counter(r['feature_id'] for r in conflict_cells).items()))
    check('exact_close_conflict_propagation_recomputed', len(bad) == 1 and len(conflict_cells) == 28 and len(conflict_dates) == 21 and
          len(actual['close_source_conflicts']) == 1 and actual['close_source_conflicts'][0]['canonical_symbol'] == '000001.SH' and
          actual['close_source_conflicts'][0]['trade_date'] == '2026-02-11',
          dict(feature_cells=len(conflict_cells), dates=conflict_dates, cells_by_feature=conflict_by_feature))
    wide_diffs = []
    actual_lookup = {(r['signal_date'], r['feature_id']): r for r in actual['features']}
    for row in actual['wide_engineering_values']:
        for k, v in row.items():
            if k in ('signal_date', 'model_input_approved', 'runtime_usable'):
                continue
            a = actual_lookup[row['signal_date'], k]
            if a['engineering_value'] != v:
                wide_diffs.append((row['signal_date'], k))
    check('wide_table_exactly_engineering_masked_values', not wide_diffs and len(actual['wide_engineering_values']) == 1160 and
          all(r['model_input_approved'] == r['runtime_usable'] == 0 for r in actual['wide_engineering_values']))
    expected_coverage = {}
    for fid in {r['feature_id'] for r in expected.values()}:
        for scope, start, end in [('all_saved', '2022-01-04', '2026-10-21'), ('research', '2023-01-03', '2026-10-21'), ('development', '2023-01-03', '2024-12-31')]:
            ff = [r for r in expected.values() if r['feature_id'] == fid and start <= r['signal_date'] <= end]
            expected_coverage[fid, scope] = dict(feature_id=fid, role=ff[0]['role'], scope=scope, dates=len(ff),
                diagnostic_computed=sum(r['diagnostic_value'] is not None for r in ff), engineering_ready=sum(r['engineering_ready'] for r in ff),
                source_conflict_quarantined=sum(r['status'] == 'CLOSE_SOURCE_CONFLICT' for r in ff),
                history_not_ready=sum(r['diagnostic_value'] is None for r in ff), formal_model_input_approved=0)
    check('all_48_coverage_rows_independently_recomputed', len(actual['coverage']) == 48 and
          all(r == expected_coverage[r['feature_id'], r['scope']] for r in actual['coverage']))
    metadata = json.loads(actual['metadata'][0]['value_json'])
    check('metadata_preserves_no_models_no_targets_and_false_formal_gates', metadata['contract'] == cfg and
          metadata['registration'] == receipt and metadata['new_models_scored'] == 0 and metadata['previous_research_variants'] == 15 and
          metadata['future_targets_read_or_generated'] is False and metadata['model_input_approved'] is False and metadata['runtime_usable'] is False and
          cfg['outcomes_2025_2026_opened'] is False and cfg['event_countdown_features_generated'] is False)
    csv_names = {'input_closes': '输入收盘及来源.csv', 'feature_catalog': '特征公式字典.csv', 'features': '逐日市场环境特征_工程准备.csv',
                 'feature_dependencies': '逐值计算依赖.csv', 'stock_segments': '个股价格分段.csv', 'wide_engineering_values': '日期宽表_未获正式准入.csv',
                 'coverage': '特征覆盖与隔离.csv', 'close_source_conflicts': '收盘差异台账.csv'}
    csv_mismatches = []
    for table, filename in csv_names.items():
        with (DELIVERY / filename).open(encoding='utf-8-sig', newline='') as f:
            rr = list(csv.DictReader(f))
        if len(rr) != len(actual[table]) or any(any((str(v) if v is not None else '') != r[k] for k, v in a.items()) for r, a in zip(rr, actual[table])):
            csv_mismatches.append(filename)
    check('all_eight_csv_exports_exactly_match_sqlite', not csv_mismatches, csv_mismatches)
    # Import only now, strictly for negative tests and synthetic causal probes.
    spec = importlib.util.spec_from_file_location('prod_market_context_audit_only', CODE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    probe_source = [r for r in source if r['trade_date'] <= '2023-02-28']
    probe_events = {d for d in ex_dates if d <= '2023-02-28'}
    negatives = []
    for name in ('empty', 'missing_series', 'duplicate_id', 'duplicate_date', 'unaligned', 'unordered',
                 'unknown_series', 'wrong_collection', 'wrong_adjustment', 'wrong_price_unit',
                 'missing_close', 'zero_close', 'negative_close', 'nan_close', 'positive_inf', 'negative_inf', 'string_close'):
        rr = deepcopy(probe_source)
        if name == 'empty':
            rr = []
        elif name == 'missing_series':
            rr = [r for r in rr if not (r['canonical_symbol'] == STOCK and r['provider'] == 'tencent')]
        elif name == 'duplicate_id':
            rr.append(deepcopy(rr[0]))
        elif name == 'duplicate_date':
            v = deepcopy(rr[0]); v['observation_id'] = 'independent_new_duplicate_date'; rr.insert(1, v)
        elif name == 'unaligned':
            rr.pop(0)
        elif name == 'unordered':
            rr[0], rr[1] = rr[1], rr[0]
        elif name == 'unknown_series':
            rr[0]['canonical_symbol'] = 'unknown'
        elif name == 'wrong_collection':
            rr[0]['collection'] = 'legacy_main'
        elif name == 'wrong_adjustment':
            rr[0]['adjustment'] = '1'
        elif name == 'wrong_price_unit':
            rr[0]['price_unit'] = 'wrong_unit'
        else:
            rr[0]['close'] = {'missing_close': None, 'zero_close': 0, 'negative_close': -1, 'nan_close': math.nan,
                             'positive_inf': math.inf, 'negative_inf': -math.inf, 'string_close': '1.23'}[name]
        exception = None
        try:
            mod.prepare(rr, probe_events, cfg)
        except (ValueError, TypeError, ArithmeticError) as exc:
            exception = type(exc).__name__
        negatives.append(dict(mutation=name, rejected=exception is not None, exception=exception))
    check('invalid_source_domain_and_close_probes_reject', all(r['rejected'] for r in negatives), negatives)
    contract_negatives = []
    for k, v in [('primary_provider', 'tencent'), ('return_lags', [1, 3, 20]), ('ma_observations_including_current', 19),
                 ('calculation_start', '2022-01-04'), ('runtime_usable', True), ('future_targets_generated_or_scored', True),
                 ('historical_industry_membership_verified', True), ('index_formula_definitions', {}), ('relative_formula', 'changed')]:
        altered = deepcopy(cfg); altered[k] = v
        try:
            mod.guard(altered); rejected = False
        except ValueError:
            rejected = True
        contract_negatives.append(dict(field=k, rejected=rejected))
    check('frozen_contract_mutation_probes_reject', all(r['rejected'] for r in contract_negatives), contract_negatives)
    prefix_results = []
    for end in ('2022-12-30', '2023-06-20', '2024-05-24', '2026-02-11', '2026-09-22'):
        result = mod.prepare([r for r in source if r['trade_date'] <= end], {d for d in ex_dates if d <= end}, cfg)
        ok = result['features'] == [r for r in actual['features'] if r['signal_date'] <= end] and result['feature_dependencies'] == [r for r in actual['feature_dependencies'] if r['signal_date'] <= end]
        prefix_results.append(dict(prefix_end=end, matches=ok))
    check('causal_prefixes_exact_including_ex_and_conflict_dates', all(r['matches'] for r in prefix_results), prefix_results)
    poisoned = deepcopy(source)
    for r in poisoned:
        if r['trade_date'] > '2024-12-31':
            r['close'] = r['close'] * 1.371 + .091
    result = mod.prepare(poisoned, ex_dates, cfg)
    check('future_source_price_mutation_cannot_change_development_features_or_dependencies',
          [r for r in result['features'] if r['signal_date'] <= '2024-12-31'] == [r for r in actual['features'] if r['signal_date'] <= '2024-12-31'] and
          [r for r in result['feature_dependencies'] if r['signal_date'] <= '2024-12-31'] == [r for r in actual['feature_dependencies'] if r['signal_date'] <= '2024-12-31'])
    synthetic = []
    for symbol in (STOCK, '399001.SZ'):
        rr = deepcopy(probe_source)
        chosen = next(r for r in rr if r['canonical_symbol'] == symbol and r['provider'] == 'tencent' and r['trade_date'] == '2023-01-03')
        chosen['close'] += .01
        exp, dep, _, _, _ = ref_build(rr, probe_events)
        generated = mod.prepare(rr, probe_events, cfg)
        expected_set = {(d, f) for (d, f), r in exp.items() if r['status'] == 'CLOSE_SOURCE_CONFLICT'}
        actual_set = {(r['signal_date'], r['feature_id']) for r in generated['features'] if r['status'] == 'CLOSE_SOURCE_CONFLICT'}
        synthetic.append(dict(conflicted_symbol=symbol, close_date='2023-01-03', expected_cells=len(expected_set),
                              expected_dates=len({d for d, _ in expected_set}), matched=expected_set == actual_set,
                              dependency_match=generated['feature_dependencies'] == dep))
    check('synthetic_stock_and_index_conflicts_propagate_transitively_exactly', all(r['matched'] and r['dependency_match'] for r in synthetic), synthetic)
    gate_results = []
    for table in ('features', 'feature_catalog', 'wide_engineering_values'):
        with sqlite3.connect(':memory:') as c:
            c.execute(schema[table])
            base = actual[table][0]
            for gate in ('model_input_approved', 'runtime_usable', 'historical_first_availability_certified'):
                if gate not in base:
                    continue
                altered = dict(base); altered[gate] = 1
                col = ','.join('"' + k.replace('"', '""') + '"' for k in altered)
                try:
                    c.execute(f'INSERT INTO "{table}" ({col}) VALUES ({",".join("?" for _ in altered)})', list(altered.values()))
                    rejected = False
                except sqlite3.IntegrityError:
                    rejected = True
                gate_results.append(dict(table=table, gate=gate, value_one_rejected=rejected))
    check('sqlite_formal_gate_constraints_reject_promotion', all(r['value_one_rejected'] for r in gate_results), gate_results)
    after = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    check('all_old_sources_final_code_contract_receipt_and_output_db_unchanged', before == after)
    report = dict(scope='Independent Fraction values and dependencies for close-only market preparation; no outcomes/targets queried.',
        passed=all(r['passed'] for r in CHECKS), checks_passed=sum(r['passed'] for r in CHECKS), checks_total=len(CHECKS), checks=CHECKS,
        independent_formula_rows=len(expected), independent_dependency_rows=len(expected_dep),
        feature_numeric_comparison_cells=compared_numeric, feature_structural_comparison_cells=compared_structural,
        max_feature_absolute_error=max_error, feature_differences=feature_differences,
        close_conflict_cells=len(conflict_cells), close_conflict_dates=conflict_dates, close_conflict_cells_by_feature=conflict_by_feature,
        synthetic_conflict_probes=synthetic, code_sha256=sha(CODE), contract_sha256=sha(CONTRACT), receipt_sha256=sha(RECEIPT),
        delivery_db_sha256=sha(DATABASE), source_sha256=sha(SOURCE), hashes_before=before, hashes_after=after,
        producer_import_use='Negative/mutation/causality probes only, after independent expected outputs already completed.',
        source_tables_queried=['market_daily', 'corporate_actions'], future_target_tables_queried=[],
        formal_historical_model_input_approved=False, runtime_usable=False, predictive_validity_certified=False,
        future_targets_generated_or_scored=False, new_model_or_scored_variants=0)
    (OUT / '市场特征独立复核.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# 市场环境特征独立复核（2026-10-31）', '',
        f'核查{report["checks_passed"]}/{report["checks_total"]}通过。独立使用Fraction精确有理数，从统一库收盘价重建16条公式×1,160日，共18,560个特征及96,312条精确价格依赖，未调用生产公式生成预期结果。', '',
        f'逐值核对{compared_numeric:,}个数值格和{compared_structural:,}个结构格；最大浮点绝对误差{max_error:.3e}，NULL、计算状态、依赖来源、已知除权分段、宽表与48行覆盖统计均与独立预期相符。', '',
        f'2026-02-11上证唯一close冲突传播为{len(conflict_cells)}个特征格、{len(conflict_dates)}个日期。只保留诊断值，工程值NULL；未误把无关open/high差异传入close计算。', '',
        '## 具有行为意义的检查', '',
        '- 空/缺失/重复/乱序/未对齐来源域、错误供应商序列/集合/调整口径/单位，以及缺失、非正、非有限或字符串价格均拒绝。',
        '- 修改固定供应商、期限、均线窗口、起算日、公式或关闭的准入开关均拒绝。代码、合同、登记和受保护源指纹匹配。',
        '- 五个日期前缀的特征及精确依赖一致；改动2024年后全部源价格不改变2023—2024工程特征及依赖。这里没有计算后期结果标签。',
        '- 分别合成一处个股及指数close冲突，依赖和衍生相对特征的隔离集合与独立预期严格一致。',
        '- 输出数据库的正式准入/运行开关在内存重建schema中拒绝写1；原数据库没有写入。',
        '- 八份CSV与SQLite逐行逐格一致，已准入视图为空。所有旧源、本次生产代码/合同/登记和输出数据库前后哈希不变。', '',
        '这是公式、依赖和隔离行为核查，不是预测有效性证明。历史首次可得性、行业成员及事件领先期尚未准入，正式模型和运行开关保持false。', '',
        '## 最终指纹', '', f'- 生产代码：{report["code_sha256"]}', f'- 合同：{report["contract_sha256"]}',
        f'- 工程数据库：{report["delivery_db_sha256"]}', '', '所有检查明细、负例及合成探针结果见同目录JSON。']
    (OUT / '市场特征独立复核.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'checks_passed', 'checks_total', 'independent_formula_rows',
        'independent_dependency_rows', 'max_feature_absolute_error', 'close_conflict_cells')}, ensure_ascii=False))
    for c in CHECKS:
        if not c['passed']:
            print(json.dumps(c, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
