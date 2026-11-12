"""Stage public announcement catalogues. Main SQLite connection is read-only."""
import hashlib,json,math,sqlite3,sys,urllib.parse,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone,timedelta
BASE=Path(__file__).resolve().parent
DB=BASE.parent.parent/'outputs/高德红外数据库/高德红外_2023起.sqlite'
START,END='2023-01-01','2026-10-15'
SH=timezone(timedelta(hours=8))
(BASE/'raw').mkdir(exist_ok=True)
(BASE/'new_documents').mkdir(exist_ok=True)

def request(name,url,params,method='GET',kind='provider_record'):
    qs=urllib.parse.urlencode(params)
    target=url+('?' + qs if method=='GET' else '')
    begun=datetime.now(timezone.utc).isoformat()
    r=dict(name=name,kind=kind,url=target,request_url=url,method=method,parameters=params,retrieved_at=begun,error=None)
    try:
        req=urllib.request.Request(target,data=qs.encode() if method=='POST' else None,headers=({'User-Agent':'Mozilla/5.0'} if 'eastmoney.com' in target else {'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/','Content-Type':'application/x-www-form-urlencoded'}),method=method)
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(15*1024*1024+1)
            if len(raw)>15*1024*1024:raise ValueError('response exceeds cap')
        r['completed_at']=datetime.now(timezone.utc).isoformat()
        r['sha256']=hashlib.sha256(raw).hexdigest()
        p=BASE/'raw'/(name+'_'+r['sha256'][:16]+'.json');p.write_bytes(raw)
        r['raw_path']=str(p)
        r['data']=json.loads(raw)
        r['snapshot_id']=name+':'+r['sha256']
    except urllib.error.HTTPError as ex:
        raw=ex.read(1024*1024);digest=hashlib.sha256(raw).hexdigest();p=BASE/'raw'/(name+'_http_error_'+digest[:16]+'.bin');p.write_bytes(raw)
        r.update(error=type(ex).__name__+': '+str(ex),http_status=ex.code,error_response_path=str(p),error_response_sha256=digest)
    except Exception as ex:r['error']=type(ex).__name__+': '+str(ex)
    return r

def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def plain_title(v):return v.replace('<em>','').replace('</em>','')

c=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True)
old={k:{} for k in ['eastmoney','cninfo_fulltext','cninfo_ir']}
for ds,encoded in c.execute("SELECT dataset,payload_json FROM current_source_records WHERE dataset LIKE 'announcements%' OR dataset LIKE 'cninfo_announcements_page%' OR dataset LIKE 'cninfo_ir_page%'"):
    row=json.loads(encoded)
    group='eastmoney' if ds.startswith('announcements') else 'cninfo_ir' if ds.startswith('cninfo_ir') else 'cninfo_fulltext'
    old[group][row['art_code'] if group=='eastmoney' else row['announcementId']]=row
out=dict(requested_start=START,requested_end=END,symbol='002414.SZ',created_at=datetime.now(timezone.utc).isoformat(),main_database_read_only=True,results=[],catalogues={},new_documents=[],notes=['Directory retrieval time and provider announcement dates do not certify earliest historical public availability.','Empty or failed responses cannot certify absence.'])

retry_only='--retry-eastmoney' in sys.argv
if retry_only:
    previous=json.loads((BASE/'stage_manifest.json').read_text())
    out=previous
    out.setdefault('retry_history',[]).extend([x for x in previous['results'] if x['name'].startswith('announcements')])
    out['results']=[x for x in previous['results'] if not x['name'].startswith('announcements')]

def stage_group(group,kind,address,base_params,page_key,page_size,keyfunc,rowsfunc,totalfunc,materialfunc):
    first=request(('announcements' if group=='eastmoney' else 'cninfo_announcements_page1' if group=='cninfo_fulltext' else 'cninfo_ir_page1'),address,base_params,'GET' if group=='eastmoney' else 'POST',kind)
    results=[first]
    total=totalfunc(first.get('data') or {}) if not first['error'] else None
    if not isinstance(total,int) or total<0:
        complete=False;reason='missing_or_invalid_provider_total';pages=0
    else:
        pages=math.ceil(total/page_size)
        if pages>30:raise ValueError('page cap exceeded; incomplete')
        for page in range(2,pages+1):
            params=dict(base_params);params[page_key]=page
            name='announcements_page'+str(page) if group=='eastmoney' else ('cninfo_announcements_page' if group=='cninfo_fulltext' else 'cninfo_ir_page')+str(page)
            results.append(request(name,address,params,'GET' if group=='eastmoney' else 'POST',kind))
        totals=[totalfunc(x.get('data') or {}) for x in results if not x['error']]
        complete=not any(x['error'] for x in results) and len(results)==max(1,pages) and all(t==total for t in totals)
        reason='all_pages_fetched' if complete else 'request_failure_or_total_changed'
    allrows=[]
    for result in results:
        rows=rowsfunc(result.get('data') or {}) if not result['error'] else []
        result['records']=rows
        result['provider_rows']=len(rows)
        result['date_key']='notice_date' if group=='eastmoney' else 'announcementTime'
        result['availability_status']='unverified_historical_availability' if group=='eastmoney' else 'provider_announcement_date_not_first_public_timestamp'
        result['source_requests']=dict(method=result['method'],parameters_json=json.dumps(result['parameters'],ensure_ascii=False,sort_keys=True))
        allrows.extend(rows)
        print(result['name'],len(rows),result['error'],flush=True)
    lookup={keyfunc(row):row for row in allrows}
    if isinstance(total,int) and (len(lookup)!=total or len(allrows)!=total):
        complete=False;reason='unique_or_raw_count_differs_from_reported_total'
    oldrows=old[group]
    new=sorted(set(lookup)-set(oldrows));missing=sorted(set(oldrows)-set(lookup)) if complete else []
    changed=[k for k in sorted(set(lookup)&set(oldrows)) if canon(lookup[k])!=canon(oldrows[k])]
    material=[k for k in changed if canon(materialfunc(lookup[k]))!=canon(materialfunc(oldrows[k]))]
    dates=[(row['notice_date'][:10] if group=='eastmoney' else datetime.fromtimestamp(row['announcementTime']/1000,SH).date().isoformat()) for row in allrows]
    out['catalogues'][group]=dict(provider_total=total,pages_requested=len(results),complete=complete,reason=reason,raw_rows=len(allrows),unique_rows=len(lookup),old_unique_rows=len(oldrows),new_ids=new,missing_ids=missing,changed_row_ids=changed,materially_changed_ids=material,actual_min_date=min(dates) if dates else None,actual_max_date=max(dates) if dates else None,records=[dict(record_id=k,payload=lookup[k]) for k in sorted(lookup)])
    out['results'].extend(results)

stage_group('eastmoney','announcements','https://np-anotice-stock.eastmoney.com/api/security/ann',dict(stock_list='002414',page_size=100,page_index=1,ann_type='A',begin_time=START,end_time=END),'page_index',100,lambda r:r['art_code'],lambda d:(d.get('data') or {}).get('list') or [],lambda d:(d.get('data') or {}).get('total_hits'),lambda r:{k:r.get(k) for k in ['art_code','notice_date','title','columns','codes','source_type']})
form=dict(pageNum=1,pageSize=30,column='szse',tabName='fulltext',stock='002414,9900012687',searchkey='',secid='',plate='',category='',trade='',seDate=START+'~'+END,sortName='',sortType='',isHLtitle='true')
for group,tab in ([] if retry_only else [('cninfo_fulltext','fulltext'),('cninfo_ir','relation')]):
    p=dict(form);p['tabName']=tab
    stage_group(group,'cninfo_announcements','https://www.cninfo.com.cn/new/hisAnnouncement/query',p,'pageNum',30,lambda r:r['announcementId'],lambda d:d.get('announcements') or [],lambda d:d.get('totalAnnouncement'),lambda r:{k:r.get(k) for k in ['announcementId','announcementTitle','announcementTime','adjunctUrl','adjunctSize','adjunctType','secCode','orgId']})

# Download only newly listed or materially revised CNINFO originals, and only for complete catalogues.
for group in ['cninfo_fulltext','cninfo_ir']:
    cat=out['catalogues'][group]
    if not cat['complete']:continue
    todo=set(cat['new_ids']+cat['materially_changed_ids'])
    for entry in cat['records']:
        if entry['record_id'] not in todo:continue
        row=entry['payload'];url='https://static.cninfo.com.cn/'+row['adjunctUrl']
        obj=dict(group=group,announcement_id=entry['record_id'],url=url,title=plain_title(row.get('announcementTitle','')),provider_date=datetime.fromtimestamp(row['announcementTime']/1000,SH).date().isoformat(),retrieved_at=datetime.now(timezone.utc).isoformat(),error=None)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=25) as resp:raw=resp.read(25*1024*1024+1)
            if len(raw)>25*1024*1024 or not raw.startswith(b'%PDF'):raise ValueError('oversize or not PDF')
            digest=hashlib.sha256(raw).hexdigest();path=BASE/'new_documents'/(entry['record_id']+'_'+digest[:16]+'.pdf');path.write_bytes(raw)
            obj.update(sha256=digest,bytes=len(raw),path=str(path),text_extraction_status='pending_pdf_skill_review')
        except Exception as ex:obj['error']=type(ex).__name__+': '+str(ex)
        out['new_documents'].append(obj)

out['finished_at']=datetime.now(timezone.utc).isoformat()
(BASE/'stage_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
summary={k:{kk:vv for kk,vv in v.items() if kk!='records'} for k,v in out['catalogues'].items()}
(BASE/'catalogue_comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
c.close()
