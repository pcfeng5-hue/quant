"""Versioned public research data collection; no analysis or broker access."""
import concurrent.futures
import hashlib
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START, END = '2023-01-01', '2026-10-13'
RAW = ROOT / 'raw'
DB = ROOT / '高德红外_2023起.sqlite'


def url(base, params):
    return base + '?' + urllib.parse.urlencode(params)


def fetch(job):
    name, kind, address = job
    now = datetime.now(timezone.utc).isoformat()
    try:
        request = urllib.request.Request(address, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
        data = json.loads(payload)
        digest = hashlib.sha256(payload).hexdigest()
        target = RAW / (name + '_' + digest[:16] + '.json')
        target.write_bytes(payload)
        return dict(name=name, kind=kind, url=address, retrieved_at=now,
                    sha256=digest, raw_path=str(target.relative_to(ROOT)), data=data, error=None)
    except Exception as exc:
        return dict(name=name, kind=kind, url=address, retrieved_at=now,
                    error=type(exc).__name__ + ': ' + str(exc))


def jobs():
    out = []
    for adj in (0, 1, 2):
        p = dict(secid='0.002414', klt=101, fqt=adj, beg='20230101', end='20261013',
                 fields1='f1,f2,f3,f4,f5,f6', fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
        out.append((f'em_daily_{adj}', 'daily_em', url('https://push2his.eastmoney.com/api/qt/stock/kline/get', p)))
    for year in range(2023, 2027):
        end = min(f'{year}-12-31', END)
        address = url('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                      dict(param=f'sz002414,day,{year}-01-01,{end},640,'))
        out.append((f'tencent_daily_{year}', 'daily_tencent', address))
    for code in ('1.000001', '0.399001'):
        p = dict(secid=code, klt=101, fqt=0, beg='20230101', end='20261013',
                 fields1='f1,f2,f3,f4,f5,f6', fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
        out.append(('index_'+code, 'index_em', url('https://push2his.eastmoney.com/api/qt/stock/kline/get', p)))
    # Fields are preserved as provider records. No interpretation as actual investor identity.
    specs = [
        ('financial_main', 'RPT_F10_FINANCE_MAINFINADATA', 'SECUCODE', 'REPORT_DATE', 'finance'),
        ('balance_sheet', 'RPT_DMSK_FN_BALANCE', 'SECUCODE', 'REPORT_DATE', 'finance'),
        ('income_statement', 'RPT_DMSK_FN_INCOME', 'SECUCODE', 'REPORT_DATE', 'finance'),
        ('cashflow_statement', 'RPT_DMSK_FN_CASHFLOW', 'SECUCODE', 'REPORT_DATE', 'finance'),
        ('margin', 'RPTA_WEB_RZRQ_GGMX', 'SCODE', 'DATE', 'market_record'),
        ('block_trade', 'RPT_DATA_BLOCKTRADE', 'SECURITY_CODE', 'TRADE_DATE', 'market_record'),
        ('billboard', 'RPT_DAILYBILLBOARD_DETAILSNEW', 'SECURITY_CODE', 'TRADE_DATE', 'market_record'),
        ('institution_seats', 'RPT_ORGANIZATION_TRADE_DETAILS', 'SECURITY_CODE', 'TRADE_DATE', 'market_record'),
        ('holder_count', 'RPT_HOLDERNUM_DET', 'SECURITY_CODE', 'HOLD_NOTICE_DATE', 'disclosure'),
        ('dividends', 'RPT_SHAREBONUS_DET', 'SECURITY_CODE', 'NOTICE_DATE', 'disclosure'),
        ('unlock', 'RPT_LIFT_STOCK', 'SECURITY_CODE', 'FREE_DATE', 'market_record'),
        ('top10_float', 'RPT_F10_EH_FREEHOLDERS', 'SECUCODE', 'NOTICE_DATE', 'disclosure'),
    ]
    for name, report, key, datefield, kind in specs:
        value = '002414.SZ' if key == 'SECUCODE' else '002414'
        filterdate = 'NOTICE_DATE' if kind == 'finance' else datefield
        filt = f'({key}="{value}")({filterdate}>=\'{START}\')({filterdate}<=\'{END}\')'
        columns = 'ALL'
        if name == 'billboard':
            columns = 'SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,TRADE_DATE,EXPLAIN,CLOSE_PRICE,CHANGE_RATE,BILLBOARD_NET_AMT,BILLBOARD_BUY_AMT,BILLBOARD_SELL_AMT,BILLBOARD_DEAL_AMT,ACCUM_AMOUNT,DEAL_NET_RATIO,DEAL_AMOUNT_RATIO,TURNOVERRATE,FREE_MARKET_CAP,EXPLANATION,SECURITY_TYPE_CODE'
        p = dict(reportName=report, columns=columns, filter=filt, pageSize=500,
                 pageNumber=1, sortColumns=datefield, sortTypes=-1, source='WEB', client='WEB')
        out.append((name, kind, url('https://datacenter-web.eastmoney.com/api/data/v1/get', p)))
    p = dict(stock_list='002414', page_size=100, page_index=1, ann_type='A',
             begin_time=START, end_time=END)
    out.append(('announcements', 'announcements', url('https://np-anotice-stock.eastmoney.com/api/security/ann', p)))
    p = dict(secid='0.002414', klt=101, lmt=0,
             fields1='f1,f2,f3,f7', fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63')
    out.append(('fund_flow_proxy', 'flow', url('https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get', p)))
    return out


def record_date(record):
    for key in ('NOTICE_DATE', 'HOLD_NOTICE_DATE', 'PUBLISH_DATE', 'PUBLICATION_DATE', 'notice_date', 'TRADE_DATE', 'DATE', 'FREE_DATE', 'REPORT_DATE', 'END_DATE'):
        value = record.get(key)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10], key
    return None, None


def store_result(con, result):
    data = result.get('data')
    error = result['error']
    snapshot_id = result['name'] + ':' + result.get('sha256', result['retrieved_at'])
    accepted, rejected = 0, 0
    dates = []
    if data is not None:
        kind = result['kind']
        if kind in ('daily_em', 'index_em'):
            records = (data.get('data') or {}).get('klines') or []
        elif kind == 'daily_tencent':
            records = (data.get('data', {}).get('sz002414') or {}).get('day') or []
        elif kind == 'announcements':
            records = (data.get('data') or {}).get('list') or []
        elif kind == 'flow':
            records = (data.get('data') or {}).get('klines') or []
        else:
            records = (data.get('result') or {}).get('data') or []
        if not records:
            error = 'EMPTY_OR_PROVIDER_ERROR: ' + str(data.get('message') or data.get('msg') or data.get('code') or data.get('rc'))
        for row in records:
            if kind in ('daily_em', 'index_em', 'daily_tencent'):
                a = row.split(',') if isinstance(row, str) else row
                day = a[0]
                if not START <= day <= END:
                    rejected += 1; continue
                try:
                    o, c, h, l, vol = map(float, a[1:6])
                    if not (0 < l <= min(o, c) <= max(o, c) <= h) or vol < 0:
                        raise ValueError('OHLC/volume invalid')
                    amount = float(a[6]) if kind != 'daily_tencent' else None
                    turnover = float(a[10]) if kind != 'daily_tencent' else None
                    if (amount is not None and amount < 0) or (turnover is not None and turnover < 0):
                        raise ValueError('negative amount/turnover')
                    symbol = '002414.SZ' if kind != 'index_em' else result['name'][6:]
                    adjustment = result['name'].rsplit('_', 1)[-1] if kind == 'daily_em' else '0'
                    con.execute('INSERT OR IGNORE INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                (snapshot_id,symbol,result['name'],adjustment,day,o,h,l,c,vol,amount,turnover,'provider_hands','provider_pct' if turnover is not None else None))
                except (ValueError, IndexError, TypeError) as exc:
                    rejected += 1
                    con.execute('INSERT INTO quality_issues VALUES (?,?,?)', (snapshot_id,str(row),str(exc)))
                    continue
            else:
                if isinstance(row, str):
                    day = row.split(',')[0]; field = 'provider_day'
                else:
                    day, field = record_date(row)
                if day is not None and not START <= day <= END:
                    rejected += 1; continue
                # Preserve full source fields, including unknown publication times.
                encoded = json.dumps(row, ensure_ascii=False, sort_keys=True)
                rowhash = hashlib.sha256(encoded.encode()).hexdigest()
                publication = None
                if isinstance(row, dict):
                    publication = row.get('NOTICE_DATE') or row.get('HOLD_NOTICE_DATE') or row.get('PUBLISH_DATE') or row.get('notice_date')
                con.execute('INSERT OR IGNORE INTO source_records VALUES (?,?,?,?,?,?,?,?,?)',
                            (snapshot_id,result['name'],rowhash,day,field,publication,
                             'proxy' if kind=='flow' else 'provider_record', 'unverified_historical_availability',encoded))
            accepted += 1
            if day: dates.append(day)
    pages = (data.get('result') or {}).get('pages', 1) if isinstance(data, dict) else 0
    result.update(snapshot_id=snapshot_id, accepted=accepted, rejected=rejected,
                  min_date=min(dates) if dates else None, max_date=max(dates) if dates else None,
                  error=error, provider_pages=pages)
    con.execute('INSERT OR IGNORE INTO source_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (snapshot_id,result['name'],result['url'],result['retrieved_at'],result.get('sha256'),
                 result.get('raw_path'),accepted,rejected,result['min_date'],result['max_date'],error))


def main():
    RAW.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript('''
      CREATE TABLE IF NOT EXISTS source_snapshots(snapshot_id TEXT PRIMARY KEY, dataset TEXT, url TEXT, retrieved_at TEXT, sha256 TEXT, raw_path TEXT, accepted INTEGER, rejected INTEGER, min_date TEXT, max_date TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS daily_bars(snapshot_id TEXT, symbol TEXT, source TEXT, adjustment TEXT, trade_date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, turnover REAL, volume_unit TEXT, turnover_unit TEXT, PRIMARY KEY(snapshot_id,symbol,trade_date));
      CREATE TABLE IF NOT EXISTS source_records(snapshot_id TEXT,dataset TEXT,row_hash TEXT,reference_date TEXT,date_field TEXT,publication_time TEXT,evidence_type TEXT,availability_status TEXT,payload_json TEXT,PRIMARY KEY(snapshot_id,row_hash));
      CREATE TABLE IF NOT EXISTS quality_issues(snapshot_id TEXT, raw_row TEXT, reason TEXT);
      CREATE TABLE IF NOT EXISTS coverage_gaps(dataset TEXT PRIMARY KEY, status TEXT, explanation TEXT);
      CREATE TABLE IF NOT EXISTS chip_estimates(trade_date TEXT, source TEXT, algorithm_version TEXT, payload_json TEXT);
      CREATE VIEW IF NOT EXISTS latest_successful_snapshots AS SELECT s.* FROM source_snapshots s WHERE error IS NULL AND retrieved_at=(SELECT MAX(t.retrieved_at) FROM source_snapshots t WHERE t.dataset=s.dataset AND t.error IS NULL);
      CREATE VIEW IF NOT EXISTS current_daily_bars AS SELECT d.* FROM daily_bars d JOIN latest_successful_snapshots s USING(snapshot_id);
      CREATE VIEW IF NOT EXISTS current_source_records AS SELECT r.* FROM source_records r JOIN latest_successful_snapshots s USING(snapshot_id);
    ''')
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(fetch, jobs()):
            store_result(con, result)
            results.append({k:v for k,v in result.items() if k != 'data'})
            print(result['name'], result['accepted'], result['min_date'], result['max_date'], result['error'], flush=True)
    # Follow pagination explicitly; a safety cap is reported, never called complete.
    for first in list(results):
        pages = first['provider_pages'] or 1
        if first['kind'] == 'announcements':
            raw = json.loads((ROOT / first['raw_path']).read_text()) if first.get('raw_path') else {}
            pages = ((raw.get('data') or {}).get('total_hits', 0) + 99)//100
        for page in range(2, min(pages, 30)+1):
            parts = urllib.parse.urlsplit(first['url'])
            params = dict(urllib.parse.parse_qsl(parts.query))
            params['page_index' if first['kind']=='announcements' else 'pageNumber'] = str(page)
            address = urllib.parse.urlunsplit((parts.scheme,parts.netloc,parts.path,urllib.parse.urlencode(params),''))
            r = fetch((first['name']+'_page'+str(page),first['kind'],address))
            store_result(con,r); results.append({k:v for k,v in r.items() if k!='data'})
        if pages > 30:
            con.execute('INSERT OR REPLACE INTO coverage_gaps VALUES (?,?,?)',
                        (first['name'],'partial',f'provider_pages={pages}; only first 30 fetched'))
    gaps = [
      ('chip_history','missing','No verified 2023-to-cutoff chip source. AKShare stock_cyq_em computes estimates and exposes recent 90 days; do not fabricate full observed history.'),
      ('tick_level2','missing','Historical order/tick data authorization and cost unconfirmed.'),
      ('news_policy_archive','pending','Complete deduplicated historical archive and first-public timestamps not acquired.'),
      ('industry_theme_history','pending','Point-in-time classification and industry history not acquired.'),
      ('fund_holder_history','partial','Top ten float holders collected where disclosed; not complete fund holdings and not real-time institutional trades.'),
      ('corporate_actions_float_shares','partial','Dividend/unlock records collected if returned; historical float-share series not acquired; adjusted prices are retrospective provider snapshots.'),
      ('trading_calendar_status','pending','Trading-day coverage, historical suspensions and risk-warning status not yet verified.'),
      ('technical_indicators','deferred','User requests raw statistical database first; MACD/KDJ/MA and signal analysis deferred.'),
    ]
    con.executemany('INSERT OR REPLACE INTO coverage_gaps VALUES (?,?,?)',gaps)
    con.commit()
    integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
    counts = dict(con.execute('SELECT dataset,COUNT(*) FROM current_source_records GROUP BY dataset'))
    coverage = list(con.execute('SELECT source,adjustment,COUNT(*),MIN(trade_date),MAX(trade_date) FROM current_daily_bars GROUP BY source,adjustment'))
    out = dict(requested_start=START,requested_end=END,integrity_check=integrity,
               daily_coverage=coverage,record_counts=counts,sources=results,gaps=gaps,
               note='Source availability is not certified. Retrieval timestamps are actual; historical publication and complete coverage remain to be verified. No trading analysis.')
    (ROOT/'采集清单与覆盖.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    con.close()


if __name__ == '__main__': main()
