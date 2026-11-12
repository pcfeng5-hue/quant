from pathlib import Path
import urllib.request,urllib.error,hashlib,json,datetime
root=Path(__file__).resolve().parent
requests=[
 ('tushare_distribution_doc','https://tushare.pro/document/2?doc_id=294'),
 ('tushare_summary_doc','https://tushare.pro/document/2?doc_id=293'),
 ('tushare_permission_doc','https://tushare.pro/document/1?doc_id=290'),
 ('quantcoda_docs','https://quantcoda.com/docs'),
 ('quantcoda_capabilities','https://quantcoda.com/capabilities'),
 ('quantcoda_methodology','https://quantcoda.com/methodology'),
 ('quantcoda_terms','https://quantcoda.com/terms'),
 ('quantcoda_anonymous_002414_sample','https://quantcoda.com/v1/chips/distribution?symbol=002414.SZ&trade_date=20230103'),
]
records=[]
for name,url in requests:
 row={'id':name,'url':url,'method':'GET','request_headers':{'User-Agent':'Mozilla/5.0'},'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authentication_used':False}
 try:
  req=urllib.request.Request(url,headers=row['request_headers'])
  with urllib.request.urlopen(req,timeout=25) as r:
   body=r.read();row.update(http_status=r.status,response_url=r.url,response_headers=dict(r.headers))
 except urllib.error.HTTPError as e:
  body=e.read();row.update(http_status=e.code,error=str(e),response_headers=dict(e.headers))
 except Exception as e:
  body=None;row.update(error=type(e).__name__+': '+str(e))
 if body is not None:
  suffix='.json' if 'json' in row.get('response_headers',{}).get('content-type','').lower() or name.endswith('capabilities') else '.html'
  path=root/(name+suffix);path.write_bytes(body)
  row.update(raw_path=str(path.relative_to(root)),sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
 records.append(row)
 print(name,row.get('http_status'),row.get('bytes'),flush=True)
(root/'requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
