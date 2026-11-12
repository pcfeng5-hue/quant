"""Public disclosure/capital supplements, preserving raw responses and date precision."""
import hashlib
import json
import math
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START, END = '2023-01-01', '2026-10-13'
SHANGHAI = timezone(timedelta(hours=8))


def request(address, params=None, method='GET'):
    encoded = urllib.parse.urlencode(params or {})
    target = address + ('?' + encoded if method == 'GET' and encoded else '')
    req = urllib.request.Request(target, data=encoded.encode() if method == 'POST' else None,
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/',
                 'Content-Type': 'application/x-www-form-urlencoded'}, method=method)
    now = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    return raw, json.loads(raw), now, target


def store(c, name, address, params, method, result, records, date_key):
    raw, data, now, target = result
    digest = hashlib.sha256(raw).hexdigest()
    path = ROOT/'raw'/(name+'_'+digest[:16]+'.json')
    path.write_bytes(raw)
    sid = name+':'+digest
    accepted, rejected, dates = 0, 0, []
    for row in records:
        if date_key == 'announcementTime':
            dt = datetime.fromtimestamp(row[date_key]/1000, SHANGHAI)
            day, publication = dt.date().isoformat(), dt.isoformat()
            availability = 'provider_announcement_date_not_first_public_timestamp'
        else:
            day = (row.get(date_key) or '')[:10]
            publication = None
            availability = 'unverified_historical_availability'
        encoded = json.dumps(row, ensure_ascii=False, sort_keys=True)
        rh = hashlib.sha256(encoded.encode()).hexdigest()
        if name.startswith('capital_structure') and day < START:
            c.execute('INSERT OR IGNORE INTO capital_baseline_candidates VALUES (?,?,?,?,?)',
                      (sid,rh,day,'pre_start_reference_not_certified_daily_history',encoded))
        if not day or not START <= day <= END:
            rejected += 1
            continue
        c.execute('INSERT OR IGNORE INTO source_records VALUES (?,?,?,?,?,?,?,?,?)',
                  (sid,name,rh,day,date_key,publication,'provider_record',availability,encoded))
        accepted += 1; dates.append(day)
    # Empty success is kept distinguishable from failure, but does not certify absence.
    provider_success = data.get('success', True)
    error = None if records and provider_success else 'EMPTY_OR_PROVIDER_ERROR: '+str(data.get('message'))
    c.execute('INSERT OR IGNORE INTO source_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)',
              (sid,name,target,now,digest,str(path.relative_to(ROOT)),accepted,rejected,
               min(dates) if dates else None,max(dates) if dates else None,error))
    c.execute('INSERT OR IGNORE INTO source_requests VALUES (?,?,?)',
              (sid,method,json.dumps(params,ensure_ascii=False,sort_keys=True)))
    print(name,accepted,'provider rows',len(records),error,flush=True)
    return dict(dataset=name,snapshot_id=sid,accepted=accepted,rejected=rejected,
                provider_rows=len(records),error=error)


def main():
    c = sqlite3.connect(ROOT/'高德红外_2023起.sqlite')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS source_requests(snapshot_id TEXT PRIMARY KEY,method TEXT,parameters_json TEXT);
      CREATE TABLE IF NOT EXISTS capital_baseline_candidates(snapshot_id TEXT,row_hash TEXT,reference_date TEXT,status TEXT,payload_json TEXT,PRIMARY KEY(snapshot_id,row_hash));
    ''')
    results=[]
    # Exact issuer orgId comes from the official public security directory.
    res=request('https://www.cninfo.com.cn/new/data/szse_stock.json')
    stock=[r for r in res[1]['stockList'] if r['code']=='002414'][0]
    raw_path=ROOT/'raw'/('cninfo_security_directory_'+hashlib.sha256(res[0]).hexdigest()[:16]+'.json')
    raw_path.write_bytes(res[0])
    address='https://www.cninfo.com.cn/new/hisAnnouncement/query'
    form=dict(pageNum=1,pageSize=30,column='szse',tabName='fulltext',stock='002414,'+stock['orgId'],
              searchkey='',secid='',plate='',category='',trade='',seDate=START+'~'+END,
              sortName='',sortType='',isHLtitle='true')
    first=request(address,form,'POST')
    pages=math.ceil(first[1].get('totalAnnouncement',0)/int(form['pageSize']))
    if pages > 30: raise ValueError('CNINFO page cap exceeded; incomplete, do not certify')
    for page in range(1,pages+1):
        form['pageNum']=page
        res=first if page==1 else request(address,form,'POST')
        results.append(store(c,'cninfo_announcements_page'+str(page),address,dict(form),'POST',
                             res,res[1].get('announcements') or [],'announcementTime'))
    results.append(dict(cninfo_reported_total=first[1].get('totalAnnouncement'),requested_pages=pages,
                        issuer=stock,security_directory_path=str(raw_path.relative_to(ROOT))))
    p=dict(reportName='RPT_F10_EH_EQUITY',columns='ALL',filter='(SECUCODE="002414.SZ")',
           pageNumber=1,pageSize=500,sortTypes=-1,sortColumns='END_DATE',source='HSF10',client='PC')
    address='https://datacenter.eastmoney.com/securities/api/data/v1/get'
    first=request(address,p)
    pages=(first[1].get('result') or {}).get('pages') or 1
    if pages>30: raise ValueError('capital page cap exceeded')
    for page in range(1,pages+1):
        p['pageNumber']=page
        res=first if page==1 else request(address,p)
        name='capital_structure' if page==1 else 'capital_structure_page'+str(page)
        results.append(store(c,name,address,dict(p),'GET',res,(res[1].get('result') or {}).get('data') or [],'END_DATE'))
    p=dict(reportName='RPT_CUSTOM_SUSPEND_DATA_INTERFACE',columns='ALL',
           filter='(MARKET="全部")(SECURITY_CODE="002414")(DATETIME>=\'2023-01-01\')(DATETIME<=\'2026-10-13\')',
           pageNumber=1,pageSize=500,sortTypes=-1,sortColumns='SUSPEND_START_DATE',source='WEB',client='WEB')
    address='https://datacenter-web.eastmoney.com/api/data/v1/get'
    res=request(address,p)
    results.append(store(c,'suspension_query',address,p,'GET',res,(res[1].get('result') or {}).get('data') or [],'SUSPEND_START_DATE'))
    c.commit();c.close()
    (ROOT/'补缺采集记录.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
