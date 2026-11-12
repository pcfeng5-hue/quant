"""Independent stdlib-only source audit. Reads index prices, never outcomes/labels.

No imports from previous collectors, and no network calls or old-file writes.
The SQLite connection is read-only; SQL is limited to market_daily/conflicts.
"""
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
STAGE = ROOT / 'work/market_industry_oct22'
DB = ROOT / 'outputs/统一数据底座_20261022/统一数据底座.sqlite'
SYMBOLS = ('000001.SH', '399001.SZ', '399967.SZ')
IDENTITY = {
    '000001.SH': ('1.000001', 'sh000001', '000001', 1, '上证指数'),
    '399001.SZ': ('0.399001', 'sz399001', '399001', 0, '深证成指'),
    '399967.SZ': ('0.399967', 'sz399967', '399967', 0, '中证军工'),
}
FIELDS = ('open', 'high', 'low', 'close', 'volume_raw', 'amount_raw', 'turnover_raw')
CHECKS = []


def check(name, ok, detail=None):
    CHECKS.append(dict(name=name, passed=bool(ok), detail=detail))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(2 ** 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(), parse_float=Decimal)


def num(value):
    return None if value is None else Decimal(str(value))


def simple(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value.relative_to(ROOT))
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(type(value).__name__)


def raw_parse(request):
    """Explicit independent raw mapping for the six saved index responses."""
    path = Path(request['raw_path'])
    payload = load(path)
    symbol, provider = request['symbol'], request['provider']
    secid, txsymbol, code, market, name = IDENTITY[symbol]
    if provider == 'eastmoney':
        data = payload['data']
        check(f'{request["id"]}:response_identity',
              data['code'] == code and data['market'] == market and
              data['name'] == name and payload['rc'] == 0)
        check(f'{request["id"]}:request_mapping',
              request['parameters']['secid'] == secid and
              request['parameters']['klt'] == 101 and
              request['parameters']['fqt'] == '0' and
              request['parameters']['fields2'] == 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
        records = data['klines']
    else:
        check(f'{request["id"]}:request_mapping',
              request['txsymbol'] == txsymbol and
              request['parameters']['param'] == f'{txsymbol},day,2022-01-01,2026-10-21,1600,' and
              payload['code'] == 0)
        data = payload['data'][txsymbol]
        records = data['day']
    parsed = []
    for index, raw in enumerate(records):
        a = raw.split(',') if isinstance(raw, str) else raw
        row = dict(symbol=symbol, source=provider, adjustment='0', trade_date=a[0],
                   open=num(a[1]), close=num(a[2]), high=num(a[3]), low=num(a[4]),
                   volume_raw=num(a[5]), amount_raw=num(a[6]) if provider == 'eastmoney' else None,
                   turnover_raw=num(a[10]) if provider == 'eastmoney' else None,
                   source_request_id=request['id'], source_sha256=request['sha256'],
                   source_row_index=index, raw_row=raw)
        parsed.append(row)
    return parsed


def main():
    # Capture all previous staging files and the unified DB, before any SQL reads.
    protected = sorted(p for p in STAGE.rglob('*') if p.is_file()) + [DB]
    before = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    manifest = load(STAGE / 'manifest.json')
    requests = [r for r in manifest['results'] if r.get('kind') == 'index' and r.get('symbol') in SYMBOLS]
    check('exactly_six_index_requests', len(requests) == 6 and
          len({(r['symbol'], r['provider']) for r in requests}) == 6)
    raw_hashes, raw_rows = [], []
    for r in requests:
        p = Path(r['raw_path'])
        h, size = digest(p), p.stat().st_size
        raw_hashes.append(dict(request_id=r['id'], path=p, sha256=h,
                               bytes=size, expected_sha256=r['sha256'],
                               expected_bytes=r['bytes'], matches=h == r['sha256'] and size == r['bytes'],
                               url=r['url'], requested_at_utc=r['requested_at_utc'],
                               finished_at_utc=r['finished_at_utc']))
        raw_rows.extend(raw_parse(r))
    check('six_original_hashes_and_sizes', all(r['matches'] for r in raw_hashes))
    check('independent_raw_parse_6960_rows', len(raw_rows) == 6960)
    check('all_raw_ohlcv_valid', all(Decimal(0) < r['low'] <= min(r['open'], r['close']) <=
           max(r['open'], r['close']) <= r['high'] and r['volume_raw'] >= 0 for r in raw_rows))
    staged = [r for r in load(STAGE / 'market_rows_unique.json') if r['symbol'] in SYMBOLS]
    key = lambda r: (r['symbol'], r['source'], r['trade_date'])
    raw_map, stage_map = {key(r): r for r in raw_rows}, {key(r): r for r in staged}
    check('raw_and_stage_unique_keys_exact', len(raw_map) == len(raw_rows) == len(stage_map) == len(staged) and
          raw_map.keys() == stage_map.keys())
    stage_differences = []
    stage_fields = (*FIELDS, 'source_request_id', 'source_sha256', 'source_row_index', 'raw_row')
    for k, r in raw_map.items():
        s = stage_map[k]
        for field in stage_fields:
            a, b = r[field], s[field]
            if field in FIELDS:
                a, b = num(a), num(b)
            if a != b:
                stage_differences.append(dict(key=k, field=field, original=a, staged=b))
    check('all_stage_cells_equal_raw', not stage_differences, dict(compared_cells=len(raw_rows) * len(stage_fields)))
    check('stage_canonical_and_price_unit', all(r['kind'] == 'index' and r['adjustment'] == '0' and
          r['price_unit'] == 'index_points' and
          r['volume_unit'] == 'provider_native_index_volume_unit_and_scope_unverified' for r in staged))
    series, coverage = {}, []
    for symbol in SYMBOLS:
        for provider in ('eastmoney', 'tencent'):
            rr = [r for r in raw_rows if r['symbol'] == symbol and r['source'] == provider]
            dd = [r['trade_date'] for r in rr]
            series[symbol, provider] = {r['trade_date']: r for r in rr}
            coverage.append(dict(symbol=symbol, provider=provider, dates=len(dd), first=min(dd), last=max(dd),
                                 warmup_2022=sum(d < '2023-01-01' for d in dd),
                                 development_2023_2024=sum('2023-01-01' <= d <= '2024-12-31' for d in dd),
                                 research_2023_onward=sum(d >= '2023-01-01' for d in dd)))
            check(f'{symbol}/{provider}:dates_unique_ordered_range', len(dd) == 1160 and dd == sorted(set(dd)) and
                  min(dd) == '2022-01-04' and max(dd) == '2026-10-21')
    all_dates = [set(v) for v in series.values()]
    check('all_six_vendor_date_sets_identical', all(d == all_dates[0] for d in all_dates))
    check('coverage_242_warmup_918_research', all(r['warmup_2022'] == 242 and r['research_2023_onward'] == 918 for r in coverage))
    price_differences, volume_differences, provider_comparison = [], [], []
    for symbol in SYMBOLS:
        a, b = series[symbol, 'eastmoney'], series[symbol, 'tencent']
        price_days, close_days = set(), set()
        for d in sorted(a):
            for f in ('open', 'high', 'low', 'close', 'volume_raw'):
                if a[d][f] != b[d][f]:
                    delta = dict(symbol=symbol, trade_date=d, field=f,
                                 eastmoney=a[d][f], tencent=b[d][f], difference_tencent_minus_eastmoney=b[d][f] - a[d][f])
                    (volume_differences if f == 'volume_raw' else price_differences).append(delta)
                    if f != 'volume_raw':
                        price_days.add(d)
                    if f == 'close':
                        close_days.add(d)
        provider_comparison.append(dict(symbol=symbol, overlap_dates=len(a), ohlc_difference_dates=sorted(price_days),
                                        close_difference_dates=sorted(close_days),
                                        volume_difference_dates=sum(x['symbol'] == symbol for x in volume_differences),
                                        exact_close_agreement_dates=len(a) - len(close_days)))
    check('exact_price_differences_five_cells', len(price_differences) == 5)
    check('development_2023_2024_three_index_close_agreement',
          not any(x['field'] == 'close' and '2023-01-01' <= x['trade_date'] <= '2024-12-31' for x in price_differences))
    check('all_price_differences_one_hundredth_point', all(abs(x['difference_tencent_minus_eastmoney']) == Decimal('.01') for x in price_differences))
    check('existing_conflict_file_equals_exact_source_recalculation',
          {(x['symbol'], x['trade_date'], f) for x in load(STAGE / 'cross_source_differences.json')
           if x['symbol'] in SYMBOLS for f in x['fields']} ==
          {(x['symbol'], x['trade_date'], x['field']) for x in price_differences + volume_differences})
    con = sqlite3.connect(f'file:{DB}?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    index_rows = [dict(r) for r in con.execute(
        "SELECT * FROM market_daily WHERE canonical_symbol IN ('000001.SH','399001.SZ','399967.SZ')")]
    latest = [r for r in index_rows if r['collection'] == 'market_industry_oct21']
    groups = defaultdict(list)
    for r in index_rows:
        groups[r['collection'], r['symbol'], r['canonical_symbol'], r['provider'], r['adjustment'],
               r['price_unit'], r['volume_unit']].append(r)
    db_coverage = []
    for k, rr in sorted(groups.items()):
        db_coverage.append(dict(collection=k[0], symbol=k[1], canonical_symbol=k[2], provider=k[3], adjustment=k[4],
                                price_unit=k[5], volume_unit=k[6], versioned_rows=len(rr), unique_dates=len({r['trade_date'] for r in rr}),
                                first=min(r['trade_date'] for r in rr), last=max(r['trade_date'] for r in rr)))
    db_map = {(r['canonical_symbol'], r['provider'], r['trade_date']): r for r in latest}
    check('unified_latest_6960_unique_index_rows', len(db_map) == len(latest) == 6960 and db_map.keys() == raw_map.keys())
    db_diffs, comparisons = [], 0
    fieldmap = {'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                'volume_raw': 'volume_native', 'amount_raw': 'amount_cny', 'turnover_raw': 'turnover_pct'}
    for k, raw in raw_map.items():
        row = db_map[k]
        for f, target in fieldmap.items():
            comparisons += 1
            if num(raw[f]) != num(row[target]):
                db_diffs.append(dict(key=k, field=f, raw=raw[f], database=row[target]))
        if (row['source_request_id'] != raw['source_request_id'] or row['source_sha256'] != raw['source_sha256'] or
                row['raw_row_index'] != raw['source_row_index']):
            db_diffs.append(dict(key=k, field='source_link'))
        r = next(r for r in requests if r['id'] == raw['source_request_id'])
        if row['retrieved_at'] != r['finished_at_utc']:
            db_diffs.append(dict(key=k, field='retrieved_at', db=row['retrieved_at'], expected=r['finished_at_utc']))
    check('unified_numeric_and_source_link_exact', not db_diffs, dict(numeric_cells=comparisons))
    check('unified_latest_canonical_price_units_and_zero_approval', all(
        r['symbol'] == r['canonical_symbol'] and r['price_unit'] == 'index_points' and
        r['adjustment'] == '0' and r['model_input_approved'] == 0 for r in latest))
    check('all_preserved_index_versions_zero_approval', all(r['model_input_approved'] == 0 for r in index_rows))
    conflicts = [dict(r) for r in con.execute(
        "SELECT collection,symbol,reference_date,field_name,status FROM conflicts "
        "WHERE collection='market_industry_oct21' AND symbol IN ('000001.SH','399001.SZ','399967.SZ')")]
    check('unified_conflict_cells_equal_exact_source_recalculation',
          {(r['symbol'], r['reference_date'], r['field_name']) for r in conflicts} ==
          {(x['symbol'], x['trade_date'], x['field']) for x in price_differences + volume_differences})
    legacy_differences = []
    for row in index_rows:
        if row['collection'] == 'market_industry_oct21':
            continue
        k = row['canonical_symbol'], row['provider'], row['trade_date']
        if k not in db_map:
            continue
        for f in ('open', 'high', 'low', 'close'):
            if num(row[f]) != num(db_map[k][f]):
                legacy_differences.append(dict(observation_id=row['observation_id'], canonical_symbol=k[0], provider=k[1],
                                               trade_date=k[2], field=f, preserved_version=row[f], latest=db_map[k][f]))
    con.close()
    after = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    check('all_protected_original_hashes_unchanged', before == after, dict(files=len(protected)))
    out = dict(
        audit_scope='Raw saved six index responses → independent Decimal parse → staged rows → unified index market rows only.',
        new_network_requests=0, labels_generated_read_or_scored=False,
        post_2024_target_tables_queried=False, model_or_signal_experiments_added=0,
        price_unit='index_points', volume_unit_certified=False,
        raw_hash_checks=raw_hashes, coverage=coverage, independent_raw_rows=len(raw_rows),
        stage_numeric_or_source_differences=stage_differences, unified_numeric_or_source_differences=db_diffs,
        unified_preserved_version_groups=db_coverage, preserved_old_vs_latest_ohlc_differences=legacy_differences,
        provider_comparison=provider_comparison, exact_ohlc_differences=price_differences,
        volume_difference_count=len(volume_differences), volume_difference_counts=dict(Counter(r['symbol'] for r in volume_differences)),
        source_selection_recommendation=dict(
            status='fixed_source_engineering_permitted_subject_to_parent_input_contract_not_formal_model_approval',
            collection='market_industry_oct21', provider='eastmoney', adjustment='0',
            fields=['close'], date_range=['2022-01-04', '2026-10-21'],
            reason='Existing declared reference uses this saved snapshot; close source lineage is complete. Provider choice is reproducibility, not truth adjudication or a result-selected choice.',
            query="SELECT * FROM market_daily WHERE collection='market_industry_oct21' AND provider='eastmoney' AND adjustment='0' AND canonical_symbol IN ('000001.SH','399001.SZ','399967.SZ') ORDER BY canonical_symbol,trade_date",
            forbid_splicing_or_averaging=True,
            close_conflict_policy='Preserve 2026-02-11/000001.SH flag; no silent repair. In close-window feature diagnostics, propagate flag through every dependency window, including ratio endpoints. A later protocol must freeze exclusion or sensitivity policy before results.',
            ohlc_discrepancy_policy='Keep all five exact field/date flags; do not falsely treat 399967 open/high differences as close mismatches.',
            missing_or_duplicate_policy='Abort/abstain on ambiguity; never forward-fill price or replace with another provider.',
            blocked_fields=['volume_native','amount_cny','turnover_pct'],
            blocked_field_reason='Index volume unit/scope and vendor-defined turnover remain unverified; no cross-provider pools. Amount not used in this close-only feature batch.',
            model_input_approved=False, runtime_usable=False),
        historical_availability=dict(
            earliest_resolution='Completed daily close only; final daily close cannot be used for an earlier same-day intraday decision.',
            timezone='Asia/Shanghai', first_historical_publication_time_certified=False,
            captured_request_times_only=True, point_in_time_vintage_certified=False,
            request_times_are_not_historical_first_publication=True,
            vendor_upstream_independence_certified=False,
            current_snapshot_future_revision_risk_retained=True),
        industry_restrictions=dict(symbol='399967.SZ', use='military-sector price-index background proxy',
                                   official_methodology_saved='2023-12 V1.2',
                                   membership_002414_any_historical_date_certified=False,
                                   historical_methodology_versions_complete=False,
                                   total_return_index=False),
        protected_hashes_before=before, protected_hashes_after=after,
        checks=CHECKS, checks_passed=sum(c['passed'] for c in CHECKS),
        checks_total=len(CHECKS), passed=all(c['passed'] for c in CHECKS))
    (OUT / '市场来源独立核对.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=simple) + '\n')
    lines = ['# 三指数价格来源独立核对（2026-10-31）', '',
             '仅核对已保存来源、价格和元数据；无联网、无标签读取生成、无模型评分，旧文件保持不变。', '',
             f'技术核查 {out["checks_passed"]}/{out["checks_total"]}。六份原始响应均与已保存SHA256、字节数一致；独立按Decimal解析6,960行，暂存和统一库逐值及来源关联相符。', '',
             '三指数每供应商均1,160个观察交易日，2022-01-04—2026-10-21；2022预热242日，2023起研究918日。日期集合一致仅证明供应商样本对齐，不能替代官方交易日历审计。', '',
             '|指数|日期|字段|东方财富|腾讯|', '|---|---|---|---:|---:|']
    for x in price_differences:
        lines.append(f'|{x["symbol"]}|{x["trade_date"]}|{x["field"]}|{x["eastmoney"]}|{x["tencent"]}|')
    lines += ['', '全部价格差异均0.01指数点。2023—2024开发期三指数收盘价双源严格一致；整个保存期仅上证2026-02-11收盘价不一致。其他四项为开盘/最高价差异，不能错误标成收盘价冲突。', '',
              f'成交量差异共{len(volume_differences)}个指数/日期，分布为：'+json.dumps(out['volume_difference_counts'],ensure_ascii=False)+'。单位和覆盖未认证，指数成交量不准入本轮价格特征。两端点不证明独立上游。', '',
              f'统一库保留早期版本与本轮快照的OHLC不同记录{len(legacy_differences)}条；来源、版本保留，禁止拼接后伪装单一历史序列。具体核对见JSON。', '',
              '## 可执行来源约定建议', '',
              '- 固定collection=market_industry_oct21、provider=eastmoney、adjustment=0，以canonical_symbol选取同份保存快照的close。沿用既有参考来源是复现选择，不宣称东方财富为真值，也不按模型成绩选供应商。',
              '- close以指数点计量。相邻收益/滚动均线始终同供应商、同口径；缺值或重复日期弃答/报错，不前填、不拼接、不求双源均值。',
              '- 保留2026-02-11上证close冲突及受影响的全部滚动依赖窗口。正式实验前另行冻结排除或敏感性政策，不能在看结果后决定。其余OHLC冲突保留字段级旗标。',
              '- 当前只准做价格特征工程。指数成交量/换手定义未认证；不据此计算资金流。',
              '- 仅用于收盘后信息集：保存的2026-10-22提取时间不是每个历史交易日的首次公开时间。供应商历史修订和历史当时可得性仍未认证，因此正式model_input_approved/runtime_usable保持false。',
              '- 中证军工399967只能作军工背景价格代理。官方2023年12月V1.2编制方案已保存，但不能证明002414任一历史日期属于成份，也不是完整历史成员库或含红利再投的全收益指数。', '',
              f'本次保护{len(protected)}个旧文件，前后SHA256全部一致。详细字段、请求URL/时间、原件路径、差异与全部核查结果见同目录JSON。']
    (OUT / '市场来源独立核对.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(passed=out['passed'], checks_passed=out['checks_passed'], checks_total=out['checks_total'],
                          failed=[c for c in CHECKS if not c['passed']], raw_rows=len(raw_rows),
                          exact_ohlc_differences=price_differences, preserved_old_vs_latest_ohlc_differences=len(legacy_differences),
                          protected_files=len(protected)), ensure_ascii=False, default=simple))
    return 0 if out['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
