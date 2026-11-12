"""Frozen development-only walk-forward probability diagnostics, with explicit abstention."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import csv,hashlib,json,math,shutil,sqlite3,tempfile

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/初始化与验证推进_20261026/时间验证'
CONTRACT=WORK/'contract.json'
OLD_CONTRACT=ROOT/'work/baseline_oct25/engineering_contract.json'
OLD_CODE=ROOT/'work/baseline_oct25/build_baseline.py'
OLD_REVIEW=ROOT/'work/baseline_oct25/audit_independent_review.json'
OLD_PROTOCOL=ROOT/'outputs/首版预测协议草案_20261016.json'
SOURCE=ROOT/'outputs/统一数据底座_20261022/统一数据底座.sqlite'
MAIN=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
UP='MA5_gt_MA10_gt_MA15_and_MA15_rising'
DOWN='MA5_lt_MA10_lt_MA15_and_MA15_falling'
SIGNALS=[
 'MA5_cross_above_MA10','MA5_cross_below_MA10','MACD_DIF_cross_above_DEA','MACD_DIF_cross_below_DEA',
 'K_cross_above_D','K_cross_below_D',UP,DOWN,'volume_gt_1p5_prev20_and_close_rising',
 'volume_gt_1p5_prev20_and_close_falling','MA_bull_cross_and_DIF_gt_DEA','MA_bear_cross_and_DIF_lt_DEA']

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def read(p):return json.loads(p.read_text())
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c
def rows(c,sql):return [dict(r) for r in c.execute(sql)]
def csvout(p,data):
    if not data:return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)

def guard_old_contract(c):
    """The legacy implementation is a fixed variant, not an editable parameter API."""
    expected={
      'source_database':'outputs/统一数据底座_20261022/统一数据底座.sqlite','source_view':'stock_raw_reference',
      'calculation_start':'2022-06-01','development_start':'2023-01-03','development_end':'2024-12-31',
      'horizon_observed_sessions':5,'ma_windows':[5,10,15],
      'macd':{'fast':12,'slow':26,'signal':9,'ema_seed':'first segment close','adjust':False,'histogram_multiplier':2,'minimum_segment_bars':130},
      'kdj':{'window':9,'k_alpha':'1/3','d_alpha':'1/3','seed_k':50,'seed_d':50,'flat_range_rsv':50,'minimum_segment_bars':30,'j_clipped':False},
      'volume':{'ratios':[5,20],'denominator':'previous n segment observations excluding current','spike_threshold':1.5,'unit':'same-provider native ratio; no stock/index unit conversion'},
      'registered_signals':SIGNALS,'registered_variant_count':12}
    for key,value in expected.items():
        if c.get(key)!=value:raise ValueError('Unsupported legacy contract change: '+key)

def guard_run_contract(c):
    expected={'development_start':'2023-01-03','development_end':'2024-12-31','horizon_observed_sessions':5,
      'models':['M0_laplace_constant','M1_ma_group_shrinkage'],'shrinkage_lambda':20,'minimum_training_rows':100,
      'event':'C[t+5]/O[t+1]-1 > 0; zero price change joins nonpositive, counted separately',
      'input_features':'outputs/三线研究启动_20261025/量价基线/日线特征与信号.sqlite',
      'input_labels':'outputs/三线研究启动_20261025/量价基线/开发期结果隔离.sqlite',
      'runtime_usable':False,'model_input_approved':False,'current_forecast_generated':False}
    for key,value in expected.items():
        if c.get(key)!=value:raise ValueError('Unsupported research contract change: '+key)
    edges=c['calibration_bin_edges']
    if edges!=[0,.2,.4,.6,.8,1] or c['log_loss_epsilon']!=1e-12:raise ValueError('Unsupported score definition')

def feature_group(up,down):
    if up is None or down is None:return None
    if up not in (0,1) or down not in (0,1) or (up and down):raise ValueError('Invalid MA group signals')
    return 'up' if up else 'down' if down else 'other'

def fit_models(train,cfg):
    n=len(train)
    if n<cfg['minimum_training_rows']:return None
    k=sum(r['y'] for r in train);p0=(k+1)/(n+2);lam=cfg['shrinkage_lambda']
    groups={}
    for group in ['up','down','other']:
        cell=[r for r in train if r['feature_group']==group]
        groups[group]={'n':len(cell),'k':sum(r['y'] for r in cell)}
        groups[group]['p']=(groups[group]['k']+lam*p0)/(groups[group]['n']+lam)
    return {'n':n,'k':k,'p0':p0,'groups':groups,'latest_training_signal':max(r['signal_date'] for r in train),'latest_training_label_end':max(r['outcome_observation_date'] for r in train)}

def scores(preds,epsilon):
    n=len(preds)
    if not n:return {'n':0,'positive_count':0,'zero_price_change_count':0,'positive_frequency':None,'mean_prediction':None,'brier':None,'log_loss':None}
    return {'n':n,'positive_count':sum(r['y'] for r in preds),'zero_price_change_count':sum(r['zero_price_change'] for r in preds),
      'positive_frequency':sum(r['y'] for r in preds)/n,'mean_prediction':sum(r['p'] for r in preds)/n,
      'brier':sum((r['p']-r['y'])**2 for r in preds)/n,
      'log_loss':-sum(r['y']*math.log(max(epsilon,min(1-epsilon,r['p'])))+(1-r['y'])*math.log(max(epsilon,min(1-epsilon,1-r['p']))) for r in preds)/n}

def evaluate(label_rows,signal_rows,anchors,cfg):
    if len({r['signal_date'] for r in label_rows})!=len(label_rows):raise ValueError('Duplicate label dates')
    if len({r['trade_date'] for r in signal_rows})!=len(signal_rows):raise ValueError('Duplicate signal dates')
    if anchors!=sorted(set(anchors)):raise ValueError('Duplicate or unordered anchor dates')
    bysignal={r['trade_date']:r for r in signal_rows}
    labels=[]
    for r in label_rows:
        if not cfg['development_start']<=r['signal_date']<=r['outcome_observation_date']<=cfg['development_end']:raise ValueError('Non-development label rejected')
        if r['outcome_sign'] not in ['price_change_gt_0','price_change_eq_0','price_change_lt_0'] or r['horizon_observed_sessions']!=cfg['horizon_observed_sessions']:raise ValueError('Incompatible label definition')
        s=bysignal[r['signal_date']]
        labels.append(dict(r,feature_group=feature_group(s[UP],s[DOWN]),y=int(r['outcome_sign']=='price_change_gt_0'),zero_price_change=int(r['outcome_sign']=='price_change_eq_0')))
    lookup={r['signal_date']:r for r in labels}
    anchor_grid={d for i,d in enumerate(anchors) if i%5==0}
    preds=[];membership=[];purges=[];folds=[];models=[]
    for fold in cfg['folds']:
        start,end=fold['validation_start'],fold['validation_end'];fid=fold['id']
        candidates=[r for r in labels if r['signal_date']<start]
        purged=[r for r in candidates if r['outcome_observation_date']>=start]
        for r in purged:purges.append(dict(fold_id=fid,signal_date=r['signal_date'],label_end=r['outcome_observation_date'],reason='TRAIN_LABEL_NOT_MATURE_BEFORE_VALIDATION_START'))
        matured=[r for r in candidates if r['outcome_observation_date']<start]
        train=[r for r in matured if r['feature_group'] is not None]
        fitted=fit_models(train,cfg)
        for r in train:membership.append(dict(fold_id=fid,signal_date=r['signal_date'],label_end=r['outcome_observation_date'],feature_group=r['feature_group'],y=r['y']))
        if fitted:
            for group,v in fitted['groups'].items():
                models.append(dict(fold_id=fid,group_id=group,train_n=fitted['n'],train_positive=fitted['k'],p0=fitted['p0'],group_n=v['n'],group_positive=v['k'],group_p=v['p'],lambda_value=cfg['shrinkage_lambda'],latest_training_signal=fitted['latest_training_signal'],latest_training_label_end=fitted['latest_training_label_end']))
        valanchors=[d for d in anchors if start<=d<=end];reasons=Counter();evaluated=[]
        for day in valanchors:
            r=lookup.get(day)
            if r is None:reason='NO_REGISTERED_MATURE_DEVELOPMENT_LABEL'
            elif r['outcome_observation_date']>end:reason='VALIDATION_LABEL_END_AFTER_FOLD_END'
            elif r['feature_group'] is None:reason='MA_FEATURE_NOT_READY'
            elif fitted is None:reason='INSUFFICIENT_TRAINING_ROWS'
            else:reason='EVALUATED';evaluated.append(r)
            reasons[reason]+=1
            purges.append(dict(fold_id=fid,signal_date=day,label_end=r['outcome_observation_date'] if r else None,reason=reason))
        if fitted:
            for r in evaluated:
                cell=fitted['groups'][r['feature_group']]
                for model_id,p in [(cfg['models'][0],fitted['p0']),(cfg['models'][1],cell['p'])]:
                    preds.append(dict(fold_id=fid,model_id=model_id,signal_date=r['signal_date'],entry_observation_date=r['entry_observation_date'],outcome_observation_date=r['outcome_observation_date'],
                      feature_group=r['feature_group'],y=r['y'],zero_price_change=r['zero_price_change'],p=p,train_n=fitted['n'],group_train_n=cell['n'],group_positive_count=cell['k'],
                      group_prior_only=int(model_id==cfg['models'][1] and cell['n']==0),latest_training_label_end=fitted['latest_training_label_end'],fixed_every_fifth_anchor=int(r['signal_date'] in anchor_grid),
                      historical_model_input_approved=0,runtime_usable=0,scope='previously_explored_development_time_ordered_diagnostic'))
        folds.append(dict(fold_id=fid,validation_start=start,validation_end=end,train_candidate_labels=len(candidates),train_purged_not_mature=len(purged),train_mature_labels=len(matured),train_feature_missing=len(matured)-len(train),train_used=len(train),
          latest_training_label_end=fitted['latest_training_label_end'] if fitted else None,validation_anchors=len(valanchors),evaluated_dates=len(evaluated),coverage=len(evaluated)/len(valanchors) if valanchors else None,
          no_registered_label=reasons['NO_REGISTERED_MATURE_DEVELOPMENT_LABEL'],label_crosses_fold_end=reasons['VALIDATION_LABEL_END_AFTER_FOLD_END'],feature_not_ready=reasons['MA_FEATURE_NOT_READY'],insufficient_training=reasons['INSUFFICIENT_TRAINING_ROWS']))
    metrics=[];calibration=[];comparisons=[]
    for fid in [r['id'] for r in cfg['folds']]+['POOLED']:
        for subset in ['all_overlapping','fixed_every_fifth_anchor']:
            target=[r for r in preds if (fid=='POOLED' or r['fold_id']==fid) and (subset=='all_overlapping' or r['fixed_every_fifth_anchor'])]
            bymodel={m:[r for r in target if r['model_id']==m] for m in cfg['models']}
            assert [(r['signal_date'],r['y']) for r in bymodel[cfg['models'][0]]]==[(r['signal_date'],r['y']) for r in bymodel[cfg['models'][1]]]
            scored={m:scores(rs,cfg['log_loss_epsilon']) for m,rs in bymodel.items()}
            for m,s in scored.items():metrics.append(dict(fold_id=fid,subset=subset,model_id=m,**s))
            a,b=[scored[m] for m in cfg['models']]
            comparisons.append(dict(fold_id=fid,subset=subset,n=a['n'],brier_M0=a['brier'],brier_M1=b['brier'],brier_delta_M1_minus_M0=b['brier']-a['brier'] if a['n'] else None,
              brier_skill_M1_vs_M0=1-b['brier']/a['brier'] if a['n'] and a['brier']>0 else None,logloss_delta_M1_minus_M0=b['log_loss']-a['log_loss'] if a['n'] else None,performance_release_approved=0))
            if subset=='all_overlapping':
                edges=cfg['calibration_bin_edges']
                for m,rs in bymodel.items():
                    for j,(lo,hi) in enumerate(zip(edges,edges[1:])):
                        cell=[r for r in rs if lo<=r['p'] and (r['p']<hi or (j==len(edges)-2 and r['p']<=hi))]
                        s=scores(cell,cfg['log_loss_epsilon'])
                        calibration.append(dict(fold_id=fid,model_id=m,bin_low=lo,bin_high=hi,n=s['n'],positive_count=s['positive_count'],zero_price_change_count=s['zero_price_change_count'],negative_count=s['n']-s['positive_count']-s['zero_price_change_count'],mean_prediction=s['mean_prediction'],observed_positive_frequency=s['positive_frequency'],observed_minus_predicted=s['positive_frequency']-s['mean_prediction'] if cell else None,empty_bin=int(not cell),sparse_display_note='empty' if not cell else 'fewer_than_20_not_a_reliability_test' if len(cell)<20 else 'count_does_not_certify_calibration',calibration_transform_fitted=0))
    return {'predictions':preds,'folds':folds,'models':models,'membership':membership,'ledger':purges,'metrics':metrics,'comparisons':comparisons,'calibration':calibration}

def validate(result,label_rows,signal_rows,anchors,cfg):
    checks=[]
    def check(n,ok,details=None):checks.append(dict(check=n,passed=bool(ok),details=details));assert ok,n
    p=result['predictions']
    check('six_disjoint_quarter_folds',len(result['folds'])==6 and len({r['signal_date'] for r in p})==sum(r['evaluated_dates'] for r in result['folds']))
    check('no_training_label_reaches_validation_start',all(r['latest_training_label_end']<r['validation_start'] for r in result['folds'] if r['latest_training_label_end']))
    check('all_prediction_outcomes_within_fold',all(next(f for f in cfg['folds'] if f['id']==r['fold_id'])['validation_start']<=r['signal_date']<r['outcome_observation_date']<=next(f for f in cfg['folds'] if f['id']==r['fold_id'])['validation_end'] for r in p))
    check('no_2025_2026_outcomes',all(r['outcome_observation_date']<'2025-01-01' for r in p))
    check('both_models_same_cases',all(sum(r['model_id']==m for r in p)==len(p)//2 for m in cfg['models']) and len(p)>0)
    check('all_probabilities_strictly_between_zero_one',all(0<r['p']<1 for r in p))
    check('all_formal_gates_remain_closed',all(r['historical_model_input_approved']==0 and r['runtime_usable']==0 for r in p))
    check('coverage_reason_accounting',all(r['validation_anchors']==r['evaluated_dates']+r['no_registered_label']+r['label_crosses_fold_end']+r['feature_not_ready']+r['insufficient_training'] for r in result['folds']))
    check('fitted_shrinkage_formula',all(math.isclose(r['p0'],(r['train_positive']+1)/(r['train_n']+2),abs_tol=1e-15) and math.isclose(r['group_p'],(r['group_positive']+20*r['p0'])/(r['group_n']+20),abs_tol=1e-15) for r in result['models']))
    check('brier_manual_example',math.isclose(scores([{'p':.25,'y':1,'zero_price_change':0},{'p':.75,'y':0,'zero_price_change':0}],1e-12)['brier'],.5625))
    check('logloss_manual_example',math.isclose(scores([{'p':.25,'y':1,'zero_price_change':0},{'p':.75,'y':0,'zero_price_change':0}],1e-12)['log_loss'],-math.log(.25)))
    small=fit_models([{'y':1,'feature_group':'up','signal_date':'2023-01-03','outcome_observation_date':'2023-01-10'}]*100,cfg)
    check('empty_group_explicit_prior_only',small['groups']['down']['n']==0 and small['groups']['down']['p']==small['p0'])
    check('insufficient_training_is_not_zero_probability',fit_models([],cfg) is None)
    check('zero_changes_join_nonpositive',all(r['y']==0 for r in p if r['zero_price_change']))
    check('all_ma_feature_missing_is_explicit',sum(r['feature_not_ready'] for r in result['folds'])==sum(r['reason']=='MA_FEATURE_NOT_READY' for r in result['ledger']))
    # Poison only validation labels, refit, and prove fold fitted parameters did not change.
    first=cfg['folds'][0];changed=[]
    for r in label_rows:
        r=dict(r)
        if first['validation_start']<=r['signal_date']<=first['validation_end']:
            r['outcome_sign']='price_change_lt_0' if r['outcome_sign']=='price_change_gt_0' else 'price_change_gt_0'
        changed.append(r)
    altered=evaluate(changed,signal_rows,anchors,cfg)
    check('validation_label_poison_does_not_change_first_fold_fit', [r for r in result['models'] if r['fold_id']==first['id']]==[r for r in altered['models'] if r['fold_id']==first['id']])
    # Later training folds may legitimately learn matured prior validation labels.
    check('validation_label_poison_does_not_change_its_predictions',[(r['signal_date'],r['model_id'],r['p']) for r in p if r['fold_id']==first['id']]==[(r['signal_date'],r['model_id'],r['p']) for r in altered['predictions'] if r['fold_id']==first['id']])
    old=read(OLD_CONTRACT);guard_old_contract(old);mutations=[]
    for group,key,value in [('macd','fast',10),('macd','adjust',True),('macd','histogram_multiplier',1),('kdj','window',5),('kdj','k_alpha','1/2'),('kdj','seed_k',0),('kdj','flat_range_rsv',0),('kdj','j_clipped',True),('volume','spike_threshold',2)]:
        c=deepcopy(old);c[group][key]=value;mutations.append(c)
    c=deepcopy(old);c['registered_signals']=list(reversed(c['registered_signals']));mutations.append(c)
    c=deepcopy(old);c['registered_signals'][0]='renamed_signal';mutations.append(c)
    c=deepcopy(old);c['ma_windows']=[3,5,10];mutations.append(c)
    rejected=0
    for c in mutations:
        try:guard_old_contract(c)
        except ValueError:rejected+=1
    check('unsupported_legacy_parameters_and_signal_names_rejected',rejected==len(mutations),{'negative_cases':len(mutations)})
    bad_contracts=[]
    for key,value in [('horizon_observed_sessions',10),('event','net_profit'),('model_input_approved',True),('development_end','2025-12-31')]:
        c=deepcopy(cfg);c[key]=value;bad_contracts.append(c)
    rejected=0
    for c in bad_contracts:
        try:guard_run_contract(c)
        except ValueError:rejected+=1
    check('incompatible_target_or_release_contract_rejected',rejected==4)
    rejected=0
    for key,value in [('horizon_observed_sessions',10),('outcome_sign','not_defined')]:
        bad=deepcopy(label_rows);bad[0][key]=value
        try:evaluate(bad,signal_rows,anchors,cfg)
        except ValueError:rejected+=1
    check('incompatible_label_rows_rejected',rejected==2)
    check('calibration_bins_reconcile_to_scored_cases',all(sum(r['n'] for r in result['calibration'] if r['fold_id']==fid and r['model_id']==m)==sum(r['fold_id']==fid and r['model_id']==m for r in p) for fid in [f['id'] for f in cfg['folds']] for m in cfg['models']))
    grid=[r for r in p if r['model_id']==cfg['models'][0] and r['fixed_every_fifth_anchor']]
    check('fixed_grid_outcome_windows_do_not_overlap',all(a['outcome_observation_date']<b['entry_observation_date'] for a,b in zip(grid,grid[1:])))
    rejected=0
    for ls,ss,aa in [(label_rows+[deepcopy(label_rows[0])],signal_rows,anchors),(label_rows,signal_rows+[deepcopy(signal_rows[0])],anchors),(label_rows,signal_rows,anchors+[anchors[-1]])]:
        try:evaluate(ls,ss,aa,cfg)
        except ValueError:rejected+=1
    check('duplicate_source_dates_rejected_before_fit',rejected==3)
    return checks

def table(c,name,data):
    if not data:return
    fields=list(data[0]);types=[]
    for k in fields:
        v=next((r[k] for r in data if r[k] is not None),None)
        types.append('INTEGER' if isinstance(v,(int,bool)) else 'REAL' if isinstance(v,float) else 'TEXT')
    q=lambda x:'"'+x.replace('"','""')+'"'
    c.execute('CREATE TABLE '+q(name)+'('+','.join(q(k)+' '+t for k,t in zip(fields,types))+')')
    c.executemany('INSERT INTO '+q(name)+' VALUES('+','.join('?' for _ in fields)+')',[tuple(r[k] for k in fields) for r in data])

def main():
    cfg=read(CONTRACT);guard_old_contract(read(OLD_CONTRACT));guard_run_contract(cfg)
    assert cfg['models']==['M0_laplace_constant','M1_ma_group_shrinkage'] and cfg['shrinkage_lambda']==20 and cfg['minimum_training_rows']==100
    assert not cfg['runtime_usable'] and not cfg['current_forecast_generated']
    # Registration is created once before any target values are read in this pipeline.
    receipt=WORK/'registration_receipt.json'
    if receipt.exists():assert read(receipt)['contract_sha256']==sha(CONTRACT)
    else:receipt.write_text(enc({'experiment_id':cfg['experiment_id'],'contract_sha256':sha(CONTRACT),'registered_at_utc':datetime.now(timezone.utc).isoformat(),'previous_development_exploration_disclosed':True}))
    feature_path=ROOT/cfg['input_features'];label_path=ROOT/cfg['input_labels']
    protected=[SOURCE,MAIN,OLD_PROTOCOL,OLD_CONTRACT,OLD_CODE,feature_path,label_path]
    before={str(p.relative_to(ROOT)):sha(p) for p in protected}
    previous_review=read(OLD_REVIEW);assert previous_review['producer_code_sha256']==sha(OLD_CODE) and previous_review['contract_sha256']==sha(OLD_CONTRACT)
    with ro(feature_path) as c:
        meta=json.loads(c.execute('SELECT value_json FROM metadata WHERE key="run"').fetchone()[0])
        assert meta['contract_sha256']==sha(OLD_CONTRACT) and meta['contract']==read(OLD_CONTRACT)
        sig=rows(c,'SELECT trade_date,"'+UP+'","'+DOWN+'" FROM signals WHERE trade_date BETWEEN \'2023-01-03\' AND \'2024-12-31\' ORDER BY trade_date')
        anchors=[r[0] for r in c.execute("SELECT trade_date FROM input_bars WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date")]
    with ro(label_path) as c:
        labels=rows(c,"SELECT signal_date,entry_observation_date,outcome_observation_date,outcome_sign,horizon_observed_sessions FROM development_price_outcomes WHERE signal_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY signal_date")
    assert len(labels)==469 and len(anchors)==484
    result=evaluate(labels,sig,anchors,cfg);checks=validate(result,labels,sig,anchors,cfg)
    after={str(p.relative_to(ROOT)):sha(p) for p in protected};assert before==after
    checks.append(dict(check='all_seven_source_stores_contracts_code_unchanged',passed=before==after,details=after))
    metadata={'experiment_contract':cfg,'contract_sha256':sha(CONTRACT),'registration_receipt':read(receipt),'source_sha256':before,'outcomes_2025_2026_opened':False,'current_forecast_generated':False,'runtime_usable':False,'model_input_approved':False,'model_variants_this_run':2}
    OUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validation_oct26_',dir=WORK) as td:
        td=Path(td)
        names={'predictions':'滚动验证概率与结果_仅开发期.csv','folds':'时间分折与覆盖.csv','models':'每折训练模型.csv','membership':'训练样本成员.csv','ledger':'剔除与弃答台账.csv','metrics':'概率评分.csv','comparisons':'与常数基准对照.csv','calibration':'固定分箱校准诊断.csv'}
        for key,name in names.items():csvout(td/name,result[key])
        with sqlite3.connect(td/'开发期滚动验证.sqlite') as c:
            for key,data in result.items():table(c,key,data)
            c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT)');c.execute('INSERT INTO metadata VALUES(?,?)',('run',enc(metadata)))
            assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        (td/'运行与输入合同.json').write_text(enc(metadata))
        (td/'研究验证协议_v1.json').write_text(enc(cfg))
        (td/'验证结果.json').write_text(enc({'checks':checks,'passed':len(checks),'total':len(checks),'all_checks_passed':True,'source_sha256_before':before,'source_sha256_after':after}))
        pooled=next(r for r in result['comparisons'] if r['fold_id']=='POOLED' and r['subset']=='all_overlapping')
        fixed=next(r for r in result['comparisons'] if r['fold_id']=='POOLED' and r['subset']=='fixed_every_fifth_anchor')
        base=next(r for r in result['metrics'] if r['fold_id']=='POOLED' and r['subset']=='all_overlapping' and r['model_id']==cfg['models'][0])
        alt=next(r for r in result['metrics'] if r['fold_id']=='POOLED' and r['subset']=='all_overlapping' and r['model_id']==cfg['models'][1])
        fold_table='\n'.join('| '+r['fold_id']+f" | {r['train_used']} | {r['validation_anchors']} | {r['evaluated_dates']} | {r['feature_not_ready']} | {r['label_crosses_fold_end']} |" for r in result['folds'])
        doc=f'''# 首版研究验证：按时间推进的开发期对照

2026年10月26日。已冻结本轮研究-only协议并实现实际逐折拟合和预测记录，所有参数先登记再运行。本轮只打开2023—2024已探索开发期；2025校准候选、2026后续评估候选均未生成或汇总结果，也不称它们从未被研究者观察。

固定事件：下一观察日开盘到第5观察日收盘的价格变化是否大于0。零变化归“非正”，另计零值数量；它不是税费后盈利、可成交收益、最终方向阈值或当前买卖概率。原首版预测草案及风险设置没有被覆盖。本轮助手研究默认选择可执行，但不代表用户确认实盘参数。

## 两个预先固定的简单模型

M0：过去已成熟且均线特征可计算的训练窗口，p0=(正变化数+1)/(训练数+2)。M1：沿用上一轮预登记均线结构，把日期分为上行、下行、其他3组，pg=(组内正数+20×p0)/(组内样本数+20)。组内无样本时明确报告prior-only，按已登记公式回到p0。没有调整20、试不同均线或从旧12信号的历史高频排行中挑赢家。

MACD、KDJ及筹码此次不强塞入最小模型；它们的覆盖和不确定性单独保留。两个模型在完全相同的训练和验证日期比较，任何均线特征缺失就明确弃答。训练少于100行整折弃答；100只是工程启动门槛，不是统计充分性认证。

每折只训练一次，整季参数冻结。训练标签的实际结束日必须早于验证首日，验证标签结束日必须不晚于该折末日；用实际结束日期清除跨界标签，不能只凭信号日期或随机切分。旧表已剔除已知除权窗口；均线继续沿用分段且不跨除权的定义。

|折|训练可用|验证锚点|实际评分日期|均线未就绪|结果越过折末|
|---|---:|---:|---:|---:|---:|
{fold_table}

## 本轮实际概率评分

汇总{pooled['n']}个评分日期（每日期两个模型），相邻5日结果会重叠，不能称独立试验。固定每5个原开发锚点取一次的敏感性网格仅{fixed['n']}个评分日期，也不保证独立。未尝试其他相位再挑最好结果。

|模型|Brier（越低越好）|对数损失（越低越好）|
|---|---:|---:|
|M0 常数基准|{base['brier']:.6f}|{base['log_loss']:.6f}|
|M1 均线分组收缩|{alt['brier']:.6f}|{alt['log_loss']:.6f}|

M1−M0的Brier差为{pooled['brier_delta_M1_minus_M0']:+.6f}，对数损失差为{pooled['logloss_delta_M1_minus_M0']:+.6f}。固定网格的Brier差为{fixed['brier_delta_M1_minus_M0']:+.6f}。这只是已探索开发期的时间顺序诊断，不据一个汇总分数宣布某模型胜出、预测有效或能赚钱。逐折、全部评分和弃答均保存。

固定5个概率分箱给出预测均值、实际正变化频率及样本数；空箱留空而不是0。这里只做校准诊断，没有用验证结果拟合校准函数、置信区间或显著性结论。以后如果改变模型、特征或参数，需登记新的研究版本，不能重置试验记录。

## 输入保护与验证

旧指标生成器有一部分参数是固定实现。本轮新增入口逐项核对MACD、KDJ、均线、量比及12个信号名称/顺序，不支持的参数改动直接拒绝，防止改了合同但程序仍静默用旧参数。旧源码和旧产物均保留。

{len(checks)}/{len(checks)}项技术检查通过：标签结束日隔离、M0/M1相同日期、覆盖原因对账、公式手算、空组收缩、训练不足弃答、验证标签污染不改变该折训练或概率、12个旧配置改动负例及7份原文件哈希未变。独立来源审计另附。本轮没有认证日级ST/停复牌、信息首次可用、限价、滑点及费用，因此所有正式输入与runtime门仍关闭。

文件：开发期滚动验证.sqlite包含训练成员、逐折参数、预测与实际结果、评分、校准分箱和弃答台账；不含2025/2026结果。所有概率均为这次回顾性开发验证产物，不提供当前股票的预测卡。

技术依据：[时间序列按时间分割](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)、[概率校准说明](https://scikit-learn.org/stable/modules/calibration.html)、[Brier评分定义](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html)。本轮按实际标签结束日自行实现清除边界，比固定gap更直接匹配本标签；没有调用这些库替本轮数据准入背书。
'''
        (td/'首版时间验证报告.md').write_text(doc)
        for p in td.iterdir():shutil.copy2(p,OUT/p.name)
    print(enc({'output':str(OUT),'evaluated_dates':pooled['n'],'fixed_grid_dates':fixed['n'],'folds':6,'models':2,'checks':len(checks),'sources_unchanged':before==after,'brier_M0':base['brier'],'brier_M1':alt['brier']}))

if __name__=='__main__':main()
