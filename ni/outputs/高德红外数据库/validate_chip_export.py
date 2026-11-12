"""Validate authorized chip JSON exports offline; never fetch, predict or fill gaps."""
import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = 'chip-export-audit-v1'
QUANTILES = ['cost_5pct', 'cost_15pct', 'cost_50pct', 'cost_85pct', 'cost_95pct']


def day(value):
    value = str(value)
    if len(value) == 8 and value.isdigit():
        value = value[:4] + '-' + value[4:6] + '-' + value[6:]
    if len(value) != 10:
        raise ValueError('date must be YYYYMMDD or YYYY-MM-DD')
    return date.fromisoformat(value).isoformat()


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('missing or boolean numeric field')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid numeric field') from exc
    if not result.is_finite():
        raise ValueError('non-finite numeric field')
    return result


def unpack(payload):
    if not isinstance(payload, dict) or payload.get('code') != 0:
        raise ValueError('requires successful original API response, code=0')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise ValueError('missing response data')
    fields, items = data.get('fields'), data.get('items')
    if not isinstance(fields, list) or not isinstance(items, list) or not fields:
        raise ValueError('missing fields/items arrays')
    if any(not isinstance(f, str) for f in fields) or len(set(fields)) != len(fields):
        raise ValueError('ambiguous field names')
    if any(not isinstance(r, list) or len(r) != len(fields) for r in items):
        raise ValueError('row width mismatch')
    return [dict(zip(fields, r)) for r in items]


def validate(payload, metadata, expected_days, coverage_start=None, coverage_end=None):
    issues, warnings, groups = [], [], defaultdict(list)
    def fail(kind, detail):
        issues.append(dict(kind=kind, detail=detail))
    interface = metadata.get('interface')
    if interface not in ('cyq_chips', 'cyq_perf'):
        fail('interface', 'Only documented cyq_chips/cyq_perf schema supported')
    if metadata.get('symbol') != '002414.SZ':
        fail('symbol_metadata', 'Expected 002414.SZ')
    if metadata.get('evidence_type') != 'provider_cost_distribution_estimate':
        fail('evidence_type', 'Must identify provider estimate, not real account inventory')
    if not metadata.get('source_url') or not metadata.get('retrieved_at'):
        fail('provenance', 'Source URL and actual retrieval time required')
    try:
        dt = datetime.fromisoformat(metadata.get('retrieved_at', '').replace('Z', '+00:00'))
        if dt.tzinfo is None: raise ValueError('timezone missing')
    except (ValueError, TypeError):
        fail('retrieval_time', 'Actual timezone-aware retrieval time required')
    try:
        start, end = day(metadata['requested_start']), day(metadata['requested_end'])
        if start > end: raise ValueError('reversed interval')
    except (ValueError, KeyError, TypeError):
        fail('request_interval', 'Valid requested interval required')
        start, end = '2023-01-01', '2026-10-13'
    known_start = coverage_start or min(expected_days, default=None)
    known_end = coverage_end or max(expected_days, default=None)
    if not expected_days or not known_start or not known_end:
        fail('baseline_unavailable', 'No verified date baseline')
    elif start < known_start or end > known_end:
        fail('outside_baseline_coverage', dict(requested_start=start, requested_end=end,
              known_start=known_start, known_end=known_end))
    try:
        rows = unpack(payload)
    except ValueError as exc:
        fail('response', str(exc)); rows = []
    if not rows: fail('empty', 'Empty result does not prove no historical data')
    if len(rows) >= 6000:
        fail('possible_truncation', 'At documented request cap; shorten request interval and recheck')
    if interface == 'cyq_chips' and metadata.get('percent_unit') != 'percentage_points':
        fail('percent_unit', 'Official percent column uses percentage points, not fractions')
    if metadata.get('price_unit') != 'CNY_per_share':
        fail('price_unit', 'Explicit CNY_per_share declaration required before comparison')
    try:
        tolerance = number(metadata.get('sum_tolerance_percentage_points', '0.05'))
        if not Decimal('0') <= tolerance <= Decimal('0.10'):
            raise ValueError('tolerance outside reviewed range')
    except ValueError:
        fail('sum_tolerance', 'Tolerance must be from 0 to 0.10 percentage points')
        tolerance = Decimal('0.05')
    seen = set()
    for index, row in enumerate(rows):
        try:
            d = day(row['trade_date'])
            if row.get('ts_code') != '002414.SZ': raise ValueError('wrong stock')
            if not start <= d <= end: raise ValueError('outside request interval')
            if d not in expected_days: raise ValueError('not an expected stock trading date')
            if interface == 'cyq_chips':
                price, pct = number(row['price']), number(row['percent'])
                if price <= 0 or not Decimal('0') <= pct <= Decimal('100'):
                    raise ValueError('price/percent range')
                key = (d, price)
            elif interface == 'cyq_perf':
                nums = [number(row[k]) for k in QUANTILES]
                low, high, avg = (number(row[k]) for k in ('his_low', 'his_high', 'weight_avg'))
                if low <= 0 or high < low or nums != sorted(nums) or not low <= nums[0] <= nums[-1] <= high or not low <= avg <= high:
                    raise ValueError('cost ordering/range invalid')
                # Documentation calls this "winner_rate" without defining its unit/meaning.
                # Do not silently reinterpret it as a strategy win probability.
                number(row['winner_rate'])
                key = (d,)
            else:
                raise ValueError('unsupported interface')
            if key in seen: raise ValueError('duplicate date or price bin; raw row retained')
            seen.add(key); groups[d].append(row)
        except (ValueError, KeyError, TypeError) as exc:
            fail('row', dict(index=index, reason=str(exc)))
    totals = {}
    if interface == 'cyq_chips':
        for d, values in groups.items():
            total = sum((number(r['percent']) for r in values), Decimal('0'))
            totals[d] = str(total)
            if abs(total - Decimal('100')) > tolerance:
                fail('distribution_sum', dict(date=d, sum_percentage_points=str(total)))
    wanted = {d for d in expected_days if start <= d <= end}
    missing = sorted(wanted - set(groups))
    if missing: fail('missing_dates', missing)
    price_basis = metadata.get('price_basis', 'unknown')
    if price_basis not in ('unadjusted', 'qfq', 'hfq') or not metadata.get('price_basis_evidence'):
        warnings.append('Price basis is not certified; block chip/price pattern comparisons')
    elif price_basis in ('qfq', 'hfq') and not metadata.get('adjustment_vintage'):
        warnings.append('Adjusted price vintage missing; retrospective revisions not certified')
    if not metadata.get('algorithm_version'):
        warnings.append('Provider algorithm version is unknown')
    warnings.append('Historical first availability/revisions require separate evidence; historical input remains disabled')
    if interface == 'cyq_perf':
        warnings.append('winner_rate precision/meaning/unit unverified; not strategy win probability')
    return dict(audit_version=VERSION, interface=interface, raw_rows=len(rows),
                unique_dates=len(groups), expected_dates=len(wanted), missing_dates=missing,
                distribution_sums=totals, issues=issues, warnings=warnings,
                structural_checks_passed=not issues, historical_input_eligible=False,
                baseline_coverage=dict(start=known_start,end=known_end),
                price_basis_declared=price_basis in ('unadjusted','qfq','hfq'),
                chip_price_alignment_ready=False,
                scope='Offline export validation only; no supplier data acquired by this script, no signal or performance calculation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--metadata', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--database', type=Path, default=ROOT/'高德红外_2023起.sqlite')
    args = parser.parse_args()
    if args.output.resolve() in (args.input.resolve(), args.metadata.resolve(), args.database.resolve()):
        parser.error('output must not overwrite an input or database')
    # No network, credentials, or database writes. File paths must be explicitly supplied.
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as c:
        expected = {r[0] for r in c.execute("SELECT trade_date FROM current_daily_bars WHERE source='em_daily_0'")}
        known_start, known_end = c.execute('SELECT MIN(trade_date),MAX(trade_date) FROM trading_calendar').fetchone()
    raw = args.input.read_bytes()
    metadata_bytes = args.metadata.read_bytes()
    report = validate(json.loads(raw), json.loads(metadata_bytes), expected, known_start, known_end)
    report.update(input_sha256=hashlib.sha256(raw).hexdigest(),
                  metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest())
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('raw_rows', 'unique_dates', 'expected_dates', 'structural_checks_passed')},ensure_ascii=False))
    if report['issues']: raise SystemExit(1)


if __name__ == '__main__': main()
