"""Integrate the staged Oct 15 public-data batch, retaining acquisition vintages."""
import collections
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
import audit_calendar
from integrate_audits import normalized_title

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]/'work'
TARGET='2026-10-15'
RUN='refresh-20261015-v1'


def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)
def read(path):return json.loads(path.read_text())


def main():
    market=read(WORK/'refresh_oct15_market/manifest.json')['results']
    indices=read(WORK/'refresh_oct15_market/tencent_index_manifest.json')['results']
    records=read(WORK/'refresh_oct15_records/manifest.json')['sources']
    announcements=read(WORK/'refresh_oct15_disclosures/stage_manifest.json')
    prepared=read(WORK/'refresh_oct15_disclosures/prepared_source_records.json')
    probes=read(WORK/'history_gap_oct15/requests.json')
    holders=read(WORK/'history_gap_oct15/top10_total_normalized.json')
    audit_calendar.END=date.fromisoformat(TARGET)
    calendar=audit_calendar.build_calendar();expected={r['trade_date'] for r in calendar if r['is_scheduled_open']}
    assert len(expected)==914
    batches=market+indices+records+announcements['results']+probes
    prepared_by=collections.defaultdict(list)
    for r in prepared:prepared_by[r['dataset']].append(r)
    backup=ROOT/'备份/高德红外_20261013_v0.4.sqlite';backup.parent.mkdir(exist_ok=True)
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
    if not backup.exists():
        with sqlite3.connect(backup) as destination:c.backup(destination)
    old_bars={s:{r['trade_date']:dict(r) for r in c.execute('SELECT * FROM current_daily_bars WHERE source=?',(s,))}
              for s in ('em_daily_0','index_1.000001','index_0.399001')}
    c.executescript('''
      CREATE TABLE IF NOT EXISTS database_settings(key TEXT PRIMARY KEY,value TEXT);
      CREATE TABLE IF NOT EXISTS data_refresh_runs(run_id TEXT PRIMARY KEY,target_end TEXT,applied_at TEXT,payload_json TEXT);
      CREATE TABLE IF NOT EXISTS data_retrieval_attempts(run_id TEXT,attempt_id TEXT,dataset TEXT,url TEXT,
        method TEXT,parameters_json TEXT,retrieved_at TEXT,sha256 TEXT,raw_path TEXT,error TEXT,payload_json TEXT,
        PRIMARY KEY(run_id,attempt_id));
      CREATE TABLE IF NOT EXISTS shareholder_history_observations(snapshot_id TEXT,row_hash TEXT,
        symbol TEXT,reference_date TEXT,holder_name TEXT,observation_scope TEXT,
        historical_input_eligible INTEGER,payload_json TEXT,PRIMARY KEY(snapshot_id,row_hash));
      CREATE TABLE IF NOT EXISTS shareholder_disclosure_links(row_hash TEXT,art_code TEXT,page_number INTEGER,
        source_sha256 TEXT,historical_input_eligible INTEGER,payload_json TEXT,
        PRIMARY KEY(row_hash,art_code,page_number,source_sha256));
      CREATE TABLE IF NOT EXISTS data_source_discrepancies(run_id TEXT,dataset TEXT,reference_date TEXT,
        status TEXT,payload_json TEXT,PRIMARY KEY(run_id,dataset,reference_date));
      CREATE VIEW IF NOT EXISTS latest_available_fund_flow AS
        SELECT n.* FROM normalized_fund_flow n JOIN source_snapshots s ON n.snapshot_id=s.snapshot_id
        WHERE s.error IS NULL AND NOT EXISTS(
          SELECT 1 FROM normalized_fund_flow newer JOIN source_snapshots ns ON newer.snapshot_id=ns.snapshot_id
          WHERE newer.trade_date=n.trade_date AND ns.error IS NULL
            AND (ns.retrieved_at>s.retrieved_at OR (ns.retrieved_at=s.retrieved_at AND newer.snapshot_id>n.snapshot_id)));
      CREATE VIEW IF NOT EXISTS current_announcement_reconciliation AS
        SELECT * FROM announcement_reconciliation WHERE audit_version=(SELECT value FROM database_settings WHERE key='reconciliation_version');
      CREATE VIEW IF NOT EXISTS current_announcement_ir_reconciliation AS
        SELECT * FROM announcement_ir_reconciliation WHERE audit_version=(SELECT value FROM database_settings WHERE key='reconciliation_version');
    ''')
    c.execute('BEGIN IMMEDIATE')
    snapshots={};attempts=[];new_bar_maps={};index_differences=[]
    for job in batches:
        name=job['name'];kind=job.get('kind','probe');error=job.get('error')
        path=job.get('stage_raw_path') or job.get('raw_path_absolute') or job.get('raw_path')
        raw=None;data=None;rel=None;sha=job.get('sha256')
        if path:
            path=Path(path)
            if not path.is_absolute():path=ROOT.parents[1]/path
            raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
            data=json.loads(raw)
            rel='raw/'+name+'_'+sha[:16]+'.json';(ROOT/rel).write_bytes(raw)
        if job.get('success') is False:error='provider_error_'+str(job.get('code'))+': '+str(job.get('message'))
        sid=name+':'+(sha or job['retrieved_at'])+':'+RUN
        params=job.get('parameters') or {}
        method=job.get('method','GET')
        attempts.append(dict(dataset=name,url=job['url'],retrieved_at=job['retrieved_at'],error=error,sha256=sha,raw_path=rel))
        aid=hashlib.sha256(dump(attempts[-1]).encode()).hexdigest()
        c.execute('INSERT OR IGNORE INTO data_retrieval_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)',
          (RUN,aid,name,job['url'],method,dump(params),job['retrieved_at'],sha,rel,error,dump(job)))
        accepted=rejected=0;days=[]
        if data is not None and not error:
            if kind in ('daily_em','index_em','daily_tencent','index_tencent'):
                if kind in ('daily_em','index_em'):items=(data.get('data') or {}).get('klines') or []
                else:items=((data.get('data') or {}).get(job.get('symbol','sz002414')) or {}).get('day') or []
                parsed=[]
                for item in items:
                    a=item.split(',') if isinstance(item,str) else item;day=a[0]
                    if not '2023-01-01'<=day<=TARGET:rejected+=1;continue
                    o,close,high,low,volume=map(float,a[1:6]);assert 0<low<=min(o,close)<=max(o,close)<=high and volume>=0
                    tencent=kind in ('daily_tencent','index_tencent')
                    amount=None if tencent else float(a[6]);turnover=None if tencent else float(a[10])
                    symbol='002414.SZ' if kind in ('daily_em','daily_tencent') else ('1.000001' if job.get('symbol')=='sh000001' else '0.399001') if kind=='index_tencent' else name[6:]
                    adjustment=name.rsplit('_',1)[-1] if kind=='daily_em' else '0'
                    unit='provider_native_index_volume' if kind=='index_tencent' else 'provider_hands'
                    c.execute('INSERT OR IGNORE INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (sid,symbol,name,adjustment,day,o,high,low,close,volume,amount,turnover,unit,'provider_pct' if turnover is not None else None))
                    parsed.append(dict(trade_date=day,open=o,high=high,low=low,close=close,volume=volume))
                    days.append(day);accepted+=1
                assert parsed,'empty market series'
                new_bar_maps[name]={r['trade_date']:r for r in parsed}
                if kind=='index_tencent':
                    assert job['provider_name']==('上证指数' if job['symbol']=='sh000001' else '深证成指')
            elif name in prepared_by:
                for r in prepared_by[name]:
                    assert hashlib.sha256(r['payload_json'].encode()).hexdigest()==r['row_hash']
                    c.execute('INSERT OR IGNORE INTO source_records VALUES (?,?,?,?,?,?,?,?,?)',
                      (sid,name,r['row_hash'],r['reference_date'],r['date_field'],r['publication_time'],r['evidence_type'],r['availability_status'],r['payload_json']))
                    days.append(r['reference_date']);accepted+=1
            elif kind in ('market_record','flow'):
                items=((data.get('data') or {}).get('klines') or []) if kind=='flow' else ((data.get('result') or {}).get('data') or [])
                for r in items:
                    day=r.split(',')[0] if isinstance(r,str) else (r.get('TRADE_DATE') or r.get('DATE') or '')[:10]
                    if not '2023-01-01'<=day<=TARGET:rejected+=1;continue
                    value=dump(r);rh=hashlib.sha256(value.encode()).hexdigest()
                    c.execute('INSERT OR IGNORE INTO source_records VALUES (?,?,?,?,?,?,?,?,?)',
                      (sid,name,rh,day,'provider_day' if isinstance(r,str) else 'TRADE_DATE' if 'TRADE_DATE' in r else 'DATE',None,
                       'proxy' if kind=='flow' else 'provider_record','unverified_historical_availability',value))
                    days.append(day);accepted+=1
            elif name=='top10_total_history':
                for r in holders:
                    assert r['source_sha256']==sha and not r['historical_input_eligible']
                    value=dump(r['payload']);assert hashlib.sha256(value.encode()).hexdigest()==r['row_hash']
                    c.execute('INSERT OR IGNORE INTO shareholder_history_observations VALUES (?,?,?,?,?,?,?,?)',
                      (sid,r['row_hash'],r['symbol'],r['reference_date'],r['payload']['HOLDER_NAME'],r['observation_scope'],0,dump(r)))
                    days.append(r['reference_date']);accepted+=1
        if kind in ('daily_em','index_em','daily_tencent','index_tencent','market_record','flow') and not accepted and not error:error='empty_or_unusable_provider_response'
        c.execute('INSERT OR IGNORE INTO source_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)',
          (sid,name,job['url'],job['retrieved_at'],sha,rel,accepted,rejected,min(days) if days else None,max(days) if days else None,error))
        c.execute('INSERT OR IGNORE INTO source_requests VALUES (?,?,?)',(sid,method,dump(params)))
        snapshots[name]=sid
    for fail in announcements.get('retry_history',[])+read(WORK/'refresh_oct15_market/attempts.json'):
        if not fail.get('error'):continue
        key=hashlib.sha256(dump(fail).encode()).hexdigest()
        c.execute('INSERT OR IGNORE INTO data_retrieval_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)',
          (RUN,key,fail['name'],fail['url'],fail.get('method','GET'),dump(fail.get('parameters',{})),fail['retrieved_at'],None,None,fail['error'],dump(fail)))
    # Authoritative scope advances only with all three stock price bases and independent stock dates.
    base=new_bar_maps['em_daily_0']
    stock_tx=new_bar_maps['tencent_daily_2026']
    for source in ('em_daily_0','em_daily_1','em_daily_2','tencent_index_sh000001','tencent_index_sz399001'):
        assert set(new_bar_maps[source])==expected,source+' calendar incomplete'
    assert set(stock_tx)=={d for d in expected if d.startswith('2026')}
    assert all(all(abs(base[d][k]-r[k])<=.005 for k in ('open','high','low','close','volume')) for d,r in stock_tx.items())
    for source,old in [('tencent_index_sh000001',old_bars['index_1.000001']),('tencent_index_sz399001',old_bars['index_0.399001'])]:
        for d in set(old)&set(new_bar_maps[source]):
            r=new_bar_maps[source][d]
            if any(abs(old[d][k]-r[k])>.005 for k in ('open','high','low','close','volume')):
                value=dict(old=old[d],new=r,status='unresolved_provider_difference_originals_retained')
                index_differences.append(dict(dataset=source,reference_date=d,**value))
                c.execute('INSERT OR IGNORE INTO data_source_discrepancies VALUES (?,?,?,?,?)',(RUN,source,d,value['status'],dump(value)))
    for r in calendar:c.execute('INSERT OR IGNORE INTO trading_calendar VALUES (?,?,?,?,?)',
        (r['trade_date'],r['exchange_scope'],r['is_scheduled_open'],r['calendar_version'],dump(r)))
    for r in read(WORK/'history_gap_oct15/nonperiodic_original_text_links.json'):
        doc=c.execute('SELECT sha256 FROM announcement_documents WHERE art_code=?',(r['art_code'],)).fetchone()
        assert doc is not None and doc[0]==r['source_sha256'] and not r['historical_input_eligible']
        assert c.execute('SELECT 1 FROM announcement_pages WHERE art_code=? AND page_number=? AND source_sha256=?',(r['art_code'],r['pdf_page'],r['source_sha256'])).fetchone()
        c.execute('INSERT OR IGNORE INTO shareholder_disclosure_links VALUES (?,?,?,?,?,?)',
          (r['row_hash'],r['art_code'],r['pdf_page'],r['source_sha256'],0,dump(r)))
    settings=dict(start='2023-01-01',end=TARGET,reconciliation_version=RUN,
        index_sources=dump({'上证指数':'tencent_index_sh000001','深证成指':'tencent_index_sz399001'}))
    for key,value in settings.items():c.execute('INSERT OR REPLACE INTO database_settings VALUES (?,?)',(key,value))
    audit_current_records(c,base)
    reconcile_catalogues(c)
    summary=dict(run_id=RUN,target_end=TARGET,applied_at=datetime.now(timezone.utc).isoformat(),
        stock_days=len(base),new_stock_dates=sorted(set(base)-set(old_bars['em_daily_0'])),
        margin_dates=c.execute("SELECT COUNT(DISTINCT reference_date) FROM current_source_records WHERE dataset LIKE 'margin%'").fetchone()[0],
        margin_end=c.execute("SELECT MAX(reference_date) FROM current_source_records WHERE dataset LIKE 'margin%'").fetchone()[0],
        fund_flow_latest_window=c.execute("SELECT COUNT(*) FROM current_source_records WHERE dataset='fund_flow_proxy'").fetchone()[0],
        fund_flow_retained_dates=c.execute('SELECT COUNT(*) FROM latest_available_fund_flow').fetchone()[0],
        shareholder_observations=c.execute('SELECT COUNT(*) FROM shareholder_history_observations').fetchone()[0],
        index_discrepancies=index_differences,attempts=attempts,original_backup=str(backup.relative_to(ROOT)))
    c.execute('INSERT OR REPLACE INTO data_refresh_runs VALUES (?,?,?,?)',(RUN,TARGET,summary['applied_at'],dump(summary)))
    gaps=[('data_refresh_index_sources','partial','两指数已取得腾讯914日；东方财富更新两次未返回，旧912日保留。两处价格与194日成交量存在来源差异，共195个来源日期、196字段；成交量统计口径待核，不静默合并。'),
      ('fund_holder_history','partial','前十大总股东170行：150定期、20非定期部分名单；另有前十大流通股东。不是全部基金持仓，源无公告日，首次可得时间未认证。'),
      ('fund_flow_history','partial','滚动接口最新120日；保留历史已取窗口后122独立日期。2023起完整资金流仍缺，大小单分类不代表机构身份。'),
      ('trading_calendar_status','partial','计划交易日历已扩至914日；个股停牌仅核实精确日期请求语法，空响应不认证完整历史或无事件。'),
      ('chip_history','access_required','完整历史筹码仍未取得；目标随已核日线扩至914日。供应商答复未确认，未采购、未重建估计填空。')]
    c.executemany('INSERT OR REPLACE INTO coverage_gaps VALUES (?,?,?)',gaps)
    c.commit();c.close()
    (ROOT/'official_calendar_2023_to_20261015.json').write_text(json.dumps(calendar,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'截至20261015补缺合库记录.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(dump({k:v for k,v in summary.items() if k not in ('attempts','index_discrepancies')}))


def audit_current_records(c,bars):
    qfq={r['trade_date']:r for r in c.execute("SELECT * FROM current_daily_bars WHERE source='em_daily_1'")}
    fields=('trade_date','main_net_amount','small_net_amount','medium_net_amount','large_net_amount','super_large_net_amount',
            'main_net_percent','small_net_percent','medium_net_percent','large_net_percent','super_large_net_percent','provider_close','change_percent')
    restrictions=collections.Counter()
    for row in list(c.execute('SELECT * FROM current_source_records')):
        d=json.loads(row['payload_json']);flags=['historical_first_availability_unverified'];period=notice=updated=None
        if isinstance(d,dict):
            period=(d.get('REPORT_DATE') or d.get('END_DATE') or '')[:10] or None
            notice=(d.get('NOTICE_DATE') or d.get('HOLD_NOTICE_DATE') or d.get('notice_date') or '')[:10] or None
            updated=(d.get('UPDATE_DATE') or '')[:10] or None
            if notice and updated and updated>notice:flags.append('provider_updated_after_notice')
            for key,value in d.items():
                if value is None:continue
                if key in ('CHANGE_RATE_1DAYS','CHANGE_RATE_5DAYS','CHANGE_RATE_10DAYS','CHANGE_RATE_20DAYS') or re.fullmatch(r'D\d+_CLOSE_ADJCHRATE',key):
                    restrictions[(row['dataset'],key,'forward_return_statistic')]+=1;flags.append('contains_forward_return_statistics')
                if key=='FCFF_FORWARD' or re.fullmatch(r'RCHANGE\d+DCP',key):
                    restrictions[(row['dataset'],key,'formula_and_historical_availability_unknown')]+=1
            if row['dataset'].startswith('cninfo'):flags.append('announcement_epoch_is_date_label_not_first_release')
        elif row['dataset']=='fund_flow_proxy':
            parts=d.split(',');assert len(parts)==13
            out={k:v if i==0 else float(v) for i,(k,v) in enumerate(zip(fields,parts))};day=out['trade_date']
            assert abs(out['main_net_amount']-out['large_net_amount']-out['super_large_net_amount'])<=1
            bar=c.execute("SELECT amount FROM current_daily_bars WHERE source='em_daily_0' AND trade_date=?",(day,)).fetchone()
            assert bar and abs(out['main_net_amount']/bar[0]*100-out['main_net_percent'])<=.02
            matches=day in qfq and abs(out['provider_close']-qfq[day]['close'])<=.005
            residual=sum(out[k] for k in ('small_net_amount','medium_net_amount','large_net_amount','super_large_net_amount'))
            out.update(evidence_type='provider_trade_size_flow_proxy',amount_unit='CNY',percent_unit='percentage_points',investor_identity='unknown',
              full_period_coverage=False,historical_availability='unverified',net_balance_residual_cny=residual,
              price_basis='matches_current_qfq_in_checked_window' if matches else 'unverified')
            c.execute('INSERT OR IGNORE INTO normalized_fund_flow VALUES (?,?,?,?,?,?)',
              (row['snapshot_id'],row['row_hash'],day,dump(out),'https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_fund_em.py','mapped_and_current_amount_checked'))
            flags.append('trade_size_proxy_not_institutional_identity')
            if abs(residual)>1:flags.append('net_flow_balance_small_residual_unexplained')
        c.execute('INSERT OR IGNORE INTO record_temporal_audit VALUES (?,?,?,?,?,?,?,?)',
          (row['snapshot_id'],row['row_hash'],'supplement-audit-v1',period,notice,updated,dump(sorted(set(flags))),0))
    for (dataset,field,reason),count in restrictions.items():
        c.execute('INSERT OR REPLACE INTO restricted_source_fields VALUES (?,?,?,?,?)',(dataset,field,reason,count,'supplement-audit-v1'))


def reconcile_catalogues(c):
    em={};cn={};ir=[]
    for row in c.execute('SELECT * FROM current_source_records'):
        if row['dataset'].startswith('announcements'):
            d=json.loads(row['payload_json']);em[(row['reference_date'],normalized_title(d['title']))]=row
        elif row['dataset'].startswith('cninfo_announcements'):
            d=json.loads(row['payload_json']);cn[(row['reference_date'],normalized_title(d['announcementTitle']))]=row
        elif row['dataset'].startswith('cninfo_ir'):ir.append(row)
    assert len(em)==312 and len(cn)==308 and len(ir)==4
    for key in sorted(set(em)|set(cn)):
        cr=cn.get(key);er=em.get(key);assert er is not None,'official announcement missing'
        status='date_and_normalized_title_match' if cr else 'eastmoney_additional_investor_activity'
        c.execute('INSERT OR IGNORE INTO announcement_reconciliation VALUES (?,?,?,?,?,?,?,?)',
          (cr['snapshot_id'] if cr else '',cr['row_hash'] if cr else '',er['snapshot_id'],er['row_hash'],key[0],key[1],status,RUN))
    for cr in ir:
        d=json.loads(cr['payload_json']);key=(cr['reference_date'],normalized_title(d['announcementTitle']));er=em[key]
        c.execute('INSERT OR IGNORE INTO announcement_ir_reconciliation VALUES (?,?,?,?,?,?,?,?)',
          (cr['snapshot_id'],cr['row_hash'],er['snapshot_id'],er['row_hash'],key[0],key[1],'official_ir_date_and_title_match',RUN))


if __name__=='__main__':main()
