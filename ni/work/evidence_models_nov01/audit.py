"""Inventory saved model evidence only. No fitting, rescoring, or target DB reads."""
from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime, timezone
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sources={}
checks=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source(relative):
    p=ROOT/relative
    sources[relative]=sha(p)
    return p
def j(relative):return json.loads(source(relative).read_text())
def rows(relative):
    with source(relative).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def ck(name,value,details=None):
    checks.append(dict(check=name,passed=bool(value),details=details))
    assert value,name
def main():
    runs={
      'M1_round':dict(base='outputs/初始化与验证推进_20261026/时间验证',contract='work/forecast_validation_oct26/contract.json',receipt='work/forecast_validation_oct26/registration_receipt.json',pred='滚动验证概率与结果_仅开发期.csv',comparison='与常数基准对照.csv',folds='时间分折与覆盖.csv',fitted='每折训练模型.csv',members='训练样本成员.csv',ledger='剔除与弃答台账.csv',calibration='固定分箱校准诊断.csv',models=['M0_laplace_constant','M1_ma_group_shrinkage'],dates=308,grid=61,predictions=616),
      'M2_round':dict(base='outputs/量价增量验证_20261026',contract='work/incremental_validation_oct26/contract.json',receipt='work/incremental_validation_oct26/registration_receipt.json',pred='逐日概率与实际结果_仅开发期.csv',comparison='同日模型对照.csv',folds='六折训练与覆盖.csv',fitted='逐折模型与全部九格.csv',members='共同训练样本成员.csv',ledger='训练与验证弃答台账.csv',calibration='固定分箱校准诊断.csv',models=['M0_laplace_constant','M1_ma_group_shrinkage','M2_ma_volume_hierarchical'],dates=298,grid=59,predictions=894),
      'M3_round':dict(base='outputs/市场环境候选验证_20261031',contract='work/market_model_oct31/contract.json',receipt='work/market_model_oct31/registration_receipt.json',pred='逐日概率与实际结果_仅开发期.csv',comparison='同日模型对照.csv',folds='六折训练与覆盖.csv',fitted='每折模型与两组参数.csv',members='共同训练成员.csv',ledger='训练与验证弃答台账.csv',calibration='固定分箱校准诊断.csv',models=['M0_laplace_constant','M3_shenzhen_ma20_group_shrinkage'],dates=331,grid=66,predictions=662)
    }
    result={};date_sets={}
    for name,run in runs.items():
        base=run['base'];cfg=j(run['contract']);receipt=j(run['receipt'])
        ck(name+'_contract_matches_saved_receipt',receipt['contract_sha256']==sources[run['contract']])
        ck(name+'_development_only_and_same_target',cfg['development_start']=='2023-01-03' and cfg['development_end']=='2024-12-31' and cfg['horizon_observed_sessions']==5 and not cfg['target_is_net_profit'])
        ck(name+'_formal_gates_remain_false',not cfg['historical_first_availability_certified'] and not cfg['historical_daily_st_or_suspension_certified'] and not cfg['execution_or_costs_modelled'] and not cfg['current_forecast_generated'] and not cfg['model_input_approved'] and not cfg['runtime_usable'])
        data={key:rows(base+'/'+run[key]) for key in ['pred','comparison','folds','fitted','members','ledger','calibration']}
        metrics=rows(base+'/概率评分.csv');pred=data['pred'];folds=data['folds'];comparisons=data['comparison']
        dates=sorted({r['signal_date'] for r in pred});date_sets[name]=set(dates)
        ck(name+'_saved_prediction_count',len(pred)==run['predictions'] and len(dates)==run['dates'])
        bydate=Counter(r['signal_date'] for r in pred)
        ck(name+'_one_prediction_per_model_per_shared_date',set(bydate.values())=={len(run['models'])} and len({(r['signal_date'],r['model_id']) for r in pred})==len(pred) and set(r['model_id'] for r in pred)==set(run['models']))
        ck(name+'_same_saved_target_for_all_models',all(len({r['y'] for r in pred if r['signal_date']==date})==1 for date in dates))
        grid=sorted({r['signal_date'] for r in pred if r['fixed_every_fifth_anchor']=='1'})
        ck(name+'_saved_grid_count',len(grid)==run['grid'])
        foldids={f['id'] for f in cfg['folds']};expected={(fold,subset,model) for fold in list(foldids)+['POOLED'] for subset in ['all_overlapping','fixed_every_fifth_anchor'] for model in run['models']}
        ck(name+'_complete_all_fold_subset_model_scores',len(metrics)==len(expected) and {(r['fold_id'],r['subset'],r['model_id']) for r in metrics}==expected)
        ck(name+'_metrics_counts_match_saved_date_membership',all(int(r['n'])==sum(p['model_id']==r['model_id'] and (r['fold_id']=='POOLED' or p['fold_id']==r['fold_id']) and (r['subset']=='all_overlapping' or p['fixed_every_fifth_anchor']=='1') for p in pred) for r in metrics))
        foldmap={r['fold_id']:r for r in folds}
        ck(name+'_actual_temporal_boundaries',all(p['latest_training_label_end']<foldmap[p['fold_id']]['validation_start']<=p['signal_date']<p['entry_observation_date']<=p['outcome_observation_date']<=foldmap[p['fold_id']]['validation_end'] for p in pred))
        ck(name+'_no_saved_later_target_or_runtime_permission',all(p['outcome_observation_date']<='2024-12-31' and p['runtime_usable']=='0' and p.get('historical_model_input_approved',p.get('model_input_approved'))=='0' for p in pred))
        if name=='M1_round':
            coverage_keys=['no_registered_label','label_crosses_fold_end','feature_not_ready','insufficient_training']
        elif name=='M2_round':
            coverage_keys=['no_registered_label','label_crosses_fold_end','ma_and_volume_missing','ma_only_missing','volume_only_missing','insufficient_training']
        else:coverage_keys=['no_registered_label','label_crosses_fold_end','feature_not_ready','insufficient_training']
        ck(name+'_366_validation_anchors_and_all_exclusions_reconcile',sum(int(r['validation_anchors']) for r in folds)==366 and all(int(r['validation_anchors'])==int(r['evaluated_dates'])+sum(int(r[k]) for k in coverage_keys) for r in folds))
        ck(name+'_five_unmatured_labels_purged_in_all_six_folds',all(int(r.get('train_purged_not_mature',r.get('training_not_mature','-1')))==5 for r in folds))
        result[name]=dict(contract=cfg,receipt=receipt,models=run['models'],scoring_dates=dates,fixed_grid_dates=grid,metrics=metrics,comparisons=comparisons,folds=folds,fitted_rows=data['fitted'],training_membership_file=base+'/'+run['members'],training_membership_rows=len(data['members']),exclusion_ledger_file=base+'/'+run['ledger'],exclusion_ledger_rows=len(data['ledger']),calibration_rows=data['calibration'],row_counts={key:len(value) for key,value in data.items()},coverage_reason_totals={k:sum(int(r[k]) for r in folds) for k in coverage_keys},notes=[])
    ck('all_98_saved_metric_rows_preserved',sum(len(v['metrics']) for v in result.values())==98)
    ck('all_70_saved_comparison_rows_preserved',sum(len(v['comparisons']) for v in result.values())==70)
    ck('all_18_coverage_fold_rows_preserved',sum(len(v['folds']) for v in result.values())==18)
    coverage=rows(runs['M2_round']['base']+'/与上轮覆盖对账.csv')
    lost=rows(runs['M2_round']['base']+'/较上轮减少的评分日期.csv')
    ck('M2_dates_subset_M1_and_exact_10_volume_loss',date_sets['M2_round']<date_sets['M1_round'] and len(lost)==10 and {r['signal_date'] for r in lost}==date_sets['M1_round']-date_sets['M2_round'] and all(r['reason']=='VOLUME_MISSING' for r in lost) and sum(int(r['lost_dates']) for r in coverage)==10)
    ck('M1_and_M2_sample_dates_subsets_of_M3_only_not_score_ranking',date_sets['M1_round']<date_sets['M3_round'] and date_sets['M2_round']<date_sets['M3_round'])
    allc=result['M1_round']['comparisons']
    ck('M1_pooled_and_grid_negative_result_retained',all(float(r['brier_delta_M1_minus_M0'])>0 and float(r['logloss_delta_M1_minus_M0'])>0 for r in allc if r['fold_id']=='POOLED'))
    allc=result['M2_round']['comparisons']
    ck('M2_pooled_and_grid_negative_against_matched_M1_and_M0_retained',all(float(r['brier_delta'])>0 and float(r['logloss_delta'])>0 and r['promotion_approved']=='0' for r in allc if r['fold_id']=='POOLED'))
    allc=result['M3_round']['comparisons']
    ck('M3_pooled_and_grid_negative_result_retained',all(float(r['brier_delta_M3_minus_M0'])>0 and float(r['logloss_delta_M3_minus_M0'])>0 and r['promotion_approved']=='0' for r in allc if r['fold_id']=='POOLED'))
    registry=j('outputs/市场环境候选验证_20261031/累计研究与本轮结论台账.json')
    baseline=j('work/baseline_oct25/engineering_contract.json')
    ck('cumulative_12_plus_2_plus_1_plus_1_equals_16',baseline['registered_variant_count']==12 and len(result['M1_round']['models'])==2 and registry['previous_registered_variants']==15 and registry['new_registered_model_variants']==1 and registry['cumulative_registered_variants']==16 and not registry['other_prepared_features_scored'])
    old_featureprep=j('outputs/市场环境输入准备_20261031/本轮状态与续作断点.json')
    ck('15_prepared_features_not_15_scored_trials',old_featureprep['prepared_candidate_feature_definitions']==15 and old_featureprep['new_scored_or_model_variants']==0)
    audit_files=[
      'outputs/初始化与验证推进_20261026/时间验证/验证结果.json','outputs/初始化与验证推进_20261026/时间验证/独立来源复核.json','outputs/初始化与验证推进_20261026/时间验证/重跑产物核验.json',
      'outputs/量价增量验证_20261026/实现验证结果.json','outputs/量价增量验证_20261026/独立模型复核.json','outputs/量价增量验证_20261026/独立量价特征核查.json','outputs/量价增量验证_20261026/完整重跑核验.json','outputs/量价增量验证_20261026/本轮交付核验.json',
      'outputs/市场环境候选验证_20261031/实现验证结果.json','outputs/市场环境候选验证_20261031/选定市场输入独立核查.json','outputs/市场环境候选验证_20261031/独立复核.json','outputs/市场环境候选验证_20261031/筛选身份与完整性严格复核.json','outputs/市场环境候选验证_20261031/本轮交付核验.json']
    audits={p:j(p) for p in audit_files}
    ck('all_saved_audit_counts_complete',all(a['passed']==a['total'] and a.get('all_checks_passed',True) for a in audits.values() if 'total' in a))
    ck('all_saved_deterministic_rerun_records_passed',all(a['all_core_files_byte_identical'] for a in audits.values() if 'all_core_files_byte_identical' in a))
    strict=audits['outputs/市场环境候选验证_20261031/筛选身份与完整性严格复核.json']
    saved_screen=j('outputs/市场环境候选验证_20261031/描述性开发筛选.json')
    guard_file='work/market_model_oct31/strict_screen_review.py';source(guard_file)
    ck('M3_strict_publication_guard_final_hash_and_all_four_failed',strict['strict_guard_sha256']==sources[guard_file] and strict['strict_result']==saved_screen and strict['matches_frozen_producer_result'] and not strict['producer_or_contract_modified'] and not saved_screen['passed'] and not any(saved_screen['conditions'].values()))
    m2cells=[r for r in result['M2_round']['fitted_rows'] if r['model_id']=='M2_ma_volume_hierarchical']
    ck('M2_sparsity_54_cells_37_lt20_3_empty',len(m2cells)==54 and sum(int(r['group_n'])<20 for r in m2cells)==37 and sum(int(r['group_n'])==0 for r in m2cells)==3)
    ck('all_inspected_old_sources_unchanged',all(sha(ROOT/p)==v for p,v in sources.items()))
    limitations=[
      'All model results are previously explored 2023–2024 development diagnostics, not untouched tests or current forecasts.',
      'Five observed sessions and strict positive original-price direction are engineering choices, not user-confirmed final holding period, net-profit or action labels.',
      'Overlapping dates, fixed every-fifth subsets and six expanding folds are not independent-trial or significance certificates.',
      'Cross-round dates and training pools differ; only within-run matched comparisons are valid evidence of incremental scoring.',
      'M3 is a grouping against M0, not an additional conditional feature on M1/M2.',
      'Full saved bins are calibration diagnostics only; no recalibration was fitted.',
      'M3 frozen producer standalone screen had fold-identity validation boundary; actual six folds were complete and mandatory separately audited strict publication guard resolves publication checks without modifying model/contract.',
      'Technical checks and deterministic reproduction show implementation correspondence, not profitable or calibrated use.',
      'Historical first availability, daily official trading states and real fees/fills are not certified; all formal and runtime permissions remain false.',
      'No outcomes for 2025/2026 read or generated in this audit; only saved bounded development CSV outputs and metadata were inspected.'
    ]
    payload=dict(audit_id='saved_model_evidence_inventory_20261101',all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_sha256=sources,created_at_utc=datetime.now(timezone.utc).isoformat(),new_models_fitted=0,new_scores_calculated=0,later_targets_read=False,unique_counting=dict(descriptive_signals=12,unique_models=['M0_laplace_constant','M1_ma_group_shrinkage','M2_ma_volume_hierarchical','M3_shenzhen_ma20_group_shrinkage'],cumulative_variants=16,repeated_comparators_not_new=True),runs=result,coverage_reconciliation_M1_to_M2=coverage,lost_M2_dates=lost,prepared_feature_definitions_not_scored_trials=15,prior_audit_records=audits,limitations=limitations)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'独立审查.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    lines=['# 已保存三轮模型研究证据独立审查','',f'2026-11-01。{len(checks)}/{len(checks)}项核对通过；只读取已保存开发期产物和协议，不运行生产器、不重新计算评分、不读取后期目标。','', '累计账法为12个描述性信号+M0/M1首次两模型+M2一个新增+M3一个新增=16。重复对照、六折、分箱、九格、网格子集和15个预备特征不计独立新增模型。','', '|轮次|日期|概率记录|固定网格|基准|候选|Brier基准|Brier候选|候选−基准|','|---|---:|---:|---:|---|---|---:|---:|---:|']
    for name,alt,base in [('M1_round','M1_ma_group_shrinkage','M0_laplace_constant'),('M2_round','M2_ma_volume_hierarchical','M1_ma_group_shrinkage'),('M3_round','M3_shenzhen_ma20_group_shrinkage','M0_laplace_constant')]:
        x=result[name];m={r['model_id']:r for r in x['metrics'] if r['fold_id']=='POOLED' and r['subset']=='all_overlapping'}
        delta=next((r.get('brier_delta',r.get('brier_delta_M1_minus_M0',r.get('brier_delta_M3_minus_M0'))) for r in x['comparisons'] if r['fold_id']=='POOLED' and r['subset']=='all_overlapping' and (name!='M2_round' or r['baseline']==base and r['alternative']==alt)),None)
        lines.append(f"|{name}|{len(x['scoring_dates'])}|{x['row_counts']['pred']}|{len(x['fixed_grid_dates'])}|{base}|{alt}|{float(m[base]['brier']):.9f}|{float(m[alt]['brier']):.9f}|{float(delta):+.9f}|")
    lines += ['', '三轮主对照以及固定网格的Brier和对数损失均较差；M2对匹配M0也较差。全部98行指标、70行配对对照、18行覆盖、全组参数和校准箱已按原顺序存JSON，没有按最优季度挑选。', '', '共同验证锚点为366：M1排除10无标签+25跨折+23均线缺失，剩308；M2排除10+25+33联合缺失，剩298；M3排除10+25，剩331。M2较M1少10日，2023年7月与2024年6月各5日，来自除权后量能额外预热；具体日期保留。每折训练均剔5个尚未成熟标签，训练特征缺失仍另计。', '', 'M2共54个折×九格，37个格n<20，3个空格；稀疏标记不是统计置信或升级门槛。', '', 'M3筛选身份边界由额外严格发布门补足，实际完整结果不变。详见原审计，不声称冻结生产器的单独辅助函数已经改写。', '', '## 全部既有评分（各轮固定顺序；非跨轮排名）','']
    for name,x in result.items():
        lines += [f'### {name}', '', '|折/子集|模型|n|Brier|对数损失|','|---|---|---:|---:|---:|']
        for r in x['metrics']:lines.append(f"|{r['fold_id']} / {r['subset']}|{r['model_id']}|{r['n']}|{r['brier']}|{r['log_loss']}|")
        lines.append('')
    lines+=['## 边界与限制','']+['- '+x for x in limitations]+['','完整数值、样本日期、组参数、覆盖、审计快照及来源指纹见同目录独立审查.json。']
    (OUT/'独立审查.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(passed=len(checks),source_files=len(sources),metric_rows=98,comparison_rows=70,coverage_rows=18,output=str(OUT)),ensure_ascii=False))
if __name__=='__main__':main()
