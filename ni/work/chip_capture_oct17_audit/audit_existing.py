"""Offline inventory of existing chip UI evidence; never collect or edit source data."""
from pathlib import Path
import csv
import hashlib
import json
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DB = ROOT / 'outputs/高德红外数据库/高德红外_2023起.sqlite'
FORMAL = ROOT / 'outputs/高德红外数据库/网页筹码核验_20261016'
ROUND2 = ROOT / 'work/chip_repeatability_round2_oct16/ui'
NAMES = ['date', 'profit_ratio_display', 'average_cost_display', 'cost90_display',
         'concentration90_display', 'cost70_display', 'concentration70_display']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    before = digest(DB)
    with sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        expected = [row[0] for row in conn.execute(
            "SELECT DISTINCT trade_date FROM current_daily_bars WHERE source='em_daily_0' ORDER BY trade_date")]
        chip_rows = conn.execute('SELECT COUNT(*) FROM chip_estimates').fetchone()[0]
    first = json.loads((FORMAL / '核验记录.json').read_text())
    second = json.loads((ROUND2 / 'records.json').read_text())
    observations = []
    rejected = []
    for row in first['observations']:
        observations.append(dict(row, evidence_directory=str(FORMAL), evidence_level='synchronized_triplet',
                                 session='round1'))
    excluded_new_work_ids = []
    for row in second['records']:
        if row.get('observed_at_utc', '') >= '2026-10-17':
            excluded_new_work_ids.append(row.get('id'))
            continue
        if not row.get('accepted'):
            rejected.append(row)
            continue
        converted = dict(zip(NAMES, row['values']))
        converted.update(kline_date=row['kline_date'], evidence_stem=row['id'],
                         evidence_directory=str(ROUND2), evidence_level='synchronized_triplet',
                         session='round2', context=row['phase'], historical_input_eligible=False,
                         full_price_bin_data_acquired=False)
        observations.append(converted)
    files = []
    issues = []
    for row in observations:
        for suffix in ('_table.html', '_ax.txt', '.jpg'):
            p = Path(row['evidence_directory']) / (row['evidence_stem'] + suffix)
            if not p.is_file():
                issues.append(dict(kind='missing_evidence_file', path=str(p)))
                continue
            files.append(dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=digest(p)))
        if row['date'] != row['kline_date']:
            issues.append(dict(kind='date_mismatch', row=row))
    dates = sorted({row['date'] for row in observations})
    variants = {}
    for day in dates:
        signatures = {}
        for row in observations:
            if row['date'] != day:
                continue
            signature = tuple(row[name] for name in NAMES[1:])
            signatures.setdefault(signature, []).append(row['evidence_stem'])
        variants[day] = [dict(values=dict(zip(NAMES[1:], key)), evidence_stems=value)
                         for key, value in signatures.items()]
    after = digest(DB)
    audit = dict(
        scope='Existing local evidence only; no browser use, networking, imported external code, or main database mutation',
        reviewed_client_date='2026-10-17', source_url=first['source_url'],
        baseline=dict(symbol='002414.SZ', dates=len(expected), start=min(expected), end=max(expected),
                      note='This is the stored market baseline, not verification through 2026-10-16 or every exchange session'),
        synchronized_triplet_snapshots=len(observations), synchronized_triplet_unique_dates=dates,
        missing_synchronized_triplet_dates=[day for day in expected if day not in dates],
        summary_variants=variants, round2_rejected_attempts=rejected,
        paused_checkpoint='Last paused action expanded earlier visible range to about 2022-09; June20 had not yet been sampled in that window at the start of this inventory.',
        inventory_cutoff='Only observations saved before the Oct17 resumption; new root collection is excluded from this baseline inventory',
        excluded_new_work_ids=excluded_new_work_ids, complete_price_bin_days=0,
        main_chip_estimates_rows=chip_rows, historical_input_eligible=False,
        existing_scripts=[
            dict(path='work/chip_history_root_oct16/archive_evidence.py', reusable='HTML/AX date synchronization, triplet copy/hash, CSV writer',
                 caveat='Hard-coded four cases and destination; do not run unchanged for bulk collection'),
            dict(path='outputs/高德红外数据库/validate_chip_export.py', reusable='Offline vendor original JSON validation for price-bin units, dates, duplicates and sums',
                 caveat='Only documented cyq_chips/cyq_perf schema; not a website collector or evidence that any export was obtained')],
        evidence_files=files, issues=issues, database_sha256_before=before, database_sha256_after=after,
        database_unchanged=before == after,
        weak_summary_only_dates=['2026-10-13', '2026-10-14', '2026-10-15'],
        weak_summary_note='Manual rendered UI transcriptions; no locally saved synchronized HTML+AX+screenshot triplet. Keep distinct from strict coverage.',
    )
    (OUT / 'existing_inventory.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    with (OUT / 'existing_date_coverage.csv').open('w', encoding='utf-8-sig', newline='') as fp:
        fields = ['trade_date', 'synchronized_triplet_count', 'summary_variant_count', 'complete_price_bins', 'historical_input_eligible']
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        for day in expected:
            w.writerow(dict(trade_date=day,
                            synchronized_triplet_count=sum(row['date'] == day for row in observations),
                            summary_variant_count=len(variants.get(day, [])), complete_price_bins=0,
                            historical_input_eligible=False))
    print(json.dumps(dict(snapshots=len(observations), unique_dates=dates, missing=len(audit['missing_synchronized_triplet_dates']),
                          june20_variants=len(variants['2023-06-20']), full_bins=0,
                          database_unchanged=before == after, issues=issues), ensure_ascii=False))


if __name__ == '__main__':
    main()
