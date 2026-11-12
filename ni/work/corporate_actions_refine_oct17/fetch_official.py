"""Read-only public PDF cross-check; does not write the main database."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib, json, re, sqlite3
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[2]
DBDIR = BASE / 'outputs/高德红外数据库'
OUT = Path(__file__).resolve().parent
(OUT / 'official').mkdir(exist_ok=True)
c = sqlite3.connect('file:' + str(DBDIR / '高德红外_2023起.sqlite') + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
selected = [
 'AN202312281615153661', 'AN202412301641472101', 'AN202512301811330148',
 'AN202504241661802971', 'AN202604141821191382',
 'AN202505201676081145', 'AN202605081822079377', 'AN202306281591781833'
]
rows = [dict(c.execute('select * from announcement_documents where art_code=?', (a,)).fetchone()) for a in selected]
c.close()
metadata = []
for p in sorted((BASE/'work/refresh_oct15_disclosures/raw').glob('cninfo_announcements_page*.json')):
 for x in json.loads(p.read_text()).get('announcements') or []:
  metadata.append((x, p, hashlib.sha256(p.read_bytes()).hexdigest()))
def norm(s): return re.sub(r'[\s:：()（）]', '', s).replace('高德红外','')
def fetch(r):
 hits=[(x,p,h) for x,p,h in metadata if norm(x['announcementTitle'])==norm(r['title']) and x['adjunctUrl'].split('/')[1]==r['notice_date'][:10]]
 if len(hits)!=1: return dict(art_code=r['art_code'],error='ambiguous_official_metadata',hits=len(hits))
 x,p,h=hits[0]
 url='https://static.cninfo.com.cn/'+x['adjunctUrl']
 rec=dict(art_code=r['art_code'],official_announcement_id=x['announcementId'],title=x['announcementTitle'],url=url,metadata_source_path=str(p),metadata_source_sha256=h,official_metadata=x,announcement_time_precision='calendar_date_at_midnight_not_exact_release_time',exact_first_publication_verified=False,retrieved_at_utc=datetime.now(timezone.utc).isoformat())
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=35) as resp:
   data=resp.read(); status=resp.status; final_url=resp.url; content_type=resp.headers.get('Content-Type')
  digest=hashlib.sha256(data).hexdigest()
  ext='.pdf' if data.startswith(b'%PDF-') else '.response'
  path=OUT/'official'/(x['announcementId']+'_'+digest[:16]+ext)
  path.write_bytes(data)
  rec.update(http_status=status,final_url=final_url,content_type=content_type,bytes=len(data),sha256=digest,path=str(path),is_pdf=data.startswith(b'%PDF-'),existing_vendor_pdf_sha256=r['sha256'],identical_to_existing_vendor_pdf=digest==r['sha256'],error=None)
 except Exception as e: rec.update(error=type(e).__name__+': '+str(e))
 return rec
with ThreadPoolExecutor(max_workers=3) as pool: result=list(pool.map(fetch,rows))
(OUT/'official_crosscheck.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps([dict(art_code=r['art_code'],http_status=r.get('http_status'),identical=r.get('identical_to_existing_vendor_pdf'),bytes=r.get('bytes'),error=r.get('error')) for r in result],ensure_ascii=False,indent=2))
