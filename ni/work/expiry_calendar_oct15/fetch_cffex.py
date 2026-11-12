import urllib.request,concurrent.futures,hashlib,json,datetime,pathlib,sys
P=pathlib.Path(__file__).resolve().parent
(P/'raw').mkdir(exist_ok=True)
def fetch(u):
 x={'url':u,'method':'GET','retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20);b=r.read();h=hashlib.sha256(b).hexdigest();fn='raw/'+h+'.html';(P/fn).write_bytes(b);x.update(status=r.status,final_url=r.url,sha256=h,raw_path=fn,bytes=len(b),accepted='error_page/' not in r.url)
 except Exception as e:x.update(error=repr(e),accepted=False)
 return x
if __name__=='__main__':
 us=json.load(open(sys.argv[1]));out=sys.argv[2]
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
  rr=[]
  for x in ex.map(fetch,us):rr.append(x);print(json.dumps({k:v for k,v in x.items() if k not in ['sha256','raw_path']},ensure_ascii=False),flush=True)
 (P/out).write_text(json.dumps(rr,ensure_ascii=False,indent=2))
