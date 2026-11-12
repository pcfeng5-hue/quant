import concurrent.futures, html, json, pathlib, re, sys
from fetch_sources import fetch, OUT

EXTRA=[
 ('rules_2023_pdf','https://docs.static.szse.cn/www/lawrules/index/rule/W020230217564423808793.pdf'),
 ('rules_2023_notice_retry','https://www.szse.cn/lawrules/index/rule/t20230217_598773.html'),
 ('rules_2026_notice_retry','https://www.szse.cn/lawrules/rule/trade/t20260424_620190.html'),
 ('first_registered_mainboard_20230410','https://www.szse.cn/aboutus/trends/news/t20230410_599854.html'),
 ('stamp_law_2021','https://www.hengqin.gov.cn/lab/flfg/fl/content/post_3517835.html'),
 ('chinaclear_fees_2026','https://www.chinaclear.cn/zdjs/fbzyls/202512/a59388fbfa714c5fa546784891a42e30/files/深圳市场证券登记结算业务收费及代收税费一览表.pdf'),
 ('chinaclear_fee_list','https://www.chinaclear.cn/zdjs/fbzyls/service_tlist/code_0.shtml'),
]

def get(item):
 name,url=item
 from urllib.parse import quote,urlsplit,urlunsplit
 p=urlsplit(url); url=urlunsplit((p.scheme,p.netloc,quote(p.path,safe='/:%'),p.query,p.fragment))
 return fetch((name,url))

def run(items):
 out=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  for row in pool.map(get,items):
   out.append(row); print(json.dumps({k:v for k,v in row.items() if k in ('name','error','bytes')},ensure_ascii=False),flush=True)
 return out

def decode(row):
 b=pathlib.Path(row['raw_path']).read_bytes()
 return b.decode('gb18030' if 'GBK' in row.get('content_type','').upper() else 'utf-8',errors='replace')

def main():
 extra=run(EXTRA); (OUT/'source_requests_extra.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2))
 months=json.loads((OUT.parent/'status_history_round6/months_catalogue.json').read_text())
 catalog=run([(f"month_catalog_{m['month']}",m['url']) for m in months])
 (OUT/'month_catalog_requests.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
 tasks=[]; links=[]
 for m,row in zip(months,catalog):
  if 'raw_path' not in row: continue
  text=decode(row)
  for href,title in re.findall(r'<a\b[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>',text,re.S|re.I):
   title=re.sub('<[^>]+>','',title).strip()
   if title not in ('证券停牌情况','证券成交统计'): continue
   url=html.unescape(href).replace('http://','https://')
   name=('suspension_' if title=='证券停牌情况' else 'security_stats_')+m['month']
   tasks.append((name,url)); links.append({'month':m['month'],'title':title,'url':url,'source_catalog_name':row['name']})
 (OUT/'month_links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2))
 rows=run(tasks); (OUT/'monthly_requests.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
