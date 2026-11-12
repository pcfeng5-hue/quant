"""Independent append-only public market staging; never opens the main database."""
import concurrent.futures
import csv
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'raw'
START, END = '2022-01-01', '2026-10-21'
EM = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
TX = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
SERIES = [('000001.SH', '上证指数', '1.000001', 'sh000001', 'index'),
          ('399001.SZ', '深证成指', '0.399001', 'sz399001', 'index'),
          ('399967.SZ', '中证军工', '0.399967', 'sz399967', 'index'),
          ('002414.SZ', '高德红外', '0.002414', 'sz002414', 'stock')]

def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')

def jobs():
    result = []
    for symbol, name, secid, txsymbol, kind in SERIES:
        for adjustment in (['0', '1'] if kind == 'stock' else ['0']):
            params = dict(secid=secid,klt=101,fqt=adjustment,beg='20220101',end='20261021',fields1='f1,f2,f3,f4,f5,f6',fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
            result.append(dict(id=f'em_{symbol}_{adjustment}', provider='eastmoney',symbol=symbol,name=name,kind=kind,adjustment=adjustment,url=EM+'?'+urllib.parse.urlencode(params),parameters=params))
            params = dict(param=f'{txsymbol},day,2022-01-01,2026-10-21,1600,'+('qfq' if adjustment=='1' else ''))
            result.append(dict(id=f'tencent_{symbol}_{adjustment}',provider='tencent',symbol=symbol,txsymbol=txsymbol,name=name,kind=kind,adjustment=adjustment,url=TX+'?'+urllib.parse.urlencode(params),parameters=params))
    result.append(dict(id='csi_399967_methodology_v1_2',provider='CSI official',kind='methodology',url='https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175428-399967_Index_Methodology_cn.pdf'))
    return result

def fetch(job):
    result = dict(job, requested_at_utc=datetime.now(timezone.utc).isoformat(),personal_account_used=False,error=None)
    try:
        req=urllib.request.Request(job['url'],headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=30) as r:
            result.update(status=r.status,response_headers=dict(r.headers),final_url=r.url)
            data=r.read()
        digest=hashlib.sha256(data).hexdigest()
        ext='pdf' if job['kind']=='methodology' else 'json'
        path=RAW/f"{job['id']}_{digest[:16]}.{ext}"
        path.write_bytes(data)
        result.update(raw_path=str(path),sha256=digest,bytes=len(data))
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
    result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    return result

def normalize(result):
    rows, errors=[],[]
    if result['error'] or result['kind']=='methodology': return rows,errors
    payload=json.loads(Path(result['raw_path']).read_bytes())
    if result['provider']=='eastmoney':
        data=payload.get('data') or {}
        rawrows=data.get('klines') or []
        result['provider_metadata']={k:v for k,v in data.items() if k!='klines'}
        result['response_key']='data.klines'
        result['provider_code']=payload.get('rc')
    else:
        data=(payload.get('data') or {}).get(result['txsymbol']) or {}
        key='qfqday' if result['adjustment']=='1' else 'day'
        rawrows=data.get(key) or []
        # No silent qfq->raw fallback. Preserve actual keys for audit.
        result['available_symbol_keys']=list(data)
        result['response_key']=f"data.{result['txsymbol']}.{key}"
        result['provider_code']=payload.get('code')
    result['provider_rows']=len(rawrows)
    for row_index,raw in enumerate(rawrows):
        try:
            a=raw.split(',') if isinstance(raw,str) else raw
            day=a[0]
            if not START <= day <= END:
                errors.append(dict(reason='out_of_requested_range',raw=raw));continue
            o,c,h,l,v=map(float,a[1:6])
            if not (0<l<=min(o,c)<=max(o,c)<=h) or v<0:raise ValueError('OHLC or volume invalid')
            is_em=result['provider']=='eastmoney'
            amount=float(a[6]) if is_em else None
            turnover=float(a[10]) if is_em else None
            rows.append(dict(symbol=result['symbol'],name=result['name'],kind=result['kind'],source=result['provider'],adjustment=result['adjustment'],trade_date=day,open=o,high=h,low=l,close=c,volume_raw=v,amount_raw=amount,turnover_raw=turnover,price_unit='index_points' if result['kind']=='index' else 'CNY_per_share',volume_unit='provider_native_index_volume_unit_and_scope_unverified' if result['kind']=='index' else 'provider_stock_hands_convention_not_formal_API_specification',amount_unit='provider_CNY' if is_em else None,turnover_unit='provider_pct_definition_unverified' if is_em else None,adjustment_vintage='retrieval_snapshot_not_point_in_time' if result['adjustment']=='1' else 'provider_unadjusted',source_request_id=result['id'],source_sha256=result['sha256'],source_row_index=row_index,raw_row=raw))
        except Exception as exc:
            errors.append(dict(reason=f'{type(exc).__name__}: {exc}',raw=raw))
    result.update(accepted_rows=len(rows),rejected_rows=len(errors),min_date=min((r['trade_date'] for r in rows),default=None),max_date=max((r['trade_date'] for r in rows),default=None))
    if not rawrows:result['error']='EMPTY_DATA_OR_UNEXPECTED_RESPONSE_KEY'
    return rows,errors

def main():
    RAW.mkdir(parents=True,exist_ok=True)
    js=jobs()
    write_json(ROOT/'requests.json',js)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(fetch,js))
    rows,rejections=[],[]
    for r in results:
        try:
            rr,ee=normalize(r);rows+=rr
            rejections += [dict(request_id=r['id'],**e) for e in ee]
        except Exception as exc:r['error']=f'parse {type(exc).__name__}: {exc}'
    write_json(ROOT/'manifest.json',dict(requested_range=[START,END],cutoff_basis='2026-10-21 common completed date requested; actual responses determine achieved coverage',results=results))
    write_json(ROOT/'market_rows.json',rows)
    write_json(ROOT/'row_rejections.json',rejections)
    if rows:
        with (ROOT/'market_rows.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps([dict(id=r['id'],error=r['error'],rows=r.get('accepted_rows'),start=r.get('min_date'),end=r.get('max_date')) for r in results],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
