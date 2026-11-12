from pathlib import Path
import concurrent.futures,datetime,hashlib,html,json,re,urllib.request,urllib.parse
P=Path(__file__).resolve().parent
(P/'event_raw').mkdir(exist_ok=True)
manifest=[]
def fetch(item):
    name,url=item; row=dict(name=name,url=url,retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=25) as r:
            raw=r.read(12*1024*1024+1); row.update(status=r.status,final_url=r.url)
        if len(raw)>12*1024*1024:raise ValueError('oversize')
        sha=hashlib.sha256(raw).hexdigest(); path=P/'event_raw'/(name+'_'+sha[:16]+'.html');path.write_bytes(raw)
        row.update(sha256=sha,raw_path=str(path),bytes=len(raw),accepted='error_page/' not in row['final_url'])
    except Exception as e:row.update(error=type(e).__name__+': '+str(e),accepted=False)
    print(name,row.get('status'),row.get('error'),flush=True)
    return row
urls=[('cffex_listing','http://www.cffex.com.cn/cn/jystz.html'),('cffex_home','http://www.cffex.com.cn/cn/'),('csrc_speech_20261019','https://www.csrc.gov.cn/csrc/c106311/c7665578/content.shtml'),('csrc_transfer_20261019','https://www.csrc.gov.cn/csrc/c100028/c7665425/content.shtml'),('csrc_consultation_20261019','https://www.csrc.gov.cn/csrc/c100028/c7665462/content.shtml')]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:manifest.extend(e.map(fetch,urls))
more={}
for row in manifest:
    if row['name'] not in ['cffex_listing','cffex_home'] or not row.get('accepted'):continue
    s=Path(row['raw_path']).read_text(errors='replace')
    for href,title in re.findall(r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>',s,re.S|re.I):
        title=html.unescape(re.sub('<[^>]+>','',title)).strip()
        if '股指' in title and ('交割' in title or '到期' in title):
            url=urllib.parse.urljoin(row['url'],href)
            if '/202610' in url:more[url]=title
if more:
    (P/'discovered_cffex_links.json').write_text(json.dumps(more,ensure_ascii=False,indent=2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:manifest.extend(e.map(fetch,[('cffex_october_'+str(i+1),url) for i,url in enumerate(more)]))
(P/'event_source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(more,ensure_ascii=False,indent=2))
