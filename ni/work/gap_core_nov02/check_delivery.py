"""Independent correspondence audit of the 36-row gap matrix.

Reads saved JSON/Markdown and file bytes only. Does not open market databases,
create outcome labels, fit models, calculate forecasts or change source files.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/时间执行与数据准入缺口矩阵_20261102'

def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def main():
 names=['时间执行与数据准入缺口矩阵_v1.md','完整缺口矩阵_v1.json','缺口矩阵总表.md','逐项补证与验收细则.md','最小补证作业清单_v1.md','后续脱敏资料字段模板.json','来源索引与SHA256.json']
 delivery_before={name:sha(OUT/name) for name in names}
 matrix=read(OUT/'完整缺口矩阵_v1.json');index=read(OUT/'来源索引与SHA256.json');core=read(WORK/'核心缺口审查.json')
 rows=matrix['gaps'];byid={r['gap_id']:r for r in rows};refs=index['evidence_references']
 source_before={p:sha(ROOT/p) for p in index['protected_source_sha256']}
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details))
  if not ok:raise AssertionError(name)
 ck('exact36_rows_three_groups',len(rows)==matrix['matrix_row_count']==36 and Counter(r['group'] for r in rows)=={'core_temporal_execution':16,'optional_feature':15,'research_and_use_control':5})
 ck('all_gap_IDs_unique',len(byid)==36)
 ck('core_independent_source_review_passed',core['all_checks_passed'] and core['passed']==core['total']==27)
 for original in core['gaps']:
  actual=byid[original['gap_id']]
  ck('core_source_record_exact_'+original['gap_id'],actual['source_record']==original)
  ck('core_normalized_values_exact_'+original['gap_id'],all(actual[k]==v for k,v in original.items() if k!='source_reference_ids'))
  ck('core_source_namespace_exact_'+original['gap_id'],actual['source_reference_ids']==['CORE:'+s for s in original['source_reference_ids']])
 common=['gap_id','title','source_reference_ids','evidence_as_of_scope','missing_evidence','affected_claims','minimum_completion_evidence','completion_criterion','independent_work_possible_now','owner','user_participation','dependencies','current_use_limit','group','required_for','alternative_route_and_limit']
 ck('all36_have_full_evidence_and_completion_schema',all(all(k in r and (r[k] or k=='dependencies') for k in common) for r in rows))
 ck('all36_have_explicit_owners_and_user_timing',all(r['owner'] and r['user_participation']['required_now'] is False for r in rows))
 ck('all_source_references_resolve',all(s in refs for r in rows for s in r['source_reference_ids']))
 for sid,ref in refs.items():ck('reference_file_hash_'+sid,(ROOT/ref['path']).is_file() and sha(ROOT/ref['path'])==ref['sha256'])
 ck('all_protected_source_hashes_match_manifest',source_before==index['protected_source_sha256'])
 ck('all_dependency_IDs_exist',all(d in byid for r in rows for d in r['dependencies']))
 visited=set();active=set()
 def visit(g):
  if g in active:raise AssertionError('Dependency cycle: '+g)
  if g in visited:return
  active.add(g)
  for d in byid[g]['dependencies']:visit(d)
  active.remove(g);visited.add(g)
 for r in rows:visit(r['gap_id'])
 ck('dependency_graph_acyclic',len(visited)==36)
 ck('dependencies_are_admission_not_collection_order','never to independent source collection' in matrix['dependency_semantics'] and 'unknown account fees do not prevent' in matrix['dependency_semantics'])
 ck('optional_features_do_not_block_all_research',all(not r['blocks_all_research_now'] for r in rows if r['group']=='optional_feature'))
 ck('all36_do_not_promote_gates_or_claim_closed',all(r['all_formal_gates_remain_false'] and not r['current_use_limit']['formal_historical_action_validation'] and not r['current_use_limit']['current_decision_or_execution'] and not r['newly_closed_this_batch'] for r in rows))
 ck('all36_allow_bounded_independent_document_work',all(not r['blocks_all_research_now'] and r['independent_work_possible_now'] for r in rows))
 expected_control=['P01','P02','P03','P04','P05']
 ck('exact_five_control_IDs',sorted(r['gap_id'] for r in rows if r['group']=='research_and_use_control')==expected_control)
 control_text={id:json.dumps(byid[id],ensure_ascii=False) for id in expected_control}
 ck('P01_pending_parameters_not_frozen_and_not_account_flat','15组研究参数仍NULL' in control_text['P01'] and '不是已核实实际空仓' in control_text['P01'] and '5日' in control_text['P01'])
 ck('P02_states_common_denominator_and_maturity','未成熟' in control_text['P02'] and '未知不填0' in control_text['P02'] and 'NAV不冒充' in control_text['P02'])
 ck('P03_prior16_and_negative_evidence_not_new_test','16=12描述信号+4模型' in control_text['P03'] and '308/298/331' in control_text['P03'] and '2025/2026目标不因本矩阵开放' in control_text['P03'])
 ck('P04_confirmed2000_realized_not_floating_pause_unchanged','已实现亏损2000元' in control_text['P04'] and '浮亏另列' in control_text['P04'] and '旧5万元账簿' in control_text['P04'] and '不擅自' in control_text['P04'])
 ck('P05_forward_log_does_not_retrocertify_PIT','前向日志不反向认证历史PIT' in control_text['P05'] and '不采购' in control_text['P05'])
 contract=read(ROOT/'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json')
 ck('15_original_parameter_groups_still_NULL',len(contract['pending_freeze'])==15 and all(v is None for v in contract['pending_freeze'].values()))
 ck('confirmed_question_exact_and_no_new_trading_auth',matrix['user_confirmed_first_use_case']==contract['user_confirmed']['first_use_case']=='收盘后判断回落时该买入还是继续等待' and not contract['user_confirmed']['is_trading_or_capital_authorization'])
 calendar=read(ROOT/'outputs/高德红外数据库/calendar_audit_result.json');conditions=read(ROOT/'work/conditions_finish_oct22/summary.json')
 ck('core_date_facts_latest_machine_calendar914_1015',calendar['end']=='2026-10-15' and calendar['expected_total_trading_days']==914 and '914' in byid['T03']['evidence_as_of_scope'] and '10/13' in byid['T03']['evidence_as_of_scope'])
 ck('conditions915_1016_and_four_zero_certifications',conditions['daily_rows']==915 and conditions['research_cutoff']=='2026-10-16' and all(conditions[k]==0 for k in ['actual_daily_verified_normal_count','official_daily_limit_price_count','execution_eligible_count','complete_account_cost_model_count']))
 ck('monthly_absence_not_promoted_to_daily_normal','未出现002414' in byid['X02']['evidence_as_of_scope'] and '不证明逐日全天正常' in byid['X02']['evidence_as_of_scope'])
 ck('fees_and_holdings_only_needed_before_respective_use',byid['C01']['user_participation']['required_now'] is False and byid['X06']['user_participation']['required_now'] is False)
 template=read(OUT/'后续脱敏资料字段模板.json')
 ck('redaction_template_not_now_no_credentials',template['required_now'] is False and template['not_a_request_for_credentials'] and template['user_provides_only_if_needed_and_redacted'] and set(['账户密码','验证码','完整账号','远程登录权限'])<=set(template['forbidden_to_request']))
 ck('all_account_template_fields_NULL',all(v is None for group in ['account_fee_fields','account_position_fields','corporate_action_fields','use_preferences'] for v in template[group].values()))
 report=(OUT/names[0]).read_text();total=(OUT/'缺口矩阵总表.md').read_text();detail=(OUT/'逐项补证与验收细则.md').read_text();worklist=(OUT/'最小补证作业清单_v1.md').read_text()
 ck('main_report_scope36_and_zero_gaps_closed','36项缺口' in report and '本批新增已关闭数据缺口为0' in report)
 ck('main_dates914_1015_915_1016_1160_1021_present',all(s in report for s in ['914日止10/15','915日止10/16','2026-10-21共1160','242个2022预热','918个2023起研究日']))
 ck('main_calendar_old_MD_scope_preserved','10/13和912日' in report and '不覆盖' in report)
 ck('main_afterhours_rule_limit_and_no_historical_backfill','不能统一假定15:00全部日量已齐' in report and '不能把2026制度回填2023—2024' in report and '排队和实际成交仍未核验' in report)
 ck('main_risk_and_no_user_work_now','用户当前不需要写代码' in report and '已实现亏损2000元' in report and '浮亏单列' in report and '旧5万元账簿' in report)
 ck('main_has_not_decided_fourth_review','下一批完成第4份' in report and '不提前宣布路线已选' in report)
 ck('main_no_new_labels_model_scores_later_targets','没有刷新行情、关闭数据缺口、生成真实标签' in report and '2025/2026后期目标继续隔离' in report and '累计16' in report)
 for row in rows:
  ck('table_and_detail_include_'+row['gap_id'],row['gap_id'] in total and row['title'] in total and row['gap_id'] in detail and row['title'] in detail)
 ck('worklist_explicitly_future_not_completed','以下均为后续待办' in worklist and '第4份路线决策尚未完成' in worklist)
 ck('all_local_report_links_resolve',all((OUT/link).is_file() for name in names if name.endswith('.md') for link in re.findall(r'\]\((\./[^)]+)\)',(OUT/name).read_text())))
 ck('matrix_no_new_data_or_targets_models_scores',matrix['new_gaps_closed']==0 and matrix['new_market_data_acquired'] is False and matrix['new_models_fitted']==0 and type(matrix['new_target_labels_generated']) is int and matrix['new_target_labels_generated']==0 and matrix['new_scores_calculated']==0 and matrix['cumulative_registered_variants']==16 and not any(matrix[k] for k in ['formal_model_input_approved','runtime_usable','current_forecast_generated','outcomes_2025_2026_opened']))
 online=index['official_online_observation'];ck('new_official_observation_hash_and_metadata',sha(ROOT/online['path'])==online['sha256'] and '2026' in json.dumps(online,ensure_ascii=False) and 'not a new binary download' in online['kind'])
 source_after={p:sha(ROOT/p) for p in source_before};ck('all201_protected_sources_unchanged',len(source_before)==201 and source_after==source_before)
 delivery_after={name:sha(OUT/name) for name in names};ck('all7_delivery_files_unchanged',delivery_after==delivery_before)
 result=dict(audit_id='core_gap_matrix_delivery_correspondence_20261102',all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,verified_matrix_rows=36,verified_core_records=16,verified_source_references=len(refs),verified_old_sources=len(source_before),source_sha256_before=source_before,source_sha256_after=source_after,delivery_sha256=delivery_before,new_market_result_database_queries=0,new_actual_labels_generated=False,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,blocking_findings=[])
 (WORK/'交付对应核验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 (WORK/'交付对应核验.md').write_text(f'''# 主缺口矩阵对应核验

2026-11-02。{len(checks)}/{len(checks)}通过。独立核对36行完整结构、16条core原记录逐值、42条来源引用、201份旧源与7主文件指纹，依赖无环。

日历914至10/15与旧MD912至10/13分开，条件915至10/16与行情1160至10/21分开，月报未见不升级为每日正常。账户费用不阻公共行情准备，依赖是声明用途放行条件，不是采集顺序。36条均有最小补证、验收和分工，无当前用户强制提供材料；模板值NULL且不请求密码等凭证。

5项control内容对应15组未冻结参数、共同目标资格、累计16与三轮否定结果、原已实现亏损暂停/浮亏口径、前向版本日志。当前只完成矩阵与计划，不提前选择第4份路线，不把技术检查或备份当预测准入。

本审查仅解析既有JSON/Markdown和文件指纹，不查询真实市场结果数据库，不新生成标签、模型或评分；2025/2026目标隔离保持。
''')
 print(json.dumps(dict(passed=len(checks),total=len(checks),core_records=16,matrix_rows=36,protected_sources=201,delivery_hashes=7),ensure_ascii=False))

if __name__=='__main__':main()
