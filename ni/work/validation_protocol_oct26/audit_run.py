"""Independent read-only audit. Production prediction/evaluation functions are not used."""
from collections import Counter
from decimal import Decimal
import csv
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = ROOT/'outputs/初始化与验证推进_20261026/时间验证'
BASE = ROOT/'outputs/三线研究启动_20261025/量价基线'


def readjson(p): return json.loads(p.read_text())
def digest(p):
    import hashlib
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''): h.update(part)
    return h.hexdigest()
def query(path, sql):
    con = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql)]
    finally: con.close()
def near(a,b):
    return a is None and b is None or a is not None and b is not None and math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-14)


def main():
    checks = []
    def check(name, passed, details=None): checks.append({'check':name,'passed':bool(passed),'details':details})
    cfg = readjson(ROOT/'work/forecast_validation_oct26/contract.json')
    production_path = ROOT/'work/forecast_validation_oct26/run_validation.py'
    original_code_sha = digest(production_path)
    ref = readjson(WORK/'independent_reference_results.json')
    expected = list(csv.DictReader((WORK/'independent_expected_predictions.csv').open()))
    labels = query(BASE/'开发期结果隔离.sqlite','SELECT * FROM development_price_outcomes ORDER BY signal_date')
    labelmap = {r['signal_date']:r for r in labels}
    signals = query(BASE/'日线特征与信号.sqlite',"SELECT * FROM signals WHERE trade_date BETWEEN '2023-01-03' AND '2024-12-31' ORDER BY trade_date")
    signalmap = {r['trade_date']:r for r in signals}
    anchors = sorted(signalmap)
    grid = set(anchors[::5])
    upkey = 'MA5_gt_MA10_gt_MA15_and_MA15_rising'
    downkey = 'MA5_lt_MA10_lt_MA15_and_MA15_falling'
    def group(day):
        up, down = signalmap[day][upkey], signalmap[day][downkey]
        if up is None or down is None: return None
        assert (up,down) in [(0,0),(1,0),(0,1)]
        return 'up' if up else 'down' if down else 'other'
    run_db = OUT/'开发期滚动验证.sqlite'
    tables = {k:query(run_db,'SELECT * FROM '+k) for k in ['predictions','folds','models','membership','ledger','metrics','comparisons','calibration']}
    actual = {(r['fold_id'],r['signal_date'],r['model_id']):r for r in tables['predictions']}
    mismatches = []
    for r in expected:
        for model,pkey in zip(cfg['models'],['p0','p1']):
            a = actual.get((r['fold'],r['signal_date'],model))
            if a is None or not (a['outcome_observation_date']==r['outcome_end'] and a['feature_group']==r['group'] and a['y']==int(r['y']) and a['zero_price_change']==int(r['zero']) and a['fixed_every_fifth_anchor']==int(r['fixed_grid']) and near(a['p'],r[pkey])):
                mismatches.append([r['fold'],r['signal_date'],model])
    check('all_616_prediction_rows_match_independent_reference',len(actual)==len(tables['predictions'])==616 and not mismatches,{'unique_dates':len(expected),'mismatches':mismatches[:10]})
    check('both_models_identical_dates_no_future_outcomes',len(expected)==308 and all(r['outcome_observation_date']<='2024-12-31' for r in tables['predictions']))
    models={(r['fold_id'],r['group_id']):r for r in tables['models']}
    ok = len(models)==18
    for f in ref['folds']:
        for g,v in f['groups'].items():
            a=models.get((f['fold'],g),{})
            ok &= (a.get('train_n')==f['train_n'] and a.get('train_positive')==f['train_positive'] and a.get('group_n')==v['n'] and a.get('group_positive')==v['positive'] and near(a.get('p0'),f['p0']) and near(a.get('group_p'),v['p']) and a.get('latest_training_signal')==f['train_last_anchor'] and a.get('latest_training_label_end')==f['train_last_label_end'])
    check('all_18_fold_group_models_match_independent_counts_and_formula',ok)
    members_expected=[]; ledger_expected=[]; fold_mismatches=[]
    for f in cfg['folds']:
        fid,start,end=f['id'],f['validation_start'],f['validation_end']
        candidate=[r for r in labels if r['signal_date']<start]
        mature=[r for r in candidate if r['outcome_observation_date']<start]
        train=[r for r in mature if group(r['signal_date']) is not None]
        for r in train: members_expected.append((fid,r['signal_date'],r['outcome_observation_date'],group(r['signal_date']),int(r['outcome_sign']=='price_change_gt_0')))
        for r in candidate:
            if r['outcome_observation_date']>=start:ledger_expected.append((fid,r['signal_date'],r['outcome_observation_date'],'TRAIN_LABEL_NOT_MATURE_BEFORE_VALIDATION_START'))
        counts=Counter()
        for day in [d for d in anchors if start<=d<=end]:
            r=labelmap.get(day)
            status='NO_REGISTERED_MATURE_DEVELOPMENT_LABEL' if r is None else 'VALIDATION_LABEL_END_AFTER_FOLD_END' if r['outcome_observation_date']>end else 'MA_FEATURE_NOT_READY' if group(day) is None else 'INSUFFICIENT_TRAINING_ROWS' if len(train)<100 else 'EVALUATED'
            counts[status]+=1
            ledger_expected.append((fid,day,None if r is None else r['outcome_observation_date'],status))
        a=next(x for x in tables['folds'] if x['fold_id']==fid)
        want={'train_candidate_labels':len(candidate),'train_purged_not_mature':len(candidate)-len(mature),'train_mature_labels':len(mature),'train_feature_missing':len(mature)-len(train),'train_used':len(train),'latest_training_label_end':max(r['outcome_observation_date'] for r in train),'validation_anchors':sum(counts.values()),'evaluated_dates':counts['EVALUATED'],'no_registered_label':counts['NO_REGISTERED_MATURE_DEVELOPMENT_LABEL'],'label_crosses_fold_end':counts['VALIDATION_LABEL_END_AFTER_FOLD_END'],'feature_not_ready':counts['MA_FEATURE_NOT_READY'],'insufficient_training':counts['INSUFFICIENT_TRAINING_ROWS']}
        for k,v in want.items():
            if a[k]!=v:fold_mismatches.append([fid,k,a[k],v])
        if not near(a['coverage'],counts['EVALUATED']/sum(counts.values())):fold_mismatches.append([fid,'coverage'])
    members_actual=[(r['fold_id'],r['signal_date'],r['label_end'],r['feature_group'],r['y']) for r in tables['membership']]
    ledger_actual=[(r['fold_id'],r['signal_date'],r['label_end'],r['reason']) for r in tables['ledger']]
    check('all_training_member_rows_match_and_mature_before_fold',Counter(members_expected)==Counter(members_actual),{'training_member_rows':len(members_actual)})
    check('all_fold_coverage_and_purge_rows_match',not fold_mismatches and Counter(ledger_expected)==Counter(ledger_actual),{'ledger_rows':len(ledger_actual),'fold_mismatches':fold_mismatches,'validation_reason_counts':dict(Counter(r['reason'] for r in tables['ledger'] if not r['reason'].startswith('TRAIN_')))})
    score_mismatches=[]; score_expect={}
    for f in [x['id'] for x in cfg['folds']]+['POOLED']:
        for subset in ['all_overlapping','fixed_every_fifth_anchor']:
            cases=[r for r in expected if (f=='POOLED' or r['fold']==f) and (subset=='all_overlapping' or int(r['fixed_grid']))]
            for model,pkey in zip(cfg['models'],['p0','p1']):
                ps=[float(r[pkey]) for r in cases];ys=[int(r['y']) for r in cases]
                n=len(cases)
                want={'n':n,'positive_count':sum(ys),'zero_price_change_count':sum(int(r['zero']) for r in cases),'positive_frequency':sum(ys)/n,'mean_prediction':math.fsum(ps)/n,'brier':math.fsum((p-y)**2 for p,y in zip(ps,ys))/n,'log_loss':-math.fsum(y*math.log(p)+(1-y)*math.log1p(-p) for p,y in zip(ps,ys))/n}
                a=next(x for x in tables['metrics'] if (x['fold_id'],x['subset'],x['model_id'])==(f,subset,model))
                for k,v in want.items():
                    if not near(a[k],v):score_mismatches.append([f,subset,model,k])
                score_expect[f,subset,model]=want
    check('all_28_metric_rows_independently_recomputed',len(tables['metrics'])==28 and not score_mismatches,{'mismatches':score_mismatches})
    comp_bad=[]
    for a in tables['comparisons']:
        m0,m1=[score_expect[a['fold_id'],a['subset'],model] for model in cfg['models']]
        if not (near(a['brier_delta_M1_minus_M0'],m1['brier']-m0['brier']) and near(a['brier_skill_M1_vs_M0'],1-m1['brier']/m0['brier']) and near(a['logloss_delta_M1_minus_M0'],m1['log_loss']-m0['log_loss']) and a['performance_release_approved']==0):comp_bad.append(a)
    check('all_14_baseline_comparisons_match',len(tables['comparisons'])==14 and not comp_bad)
    cal_bad=[]; sparse=[]
    for a in tables['calibration']:
        pkey='p0' if a['model_id']==cfg['models'][0] else 'p1'
        candidates=[r for r in expected if a['fold_id']=='POOLED' or r['fold']==a['fold_id']]
        cases=[r for r in candidates if min(4,int(float(r[pkey])*5))==int(round(a['bin_low']*5))]
        n=len(cases);mean=math.fsum(float(r[pkey]) for r in cases)/n if n else None;freq=sum(int(r['y']) for r in cases)/n if n else None
        positives=sum(int(r['y']) for r in cases);zeros=sum(int(r['zero']) for r in cases)
        note='empty' if n==0 else 'fewer_than_20_not_a_reliability_test' if n<20 else 'count_does_not_certify_calibration'
        if not (a['n']==n and a['positive_count']==positives and a['zero_price_change_count']==zeros and a['negative_count']==n-positives-zeros and near(a['mean_prediction'],mean) and near(a['observed_positive_frequency'],freq) and near(a['observed_minus_predicted'],None if n==0 else freq-mean) and a['empty_bin']==int(n==0) and a['sparse_display_note']==note and a['calibration_transform_fitted']==0):cal_bad.append(a)
        if 0<n<20:sparse.append({'fold_id':a['fold_id'],'model_id':a['model_id'],'bin_low':a['bin_low'],'bin_high':a['bin_high'],'n':n})
    check('all_70_calibration_rows_match_fixed_five_bins',len(tables['calibration'])==70 and not cal_bad,{'sparse_nonempty_bins':sparse})
    files={'predictions':'滚动验证概率与结果_仅开发期.csv','folds':'时间分折与覆盖.csv','models':'每折训练模型.csv','membership':'训练样本成员.csv','ledger':'剔除与弃答台账.csv','metrics':'概率评分.csv','comparisons':'与常数基准对照.csv','calibration':'固定分箱校准诊断.csv'}
    csv_bad=[]
    for table,filename in files.items():
        data=list(csv.DictReader((OUT/filename).open(encoding='utf-8-sig')))
        if len(data)!=len(tables[table]):csv_bad.append([filename,'length']);continue
        for i,(a,b) in enumerate(zip(data,tables[table])):
            for k,v in b.items():
                if v is None:ok=a[k]==''
                elif isinstance(v,(int,float)):ok=near(a[k],v)
                else:ok=a[k]==str(v)
                if not ok:csv_bad.append([filename,i,k])
    check('all_eight_delivered_csvs_equal_sqlite_tables',not csv_bad,{'mismatches':csv_bad[:10]})
    raw=query(ROOT/'outputs/统一数据底座_20261022/统一数据底座.sqlite',"SELECT trade_date,open,close FROM stock_raw_reference WHERE trade_date <= '2024-12-31' ORDER BY trade_date")
    indices={r['trade_date']:i for i,r in enumerate(raw)}
    exdates={r['ex_date'] for r in query(ROOT/'outputs/统一数据底座_20261022/统一数据底座.sqlite','SELECT ex_date FROM corporate_actions')}
    label_bad=[]
    for r in labels:
        i=indices[r['signal_date']];entry,end=raw[i+1],raw[i+5]
        change=Decimal(str(end['close']))/Decimal(str(entry['open']))-1
        sign='price_change_gt_0' if change>0 else 'price_change_lt_0' if change<0 else 'price_change_eq_0'
        if not (r['entry_observation_date']==entry['trade_date'] and r['outcome_observation_date']==end['trade_date'] and r['outcome_sign']==sign and not any(entry['trade_date']<=d<=end['trade_date'] for d in exdates)):label_bad.append(r['signal_date'])
    check('all_469_source_labels_match_raw_next_open_fifth_close_sign_and_exdate_bounds',not label_bad,{'mismatches':label_bad})
    feats=query(BASE/'日线特征与信号.sqlite',"SELECT trade_date,segment_start,segment_bars,macd_dif,kdj_k,ma5,ma10,ma15,model_input_approved,runtime_usable FROM features ORDER BY trade_date")
    exrows=[r for r in feats if r['trade_date'] in exdates]
    check('source_artifact_keeps_three_resets_130_30_warmup_and_closed_gates',len(exrows)==3 and all(r['segment_bars']==1 and all(r[k] is None for k in ['macd_dif','kdj_k','ma5','ma10','ma15']) for r in exrows) and all(r['macd_dif'] is None for r in feats if r['segment_bars']<130) and all(r['kdj_k'] is None for r in feats if r['segment_bars']<30) and all(r['model_input_approved']==r['runtime_usable']==0 for r in feats))
    metadata=readjson(OUT/'运行与输入合同.json');validation=readjson(OUT/'验证结果.json')
    check('all_seven_protected_hashes_match_both_manifest_and_current_files',len(metadata['source_sha256'])==7 and metadata['source_sha256']==validation['source_sha256_before']==validation['source_sha256_after'] and all(digest(ROOT/p)==h for p,h in metadata['source_sha256'].items()))
    check('independent_reference_and_producer_used_same_contract_and_two_sources',ref['contract_sha256']==metadata['contract_sha256']==digest(ROOT/'work/forecast_validation_oct26/contract.json') and all(metadata['source_sha256'][p]==h for p,h in ref['source_hashes'].items()))
    old_protocol=readjson(ROOT/'outputs/首版预测协议草案_20261016.json')
    check('old_protocol_pending_fields_still_null_and_no_runtime_forecast',old_protocol['status']=='draft_not_frozen' and all(v is None for v in old_protocol['pending_freeze'].values()) and not metadata['current_forecast_generated'] and not metadata['outcomes_2025_2026_opened'] and not metadata['runtime_usable'] and not metadata['model_input_approved'])
    # Import is used only to probe the parameter guard, never to generate expected results.
    spec=importlib.util.spec_from_file_location('readonly_producer_guard',production_path)
    producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
    old=readjson(ROOT/'work/baseline_oct25/engineering_contract.json')
    probes=[]
    for section,key,value in [('macd','fast',11),('macd','slow',27),('macd','signal',8),('macd','ema_seed','zero'),('macd','adjust',True),('macd','histogram_multiplier',1),('macd','minimum_segment_bars',26),('kdj','window',7),('kdj','k_alpha','1/2'),('kdj','d_alpha','1/2'),('kdj','seed_k',0),('kdj','seed_d',0),('kdj','flat_range_rsv',0),('kdj','minimum_segment_bars',9),('kdj','j_clipped',True),('volume','ratios',[10,20]),('volume','denominator','including_current'),('volume','spike_threshold',2),('volume','unit','shares')]:
        c=deepcopy(old);c[section][key]=value
        try:producer.guard_old_contract(c);rejected=False
        except ValueError:rejected=True
        probes.append({'field':section+'.'+key,'rejected':rejected})
    for key,value in [('calculation_start','2022-01-01'),('development_start','2022-01-01'),('development_end','2025-12-31'),('horizon_observed_sessions',10),('ma_windows',[3,5,10]),('registered_signals',list(reversed(old['registered_signals']))),('source_database','other.sqlite'),('source_view','other_view')]:
        c=deepcopy(old);c[key]=value
        try:producer.guard_old_contract(c);rejected=False
        except ValueError:rejected=True
        probes.append({'field':key,'rejected':rejected})
    check('27_independent_formula_and_core_numeric_contract_mutations_rejected',len(probes)==27 and all(r['rejected'] for r in probes),probes)
    semantic=[]
    for key in ['price_change_definition','price_handling','label_exclusion']:
        c=deepcopy(old);c[key]='deliberately changed semantic statement'
        try:producer.guard_old_contract(c);rejected=False
        except ValueError:rejected=True
        semantic.append({'field':key,'rejected':rejected})
    old_review=readjson(ROOT/'work/baseline_oct25/audit_independent_review.json')
    producer_text=production_path.read_text()
    check('old_complete_contract_hash_locked_to_prior_independent_audit',old_review['contract_sha256']==digest(ROOT/'work/baseline_oct25/engineering_contract.json') and "previous_review['contract_sha256']==sha(OLD_CONTRACT)" in producer_text,{'semantic_strings_not_rejected_by_subguard_are_protected_by_full_hash':semantic})
    run_probes=[]
    for key,value in [('development_start','2022-01-01'),('development_end','2025-12-31'),('horizon_observed_sessions',10),('models',['M0_only']),('shrinkage_lambda',30),('minimum_training_rows',50),('event','net_profit'),('input_features','other.sqlite'),('input_labels','other.sqlite'),('runtime_usable',True),('model_input_approved',True),('current_forecast_generated',True),('calibration_bin_edges',[0,.5,1]),('log_loss_epsilon',1e-6)]:
        c=deepcopy(cfg);c[key]=value
        try:producer.guard_run_contract(c);rejected=False
        except ValueError:rejected=True
        run_probes.append({'field':key,'rejected':rejected})
    check('14_independent_run_target_source_release_score_mutations_rejected',len(run_probes)==14 and all(r['rejected'] for r in run_probes),run_probes)
    uniqueness_cases=[
        ('duplicate_label_dates',labels+[dict(labels[0])],signals,anchors,'Duplicate label dates'),
        ('duplicate_signal_dates',labels,signals+[dict(signals[0])],anchors,'Duplicate signal dates'),
        ('duplicate_anchor_dates',labels,signals,anchors+[anchors[-1]],'Duplicate or unordered anchor dates'),
        ('unordered_anchor_dates',labels,signals,list(reversed(anchors)),'Duplicate or unordered anchor dates')]
    uniqueness_probes=[]
    for name,probe_labels,probe_signals,probe_anchors,message in uniqueness_cases:
        try:
            producer.evaluate(probe_labels,probe_signals,probe_anchors,cfg)
            rejected=False;actual_message=None
        except ValueError as error:
            actual_message=str(error);rejected=actual_message==message
        uniqueness_probes.append({'case':name,'rejected_before_fit':rejected,'message':actual_message})
    check('four_independent_duplicate_and_unordered_date_cases_rejected_before_fit',all(r['rejected_before_fit'] for r in uniqueness_probes),uniqueness_probes)
    check('final_producer_24_builtin_checks_pass',validation['all_checks_passed'] and validation['passed']==validation['total']==24 and all(r['passed'] for r in validation['checks']))
    check('producer_code_unchanged_during_audit',digest(production_path)==original_code_sha)
    report={'audit_id':'002414_oct26_independent_protocol_and_producer_audit_v1','method':'Read-only independent date masks, all predictions, group arithmetic and probability metrics; Production evaluate/fit/scores not used for expected results. Guards and evaluate imported only for contract mutations and invalid-date rejection before fit.','all_checks_passed':all(r['passed'] for r in checks),'passed':sum(r['passed'] for r in checks),'total':len(checks),'checks':checks,'blocking_findings':[],'resolved_review_items':[{'id':'sparse_calibration_display','finding':'Final production table includes sparse flags, positive/zero/negative counts and observed-minus-predicted. All 70 rows match independent reconstruction.','sparse_rows':sparse},{'id':'legacy_semantic_guard_scope','finding':'Final entrypoint locks full old contract hash to prior independent review, covering semantic text outside the numeric subguard; current hash verified.'},{'id':'unknown_label_definition','finding':'Final evaluate rejects unknown outcome_sign and non-h5 labels before fit; built-in negative tests pass and all actual source rows were independently reconstructed.'}],'advisories':[],'research_conclusion':'M1 development Brier and log-loss are slightly higher than M0. Keep the registered result; no lambda optimization, group reselection, confidence claim or current forecast follows.','source_uniqueness_review_resolved':{'status':'resolved','independent_cases':uniqueness_probes,'finding':'Final evaluate rejects duplicate label dates, duplicate signal dates, duplicate anchor dates and unordered anchors before any fit.'},'source_outcome_period':'2023-2024 only','source_feature_boundary_rows_inspected':'All feature reset/warmup/gate rows including the known 2026 reset; no 2025/2026 outcomes read or generated.','producer_code_sha256':original_code_sha,'contract_sha256':digest(ROOT/'work/forecast_validation_oct26/contract.json')}
    (WORK/'独立复核.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    md=f'''# 2026年10月26日时间验证独立复核

结论：{report['passed']}/{report['total']}项检查通过，all_checks_passed={str(report['all_checks_passed']).lower()}。本次固定输入和已交付产物未发现阻塞问题；结论限于此前已探索的2023—2024开发诊断。

独立逐行比对616条模型预测（308个共同日期）、18条训练分组参数、所有训练成员、6折coverage、训练purge/验证弃答台账、28条评分、14条基准差及70条固定分箱记录。8个CSV与SQLite一致。固定每5锚点网格为61个日期，未选相位。还由原始OHLC独立重建469条标签的日期、方向与已知除权边界；核对三个价格段重置、MACD130/KDJ30缺值及全部正式gates关闭。7个保护文件当前哈希与运行前后记录相同；旧草案仍待冻结。

独立汇总：M0 Brier={ref['metrics'][0]['brier']:.12f}，log-loss={ref['metrics'][0]['log_loss']:.12f}；M1 Brier={ref['metrics'][1]['brier']:.12f}，log-loss={ref['metrics'][1]['log_loss']:.12f}。M1误差略高，应保留此结果；不因此调lambda或重选分组，不代表概率已经校准、独立验证有效或能获利。

本次审查只读生产代码与产物；独立预期结果不调用生产fit/evaluate/scores。仅为参数guard负例和无效日期入口拒绝负例导入生产模块；无效日期在任何拟合前立即抛出ValueError，未运行main或写生产目录。

已解决的审查点：

- 两条非空校准记录只有17条观察（F2及汇总的M1 [.2,.4)区间）；最终表已有稀疏标志、正/零/负计数及观察频率减平均p，70条分箱记录均独立复算一致。
- 独立27个旧数值/公式/初始化/数据范围改动和14个新目标/来源/release/评分参数改动均被guard拒绝。旧合同完整hash现已与原独立审计绑定，覆盖数值子guard之外的price_change_definition、price_handling、label_exclusion等语义字段。
- 未知outcome_sign和非h5标签现在先于训练被拒绝；当前469条源标签的方向及日期已独立重建。

唯一性建议已解决：最终evaluate在拟合前明确拒绝重复标签、重复信号、重复锚点和锚点乱序。本审计分别构造4个负例，均命中对应ValueError；生产内置24/24项检查也全部通过。独立逐行/日期掩码核对覆盖全部六折。没有未解决的审查建议。

F1实际用于两个模型的末训练锚点为2023-06-12、末标签为06-19；纯价格池在特征掩码前可到06-21/06-30，不能混写。2025/2026结果未读；2026的特征reset行被检查，不属于结果或效果检查。旧风险和实盘授权口径不变。
'''
    (WORK/'独立复核.md').write_text(md)
    print(json.dumps({'all_checks_passed':report['all_checks_passed'],'passed':report['passed'],'total':report['total'],'blocking_findings':report['blocking_findings']},ensure_ascii=False))
    if not report['all_checks_passed']:
        print(json.dumps([r for r in checks if not r['passed']],ensure_ascii=False,indent=2))
        raise SystemExit(1)


if __name__=='__main__':main()
