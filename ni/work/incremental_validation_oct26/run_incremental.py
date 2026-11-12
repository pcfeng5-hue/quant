"""One preregistered price-volume increment; development only, matched cases."""
from pathlib import Path
from collections import Counter
from copy import deepcopy
import csv, hashlib, json, math, shutil, sqlite3, tempfile

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/量价增量验证_20261026'
CONTRACT=WORK/'contract.json'
RECEIPT=WORK/'registration_receipt.json'
UP='MA5_gt_MA10_gt_MA15_and_MA15_rising'
DOWN='MA5_lt_MA10_lt_MA15_and_MA15_falling'
VUP='volume_gt_1p5_prev20_and_close_rising'
VDOWN='volume_gt_1p5_prev20_and_close_falling'
MAS=['up','down','other']
VPS=['spike_up','spike_down','other']
MODELS=['M0_laplace_constant','M1_ma_group_shrinkage','M2_ma_volume_hierarchical']

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def ro(p):
    c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c
def csvout(path,rs):
    if not rs:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def table(c,name,rs):
    if not rs:return
    fields=list(rs[0]);types=[]
    for k in fields:
        v=next((r[k] for r in rs if r[k] is not None),None)
        types.append('INTEGER' if isinstance(v,(int,bool)) else 'REAL' if isinstance(v,float) else 'TEXT')
    q=lambda s:'"'+s.replace('"','""')+'"'
    c.execute('CREATE TABLE '+q(name)+'('+','.join(q(k)+' '+t for k,t in zip(fields,types))+')')
    c.executemany('INSERT INTO '+q(name)+' VALUES('+','.join('?' for _ in fields)+')',[tuple(r[k] for k in fields) for r in rs])

def guard(cfg):
    # All semantics are frozen, not just a subset of numeric settings.
    if cfg!=read(CONTRACT):raise ValueError('Unsupported frozen research contract mutation')

def state(a,b,positive,negative):
    if any(x is not None and (type(x) not in (int,bool) or x not in (0,1)) for x in (a,b)):
        raise ValueError('Signal must be 0/1/NULL')
    if a==1 and b==1:raise ValueError('Contradictory opposite signals')
    if a is None or b is None:return None
    return positive if a else negative if b else 'other'

def fit(train,cfg):
    n=len(train)
    if n<cfg['minimum_training_rows']:return None
    k=sum(r['y'] for r in train);p0=(k+1)/(n+2);lam=cfg['shrinkage_lambda']
    parents={};cells={}
    for ma in MAS:
        rs=[r for r in train if r['ma_state']==ma];pn=len(rs);pk=sum(r['y'] for r in rs)
        pp=(pk+lam*p0)/(pn+lam) if pn else p0;parents[ma]={'n':pn,'k':pk,'p':pp}
        for vp in VPS:
            sub=[r for r in rs if r['volume_price_state']==vp];cn=len(sub);ck=sum(r['y'] for r in sub)
            cells[(ma,vp)]={'n':cn,'k':ck,'p':(ck+lam*pp)/(cn+lam) if cn else pp}
    return {'n':n,'k':k,'p0':p0,'parents':parents,'cells':cells,'latest_training_label_end':max(r['outcome_observation_date'] for r in train)}

def score(rs,eps):
    n=len(rs)
    if not n:return dict(n=0,positive_count=0,zero_count=0,negative_count=0,mean_prediction=None,positive_frequency=None,brier=None,log_loss=None)
    k=sum(r['y'] for r in rs);z=sum(r['zero_change'] for r in rs)
    return dict(n=n,positive_count=k,zero_count=z,negative_count=n-k-z,mean_prediction=sum(r['p'] for r in rs)/n,positive_frequency=k/n,
      brier=sum((r['p']-r['y'])**2 for r in rs)/n,
      log_loss=-sum(math.log(max(eps,min(1-eps,r['p'] if r['y'] else 1-r['p']))) for r in rs)/n)

def evaluate(labels,signals,anchors,cfg):
    guard(cfg)
    if len({r['signal_date'] for r in labels})!=len(labels):raise ValueError('Duplicate label dates')
    if len({r['trade_date'] for r in signals})!=len(signals):raise ValueError('Duplicate signal dates')
    if anchors!=sorted(set(anchors)):raise ValueError('Duplicate or unordered anchor dates')
    if any(not cfg['development_start']<=d<=cfg['development_end'] for d in anchors):raise ValueError('Non-development anchor')
    sig={r['trade_date']:r for r in signals}
    if set(sig)!=set(anchors):raise ValueError('Signal and anchor domains differ')
    groups={d:(state(s[UP],s[DOWN],'up','down'),state(s[VUP],s[VDOWN],'spike_up','spike_down')) for d,s in sig.items()}
    joined=[]
    for r in labels:
        d=r['signal_date'];entry=r['entry_observation_date'];end=r['outcome_observation_date']
        if d not in sig or not cfg['development_start']<=d<entry<=end<=cfg['development_end']:raise ValueError('Invalid label date domain')
        if r['horizon_observed_sessions']!=5 or r['outcome_sign'] not in ('price_change_gt_0','price_change_eq_0','price_change_lt_0'):raise ValueError('Incompatible label event')
        ma,vp=groups[d]
        joined.append(dict(r,ma_state=ma,volume_price_state=vp,y=int(r['outcome_sign']=='price_change_gt_0'),zero_change=int(r['outcome_sign']=='price_change_eq_0')))
    lookup={r['signal_date']:r for r in joined};grid={d for i,d in enumerate(anchors) if i%5==0}
    predictions=[];fitted_rows=[];members=[];ledger=[];folds=[]
    for fold in cfg['folds']:
        fid=fold['id'];start=fold['validation_start'];end=fold['validation_end']
        candidates=[r for r in joined if r['signal_date']<start]
        mature=[r for r in candidates if r['outcome_observation_date']<start]
        train=[r for r in mature if r['ma_state'] is not None and r['volume_price_state'] is not None]
        fitted=fit(train,cfg)
        for r in candidates:
            reason='TRAIN_LABEL_NOT_MATURE' if r['outcome_observation_date']>=start else 'TRAIN_MA_AND_VOLUME_MISSING' if r['ma_state'] is None and r['volume_price_state'] is None else 'TRAIN_MA_MISSING' if r['ma_state'] is None else 'TRAIN_VOLUME_MISSING' if r['volume_price_state'] is None else 'TRAIN_USED'
            ledger.append(dict(fold_id=fid,role='training',signal_date=r['signal_date'],label_end=r['outcome_observation_date'],reason=reason))
        for r in train:members.append(dict(fold_id=fid,signal_date=r['signal_date'],label_end=r['outcome_observation_date'],ma_state=r['ma_state'],volume_price_state=r['volume_price_state'],y=r['y']))
        if fitted:
            base=dict(fold_id=fid,model_id=MODELS[0],ma_state='ALL',volume_price_state='ALL',training_pool_n=fitted['n'],training_pool_positive=fitted['k'],group_n=fitted['n'],group_positive=fitted['k'],prior_p=None,p=fitted['p0'],prior_only=0,group_n_lt_20=int(fitted['n']<20),latest_training_label_end=fitted['latest_training_label_end'])
            fitted_rows.append(base)
            for ma in MAS:
                parent=fitted['parents'][ma]
                fitted_rows.append(dict(base,model_id=MODELS[1],ma_state=ma,group_n=parent['n'],group_positive=parent['k'],prior_p=fitted['p0'],p=parent['p'],prior_only=int(parent['n']==0),group_n_lt_20=int(parent['n']<20)))
                for vp in VPS:
                    cell=fitted['cells'][(ma,vp)]
                    fitted_rows.append(dict(base,model_id=MODELS[2],ma_state=ma,volume_price_state=vp,group_n=cell['n'],group_positive=cell['k'],prior_p=parent['p'],p=cell['p'],prior_only=int(cell['n']==0),group_n_lt_20=int(cell['n']<20)))
        counts=Counter();valanchors=[d for d in anchors if start<=d<=end]
        for d in valanchors:
            r=lookup.get(d)
            if r is None:reason='NO_REGISTERED_LABEL'
            elif r['outcome_observation_date']>end:reason='LABEL_CROSSES_FOLD_END'
            elif r['ma_state'] is None and r['volume_price_state'] is None:reason='MA_AND_VOLUME_MISSING'
            elif r['ma_state'] is None:reason='MA_MISSING'
            elif r['volume_price_state'] is None:reason='VOLUME_MISSING'
            elif fitted is None:reason='INSUFFICIENT_JOINT_TRAINING'
            else:reason='EVALUATED'
            counts[reason]+=1
            ledger.append(dict(fold_id=fid,role='validation',signal_date=d,label_end=r['outcome_observation_date'] if r else None,reason=reason))
            if reason!='EVALUATED':continue
            ma,vp=r['ma_state'],r['volume_price_state'];parent=fitted['parents'][ma];cell=fitted['cells'][(ma,vp)]
            estimates=[(MODELS[0],fitted['p0'],fitted['n'],fitted['k']),(MODELS[1],parent['p'],parent['n'],parent['k']),(MODELS[2],cell['p'],cell['n'],cell['k'])]
            for mid,p,gn,gk in estimates:
                predictions.append(dict(fold_id=fid,model_id=mid,signal_date=d,entry_observation_date=r['entry_observation_date'],outcome_observation_date=r['outcome_observation_date'],ma_state=ma,volume_price_state=vp,y=r['y'],zero_change=r['zero_change'],p=p,training_pool_n=fitted['n'],model_group_n=gn,model_group_positive=gk,prior_only=int(gn==0),group_n_lt_20=int(gn<20),latest_training_label_end=fitted['latest_training_label_end'],fixed_every_fifth_anchor=int(d in grid),historical_model_input_approved=0,runtime_usable=0))
        folds.append(dict(fold_id=fid,validation_start=start,validation_end=end,train_candidates=len(candidates),train_purged_not_mature=len(candidates)-len(mature),train_mature=len(mature),train_ma_missing=sum(r['ma_state'] is None for r in mature),train_volume_missing=sum(r['volume_price_state'] is None for r in mature),train_joint_missing=len(mature)-len(train),train_used=len(train),latest_training_label_end=fitted['latest_training_label_end'] if fitted else None,validation_anchors=len(valanchors),evaluated_dates=counts['EVALUATED'],no_registered_label=counts['NO_REGISTERED_LABEL'],label_crosses_fold_end=counts['LABEL_CROSSES_FOLD_END'],ma_and_volume_missing=counts['MA_AND_VOLUME_MISSING'],ma_only_missing=counts['MA_MISSING'],volume_only_missing=counts['VOLUME_MISSING'],insufficient_training=counts['INSUFFICIENT_JOINT_TRAINING']))
    metrics=[];comparisons=[];bins=[];paired=[]
    for fid in [f['id'] for f in cfg['folds']]+['POOLED']:
        for subset in ['all_overlapping','fixed_every_fifth_anchor']:
            target=[r for r in predictions if (fid=='POOLED' or r['fold_id']==fid) and (subset=='all_overlapping' or r['fixed_every_fifth_anchor'])]
            bymodel={m:[r for r in target if r['model_id']==m] for m in MODELS}
            scored={m:score(rs,cfg['log_loss_epsilon']) for m,rs in bymodel.items()}
            for m,v in scored.items():metrics.append(dict(fold_id=fid,subset=subset,model_id=m,**v))
            for alt,base in [(MODELS[2],MODELS[1]),(MODELS[2],MODELS[0]),(MODELS[1],MODELS[0])]:
                a,b=scored[alt],scored[base]
                comparisons.append(dict(fold_id=fid,subset=subset,alternative=alt,baseline=base,n=a['n'],alternative_brier=a['brier'],baseline_brier=b['brier'],brier_delta=a['brier']-b['brier'] if a['n'] else None,logloss_delta=a['log_loss']-b['log_loss'] if a['n'] else None,promotion_approved=0))
            if subset!='all_overlapping':continue
            edges=cfg['calibration_bin_edges']
            for m,rs in bymodel.items():
                for j,(lo,hi) in enumerate(zip(edges,edges[1:])):
                    selected=[r for r in rs if lo<=r['p'] and (r['p']<hi or j==len(edges)-2 and r['p']<=hi)]
                    s=score(selected,cfg['log_loss_epsilon'])
                    bins.append(dict(fold_id=fid,model_id=m,bin_low=lo,bin_high=hi,n=s['n'],positive_count=s['positive_count'],zero_count=s['zero_count'],negative_count=s['negative_count'],mean_prediction=s['mean_prediction'],observed_positive_frequency=s['positive_frequency'],observed_minus_prediction=s['positive_frequency']-s['mean_prediction'] if s['n'] else None,empty_bin=int(s['n']==0),sparse_note='empty' if not s['n'] else 'n_lt_20_not_reliability_test' if s['n']<20 else 'n_does_not_certify_calibration',calibration_transform_fitted=0))
    index={(r['fold_id'],r['signal_date'],r['model_id']):r for r in predictions}
    for r in predictions:
        if r['model_id']!=MODELS[2]:continue
        for base in [MODELS[1],MODELS[0]]:
            b=index[(r['fold_id'],r['signal_date'],base)];eps=cfg['log_loss_epsilon']
            paired.append(dict(fold_id=r['fold_id'],signal_date=r['signal_date'],baseline=base,alternative=MODELS[2],y=r['y'],alternative_p=r['p'],baseline_p=b['p'],brier_delta=(r['p']-r['y'])**2-(b['p']-b['y'])**2,logloss_delta=-math.log(max(eps,r['p'] if r['y'] else 1-r['p']))+math.log(max(eps,b['p'] if b['y'] else 1-b['p'])),fixed_every_fifth_anchor=r['fixed_every_fifth_anchor']))
    return dict(predictions=predictions,folds=folds,fitted=fitted_rows,membership=members,ledger=ledger,metrics=metrics,comparisons=comparisons,calibration=bins,paired_loss=paired)

def validate(result,labels,signals,anchors,cfg):
    checks=[]
    def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
    p=result['predictions'];foldmap={f['id']:f for f in cfg['folds']}
    cases=[[(r['fold_id'],r['signal_date'],r['y']) for r in p if r['model_id']==m] for m in MODELS]
    ck('three_models_identical_dates_and_outcomes',cases[0]==cases[1]==cases[2],{'evaluated_dates':len(cases[0]),'empty_means_no_score_not_failure':True})
    ck('all_training_labels_precede_validation',all(r['latest_training_label_end']<r['validation_start'] for r in result['folds'] if r['latest_training_label_end']))
    ck('all_scored_outcomes_within_fold',all(foldmap[r['fold_id']]['validation_start']<=r['signal_date']<r['entry_observation_date']<=r['outcome_observation_date']<=foldmap[r['fold_id']]['validation_end'] for r in p))
    ck('only_development_outcomes',all(r['outcome_observation_date']<'2025-01-01' for r in p))
    ck('all_probabilities_open_unit_interval',all(0<r['p']<1 for r in p))
    ck('runtime_and_input_gates_closed',all(r['runtime_usable']==r['historical_model_input_approved']==0 for r in p))
    ck('validation_coverage_reconciles',all(r['validation_anchors']==sum(r[k] for k in ['evaluated_dates','no_registered_label','label_crosses_fold_end','ma_and_volume_missing','ma_only_missing','volume_only_missing','insufficient_training']) for r in result['folds']))
    ck('all_nine_subcells_and_three_parents_reported',all(sum(r['fold_id']==f['fold_id'] and r['model_id']==MODELS[2] for r in result['fitted'])==9 and sum(r['fold_id']==f['fold_id'] and r['model_id']==MODELS[1] for r in result['fitted'])==3 for f in result['folds'] if f['train_used']>=100))
    ck('all_fitted_formulas',all(math.isclose(r['p'],(r['group_positive']+1)/(r['group_n']+2) if r['model_id']==MODELS[0] else (r['group_positive']+20*r['prior_p'])/(r['group_n']+20),rel_tol=0,abs_tol=1e-15) for r in result['fitted']))
    ck('training_membership_counts',all(sum(r['fold_id']==f['fold_id'] for r in result['membership'])==f['train_used'] for f in result['folds']))
    synthetic=[dict(y=1,ma_state='up',volume_price_state='spike_up',outcome_observation_date='2023-01-10') for _ in range(100)]
    fitted=fit(synthetic,cfg)
    ck('empty_parent_falls_to_p0',fitted['parents']['down']['n']==0 and fitted['parents']['down']['p']==fitted['p0'])
    ck('empty_cell_falls_to_parent',fitted['cells'][('up','spike_down')]['n']==0 and fitted['cells'][('up','spike_down')]['p']==fitted['parents']['up']['p'])
    ck('less_than_100_joint_train_abstains',fit(synthetic[:-1],cfg) is None)
    ck('zero_change_is_nonpositive',all(not r['y'] for r in p if r['zero_change']))
    example=score([dict(p=.25,y=1,zero_change=0),dict(p=.75,y=0,zero_change=0)],1e-12)
    ck('brier_and_logloss_hand_example',math.isclose(example['brier'],.5625) and math.isclose(example['log_loss'],-math.log(.25)))
    ck('empty_score_remains_null',score([],1e-12)['brier'] is None)
    ck('calibration_bins_reconcile',all(sum(r['n'] for r in result['calibration'] if r['fold_id']==fid and r['model_id']==m)==sum(r['model_id']==m and (fid=='POOLED' or r['fold_id']==fid) for r in p) for fid in list(foldmap)+['POOLED'] for m in MODELS))
    grid={d for i,d in enumerate(anchors) if i%5==0}
    ck('original_anchor_fixed_grid',all(r['fixed_every_fifth_anchor']==int(r['signal_date'] in grid) for r in p))
    gp=[r for r in p if r['model_id']==MODELS[0] and r['fixed_every_fifth_anchor']]
    ck('fixed_grid_observation_windows_do_not_overlap',all(a['outcome_observation_date']<b['entry_observation_date'] for a,b in zip(gp,gp[1:])))
    first=cfg['folds'][0];poison=deepcopy(labels)
    for r in poison:
        if first['validation_start']<=r['signal_date']<=first['validation_end']:r['outcome_sign']='price_change_lt_0' if r['outcome_sign']=='price_change_gt_0' else 'price_change_gt_0'
    changed=evaluate(poison,signals,anchors,cfg)
    ck('validation_label_poison_does_not_change_first_fold_fit',[r for r in result['fitted'] if r['fold_id']==first['id']]==[r for r in changed['fitted'] if r['fold_id']==first['id']])
    ck('validation_label_poison_does_not_change_first_fold_probabilities',[(r['signal_date'],r['model_id'],r['p']) for r in p if r['fold_id']==first['id']]==[(r['signal_date'],r['model_id'],r['p']) for r in changed['predictions'] if r['fold_id']==first['id']])
    bad_inputs=[(labels+[deepcopy(labels[0])],signals,anchors),(labels,signals+[deepcopy(signals[0])],anchors),(labels,signals,anchors+[anchors[-1]]),(labels,signals,list(reversed(anchors)))]
    count=0
    for ls,ss,aa in bad_inputs:
        try:evaluate(ls,ss,aa,cfg)
        except ValueError:count+=1
    ck('duplicate_and_unordered_domains_rejected',count==len(bad_inputs))
    count=0
    for a,b in [(1,1),(2,0),(.5,0),(0,'1')]:
        try:state(a,b,'up','down')
        except ValueError:count+=1
    ck('invalid_and_contradictory_signals_rejected',count==4)
    ck('missing_signal_not_zero_filled',state(None,0,'up','down') is None and state(0,None,'up','down') is None)
    count=0
    for key,value in [('shrinkage_lambda',10),('volume_spike_threshold',2),('minimum_training_rows',50),('runtime_usable',True),('development_end','2025-12-31'),('event','net profit')]:
        bad=deepcopy(cfg);bad[key]=value
        try:guard(bad)
        except ValueError:count+=1
    ck('frozen_parameter_mutations_rejected',count==6)
    count=0
    for key,value in [('horizon_observed_sessions',10),('outcome_sign','unknown'),('outcome_observation_date','2025-01-02')]:
        bad=deepcopy(labels);bad[0][key]=value
        try:evaluate(bad,signals,anchors,cfg)
        except ValueError:count+=1
    ck('invalid_label_definition_or_future_date_rejected',count==3)
    ck('paired_loss_reconciles_to_primary_score',all(math.isclose(sum(r['brier_delta'] for r in result['paired_loss'] if r['baseline']==c['baseline'] and (c['fold_id']=='POOLED' or r['fold_id']==c['fold_id']) and (c['subset']=='all_overlapping' or r['fixed_every_fifth_anchor']))/c['n'],c['brier_delta'],rel_tol=0,abs_tol=1e-14) for c in result['comparisons'] if c['alternative']==MODELS[2] and c['n']))
    return checks

def main():
    cfg=read(CONTRACT);receipt=read(RECEIPT);guard(cfg)
    if receipt['contract_sha256']!=sha(CONTRACT) or receipt['producer_code_sha256']!=sha(Path(__file__).resolve()):raise ValueError('Registration does not match contract/code')
    before={p:sha(ROOT/p) for p in receipt['protected_source_sha256']}
    if before!=receipt['protected_source_sha256']:raise ValueError('Protected source changed since registration')
    with ro(ROOT/cfg['input_features']) as c:
        meta=json.loads(c.execute("SELECT value_json FROM metadata WHERE key='run'").fetchone()[0])
        if meta['contract_sha256']!=before['work/baseline_oct25/engineering_contract.json']:raise ValueError('Legacy feature contract mismatch')
        query='SELECT trade_date,'+','.join('"'+s+'"' for s in [UP,DOWN,VUP,VDOWN])+" FROM signals WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date"
        signals=[dict(r) for r in c.execute(query)]
        anchors=[r[0] for r in c.execute("SELECT trade_date FROM input_bars WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date")]
    with ro(ROOT/cfg['input_labels']) as c:
        labels=[dict(r) for r in c.execute("SELECT signal_date,entry_observation_date,outcome_observation_date,outcome_sign,horizon_observed_sessions FROM development_price_outcomes WHERE signal_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY signal_date")]
    if len(labels)!=469 or len(anchors)!=484:raise ValueError('Unexpected source coverage')
    result=evaluate(labels,signals,anchors,cfg);checks=validate(result,labels,signals,anchors,cfg)
    with ro(ROOT/'outputs/初始化与验证推进_20261026/时间验证/开发期滚动验证.sqlite') as c:
        old=[dict(r) for r in c.execute("SELECT fold_id,signal_date,model_id FROM predictions WHERE model_id='M0_laplace_constant' ORDER BY signal_date")]
    new={(r['fold_id'],r['signal_date']) for r in result['predictions'] if r['model_id']==MODELS[0]}
    previous={(r['fold_id'],r['signal_date']) for r in old}
    if not new<=previous:raise ValueError('Joint scoring mask unexpectedly expands old MA-only cases')
    reasons={(r['fold_id'],r['signal_date']):r['reason'] for r in result['ledger'] if r['role']=='validation'}
    result['prior_coverage_comparison']=[dict(fold_id=f['id'],old_ma_only_dates=sum(fid==f['id'] for fid,d in previous),joint_dates=sum(fid==f['id'] for fid,d in new),lost_dates=sum(fid==f['id'] for fid,d in previous-new)) for f in cfg['folds']]
    result['lost_prior_scoring_dates']=[dict(fold_id=fid,signal_date=d,reason=reasons[(fid,d)]) for fid,d in sorted(previous-new)]
    after={p:sha(ROOT/p) for p in before}
    if before!=after:raise ValueError('Source modified during run')
    checks.append(dict(check='registered_sources_unchanged',passed=True,details=after))
    metadata=dict(contract=cfg,registration=receipt,source_sha256=before,outcomes_2025_2026_opened=False,current_forecast_generated=False,runtime_usable=False,model_input_approved=False)
    OUT.mkdir(parents=True,exist_ok=True)
    names={'predictions':'逐日概率与实际结果_仅开发期.csv','folds':'六折训练与覆盖.csv','fitted':'逐折模型与全部九格.csv','membership':'共同训练样本成员.csv','ledger':'训练与验证弃答台账.csv','metrics':'概率评分.csv','comparisons':'同日模型对照.csv','calibration':'固定分箱校准诊断.csv','paired_loss':'逐日配对误差差.csv','prior_coverage_comparison':'与上轮覆盖对账.csv','lost_prior_scoring_dates':'较上轮减少的评分日期.csv'}
    with tempfile.TemporaryDirectory(prefix='incremental_',dir=WORK) as td:
        td=Path(td)
        for key,name in names.items():csvout(td/name,result[key])
        with sqlite3.connect(td/'量价增量开发验证.sqlite') as c:
            for name,rs in result.items():table(c,name,rs)
            c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT)');c.execute('INSERT INTO metadata VALUES(?,?)',('run',enc(metadata)))
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite check failed')
        (td/'预登记研究协议.json').write_text(enc(cfg))
        (td/'运行与输入合同.json').write_text(enc(metadata))
        (td/'实现验证结果.json').write_text(enc(dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,producer_code_sha256=sha(Path(__file__).resolve()),contract_sha256=sha(CONTRACT),source_sha256_before=before,source_sha256_after=after)))
        for path in td.iterdir():shutil.copy2(path,OUT/path.name)
    print(enc(dict(output=str(OUT),checks=len(checks),evaluated_dates=len(new),prediction_rows=len(result['predictions']),lost_vs_previous=len(previous-new),pooled=[r for r in result['metrics'] if r['fold_id']=='POOLED'],comparisons=[r for r in result['comparisons'] if r['fold_id']=='POOLED'])))

if __name__=='__main__':main()
