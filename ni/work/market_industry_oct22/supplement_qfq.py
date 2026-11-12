import concurrent.futures
import urllib.parse
from collect import ROOT,TX,fetch,normalize,write_json

jobs=[]
for year in (2022,2023,2024):
    params=dict(param=f'sz002414,day,{year}-01-01,{year}-12-31,640,qfq')
    jobs.append(dict(id=f'tencent_002414.SZ_1_year{year}',provider='tencent',symbol='002414.SZ',txsymbol='sz002414',name='高德红外',kind='stock',adjustment='1',url=TX+'?'+urllib.parse.urlencode(params),parameters=params))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p:
    results=list(p.map(fetch,jobs))
rows=[]
rejections=[]
for r in results:
    rr,ee=normalize(r);rows+=rr
    rejections += [dict(request_id=r['id'],**e) for e in ee]
write_json(ROOT/'qfq_supplement_manifest.json',dict(reason='Tencent full-range qfq response capped at 640 rows; complete earlier years with explicit bounded requests',results=results))
write_json(ROOT/'qfq_supplement_rows.json',rows)
write_json(ROOT/'qfq_supplement_rejections.json',rejections)
print([(r['id'],r['error'],r.get('accepted_rows'),r.get('min_date'),r.get('max_date')) for r in results])
