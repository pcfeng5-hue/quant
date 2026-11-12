"""One frozen Shenzhen MA20 state candidate, retrospective development only."""
from pathlib import Path
from collections import Counter
from copy import deepcopy
from datetime import date
import csv,hashlib,json,math,shutil,sqlite3,tempfile

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/市场环境候选验证_20261031'
CONTRACT=WORK/'contract.json'
RECEIPT=WORK/'registration_receipt.json'
MODELS=['M0_laplace_constant','M3_shenzhen_ma20_group_shrinkage']
GROUPS=['above_ma20','at_or_below_ma20']

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def ro(p):
    c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c
def csvout(p,rs):
    if not rs:return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def table(c,name,rs):
    if not rs:return
    fields=list(rs[0]);types=[]
    for k in fields:
        v=next((r[k] for r in rs if r[k] is not None),None)
        t='INTEGER' if isinstance(v,(int,bool)) else 'REAL' if isinstance(v,float) else 'TEXT'
        if k in ('model_input_approved','runtime_usable','promotion_approved'):t+=' NOT NULL CHECK("'+k+'"=0)'
        types.append(t)
    q=lambda s:'"'+s.replace('"','""')+'"'
    c.execute('CREATE TABLE '+q(name)+'('+','.join(q(k)+' '+t for k,t in zip(fields,types))+')')
    c.executemany('INSERT INTO '+q(name)+' VALUES('+','.join('?' for _ in fields)+')',[tuple(r[k] for k in fields) for r in rs])

def guard(cfg):
    if cfg!=read(CONTRACT):raise ValueError('Frozen candidate contract mutation rejected')

def market_state(r,cfg):
    if r is None:return None
    required={'signal_date','feature_id','role','engineering_value','engineering_ready','status','dependency_n','dependency_first_date','max_dependency_date','close_source_conflict_n','historical_first_availability_certified','model_input_approved','runtime_usable'}
    if not required<=r.keys():raise ValueError('Incomplete feature row')
    if r['feature_id']!=cfg['feature_id'] or r['role']!='candidate_context_feature':raise ValueError('Unregistered feature ID or role')
    if any(r[k]!=0 for k in ['historical_first_availability_certified','model_input_approved','runtime_usable']):raise ValueError('Research exception cannot promote formal gates')
    if type(r['engineering_ready']) is not int or r['engineering_ready'] not in (0,1):raise ValueError('Invalid readiness flag')
    for k in ['dependency_n','close_source_conflict_n']:
        if type(r[k]) is not int or r[k]<0:raise ValueError('Invalid dependency counts')
    day=r['signal_date'];date.fromisoformat(day)
    if not cfg['development_start']<=day<=cfg['development_end']:raise ValueError('Feature date outside development')
    value=r['engineering_value'];status=r['status']
    if r['engineering_ready']:
        if status!='ENGINEERING_READY_NOT_FORMAL_PIT' or type(value) not in (int,float) or not math.isfinite(value) or value<=-1:raise ValueError('Contradictory ready feature value/status')
        if r['dependency_n']!=20 or r['close_source_conflict_n']!=0 or r['max_dependency_date']!=day or not r['dependency_first_date'] or r['dependency_first_date']>day:raise ValueError('Invalid ready feature trace')
        date.fromisoformat(r['dependency_first_date'])
        return GROUPS[0] if value>0 else GROUPS[1]
    allowed={'BEFORE_CALCULATION_START','INSUFFICIENT_INDEX_HISTORY','CLOSE_SOURCE_CONFLICT'}
    if value is not None or status not in allowed:raise ValueError('Contradictory missing feature value/status')
    if (status=='CLOSE_SOURCE_CONFLICT')!=(r['close_source_conflict_n']>0):raise ValueError('Contradictory conflict state')
    if status=='CLOSE_SOURCE_CONFLICT':
        if r['dependency_n']!=20 or r['close_source_conflict_n']>20 or r['max_dependency_date']!=day or not r['dependency_first_date'] or r['dependency_first_date']>day:raise ValueError('Invalid missing conflict trace')
        date.fromisoformat(r['dependency_first_date'])
    elif r['dependency_n']!=0 or r['dependency_first_date'] is not None or r['max_dependency_date'] is not None:raise ValueError('Cold-start row must have empty trace')
    return None

def verify_inputs(features,dependencies,observations,cfg):
    if len({r['signal_date'] for r in features})!=len(features):raise ValueError('Duplicate feature dates')
    obs={};calendar=[]
    for r in observations:
        if r['observation_id'] in obs:raise ValueError('Duplicate close observation ID')
        if r['canonical_symbol']!='399001.SZ' or r['provider']!='eastmoney' or r['price_unit']!='index_points' or r['collection']!='market_industry_oct21' or r['adjustment']!='0':raise ValueError('Unregistered close source')
        if type(r['close']) not in (int,float) or not math.isfinite(r['close']) or r['close']<=0:raise ValueError('Invalid dependency close')
        if not '2022-06-01'<=r['trade_date']<=cfg['development_end']:raise ValueError('Invalid source-close date')
        obs[r['observation_id']]=r;calendar.append(r['trade_date'])
    if calendar!=sorted(set(calendar)):raise ValueError('Duplicate or unordered close calendar')
    bydate={};keys=set()
    for r in dependencies:
        key=(r['signal_date'],r['dependency_order'])
        if key in keys:raise ValueError('Duplicate dependency order')
        if r['feature_id']!=cfg['feature_id']:raise ValueError('Unregistered dependency feature')
        if r['dependency_symbol']!='399001.SZ' or r['dependency_date']>r['signal_date']:raise ValueError('Invalid dependency symbol or future date')
        if r['observation_id'] not in obs:raise ValueError('Missing original dependency observation')
        raw=obs[r['observation_id']]
        if raw['trade_date']!=r['dependency_date'] or raw['close']!=r['source_close'] or raw['source_sha256']!=r['source_sha256']:raise ValueError('Dependency source correspondence failed')
        if r['source_close_conflict'] not in (0,1):raise ValueError('Invalid source conflict flag')
        keys.add(key);bydate.setdefault(r['signal_date'],[]).append(r)
    domains={r['signal_date'] for r in features}
    if not set(bydate)<=domains:raise ValueError('Orphan feature dependencies')
    for r in features:
        group=market_state(r,cfg);ds=sorted(bydate.get(r['signal_date'],[]),key=lambda x:x['dependency_order'])
        if len(ds)!=r['dependency_n']:raise ValueError('Feature/dependency count mismatch')
        if sum(d['source_close_conflict'] for d in ds)!=r['close_source_conflict_n']:raise ValueError('Feature/dependency conflict count mismatch')
        if not ds:continue
        if [d['dependency_order'] for d in ds]!=list(range(20)):raise ValueError('Dependency order is not complete MA20')
        dates=[d['dependency_date'] for d in ds]
        if dates!=sorted(set(dates)) or dates[0]!=r['dependency_first_date'] or dates[-1]!=r['max_dependency_date']:raise ValueError('Feature/dependency dates differ')
        if r['signal_date'] not in calendar:raise ValueError('Signal not on selected index calendar')
        i=calendar.index(r['signal_date'])
        if i<19 or dates!=calendar[i-19:i+1]:raise ValueError('MA20 does not use exact preceding observed closes')
        if group is None:continue
        if any(d['source_close_conflict'] for d in ds):raise ValueError('Ready feature has conflicted close dependency')
        recomputed=ds[-1]['source_close']/(math.fsum(d['source_close'] for d in ds)/20)-1
        if not math.isclose(recomputed,r['engineering_value'],rel_tol=0,abs_tol=cfg['dependency_numeric_absolute_tolerance']):raise ValueError('Feature formula correspondence failed')

def fit(train,cfg):
    n=len(train)
    if n<cfg['minimum_training_rows']:return None
    k=sum(r['y'] for r in train);z=sum(r['zero_change'] for r in train);p0=(k+1)/(n+2);groups={}
    for g in GROUPS:
        rs=[r for r in train if r['market_state']==g];gn=len(rs);gk=sum(r['y'] for r in rs);gz=sum(r['zero_change'] for r in rs)
        groups[g]=dict(n=gn,k=gk,z=gz,p=(gk+cfg['shrinkage_lambda']*p0)/(gn+cfg['shrinkage_lambda']) if gn else p0)
    return dict(n=n,k=k,z=z,p0=p0,groups=groups,latest_training_label_end=max(r['outcome_observation_date'] for r in train))

def score(rs,eps):
    n=len(rs)
    if not n:return dict(n=0,positive_count=0,zero_count=0,negative_count=0,positive_frequency=None,mean_prediction=None,brier=None,log_loss=None)
    k=sum(r['y'] for r in rs);z=sum(r['zero_change'] for r in rs)
    return dict(n=n,positive_count=k,zero_count=z,negative_count=n-k-z,positive_frequency=k/n,mean_prediction=sum(r['p'] for r in rs)/n,brier=sum((r['p']-r['y'])**2 for r in rs)/n,log_loss=-sum(math.log(max(eps,min(1-eps,r['p'] if r['y'] else 1-r['p']))) for r in rs)/n)

def evaluate(labels,features,anchors,dependencies,observations,cfg):
    guard(cfg);verify_inputs(features,dependencies,observations,cfg)
    if anchors!=sorted(set(anchors)) or any(not cfg['development_start']<=d<=cfg['development_end'] for d in anchors):raise ValueError('Invalid development anchors')
    if len({r['signal_date'] for r in labels})!=len(labels):raise ValueError('Duplicate label dates')
    if not {r['signal_date'] for r in features}<=set(anchors):raise ValueError('Feature outside anchor domain')
    byfeature={r['signal_date']:r for r in features};joined=[]
    for r in labels:
        d=r['signal_date'];entry=r['entry_observation_date'];end=r['outcome_observation_date']
        if d not in anchors or not cfg['development_start']<=d<entry<=end<=cfg['development_end']:raise ValueError('Invalid label date domain')
        if r['horizon_observed_sessions']!=5 or r['outcome_sign'] not in ('price_change_gt_0','price_change_eq_0','price_change_lt_0'):raise ValueError('Invalid target definition')
        f=byfeature.get(d)
        joined.append(dict(r,market_state=market_state(f,cfg),market_value=f['engineering_value'] if f else None,feature_status=f['status'] if f else 'FEATURE_ROW_ABSENT',y=int(r['outcome_sign']=='price_change_gt_0'),zero_change=int(r['outcome_sign']=='price_change_eq_0')))
    lookup={r['signal_date']:r for r in joined};grid={d for i,d in enumerate(anchors) if i%5==0}
    preds=[];fitted=[];members=[];ledger=[];folds=[]
    for fold in cfg['folds']:
        fid=fold['id'];start=fold['validation_start'];end=fold['validation_end']
        candidates=[r for r in joined if r['signal_date']<start]
        mature=[r for r in candidates if r['outcome_observation_date']<start]
        train=[r for r in mature if r['market_state'] is not None];model=fit(train,cfg)
        for r in candidates:
            reason='TRAIN_LABEL_NOT_MATURE' if r['outcome_observation_date']>=start else 'TRAIN_MARKET_FEATURE_NOT_READY' if r['market_state'] is None else 'TRAIN_USED'
            ledger.append(dict(fold_id=fid,role='training',signal_date=r['signal_date'],label_end=r['outcome_observation_date'],reason=reason,feature_status=r['feature_status']))
        for r in train:members.append(dict(fold_id=fid,signal_date=r['signal_date'],label_end=r['outcome_observation_date'],market_state=r['market_state'],market_value=r['market_value'],y=r['y'],zero_change=r['zero_change']))
        if model:
            base=dict(fold_id=fid,model_id=MODELS[0],group_id='ALL',training_n=model['n'],training_positive=model['k'],training_zero=model['z'],group_n=model['n'],group_positive=model['k'],group_zero=model['z'],group_negative=model['n']-model['k']-model['z'],prior_p=None,p=model['p0'],prior_only=0,group_n_lt20=int(model['n']<20),latest_training_label_end=model['latest_training_label_end'])
            fitted.append(base)
            for g,v in model['groups'].items():fitted.append(dict(base,model_id=MODELS[1],group_id=g,group_n=v['n'],group_positive=v['k'],group_zero=v['z'],group_negative=v['n']-v['k']-v['z'],prior_p=model['p0'],p=v['p'],prior_only=int(v['n']==0),group_n_lt20=int(v['n']<20)))
        counts=Counter();valanchors=[d for d in anchors if start<=d<=end]
        for d in valanchors:
            r=lookup.get(d)
            reason='NO_REGISTERED_LABEL' if r is None else 'LABEL_CROSSES_FOLD_END' if r['outcome_observation_date']>end else 'MARKET_FEATURE_NOT_READY' if r['market_state'] is None else 'INSUFFICIENT_JOINT_TRAINING' if model is None else 'EVALUATED'
            counts[reason]+=1;ledger.append(dict(fold_id=fid,role='validation',signal_date=d,label_end=r['outcome_observation_date'] if r else None,reason=reason,feature_status=r['feature_status'] if r else None))
            if reason!='EVALUATED':continue
            cell=model['groups'][r['market_state']]
            for mid,p,gn in [(MODELS[0],model['p0'],model['n']),(MODELS[1],cell['p'],cell['n'])]:
                preds.append(dict(fold_id=fid,model_id=mid,signal_date=d,entry_observation_date=r['entry_observation_date'],outcome_observation_date=r['outcome_observation_date'],market_state=r['market_state'],market_value=r['market_value'],y=r['y'],zero_change=r['zero_change'],p=p,training_n=model['n'],group_training_n=gn,prior_only=int(gn==0),latest_training_label_end=model['latest_training_label_end'],fixed_every_fifth_anchor=int(d in grid),model_input_approved=0,runtime_usable=0))
        folds.append(dict(fold_id=fid,validation_start=start,validation_end=end,training_candidates=len(candidates),training_not_mature=len(candidates)-len(mature),training_mature=len(mature),training_feature_missing=len(mature)-len(train),training_used=len(train),latest_training_label_end=model['latest_training_label_end'] if model else None,validation_anchors=len(valanchors),evaluated_dates=counts['EVALUATED'],no_registered_label=counts['NO_REGISTERED_LABEL'],label_crosses_fold_end=counts['LABEL_CROSSES_FOLD_END'],feature_not_ready=counts['MARKET_FEATURE_NOT_READY'],insufficient_training=counts['INSUFFICIENT_JOINT_TRAINING']))
    metrics=[];comparisons=[];bins=[];paired=[]
    for fid in [f['id'] for f in cfg['folds']]+['POOLED']:
        for subset in ['all_overlapping','fixed_every_fifth_anchor']:
            target=[r for r in preds if (fid=='POOLED' or r['fold_id']==fid) and (subset=='all_overlapping' or r['fixed_every_fifth_anchor'])]
            bymodel={m:[r for r in target if r['model_id']==m] for m in MODELS};scores={m:score(rs,cfg['log_loss_epsilon']) for m,rs in bymodel.items()}
            for m,v in scores.items():metrics.append(dict(fold_id=fid,subset=subset,model_id=m,**v))
            a,b=[scores[m] for m in MODELS]
            comparisons.append(dict(fold_id=fid,subset=subset,n=a['n'],brier_M0=a['brier'],brier_M3=b['brier'],brier_delta_M3_minus_M0=b['brier']-a['brier'] if a['n'] else None,logloss_delta_M3_minus_M0=b['log_loss']-a['log_loss'] if a['n'] else None,promotion_approved=0))
            if subset!='all_overlapping':continue
            for m,rs in bymodel.items():
                edges=cfg['calibration_bin_edges']
                for j,(lo,hi) in enumerate(zip(edges,edges[1:])):
                    selected=[r for r in rs if lo<=r['p'] and (r['p']<hi or j==len(edges)-2 and r['p']<=hi)];s=score(selected,cfg['log_loss_epsilon'])
                    bins.append(dict(fold_id=fid,model_id=m,bin_low=lo,bin_high=hi,n=s['n'],positive_count=s['positive_count'],zero_count=s['zero_count'],negative_count=s['negative_count'],mean_prediction=s['mean_prediction'],observed_positive_frequency=s['positive_frequency'],observed_minus_prediction=s['positive_frequency']-s['mean_prediction'] if s['n'] else None,empty_bin=int(not s['n']),sparse_note='empty' if not s['n'] else 'n_lt20_not_reliability_test' if s['n']<20 else 'n_does_not_certify_calibration',calibration_transform_fitted=0))
    index={(r['signal_date'],r['model_id']):r for r in preds}
    for r in preds:
        if r['model_id']!=MODELS[1]:continue
        b=index[(r['signal_date'],MODELS[0])];eps=cfg['log_loss_epsilon']
        paired.append(dict(fold_id=r['fold_id'],signal_date=r['signal_date'],y=r['y'],p_M0=b['p'],p_M3=r['p'],brier_delta=(r['p']-r['y'])**2-(b['p']-b['y'])**2,logloss_delta=-math.log(max(eps,r['p'] if r['y'] else 1-r['p']))+math.log(max(eps,b['p'] if b['y'] else 1-b['p'])),fixed_every_fifth_anchor=r['fixed_every_fifth_anchor']))
    return dict(predictions=preds,fitted=fitted,membership=members,ledger=ledger,folds=folds,metrics=metrics,comparisons=comparisons,calibration=bins,paired_loss=paired)

def development_screen(comparisons):
    pooled=next(r for r in comparisons if r['fold_id']=='POOLED' and r['subset']=='all_overlapping')
    grid=next(r for r in comparisons if r['fold_id']=='POOLED' and r['subset']=='fixed_every_fifth_anchor')
    folds=[r for r in comparisons if r['fold_id']!='POOLED' and r['subset']=='all_overlapping']
    evaluable=len(folds)==6 and all(r['n']>0 and all(type(v) in (int,float) and math.isfinite(v) for v in [r['brier_delta_M3_minus_M0'],r['logloss_delta_M3_minus_M0']]) for r in [pooled,grid]+folds)
    lower=sum(r['brier_delta_M3_minus_M0']<0 for r in folds if r['brier_delta_M3_minus_M0'] is not None)
    conditions=dict(pooled_brier_strictly_lower=pooled['brier_delta_M3_minus_M0']<0 if evaluable else None,pooled_logloss_strictly_lower=pooled['logloss_delta_M3_minus_M0']<0 if evaluable else None,fixed_grid_brier_no_worse=grid['brier_delta_M3_minus_M0']<=0 if evaluable else None,at_least_four_folds_strictly_lower=lower>=4 if evaluable else None)
    return dict(evaluable=evaluable,not_evaluable_reason=None if evaluable else 'One or more registered folds or fixed-grid metrics unavailable',lower_brier_fold_count=lower,conditions=conditions,passed=bool(evaluable and all(conditions.values())),statistical_or_profit_proof=False,automatic_phase_promotion=False)

def validate(result,labels,features,anchors,deps,obs,cfg):
    checks=[]
    def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
    p=result['predictions'];fm={f['id']:f for f in cfg['folds']}
    ck('identical_model_dates_and_outcomes',[(r['signal_date'],r['y']) for r in p if r['model_id']==MODELS[0]]==[(r['signal_date'],r['y']) for r in p if r['model_id']==MODELS[1]])
    ck('training_labels_end_before_fold',all(f['latest_training_label_end']<f['validation_start'] for f in result['folds'] if f['latest_training_label_end']))
    ck('validation_labels_within_fold',all(fm[r['fold_id']]['validation_start']<=r['signal_date']<r['entry_observation_date']<=r['outcome_observation_date']<=fm[r['fold_id']]['validation_end'] for r in p))
    ck('only_development_outcomes',all(r['outcome_observation_date']<'2025-01-01' for r in p))
    ck('probability_and_formal_flags',all(0<r['p']<1 and r['model_input_approved']==r['runtime_usable']==0 for r in p))
    ck('coverage_accounts_for_every_anchor',all(f['validation_anchors']==sum(f[k] for k in ['evaluated_dates','no_registered_label','label_crosses_fold_end','feature_not_ready','insufficient_training']) for f in result['folds']))
    ck('every_fitted_group_and_empty_group_reported',all(sum(r['fold_id']==f['fold_id'] and r['model_id']==MODELS[1] for r in result['fitted'])==2 for f in result['folds'] if f['training_used']>=100))
    ck('fitted_formulas_match',all(math.isclose(r['p'],(r['group_positive']+1)/(r['group_n']+2) if r['model_id']==MODELS[0] else (r['group_positive']+20*r['prior_p'])/(r['group_n']+20),rel_tol=0,abs_tol=1e-15) for r in result['fitted']))
    ck('training_members_count',all(sum(r['fold_id']==f['fold_id'] for r in result['membership'])==f['training_used'] for f in result['folds']))
    ex=deepcopy(features[0]);ex['engineering_value']=0
    ck('zero_state_goes_at_or_below',market_state(ex,cfg)==GROUPS[1])
    ex['engineering_value']=1e-15;ck('no_positive_epsilon_threshold',market_state(ex,cfg)==GROUPS[0])
    ex['engineering_value']=-1e-15;ck('negative_state_goes_at_or_below',market_state(ex,cfg)==GROUPS[1])
    ex.update(engineering_ready=0,engineering_value=None,status='INSUFFICIENT_INDEX_HISTORY',dependency_n=0,dependency_first_date=None,max_dependency_date=None)
    ck('missing_state_does_not_equal_below',market_state(ex,cfg) is None and market_state(None,cfg) is None)
    synthetic=[dict(y=1,zero_change=0,market_state=GROUPS[0],outcome_observation_date='2023-01-10')]*100
    fitted=fit(synthetic,cfg)
    ck('empty_group_exact_p0',fitted['groups'][GROUPS[1]]['n']==0 and fitted['groups'][GROUPS[1]]['p']==fitted['p0'])
    ck('insufficient_training_common_abstention',fit(synthetic[:-1],cfg) is None)
    s=score([dict(p=.25,y=1,zero_change=0),dict(p=.75,y=0,zero_change=0)],1e-12)
    ck('manual_brier_logloss',math.isclose(s['brier'],.5625) and math.isclose(s['log_loss'],-math.log(.25)))
    ck('empty_score_null',score([],1e-12)['brier'] is None)
    ck('zero_price_change_not_positive',all(not r['y'] for r in p if r['zero_change']))
    ck('all_bins_reconcile',all(sum(r['n'] for r in result['calibration'] if r['fold_id']==fid and r['model_id']==m)==sum(r['model_id']==m and (fid=='POOLED' or r['fold_id']==fid) for r in p) for fid in list(fm)+['POOLED'] for m in MODELS))
    grid={d for i,d in enumerate(anchors) if i%5==0};ck('grid_before_filtering',all(r['fixed_every_fifth_anchor']==int(r['signal_date'] in grid) for r in p))
    rs=[r for r in p if r['model_id']==MODELS[0] and r['fixed_every_fifth_anchor']]
    ck('grid_result_windows_nonoverlapping',all(a['outcome_observation_date']<b['entry_observation_date'] for a,b in zip(rs,rs[1:])))
    first=cfg['folds'][0];poison=deepcopy(labels)
    for r in poison:
        if first['validation_start']<=r['signal_date']<=first['validation_end']:r['outcome_sign']='price_change_lt_0' if r['outcome_sign']=='price_change_gt_0' else 'price_change_gt_0'
    altered=evaluate(poison,features,anchors,deps,obs,cfg)
    ck('validation_label_poison_does_not_change_fit',[r for r in result['fitted'] if r['fold_id']==first['id']]==[r for r in altered['fitted'] if r['fold_id']==first['id']])
    ck('validation_label_poison_does_not_change_probabilities',[(r['signal_date'],r['model_id'],r['p']) for r in p if r['fold_id']==first['id']]==[(r['signal_date'],r['model_id'],r['p']) for r in altered['predictions'] if r['fold_id']==first['id']])
    count=0
    for ls,fs,aa,dd,oo in [(labels+[deepcopy(labels[0])],features,anchors,deps,obs),(labels,features+[deepcopy(features[0])],anchors,deps,obs),(labels,features,anchors+[anchors[-1]],deps,obs),(labels,features,anchors,deps+[deepcopy(deps[0])],obs)]:
        try:evaluate(ls,fs,aa,dd,oo,cfg)
        except ValueError:count+=1
    ck('duplicate_label_feature_anchor_dependency_rejected',count==4)
    count=0
    for key,v in [('feature_id','000001.SH:past_return_5'),('engineering_value',float('nan')),('engineering_ready',0),('status','APPROVED'),('model_input_approved',1),('max_dependency_date','2025-01-02'),('close_source_conflict_n',1)]:
        row=deepcopy(features[0]);row[key]=v
        try:market_state(row,cfg)
        except ValueError:count+=1
    ck('contradictory_or_unregistered_feature_rejected',count==7)
    count=0
    for key,v in [('horizon_observed_sessions',10),('outcome_sign','unknown'),('outcome_observation_date','2025-01-02')]:
        bad=deepcopy(labels);bad[0][key]=v
        try:evaluate(bad,features,anchors,deps,obs,cfg)
        except ValueError:count+=1
    ck('invalid_or_later_target_rejected',count==3)
    count=0
    for k,v in [('shrinkage_lambda',10),('feature_id','000001.SH:past_return_5'),('runtime_usable',True),('development_end','2025-12-31')]:
        bad=deepcopy(cfg);bad[k]=v
        try:guard(bad)
        except ValueError:count+=1
    ck('frozen_candidate_mutations_rejected',count==4)
    ck('paired_losses_reconcile',all(math.isclose(sum(r['brier_delta'] for r in result['paired_loss'] if (c['fold_id']=='POOLED' or r['fold_id']==c['fold_id']) and (c['subset']=='all_overlapping' or r['fixed_every_fifth_anchor']))/c['n'],c['brier_delta_M3_minus_M0'],rel_tol=0,abs_tol=1e-14) for c in result['comparisons'] if c['n']))
    empty=deepcopy(result['comparisons'])
    for r in empty:
        if r['fold_id']=='F1_2023Q3':r['n']=0;r['brier_delta_M3_minus_M0']=None;r['logloss_delta_M3_minus_M0']=None
    ck('screen_unavailable_fold_cannot_pass',not development_screen(empty)['evaluable'] and not development_screen(empty)['passed'])
    invalid=deepcopy(result['comparisons']);invalid[0]['brier_delta_M3_minus_M0']=float('nan')
    ck('screen_nonfinite_metric_cannot_pass',not development_screen(invalid)['evaluable'] and not development_screen(invalid)['passed'])
    return checks

def main():
    cfg=read(CONTRACT);receipt=read(RECEIPT);guard(cfg)
    if receipt['contract_sha256']!=sha(CONTRACT) or receipt['producer_code_sha256']!=sha(Path(__file__).resolve()):raise ValueError('Candidate registration fingerprint mismatch')
    protected=receipt['protected_source_sha256'];before={p:sha(ROOT/p) for p in protected}
    if before!=protected:raise ValueError('Protected input changed since registration')
    with ro(ROOT/cfg['input_features']) as c:
        metadata=json.loads(c.execute("SELECT value_json FROM metadata WHERE key='run'").fetchone()[0])
        prep_receipt=read(ROOT/'work/market_context_oct31/registration_receipt.json')
        if metadata['contract']!=read(ROOT/'work/market_context_oct31/contract.json') or metadata['registration']!=prep_receipt:raise ValueError('Preparation contract/receipt mismatch')
        if prep_receipt['producer_code_sha256']!=sha(ROOT/'work/market_context_oct31/build_context.py'):raise ValueError('Preparation code changed')
        fs=[dict(r) for r in c.execute("SELECT signal_date,feature_id,role,engineering_value,engineering_ready,status,dependency_n,dependency_first_date,max_dependency_date,close_source_conflict_n,historical_first_availability_certified,model_input_approved,runtime_usable FROM features WHERE feature_id=? AND signal_date BETWEEN ? AND ? ORDER BY signal_date",(cfg['feature_id'],cfg['development_start'],cfg['development_end']))]
        deps=[dict(r) for r in c.execute("SELECT * FROM feature_dependencies WHERE feature_id=? AND signal_date BETWEEN ? AND ? ORDER BY signal_date,dependency_order",(cfg['feature_id'],cfg['development_start'],cfg['development_end']))]
        obs=[dict(r) for r in c.execute("SELECT * FROM input_closes WHERE canonical_symbol='399001.SZ' AND provider='eastmoney' AND trade_date BETWEEN '2022-06-01' AND '2024-12-31' ORDER BY trade_date")]
    verify_inputs(fs,deps,obs,cfg)
    with ro(ROOT/cfg['input_anchors']) as c:anchors=[r[0] for r in c.execute("SELECT trade_date FROM input_bars WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date")]
    with ro(ROOT/cfg['input_labels']) as c:
        labels=[dict(r) for r in c.execute("SELECT signal_date,entry_observation_date,outcome_observation_date,outcome_sign,horizon_observed_sessions FROM development_price_outcomes WHERE signal_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY signal_date")]
        exclusions=[dict(r) for r in c.execute("SELECT trade_date,reason FROM excluded_anchors WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date")]
    if len(fs)!=484 or len(anchors)!=484 or len(labels)!=469 or len(exclusions)!=15:raise ValueError('Unexpected frozen source coverage')
    result=evaluate(labels,fs,anchors,deps,obs,cfg);checks=validate(result,labels,fs,anchors,deps,obs,cfg)
    result['registered_source_exclusions']=exclusions;result['selected_input_features']=fs
    screen=development_screen(result['comparisons'])
    after={p:sha(ROOT/p) for p in protected}
    if after!=before:raise ValueError('Protected input modified during candidate run')
    checks.append(dict(check='all_protected_inputs_unchanged',passed=True,details=after))
    metadata=dict(contract=cfg,registration=receipt,protected_source_sha256=before,outcomes_2025_2026_opened=False,formal_input_approved=False,runtime_usable=False,current_forecast_generated=False,new_registered_model_variants=1,cumulative_registered_variants=16)
    OUT.mkdir(parents=True,exist_ok=True)
    names={'predictions':'逐日概率与实际结果_仅开发期.csv','fitted':'每折模型与两组参数.csv','membership':'共同训练成员.csv','ledger':'训练与验证弃答台账.csv','folds':'六折训练与覆盖.csv','metrics':'概率评分.csv','comparisons':'同日模型对照.csv','calibration':'固定分箱校准诊断.csv','paired_loss':'逐日配对误差差.csv','registered_source_exclusions':'沿用标签预排除.csv','selected_input_features':'选定市场输入_仅开发期.csv'}
    with tempfile.TemporaryDirectory(prefix='market_model_',dir=WORK) as td:
        td=Path(td)
        for k,name in names.items():csvout(td/name,result[k])
        with sqlite3.connect(td/'市场状态候选开发验证.sqlite') as c:
            for k,rs in result.items():table(c,k,rs)
            c.execute('CREATE UNIQUE INDEX unique_prediction ON predictions(signal_date,model_id)')
            c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT)');c.execute('INSERT INTO metadata VALUES(?,?)',('run',enc(metadata)))
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite check failed')
        (td/'预登记研究协议.json').write_text(enc(cfg));(td/'运行与输入记录.json').write_text(enc(metadata));(td/'描述性开发筛选.json').write_text(enc(screen))
        (td/'实现验证结果.json').write_text(enc(dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,producer_code_sha256=sha(Path(__file__).resolve()),contract_sha256=sha(CONTRACT),source_sha256_before=before,source_sha256_after=after)))
        for p in td.iterdir():shutil.copy2(p,OUT/p.name)
    print(enc(dict(output=str(OUT),checks=len(checks),pooled_metrics=[r for r in result['metrics'] if r['fold_id']=='POOLED'],pooled_comparisons=[r for r in result['comparisons'] if r['fold_id']=='POOLED'],descriptive_screen=screen)))

if __name__=='__main__':main()
