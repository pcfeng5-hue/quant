"""Source-frozen causal close-only feature preparation. Never reads outcome tables."""
from pathlib import Path
from collections import Counter
from decimal import Decimal
from copy import deepcopy
import csv,hashlib,json,math,shutil,sqlite3,tempfile

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/市场环境输入准备_20261031'
CONTRACT=WORK/'contract.json'
RECEIPT=WORK/'registration_receipt.json'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def compact(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def ro(p):
    c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c
def csvout(path,rs):
    if not rs:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def table(c,name,rs):
    if not rs:return
    fields=list(rs[0]);types=[]
    for k in fields:
        v=next((r[k] for r in rs if r[k] is not None),None)
        typ='INTEGER' if isinstance(v,(int,bool)) else 'REAL' if isinstance(v,float) else 'TEXT'
        if k in ('model_input_approved','runtime_usable','historical_first_availability_certified'):typ+=' NOT NULL CHECK("'+k+'"=0)'
        types.append(typ)
    q=lambda x:'"'+x.replace('"','""')+'"'
    c.execute('CREATE TABLE '+q(name)+'('+','.join(q(k)+' '+t for k,t in zip(fields,types))+')')
    c.executemany('INSERT INTO '+q(name)+' VALUES('+','.join('?' for _ in fields)+')',[tuple(r[k] for k in fields) for r in rs])

def guard(cfg):
    if cfg!=read(CONTRACT):raise ValueError('Unsupported frozen preparation contract change')

def prepare(input_rows,ex_dates,cfg):
    guard(cfg)
    symbols=[cfg['stock_symbol']]+cfg['index_symbols'];providers=[cfg['primary_provider'],cfg['comparison_provider']]
    byseries={(s,p):[] for s in symbols for p in providers};ids=set()
    for r in input_rows:
        key=(r['canonical_symbol'],r['provider'])
        if key not in byseries or r['observation_id'] in ids:raise ValueError('Unexpected series or duplicate observation ID')
        if r['collection']!=cfg['collection'] or r['adjustment']!=cfg['adjustment']:raise ValueError('Wrong source collection or adjustment')
        if not isinstance(r['close'],(int,float)) or not math.isfinite(r['close']) or r['close']<=0:raise ValueError('Nonpositive or nonfinite close')
        if not cfg['source_start']<=r['trade_date']<=cfg['source_last_date']:raise ValueError('Source date outside frozen snapshot')
        expected_unit='CNY_per_share' if r['canonical_symbol']==cfg['stock_symbol'] else 'index_points'
        if r['price_unit']!=expected_unit:raise ValueError('Unexpected price unit')
        ids.add(r['observation_id']);byseries[key].append(r)
    dates=None
    for key,rs in byseries.items():
        current=[r['trade_date'] for r in rs]
        if not current or current!=sorted(set(current)):raise ValueError('Empty, duplicate, or unordered series dates')
        if dates is None:dates=current
        elif dates!=current:raise ValueError('Provider/symbol date domains not aligned')
    primary={s:byseries[(s,cfg['primary_provider'])] for s in symbols}
    conflicts=[];bad_ids=set()
    for s in symbols:
        for a,b in zip(primary[s],byseries[(s,cfg['comparison_provider'])]):
            if Decimal(str(a['close']))!=Decimal(str(b['close'])):
                bad_ids.add(a['observation_id'])
                conflicts.append(dict(canonical_symbol=s,trade_date=a['trade_date'],primary_observation_id=a['observation_id'],comparison_observation_id=b['observation_id'],primary_close=a['close'],comparison_close=b['close'],difference_decimal=str(Decimal(str(a['close']))-Decimal(str(b['close']))),status='unadjudicated_primary_not_truth'))
    catalog=[]
    for s in cfg['index_symbols']:
        for name,formula in cfg['index_formula_definitions'].items():
            catalog.append(dict(feature_id=s+':'+name,role='candidate_context_feature',subject_symbol=s,formula=formula,value_unit='fraction',preparation_only=1,model_input_approved=0,runtime_usable=0))
    auxid=cfg['stock_symbol']+':past_return_5_aux'
    catalog.append(dict(feature_id=auxid,role='auxiliary_calculation',subject_symbol=cfg['stock_symbol'],formula=cfg['auxiliary_stock_formula'],value_unit='fraction',preparation_only=1,model_input_approved=0,runtime_usable=0))
    for s in cfg['index_symbols']:
        catalog.append(dict(feature_id=cfg['stock_symbol']+':minus_'+s+':past_return_5',role='candidate_context_feature',subject_symbol=cfg['stock_symbol'],formula=cfg['relative_formula'],value_unit='difference_of_return_fractions',preparation_only=1,model_input_approved=0,runtime_usable=0))
    features=[];dependencies=[];lookup={};deps_lookup={};roles={r['feature_id']:r['role'] for r in catalog}
    def emit(day,fid,value,dependencies_used,not_ready_reason=None):
        dependencies_used=sorted({r['observation_id']:r for r in dependencies_used}.values(),key=lambda r:(r['trade_date'],r['canonical_symbol']))
        conflicts_used=[r for r in dependencies_used if r['observation_id'] in bad_ids]
        reason=not_ready_reason or ('CLOSE_SOURCE_CONFLICT' if conflicts_used else 'ENGINEERING_READY_NOT_FORMAL_PIT')
        ready=int(value is not None and not not_ready_reason and not conflicts_used)
        row=dict(signal_date=day,feature_id=fid,role=roles[fid],diagnostic_value=value,engineering_value=value if ready else None,engineering_ready=ready,status=reason,dependency_n=len(dependencies_used),dependency_first_date=min((r['trade_date'] for r in dependencies_used),default=None),max_dependency_date=max((r['trade_date'] for r in dependencies_used),default=None),close_source_conflict_n=len(conflicts_used),historical_first_availability_certified=0,model_input_approved=0,runtime_usable=0)
        features.append(row);lookup[(day,fid)]=row;deps_lookup[(day,fid)]=dependencies_used
        for j,r in enumerate(dependencies_used):dependencies.append(dict(signal_date=day,feature_id=fid,dependency_order=j,dependency_symbol=r['canonical_symbol'],dependency_date=r['trade_date'],observation_id=r['observation_id'],source_close=r['close'],source_sha256=r['source_sha256'],source_close_conflict=int(r['observation_id'] in bad_ids)))
    for s in cfg['index_symbols']:
        history=[]
        for r in primary[s]:
            day=r['trade_date']
            if day>=cfg['calculation_start']:history.append(r)
            for name in cfg['index_formula_definitions']:
                fid=s+':'+name
                if day<cfg['calculation_start']:emit(day,fid,None,[],'BEFORE_CALCULATION_START');continue
                if name.startswith('past_return_'):
                    n=int(name.rsplit('_',1)[1])
                    if len(history)<=n:emit(day,fid,None,[],'INSUFFICIENT_INDEX_HISTORY');continue
                    used=[history[-n-1],history[-1]];value=used[-1]['close']/used[0]['close']-1
                else:
                    n=cfg['ma_observations_including_current']
                    if len(history)<n:emit(day,fid,None,[],'INSUFFICIENT_INDEX_HISTORY');continue
                    used=history[-n:];value=r['close']/(math.fsum(x['close'] for x in used)/n)-1
                emit(day,fid,value,used)
    segment=[];segment_start=None;stock_segments=[]
    for r in primary[cfg['stock_symbol']]:
        day=r['trade_date']
        if day<cfg['calculation_start']:
            emit(day,auxid,None,[],'BEFORE_CALCULATION_START');stock_segments.append(dict(trade_date=day,segment_start=None,segment_bars=0));continue
        if not segment or day in ex_dates:segment=[];segment_start=day
        segment.append(r);stock_segments.append(dict(trade_date=day,segment_start=segment_start,segment_bars=len(segment)))
        if len(segment)<=5:emit(day,auxid,None,[],'INSUFFICIENT_SAME_SEGMENT_STOCK_HISTORY');continue
        used=[segment[-6],segment[-1]];emit(day,auxid,used[-1]['close']/used[0]['close']-1,used)
    for s in cfg['index_symbols']:
        fid=cfg['stock_symbol']+':minus_'+s+':past_return_5';indexfid=s+':past_return_5'
        for day in dates:
            a,b=lookup[(day,auxid)],lookup[(day,indexfid)]
            if a['diagnostic_value'] is None or b['diagnostic_value'] is None:
                reason='BEFORE_CALCULATION_START' if day<cfg['calculation_start'] else 'COMPONENT_HISTORY_NOT_READY'
                emit(day,fid,None,[],reason);continue
            emit(day,fid,a['diagnostic_value']-b['diagnostic_value'],deps_lookup[(day,auxid)]+deps_lookup[(day,indexfid)])
    features.sort(key=lambda r:(r['signal_date'],r['feature_id']));dependencies.sort(key=lambda r:(r['signal_date'],r['feature_id'],r['dependency_order']))
    wide=[]
    for day in dates:
        row={'signal_date':day}
        for f in catalog:row[f['feature_id']]=lookup[(day,f['feature_id'])]['engineering_value']
        row.update(model_input_approved=0,runtime_usable=0);wide.append(row)
    coverage=[]
    for f in catalog:
        for scope,start,end in [('all_saved',cfg['source_start'],cfg['source_last_date']),('research',cfg['research_start'],cfg['source_last_date']),('development','2023-01-03','2024-12-31')]:
            rs=[r for r in features if r['feature_id']==f['feature_id'] and start<=r['signal_date']<=end]
            coverage.append(dict(feature_id=f['feature_id'],role=f['role'],scope=scope,dates=len(rs),diagnostic_computed=sum(r['diagnostic_value'] is not None for r in rs),engineering_ready=sum(r['engineering_ready'] for r in rs),source_conflict_quarantined=sum(r['status']=='CLOSE_SOURCE_CONFLICT' for r in rs),history_not_ready=sum(r['diagnostic_value'] is None for r in rs),formal_model_input_approved=0))
    return dict(input_closes=input_rows,feature_catalog=catalog,close_source_conflicts=conflicts,features=features,feature_dependencies=dependencies,stock_segments=stock_segments,wide_engineering_values=wide,coverage=coverage)

def validate(result,source,ex_dates,cfg):
    checks=[]
    def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
    fs=result['features'];ds=result['feature_dependencies'];catalog=result['feature_catalog']
    ck('sixteen_definitions_fifteen_candidates_one_aux',len(catalog)==16 and sum(r['role']=='candidate_context_feature' for r in catalog)==15)
    ck('all_original_dates_retained_for_every_definition',len(fs)==1160*16 and len({(r['signal_date'],r['feature_id']) for r in fs})==len(fs))
    ck('research_feature_rows_14688',sum(r['signal_date']>=cfg['research_start'] for r in fs)==918*16)
    ck('all_dependencies_no_later_than_signal',all(r['dependency_date']<=r['signal_date'] for r in ds))
    ck('all_computed_values_finite',all(r['diagnostic_value'] is None or math.isfinite(r['diagnostic_value']) for r in fs))
    ck('engineering_mask_matches_value_and_reason',all((r['engineering_value'] is not None)==bool(r['engineering_ready']) and (r['status']=='ENGINEERING_READY_NOT_FORMAL_PIT')==bool(r['engineering_ready']) for r in fs))
    ck('all_formal_gates_closed',all(r['model_input_approved']==r['runtime_usable']==r['historical_first_availability_certified']==0 for r in fs))
    depcounts=Counter((r['signal_date'],r['feature_id']) for r in ds)
    ck('exact_dependency_counts',all(depcounts[(r['signal_date'],r['feature_id'])]==r['dependency_n'] for r in fs))
    ck('no_price_conflict_silently_promoted',all(r['engineering_value'] is None and r['close_source_conflict_n']>0 for r in fs if r['status']=='CLOSE_SOURCE_CONFLICT'))
    ck('every_conflicted_dependency_forces_abstention',all(r['engineering_value'] is None and r['engineering_ready']==0 and r['status']=='CLOSE_SOURCE_CONFLICT' for r in fs if r['close_source_conflict_n']>0))
    ck('all_usable_values_retain_diagnostic',all(r['engineering_value']==r['diagnostic_value'] for r in fs if r['engineering_ready']))
    starts={r['trade_date']:r for r in result['stock_segments']}
    ck('all_three_known_ex_dates_restart_stock_history',all(starts[d]['segment_start']==d and starts[d]['segment_bars']==1 for d in ex_dates))
    aux=cfg['stock_symbol']+':past_return_5_aux'
    auxrows={r['signal_date']:r for r in fs if r['feature_id']==aux}
    ck('stock_raw_returns_do_not_bridge_known_ex_dates',all(auxrows[d]['diagnostic_value'] is None if v['segment_bars']<=5 else auxrows[d]['diagnostic_value'] is not None for d,v in starts.items()))
    ck('returns_use_exactly_two_endpoint_closes',all(r['dependency_n']==2 for r in fs if ':past_return_' in r['feature_id'] and ':minus_' not in r['feature_id'] and r['diagnostic_value'] is not None))
    ck('ma20_uses_twenty_closes',all(r['dependency_n']==20 for r in fs if r['feature_id'].endswith('close_over_ma20_minus_one') and r['diagnostic_value'] is not None))
    ck('relative_uses_four_closes',all(r['dependency_n']==4 for r in fs if ':minus_' in r['feature_id'] and r['diagnostic_value'] is not None))
    for day in ['2022-12-30','2023-06-20','2024-05-24','2026-02-11','2026-09-22']:
        smaller=prepare([r for r in source if r['trade_date']<=day],{d for d in ex_dates if d<=day},cfg)
        ck('prefix_invariance_'+day,smaller['features']==[r for r in fs if r['signal_date']<=day] and smaller['feature_dependencies']==[r for r in ds if r['signal_date']<=day])
    changed=deepcopy(source)
    for r in changed:
        if r['trade_date']>'2024-12-31':r['close']+=.123
    mutated=prepare(changed,ex_dates,cfg)
    ck('future_price_poison_does_not_change_development_features',[r for r in mutated['features'] if r['signal_date']<='2024-12-31']==[r for r in fs if r['signal_date']<='2024-12-31'])
    ck('no_labels_probabilities_or_event_countdowns_in_output',set(result)=={'input_closes','feature_catalog','close_source_conflicts','features','feature_dependencies','stock_segments','wide_engineering_values','coverage'} and all('event' not in r['feature_id'] for r in catalog))
    rejected=0
    for mutation in ['duplicate_id','duplicate_date','misaligned_dates','missing_series','bad_price','wrong_unit','wrong_adjustment']:
        rows=deepcopy(source)
        if mutation=='duplicate_id':rows.append(dict(rows[0]))
        elif mutation=='duplicate_date':new=dict(rows[0]);new['observation_id']='unique_duplicate_date';rows.append(new)
        elif mutation=='misaligned_dates':rows.pop(0)
        elif mutation=='missing_series':rows=[r for r in rows if (r['canonical_symbol'],r['provider'])!=(cfg['stock_symbol'],cfg['comparison_provider'])]
        elif mutation=='bad_price':rows[0]['close']=float('nan')
        elif mutation=='wrong_unit':rows[0]['price_unit']='CNY_total_return'
        else:rows[0]['adjustment']='1'
        try:prepare(rows,ex_dates,cfg)
        except ValueError:rejected+=1
    ck('invalid_source_domains_prices_and_units_rejected',rejected==7)
    rejected=0
    for k,v in [('return_lags',[1,10,20]),('primary_provider','tencent'),('runtime_usable',True),('event_countdown_features_generated',True)]:
        c=deepcopy(cfg);c[k]=v
        try:guard(c)
        except ValueError:rejected+=1
    ck('frozen_spec_mutations_rejected',rejected==4)
    return checks

def main():
    cfg=read(CONTRACT);receipt=read(RECEIPT);guard(cfg)
    if receipt['contract_sha256']!=sha(CONTRACT) or receipt['producer_code_sha256']!=sha(Path(__file__).resolve()):raise ValueError('Frozen registration fingerprint mismatch')
    protected=receipt['protected_source_sha256'];before={p:sha(ROOT/p) for p in protected}
    if before!=protected:raise ValueError('Protected sources changed since registration')
    with ro(ROOT/cfg['source_database']) as c:
        source=[dict(r) for r in c.execute("SELECT observation_id,collection,canonical_symbol,provider,adjustment,trade_date,close,price_unit,source_sha256,source_request_id,retrieved_at,input_path,input_row_index FROM market_daily WHERE collection='market_industry_oct21' AND adjustment='0' AND provider IN ('eastmoney','tencent') AND canonical_symbol IN ('000001.SH','399001.SZ','399967.SZ','002414.SZ') ORDER BY provider,canonical_symbol,trade_date")]
        actions=[dict(r) for r in c.execute('SELECT event_id,symbol,ex_date FROM corporate_actions ORDER BY ex_date')]
    if len(source)!=8*cfg['expected_dates_per_series']:raise ValueError('Unexpected snapshot coverage')
    ex_dates={r['ex_date'] for r in actions if r['symbol']==cfg['stock_symbol']}
    if ex_dates!={'2023-06-20','2024-05-24','2026-09-22'}:raise ValueError('Unexpected corporate-action boundary set')
    result=prepare(source,ex_dates,cfg);checks=validate(result,source,ex_dates,cfg)
    after={p:sha(ROOT/p) for p in protected}
    if after!=before:raise ValueError('Protected input was modified')
    checks.append(dict(check='all_registered_inputs_unchanged',passed=True,details=after))
    metadata=dict(contract=cfg,registration=receipt,source_sha256=before,source_rows=len(source),observed_dates=1160,research_dates=918,model_input_approved=False,runtime_usable=False,new_models_scored=0,previous_research_variants=15,candidate_definitions_prepared=15,auxiliary_definitions_prepared=1,future_targets_read_or_generated=False)
    OUT.mkdir(parents=True,exist_ok=True)
    names={'input_closes':'输入收盘及来源.csv','feature_catalog':'特征公式字典.csv','close_source_conflicts':'收盘差异台账.csv','features':'逐日市场环境特征_工程准备.csv','feature_dependencies':'逐值计算依赖.csv','stock_segments':'个股价格分段.csv','wide_engineering_values':'日期宽表_未获正式准入.csv','coverage':'特征覆盖与隔离.csv'}
    with tempfile.TemporaryDirectory(prefix='market_context_',dir=WORK) as td:
        td=Path(td)
        for key,name in names.items():csvout(td/name,result[key])
        with sqlite3.connect(td/'市场环境工程输入.sqlite') as c:
            for name,rs in result.items():table(c,name,rs)
            c.execute('CREATE UNIQUE INDEX unique_feature_date ON features(signal_date,feature_id)')
            c.execute('CREATE UNIQUE INDEX unique_dependency ON feature_dependencies(signal_date,feature_id,dependency_order)')
            c.execute('CREATE VIEW engineering_ready_candidates AS SELECT * FROM features WHERE engineering_ready=1 AND role="candidate_context_feature"')
            c.execute('CREATE VIEW approved_market_context_inputs AS SELECT * FROM features WHERE model_input_approved=1 AND runtime_usable=1')
            c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT)');c.execute('INSERT INTO metadata VALUES(?,?)',('run',enc(metadata)))
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite validation failed')
        (td/'冻结工程规格.json').write_text(enc(cfg));(td/'运行与来源记录.json').write_text(enc(metadata))
        (td/'实现核验.json').write_text(enc(dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,producer_code_sha256=sha(Path(__file__).resolve()),contract_sha256=sha(CONTRACT),source_sha256_before=before,source_sha256_after=after)))
        for p in td.iterdir():shutil.copy2(p,OUT/p.name)
    print(enc(dict(output=str(OUT),checks=len(checks),feature_rows=len(result['features']),dependency_rows=len(result['feature_dependencies']),close_conflicts=result['close_source_conflicts'],research_coverage=[r for r in result['coverage'] if r['scope']=='research'],new_models_scored=0)))

if __name__=='__main__':main()
