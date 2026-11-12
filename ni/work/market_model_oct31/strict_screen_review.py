"""Publication guard for complete fold/subset identities; no fitting or tuning.

Added during independent audit. The frozen candidate producer, registration and
its initial result remain intact. Reports must pass this stricter result gate.
"""
from copy import deepcopy
import math

def strict_screen(comparisons,cfg):
    ids=[f['id'] for f in cfg['folds']]
    if len(ids)!=6 or len(set(ids))!=6:raise ValueError('Registered fold IDs must be six unique values')
    subsets=['all_overlapping','fixed_every_fifth_anchor']
    expected={(fid,subset) for fid in ids+['POOLED'] for subset in subsets}
    keys=[(r['fold_id'],r['subset']) for r in comparisons]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:raise ValueError('Missing, duplicated, or unexpected fold/subset identity')
    bykey=dict(zip(keys,comparisons))
    metric_names=['brier_M0','brier_M3','brier_delta_M3_minus_M0','logloss_delta_M3_minus_M0']
    for r in comparisons:
        if type(r['n']) is not int or r['n']<0:raise ValueError('Invalid result count')
        if r['promotion_approved']!=0:raise ValueError('Result cannot promote itself')
        values=[r[k] for k in metric_names]
        if not r['n']:
            if any(v is not None for v in values):raise ValueError('Empty result has nonempty metric')
            continue
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Nonfinite or missing scored metric')
        if not (0<=r['brier_M0']<=1 and 0<=r['brier_M3']<=1):raise ValueError('Brier out of bounds')
        if not math.isclose(r['brier_M3']-r['brier_M0'],r['brier_delta_M3_minus_M0'],rel_tol=0,abs_tol=1e-12):raise ValueError('Inconsistent paired Brier difference')
    for subset in subsets:
        if sum(bykey[(fid,subset)]['n'] for fid in ids)!=bykey[('POOLED',subset)]['n']:raise ValueError('Pooled count does not equal all registered folds')
    for fid in ids+['POOLED']:
        if bykey[(fid,subsets[1])]['n']>bykey[(fid,subsets[0])]['n']:raise ValueError('Fixed-grid count exceeds full count')
    pooled=bykey[('POOLED',subsets[0])];grid=bykey[('POOLED',subsets[1])]
    folds=[bykey[(fid,subsets[0])] for fid in ids]
    evaluable=all(r['n']>0 for r in [pooled,grid]+folds)
    lower=sum(r['brier_delta_M3_minus_M0']<0 for r in folds if r['n'])
    conditions=dict(pooled_brier_strictly_lower=pooled['brier_delta_M3_minus_M0']<0 if evaluable else None,pooled_logloss_strictly_lower=pooled['logloss_delta_M3_minus_M0']<0 if evaluable else None,fixed_grid_brier_no_worse=grid['brier_delta_M3_minus_M0']<=0 if evaluable else None,at_least_four_folds_strictly_lower=lower>=4 if evaluable else None)
    return dict(evaluable=evaluable,not_evaluable_reason=None if evaluable else 'One or more registered folds or fixed-grid metrics unavailable',lower_brier_fold_count=lower,conditions=conditions,passed=bool(evaluable and all(conditions.values())),statistical_or_profit_proof=False,automatic_phase_promotion=False)

def validate_guard(comparisons,cfg):
    checks=[]
    def ck(name,passed):checks.append(dict(check=name,passed=bool(passed)));assert passed,name
    variants=[]
    bad=deepcopy(comparisons);bad[1]=deepcopy(bad[0]);variants.append(('duplicate_replaces_missing_same_length',bad))
    variants.append(('missing_fold_or_subset',deepcopy(comparisons[:-1])))
    bad=deepcopy(comparisons);bad.append(deepcopy(bad[0]));variants.append(('duplicate_extra_row',bad))
    bad=deepcopy(comparisons);bad[0]['fold_id']='unregistered';variants.append(('unregistered_fold',bad))
    bad=deepcopy(comparisons);bad[0]['subset']='chosen_best_phase';variants.append(('unregistered_subset',bad))
    for value in [float('nan'),float('inf'),float('-inf'),None]:
        bad=deepcopy(comparisons);bad[0]['brier_delta_M3_minus_M0']=value;variants.append(('invalid_scored_metric_'+str(value),bad))
    bad=deepcopy(comparisons);bad[-1]['n']+=1;variants.append(('pooled_count_mismatch',bad))
    bad=deepcopy(comparisons);bad[0]['promotion_approved']=1;variants.append(('promotion_rejected',bad))
    for name,bad in variants:
        rejected=False
        try:strict_screen(bad,cfg)
        except ValueError:rejected=True
        ck(name,rejected)
    ck('valid_exact_identity_result_accepted',strict_screen(comparisons,cfg)['evaluable'])
    empty=deepcopy(comparisons)
    for r in empty:
        r['n']=0
        for key in ['brier_M0','brier_M3','brier_delta_M3_minus_M0','logloss_delta_M3_minus_M0']:r[key]=None
    ck('complete_but_empty_results_are_not_evaluable',not strict_screen(empty,cfg)['evaluable'] and not strict_screen(empty,cfg)['passed'])
    empty[0]['promotion_approved']=1
    rejected=False
    try:strict_screen(empty,cfg)
    except ValueError:rejected=True
    ck('empty_result_cannot_promote_itself',rejected)
    return checks
