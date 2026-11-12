import concurrent.futures,json
from fetch_sources import fetch,OUT
ITEMS=[
 ('rules_2023_pdf_stock_trade','https://docs.static.szse.cn/www/lawrules/rule/stock/trade/W020230217564423808793.pdf'),
 ('rules_2023_notice_listing','https://www.szse.cn/index/listing/rule/t20230217_598773.html'),
]
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:r=list(p.map(fetch,ITEMS))
 (OUT/'source_requests_final.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
 for x in r:print(json.dumps(x,ensure_ascii=False))
