"""Independently compare optional-feature review with the delivered matrix.

Reads saved JSON/Markdown and hashes local files only; no database, network,
prices, outcome generation, fits or probability scoring.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import json,hashlib,re

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/时间执行与数据准入缺口矩阵_20261102'
FILES=['时间执行与数据准入缺口矩阵_v1.md','完整缺口矩阵_v1.json','缺口矩阵总表.md','逐项补证与验收细则.md','最小补证作业清单_v1.md','后续脱敏资料字段模板.json','来源索引与SHA256.json']
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 before={p:sha(OUT/p) for p in FILES}
 source=read(WORK/'特征缺口审查.json')
 matrix=read(OUT/'完整缺口矩阵_v1.json')
 index=read(OUT/'来源索引与SHA256.json')
 template=read(OUT/'后续脱敏资料字段模板.json')
 refs=index['evidence_references']
 gaps=matrix['gaps'];byid={r['gap_id']:r for r in gaps}
 report=(OUT/FILES[0]).read_text();table=(OUT/'缺口矩阵总表.md').read_text();details=(OUT/'逐项补证与验收细则.md').read_text();worklist=(OUT/'最小补证作业清单_v1.md').read_text()
 checks=[]
 def ck(name,ok,detail=None):
  checks.append(dict(check=name,passed=bool(ok),details=detail))
  if not ok:raise AssertionError(name)
 ck('all_7_delivery_files_exist',all((OUT/p).is_file() for p in FILES))
 ck('independent_feature_source_review_passed_12',source['all_checks_passed'] and source['passed']==source['total']==12)
 ck('exact_36_unique_rows_three_groups',len(gaps)==len(byid)==36 and matrix['matrix_row_count']==36 and Counter(r['group'] for r in gaps)=={'core_temporal_execution':16,'optional_feature':15,'research_and_use_control':5})
 ck('count_fields_match_actual_groups',matrix['counts_by_group']==dict(Counter(r['group'] for r in gaps)))
 ck('all_original_15_ids_present_in_same_order',[r['gap_id'] for r in gaps if r['group']=='optional_feature']==[r['gap_id'] for r in source['gaps']])
 source_hashes=source['source_sha256_before'];ck('all_21_original_source_hashes_match_now',len(source_hashes)==21 and source_hashes==source['source_sha256_after'] and all(sha(ROOT/p)==h for p,h in source_hashes.items()))
 for original in source['gaps']:
  ident=original['gap_id'];row=byid[ident]
  ck(ident+'_source_record_exactly_preserved',row['source_record']==original)
  ck(ident+'_title_and_current_evidence_exact',row['title']==original['name'] and row['evidence_as_of_scope']==original['existing_evidence'])
  ck(ident+'_missing_and_affected_uses_exact',row['missing_evidence']==[original['unresolved_evidence']] and row['affected_claims']==original['affected_tasks'])
  ck(ident+'_minimum_evidence_and_workflow_preserved',row['minimum_completion_evidence']==[original['minimum_additional_evidence'],original['proposed_acquisition_and_verification']])
  ck(ident+'_criterion_and_independent_work_exact',row['completion_criterion']==original['acceptance'] and row['independent_work_possible_now']==[original['independent_work_possible_now']])
  ck(ident+'_alternative_not_promoted_to_equivalent',row['alternative_route_and_limit']==original['limited_alternative'] and row['limited_alternative']==original['limited_alternative'])
  ck(ident+'_owner_and_user_requirement_preserved',row['owner']==original['owner'] and row['user_participation']==dict(required_now=False,description=original['user_participation']) and row['user_required_now'] is False)
  ck(ident+'_source_path_set_unchanged',row['source_paths']==original['source_paths'] and len(row['source_reference_ids'])==len(original['source_paths']))
  mapped=[refs[ref] for ref in row['source_reference_ids']]
  ck(ident+'_namespaced_source_references_and_SHA',all(ref.startswith('FEATURE:') for ref in row['source_reference_ids']) and [r['path'] for r in mapped]==original['source_paths'] and all(r['sha256']==source_hashes[r['path']] and sha(ROOT/r['path'])==r['sha256'] for r in mapped))
  ck(ident+'_conditional_not_blocking_all_research',row['group']=='optional_feature' and row['blocks_all_research_now'] is False and row['does_not_block_all_other_research'] is True and '只有选用该特征' in row['required_for'])
  ck(ident+'_formal_gates_still_false',row['all_formal_gates_remain_false'] is True and row['current_use_limit']['formal_historical_action_validation'] is False and row['current_use_limit']['current_decision_or_execution'] is False and row['newly_closed_this_batch'] is False)
  ck(ident+'_T01_dependency_for_admission_not_data_collection',row['dependencies']==['T01'] and 'never to independent source collection' in matrix['dependency_semantics'])
  ck(ident+'_readable_tables_include_evidence_and_criterion',f'| {ident} |' in table and original['existing_evidence'] in table and original['minimum_additional_evidence'] in table and original['acceptance'] in table)
  ck(ident+'_detail_page_preserves_actions_and_limits',f'## {ident} '+original['name'] in details and original['independent_work_possible_now'] in details and original['limited_alternative'] in details and original['user_participation'] in details)
 ck('all_36_records_have_actionable_required_fields',all(all(k in r for k in ['title','source_reference_ids','evidence_as_of_scope','missing_evidence','affected_claims','minimum_completion_evidence','completion_criterion','independent_work_possible_now','owner','user_participation','dependencies','current_use_limit']) for r in gaps))
 ck('all_dependencies_reference_known_ids',all(d in byid for r in gaps for d in r['dependencies']))
 ck('all_source_ref_keys_resolve',all(k in refs for r in gaps for k in r['source_reference_ids']))
 ck('all_rows_no_global_block_or_new_closure',all(r['blocks_all_research_now'] is False and r['newly_closed_this_batch'] is False and r['all_formal_gates_remain_false'] for r in gaps))
 ck('matrix_counts_not_new_experiments',matrix['cumulative_registered_variants']==16 and matrix['new_gaps_closed']==0 and matrix['new_models_fitted']==matrix['new_scores_calculated']==0 and not any(matrix[k] for k in ['new_market_data_acquired','new_target_labels_generated','formal_model_input_approved','runtime_usable','current_forecast_generated','outcomes_2025_2026_opened']))
 ck('report_distinguishes_unadmitted_from_failed_test',all(t in report for t in ['M1/M2/M3已经测试但没有改善','可选特征没有补齐也不阻止独立的底座整理','三者分别管理','本批新增已关闭数据缺口为0']))
 ck('report_optional_coverage_facts_preserved',all(t in report for t in ['筹码摘要915日止10/16','完整供应商原生价档0日','15候选定义与1辅助','28个特征单元','67个日期角色','59个经济事件编号','46个月中5个月','41个月仍规则候选','公告312原件/4253页','10个政策样本']))
 ck('current_snapshot_not_claimed_refreshed_to_nov02','数据覆盖沿用旧快照' in report and '没有刷新行情' in report)
 ck('six_followup_work_groups_are_not_completed_data_collection',len(re.findall(r'^\d\. \*\*',worklist,re.M))==6 and '以下均为后续待办' in worklist and '第4份路线决策尚未完成' in worklist)
 ck('template_does_not_require_material_now',template['required_now'] is False and template['not_a_request_for_credentials'] is True and template['user_provides_only_if_needed_and_redacted'] is True)
 ck('all_future_private_and_preference_template_values_NULL',all(v is None for group in ['account_fee_fields','account_position_fields','corporate_action_fields','use_preferences'] for v in template[group].values()))
 ck('template_excludes_credentials_and_control',all(t in template['forbidden_to_request'] for t in ['账户密码','验证码','完整账号','远程登录权限']))
 ck('report_does_not_request_new_user_work_now','用户当前不需要写代码、找数据渠道、联系亲属或提供账户材料' in report and '目前不需要用户' not in template['stage'])
 ck('all_protected_source_hashes_match_now',all(sha(ROOT/p)==h for p,h in index['protected_source_sha256'].items()))
 after={p:sha(OUT/p) for p in FILES}
 ck('all_7_delivered_artifacts_unchanged_during_audit',before==after)
 ck('all_21_feature_sources_unchanged_during_audit',{p:sha(ROOT/p) for p in source_hashes}==source_hashes)
 result=dict(audit_id='gap_features_delivery_correspondence_20261102',created_at_utc=datetime.now(timezone.utc).isoformat(),all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,feature_gap_rows=15,total_matrix_rows=36,old_source_sha256=source_hashes,delivery_sha256=after,original_feature_records_exact=True,all_source_namespaces_resolve=True,source_facts_not_fresh_collection=True,new_market_data=False,new_actual_target_labels=False,new_models_or_scores=0,outcomes_2025_2026_opened=False,formal_input_approved=False,runtime_usable=False)
 (WORK/'交付对应核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 (WORK/'交付对应核验.md').write_text('# 条件性特征缺口交付对应核验\n\n2026年11月2日。'+str(len(checks))+'/'+str(len(checks))+'项通过。\n\n逐项核对F01—F15原记录完整保留、归一字段、21来源映射与SHA、当前准入门、最小补证/责任/替代限制和独立工作。36项总表、分组、依赖、主报告的条件性特征事实与六组后续作业对应；未准入与旧候选失败分开。后续脱敏模板不要求当前提供材料，全部私有/偏好值NULL并排除账户凭证。\n\n7交付文件与21特征来源前后哈希不变；新采集、真实目标、模型、评分均为0，后期目标未打开。详细检查与交付SHA见同目录JSON。完成后停止项目写入。\n')
 print(json.dumps(dict(passed=len(checks),total=len(checks),feature_rows=15,matrix_rows=36,locked_delivery_files=7),ensure_ascii=False))

if __name__=='__main__':main()
