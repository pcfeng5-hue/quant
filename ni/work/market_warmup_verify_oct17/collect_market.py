"""Stage public stock bars only. Never writes the project research database."""
from __future__ import annotations
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RAW = OUT / 'raw'
START, END = '2022-01-01', '2026-10-16'
DB = ROOT / 'outputs/高德红外数据库/高德红外_2023起.sqlite'
ADJ = {'0':'unadjusted', '1':'forward_adjusted_snapshot', '2':'backward_adjusted_snapshot'}

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def get_jobs():
    jobs=[]
    for flag in ('0','1','2'):
        params=dict(secid='0.002414',klt=101,fqt=flag,beg=START.replace('-',''),end=END.replace('-',''),
                    fields1='f1,f2,f3,f4,f5,f6',fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
        jobs.append(dict(name=f'em_{flag}_20220101_20261016',provider='eastmoney',adjustment_flag=flag,
                         base_url='https://push2his.eastmoney.com/api/qt/stock/kline/get',parameters=params))
    for year in range(2022,2027):
        begin=f'{year}-01-01';end=min(f'{year}-12-31',END)
        for flag,mode in [('0',''),('1','qfq'),('2','hfq')]:
            params=dict(param=f'sz002414,day,{begin},{end},640,{mode}')
            jobs.append(dict(name=f'tencent_{flag}_{year}',provider='tencent',adjustment_flag=flag,
                             base_url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',parameters=params))
    for job in jobs:
        job['url']=job['base_url']+'?'+urllib.parse.urlencode(job['parameters'])
    return jobs

def fetch(job):
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    result={**job,'method':'GET','requested_range':{'start':START,'end':END},'retrieved_at_utc':stamp,
            'personal_account_used':False,'error':None}
    try:
        req=urllib.request.Request(job['url'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/' if job['provider']=='eastmoney' else 'https://gu.qq.com/'})
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read()
            result['status']=response.status
            result['response_headers']=dict(response.headers)
        sha=hashlib.sha256(raw).hexdigest()
        path=RAW/(job['name']+'_'+sha[:16]+'.json')
        path.write_bytes(raw)
        result.update(sha256=sha,bytes=len(raw),raw_path=str(path))
        data=json.loads(raw)
        result['top_level_keys']=list(data) if isinstance(data,dict) else None
        if job['provider']=='eastmoney':
            values=data.get('data') or {}
            records=values.get('klines') or []
            result['response_metadata']={k:v for k,v in values.items() if k!='klines'}
            result['provider_code']=data.get('rc')
            result['response_key']='data.klines'
        else:
            values=(data.get('data') or {}).get('sz002414') or {}
            key={'0':'day','1':'qfqday','2':'hfqday'}[job['adjustment_flag']]
            records=values.get(key) or []
            result['provider_code']=data.get('code')
            result['response_key']='data.sz002414.'+key
            result['available_symbol_keys']=list(values)
        result['provider_rows']=len(records)
        if not records:
            result['error']='EMPTY_OR_MISSING_EXPECTED_RESPONSE_KEY: '+str(data.get('msg') or data.get('message') or result['provider_code'])
    except Exception as exc:
        result['error']=type(exc).__name__+': '+str(exc)
    result['finished_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    return result

def parse_result(result):
    rows=[];errors=[]
    if result.get('error') or not result.get('raw_path'):
        return rows,errors
    data=json.loads(Path(result['raw_path']).read_text())
    if result['provider']=='eastmoney':
        records=(data.get('data') or {}).get('klines') or []
    else:
        key={'0':'day','1':'qfqday','2':'hfqday'}[result['adjustment_flag']]
        records=((data.get('data') or {}).get('sz002414') or {}).get(key) or []
    seen=set()
    for position,value in enumerate(records):
        parts=value.split(',') if isinstance(value,str) else value
        try:
            day=parts[0]
            if not START<=day<=END:
                raise ValueError('date outside requested research range')
            if day in seen:
                raise ValueError('duplicate date within request')
            seen.add(day)
            o,c,h,l,v=map(float,parts[1:6])
            if not (0<l<=min(o,c)<=max(o,c)<=h) or v<0:
                raise ValueError('invalid OHLC or volume')
            em=result['provider']=='eastmoney'
            row=dict(date=day,symbol='002414.SZ',provider=result['provider'],source_request=result['name'],
                     source_sha256=result['sha256'],retrieved_at_utc=result['retrieved_at_utc'],
                     adjustment_flag=result['adjustment_flag'],adjustment=ADJ[result['adjustment_flag']],
                     open=o,high=h,low=l,close=c,volume_provider_native=v,
                     volume_unit='provider_numeric; stock hands convention supported by existing cross-source comparison; formal vendor API unit specification not obtained',
                     amount_cny=float(parts[6]) if em else None,turnover_percent=float(parts[10]) if em else None,
                     price_unit='CNY_per_share',adjustment_vintage='retrieval_snapshot; not_point_in_time',
                     raw_row=value,source_row_index=position)
            rows.append(row)
        except (ValueError,TypeError,IndexError) as exc:
            errors.append(dict(source_request=result['name'],source_row_index=position,error=str(exc),raw_row=value))
    result.update(accepted_rows=len(rows),rejected_rows=len(errors),
                  min_date=min((r['date'] for r in rows),default=None),max_date=max((r['date'] for r in rows),default=None))
    return rows,errors

def compare(rows):
    maps={}
    conflicts=[]
    for row in rows:
        key=(row['provider'],row['adjustment_flag'])
        old=maps.setdefault(key,{})
        if row['date'] in old:
            conflicts.append(dict(provider=key[0],adjustment_flag=key[1],date=row['date'],error='duplicate source date across requests'))
        old[row['date']]=row
    rawem=maps.get(('eastmoney','0'),{}); rawtx=maps.get(('tencent','0'),{})
    common=sorted(set(rawem)&set(rawtx));comparisons=[];mismatches=[]
    for day in common:
        row=dict(date=day,all_ohlc_within_half_cent=True,volume_exact_equal=True,fields={})
        for field in ('open','high','low','close','volume_provider_native'):
            a,b=rawem[day][field],rawtx[day][field]
            diff=abs(a-b); tolerance=0 if field=='volume_provider_native' else 0.005
            ok=diff<=tolerance+1e-10
            row['fields'][field]=dict(eastmoney=a,tencent=b,absolute_difference=diff,tolerance=tolerance,pass_check=ok)
            if field=='volume_provider_native':row['volume_exact_equal']=ok
            else:row['all_ohlc_within_half_cent'] &= ok
            if not ok:mismatches.append(dict(date=day,field=field,**row['fields'][field]))
        comparisons.append(row)
    summary=dict(compared_adjustment='unadjusted only',comparison_fields=['open','high','low','close','volume_provider_native'],
                 overlap_dates=len(common),matching_dates=sum(r['all_ohlc_within_half_cent'] and r['volume_exact_equal'] for r in comparisons),
                 mismatch_fields=len(mismatches),only_eastmoney=sorted(set(rawem)-set(rawtx)),only_tencent=sorted(set(rawtx)-set(rawem)),
                 amount_and_turnover_cross_source_verification='not_available_from_tencent_daily_schema',
                 source_independence_boundary='Different provider endpoints; their upstream exchange/vendor feeds are not independently established.',
                 duplicate_source_dates=conflicts)
    dump(OUT/'cross_source_daily_comparison.json',comparisons)
    dump(OUT/'cross_source_mismatches.json',mismatches)
    return maps,summary

def old_baseline_comparison(maps):
    old_manifest=json.loads((ROOT/'work/refresh_oct15_market/manifest.json').read_text())
    results=[];diffs=[]
    for item in old_manifest['results']:
        if not item['name'].startswith('em_daily_') or not item.get('stage_raw_path'):continue
        flag=item['name'].rsplit('_',1)[-1]
        olddata=json.loads(Path(item['stage_raw_path']).read_text())
        old={r.split(',')[0]:r.split(',') for r in (olddata.get('data') or {}).get('klines',[])}
        new=maps.get(('eastmoney',flag),{})
        common=sorted(set(old)&set(new));changed=0
        for day in common:
            oldrow=old[day];newrow=new[day]['raw_row'].split(',')
            if oldrow!=newrow:
                changed+=1
                diffs.append(dict(date=day,adjustment_flag=flag,old=oldrow,new=newrow))
        results.append(dict(provider='eastmoney',adjustment_flag=flag,baseline_retrieval=item['retrieved_at'],
                            baseline_sha256=item['sha256'],common_dates=len(common),rows_changed=changed,
                            note='Matching snapshots does not certify point-in-time history.'))
    dump(OUT/'baseline_snapshot_differences.json',diffs)
    return results

def create_outputs(results):
    allrows=[];errors=[]
    for result in results:
        rows,bad=parse_result(result);allrows+=rows;errors+=bad
    maps,cross=compare(allrows)
    baseline=old_baseline_comparison(maps)
    dump(OUT/'market_rows.json',allrows)
    dump(OUT/'row_rejections.json',errors)
    csvfields=['date','symbol','provider','adjustment_flag','adjustment','open','high','low','close','volume_provider_native',
               'amount_cny','turnover_percent','price_unit','adjustment_vintage','source_request','source_sha256','retrieved_at_utc']
    with (OUT/'market_rows.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=csvfields,extrasaction='ignore');writer.writeheader();writer.writerows(allrows)
    cover=[]
    for key,mapping in sorted(maps.items()):
        dates=sorted(mapping)
        cover.append(dict(provider=key[0],adjustment_flag=key[1],adjustment=ADJ[key[1]],rows=len(dates),
                          min_date=dates[0] if dates else None,max_date=dates[-1] if dates else None,
                          warmup_2022_dates=sum(d.startswith('2022-') for d in dates),
                          research_2023_onward_dates=sum(d>='2023-01-01' for d in dates)))
    target=[r for r in allrows if r['date']==END]
    dump(OUT/'target_20261016_rows.json',target)
    summary=dict(scope={'symbol':'002414.SZ','requested_start':START,'requested_end':END,'warmup_range':'full calendar year 2022',
                        'research_range':'2023-01-01 through 2026-10-16'},
                 collection_completed_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                 attempted_requests=len(results),successful_requests=sum(not r.get('error') for r in results),
                 failed_requests=[dict(name=r['name'],url=r['url'],error=r['error']) for r in results if r.get('error')],
                 accepted_source_rows=len(allrows),rejected_source_rows=len(errors),coverage=cover,
                 unadjusted_cross_source=cross,baseline_snapshot_comparison=baseline,
                 target_20261016_source_rows=len(target),
                 historical_adjustment_factor_status='No vendor-documented factor series obtained. Adjusted price series retained separately as current retrieval snapshots.',
                 point_in_time_factor_eligible=False,main_database_mutated=False,
                 known_boundaries=['Source consistency is not independent ground truth certification.',
                                   'No indicators, signal probabilities or return labels computed.',
                                   '2022 bars are warmup observations, not research-outcome sample additions.',
                                   'Do not infer adjusted volume from adjusted price mode; all raw source fields preserved.',
                                   'Tencent daily schema does not supply comparable amount/turnover in the preserved day rows.'])
    dump(OUT/'summary.json',summary)
    lines=['# 高德红外行情与预热数据暂存核对','',
           f'- 请求范围：{START}—{END}；2022年仅作指标预热。',
           f'- 请求{len(results)}次，成功{summary["successful_requests"]}次；原始响应、时间、URL、SHA-256分别留存。',
           f'- 解析源行{len(allrows)}条，拒绝{len(errors)}条。','',
           '|供应商|复权请求|日期数|最早|最晚|2022预热日数|','|---|---|---:|---|---|---:|']
    for c in cover:lines.append(f'|{c["provider"]}|{c["adjustment"]}|{c["rows"]}|{c["min_date"]}|{c["max_date"]}|{c["warmup_2022_dates"]}|')
    lines+=['',f'- 不复权双源共同日期{cross["overlap_dates"]}，OHLC半分容差且成交量数字完全一致日期{cross["matching_dates"]}，差异字段{cross["mismatch_fields"]}。',
            '- 单位：价格为每股人民币；成交量保留供应商原数，股票手数口径受到现有跨源相等与成交额范围检查支持，但尚未取得两供应商正式接口单位文档。金额/换手率只来自东方财富，腾讯逐日字段未提供可比项。',
            '- 复权价格全部为本次读取的历史快照，不是历史当日可获得的版本。没有取得供应商有定义的独立复权因子序列，禁止将前复权/不复权收盘之比当成已验证因子。',
            '- 本目录暂存，不修改主库，不计算技术指标或概率，不证明历史可交易性。']
    if summary['failed_requests']:
        lines+=['','## 失败请求']+[f'- {r["name"]}: {r["error"]}' for r in summary['failed_requests']]
    (OUT/'行情预热与末日核对.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary

def main():
    RAW.mkdir(parents=True,exist_ok=True)
    before={'sha256':digest(DB),'bytes':DB.stat().st_size}
    conn=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True)
    before['quick_check']=conn.execute('pragma quick_check').fetchone()[0];conn.close()
    dump(OUT/'main_database_before.json',before)
    tag=sys.argv[1] if len(sys.argv)>1 else 'network_attempt'
    attempt_path=OUT/(tag+'_requests.json')
    jobs=get_jobs()
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(fetch,j) for j in jobs]
        for future in concurrent.futures.as_completed(futures):
            result=future.result();results.append(result)
            dump(attempt_path,sorted(results,key=lambda x:x['name']))
            print(json.dumps({k:result.get(k) for k in ('name','status','provider_rows','bytes','error')},ensure_ascii=False),flush=True)
    results.sort(key=lambda x:x['name'])
    summary=create_outputs(results)
    dump(OUT/'manifest.json',dict(attempt_file=str(attempt_path),results=results))
    after={'sha256':digest(DB),'bytes':DB.stat().st_size}
    check=dict(before=before,after=after,unchanged=before['sha256']==after['sha256'] and before['bytes']==after['bytes'])
    dump(OUT/'main_database_readonly_check.json',check)
    print(json.dumps(dict(successful_requests=summary['successful_requests'],accepted_source_rows=summary['accepted_source_rows'],coverage=summary['coverage'],cross_source=summary['unadjusted_cross_source'],main_database_unchanged=check['unchanged']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
