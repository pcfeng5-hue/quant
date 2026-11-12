"""Incremental delivery correspondence audit; does not re-run metadata DB audit."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
ROOT=Path(__file__).resolve().parents[2];WORK=Path(__file__).resolve().parent;OUT=ROOT/'outputs/输入证据合库与验证设计_20261105'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=['买入还是等待_研究候选BW17_冻结v1.json','累计研究选择登记_增补BW17.json','本轮用户确认与参数状态.json','历史研究用途与缺证据矩阵.json','设计冻结与来源指纹.json']
initial={n:sha(OUT/n) for n in files};p,r,u,m,f=[read(OUT/n) for n in files]
checks=[]
def ck(n,v,d=None):checks.append(dict(check=n,passed=bool(v),details=d))
oldpath=ROOT/'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json';old=read(oldpath)
ck('explicit_user_10_session_confirmation',u['source_kind']=='explicit_user_reply_in_this_chat' and u['verbatim_answer']=='未来10个交易日' and u['confirmed_field']=='main_horizon_planned_exchange_sessions' and u['confirmed_value']==10)
latest=u['latest_user_parameter_state'];pending={k:v for k,v in latest.items() if k!='main_horizon_planned_exchange_sessions'}
ck('latest_1_confirmed14_pending',len(latest)==15 and latest['main_horizon_planned_exchange_sessions']==10 and len(pending)==14 and all(v is None for v in pending.values()) and u['confirmed_groups']==1 and u['pending_groups']==14)
ck('protocol_horizon_concordance',p['user_binding']['H_planned_sessions']==p['research_constants']['H_planned_sessions']==r['new_choice']['H']==10 and p['paths']['all_paths']['common_terminal']=='T=d10 close, fixed from d0, never reset from later buy')
ck('14_unconfirmed_groups_exact',p['unbound_user_groups']==pending and p['user_binding']['other_14_user_groups_unconfirmed'] is True)
ck('old_15_NULL_unchanged',len(old['pending_freeze'])==15 and all(v is None for v in old['pending_freeze'].values()) and sha(oldpath)==u['old_15_null_contract_sha256']==f['source_hashes'][str(oldpath.relative_to(ROOT))] and u['old_contract_modified'] is False)
ck('BW17_identity_correspondence',p['research_selection_id']==r['new_choice']['id']==17 and p['protocol_id']==r['new_choice']['definition_id']=='BW17_002414_buy_vs_wait_H10_W2_v1')
ck('17_total_not17_scored',r['old_registered_choices']==16 and r['total_registered_choices']==17 and r['new_evaluated_choices']==0 and r['old_16_evaluation_status_unchanged'] is True and r['old_failures_retained'] is True and r['legacy_model_definitions']==4)
ck('new_choice_unrun_no_labels_models_scores',r['new_choice']['status']=='frozen_unrun_evidence_blocked' and all(r['new_choice'][k]==0 for k in ['models_fitted','real_labels','scores']) and p['registration_basis']['old_choices']==16 and p['registration_basis']['new_policy_definitions']==1 and p['registration_basis']['new_models']==p['registration_basis']['new_scores']==0)
ck('no_H5_scored_or_frozen_misclaim',p['registration_basis']['H5_was_discussion_only_never_frozen_or_scored'] is True)
ck('operational_gates_all_false',p['gates']['definition_frozen'] is True and all(v is False for k,v in p['gates'].items() if k!='definition_frozen'))
ck('not_executable_prediction_freeze',p['definition_only'] is True and p['status']=='candidate_definition_frozen_evidence_bindings_missing_not_executable' and f['fully_executable_prediction_protocol'] is False and f['frozen_before_real_labels_models_scores'] is True)
ck('user_preferences_not_inferred_from_constants',u['actual_account_flat_confirmed'] is False and u['capital_or_trading_authorized'] is False and p['research_constants']['research_constants_do_not_change_account_risk'] is True and p['research_constants']['starting_cash_CNY']==10000 and p['research_constants']['max_confirmation_sessions']==r['new_choice']['W']==2 and len(u['research_constants_are_not_user_preferences'])==6)
ck('risk_preservation_explicit',u['existing_realized_loss_pause_CNY']==p['confirmed_risk_preservation']['existing_pause_realized_loss_CNY']==2000 and u['floating_loss_counted_in_that_trigger'] is False and u['risk_setting_modified'] is False and p['confirmed_risk_preservation']['floating_PnL_reported_separately'] is True and p['confirmed_risk_preservation']['this_is_not_capital_authorization'] is True)
ck('execution_cost_rights_bindings_remain_NULL',all(p['order_and_wealth_contract'][k] is None for k in ['execution_binding','fee_and_tax_binding','corporate_action_and_liability_binding']) and p['labels_and_reporting']['economic_neutral_band'] is None)
ck('2023_2024_development_only_2025_2026_closed',p['scope']['data_dates_for_future_development_only']==['2023-01-03','2024-12-31'] and p['scope']['these_dates_are_previously_seen_development_not_independent_test'] is True and p['scope']['targets_2025_2026_isolated'] is True and p['scope']['no_cross_2024_endpoint_or_outcome_read'] is True)
ck('old14_optional_columns_not_scanned',r['old14_prepared_columns_still_not_scanned'] is True and set(p['scope']['optional_features_not_selected'])=={'chip_estimates_or_summaries','MACD','KDJ','MA_groups','volume_groups','news_or_policy_sentiment','current_industry_membership','large_order_or_institutional_identity_proxies'})
canon=json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
ck('protocol_file_SHA_match',f['protocol_file']==files[0] and f['file_sha256']==initial[files[0]])
ck('protocol_canonical_SHA_match',hashlib.sha256(canon).hexdigest()==f['canonical_json_sha256'])
ck('user_confirmation_SHA_match',f['new_user_confirmation_file_sha256']==initial[files[2]])
ck('5_design_source_hashes_match',len(f['source_hashes'])==5 and all(sha(ROOT/path)==h for path,h in f['source_hashes'].items()))
ck('version_registration_change_control',f['future_changes_require_new_registration'] is True and 'new version and research-choice entry' in p['change_control'])
oldfields=read(OUT/'字段时点与版本台账.json')['field_provider_rows'];matrix_fields=m['rows'][:10]
ck('matrix_14_rows',m['row_count']==len(m['rows'])==14 and len({x['item'] for x in m['rows']})==14)
ck('10_matrix_fields_exact_metadata_ids_and_refs',[x['item'] for x in matrix_fields]==[x['evidence_id'] for x in oldfields] and all(x['reference']==s['snapshot_source_reference'] for x,s in zip(matrix_fields,oldfields)))
ck('matrix_selected_only_close_fields',all(x['selected_for_BW17']==(s['field_family']=='raw_close') for x,s in zip(matrix_fields,oldfields)) and p['scope']['selected_input_families'][0]=='raw_close')
ck('all_matrix_new_formal_current_false',all(x['new_formal_historical_action_input'] is False and x['current_or_runtime_input'] is False for x in m['rows']))
ck('matrix_no_new_gap_close_or_full_PIT_claim',m['new_formal_data_gaps_closed']==0 and m['original_36_gap_inventory_preserved'] is True and m['bounded_source_pass_finished'] is True and m['content_reextracted'] is False and m['extra_domain_source_paths']==0)
ck('matrix_gaps_and_minimum_proofs_complete',all(x.get('missing') and x.get('minimum_next_proof') for x in m['rows']))
ck('all_matrix_types_accounted',set(x['item'] for x in m['rows'][10:])=={'planned_calendar_2023_2024','daily_stock_status_and_rules','corporate_actions_fees_and_execution','optional_chips_news_industry_and_large_orders'})
ck('old_registry_reference_exists',(ROOT/r['old_registry_reference']).is_file())
ck('user_binding_file_matches',p['user_binding']['latest_parameter_state_file']==files[2])
ck('5_artifacts_stable_during_review',initial=={n:sha(OUT/n) for n in files})
result=dict(audit_id='BW17_delivery_correspondence_20261105',created_at_utc=datetime.now(timezone.utc).isoformat(),all_checks_passed=all(x['passed'] for x in checks),passed=sum(x['passed'] for x in checks),total=len(checks),checks=checks,artifact_sha256=initial,protocol_canonical_sha256=f['canonical_json_sha256'],metadata_83_checks_not_rerun=True,independent_policy_math_review_not_claimed=True,market_data_or_targets_read=False,new_labels=0,new_models=0,new_scores=0,interpretation='Delivery identity, version, registration, user-binding and admission-boundary concordance only; not an executable-protocol or predictive-validity certification.')
(WORK/'协议交付对应复核.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(WORK/'协议交付对应复核.md').write_text(f'''# BW17协议交付对应复核

2026年11月5日。增量对应审查{result['passed']}/{result['total']}通过，未重跑元数据83项。

用户确认10个计划交易日，新状态1项已确认、14项待定；旧15项NULL合同及哈希保持。BW17作为新增一项未运行政策定义登记，累计17项，旧16项及失败保留；未新增已评估选择、模型、标签或评分。W2、研究现金10000、18:00等均未冒充用户偏好或资金授权。

设计正文SHA、规范JSON SHA、用户确认SHA及5个来源指纹相符，矩阵14行与10组字段及其引用对应；只有收盘字段被本候选选中，所有正式/current/runtime和真实实验门仍关闭。冻结的是候选定义，完整可执行预测协议未完成；费用、成交和权益绑定仍NULL。

这里只核交付对应关系，政策数学与执行逻辑另由专门独立审查负责。所有新文件在本次审查中保持不变，未读取市场或目标数据。
''')
print(json.dumps({k:result[k] for k in ['all_checks_passed','passed','total','protocol_canonical_sha256']}))
if not result['all_checks_passed']:raise SystemExit(1)
