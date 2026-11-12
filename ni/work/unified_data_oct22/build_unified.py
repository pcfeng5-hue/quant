"""Build a portable, typed observation store; original stores remain read-only."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
import csv, hashlib, json, shutil, sqlite3, tempfile
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/统一数据底座_20261022'
MAIN = ROOT / 'outputs/高德红外数据库/高德红外_2023起.sqlite'

def enc(x): return json.dumps(x, ensure_ascii=False, separators=(',', ':'))
def read(p): return json.loads((ROOT / p).read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def q(x): return '"'+x.replace('"','""')+'"'
def relpath(p, base=ROOT):
    if not p: return None
    z=Path(p)
    if not z.is_absolute(): z=base/z
    try: return z.resolve().relative_to(ROOT).as_posix()
    except ValueError: return str(z)
def numeric(v): return None if v in (None,'','-') else float(v)
def write_csv(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'统一数据底座.sqlite').exists(): raise FileExistsError('Existing completed build; create a new version')
    before=sha(MAIN)
    old=sqlite3.connect(MAIN.as_uri()+'?mode=ro',uri=True);old.row_factory=sqlite3.Row
    assert old.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    restrictions=[dict(r) for r in old.execute('SELECT * FROM restricted_source_fields')]
    blocked={r['field_name']:r['reason'] for r in restrictions}
    manifest_by_key={}
    for path in ['work/market_industry_oct22/manifest.json','work/market_industry_oct22/qfq_supplement_manifest.json']:
        for r in read(path)['results']:
            manifest_by_key[(r['id'],r.get('sha256'))]=r
    checks=[]
    with tempfile.TemporaryDirectory(prefix='unified_data_',dir=ROOT/'work/unified_data_oct22') as temp:
        temp=Path(temp)
        db=sqlite3.connect(temp/'统一数据底座.sqlite');db.row_factory=sqlite3.Row
        quarant=sqlite3.connect(temp/'受限字段隔离.sqlite')
        quarant.execute('CREATE TABLE restricted_values(dataset TEXT,source_record_id TEXT,json_path TEXT,field_name TEXT,value_json TEXT,reason TEXT,source_input TEXT)')
        db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
        CREATE TABLE ingestion_sources(dataset_id TEXT PRIMARY KEY,title TEXT,source_path TEXT,source_sha256 TEXT,source_rows INTEGER,source_min_date TEXT,source_max_date TEXT,role TEXT);
        CREATE TABLE file_assets(project_relative_path TEXT PRIMARY KEY,sha256 TEXT,bytes INTEGER,exists_locally INTEGER,prior_audit_sha256 TEXT,references_json TEXT);
        CREATE INDEX asset_content ON file_assets(sha256);
        CREATE TABLE source_requests(request_key TEXT PRIMARY KEY,request_id TEXT,url TEXT,raw_path TEXT,source_sha256 TEXT,retrieved_at TEXT,requested_at TEXT,normalized_requested_start TEXT,normalized_requested_end TEXT,time_semantics TEXT,payload_json TEXT);
        CREATE TABLE source_records(dataset_id TEXT,seq INTEGER,record_kind TEXT,reference_date TEXT,source_record_id TEXT,payload_json TEXT,PRIMARY KEY(dataset_id,seq));
        CREATE TABLE instrument_identifiers(provider_symbol TEXT PRIMARY KEY,canonical_symbol TEXT,instrument_name TEXT,instrument_type TEXT,price_unit TEXT,mapping_evidence TEXT);
        CREATE TABLE market_daily(observation_id TEXT PRIMARY KEY,collection TEXT,snapshot_key TEXT,symbol TEXT,provider TEXT,endpoint TEXT,adjustment TEXT,trade_date TEXT,open REAL,high REAL,low REAL,close REAL,volume_native REAL,amount_cny REAL,turnover_pct REAL,volume_unit TEXT,amount_unit TEXT,turnover_unit TEXT,retrieved_at TEXT,source_sha256 TEXT,source_request_id TEXT,raw_row_index INTEGER,input_path TEXT,input_row_index INTEGER,adjustment_vintage TEXT,model_input_approved INTEGER CHECK(model_input_approved=0));
        CREATE INDEX market_lookup ON market_daily(symbol,trade_date,provider,adjustment,collection);
        CREATE TABLE chip_observations(observation_id TEXT PRIMARY KEY,collection TEXT,expected_date TEXT,actual_date TEXT,kline_date TEXT,accepted_capture INTEGER,profit_ratio_pct REAL,average_cost_display REAL,cost90_low REAL,cost90_high REAL,concentration90_pct REAL,cost70_low REAL,cost70_high REAL,concentration70_pct REAL,kline_basis_control TEXT,context TEXT,observed_at_utc TEXT,complete_price_bins INTEGER CHECK(complete_price_bins=0),model_input_approved INTEGER CHECK(model_input_approved=0),evidence_directory TEXT,payload_json TEXT);
        CREATE INDEX chip_date ON chip_observations(actual_date);
        CREATE TABLE chip_evidence_files(observation_id TEXT,role TEXT,project_relative_path TEXT,sha256 TEXT,exists_locally INTEGER,PRIMARY KEY(observation_id,role),FOREIGN KEY(observation_id) REFERENCES chip_observations(observation_id));
        CREATE TABLE filings(art_code TEXT PRIMARY KEY,title TEXT,notice_date TEXT,original_path TEXT,original_sha256 TEXT,original_url TEXT,original_retrieved_at TEXT,current_catalogue_retrieved_at TEXT,first_publication_time TEXT,availability_status TEXT,model_input_approved INTEGER CHECK(model_input_approved=0),time_payload_json TEXT);
        CREATE TABLE document_pages(art_code TEXT,page_number INTEGER,source_sha256 TEXT,extractor TEXT,text TEXT,status TEXT,error TEXT,PRIMARY KEY(art_code,page_number,source_sha256));
        CREATE TABLE ocr_pages(run_id TEXT,art_code TEXT,page_number INTEGER,source_sha256 TEXT,text TEXT,status TEXT,payload_json TEXT);
        CREATE TABLE financial_report_observations(art_code TEXT,source_sha256 TEXT,report_period TEXT,metric TEXT,value_decimal TEXT,unit TEXT,provider_notice_date TEXT,availability_status TEXT,evidence_json TEXT);
        CREATE TABLE corporate_actions(event_id TEXT PRIMARY KEY,symbol TEXT,attributable_period TEXT,record_date TEXT,ex_date TEXT,official_cash_date TEXT,cash_cny_per_10_gross TEXT,transfer_shares_per_10 TEXT,total_shares_before INTEGER,total_shares_after INTEGER,first_publication_time TEXT,model_input_approved INTEGER CHECK(model_input_approved=0),payload_json TEXT);
        CREATE TABLE capital_snapshots(observation_id TEXT PRIMARY KEY,period_end TEXT,total_shares INTEGER,limited_shares INTEGER,unlimited_shares INTEGER,unit TEXT,daily_effective_date TEXT,model_input_approved INTEGER CHECK(model_input_approved=0),payload_json TEXT);
        CREATE TABLE trade_conditions(trade_date TEXT PRIMARY KEY,symbol TEXT,rule_id TEXT,historical_st_state TEXT,intraday_suspension_state TEXT,official_normal_state INTEGER,official_upper_limit REAL,official_lower_limit REAL,broker_commission_rate REAL,cost_model_complete INTEGER,execution_eligible INTEGER,original_bar_available INTEGER,current_bar_available INTEGER,previous_close_unadjusted_candidate REAL,previous_close_date TEXT,ex_rights_date INTEGER,limit_reference_price REAL,derived_context_status TEXT,payload_json TEXT);
        CREATE TABLE trade_rules(rule_id TEXT PRIMARY KEY,effective_date TEXT,research_from TEXT,research_to TEXT,normal_limit_pct REAL,st_limit_pct REAL,buy_lot INTEGER,price_tick_cny REAL,validation_scope TEXT,payload_json TEXT);
        CREATE TABLE fee_components(seq INTEGER PRIMARY KEY,fee TEXT,effective_date TEXT,research_from TEXT,research_to TEXT,buy_rate REAL,sell_rate REAL,status TEXT,payload_json TEXT);
        CREATE TABLE events(event_id TEXT PRIMARY KEY,event_type TEXT,event_date TEXT,date_role TEXT,economic_episode_id TEXT,source_url TEXT,source_sha256 TEXT,raw_path TEXT,source_timestamp_raw_json TEXT,first_publication_time TEXT,earliest_model_use_time TEXT,source_level TEXT,model_input_approved INTEGER CHECK(model_input_approved=0),payload_json TEXT);
        CREATE TABLE trading_calendar(trade_date TEXT,exchange_scope TEXT,is_scheduled_open INTEGER,calendar_version TEXT,payload_json TEXT);
        CREATE TABLE conflicts(conflict_id INTEGER PRIMARY KEY,collection TEXT,symbol TEXT,reference_date TEXT,field_name TEXT,status TEXT,payload_json TEXT);
        CREATE TABLE gaps(gap_id TEXT PRIMARY KEY,priority INTEGER,status TEXT,explanation TEXT,next_evidence_needed TEXT);
        CREATE TABLE daily_coverage(trade_date TEXT PRIMARY KEY,is_warmup INTEGER,stock_raw_bar INTEGER,stock_qfq_bar INTEGER,market_background INTEGER,chip_full_capture INTEGER,chip_accepted_observations INTEGER,chip_distinct_value_sets INTEGER,condition_table_present INTEGER,official_daily_state_known INTEGER,official_limit_prices_known INTEGER,calendar_evidence_present INTEGER,margin_observation INTEGER,fund_flow_observation INTEGER,event_date_roles INTEGER);
        ''')

        def sanitize(obj,dataset,rid,input_path,path='$'):
            if isinstance(obj,dict):
                out={}
                for k,v in obj.items():
                    if k in blocked:
                        quarant.execute('INSERT INTO restricted_values VALUES(?,?,?,?,?,?,?)',(dataset,rid,path+'.'+k,k,enc(v),blocked[k],input_path))
                    else: out[k]=sanitize(v,dataset,rid,input_path,path+'.'+k)
                return out
            if isinstance(obj,list): return [sanitize(v,dataset,rid,input_path,path+f'[{i}]') for i,v in enumerate(obj)]
            return obj

        def register(dataset,title,path,rows,role='raw_observation'):
            dates=[str(r.get('trade_date') or r.get('date') or r.get('reference_date') or r.get('event_date')) for r in rows if isinstance(r,dict) and (r.get('trade_date') or r.get('date') or r.get('reference_date') or r.get('event_date'))]
            db.execute('INSERT INTO ingestion_sources VALUES(?,?,?,?,?,?,?,?)',(dataset,title,path,sha(ROOT/path),len(rows),min(dates) if dates else None,max(dates) if dates else None,role))

        def generic(dataset,title,path,kind):
            content=read(path);rows=content if isinstance(content,list) else [content]
            register(dataset,title,path,rows)
            for i,r in enumerate(rows):
                rid=str(r.get('event_id') or r.get('observation_id') or r.get('record_id') or i) if isinstance(r,dict) else str(i)
                clean=sanitize(r,dataset,rid,path)
                date=(r.get('trade_date') or r.get('date') or r.get('reference_date') or r.get('event_date')) if isinstance(r,dict) else None
                db.execute('INSERT INTO source_records VALUES(?,?,?,?,?,?)',(dataset,i,kind,date,rid,enc(clean)))
            return rows

        # Every original snapshot and auxiliary record is retained, with restricted fields quarantined.
        db.execute('INSERT INTO ingestion_sources VALUES(?,?,?,?,?,?,?,?)',('legacy_main','既有主库原始快照',str(MAIN.relative_to(ROOT)),before,old.execute('SELECT COUNT(*) FROM daily_bars').fetchone()[0],None,None,'legacy_baseline'))
        snapshot_meta={r['snapshot_id']:dict(r) for r in old.execute('SELECT * FROM source_snapshots')}
        for sid,s in snapshot_meta.items():
            db.execute('INSERT INTO source_requests VALUES(?,?,?,?,?,?,?,?,?,?,?)',('legacy:'+sid,sid,s['url'],relpath(s['raw_path'],MAIN.parent),s['sha256'],s['retrieved_at'],None,None,None,'legacy_literal_retrieved_at; not_first_publication',enc(s)))
        def add_market(collection,i,r,input_path,legacy=False):
            if legacy:
                sm=snapshot_meta[r['snapshot_id']]
                host=urlparse(sm['url']).hostname or ''
                provider='eastmoney' if host.endswith('.eastmoney.com') else 'tencent' if host.endswith('.gtimg.cn') else r['source']
                endpoint=r['source'];adjustment=r['adjustment'];retrieved=sm['retrieved_at'];rawsha=sm['sha256'];request=r['snapshot_id'];snapshot=r['snapshot_id']
                day=r['trade_date'];v=r['volume'];amount=r['amount'];turn=r['turnover'];vu=r['volume_unit'];au='CNY_per_source_mapping' if amount is not None else None;tu=r['turnover_unit'];vintage='legacy_retrieval_snapshot'
            else:
                provider=r.get('provider',r.get('source'));endpoint=r.get('endpoint','kline' if provider=='eastmoney' else 'fqkline')
                adjustment=str(r.get('adjustment_flag',r.get('adjustment')));retrieved=r.get('retrieved_at_utc');rawsha=r.get('source_sha256');request=r.get('source_request',r.get('source_request_id'));snapshot=collection+':'+str(request)
                if collection=='market_industry_oct21': retrieved=manifest_by_key[(request,rawsha)]['finished_at_utc']
                day=r.get('date',r.get('trade_date'));v=r.get('volume_provider_native',r.get('volume_raw'));amount=r.get('amount_cny',r.get('amount_raw'));turn=r.get('turnover_percent',r.get('turnover_raw'));vu=r.get('volume_unit');au=r.get('amount_unit',r.get('amount_provider_unit','CNY_per_normalization' if amount is not None else None));tu=r.get('turnover_unit','percent_per_normalization' if turn is not None else None);vintage=r.get('adjustment_vintage')
            values=(f'{collection}:{i}',collection,snapshot,r['symbol'],provider,endpoint,adjustment,day,r['open'],r['high'],r['low'],r['close'],v,amount,turn,vu,au,tu,retrieved,rawsha,request,r.get('source_row_index'),input_path,i,vintage,0)
            assert 0 < r['low'] <= min(r['open'],r['close']) <= max(r['open'],r['close']) <= r['high']
            db.execute('INSERT INTO market_daily VALUES('+','.join('?' for _ in values)+')',values)
        for i,row in enumerate(old.execute('SELECT * FROM daily_bars')): add_market('legacy_main',i,dict(row),str(MAIN.relative_to(ROOT)),True)
        for collection,path,title in [('warmup_oct16','work/market_warmup_finalize_oct22/market_rows_all_endpoints.json','行情预热三端点快照'),('market_industry_oct21','work/market_industry_oct22/market_rows_unique.json','个股及市场行业背景双源')]:
            rows=read(path);register(collection,title,path,rows)
            for i,r in enumerate(rows): add_market(collection,i,r,path)
        identifiers=[('002414.SZ','002414.SZ','高德红外','stock','CNY_per_share'),('1.000001','000001.SH','上证指数','index','index_points'),('0.399001','399001.SZ','深证成指','index','index_points'),('000001.SH','000001.SH','上证指数','index','index_points'),('399001.SZ','399001.SZ','深证成指','index','index_points'),('399967.SZ','399967.SZ','中证军工','index','index_points')]
        db.executemany('INSERT INTO instrument_identifiers VALUES(?,?,?,?,?,?)',[r+('raw response instrument identity / source request parameters; original symbol preserved',) for r in identifiers])
        db.execute('ALTER TABLE market_daily ADD COLUMN canonical_symbol TEXT')
        db.execute('ALTER TABLE market_daily ADD COLUMN price_unit TEXT')
        db.execute('UPDATE market_daily SET canonical_symbol=(SELECT canonical_symbol FROM instrument_identifiers i WHERE i.provider_symbol=market_daily.symbol),price_unit=(SELECT price_unit FROM instrument_identifiers i WHERE i.provider_symbol=market_daily.symbol)')
        for i,r in enumerate(old.execute('SELECT * FROM source_records')):
            r=dict(r);payload=json.loads(r.pop('payload_json'));payload=sanitize(payload,r['dataset'],r['row_hash'],str(MAIN.relative_to(ROOT)))
            db.execute('INSERT INTO source_records VALUES(?,?,?,?,?,?)',('legacy_auxiliary',i,r['dataset'],r['reference_date'],r['row_hash'],enc(dict(r,payload=payload))))
        special={'source_records','daily_bars','announcement_documents','announcement_pages','announcement_ocr_texts','original_report_observations','trading_calendar','source_snapshots'}
        for table, in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            if table in special: continue
            for i,row in enumerate(old.execute('SELECT * FROM '+q(table))):
                row=sanitize(dict(row),'legacy_'+table,str(i),str(MAIN.relative_to(ROOT)))
                db.execute('INSERT INTO source_records VALUES(?,?,?,?,?,?)',('legacy_'+table,i,'legacy_evidence',row.get('reference_date'),str(i),enc(row)))

        # Store every chip capture attempt, including rejected attempts and differing versions.
        chip_inputs=[('full_capture','work/chip_full_capture_oct17/records.json',None),('round2','work/chip_repeatability_round2_oct16/ui/records.json','records'),('refine_oct17','work/chip_refine_first3_oct17/records.json',None),('repeat_oct22','work/chip_audit_oct22/records.json',None),('round1','outputs/高德红外数据库/网页筹码核验_20261016/核验记录.json','observations')]
        for collection,path,key in chip_inputs:
            content=read(path);rows=content[key] if key else content;register('chip_'+collection,'筹码原始观察 '+collection,path,rows)
            for i,r in enumerate(rows):
                if collection=='round1':
                    r=dict(r,id=r['evidence_stem'],expected=r['date'],accepted=r['date']==r['kline_date'],values=[r['date'],r['profit_ratio_display'],r['average_cost_display'],r['cost90_display'],r['concentration90_display'],r['cost70_display'],r['concentration70_display']])
                v=r['values'];lo90,hi90=map(float,v[3].split('-'));lo70,hi70=map(float,v[5].split('-'))
                k=r.get('kline',r.get('kline_prices',{}));day=k.get('时间',r.get('kline_date'))
                flat=collection in ('round1','round2');ev=Path(path).parent if flat else Path(path).parent/'records'/r['id']
                obsid=collection+':'+r['id']
                vals=(obsid,collection,r.get('expected'),r.get('date',v[0]),day,int(r.get('accepted',False)),numeric(v[1].rstrip('%')),numeric(v[2]),lo90,hi90,numeric(v[4].rstrip('%')),lo70,hi70,numeric(v[6].rstrip('%')),r.get('basis',r.get('basis_control',r.get('kline_basis_control'))),r.get('context',r.get('stage',collection)),r.get('observed_at_utc'),0,0,str(ev),enc(r))
                db.execute('INSERT INTO chip_observations VALUES('+','.join('?' for _ in vals)+')',vals)
                if flat:
                    proofs={'record_index':Path(path),'summary_html':ev/(r['id']+'_table.html'),'accessibility':ev/(r['id']+'_ax.txt'),'chart':ev/(r['id']+'.jpg')}
                else:
                    proofs={'record':ev/'record.json','summary_html':ev/'summary.html','kline_html':ev/'kline.html','accessibility':ev/('dom.txt' if collection=='refine_oct17' else 'ax.txt'),'chart':ev/'chart.jpg'}
                for role,proof in proofs.items():
                    exists=(ROOT/proof).is_file()
                    db.execute('INSERT INTO chip_evidence_files VALUES(?,?,?,?,?)',(obsid,role,str(proof),sha(ROOT/proof) if exists else None,int(exists)))
        # The round1 flattened schema is retained as raw evidence too.
        generic('chip_round1_evidence','筹码早期历史版本','outputs/高德红外数据库/网页筹码核验_20261016/核验记录.json','chip_evidence')
        ledger=generic('filing_time_ledger','公告时间台账','work/events_publication_oct22/announcement_time_ledger_current.json','disclosure_time')
        time_byid={r['record_id']:r for r in ledger}
        for r in old.execute('SELECT * FROM announcement_documents'):
            t=time_byid.get(r['art_code'],{})
            db.execute('INSERT INTO filings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(r['art_code'],r['title'],r['notice_date'],relpath(r['relative_path'],MAIN.parent),r['sha256'],r['url'],r['retrieved_at'],t.get('retrieved_at'),None,t.get('availability_status','unknown'),0,enc(t)))
        for r in old.execute('SELECT * FROM announcement_pages'): db.execute('INSERT INTO document_pages VALUES(?,?,?,?,?,?,?)',tuple(r))
        for r in old.execute('SELECT * FROM announcement_ocr_texts'): db.execute('INSERT INTO ocr_pages VALUES(?,?,?,?,?,?,?)',(r['run_id'],r['art_code'],r['page_number'],r['source_sha256'],r['text'],r['status'],enc(dict(r))))
        for r in old.execute('SELECT * FROM original_report_observations'): db.execute('INSERT INTO financial_report_observations VALUES(?,?,?,?,?,?,?,?,?)',tuple(r))
        for r in old.execute('SELECT * FROM trading_calendar'): db.execute('INSERT INTO trading_calendar VALUES(?,?,?,?,?)',tuple(r))
        corporate=generic('corporate_actions','分派经济事件','work/corporate_actions_refine_oct17/corporate_actions.json','corporate_action')
        for r in corporate:
            db.execute('INSERT INTO corporate_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['event_id'],r['symbol'],r['attributable_period'],r['record_date'],r['ex_date'],r['official_delegated_cash_distribution_date'],r['cash_cny_per_10_shares_gross'],r['transfer_shares_per_10'],r.get('total_shares_before'),r.get('total_shares_after'),None,0,enc(r)))
        for r in generic('capital_snapshots','期末股本观察','work/corporate_actions_refine_oct17/capital_period_observations.json','capital_period'):
            db.execute('INSERT INTO capital_snapshots VALUES(?,?,?,?,?,?,?,?,?)',(r['observation_id'],r['period_end'],r['total_shares'],r['limited_shares'],r['unlimited_shares'],r['unit'],None,0,enc(r)))
        for name,file,kind in [('non_distribution','non_distribution_decisions.json','non_distribution'),('capital_bridges','capital_bridges.json','arithmetic_bridge'),('capital_unresolved','unresolved_capital_issues.json','unresolved'),('nontrade_transfers','nontrade_transfers.json','nontrade_transfer'),('capital_registration','registration_date_refinement.json','retrospective_evidence')]:
            generic(name,name,'work/corporate_actions_refine_oct17/'+file,kind)
        latest_raw=[dict(r) for r in db.execute("SELECT * FROM market_daily WHERE collection='market_industry_oct21' AND provider='eastmoney' AND symbol='002414.SZ' AND adjustment='0' ORDER BY trade_date")]
        bar_bydate={r['trade_date']:r for r in latest_raw};previous={r['trade_date']:(latest_raw[i-1] if i else None) for i,r in enumerate(latest_raw)}
        conditions=generic('trade_conditions','历史交易条件原表','work/conditions_finish_oct22/daily_trade_conditions_915.json','trade_condition')
        context_corrections=[]
        for r in conditions:
            day=r['trade_date'];p=previous.get(day)
            vals=(day,r['symbol'],r['rule_id'],None if 'unknown' in r['historical_st_status'] else r['historical_st_status'],None,None,r['official_daily_upper_limit'],r['official_daily_lower_limit'],r['broker_commission_rate'],int(r['cost_model_complete']),int(r['execution_eligible']),int(r['unadjusted_daily_bar_available']),int(day in bar_bydate),p['close'] if p else None,p['trade_date'] if p else None,int(r['ex_rights_date_from_existing_original_terms']),None,'joined_current_raw_bars; previous_close_is_not_official_limit_reference',enc(r))
            db.execute('INSERT INTO trade_conditions VALUES('+','.join('?' for _ in vals)+')',vals)
            if not r['unadjusted_daily_bar_available'] and day in bar_bydate: context_corrections.append({'trade_date':day,'change':'current bar source now present','original_observation_unchanged':True})
        for r in generic('trade_rules','交易规则分段','work/conditions_finish_oct22/rule_regimes.json','rule_interval'):
            db.execute('INSERT INTO trade_rules VALUES(?,?,?,?,?,?,?,?,?,?)',(r['rule_id'],r['effective_date'],r['research_period_from'],r['research_period_to'],r['normal_mainboard_limit_pct'],r['mainboard_st_limit_pct'],r['buy_lot'],r['price_tick_cny'],r['status'],enc(r)))
        for i,r in enumerate(generic('fee_components','费用构成历史段','work/conditions_finish_oct22/fee_schedule.json','fee_interval')):
            db.execute('INSERT INTO fee_components VALUES(?,?,?,?,?,?,?,?,?)',(i,r.get('fee'),r.get('effective_date'),r.get('research_from'),r.get('research_to'),r.get('buy_rate'),r.get('sell_rate'),r.get('status'),enc(r)))
        for r in generic('events','标准事件日期角色','work/events_publication_oct22/normalized_events.json','event'):
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['event_id'],r['event_type'],r.get('event_date'),r.get('date_role'),r['economic_episode_id'],r.get('source_url'),r.get('source_sha256'),relpath(r.get('raw_path')),enc(r.get('source_timestamp_raw')),r.get('historical_first_publication_timestamp'),r.get('earliest_model_use_timestamp'),r.get('source_level'),0,enc(r)))
        for i,r in enumerate(read('work/market_industry_oct22/cross_source_differences.json')):
            for field,value in r['fields'].items(): db.execute('INSERT INTO conflicts(collection,symbol,reference_date,field_name,status,payload_json) VALUES(?,?,?,?,?,?)',('market_industry_oct21',r['symbol'],r['trade_date'],field,'unresolved_provider_difference',enc(dict(r,field_values=value))))
        for r in read('work/market_warmup_finalize_oct22/tencent_new_cross_source_strict_mismatches.json'):
            db.execute('INSERT INTO conflicts(collection,symbol,reference_date,field_name,status,payload_json) VALUES(?,?,?,?,?,?)',('warmup_oct16','002414.SZ',r['date'],r['field'],'unresolved_provider_difference',enc(r)))
        for day, in db.execute('SELECT DISTINCT actual_date FROM chip_observations WHERE accepted_capture=1'):
            variants=list(db.execute('SELECT DISTINCT profit_ratio_pct,average_cost_display,cost90_low,cost90_high,concentration90_pct,cost70_low,cost70_high,concentration70_pct FROM chip_observations WHERE actual_date=? AND accepted_capture=1',(day,)))
            if len(variants)>1: db.execute('INSERT INTO conflicts(collection,symbol,reference_date,field_name,status,payload_json) VALUES(?,?,?,?,?,?)',('chip_all_contexts','002414.SZ',day,'chip_summary','loading_context_or_version_difference',enc([list(v) for v in variants])))
        gaps=[('chip_bins',1,'not_acquired','完整价格档数值仍为0日','供应商样本及授权、算法与复权/初始化证据'),('chip_versions',1,'unresolved','同日筹码不同加载条件出现差异','固定条件、跨会话与算法原文'),('historical_time',1,'unverified','首次公开精确时间未认证','历史发布/首次接收日志及修订链'),('daily_state',1,'unknown','逐日ST/停复牌和官方限价不齐','官方逐日状态和参考价'),('float_denominator',2,'unresolved','期末股本不可当逐日流通股本','每日生效股本及股份性质事件'),('fees',2,'unknown_account_terms','实际佣金、最低收费与包费未知','用户后续费率/账单'),('industry_members',2,'not_acquired','历史成分和市场宽度仍缺','历史成员与全市场统计'),('rejected_chip_proof',3,'not_saved','round2:R1_pan_later为拒绝记录，索引在，单份HTML/AX/截图未保存','保留索引及缺口；不得用corrected尝试的证据替代'),('minute_data',3,'not_acquired','未取得盘中做T所需分钟或逐笔数据','单独定义盘中研究后再采集')]
        db.executemany('INSERT INTO gaps VALUES(?,?,?,?,?)',gaps)
        seed=read('work/lineage_audit_oct22/evidence_registry_seed.json')
        for f in seed['files']:
            p=ROOT/f['project_relative_path'];exists=p.is_file()
            db.execute('INSERT INTO file_assets VALUES(?,?,?,?,?,?)',(f['project_relative_path'],sha(p) if exists else None,p.stat().st_size if exists else None,int(exists),f['sha256'],enc(f['references'])))
        for i,r in enumerate(seed['requests']):
            m=manifest_by_key.get((r.get('request_id'),r.get('source_sha256')),{})
            retrieved=m.get('finished_at_utc') or r.get('retrieved_at_utc') or r.get('retrieved_at')
            requested=m.get('requested_at_utc') or r.get('requested_at_utc')
            semantics='manifest_finished_at_utc; not_first_publication' if m else 'source_literal_retrieved_at_utc; not_first_publication' if r.get('retrieved_at_utc') else 'source_literal_retrieved_at; not_first_publication' if r.get('retrieved_at') else 'retrieval_completion_unknown; requested_at_is_not_retrieved_at'
            params=r.get('parameters') or {};param=params.get('param') or parse_qs(urlparse(r.get('url') or '').query).get('param',[None])[0]
            start=end=None
            if param and len(param.split(','))>=4: start,end=param.split(',')[2:4]
            elif 'beg' in params:
                def iso(v):
                    v=str(v);return v[:4]+'-'+v[4:6]+'-'+v[6:8] if len(v)==8 else v
                start,end=iso(params['beg']),iso(params.get('end',''))
            db.execute('INSERT OR IGNORE INTO source_requests VALUES(?,?,?,?,?,?,?,?,?,?,?)',('audit:'+str(i),r.get('request_id'),r.get('url'),r.get('raw_project_relative_path'),r.get('source_sha256'),retrieved,requested,start,end,semantics,enc(r)))
        db.executescript('''
        CREATE VIEW market_reference AS SELECT m.*,
          EXISTS(SELECT 1 FROM conflicts c WHERE c.collection=m.collection AND c.symbol=m.symbol AND c.reference_date=m.trade_date AND c.field_name IN ('open','high','low','close')) AS has_price_source_conflict,
          EXISTS(SELECT 1 FROM conflicts c WHERE c.collection=m.collection AND c.symbol=m.symbol AND c.reference_date=m.trade_date AND c.field_name IN ('volume_raw','volume_provider_native')) AS has_volume_source_conflict
          FROM market_daily m WHERE collection='market_industry_oct21' AND provider='eastmoney';
        CREATE VIEW stock_raw_reference AS SELECT * FROM market_reference WHERE symbol='002414.SZ' AND adjustment='0';
        CREATE VIEW stock_qfq_reference AS SELECT * FROM market_reference WHERE symbol='002414.SZ' AND adjustment='1';
        CREATE VIEW approved_market_inputs AS SELECT * FROM market_daily WHERE model_input_approved=1;
        CREATE VIEW approved_chip_inputs AS SELECT * FROM chip_observations WHERE model_input_approved=1;
        ''')
        chip_dates={r[0]:r[1] for r in db.execute("SELECT actual_date,COUNT(*) FROM chip_observations WHERE collection='full_capture' AND accepted_capture=1 GROUP BY actual_date")}
        calendar_dates={r[0] for r in db.execute('SELECT trade_date FROM trading_calendar WHERE is_scheduled_open=1')}
        margin_dates={r['reference_date'] for r in db.execute("SELECT reference_date FROM source_records WHERE record_kind IN ('margin','margin_page2')")}
        flow_dates={r['reference_date'] for r in db.execute("SELECT reference_date FROM source_records WHERE record_kind='fund_flow_proxy'")}
        coverage=[]
        for day in sorted(bar_bydate):
            vals=db.execute('SELECT COUNT(*),COUNT(DISTINCT printf("%s|%s|%s|%s|%s|%s|%s|%s",profit_ratio_pct,average_cost_display,cost90_low,cost90_high,concentration90_pct,cost70_low,cost70_high,concentration70_pct)) FROM chip_observations WHERE actual_date=? AND accepted_capture=1',(day,)).fetchone()
            condition=db.execute('SELECT official_normal_state,official_upper_limit,official_lower_limit FROM trade_conditions WHERE trade_date=?',(day,)).fetchone()
            events=db.execute('SELECT COUNT(*) FROM events WHERE event_date=?',(day,)).fetchone()[0]
            row=(day,int(day<'2023-01-01'),1,1,1,int(day in chip_dates),vals[0],vals[1],int(condition is not None),int(condition is not None and condition[0] is not None),int(condition is not None and condition[1] is not None and condition[2] is not None),int(day in calendar_dates),int(day in margin_dates),int(day in flow_dates),events)
            db.execute('INSERT INTO daily_coverage VALUES('+','.join('?' for _ in row)+')',row)
        # Validate the new store and its source accounting before publishing either file.
        counts={r[0]:db.execute('SELECT COUNT(*) FROM '+q(r[0])).fetchone()[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name,passed in [('market_total',counts['market_daily']==15701+10413+11600),('research_dates',db.execute('SELECT COUNT(*) FROM daily_coverage WHERE is_warmup=0').fetchone()[0]==918),('raw_stock_dates',db.execute('SELECT COUNT(*) FROM stock_raw_reference').fetchone()[0]==1160),('chip_full_dates',db.execute("SELECT COUNT(DISTINCT actual_date) FROM chip_observations WHERE collection='full_capture' AND accepted_capture=1").fetchone()[0]==915),('all_chip_attempts',counts['chip_observations']==954),('accepted_chip_evidence_present',db.execute('SELECT COUNT(*) FROM chip_evidence_files e JOIN chip_observations c USING(observation_id) WHERE c.accepted_capture=1 AND e.exists_locally=0').fetchone()[0]==0),('market_retrieval_time_present',db.execute("SELECT COUNT(*) FROM market_daily WHERE collection='market_industry_oct21' AND retrieved_at IS NULL").fetchone()[0]==0),('condition_context_repair',len(context_corrections)==1 and context_corrections[0]['trade_date']=='2026-10-16'),('first_previous_close',db.execute("SELECT previous_close_date FROM trade_conditions WHERE trade_date='2023-01-03'").fetchone()[0]=='2022-12-30'),('filing_count',counts['filings']==312),('source_records_preserved',db.execute("SELECT COUNT(*) FROM source_records WHERE dataset_id='legacy_auxiliary'").fetchone()[0]==4094),('all_model_gates_closed',db.execute('SELECT COUNT(*) FROM approved_market_inputs').fetchone()[0]==0 and db.execute('SELECT COUNT(*) FROM approved_chip_inputs').fetchone()[0]==0),('no_foreign_key_errors',not db.execute('PRAGMA foreign_key_check').fetchall())]:
            checks.append({'check':name,'passed':passed});assert passed,name
        for payload, in db.execute('SELECT payload_json FROM source_records'):
            def no_blocked(obj):
                if isinstance(obj,dict): return not any(k in blocked for k in obj) and all(no_blocked(v) for v in obj.values())
                if isinstance(obj,list): return all(no_blocked(v) for v in obj)
                return True
            assert no_blocked(json.loads(payload))
        quarant.commit();isolated_count=quarant.execute('SELECT COUNT(*) FROM restricted_values').fetchone()[0]
        counts['metadata']=3
        for name,passed in [('all_request_times_mapped',db.execute('SELECT COUNT(*) FROM source_requests WHERE retrieved_at IS NULL').fetchone()[0]==0),('all_instrument_units_mapped',db.execute('SELECT COUNT(*) FROM market_daily WHERE canonical_symbol IS NULL OR price_unit IS NULL').fetchone()[0]==0)]:
            checks.append({'check':name,'passed':passed});assert passed,name
        build={'build_version':'unified-observation-v4','client_date':'2026-10-22','created_at_utc':datetime.now(timezone.utc).isoformat(),'baseline_main_sha256':before,'table_counts':counts,'restricted_values_isolated':isolated_count,'source_originals_unchanged':True,'context_corrections':context_corrections,'model_input_approved':False,'date_basis':'observed provider dates; official calendar only where separately present','core_scope':'raw observations, time and quality organization; no technical indicators or probability model'}
        db.execute('INSERT INTO metadata VALUES(?,?)',('build',enc(build)))
        db.execute('INSERT INTO metadata VALUES(?,?)',('restricted_field_definitions',enc(restrictions)))
        db.execute('INSERT INTO metadata VALUES(?,?)',('selection_policy',enc({'reference_collection':'market_industry_oct21','reference_provider':'eastmoney','purpose':'explicit browsing reference only; source conflicts preserved; not a model approval','no_provider_averaging':True})))
        db.commit();assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok';assert quarant.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        def export_query(sql,path):
            cur=db.execute(sql);write_csv(temp/path,[dict(r) for r in cur],[d[0] for d in cur.description])
        export_query('SELECT * FROM ingestion_sources','数据目录.csv')
        export_query('SELECT * FROM daily_coverage','逐日覆盖核对.csv')
        export_query('SELECT * FROM gaps ORDER BY priority,gap_id','缺口与待核清单.csv')
        export_query('SELECT project_relative_path,sha256,bytes,exists_locally FROM file_assets','原件相对路径与哈希.csv')
        export_query('SELECT * FROM chip_evidence_files','筹码证据文件.csv')
        export_query('SELECT request_key,request_id,url,raw_path,source_sha256,retrieved_at,requested_at,normalized_requested_start,normalized_requested_end,time_semantics FROM source_requests','来源请求与时间.csv')
        export_query('SELECT conflict_id,collection,symbol,reference_date,field_name,status,payload_json FROM conflicts','来源差异.csv')
        write_csv(temp/'默认查询行情.csv',[dict(r) for r in db.execute('SELECT * FROM market_reference')],[d[0] for d in db.execute('SELECT * FROM market_reference LIMIT 0').description])
        (temp/'核验结果.json').write_text(json.dumps(dict(build,checks=checks),ensure_ascii=False,indent=2))
        db.close();quarant.close();old.close();assert sha(MAIN)==before
        for p in temp.iterdir(): shutil.copy2(p,OUT/p.name)
    print(enc({'output':str(OUT),'market_source_rows':counts['market_daily'],'research_dates':918,'files_indexed':counts['file_assets'],'restricted_values_isolated':isolated_count,'checks_passed':len(checks),'main_unchanged':sha(MAIN)==before}))

if __name__=='__main__':main()
