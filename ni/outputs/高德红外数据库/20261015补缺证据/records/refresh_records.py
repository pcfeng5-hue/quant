"""Read public research feeds into isolated files; never mutate the main database."""
import concurrent.futures
import hashlib
import json
import sqlite3
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
DB = PROJECT / 'outputs/高德红外数据库/高德红外_2023起.sqlite'
START, END = '2023-01-01', '2026-10-15'
NAMES = ('margin', 'block_trade', 'billboard', 'institution_seats', 'fund_flow_proxy')


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def row_day(row):
    if isinstance(row, str):
        return row.split(',')[0]
    for key in ('TRADE_DATE', 'DATE'):
        value = row.get(key)
        if value:
            return str(value)[:10]
    return None


def rows_of(payload, kind):
    if kind == 'flow':
        return (payload.get('data') or {}).get('klines') or []
    return (payload.get('result') or {}).get('data') or []


def fetch(job):
    name, kind, address = job
    result = dict(name=name, kind=kind, url=address, method='GET',
                  parameters=dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(address).query)),
                  retrieved_at=datetime.now(timezone.utc).isoformat())
    try:
        request = urllib.request.Request(address, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(25_000_001)
        if len(raw) > 25_000_000:
            raise ValueError('response exceeded 25 MB limit')
        digest = hashlib.sha256(raw).hexdigest()
        path = ROOT / 'raw' / f'{name}_{digest[:16]}.json'
        path.write_bytes(raw)
        payload = json.loads(raw)
        rows = rows_of(payload, kind)
        accepted = [r for r in rows if row_day(r) and START <= row_day(r) <= END]
        dates = [row_day(r) for r in accepted]
        result.update(sha256=digest, raw_path=str(path.relative_to(PROJECT)),
                      raw_path_absolute=str(path), bytes=len(raw),
                      accepted=len(accepted), rejected=len(rows)-len(accepted),
                      min_date=min(dates) if dates else None,
                      max_date=max(dates) if dates else None,
                      provider_pages=(payload.get('result') or {}).get('pages', 1),
                      provider_count=(payload.get('result') or {}).get('count'),
                      error=None if rows else f"EMPTY_OR_PROVIDER_ERROR: {payload.get('message') or payload.get('msg') or payload.get('rc') or payload.get('code')}")
    except Exception as exc:
        result.update(error=f'{type(exc).__name__}: {exc}')
    print(name, result.get('accepted'), result.get('min_date'), result.get('max_date'), result['error'], flush=True)
    return result


def main():
    (ROOT / 'raw').mkdir(exist_ok=True)
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    jobs, old_snapshots = [], []
    for name in NAMES:
        row = con.execute('SELECT dataset,url,snapshot_id,retrieved_at,raw_path FROM latest_successful_snapshots WHERE dataset=?', (name,)).fetchone()
        if not row:
            raise ValueError(f'No previous successful snapshot for {name}')
        old_snapshots.append(dict(zip(('dataset','url','snapshot_id','retrieved_at','raw_path'), row)))
        parts = urllib.parse.urlsplit(row[1])
        params = dict(urllib.parse.parse_qsl(parts.query))
        if 'filter' in params:
            params['filter'] = params['filter'].replace("2026-10-13", END)
        address = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params), ''))
        jobs.append((name, 'flow' if name == 'fund_flow_proxy' else 'market_record', address))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch, jobs))
    for first in list(results):
        if first['error'] or first['kind'] == 'flow':
            continue
        pages = int(first.get('provider_pages') or 1)
        for page in range(2, min(pages, 30) + 1):
            parts = urllib.parse.urlsplit(first['url'])
            params = dict(urllib.parse.parse_qsl(parts.query))
            params['pageNumber'] = str(page)
            address = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params), ''))
            results.append(fetch((first['name'] + '_page' + str(page), first['kind'], address)))
    reports = []
    for base in NAMES:
        prefix = base + '_page'
        previous = con.execute('SELECT dataset,reference_date,payload_json FROM current_source_records WHERE dataset=? OR dataset LIKE ?', (base, prefix+'%')).fetchall()
        old_rows = [json.loads(r[2]) for r in previous]
        snapshots = [r for r in results if r['name'] == base or r['name'].startswith(prefix)]
        new_rows = []
        for snap in snapshots:
            if snap['error']:
                continue
            payload = json.loads(Path(snap['raw_path_absolute']).read_text())
            new_rows.extend(r for r in rows_of(payload, snap['kind']) if row_day(r) and START <= row_day(r) <= END)
        old_map, new_map = defaultdict(list), defaultdict(list)
        for row in old_rows:
            old_map[row_day(row)].append(row)
        for row in new_rows:
            new_map[row_day(row)].append(row)
        old_dates, new_dates = set(old_map), set(new_map)
        revised = []
        for date in sorted(old_dates & new_dates):
            a, b = Counter(map(canon, old_map[date])), Counter(map(canon, new_map[date]))
            if a != b:
                item = dict(date=date, old_rows=len(old_map[date]), new_rows=len(new_map[date]),
                            removed_rows=[json.loads(s) for s in (a-b).elements()],
                            added_rows=[json.loads(s) for s in (b-a).elements()])
                if len(old_map[date]) == len(new_map[date]) == 1 and isinstance(old_map[date][0], dict):
                    old, new = old_map[date][0], new_map[date][0]
                    item['changed_fields'] = {key:dict(old=old.get(key),new=new.get(key)) for key in sorted(set(old)|set(new)) if old.get(key) != new.get(key)}
                revised.append(item)
        first = next(s for s in snapshots if s['name'] == base)
        expected_pages = int(first.get('provider_pages') or 1)
        report = dict(dataset=base, old_count=len(old_rows), old_min_date=min(old_dates) if old_dates else None,
                      old_max_date=max(old_dates) if old_dates else None,
                      new_count=len(new_rows), new_min_date=min(new_dates) if new_dates else None,
                      new_max_date=max(new_dates) if new_dates else None,
                      new_dates=sorted(new_dates-old_dates), old_dates_not_in_new_snapshot=sorted(old_dates-new_dates),
                      changed_overlap_dates=len(revised), revisions_path=f'work/refresh_oct15_records/{base}_revisions.json',
                      new_date_rows_path=f'work/refresh_oct15_records/{base}_new_dates.json',
                      complete_provider_pagination=(len(snapshots) == expected_pages and all(not s['error'] for s in snapshots) and expected_pages <= 30),
                      provider_pages=expected_pages, fetched_pages=len(snapshots))
        if base == 'fund_flow_proxy':
            report['interpretation'] = 'Rolling provider window. Preserve all previously acquired rows; no historical reconstruction. Provider price previously matched current qfq snapshot, not certified original basis. Flow proxy does not identify institutions.'
        save(f'{base}_revisions.json', revised)
        save(f'{base}_new_dates.json', [r for r in new_rows if row_day(r) in new_dates-old_dates])
        reports.append(report)
    manifest = dict(requested_start=START, requested_end=END,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    database_mode='read_only_no_main_database_changes', sources=results,
                    comparisons=reports, previous_base_snapshots=old_snapshots,
                    restrictions=['No broker access, no indicator or return analysis.', 'Public research records remain unverified for first historical availability.', 'Old and new rolling flow windows must be retained as separate snapshots.', 'Large trades and flow-size proxies do not certify investor identity.'])
    save('manifest.json', manifest)
    con.close()
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
