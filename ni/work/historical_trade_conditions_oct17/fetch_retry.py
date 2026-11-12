import concurrent.futures,json
from fetch_sources import fetch,OUT
ITEMS=[
 ('rules_2023_pdf_trade','https://docs.static.szse.cn/www/lawrules/rule/trade/W020230217564423808793.pdf'),
 ('rules_2023_pdf_stock','https://docs.static.szse.cn/www/lawrules/rule/stock/W020230217564423808793.pdf'),
 ('rules_2023_pdf_repeal','https://www.szse.cn/lawrules/rule/repeal/rules/P020231230545143336292.pdf'),
 ('rules_2023_notice_trade','https://www.szse.cn/lawrules/rule/stock/trade/t20230217_598773.html'),
 ('rules_2023_notice_stock','https://investor.szse.cn/lawrules/rule/stock/t20230217_598773.html'),
 ('chinaclear_original_publisher_transfer_notice','https://finance.sina.cn/2022-04-28/detail-imcwipii6993883.d.html?wm=3049_0015'),
 ('dividend_personal_tax_2015','https://www.chinatax.gov.cn/n810341/n810755/c1797427/content.html'),
]
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p:r=list(p.map(fetch,ITEMS))
 (OUT/'source_requests_retry.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
 for x in r: print(json.dumps(x,ensure_ascii=False))
