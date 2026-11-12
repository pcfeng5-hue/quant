#!/usr/bin/env python3
"""Independent stdlib exact-arithmetic audit of the one market-state model.

Expected results are reconstructed below without importing production code.
Production is imported only at the end for rejection and poisoning probes.
All target SQL is bounded to 2023--2024. Later DB files are hashed, not queried.
"""
from __future__ import annotations
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext
from collections import Counter, defaultdict
from datetime import datetime
from copy import deepcopy
import hashlib, json, math, sqlite3, importlib.util, csv

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
PRODUCER=ROOT/'work/market_model_oct31/run_market_model.py'
CONTRACT=ROOT/'work/market_model_oct31/contract.json'
RECEIPT=ROOT/'work/market_model_oct31/registration_receipt.json'
OUT=ROOT/'outputs/市场环境候选验证_20261031'
FIRST,LAST='2023-01-03','2024-12-31'
FEATURE='399001.SZ:close_over_ma20_minus_one'
M0,M3='M0_laplace_constant','M3_shenzhen_ma20_group_shrinkage'
GROUPS=['above_ma20','at_or_below_ma20']
checks=[]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def ro(p):
    c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c
def ck(name,ok,details=None):
    checks.append(dict(check=name,passed=bool(ok),details=details))
    if not ok:raise AssertionError(name)
def frac(x):return F(str(x))
def D(x):
    if isinstance(x,F):return Decimal(x.numerator)/Decimal(x.denominator)
    return Decimal(str(x))
def same(a,b,tol=2e-12):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(same(a[k],b[k],tol) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y,tol) for x,y in zip(a,b))
    if isinstance(a,(float,F,Decimal)) and isinstance(b,(int,float)):
        return math.isfinite(float(a)) and math.isfinite(b) and abs(float(a)-b)<=tol
    return a==b
def score_ind(rows):
    n=len(rows)
    if not n:return dict(n=0,positive_count=0,zero_count=0,negative_count=0,positive_frequency=None,mean_prediction=None,brier=None,log_loss=None)
    k=sum(r['y'] for r in rows);z=sum(r['zero_change'] for r in rows)
    with localcontext() as ctx:
        ctx.prec=60
        # All fitted p are strictly internal, so registered clipping does not bind.
        logs=[-(D(r['p']) if r['y'] else 1-D(r['p'])).ln() for r in rows]
        logloss=sum(logs,Decimal())/n
    return dict(n=n,positive_count=k,zero_count=z,negative_count=n-k-z,
                positive_frequency=F(k,n),mean_prediction=sum((r['p'] for r in rows),F())/n,
                brier=sum(((r['p']-r['y'])**2 for r in rows),F())/n,log_loss=logloss)

def expected_results(labels,features,anchors,foldspec):
    # Features were separately rederived from original price strings, and every
    # actual row is ready. Exact sign comparison avoids a float group threshold.
    states={r['signal_date']:r['expected_state'] for r in features}
    values={r['signal_date']:r['engineering_value'] for r in features}
    joined=[dict(r,market_state=states[r['signal_date']],market_value=values[r['signal_date']],
                 y=int(r['outcome_sign']=='price_change_gt_0'),zero_change=int(r['outcome_sign']=='price_change_eq_0'),
                 feature_status='ENGINEERING_READY_NOT_FORMAL_PIT') for r in labels]
    lookup={r['signal_date']:r for r in joined}
    grid=set(anchors[::5]);predictions=[];fitted=[];membership=[];ledger=[];folds=[]
    for f in foldspec:
        fid,start,end=f['id'],f['validation_start'],f['validation_end']
        candidates=[r for r in joined if r['signal_date']<start]
        matured=[r for r in candidates if r['outcome_observation_date']<start]
        train=[r for r in matured if r['market_state'] is not None]
        n=len(train);k=sum(r['y'] for r in train);z=sum(r['zero_change'] for r in train)
        for r in candidates:
            reason='TRAIN_LABEL_NOT_MATURE' if r['outcome_observation_date']>=start else 'TRAIN_MARKET_FEATURE_NOT_READY' if r['market_state'] is None else 'TRAIN_USED'
            ledger.append(dict(fold_id=fid,role='training',signal_date=r['signal_date'],label_end=r['outcome_observation_date'],reason=reason,feature_status=r['feature_status']))
        for r in train:membership.append(dict(fold_id=fid,signal_date=r['signal_date'],label_end=r['outcome_observation_date'],market_state=r['market_state'],market_value=r['market_value'],y=r['y'],zero_change=r['zero_change']))
        model=None
        if n>=100:
            p0=F(k+1,n+2);latest=max(r['outcome_observation_date'] for r in train)
            base=dict(fold_id=fid,model_id=M0,group_id='ALL',training_n=n,training_positive=k,training_zero=z,group_n=n,group_positive=k,group_zero=z,group_negative=n-k-z,prior_p=None,p=p0,prior_only=0,group_n_lt20=int(n<20),latest_training_label_end=latest)
            fitted.append(base);groups={}
            for g in GROUPS:
                rs=[r for r in train if r['market_state']==g];gn=len(rs);gk=sum(r['y'] for r in rs);gz=sum(r['zero_change'] for r in rs)
                p=(gk+20*p0)/(gn+20) if gn else p0
                groups[g]=dict(p=p,n=gn)
                fitted.append(dict(base,model_id=M3,group_id=g,group_n=gn,group_positive=gk,group_zero=gz,group_negative=gn-gk-gz,prior_p=p0,p=p,prior_only=int(gn==0),group_n_lt20=int(gn<20)))
            model=(p0,groups,latest)
        counts=Counter();va=[a for a in anchors if start<=a<=end]
        for a in va:
            r=lookup.get(a)
            reason='NO_REGISTERED_LABEL' if r is None else 'LABEL_CROSSES_FOLD_END' if r['outcome_observation_date']>end else 'MARKET_FEATURE_NOT_READY' if r['market_state'] is None else 'INSUFFICIENT_JOINT_TRAINING' if model is None else 'EVALUATED'
            counts[reason]+=1
            ledger.append(dict(fold_id=fid,role='validation',signal_date=a,label_end=r['outcome_observation_date'] if r else None,reason=reason,feature_status=r['feature_status'] if r else None))
            if reason!='EVALUATED':continue
            p0,groups,latest=model;cell=groups[r['market_state']]
            for mid,p,gn in [(M0,p0,n),(M3,cell['p'],cell['n'])]:
                predictions.append(dict(fold_id=fid,model_id=mid,signal_date=a,entry_observation_date=r['entry_observation_date'],outcome_observation_date=r['outcome_observation_date'],market_state=r['market_state'],market_value=r['market_value'],y=r['y'],zero_change=r['zero_change'],p=p,training_n=n,group_training_n=gn,prior_only=int(gn==0),latest_training_label_end=latest,fixed_every_fifth_anchor=int(a in grid),model_input_approved=0,runtime_usable=0))
        folds.append(dict(fold_id=fid,validation_start=start,validation_end=end,training_candidates=len(candidates),training_not_mature=len(candidates)-len(matured),training_mature=len(matured),training_feature_missing=len(matured)-len(train),training_used=n,latest_training_label_end=model[2] if model else None,validation_anchors=len(va),evaluated_dates=counts['EVALUATED'],no_registered_label=counts['NO_REGISTERED_LABEL'],label_crosses_fold_end=counts['LABEL_CROSSES_FOLD_END'],feature_not_ready=counts['MARKET_FEATURE_NOT_READY'],insufficient_training=counts['INSUFFICIENT_JOINT_TRAINING']))
    metrics=[];comparisons=[];calibration=[];paired=[]
    for fid in [f['id'] for f in foldspec]+['POOLED']:
        for subset in ['all_overlapping','fixed_every_fifth_anchor']:
            target=[r for r in predictions if (fid=='POOLED' or r['fold_id']==fid) and (subset=='all_overlapping' or r['fixed_every_fifth_anchor'])]
            groups={m:[r for r in target if r['model_id']==m] for m in [M0,M3]};scores={m:score_ind(rs) for m,rs in groups.items()}
            for m,s in scores.items():metrics.append(dict(fold_id=fid,subset=subset,model_id=m,**s))
            a,b=scores[M0],scores[M3]
            comparisons.append(dict(fold_id=fid,subset=subset,n=a['n'],brier_M0=a['brier'],brier_M3=b['brier'],brier_delta_M3_minus_M0=b['brier']-a['brier'] if a['n'] else None,logloss_delta_M3_minus_M0=b['log_loss']-a['log_loss'] if a['n'] else None,promotion_approved=0))
            if subset!='all_overlapping':continue
            for m,rs in groups.items():
                for j in range(5):
                    lo,hi=F(j,5),F(j+1,5);selected=[r for r in rs if lo<=r['p'] and (r['p']<hi or j==4 and r['p']<=hi)]
                    s=score_ind(selected)
                    calibration.append(dict(fold_id=fid,model_id=m,bin_low=lo,bin_high=hi,n=s['n'],positive_count=s['positive_count'],zero_count=s['zero_count'],negative_count=s['negative_count'],mean_prediction=s['mean_prediction'],observed_positive_frequency=s['positive_frequency'],observed_minus_prediction=s['positive_frequency']-s['mean_prediction'] if s['n'] else None,empty_bin=int(not s['n']),sparse_note='empty' if not s['n'] else 'n_lt20_not_reliability_test' if s['n']<20 else 'n_does_not_certify_calibration',calibration_transform_fitted=0))
    ix={(r['signal_date'],r['model_id']):r for r in predictions}
    for r in predictions:
        if r['model_id']!=M3:continue
        b=ix[r['signal_date'],M0]
        with localcontext() as ctx:
            ctx.prec=60
            logdelta=-(D(r['p']) if r['y'] else 1-D(r['p'])).ln()+(D(b['p']) if b['y'] else 1-D(b['p'])).ln()
        paired.append(dict(fold_id=r['fold_id'],signal_date=r['signal_date'],y=r['y'],p_M0=b['p'],p_M3=r['p'],brier_delta=(r['p']-r['y'])**2-(b['p']-b['y'])**2,logloss_delta=logdelta,fixed_every_fifth_anchor=r['fixed_every_fifth_anchor']))
    return dict(predictions=predictions,fitted=fitted,membership=membership,ledger=ledger,folds=folds,metrics=metrics,comparisons=comparisons,calibration=calibration,paired_loss=paired)

def main():
    cfg=read(CONTRACT);receipt=read(RECEIPT)
    source_before={p:sha(ROOT/p) for p in receipt['protected_source_sha256']}
    producer_hash=sha(PRODUCER);contract_hash=sha(CONTRACT)
    ck('25_protected_source_hashes_match_registration',len(source_before)==25 and source_before==receipt['protected_source_sha256'])
    ck('frozen_code_and_contract_fingerprints',receipt['contract_sha256']==contract_hash and receipt['producer_code_sha256']==producer_hash and read(OUT/'预登记研究协议.json')==cfg)
    ck('local_registration_before_output_not_external_timestamp',receipt['before_this_candidate_results'] is True and receipt['not_an_external_timestamped_registration'] is True and datetime.fromisoformat(receipt['registered_at_utc']).timestamp()<=min(p.stat().st_mtime for p in [OUT/'市场状态候选开发验证.sqlite',OUT/'逐日概率与实际结果_仅开发期.csv']))
    ck('unique_single_hypothesis_and_unchanged_research_only_parameters',cfg['feature_id']==FEATURE and cfg['models']==[M0,M3] and cfg['shrinkage_lambda']==20 and cfg['minimum_training_rows']==100 and cfg['horizon_observed_sessions']==5 and cfg['development_start']==FIRST and cfg['development_end']==LAST and not cfg['other_prepared_columns_scored_in_this_run'] and not cfg['parameter_or_index_or_window_search'])
    log=read(ROOT/'work/market_model_oct31/cumulative_registration.json')
    ck('cumulative_16_retains_previous_15_and_negative_outcomes',log['previous_registered_variants']==15 and log['new_registered_model_variants']==1 and log['cumulative_registered_variants']==16 and log['old_negative_results_retained'] and cfg['cumulative_registered_variants_after_this_run']==16)
    with ro(ROOT/cfg['input_anchors']) as c:
        raw=[dict(r) for r in c.execute("SELECT * FROM input_bars WHERE trade_date BETWEEN '2022-01-04' AND '2024-12-31' ORDER BY trade_date")]
        exdates=[r['ex_date'] for r in c.execute("SELECT * FROM corporate_action_boundaries WHERE ex_date<='2024-12-31' ORDER BY ex_date")]
    anchors=[r['trade_date'] for r in raw if FIRST<=r['trade_date']<=LAST]
    ck('484_original_observed_anchors_and_two_known_ex_dates',len(anchors)==484 and anchors==sorted(set(anchors)) and exdates==['2023-06-20','2024-05-24'])
    with ro(ROOT/cfg['input_labels']) as c:
        source_labels=[dict(r) for r in c.execute("SELECT * FROM development_price_outcomes WHERE signal_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY signal_date")]
        source_exclusions=[dict(r) for r in c.execute("SELECT * FROM excluded_anchors WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date")]
    labels=[];expected_full_labels=[];exclusions=[]
    for i,r in enumerate(raw):
        d=r['trade_date']
        if d not in anchors:continue
        if i+5>=len(raw):exclusions.append(dict(trade_date=d,reason='OUTCOME_END_CROSSES_DEVELOPMENT_BOUNDARY'));continue
        entry,end=raw[i+1],raw[i+5]
        if any(entry['trade_date']<=x<=end['trade_date'] for x in exdates):exclusions.append(dict(trade_date=d,reason='KNOWN_EX_DATE_WITHIN_PRICE_WINDOW'));continue
        change=frac(end['close'])/frac(entry['open'])-1
        sign='price_change_gt_0' if change>0 else 'price_change_lt_0' if change<0 else 'price_change_eq_0'
        small=dict(signal_date=d,entry_observation_date=entry['trade_date'],outcome_observation_date=end['trade_date'],outcome_sign=sign,horizon_observed_sessions=5)
        labels.append(small)
        expected_full_labels.append(dict(signal_date=d,entry_observation_date=entry['trade_date'],outcome_observation_date=end['trade_date'],entry_open_raw=entry['open'],outcome_close_raw=end['close'],horizon_observed_sessions=5,price_change_fraction=change,outcome_sign=sign,entry_source_observation_id=entry['observation_id'],outcome_source_observation_id=end['observation_id'],daily_status_certified=0,execution_modelled=0,model_input_approved=0,scope='development_retrospective_price_only'))
    ck('469_labels_independently_reconstructed_from_raw_open_close',len(labels)==469 and same(expected_full_labels,source_labels),{'target_queries_bounded_to':LAST})
    ck('15_label_exclusions_and_all_development_anchors_accounted',len(exclusions)==15 and same(exclusions,source_exclusions) and len(labels)+len(exclusions)==len(anchors))
    with ro(ROOT/cfg['input_features']) as c:
        features=[dict(r) for r in c.execute("SELECT signal_date,feature_id,role,engineering_value,engineering_ready,status,dependency_n,dependency_first_date,max_dependency_date,close_source_conflict_n,historical_first_availability_certified,model_input_approved,runtime_usable FROM features WHERE feature_id=? AND signal_date BETWEEN ? AND ? ORDER BY signal_date",(FEATURE,FIRST,LAST))]
        deps=[dict(r) for r in c.execute("SELECT * FROM feature_dependencies WHERE feature_id=? AND signal_date BETWEEN ? AND ? ORDER BY signal_date,dependency_order",(FEATURE,FIRST,LAST))]
        obs=[dict(r) for r in c.execute("SELECT * FROM input_closes WHERE canonical_symbol='399001.SZ' AND provider='eastmoney' AND trade_date BETWEEN '2022-06-01' AND '2024-12-31' ORDER BY trade_date")]
    manifest=read(ROOT/'work/market_industry_oct22/manifest.json')
    sources={r['provider']:r for r in manifest['results'] if r.get('symbol')=='399001.SZ' and r.get('adjustment')=='0' and r.get('provider') in ['eastmoney','tencent']}
    ck('chosen_index_both_original_raw_response_hashes',set(sources)=={'eastmoney','tencent'} and all(sha(Path(r['raw_path']))==r['sha256'] for r in sources.values()))
    em_payload=read(Path(sources['eastmoney']['raw_path']));tx_payload=read(Path(sources['tencent']['raw_path']))
    em={};tx={}
    for row in em_payload['data']['klines']:
        fields=row.split(',');d=fields[0]
        if '2022-06-01'<=d<=LAST:assert d not in em;em[d]=F(fields[2])
    for fields in tx_payload['data']['sz399001']['day']:
        d=fields[0]
        if '2022-06-01'<=d<=LAST:assert d not in tx;tx[d]=F(fields[2])
    calendar=sorted(em);omap={r['observation_id']:r for r in obs}
    ck('original_provider_closes_positive_matching_and_no_close_conflicts',len(em)==len(tx)==len(obs) and set(em)==set(tx) and all(em[d]>0 and em[d]==tx[d] for d in em))
    ck('index_source_observations_unique_exact_raw_identity',len(omap)==len(obs) and [r['trade_date'] for r in obs]==calendar and all(frac(r['close'])==em[r['trade_date']] and r['canonical_symbol']=='399001.SZ' and r['provider']=='eastmoney' and r['collection']=='market_industry_oct21' and r['adjustment']=='0' and r['price_unit']=='index_points' and r['source_sha256']==sources['eastmoney']['sha256'] for r in obs))
    bydate=defaultdict(list)
    for dep in deps:bydate[dep['signal_date']].append(dep)
    ck('484_selected_rows_and_9680_unique_actual_dependencies',len(features)==484 and [r['signal_date'] for r in features]==anchors and len(deps)==9680 and len({(r['signal_date'],r['dependency_order']) for r in deps})==9680)
    precise_features=[];max_error=0.;trace_ok=True;flags_ok=True
    for fr in features:
        d=fr['signal_date'];i=calendar.index(d);window=calendar[i-19:i+1];ds=bydate[d]
        value=em[d]/(sum((em[x] for x in window),F())/20)-1
        max_error=max(max_error,abs(float(value)-fr['engineering_value']))
        trace_ok &= len(window)==20 and [x['dependency_order'] for x in ds]==list(range(20)) and [x['dependency_date'] for x in ds]==window and fr['dependency_first_date']==window[0] and fr['max_dependency_date']==d and fr['dependency_n']==20
        for dep in ds:
            original=omap.get(dep['observation_id'])
            trace_ok &= original is not None and dep['feature_id']==FEATURE and dep['dependency_symbol']=='399001.SZ' and dep['dependency_date']<=d and dep['source_close_conflict']==0 and original['trade_date']==dep['dependency_date'] and original['close']==dep['source_close'] and original['source_sha256']==dep['source_sha256']
        flags_ok &= fr['feature_id']==FEATURE and fr['role']=='candidate_context_feature' and fr['engineering_ready']==1 and fr['status']=='ENGINEERING_READY_NOT_FORMAL_PIT' and fr['close_source_conflict_n']==fr['historical_first_availability_certified']==fr['model_input_approved']==fr['runtime_usable']==0
        precise_features.append(dict(fr,expected_state=GROUPS[0] if value>0 else GROUPS[1]))
    ck('every_actual_dependency_identity_order_hash_value_and_20_date_window',trace_ok)
    ck('exact_fraction_MA20_formula_and_group_signs',max_error<1e-12,{'max_absolute_feature_error':max_error})
    ck('selected_feature_all_formal_gates_remain_false',flags_ok)
    expected=expected_results(labels,precise_features,anchors,cfg['folds'])
    with ro(OUT/'市场状态候选开发验证.sqlite') as c:
        ck('saved_database_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        actual={name:[dict(r) for r in c.execute('SELECT * FROM '+name)] for name in expected}
        selected=[dict(r) for r in c.execute('SELECT * FROM selected_input_features')]
        saved_exclusions=[dict(r) for r in c.execute('SELECT * FROM registered_source_exclusions')]
        metadata=json.loads(c.execute("SELECT value_json FROM metadata WHERE key='run'").fetchone()[0])
    ck('selected_input_and_old_exclusions_copied_exactly',same(selected,features) and same(saved_exclusions,exclusions))
    csvnames={'predictions':'逐日概率与实际结果_仅开发期.csv','fitted':'每折模型与两组参数.csv','membership':'共同训练成员.csv','ledger':'训练与验证弃答台账.csv','folds':'六折训练与覆盖.csv','metrics':'概率评分.csv','comparisons':'同日模型对照.csv','calibration':'固定分箱校准诊断.csv','paired_loss':'逐日配对误差差.csv'}
    csv_ok=True;csvrows=0
    def csv_equal(csv_rows,db_rows):
        if len(csv_rows)!=len(db_rows):return False
        for cr,dr in zip(csv_rows,db_rows):
            if cr.keys()!=dr.keys():return False
            for k,v in dr.items():
                if isinstance(v,(float,int)):
                    if frac(cr[k])!=frac(v):return False
                elif cr[k]!=('' if v is None else str(v)):return False
        return True
    for name,filename in csvnames.items():
        with (OUT/filename).open(encoding='utf-8-sig',newline='') as fh:rs=list(csv.DictReader(fh))
        csv_ok &= csv_equal(rs,actual[name]);csvrows+=len(rs)
    for rows,filename in [(selected,'选定市场输入_仅开发期.csv'),(saved_exclusions,'沿用标签预排除.csv')]:
        with (OUT/filename).open(encoding='utf-8-sig',newline='') as fh:rs=list(csv.DictReader(fh))
        csv_ok &= csv_equal(rs,rows);csvrows+=len(rs)
    ck('all_11_csv_exports_exactly_match_saved_sqlite_rows',csv_ok,{'rows':csvrows})
    for name in expected:
        ck('independent_exact_'+name,same(expected[name],actual[name]),{'rows':len(expected[name]),'arithmetic':'Fraction; 60-digit Decimal ln for log loss'})
    pred=expected['predictions'];cases=[r for r in pred if r['model_id']==M0]
    ck('331_common_dates_662_predictions_66_fixed_original_grid',len(cases)==331 and len(pred)==662 and sum(r['fixed_every_fifth_anchor'] for r in cases)==66 and [(r['signal_date'],r['y']) for r in pred if r['model_id']==M0]==[(r['signal_date'],r['y']) for r in pred if r['model_id']==M3])
    ck('actual_time_boundaries_and_fixed_grid_nonoverlap',all(r['latest_training_label_end']<next(f['validation_start'] for f in cfg['folds'] if f['id']==r['fold_id']) for r in pred) and all(a['outcome_observation_date']<b['entry_observation_date'] for a,b in zip([r for r in cases if r['fixed_every_fifth_anchor']],[r for r in cases if r['fixed_every_fifth_anchor']][1:])))
    comps=expected['comparisons'];pool=next(r for r in comps if r['fold_id']=='POOLED' and r['subset']=='all_overlapping');grid=next(r for r in comps if r['fold_id']=='POOLED' and r['subset']=='fixed_every_fifth_anchor');folds=[r for r in comps if r['fold_id']!='POOLED' and r['subset']=='all_overlapping'];lower=sum(r['brier_delta_M3_minus_M0']<0 for r in folds)
    conditions=dict(pooled_brier_strictly_lower=pool['brier_delta_M3_minus_M0']<0,pooled_logloss_strictly_lower=pool['logloss_delta_M3_minus_M0']<0,fixed_grid_brier_no_worse=grid['brier_delta_M3_minus_M0']<=0,at_least_four_folds_strictly_lower=lower>=4)
    screen=dict(evaluable=True,not_evaluable_reason=None,lower_brier_fold_count=lower,conditions=conditions,passed=all(conditions.values()),statistical_or_profit_proof=False,automatic_phase_promotion=False)
    ck('all_four_preregistered_descriptive_screen_conditions',same(screen,read(OUT/'描述性开发筛选.json')),screen)
    ck('no_later_targets_no_current_forecast_or_formal_promotion',metadata['outcomes_2025_2026_opened']==metadata['formal_input_approved']==metadata['runtime_usable']==metadata['current_forecast_generated']==False and metadata['cumulative_registered_variants']==16 and all(r['outcome_observation_date']<=LAST and r['model_input_approved']==r['runtime_usable']==0 for r in actual['predictions']) and all(r['promotion_approved']==0 for r in actual['comparisons']))
    ck('metadata_provenance_matches_frozen_receipt',metadata['registration']==receipt and metadata['contract']==cfg and metadata['protected_source_sha256']==source_before and metadata==read(OUT/'运行与输入记录.json'))
    # Production functions are used only for synthetic/rejection/poison probes.
    spec=importlib.util.spec_from_file_location('market_model_under_test',PRODUCER);prod=importlib.util.module_from_spec(spec);spec.loader.exec_module(prod)
    rejection_details=[]
    def rejects(name,fn):
        try:fn()
        except (ValueError,TypeError,KeyError,StopIteration):rejection_details.append(dict(probe=name,rejected=True));return
        raise AssertionError('Mutation was not rejected: '+name)
    for key,value in [('feature_id','000001.SH:past_return_5'),('role','auxiliary'),('engineering_value',float('nan')),('engineering_value',float('inf')),('engineering_value',-1),('engineering_ready',2),('engineering_ready',True),('status','APPROVED'),('dependency_n',19),('dependency_first_date','2025-01-01'),('max_dependency_date','2025-01-02'),('close_source_conflict_n',1),('historical_first_availability_certified',1),('model_input_approved',1),('runtime_usable',1)]:
        row=deepcopy(features[0]);row[key]=value;rejects('bad feature '+key+' '+repr(value),lambda row=row:prod.market_state(row,cfg))
    for key,value in [('canonical_symbol','000001.SH'),('provider','tencent'),('collection','other'),('adjustment','1'),('price_unit','CNY'),('close',float('nan')),('close',0),('trade_date','2025-01-01')]:
        oo=deepcopy(obs);oo[0][key]=value;rejects('bad source '+key,lambda oo=oo:prod.verify_inputs(features,deps,oo,cfg))
    for key,value in [('feature_id','other'),('dependency_order',1),('dependency_symbol','000001.SH'),('dependency_date','2025-01-02'),('observation_id','absent'),('source_close',0),('source_sha256','0'*64),('source_close_conflict',1)]:
        dd=deepcopy(deps);dd[0][key]=value;rejects('bad actual dependency '+key,lambda dd=dd:prod.verify_inputs(features,dd,obs,cfg))
    duplicate_inputs=[('features',lambda:prod.verify_inputs(features+[deepcopy(features[0])],deps,obs,cfg)),('dependencies',lambda:prod.verify_inputs(features,deps+[deepcopy(deps[0])],obs,cfg)),('observations',lambda:prod.verify_inputs(features,deps,obs+[deepcopy(obs[0])],cfg)),('labels',lambda:prod.evaluate(labels+[deepcopy(labels[0])],features,anchors,deps,obs,cfg)),('anchors',lambda:prod.evaluate(labels,features,anchors+[anchors[-1]],deps,obs,cfg))]
    for name,fn in duplicate_inputs:rejects('duplicate '+name,fn)
    ck('illegal_duplicate_source_and_actual_trace_mutations_rejected',len(rejection_details)==36,rejection_details)
    r=deepcopy(features[0]);r['engineering_value']=0;states_test=[prod.market_state(r,cfg)];r['engineering_value']=1e-15;states_test.append(prod.market_state(r,cfg));r['engineering_value']=-1e-15;states_test.append(prod.market_state(r,cfg))
    r.update(engineering_ready=0,engineering_value=None,status='INSUFFICIENT_INDEX_HISTORY',dependency_n=0,dependency_first_date=None,max_dependency_date=None)
    states_test.extend([prod.market_state(r,cfg),prod.market_state(None,cfg)])
    ck('equality_below_positive_negative_and_missing_separate',states_test==[GROUPS[1],GROUPS[0],GROUPS[1],None,None])
    missing=[]
    for change in [dict(status='CLOSE_SOURCE_CONFLICT'),dict(engineering_value=0),dict(close_source_conflict_n=1),dict(dependency_n=20)]:
        bad=dict(r,**change);rejects('bad missing '+str(change),lambda bad=bad:prod.market_state(bad,cfg));missing.append(True)
    conflict=dict(features[0],engineering_ready=0,engineering_value=None,status='CLOSE_SOURCE_CONFLICT',close_source_conflict_n=1)
    ck('consistent_missing_conflict_abstains_and_contradictions_rejected',len(missing)==4 and prod.market_state(conflict,cfg) is None)
    for key,value in [('horizon_observed_sessions',10),('outcome_sign','unknown'),('outcome_observation_date','2025-01-02'),('entry_observation_date',labels[0]['signal_date'])]:
        ls=deepcopy(labels);ls[0][key]=value;rejects('target mutation '+key,lambda ls=ls:prod.evaluate(ls,features,anchors,deps,obs,cfg))
    for key,value in [('shrinkage_lambda',10),('minimum_training_rows',99),('models',[M0]),('feature_id','000001.SH:past_return_5'),('runtime_usable',True),('development_end','2025-12-31')]:
        bad=deepcopy(cfg);bad[key]=value;rejects('contract mutation '+key,lambda bad=bad:prod.guard(bad))
    ck('target_and_frozen_contract_mutations_rejected',len(rejection_details)==50)
    firstfold=cfg['folds'][0];poison=deepcopy(labels)
    for ls in poison:
        if firstfold['validation_start']<=ls['signal_date']<=firstfold['validation_end']:ls['outcome_sign']='price_change_lt_0' if ls['outcome_sign']=='price_change_gt_0' else 'price_change_gt_0'
    altered=prod.evaluate(poison,features,anchors,deps,obs,cfg)
    ck('first_fold_validation_label_poison_cannot_change_first_fit_or_probability',same([r for r in actual['fitted'] if r['fold_id']==firstfold['id']],[r for r in altered['fitted'] if r['fold_id']==firstfold['id']]) and [(r['signal_date'],r['model_id'],r['p']) for r in actual['predictions'] if r['fold_id']==firstfold['id']]==[(r['signal_date'],r['model_id'],r['p']) for r in altered['predictions'] if r['fold_id']==firstfold['id']])
    synth=[dict(y=1,zero_change=0,market_state=GROUPS[0],outcome_observation_date='2023-01-10') for _ in range(100)]
    fitted=prod.fit(synth,cfg)
    ck('99_training_rows_abstain_100_all_one_group_prior_fallback',prod.fit(synth[:99],cfg) is None and abs(fitted['p0']-float(F(101,102)))<1e-15 and fitted['groups'][GROUPS[1]]['n']==0 and fitted['groups'][GROUPS[1]]['p']==fitted['p0'])
    strictpath=ROOT/'work/market_model_oct31/strict_screen_review.py'
    strict_hash=sha(strictpath)
    spec2=importlib.util.spec_from_file_location('strict_market_screen_under_test',strictpath);strictmod=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(strictmod)
    strictscreen=strictmod.strict_screen
    ck('strict_publication_gate_matches_independent_four_condition_result',same(strictscreen(actual['comparisons'],cfg),screen))
    screen_probes=[]
    for metric in ['brier_delta_M3_minus_M0','logloss_delta_M3_minus_M0']:
        for badvalue in [float('nan'),float('inf'),None]:
            bad=deepcopy(actual['comparisons']);bad[0][metric]=badvalue
            try:s=strictscreen(bad,cfg);screen_probes.append(not s['evaluable'] and not s['passed'])
            except (ValueError,StopIteration):screen_probes.append(True)
    for role in ['remove_fold','empty_fold','empty_grid','duplicate_fold_hiding_missing_fold']:
        bad=deepcopy(actual['comparisons'])
        if role=='remove_fold':bad=[r for r in bad if r['fold_id']!=firstfold['id']]
        elif role=='empty_fold':
            for rr in bad:
                if rr['fold_id']==firstfold['id']:rr['n']=0;rr['brier_delta_M3_minus_M0']=rr['logloss_delta_M3_minus_M0']=None
        elif role=='empty_grid':
            for rr in bad:
                if rr['fold_id']=='POOLED' and rr['subset']=='fixed_every_fifth_anchor':rr['n']=0;rr['brier_delta_M3_minus_M0']=rr['logloss_delta_M3_minus_M0']=None
        else:
            for rr in bad:
                if rr['fold_id']=='F6_2024Q4':rr['fold_id']=firstfold['id']
        try:s=strictscreen(bad,cfg);screen_probes.append(not s['evaluable'] and not s['passed'])
        except (ValueError,StopIteration):screen_probes.append(True)
    ck('strict_screen_NaN_Inf_missing_metric_missing_fold_empty_grid_duplicate_fold_rejected',all(screen_probes),{'probes':len(screen_probes),'outcomes':screen_probes,'producer_helper_limitation':'Frozen original development_screen checked fold count, not exact IDs; strict publication guard is required, unchanged actual six-fold output independently complete'})
    extra_probes=[]
    for key,value in [('fold_id','F0_unregistered'),('subset','best_phase'),('n',True),('n',-1),('brier_M0',-0.01),('brier_M3',1.01),('promotion_approved',1)]:
        bad=deepcopy(actual['comparisons']);bad[0][key]=value
        try:strictscreen(bad,cfg);extra_probes.append(False)
        except ValueError:extra_probes.append(True)
    bad=deepcopy(actual['comparisons']);bad.append(deepcopy(bad[0]))
    try:strictscreen(bad,cfg);extra_probes.append(False)
    except ValueError:extra_probes.append(True)
    bad=deepcopy(actual['comparisons']);bad[-1]['n']+=1
    try:strictscreen(bad,cfg);extra_probes.append(False)
    except ValueError:extra_probes.append(True)
    ck('strict_screen_extra_identity_count_bounds_and_promotion_probes',all(extra_probes),{'probes':len(extra_probes)})
    empty=deepcopy(actual['comparisons'])
    for rr in empty:
        rr['n']=0
        for key in ['brier_M0','brier_M3','brier_delta_M3_minus_M0','logloss_delta_M3_minus_M0']:rr[key]=None
    empty_result=strictscreen(empty,cfg)
    ck('complete_empty_result_explicitly_unevaluable_without_promotion',not empty_result['evaluable'] and not empty_result['passed'] and not empty_result['automatic_phase_promotion'])
    empty[0]['promotion_approved']=1
    empty_promotion_rejected=False
    try:strictscreen(empty,cfg)
    except ValueError:empty_promotion_rejected=True
    ck('strict_screen_empty_result_cannot_promote_itself',empty_promotion_rejected)
    release_review=read(OUT/'筛选身份与完整性严格复核.json')
    ck('saved_strict_publication_review_matches_independent_actual_screen',release_review['all_checks_passed'] and release_review['matches_frozen_producer_result'] and not release_review['producer_or_contract_modified'] and same(release_review['strict_result'],screen))
    ck('production_code_and_registration_unchanged_during_audit',sha(PRODUCER)==producer_hash and sha(CONTRACT)==contract_hash and read(RECEIPT)==receipt)
    source_after={p:sha(ROOT/p) for p in source_before}
    ck('all_25_protected_old_sources_unchanged',source_after==source_before)
    ck('strict_publication_guard_unchanged_during_audit',sha(strictpath)==strict_hash)
    summary=dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,producer_code_sha256=producer_hash,contract_sha256=contract_hash,strict_publication_guard_sha256=strict_hash,source_sha256_before=source_before,source_sha256_after=source_after,
                 audit_method='Independent stdlib Fraction / 60-digit Decimal reconstruction; production imported only for rejection, synthetic and label-poison probes',outcomes_2025_2026_opened=False,
                 case_count=len(cases),prediction_rows=len(pred),fixed_original_grid_cases=sum(r['fixed_every_fifth_anchor'] for r in cases),pooled_comparisons=[{k:float(v) if isinstance(v,(F,Decimal)) else v for k,v in c.items()} for c in comps if c['fold_id']=='POOLED'])
    WORK.mkdir(exist_ok=True)
    (WORK/'独立复核.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    (WORK/'独立复核.md').write_text('# 市场状态候选独立复核\n\n'
       f'通过 {len(checks)}/{len(checks)} 项独立复核。预期结果未调用生产 fit/evaluate/score 生成。\n\n'
       '从原始保存指数价格字符串用 Fraction 重建484个深成指相对MA20输入，核对9680条真实依赖；从旧原始个股开收盘重建469个2023—2024标签与15个排除；独立重建6季度共同训练、成熟标签边界、331个评分日期、662条预测和66个固定原锚点网格样本。全部训练成员、弃答、参数、配对误差、Brier、60位Decimal对数损失和固定分箱逐行匹配。\n\n'
       '合成及拒绝探针覆盖非法/重复来源、真实依赖修改、缺值与相等/负值分开、合同及目标变异、首折验证标签投毒、99样本弃答、空组回退、筛选NaN/Inf/缺折/空网格。25个旧源前后哈希一致。\n\n'
       '冻结生产器的 development_screen 工具函数原先仅校验折数，未校验固定六折ID完整唯一集合；实际输出的六折身份完整且已独立验证，不影响此次概率和评分。新 strict_screen_review.py 必须作为发布前强制门，独立反例确认其拒绝缺折同时重复补行等畸形结果；生产器、合同、回执及原始结果未更改。\n\n'
       '本次只读取旧2023—2024标签，没有生成、读取或汇总2025/2026目标。注册时间仅以本地文件和回执验证，未声称外部时间戳。全部正式输入、历史当时可得、运行使用和升级许可均为否。复核通过只证明实现对应冻结研究规格，不证明预测或收益有效。\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['checks','source_sha256_before','source_sha256_after']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
