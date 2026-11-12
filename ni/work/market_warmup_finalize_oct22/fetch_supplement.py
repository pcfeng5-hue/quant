"""Preserve public documentation and bounded provider probes; no source execution."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

OUT=Path(__file__).resolve().parent
RAW=OUT/'raw'
LOG=OUT/'supplement_requests.json'

def request(name,url,notes,parameters=None):
    if parameters:url+='?'+urllib.parse.urlencode(parameters)
    row=dict(name=name,url=url,method='GET',parameters=parameters or {},notes=notes,
             retrieved_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),error=None)
    data=None
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read();row['status']=response.status;row['response_headers']=dict(response.headers)
        sha=hashlib.sha256(raw).hexdigest();path=RAW/(name+'_'+sha[:16]+'.txt');path.write_bytes(raw)
        row.update(raw_path=str(path),sha256=sha,bytes=len(raw))
        text=raw.decode('utf-8')
        try:data=json.loads(text)
        except json.JSONDecodeError:
            # Parse only documented JSONP assignment as JSON, never evaluate JavaScript.
            match=re.fullmatch(r'\s*[A-Za-z_$][\w$]*\s*=\s*(\{.*\})\s*;?\s*',text,re.S)
            if match:data=json.loads(match.group(1));row['wrapper']='JSONP assignment parsed as JSON, not executed'
        if isinstance(data,dict):
            row['provider_code']=data.get('code')
            symbol=(data.get('data') or {}).get('sz002414') or {}
            row['symbol_keys']=list(symbol)
            for key in ('day','qfqday','hfqday'):
                if key in symbol:
                    items=symbol[key];row[key+'_rows']=len(items)
                    row[key+'_first']=items[0] if items else None;row[key+'_last']=items[-1] if items else None
    except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)
    saved=json.loads(LOG.read_text()) if LOG.exists() else []
    saved.append(row);LOG.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in row.items() if k in ('name','status','bytes','error','day_rows','qfqday_rows','hfqday_rows','day_first','day_last')},ensure_ascii=False),flush=True)
    return row,data

if __name__=='__main__':
    RAW.mkdir(exist_ok=True)
    mode=sys.argv[1] if len(sys.argv)>1 else 'probe'
    if mode=='probe':
        request('tencent_new_0_2026_probe','https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get',
                'New provider endpoint located in AKShare official source. Probe schema and units; no source executed.',
                dict(_var='kline_day2026',param='sz002414,day,2026-01-01,2026-10-16,640,'))
    elif mode=='docs':
        for name,url in [
            ('akshare_official_tx_source','https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_hist_tx.py'),
            ('akshare_official_em_source','https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_hist_em.py'),
            ('akshare_official_stock_docs','https://akshare.akfamily.xyz/data/stock/stock.html'),
            ('eastmoney_adjustment_education','https://baike.eastmoney.com/item/%E5%A4%8D%E6%9D%83')]:
            request(name,url,'Read-only preserved source document. AKShare is primary for its SDK mapping, not provider-certified API documentation; educational page does not prove endpoint implementation.')
    elif mode=='new_all':
        for year in range(2022,2027):
            for flag,adj in [('0',''),('1','qfq'),('2','hfq')]:
                request(f'tencent_new_{flag}_{year}','https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get',
                        'Documented SDK mapping: native main-board stock volume hands; amount ten-thousand CNY; turnover percent. Raw fields retained; snapshot not PIT.',
                        dict(_var=f'kline_day{adj}{year}',param=f'sz002414,day,{year}-01-01,{min(str(year)+"-12-31","2026-10-16")},640,{adj}'))
