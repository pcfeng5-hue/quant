"""Independently match delivered inventory against saved records; never rescore."""
from pathlib import Path
from collections import Counter
import hashlib,json,re,sqlite3
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/研究证据与覆盖审查_20261101'
checks=[]
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ck(name,value,details=None):
    checks.append(dict(check=name,passed=bool(value),details=details));assert value,name
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def main():
    own=j(WORK/'独立审查.json');master=j(OUT/'16项研究变体完整台账.json');index=j(OUT/'全部结果表与样本索引.json');manifest=j(OUT/'原有结果文件清单与SHA256.json')
    ck('previous_independent_54_checks_and_sources_still_match',own['all_checks_passed'] and own['passed']==own['total']==54 and all(sha(ROOT/p)==v for p,v in own['source_sha256'].items()))
    ck('16_counting_and_unique_definitions',master['variant_count']==16 and master['descriptive_signal_definitions']==12 and master['unique_model_definitions']==4 and [v['variant_id'] for v in master['variants']]==list(range(1,17)) and len({v['key'] for v in master['variants']})==16)
    ck('model_entries13to16_exactly_M0_M1_M2_M3',[v['key'] for v in master['variants'][12:]]==['M0_laplace_constant','M1_ma_group_shrinkage','M2_ma_volume_hierarchical','M3_shenzhen_ma20_group_shrinkage'])
    ck('all_three_round_records_equal_independent_inventory',master['model_rounds']==own['runs'])
    for variant in master['variants'][12:]:
        expected=[name for name,x in own['runs'].items() if variant['key'] in x['models']]
        ck('model_'+str(variant['variant_id'])+'_repeated_comparator_rounds_and_all_metrics',variant['rounds']==expected and [x['round_id'] for x in variant['evaluations']]==expected and all(ev['all_saved_metrics']==[r for r in own['runs'][ev['round_id']]['metrics'] if r['model_id']==variant['key']] and ev['scoring_dates']==len(own['runs'][ev['round_id']]['scoring_dates']) and ev['fixed_grid_dates']==len(own['runs'][ev['round_id']]['fixed_grid_dates']) for ev in variant['evaluations']))
        ck('model_'+str(variant['variant_id'])+'_not_current_forecast',not variant['current_forecast_approved'])
    ck('no_new_model_score_target_or_runtime',master['new_models_fitted']==master['new_scores_calculated']==0 and not any(master[k] for k in ['new_target_labels_generated','outcomes_2025_2026_opened','current_forecast_generated','formal_model_input_approved','runtime_usable']))
    ck('88_snapshot_rows_and_unique_sources',len(manifest['files'])==88 and len({r['source'] for r in manifest['files']})==88 and len({r['snapshot'] for r in manifest['files']})==88)
    for row in manifest['files']:
        a=ROOT/row['source'];b=OUT/row['snapshot']
        ck('snapshot_exact_'+row['source'],a.is_file() and b.is_file() and a.stat().st_size==b.stat().st_size==row['bytes'] and sha(a)==sha(b)==row['sha256'])
    with ro(OUT/'研究证据汇总.sqlite') as c:
        ck('summary_sqlite_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        variants=[dict(r) for r in c.execute('SELECT * FROM variants ORDER BY variant_id')]
        ck('sqlite_16_variant_records_equal_json',len(variants)==16 and [json.loads(r['record_json']) for r in variants]==master['variants'])
        tables=index['tables'];seen=set();modelpred=0;checkedrows=0
        for item in tables:
            key=(item['round_id'],item['table_name']);assert key not in seen;seen.add(key)
            with ro(ROOT/item['source_database']) as old:
                table=item['table_name'];assert table.replace('_','').isalnum()
                expected=[dict(r) for r in old.execute('SELECT * FROM "'+table+'"')]
            saved=[dict(r) for r in c.execute('SELECT * FROM saved_result_rows WHERE round_id=? AND table_name=? ORDER BY row_number',key)]
            actual=[json.loads(r['record_json']) for r in saved]
            ck('original_table_exact_'+key[0]+'_'+key[1],len(saved)==len(expected)==item['rows'] and actual==expected and [r['row_number'] for r in saved]==list(range(len(saved))) and all(r['source_database']==item['source_database'] for r in saved))
            checkedrows+=len(saved)
            if table=='predictions':
                modelpred+=len(saved)
                ck(key[0]+'_all_saved_prediction_outcome_dates_bounded_2024',all(r['outcome_observation_date']<='2024-12-31' for r in actual))
        ck('all37_tables13369_rows_no_unindexed_extras',len(tables)==37 and checkedrows==13369 and c.execute('SELECT COUNT(*) FROM saved_result_rows').fetchone()[0]==checkedrows)
        ck('all2172_original_model_prediction_rows_retained',modelpred==2172)
        totals={name:c.execute('SELECT COUNT(*) FROM saved_result_rows WHERE table_name=?',(name,)).fetchone()[0] for name in ['metrics','comparisons','folds']}
        ck('98_metrics70_comparisons18_folds_in_db',totals==dict(metrics=98,comparisons=70,folds=18))
    ck('all_sample_date_indexes_exact',all(index['all_sample_dates'][name]['scoring_dates']==run['scoring_dates'] and index['all_sample_dates'][name]['fixed_grid_dates']==run['fixed_grid_dates'] and index['all_sample_dates'][name]['training_membership_file']==run['training_membership_file'] and index['all_sample_dates'][name]['exclusion_ledger_file']==run['exclusion_ledger_file'] for name,run in own['runs'].items()))
    ck('M1toM2_coverage_and_lost_dates_exact',master['coverage_reconciliation_M1_to_M2']==own['coverage_reconciliation_M1_to_M2'] and master['lost_M2_dates']==own['lost_M2_dates'])
    attachment=(OUT/'全部既有评分与覆盖.md').read_text();blocks=[json.loads(s) for s in re.findall(r'```json\s*\n(.*?)\n```',attachment,re.S)]
    expectedblocks=[run[key] for run in own['runs'].values() for key in ['comparisons','folds','fitted_rows','calibration_rows']]
    ck('markdown_all12_json_blocks_exact_and_unselected',blocks==expectedblocks)
    ck('markdown_all98_rounded_score_lines_match',all(f"| {r['fold_id']} | {r['subset']} | {r['model_id']} | {r['n']} | {float(r['brier']):.9f} | {float(r['log_loss']):.9f} |" in attachment for run in own['runs'].values() for r in run['metrics']))
    report=(OUT/'研究证据与覆盖审查_v1.md').read_text()
    required=['12个描述性信号定义＋4个模型定义','12+2+1+1','不是16次独立检验','不能拿跨轮M0或M1分数直接相减排名','2172是含重复模型和日期的存储行数','本批没有训练模型、生成新目标或重新评分','+0.002997484','+0.002026685','+0.003201429','M3并','冻结生产器','原源码修好','不能以检查通过代替预测有效','2025/2026','当前没有通过验收的买卖预测卡','没有进入模拟使用或真实资金阶段']
    # The contrast about M3 is expressed as “并未检验” in the definition table.
    required.remove('M3并');required.append('并未检验在M1/M2之上的增量')
    ck('report_counts_negative_results_and_technical_limits',all(s in report for s in required))
    ck('report_all14_pooled_score_lines_match',all(f"| {name} | {r['subset']} | {r['model_id']} | {r['n']} | {float(r['brier']):.9f} | {float(r['log_loss']):.9f} |" in report for name,run in own['runs'].items() for r in run['metrics'] if r['fold_id']=='POOLED'))
    ck('report_all_three_coverage_lines',all(line in report for line in ['|M1|366|10|25|23|308|61|616|','|M2|366|10|25|33|298|59|894|','|M3|366|10|25|0|331|66|662|']))
    ck('model_formulas_and_fixed_parameters_documented',all(s in report for s in ['p0=(k+1)/(n+2)','向p0固定20收缩','向均线父组固定20收缩','M3均价含当日','分母不含当日','训练少于100共同弃答','缺失不填0']))
    ck('all_manifest_source_and_snapshot_hashes_unchanged_at_end',all(sha(ROOT/r['source'])==sha(OUT/r['snapshot'])==r['sha256'] for r in manifest['files']))
    delivered=['16项研究变体完整台账.json','研究证据与覆盖审查_v1.md','全部既有评分与覆盖.md','研究证据汇总.sqlite','原有结果文件清单与SHA256.json','全部结果表与样本索引.json']
    payload=dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,old_source_sha256=own['source_sha256'],delivery_sha256={n:sha(OUT/n) for n in delivered},verified_tables=37,verified_saved_result_rows=13369,verified_model_prediction_rows=2172,verified_metric_rows=98,verified_comparison_rows=70,verified_fold_rows=18,verified_snapshot_files=88,new_model_fits=0,new_loss_scores_computed=0,later_targets_read=False,report_no_upgrade_evidence_preserved=True)
    (WORK/'交付对应核验.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (WORK/'交付对应核验.md').write_text(f'''# 研究证据台账交付对应核验

2026-11-01，{len(checks)}/{len(checks)}通过。

独立对应16项账法的13—16模型定义、全部98评分/70对照/18折、2172条既有模型预测、37张原表共13369行记录，原数据逐值相同。全部88份原样快照与原文件的大小和SHA均一致；SQLite完整性通过。模型轮次数据与此前独立54项证据核查逐字段相同。

报告全部合并分数、覆盖、公式、冻结参数、否定结论和M3原筛选辅助函数的技术边界准确；完整附件12段JSON及98行分数按原顺序保留，没有挑季度、组或抽样相位。

不运行原生产器、不拟合新模型、不计算新损失、不读取2025/2026目标。以上为交付对应准确性，不认证预测有效。审核后停止项目写入，以便全量冻结归档。
''')
    print(json.dumps(dict(all_checks_passed=True,passed=len(checks),tables=37,rows=13369,snapshots=88),ensure_ascii=False))
if __name__=='__main__':main()
