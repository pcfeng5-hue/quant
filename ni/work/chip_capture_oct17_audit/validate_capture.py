"""Read-only audit of root's visible-UI chip capture; outputs stay outside capture root.

Run after capture ends. --limit is for a named sample preview, never final coverage.
No network, browser interaction, inferred bins or main database writes.
"""
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = Path(__file__).resolve().parent
DEFAULT_CAPTURE = ROOT / 'work/chip_full_capture_oct17'
MAIN_DB = ROOT / 'outputs/高德红外数据库/高德红外_2023起.sqlite'
FIELD_NAMES = ['date', 'profit_ratio_display', 'average_cost_display', 'cost90_display',
               'concentration90_display', 'cost70_display', 'concentration70_display']
REQUIRED_EVIDENCE = ['record.json', 'summary.html', 'kline.html', 'ax.txt', 'chart.jpg']
DECLARED_UI_EXTENSIONS = ['2026-10-16']


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for part in iter(lambda: fp.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def json_retry(path, tries=4):
    for attempt in range(tries):
        try:
            raw = path.read_bytes()
            return json.loads(raw), raw
        except (json.JSONDecodeError, FileNotFoundError):
            if attempt == tries - 1:
                raise
            time.sleep(0.25)


def strip_tags(text):
    return unescape(re.sub(r'<[^>]*>', '', text)).strip()


def decimal(text, pct=False):
    if not isinstance(text, str):
        raise ValueError('numeric display must remain a string')
    if pct and not text.endswith('%'):
        raise ValueError('percentage display lacks % unit')
    value = Decimal(text[:-1] if pct else text)
    if not value.is_finite():
        raise ValueError('nonfinite value')
    return value


def cost_range(text):
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)-([0-9]+(?:\.[0-9]+)?)', text)
    if not match:
        raise ValueError('invalid displayed cost range')
    lo, hi = [decimal(x) for x in match.groups()]
    if not Decimal('0') < lo <= hi:
        raise ValueError('nonpositive or reversed cost range')
    return lo, hi


def audit_row(row, capture):
    rid = row.get('id')
    issues = []
    diagnostics = []
    numbers = {}
    if not isinstance(rid, str) or Path(rid).name != rid or rid in ('.', '..'):
        return dict(id=str(rid), raw=row, issues=['unsafe_or_missing_id'], diagnostics=[],
                    audit_accepted=False, source_accepted=row.get('accepted') is True, numbers={})
    record_dir = capture / 'records' / rid
    missing = [name for name in REQUIRED_EVIDENCE if not (record_dir / name).is_file()]
    if missing:
        issues.append(dict(missing_evidence=missing))
    if (record_dir / 'chart.jpg').is_file():
        with (record_dir / 'chart.jpg').open('rb') as fp:
            if fp.read(3) != b'\xff\xd8\xff':
                issues.append('chart_file_not_jpeg')
    if (record_dir / 'ax.txt').is_file() and not (record_dir / 'ax.txt').read_text().strip():
        issues.append('empty_ax_snapshot')
    if (record_dir / 'record.json').is_file():
        saved, _ = json_retry(record_dir / 'record.json')
        if saved != row:
            issues.append('record_json_differs_from_root_index')
    values = row.get('values')
    if not isinstance(values, list) or len(values) != 7:
        issues.append('summary_requires_seven_display_values')
        values = []
    if values:
        actual_dates = [row.get('expected'), row.get('actual'), row.get('date'), values[0],
                        row.get('kline', {}).get('时间'), row.get('post', {}).get('date'),
                        row.get('post', {}).get('kline_date')]
        if len(set(actual_dates)) != 1 or not all(isinstance(x, str) for x in actual_dates):
            issues.append(dict(date_synchronization=actual_dates))
        try:
            datetime.strptime(values[0], '%Y-%m-%d')
        except (ValueError, TypeError):
            issues.append('invalid_actual_date')
        if row.get('post', {}).get('visible') != 'block':
            issues.append('post_capture_tooltip_not_visible')
        if (record_dir / 'summary.html').is_file():
            table = (record_dir / 'summary.html').read_text()
            parsed = [strip_tags(s) for s in re.findall(r'<td\b[^>]*class=[\"\'][^\"\']*\bqcyq_t_v\b[^\"\']*[\"\'][^>]*>(.*?)</td>', table, re.S)]
            if parsed != values:
                issues.append(dict(summary_html_values=parsed, record_values=values))
        if (record_dir / 'kline.html').is_file():
            kline_html = (record_dir / 'kline.html').read_text()
            kline_dates = [strip_tags(s) for s in re.findall(r'<td\b[^>]*class=[\"\'][^\"\']*\bkline_date\b[^\"\']*[\"\'][^>]*>(.*?)</td>', kline_html, re.S)]
            if kline_dates != [values[0]]:
                issues.append(dict(kline_html_dates=kline_dates))
            if not re.search(r'display\s*:\s*block', kline_html):
                issues.append('saved_kline_tooltip_not_visible')
            cells = [strip_tags(s) for s in re.findall(r'<td\b[^>]*>(.*?)</td>', kline_html, re.S)]
            parsed_kline = dict(zip(cells[::2], cells[1::2]))
            for key, value in row.get('kline', {}).items():
                if parsed_kline.get(key) != value:
                    issues.append(dict(kline_field=key, html=parsed_kline.get(key), record=value))
        try:
            p, avg, c90, c70 = decimal(values[1], True), decimal(values[2]), decimal(values[4], True), decimal(values[6], True)
            low90, high90 = cost_range(values[3])
            low70, high70 = cost_range(values[5])
            if not all(Decimal('0') <= v <= Decimal('100') for v in (p, c90, c70)):
                raise ValueError('percentage outside 0 to 100')
            if avg <= 0:
                raise ValueError('average cost nonpositive')
            if not low90 <= low70 <= high70 <= high90:
                raise ValueError('70 percent range not nested in 90 percent range')
            if not low90 <= avg <= high90:
                diagnostics.append('displayed_average_outside_90pct_range')
            if c70 > c90:
                diagnostics.append('70pct_concentration_exceeds_90pct')
            numbers = dict(profit_ratio_pct=float(p), average_cost=float(avg), cost90_low=float(low90),
                           cost90_high=float(high90), concentration90_pct=float(c90),
                           cost70_low=float(low70), cost70_high=float(high70), concentration70_pct=float(c70))
        except (ValueError, TypeError, InvalidOperation) as exc:
            issues.append(dict(field_structure=str(exc)))
    try:
        dt = datetime.fromisoformat(row.get('observed_at_utc', '').replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('timezone_missing')
    except (ValueError, TypeError):
        issues.append('invalid_retrieval_timestamp')
    try:
        kline = row.get('kline', {})
        op, close, high, low = [decimal(kline[key]) for key in ['开盘', '收盘', '最高', '最低']]
        if not Decimal('0') < low <= min(op, close) <= max(op, close) <= high:
            raise ValueError('invalid OHLC ordering or positivity')
        turnover = decimal(kline['换手率'], pct=True)
        if not Decimal('0') <= turnover <= Decimal('100'):
            raise ValueError('turnover outside 0 to 100')
    except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
        issues.append(dict(kline_structure=str(exc)))
    if row.get('basis') not in ('前复权', '后复权', '不复权'):
        issues.append('unrecognized_displayed_kline_basis')
    if not row.get('session'):
        issues.append('missing_session_context')
    if row.get('historical_input_eligible') is not False:
        issues.append('historical_input_eligibility_must_be_false')
    if row.get('complete_price_bins') is not False:
        issues.append('full_bins_must_not_be_claimed_from_summary')
    return dict(id=rid, raw=row, source_accepted=row.get('accepted') is True,
                audit_accepted=row.get('accepted') is True and not issues,
                issues=issues, diagnostics=diagnostics, numbers=numbers)


def make_sqlite(path, meta, audited, evidence, expected, ui_extensions, ohlc_comparisons):
    if path.exists():
        raise FileExistsError('Refusing to overwrite prior audit database: ' + str(path))
    conn = sqlite3.connect(path)
    try:
        conn.executescript('''
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
        CREATE TABLE observations (
          id TEXT PRIMARY KEY, actual_date TEXT, expected_date TEXT, session TEXT, stage TEXT,
          observed_at_utc TEXT, accessibility_source TEXT, source_accepted INTEGER NOT NULL, audit_accepted INTEGER NOT NULL,
          basis_display TEXT, profit_ratio_pct REAL, average_cost REAL,
          cost90_low REAL, cost90_high REAL, concentration90_pct REAL,
          cost70_low REAL, cost70_high REAL, concentration70_pct REAL,
          historical_input_eligible INTEGER NOT NULL CHECK(historical_input_eligible=0),
          complete_price_bins INTEGER NOT NULL CHECK(complete_price_bins=0),
          issues_json TEXT NOT NULL, diagnostics_json TEXT NOT NULL, raw_json TEXT NOT NULL);
        CREATE INDEX observation_dates ON observations(actual_date);
        CREATE TABLE evidence (
          relative_path TEXT PRIMARY KEY, observation_id TEXT, bytes INTEGER NOT NULL,
          sha256 TEXT NOT NULL, mtime_ns INTEGER NOT NULL);
        CREATE TABLE expected_dates (
          trade_date TEXT PRIMARY KEY,
          coverage_scope TEXT NOT NULL,
          main_database_date_present INTEGER NOT NULL);
        CREATE TABLE ohlc_comparison (
          observation_id TEXT NOT NULL, trade_date TEXT NOT NULL, field TEXT NOT NULL,
          display_value TEXT NOT NULL, main_qfq_value TEXT NOT NULL, absolute_delta TEXT NOT NULL,
          exact_match INTEGER NOT NULL, within_0005 INTEGER NOT NULL,
          PRIMARY KEY(observation_id,field));
        ''')
        conn.executemany('INSERT INTO metadata VALUES (?,?)', [(key, json.dumps(value, ensure_ascii=False)) for key, value in meta.items()])
        for a in audited:
            r, n = a['raw'], a['numbers']
            row = [a['id'], r.get('date'), r.get('expected'), r.get('session'), r.get('stage'),
                   r.get('observed_at_utc'), r.get('accessibility_source', 'native_ax_or_legacy_unlabelled'),
                   int(a['source_accepted']), int(a['audit_accepted']), r.get('basis')]
            row += [n.get(k) for k in ['profit_ratio_pct', 'average_cost', 'cost90_low', 'cost90_high',
                                      'concentration90_pct', 'cost70_low', 'cost70_high', 'concentration70_pct']]
            row += [0, 0, json.dumps(a['issues'], ensure_ascii=False), json.dumps(a['diagnostics'], ensure_ascii=False),
                    json.dumps(r, ensure_ascii=False)]
            conn.execute('INSERT INTO observations VALUES (' + ','.join('?' for _ in row) + ')', row)
        conn.executemany('INSERT INTO evidence VALUES (?,?,?,?,?)', [(r['relative_path'], r['observation_id'], r['bytes'], r['sha256'], r['mtime_ns']) for r in evidence])
        conn.executemany('INSERT INTO expected_dates VALUES (?,?,?)',
                         [(day, 'stored_market_baseline', 1) for day in expected] +
                         [(day, 'web_observation_extension', 0) for day in ui_extensions])
        conn.executemany('INSERT INTO ohlc_comparison VALUES (?,?,?,?,?,?,?,?)',
                         [(r['observation_id'], r['trade_date'], r['field'], r['display_value'],
                           r['main_qfq_value'], r['absolute_delta'], r['exact_match'], r['within_0005'])
                          for r in ohlc_comparisons])
        conn.commit()
        result = conn.execute('PRAGMA quick_check').fetchone()[0]
        if result != 'ok':
            raise RuntimeError('Output database quick_check: ' + result)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument('--main-database', type=Path, default=MAIN_DB)
    parser.add_argument('--prefix', default='full_capture_final')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if Path(args.prefix).name != args.prefix:
        parser.error('prefix must be a plain filename stem')
    if args.limit is not None and (args.limit < 1 or 'preview' not in args.prefix):
        parser.error('sample limit requires positive count and preview in prefix')
    capture = args.capture.resolve()
    database = args.main_database.resolve()
    if AUDIT_DIR == capture or capture in AUDIT_DIR.parents:
        parser.error('audit output must stay outside capture root')
    paths = {suffix: AUDIT_DIR / (args.prefix + suffix) for suffix in ['.json', '.sqlite', '_coverage.csv', '_manifest.json', '_ohlc_comparison.csv']}
    if any(path.exists() for path in paths.values()):
        parser.error('output prefix already exists; choose a fresh prefix')
    before_db = sha_file(database)
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as c:
        c.row_factory = sqlite3.Row
        expected = [r[0] for r in c.execute("SELECT DISTINCT trade_date FROM current_daily_bars WHERE source='em_daily_0' ORDER BY trade_date")]
        qfq_rows = [dict(r) for r in c.execute("SELECT * FROM current_daily_bars WHERE source='em_daily_1' AND adjustment='1' AND symbol='002414.SZ'")]
    qfq = {r['trade_date']: r for r in qfq_rows}
    if len(qfq) != len(qfq_rows):
        raise ValueError('Stored qfq data has duplicate trading dates; do not guess a version')
    rows, raw_index = json_retry(capture / 'records.json')
    if not isinstance(rows, list):
        raise ValueError('root records.json must contain an array')
    all_rows = rows
    if args.limit is not None:
        rows = rows[:args.limit]
    audited = [audit_row(row, capture) for row in rows]
    ids = [row.get('id') for row in rows]
    duplicate_ids = sorted({rid for rid in ids if ids.count(rid) > 1})
    evidence = []
    initial_files = sorted(p for p in capture.rglob('*') if p.is_file())
    for p in initial_files:
        stat = p.stat()
        relative = p.relative_to(capture)
        rid = relative.parts[1] if len(relative.parts) > 2 and relative.parts[0] == 'records' else None
        evidence.append(dict(relative_path=str(relative), observation_id=rid, bytes=stat.st_size,
                             sha256=sha_file(p), mtime_ns=stat.st_mtime_ns))
    source_changed = []
    if {str(p.relative_to(capture)) for p in capture.rglob('*') if p.is_file()} != {e['relative_path'] for e in evidence}:
        source_changed.append('capture_file_set_changed_during_audit')
    for entry in evidence:
        p = capture / entry['relative_path']
        if not p.exists() or p.stat().st_size != entry['bytes'] or p.stat().st_mtime_ns != entry['mtime_ns']:
            source_changed.append(entry['relative_path'])
    if sha_file(capture / 'records.json') != sha_bytes(raw_index):
        source_changed.append('root_records_changed_during_audit')
    after_db = sha_file(database)
    source_dates = sorted({a['raw'].get('date') for a in audited if a['source_accepted']})
    accepted = [a for a in audited if a['audit_accepted']]
    acquired = sorted({a['raw']['date'] for a in accepted})
    ui_extensions = sorted(set(DECLARED_UI_EXTENSIONS) - set(expected))
    target = sorted(set(expected) | set(ui_extensions))
    ohlc_comparisons = []
    ohlc_skipped = []
    for a in accepted:
        r = a['raw']
        if r.get('basis') != '前复权':
            ohlc_skipped.append(dict(id=a['id'], reason='displayed_basis_not_qfq'))
            continue
        if r['date'] not in qfq:
            ohlc_skipped.append(dict(id=a['id'], date=r['date'], reason='no_matching_main_qfq_date'))
            continue
        for display_field, main_field in [('开盘', 'open'), ('收盘', 'close'), ('最高', 'high'), ('最低', 'low')]:
            display = decimal(r['kline'][display_field])
            main = Decimal(str(qfq[r['date']][main_field]))
            delta = abs(display - main)
            ohlc_comparisons.append(dict(observation_id=a['id'], trade_date=r['date'], field=main_field,
                                         display_value=str(display), main_qfq_value=str(main), absolute_delta=str(delta),
                                         exact_match=delta == 0, within_0005=delta <= Decimal('0.005')))
    qfq_mismatches = [r for r in ohlc_comparisons if not r['exact_match']]
    target_file = capture / 'target_dates.json'
    declared_target_file = json_retry(target_file)[0] if target_file.is_file() else None
    variants = {}
    for day in acquired:
        groups = {}
        for a in accepted:
            if a['raw']['date'] == day:
                key = json.dumps(a['raw']['values'][1:], ensure_ascii=False)
                groups.setdefault(key, []).append(a['id'])
        variants[day] = [dict(values=json.loads(key), observation_ids=value) for key, value in groups.items()]
    orphan_dirs = sorted(p.name for p in (capture / 'records').iterdir() if p.is_dir() and p.name not in {r.get('id') for r in all_rows})
    report = dict(
        audit_version='visible-ui-summary-capture-audit-v1', capture_root=str(capture),
        scope='raw-only visible vendor summary observations; no full price bins, no main database writes, no forecasting',
        preview=args.limit is not None, root_index_records=len(all_rows), audited_records=len(audited),
        root_index_sha256=sha_bytes(raw_index),
        baseline=dict(symbol='002414.SZ', dates=len(expected), start=min(expected), end=max(expected),
                      acquired_dates=len(set(expected) & set(acquired)),
                      coverage_percent=round(len(set(expected) & set(acquired)) / len(expected) * 100, 6)),
        collection_target=dict(dates=len(target), start=min(target), end=max(target),
                               acquired_dates=len(set(target) & set(acquired)),
                               coverage_percent=round(len(set(target) & set(acquired)) / len(target) * 100, 6),
                               note='Stored market baseline plus explicitly declared additional webpage observation date; no main database extension'),
        declared_web_observation_extensions=[dict(date=day, acquired=day in acquired,
                                                  main_database_cross_checked=False,
                                                  historical_input_eligible=False) for day in ui_extensions],
        source_accepted_observations=sum(a['source_accepted'] for a in audited), source_accepted_unique_dates=source_dates,
        audit_accepted_observations=len(accepted), audit_accepted_unique_dates=acquired,
        expected_dates_acquired=len(set(expected) & set(acquired)),
        missing_expected_dates=sorted(set(expected) - set(acquired)),
        missing_collection_target_dates=sorted(set(target) - set(acquired)),
        acquired_dates_outside_baseline=sorted(set(acquired) - set(expected)),
        acquired_dates_outside_declared_target=sorted(set(acquired) - set(target)),
        source_target_dates_file_matches_audit_target=declared_target_file == target if declared_target_file is not None else None,
        summary_variant_dates={day: values for day, values in variants.items() if len(values) > 1},
        duplicate_ids=duplicate_ids, orphan_record_directories=orphan_dirs,
        row_results=[dict(id=a['id'], source_accepted=a['source_accepted'], audit_accepted=a['audit_accepted'],
                          issues=a['issues'], diagnostics=a['diagnostics']) for a in audited],
        evidence_files=len(evidence), evidence_bytes=sum(e['bytes'] for e in evidence),
        source_changed_during_audit=source_changed,
        main_database_sha256_before=before_db, main_database_sha256_after=after_db,
        main_database_unchanged=before_db == after_db,
        main_database_ohlc_compared_in_this_audit=True,
        ohlc_comparison=dict(source='current_daily_bars', source_filter="source='em_daily_1' AND adjustment='1' AND symbol='002414.SZ'",
                             mapping_evidence='Local refresh manifest URL fqt=1; build_browser.py and audit_calendar.py map em_daily_1 to 前复权',
                             stored_snapshot_ids=sorted({r['snapshot_id'] for r in qfq_rows}),
                             compared_observations=len({r['observation_id'] for r in ohlc_comparisons}),
                             compared_unique_dates=len({r['trade_date'] for r in ohlc_comparisons}),
                             compared_fields=len(ohlc_comparisons), exact_mismatch_fields=len(qfq_mismatches),
                             over_half_cent_fields=sum(not r['within_0005'] for r in ohlc_comparisons),
                             maximum_absolute_delta=str(max((Decimal(r['absolute_delta']) for r in ohlc_comparisons), default=Decimal('0'))),
                             mismatches=qfq_mismatches, skipped=ohlc_skipped,
                             note='Displayed front-adjusted K OHLC only; does not certify chip adjustment or historical availability'),
        accessibility_evidence_formats={key: sum(a['raw'].get('accessibility_source', 'native_ax_or_legacy_unlabelled') == key for a in audited)
                                        for key in sorted({a['raw'].get('accessibility_source', 'native_ax_or_legacy_unlabelled') for a in audited})},
        accessibility_filename_note='ax.txt is a historical filename; rows marked playwright_dom_snapshot contain that supported DOM snapshot rather than native AX text',
        historical_input_eligible=False, complete_price_bin_days=0,
        chip_price_basis_verified=False, algorithm_and_initialization_verified=False,
        historical_first_availability_verified=False,
        caveats=['Percentage is vendor displayed profit ratio, not forecast probability',
                 'Daily K front adjustment selection does not certify chip price basis',
                 'Complete baseline coverage means saved summaries only',
                 'Retrospective collection does not establish historical point-in-time availability'],
    )
    paths['_manifest.json'].write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    paths['.json'].write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    with paths['_ohlc_comparison.csv'].open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=['observation_id', 'trade_date', 'field', 'display_value', 'main_qfq_value', 'absolute_delta', 'exact_match', 'within_0005'])
        writer.writeheader()
        writer.writerows(ohlc_comparisons)
    with paths['_coverage.csv'].open('w', encoding='utf-8-sig', newline='') as fp:
        fields = ['trade_date', 'coverage_scope', 'main_database_date_present', 'source_accepted_observations', 'audit_accepted_observations',
                  'summary_variant_count', 'complete_price_bins', 'historical_input_eligible']
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for day in target:
            writer.writerow(dict(trade_date=day,
                                 coverage_scope='stored_market_baseline' if day in expected else 'web_observation_extension',
                                 main_database_date_present=day in expected,
                                 source_accepted_observations=sum(a['source_accepted'] and a['raw'].get('date') == day for a in audited),
                                 audit_accepted_observations=sum(a['raw']['date'] == day for a in accepted),
                                 summary_variant_count=len(variants.get(day, [])),
                                 complete_price_bins=0, historical_input_eligible=False))
    if duplicate_ids:
        report['sqlite_creation_skipped'] = 'Duplicate IDs prevent lossless primary keys; preserve report and resolve explicitly'
        paths['.json'].write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    else:
        make_sqlite(paths['.sqlite'], report, audited, evidence, expected, ui_extensions, ohlc_comparisons)
    summary = {key: report[key] for key in ['preview', 'root_index_records', 'audited_records',
               'audit_accepted_observations', 'expected_dates_acquired', 'evidence_files',
               'evidence_bytes', 'main_database_unchanged', 'source_changed_during_audit']}
    summary.update(missing=len(report['missing_expected_dates']),
                   collection_target_acquired=report['collection_target']['acquired_dates'],
                   collection_target_dates=len(target), missing_target=len(report['missing_collection_target_dates']),
                   acquired_web_extension_dates=sorted(set(acquired) & set(ui_extensions)),
                   variant_dates=len(report['summary_variant_dates']),
                   ohlc_exact_mismatch_fields=len(qfq_mismatches),
                   ohlc_over_half_cent_fields=sum(not r['within_0005'] for r in ohlc_comparisons),
                   source_accepted_with_issues=sum(a['source_accepted'] and bool(a['issues']) for a in audited),
                   output_prefix=str(AUDIT_DIR / args.prefix))
    print(json.dumps(summary, ensure_ascii=False))
    if source_changed or before_db != after_db or duplicate_ids or any(a['source_accepted'] and a['issues'] for a in audited):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
