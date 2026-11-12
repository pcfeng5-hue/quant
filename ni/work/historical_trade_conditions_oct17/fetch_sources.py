import concurrent.futures, datetime, hashlib, json, pathlib, urllib.request

OUT = pathlib.Path(__file__).resolve().parent
SOURCES = [
 ('rules_2021_pdf','https://docs.static.szse.cn/www/lawrules/rule/trade/W020210331716400647184.pdf'),
 ('rules_2023_notice','https://investor.szse.cn/lawrules/index/rule/t20230217_598773.html'),
 ('rules_2026_notice','https://investor.szse.cn/lawrules/rule/trade/t20260424_620190.html'),
 ('rules_2026_pdf','https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf'),
 ('fee_reduction_2023','https://www.szse.cn/disclosure/notice/t20230818_602805.html'),
 ('fees_current','https://investor.szse.cn/marketServices/deal/payFees/index.html'),
 ('stamp_reduction_2023','https://shanxi.chinatax.gov.cn/web/detail/sx-11400-545-1780448'),
 ('szse_suspension_202301','https://docs.static.szse.cn/www/market/periodical/month/W020230202548759938270.html'),
 ('szse_month_index','https://www.szse.cn/market/periodical/month/index.html'),
 ('chinaclear_history','https://m.chinaclear.cn/zdjs/dsj/about_dsj.shtml'),
]

def fetch(item):
 name,url=item
 meta={'name':name,'url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET','primary_source':True}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=35) as r:
   raw=r.read(); ctype=r.headers.get('Content-Type','')
   sha=hashlib.sha256(raw).hexdigest(); ext='pdf' if raw[:4]==b'%PDF' else 'html'
   target=OUT/'raw'/f'{name}_{sha[:16]}.{ext}'; target.write_bytes(raw)
   meta.update(final_url=r.url,http_status=r.status,content_type=ctype,bytes=len(raw),sha256=sha,raw_path=str(target))
 except Exception as e: meta['error']=repr(e)
 return meta

if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(fetch,SOURCES))
 (OUT/'source_requests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 for row in result: print(json.dumps(row,ensure_ascii=False))
