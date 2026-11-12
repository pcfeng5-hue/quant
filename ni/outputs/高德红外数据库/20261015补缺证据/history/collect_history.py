import urllib.request, urllib.parse, datetime, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MAN=ROOT/'requests.json'

def request(name,base,params,notes=''):
    url=base+'?'+urllib.parse.urlencode(params)
    meta={'name':name,'method':'GET','base_url':base,'parameters':params,'url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'notes':notes}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.eastmoney.com/'})
        with urllib.request.urlopen(req,timeout=25) as r: raw=r.read(25000000)
        sha=hashlib.sha256(raw).hexdigest(); target=ROOT/(name+'_'+sha[:16]+'.json');target.write_bytes(raw)
        meta.update(sha256=sha,raw_path=str(target),bytes=len(raw))
        data=json.loads(raw);meta.update(success=data.get('success'),code=data.get('code'),message=data.get('message'))
        result=data.get('result')
        if isinstance(result,dict): meta.update(pages=result.get('pages'),count=result.get('count'),rows=len(result.get('data') or []))
        else: meta['top_level_keys']=list(data)
    except Exception as e:
        data=None; meta['error']=type(e).__name__+': '+str(e)
    saved=json.loads(MAN.read_text()) if MAN.exists() else []
    saved.append(meta);MAN.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
    print(json.dumps(meta,ensure_ascii=False),flush=True)
    return data

if __name__=='__main__':
    base='https://datacenter-web.eastmoney.com/api/data/v1/get'
    p=dict(reportName='RPT_CUSTOM_SUSPEND_DATA_INTERFACE',columns='ALL',filter='(MARKET="全部")(DATETIME=\'2026-10-15\')',pageNumber=1,pageSize=500,sortColumns='SUSPEND_START_DATE',sortTypes=-1,source='WEB',client='WEB')
    d=request('suspension_schema_daily',base,p,'Exact date equality per AKShare official source; response used to inspect stock-code field. Does not establish historical absence.')
    if d:print('schema first',(d.get('result') or {}).get('data',[None])[:1])
    p=dict(reportName='RPT_HOLDERNUM_DET',columns='ALL',filter='(SECURITY_CODE="002414")',pageNumber=1,pageSize=500,sortColumns='END_DATE',sortTypes=-1,source='WEB',client='WEB')
    request('holder_count_all',base,p,'No report-period or disclosure-date filtering; check for any finer interval already publicly supplied.')
    p=dict(reportName='RPT_F10_EH_EQUITY',columns='ALL',filter='(SECUCODE="002414.SZ")',pageNumber=1,pageSize=500,sortColumns='END_DATE',sortTypes=-1,source='HSF10',client='PC')
    request('capital_structure_all','https://datacenter.eastmoney.com/securities/api/data/v1/get',p,'Existing verified AKShare-equity schema, fetch latest as-of retrieval snapshot, not certified historical vintage.')
