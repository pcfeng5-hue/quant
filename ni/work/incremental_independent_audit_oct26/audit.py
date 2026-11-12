"""Independent stdlib reconstruction; producer imported only for adversarial probes."""
from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from copy import deepcopy
from datetime import datetime, timezone
import ast, csv, hashlib, importlib.util, json, math, sqlite3
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORK=ROOT/'work/incremental_validation_oct26'
OUT=ROOT/'outputs/量价增量验证_20261026'
CFG=json.loads((WORK/'contract.json').read_text())
RC=json.loads((WORK/'registration_receipt.json').read_text())
M=['M0_laplace_constant','M1_ma_group_shrinkage','M2_ma_volume_hierarchical']
MA=['up','down','other']; VP=['spike_up','spike_down','other']
C=['MA5_gt_MA10_gt_MA15_and_MA15_rising','MA5_lt_MA10_lt_MA15_and_MA15_falling','volume_gt_1p5_prev20_and_close_rising','volume_gt_1p5_prev20_and_close_falling']
checks=[]
def ck(name,ok,detail=None):
    checks.append({'check':name,'passed':bool(ok),'details':detail})
    if not ok: raise AssertionError(name+': '+str(detail))
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def connect(path):
    x=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);x.row_factory=sqlite3.Row
    x.execute('PRAGMA query_only=ON');return x
def readrows(con,table):return [dict(x) for x in con.execute('SELECT * FROM "'+table+'"')]
def state(x,y,poss):
    assert x in [None,0,1] and y in [None,0,1] and (x,y)!=(1,1)
    if x is None or y is None:return None
    return poss[0] if x else poss[1] if y else 'other'
def dec(x):return Decimal(x)
def stats(rows):
    n=len(rows)
    if not n:return dict(n=0,positive_count=0,zero_count=0,negative_count=0,mean_prediction=None,positive_frequency=None,brier=None,log_loss=None)
    k=sum(x['y'] for x in rows);z=sum(x['zero_change'] for x in rows)
    return dict(n=n,positive_count=k,zero_count=z,negative_count=n-k-z,
      mean_prediction=math.fsum(x['p'] for x in rows)/n,positive_frequency=k/n,
      brier=math.fsum((x['p']-x['y'])**2 for x in rows)/n,
      log_loss=math.fsum(-math.log(max(CFG['log_loss_epsilon'], min(1-CFG['log_loss_epsilon'], x['p'] if x['y'] else 1-x['p']))) for x in rows)/n)

def reconstruct(labels,signals,anchors):
    # Independent grouping pass, rational/Decimal fit, then materialize all rows.
    gm={x['trade_date']:(state(x[C[0]],x[C[1]],MA[:2]),state(x[C[2]],x[C[3]],VP[:2])) for x in signals}
    ls={x['signal_date']:{**x,'ma_state':gm[x['signal_date']][0],'volume_price_state':gm[x['signal_date']][1], 'y':int(x['outcome_sign']=='price_change_gt_0'),'zero_change':int(x['outcome_sign']=='price_change_eq_0')} for x in labels}
    grid=set(anchors[::5]); r={k:[] for k in ['predictions','folds','fitted','membership','ledger','metrics','comparisons','calibration','paired_loss']}
    for f in CFG['folds']:
        fid,lo,hi=f['id'],f['validation_start'],f['validation_end']
        candidates=[ls[d] for d in sorted(ls) if d<lo]
        mature=[x for x in candidates if x['outcome_observation_date']<lo]
        train=[x for x in mature if None not in (x['ma_state'],x['volume_price_state'])]
        for x in candidates:
            if x['outcome_observation_date']>=lo:reason='TRAIN_LABEL_NOT_MATURE'
            elif x['ma_state'] is None and x['volume_price_state'] is None:reason='TRAIN_MA_AND_VOLUME_MISSING'
            elif x['ma_state'] is None:reason='TRAIN_MA_MISSING'
            elif x['volume_price_state'] is None:reason='TRAIN_VOLUME_MISSING'
            else:reason='TRAIN_USED'
            r['ledger'].append(dict(fold_id=fid,role='training',signal_date=x['signal_date'],label_end=x['outcome_observation_date'],reason=reason))
        for x in train:r['membership'].append(dict(fold_id=fid,signal_date=x['signal_date'],label_end=x['outcome_observation_date'],ma_state=x['ma_state'],volume_price_state=x['volume_price_state'],y=x['y']))
        fit={};latest=max((x['outcome_observation_date'] for x in train),default=None)
        if len(train)>=100:
            n,k=len(train),sum(x['y'] for x in train)
            parent_counts={a:[0,0] for a in MA};cell_counts={(a,b):[0,0] for a in MA for b in VP}
            for x in train:
                pair=parent_counts[x['ma_state']];pair[0]+=1;pair[1]+=x['y']
                pair=cell_counts[x['ma_state'],x['volume_price_state']];pair[0]+=1;pair[1]+=x['y']
            with localcontext() as ctx:
                ctx.prec=70
                p0=dec(k+1)/dec(n+2)
                fit[(M[0],'ALL','ALL')]=(n,k,p0,None)
                for a in MA:
                    pn,pk=parent_counts[a];pm=(dec(pk)+dec(20)*p0)/dec(pn+20)
                    fit[(M[1],a,'ALL')]=(pn,pk,pm,p0)
                    for b in VP:
                        cn,ck_=cell_counts[a,b];pc=(dec(ck_)+dec(20)*pm)/dec(cn+20)
                        fit[(M[2],a,b)]=(cn,ck_,pc,pm)
            for (m,a,b),(gn,gk,p,prior) in fit.items():
                r['fitted'].append(dict(fold_id=fid,model_id=m,ma_state=a,volume_price_state=b,training_pool_n=n,training_pool_positive=k,group_n=gn,group_positive=gk,prior_p=float(prior) if prior is not None else None,p=float(p),prior_only=int(gn==0),group_n_lt_20=int(gn<20),latest_training_label_end=latest))
        counts=Counter();val=[d for d in anchors if lo<=d<=hi]
        for d in val:
            x=ls.get(d)
            if x is None:reason='NO_REGISTERED_LABEL'
            elif x['outcome_observation_date']>hi:reason='LABEL_CROSSES_FOLD_END'
            elif x['ma_state'] is None and x['volume_price_state'] is None:reason='MA_AND_VOLUME_MISSING'
            elif x['ma_state'] is None:reason='MA_MISSING'
            elif x['volume_price_state'] is None:reason='VOLUME_MISSING'
            elif not fit:reason='INSUFFICIENT_JOINT_TRAINING'
            else:reason='EVALUATED'
            counts[reason]+=1
            r['ledger'].append(dict(fold_id=fid,role='validation',signal_date=d,label_end=x['outcome_observation_date'] if x else None,reason=reason))
            if reason!='EVALUATED':continue
            a,b=x['ma_state'],x['volume_price_state']
            for key in [(M[0],'ALL','ALL'),(M[1],a,'ALL'),(M[2],a,b)]:
                gn,gk,p,_=fit[key]
                r['predictions'].append(dict(fold_id=fid,model_id=key[0],signal_date=d,entry_observation_date=x['entry_observation_date'],outcome_observation_date=x['outcome_observation_date'],ma_state=a,volume_price_state=b,y=x['y'],zero_change=x['zero_change'],p=float(p),training_pool_n=len(train),model_group_n=gn,model_group_positive=gk,prior_only=int(gn==0),group_n_lt_20=int(gn<20),latest_training_label_end=latest,fixed_every_fifth_anchor=int(d in grid),historical_model_input_approved=0,runtime_usable=0))
        r['folds'].append(dict(fold_id=fid,validation_start=lo,validation_end=hi,train_candidates=len(candidates),train_purged_not_mature=len(candidates)-len(mature),train_mature=len(mature),train_ma_missing=sum(x['ma_state'] is None for x in mature),train_volume_missing=sum(x['volume_price_state'] is None for x in mature),train_joint_missing=len(mature)-len(train),train_used=len(train),latest_training_label_end=latest if fit else None,validation_anchors=len(val),evaluated_dates=counts['EVALUATED'],no_registered_label=counts['NO_REGISTERED_LABEL'],label_crosses_fold_end=counts['LABEL_CROSSES_FOLD_END'],ma_and_volume_missing=counts['MA_AND_VOLUME_MISSING'],ma_only_missing=counts['MA_MISSING'],volume_only_missing=counts['VOLUME_MISSING'],insufficient_training=counts['INSUFFICIENT_JOINT_TRAINING']))
    for fid in [f['id'] for f in CFG['folds']]+['POOLED']:
        for subset in ['all_overlapping','fixed_every_fifth_anchor']:
            bymodel={m:[x for x in r['predictions'] if x['model_id']==m and (fid=='POOLED' or x['fold_id']==fid) and (subset=='all_overlapping' or x['fixed_every_fifth_anchor'])] for m in M}
            ss={m:stats(xs) for m,xs in bymodel.items()}
            for m,s in ss.items():r['metrics'].append(dict(fold_id=fid,subset=subset,model_id=m,**s))
            for a,b in [(M[2],M[1]),(M[2],M[0]),(M[1],M[0])]:
                sa,sb=ss[a],ss[b]
                r['comparisons'].append(dict(fold_id=fid,subset=subset,alternative=a,baseline=b,n=sa['n'],alternative_brier=sa['brier'],baseline_brier=sb['brier'],brier_delta=sa['brier']-sb['brier'] if sa['n'] else None,logloss_delta=sa['log_loss']-sb['log_loss'] if sa['n'] else None,promotion_approved=0))
            if subset!='all_overlapping':continue
            edges=[0,.2,.4,.6,.8,1]
            for m,xs in bymodel.items():
                buckets=[[] for _ in range(5)]
                for x in xs:
                    j=min(int(x['p']*5),4);buckets[j].append(x)
                for j,xs_ in enumerate(buckets):
                    s=stats(xs_)
                    r['calibration'].append(dict(fold_id=fid,model_id=m,bin_low=edges[j],bin_high=edges[j+1],n=s['n'],positive_count=s['positive_count'],zero_count=s['zero_count'],negative_count=s['negative_count'],mean_prediction=s['mean_prediction'],observed_positive_frequency=s['positive_frequency'],observed_minus_prediction=s['positive_frequency']-s['mean_prediction'] if s['n'] else None,empty_bin=int(s['n']==0),sparse_note='empty' if not s['n'] else 'n_lt_20_not_reliability_test' if s['n']<20 else 'n_does_not_certify_calibration',calibration_transform_fitted=0))
    lookup={(x['fold_id'],x['signal_date'],x['model_id']):x for x in r['predictions']}
    for x in r['predictions']:
        if x['model_id']!=M[2]:continue
        for b in [M[1],M[0]]:
            y=lookup[x['fold_id'],x['signal_date'],b];eps=CFG['log_loss_epsilon']
            r['paired_loss'].append(dict(fold_id=x['fold_id'],signal_date=x['signal_date'],baseline=b,alternative=M[2],y=x['y'],alternative_p=x['p'],baseline_p=y['p'],brier_delta=(x['p']-x['y'])**2-(y['p']-y['y'])**2,logloss_delta=math.log(max(eps,y['p'] if y['y'] else 1-y['p']))-math.log(max(eps,x['p'] if x['y'] else 1-x['p'])),fixed_every_fifth_anchor=x['fixed_every_fifth_anchor']))
    return r

def main():
    ck('registered_contract_and_producer_hashes',digest(WORK/'contract.json')==RC['contract_sha256'] and digest(WORK/'run_incremental.py')==RC['producer_code_sha256'],{'contract':digest(WORK/'contract.json'),'producer':digest(WORK/'run_incremental.py')})
    before={p:digest(ROOT/p) for p in RC['protected_source_sha256']}
    ck('all_13_protected_sources_match_registration',before==RC['protected_source_sha256'],before)
    core=['量价增量开发验证.sqlite','预登记研究协议.json','运行与输入合同.json','实现验证结果.json','逐日概率与实际结果_仅开发期.csv','六折训练与覆盖.csv','逐折模型与全部九格.csv','共同训练样本成员.csv','训练与验证弃答台账.csv','概率评分.csv','同日模型对照.csv','固定分箱校准诊断.csv','逐日配对误差差.csv','与上轮覆盖对账.csv','较上轮减少的评分日期.csv']
    stamp=datetime.fromisoformat(RC['registered_at_utc']).timestamp();times={p:(OUT/p).stat().st_mtime for p in core}
    ck('local_receipt_precedes_all_15_core_output_mtimes',all(stamp<=t for t in times.values()),{'registered_at_utc':RC['registered_at_utc'],'minimum_output_delay_seconds':min(times.values())-stamp,'local_receipt_not_external_timestamp_attestation':True})
    log=json.loads((WORK/'cumulative_experiment_registration.json').read_text())
    ck('cumulative_15_variants_no_reset',log['cumulative_variants']==sum(x['variants'] for x in log['entries'])==15 and [x['variants'] for x in log['entries']]==[12,2,1] and log['entries'][-1]['repeated_comparators']==2)
    with connect(ROOT/CFG['input_labels']) as con:
        labels=[dict(x) for x in con.execute("SELECT signal_date,entry_observation_date,outcome_observation_date,outcome_sign,horizon_observed_sessions FROM development_price_outcomes WHERE signal_date>='2023-01-03' AND signal_date<='2024-12-31' ORDER BY signal_date")]
    with connect(ROOT/CFG['input_features']) as con:
        anchors=[x[0] for x in con.execute("SELECT trade_date FROM input_bars WHERE trade_date>='2023-01-03' AND trade_date<='2024-12-31' ORDER BY trade_date")]
        signals=[dict(x) for x in con.execute('SELECT trade_date,'+','.join('"'+n+'"' for n in C)+" FROM signals WHERE trade_date>='2023-01-03' AND trade_date<='2024-12-31' ORDER BY trade_date")]
    ck('frozen_source_counts_and_unique_development_domains',len(labels)==469 and len(anchors)==484 and len(signals)==484 and len({x['signal_date'] for x in labels})==469 and anchors==sorted(set(anchors)) and [x['trade_date'] for x in signals]==anchors and all(x['outcome_observation_date']<'2025-01-01' for x in labels))
    ck('input_label_event_and_domains',all(x['horizon_observed_sessions']==5 and x['outcome_sign'] in ['price_change_gt_0','price_change_eq_0','price_change_lt_0'] and x['signal_date']<x['entry_observation_date']<=x['outcome_observation_date'] for x in labels))
    expected=reconstruct(labels,signals,anchors)
    with connect(ROOT/'outputs/初始化与验证推进_20261026/时间验证/开发期滚动验证.sqlite') as con:
        previous={(x[0],x[1]) for x in con.execute("SELECT fold_id,signal_date FROM predictions WHERE model_id='M0_laplace_constant'")}
    new={(x['fold_id'],x['signal_date']) for x in expected['predictions'] if x['model_id']==M[0]}
    reasons={(x['fold_id'],x['signal_date']):x['reason'] for x in expected['ledger'] if x['role']=='validation'}
    expected['prior_coverage_comparison']=[dict(fold_id=f['id'],old_ma_only_dates=sum(k[0]==f['id'] for k in previous),joint_dates=sum(k[0]==f['id'] for k in new),lost_dates=sum(k[0]==f['id'] for k in previous-new)) for f in CFG['folds']]
    expected['lost_prior_scoring_dates']=[dict(fold_id=fid,signal_date=d,reason=reasons[fid,d]) for fid,d in sorted(previous-new)]
    ck('joint_scoring_mask_subset_and_10_lost_dates',new<=previous and len(previous-new)==10,{'previous_dates':len(previous),'joint_dates':len(new),'lost_dates':len(previous-new)})
    table_results={};cells=0;maxerr=0
    with connect(OUT/'量价增量开发验证.sqlite') as con:
        ck('sqlite_quick_check',con.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        actual={name:readrows(con,name) for name in expected}
        metadata=json.loads(con.execute("SELECT value_json FROM metadata WHERE key='run'").fetchone()[0])
    # Compare all scalar cells, preserving independently created source/fold order.
    for table,reference in expected.items():
        got=actual[table];mismatches=[];err=0;count=0
        if len(got)!=len(reference):mismatches.append(('rows',len(got),len(reference)))
        for i,(a,b) in enumerate(zip(reference,got)):
            if set(a)!=set(b):mismatches.append((i,'columns'))
            for key,value in a.items():
                other=b[key];count+=1
                if isinstance(value,float):
                    if not isinstance(other,(float,int)) or not math.isfinite(other) or abs(value-other)>1e-14:mismatches.append((i,key,value,other))
                    if isinstance(other,(float,int)):err=max(err,abs(value-other))
                elif value!=other:mismatches.append((i,key,value,other))
        table_results[table]={'rows':len(reference),'scalar_cells':count,'max_absolute_float_difference':err,'mismatches':mismatches[:10]};cells+=count;maxerr=max(maxerr,err)
        ck('independent_reconstruction_'+table,not mismatches,table_results[table])
    names={'predictions':'逐日概率与实际结果_仅开发期.csv','folds':'六折训练与覆盖.csv','fitted':'逐折模型与全部九格.csv','membership':'共同训练样本成员.csv','ledger':'训练与验证弃答台账.csv','metrics':'概率评分.csv','comparisons':'同日模型对照.csv','calibration':'固定分箱校准诊断.csv','paired_loss':'逐日配对误差差.csv','prior_coverage_comparison':'与上轮覆盖对账.csv','lost_prior_scoring_dates':'较上轮减少的评分日期.csv'}
    csv_cells=0
    for table,name in names.items():
        with (OUT/name).open(encoding='utf-8-sig',newline='') as f:csvrows=list(csv.DictReader(f))
        assert len(csvrows)==len(actual[table]),name
        for a,b in zip(csvrows,actual[table]):
            assert set(a)==set(b)
            for key,x in b.items():
                csv_cells+=1
                if x is None:assert a[key]=='',(name,key)
                elif isinstance(x,(int,float)):assert float(a[key])==x,(name,key)
                else:assert a[key]==x,(name,key)
    ck('all_11_csv_exports_match_sqlite',True,{'scalar_cells':csv_cells})
    ck('metadata_contract_receipt_and_sources_exact',metadata['contract']==CFG and metadata['registration']==RC and metadata['source_sha256']==before and json.loads((OUT/'预登记研究协议.json').read_text())==CFG and json.loads((OUT/'运行与输入合同.json').read_text())==metadata)
    gates=['outcomes_2025_2026_opened','current_forecast_generated','runtime_usable','model_input_approved']
    ck('all_input_execution_promotion_calibration_gates_closed',all(metadata[k] is False for k in gates) and all(CFG[k] is False for k in ['outcomes_2025_2026_opened','historically_untouched_period_claim','probability_recalibration_fitted','confidence_or_significance_claims','target_is_net_profit','historical_first_availability_certified','historical_daily_st_or_suspension_certified','execution_or_costs_modelled','chip_features_used','current_forecast_generated','model_input_approved','runtime_usable','old_forecast_protocol_or_risk_modified']) and all(x['runtime_usable']==x['historical_model_input_approved']==0 for x in actual['predictions']) and all(x['promotion_approved']==0 for x in actual['comparisons']) and all(x['calibration_transform_fitted']==0 for x in actual['calibration']))
    text=(WORK/'run_incremental.py').read_text();tree=ast.parse(text)
    sqlstrings=[x.value for x in ast.walk(tree) if isinstance(x,ast.Constant) and isinstance(x.value,str) and ('SELECT' in x.value or 'WHERE trade_date BETWEEN' in x.value)]
    ck('static_sql_outcome_reads_limited_to_development',any('FROM development_price_outcomes' in s and "BETWEEN '2023-01-03' AND '2024-12-31'" in s for s in sqlstrings) and 'outcomes_2025_2026_opened=False' in text,{'inspection_scope':'main source query bounds and output rows; raw file hashing is not outcome querying','query_fragments':sqlstrings})
    ck('all_training_members_strictly_mature_and_validation_windows_contained',all(x['label_end']<next(f['validation_start'] for f in CFG['folds'] if f['id']==x['fold_id']) for x in actual['membership']) and all(x['outcome_observation_date']<=next(f['validation_end'] for f in CFG['folds'] if f['id']==x['fold_id']) for x in actual['predictions']))
    p={m:{(x['fold_id'],x['signal_date'],x['y']) for x in actual['predictions'] if x['model_id']==m} for m in M}
    ck('all_three_models_identical_scoring_dates_outcomes',p[M[0]]==p[M[1]]==p[M[2]])
    # No producer result is used above this line; now adversarial calls only.
    spec=importlib.util.spec_from_file_location('producer_for_negative_probes',WORK/'run_incremental.py');prod=importlib.util.module_from_spec(spec);spec.loader.exec_module(prod)
    probes=[]
    def reject(name,fn):
        try:fn()
        except ValueError:probes.append(name)
        else:raise AssertionError('Expected ValueError: '+name)
    syn=[dict(y=1,ma_state='up',volume_price_state='spike_up',outcome_observation_date='2023-01-10') for _ in range(100)]
    ck('probe_99_rows_abstain',prod.fit(syn[:-1],CFG) is None)
    ff=prod.fit(syn,CFG);p0=101/102
    ck('probe_empty_parent_and_cell_use_declared_prior',ff['parents']['down']['n']==0 and abs(ff['parents']['down']['p']-p0)<1e-15 and ff['cells']['up','spike_down']['n']==0 and ff['cells']['up','spike_down']['p']==ff['parents']['up']['p'])
    for a,b in [(1,1),(2,0),(-1,0),(.5,0),(1.0,0),('1',0),(0,'0'),([],0)]:reject('illegal_signal_'+repr((a,b)),lambda a=a,b=b:prod.state(a,b,'up','down'))
    ck('probe_missing_is_not_false',prod.state(None,0,'up','down') is None and prod.state(0,None,'up','down') is None)
    for what in ['label','signals','anchor','anchor_order']:
        ll,ss,aa=deepcopy(labels),deepcopy(signals),anchors[:]
        if what=='label':ll.append(deepcopy(ll[0]))
        if what=='signals':ss.append(deepcopy(ss[0]))
        if what=='anchor':aa.append(aa[-1])
        if what=='anchor_order':aa.reverse()
        reject('duplicate_or_unordered_'+what,lambda ll=ll,ss=ss,aa=aa:prod.evaluate(ll,ss,aa,CFG))
    for key,value in [('horizon_observed_sessions',4),('outcome_sign','unknown'),('outcome_observation_date','2025-01-02'),('entry_observation_date','2022-12-31'),('signal_date','2025-01-02')]:
        bad=deepcopy(labels);bad[0][key]=value;reject('bad_label_'+key,lambda bad=bad:prod.evaluate(bad,signals,anchors,CFG))
    # Every top-level contract field is checked by a semantic mutation, incl nested lists.
    for key,value in CFG.items():
        bad=deepcopy(CFG)
        if isinstance(value,bool):bad[key]=not value
        elif isinstance(value,int):bad[key]=value+1
        elif isinstance(value,float):bad[key]=value+.01
        elif isinstance(value,list):bad[key]=deepcopy(value)+['MUTATED']
        elif isinstance(value,str):bad[key]=value+' MUTATED'
        else:bad[key]=None
        reject('contract_'+key,lambda bad=bad:prod.guard(bad))
    # Poison first validation outcomes, compare production outputs against our independent baseline.
    bad=deepcopy(labels);f=CFG['folds'][0]
    for x in bad:
        if f['validation_start']<=x['signal_date']<=f['validation_end']:x['outcome_sign']='price_change_lt_0' if x['outcome_sign']=='price_change_gt_0' else 'price_change_gt_0'
    poison=prod.evaluate(bad,signals,anchors,CFG)
    def fitkey(x):return (x['model_id'],x['ma_state'],x['volume_price_state'])
    oldfit={fitkey(x):x for x in expected['fitted'] if x['fold_id']==f['id']}
    newfit={fitkey(x):x for x in poison['fitted'] if x['fold_id']==f['id']}
    ck('probe_validation_outcome_poison_does_not_change_first_fold_fit',set(oldfit)==set(newfit) and all(abs(oldfit[k]['p']-newfit[k]['p'])<1e-14 and oldfit[k]['group_n']==newfit[k]['group_n'] for k in oldfit))
    ck('probe_validation_outcome_poison_does_not_change_first_fold_probabilities',all(abs(x['p']-next(y['p'] for y in expected['predictions'] if y['fold_id']==x['fold_id'] and y['model_id']==x['model_id'] and y['signal_date']==x['signal_date']))<1e-14 for x in poison['predictions'] if x['fold_id']==f['id']))
    # Force first fold to 99 complete training cases without changing labels.
    members=[x['signal_date'] for x in expected['membership'] if x['fold_id']==f['id']]
    doomed=set(members[99:]);bad=deepcopy(signals)
    for x in bad:
        if x['trade_date'] in doomed:x[C[2]]=None
    insufficient=prod.evaluate(labels,bad,anchors,CFG)
    ifold=next(x for x in insufficient['folds'] if x['fold_id']==f['id'])
    ck('probe_fold_wide_99_joint_train_abstention',ifold['train_used']==99 and ifold['evaluated_dates']==0 and ifold['insufficient_training']>0 and not any(x['fold_id']==f['id'] for x in insufficient['fitted']) and not any(x['fold_id']==f['id'] for x in insufficient['predictions']))
    # Push one prior complete label endpoint exactly onto first validation start.
    bad=deepcopy(labels);boundary=members[0]
    for x in bad:
        if x['signal_date']==boundary:x['outcome_observation_date']=f['validation_start']
    edge=prod.evaluate(bad,signals,anchors,CFG)
    ck('probe_equal_validation_start_endpoint_is_purged',not any(x['fold_id']==f['id'] and x['signal_date']==boundary for x in edge['membership']) and any(x['fold_id']==f['id'] and x['signal_date']==boundary and x['reason']=='TRAIN_LABEL_NOT_MATURE' for x in edge['ledger']))
    ck('all_adversarial_rejection_probes',True,{'rejected_count':len(probes),'names':probes})
    after={p:digest(ROOT/p) for p in RC['protected_source_sha256']}
    ck('sources_and_producer_unchanged_during_independent_audit',before==after and digest(WORK/'run_incremental.py')==RC['producer_code_sha256'])
    pooled=[x for x in expected['comparisons'] if x['fold_id']=='POOLED']
    result=dict(all_checks_passed=True,passed=len(checks),total=len(checks),audit_method='stdlib independent grouping and 70-digit Decimal shrinkage; no producer expected-data calls; producer imported only after independent table comparisons for adversarial probes',producer_code_sha256=digest(WORK/'run_incremental.py'),contract_sha256=digest(WORK/'contract.json'),source_sha256=after,checks=checks,compared_scalar_cells=cells,max_absolute_float_difference=maxerr,table_comparisons=table_results,source_counts={'labels':len(labels),'anchors':len(anchors)},result_counts={'scoring_dates':len(new),'prediction_rows':len(expected['predictions']),'fitted_cells_and_parents':len(expected['fitted']),'paired_loss_rows':len(expected['paired_loss'])},pooled_comparisons=pooled,limitations=['This is a local independently coded audit, not external preregistration attestation.','2025/2026 outcome isolation is supported by static production SQL bounds, fixed input hashes and output domains; byte hashing entire files is distinguished from outcome querying.','Previously independently checked raw-label derivation is referenced by frozen source DB; this audit does not re-extract 2022 files.','Passing software checks does not establish predictive value, net profits, execution feasibility, or probability calibration.'])
    (HERE/'独立复核.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    lines=['# 量价增量验证独立复核','',f'共 {len(checks)}/{len(checks)} 项通过。以旧版 469 条开发标签及 484 个原始锚点，独立重建共同掩码、六折训练与验证成员、分层概率、评分、校准分箱、覆盖损失。未调用生产拟合或评分函数生成预期值。','',f'核对 {cells:,} 个 SQLite 标量及 {csv_cells:,} 个 CSV 标量；最大浮点差 {maxerr:.3g}。独立概率使用 70 位 Decimal 计算。', '',f'结果为 {len(new)} 个共同评分日期、{len(expected["predictions"])} 行预测、{len(expected["fitted"])} 行完整父层/九格参数。较上轮 308 个评分日期减少 {len(previous-new)} 个。','',f'本地登记先于全部 15 个核心产物；合同和生产代码哈希一致，13 个受保护原件未改变；累计登记变体 15，未重置。所有正式输入、运行、晋级和再校准开关为关闭。','', '## 核心结果','']
    for x in pooled:lines.append(f'- {x["subset"]}: {x["alternative"]} 对 {x["baseline"]}，n={x["n"]}，Brier 差={x["brier_delta"]:.12g}，log loss 差={x["logloss_delta"]:.12g}。')
    lines+=['','正差代表误差更高。本轮开发证据不足以支持新增量价层晋级。','',f'另有 {len(probes)} 个拒绝性负例：逐个顶层合同字段突变、非法/矛盾信号、重复/乱序日期、非法与未来标签；验证标签投毒不改变该折拟合和预测，99 条共同训练样本使整折弃答，训练标签终点等于验证开始时被剔除。','','## 限制','','登记为本地记录，不构成外部时间戳证明。2025/2026 隔离根据生产查询边界、输入哈希和输出范围核实；整文件哈希读取字节不等同于查询未来结果。旧标签原始重建沿用上轮独立核验，此次未重做 2022 原件提取。代码通过不代表模型有收益或预测优势。','','## 指纹','',f'- 生产代码 SHA-256：`{result["producer_code_sha256"]}`',f'- 合同 SHA-256：`{result["contract_sha256"]}`','', '复算：使用 Python 3 执行本目录 `audit.py`。脚本仅在本目录写出本报告与 JSON，不运行生产 main，不改生产或来源文件。']
    (HERE/'独立复核.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'passed':len(checks),'scalar_cells':cells,'csv_cells':csv_cells,'maxerr':maxerr,'scoring_dates':len(new),'probes':len(probes),'outputs':str(HERE)},ensure_ascii=False))
if __name__=='__main__':main()
