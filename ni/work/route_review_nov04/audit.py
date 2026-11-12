"""Independent route/charter correspondence audit, not a market-data reader.

Queries no database or outcome table. Protected databases are fingerprinted only.
The pending route state is reviewed separately because publication changes its
completion metadata; five stable delivery documents and build code are locked.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import ast,hashlib,json,re

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/下一阶段路线决策_20261104'
START=datetime.fromisoformat('2026-11-04T05:42:27.899369+00:00')

def guard():
    now=datetime.now(ZoneInfo('America/Toronto'))
    if now.date().isoformat()!='2026-11-04' or not(0<=now.hour<5) or (now.hour==4 and now.minute>=45) or now.astimezone(timezone.utc)>START+timedelta(minutes=40):
        raise RuntimeError('Outside bounded overnight review window')
    return now

def read(path):return json.loads(Path(path).read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    checked=guard();checks=[]
    def ck(name,ok,details=None):
        checks.append(dict(check=name,passed=bool(ok),details=details))
        if not ok:raise AssertionError(name)
    decision=read(OUT/'路线选择与准入门.json')
    charter=read(OUT/'下一批有限工程任务书.json')
    precheck=read(OUT/'任务书来源存在性预检.json')
    build=read(OUT/'本轮构建核验.json')
    state=read(OUT/'本轮状态与续作断点.json')
    protected=build['protected_source_sha256']
    before={p:sha(ROOT/p) for p in protected}
    ck('222_prior_source_fingerprints_match',len(protected)==222 and before==protected)
    ck('builder_checks_all_passed',build['all_checks_passed'] and build['passed']==build['total'] and all(c['passed'] for c in build['checks']))
    label=read(ROOT/'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json')
    gaps=read(ROOT/'outputs/时间执行与数据准入缺口矩阵_20261102/完整缺口矩阵_v1.json')
    review_paths=['outputs/研究证据与覆盖审查_20261101/研究证据与覆盖审查_v1.md','outputs/预测问题与标签适用性审查_20261101/预测问题与标签适用性审查_v1.md','outputs/时间执行与数据准入缺口矩阵_20261102/时间执行与数据准入缺口矩阵_v1.md']
    old_reports=[(ROOT/p).read_text() for p in review_paths]
    ck('three_saved_reviews_present_in_protected_set',all(p in protected for p in review_paths))
    ck('16_choices_and_three_negative_candidates_retained',decision['cumulative_registered_variants']==state['cumulative_registered_variants']==16 and decision['old_failures_retained'] and all(m in old_reports[0] for m in ['M1','M2','M3','未取得升级依据']))
    ck('36_gap_inventory_not_claimed_closed',gaps['matrix_row_count']==36 and decision['new_data_gaps_closed']==state['archive_summary']['newly_closed_data_gaps']==0)
    ck('only_R2_selected',len(decision['options'])==5 and sum(bool(r['selected']) for r in decision['options'])==1 and next(r['id'] for r in decision['options'] if r['selected'])==decision['selected_route']=='R2')
    ck('confirmed_use_case_only_preserved',decision['user_confirmed_first_use_case']==label['user_confirmed']['first_use_case']=='收盘后判断回落时该买入还是继续等待')
    ck('all_15_parameter_groups_remain_null',decision['pending_freeze']==state['pending_freeze']==label['pending_freeze'] and len(decision['pending_freeze'])==15 and all(v is None for v in decision['pending_freeze'].values()))
    ck('selected_gap_focus_only_existing_ids',set(decision['gap_focus'])<=set(g['gap_id'] for g in gaps['gaps']))
    ck('new_market_labels_models_scores_zero',decision['new_real_labels']==decision['new_models_fitted']==decision['new_scores_calculated']==0 and state['new_real_market_targets']==state['new_models_fitted']==state['new_scores_calculated']==0)
    for key in ['model_input_approved','runtime_usable','current_forecast_generated','outcomes_2025_2026_opened','real_funds_authorized','prospective_forecast_started']:
        ck('decision_gate_false_'+key,decision[key] is False)
    ck('old_protocol_risk_unchanged_flag',state['old_protocol_or_risk_modified'] is False)
    ck('pending_route_not_yet_counted_complete',state['status']=='route_built_pending_independent_audit' and state['review_package_step']==4 and state['review_package_step_completed'] is False and state['archive_summary']['review_steps_completed']==3 and state['archive_summary']['review_steps_remaining']==1 and state['counts_as_completed_nightly_batch'] is False)
    ck('next_task_is_engineering_not_model_protocol',charter['status']=='engineering_evidence_audit_only_not_model_protocol' and charter['symbol']=='002414.SZ')
    ck('existing_development_metadata_scope_only',charter['metadata_period']==['2023-01-03','2024-12-31'] and charter['exchange']=='SZSE')
    ck('five_OHLCV_families_no_optional_expansion',charter['field_families']==['raw_open','raw_high','raw_low','raw_close','raw_volume'])
    ck('two_fixed_saved_provider_roles_and_ten_pairs',charter['providers']==['eastmoney_primary_saved_snapshot','tencent_comparison_saved_snapshot'] and charter['field_family_provider_pairs']==10==len(charter['field_families'])*len(charter['providers']))
    paths=charter['local_source_paths']
    ck('fifteen_fixed_local_paths_unique_and_present',len(paths)==len(set(paths))==15 and all((ROOT/p).is_file() for p in paths))
    ck('precheck_same_paths_and_existing_sha',set(precheck['sources'])==set(paths) and all(precheck['sources'][p]['exists'] is True and precheck['sources'][p]['sha256']==sha(ROOT/p) for p in paths))
    ck('precheck_not_next_ledger_completion','Only file existence' in precheck['scope'] and 'not extracted' in precheck['scope'])
    ck('only_one_fixed_source_pass',charter['source_pass_limit']==1)
    ck('extra_five_only_explicit_references_registered_preread',charter['local_source_path_cap']==20 and charter['additional_referenced_evidence_file_cap']==5 and all(s in charter['additional_path_policy'] for s in ['explicitly referenced','record path/reason before read','no provider expansion','no','price/outcome']))
    ck('30_work_plus_10_QA_within_40',charter['work_minutes_budget']==30 and charter['verification_and_save_minutes_reserved']>=10 and charter['total_batch_minutes_cap']==40 and charter['work_minutes_budget']+charter['verification_and_save_minutes_reserved']<=40)
    ck('three_concrete_next_outputs',len(charter['deliverables'])==3 and any('10组' in r for r in charter['deliverables']) and any('计划交易日' in r or '计划交易日及状态' in r for r in charter['deliverables']) and any('可恢复性结论' in r for r in charter['deliverables']))
    ck('required_asof_version_unknown_columns',{'field_family','provider','source_path','source_sha256','captured_at','historical_first_available_at','revision_available_at','time_precision','evidence_kind','reason_unknown','admission_for_declared_use'}<=set(charter['evidence_columns']))
    acceptance=' '.join(charter['acceptance']);stops=' '.join(charter['stop_conditions'])
    ck('all_families_dates_accounted_no_silent_drop','全部10组' in acceptance and '声明日期' in acceptance and '静默丢行' in acceptance)
    ck('captured_time_not_historical_publication','采集时刻不代替历史公开' in acceptance and '统一猜滞后' in acceptance)
    ck('calendar_not_observed_bars_month_absence_not_normal','计划日历不是股票观察日' in acceptance and '月报未出现记录不等于逐日正常' in acceptance)
    ck('technical_completion_never_PIT_or_forecast','不等于PIT或预测通过' in acceptance and '门保持false' in acceptance)
    ck('finite_stop_and_NULL_unknown','固定本地来源集合' in stops and 'NULL' in stops and '不补0' in stops)
    ck('fallback_design_not_retroactive_PIT','前向首收采集设计' in stops and '不能宣称历史PIT补齐' in stops)
    ck('unfinished_checkpoint_not_completed_batch','保存部分状态' in stops and '不记完成批次' in stops)
    for key in ['required_user_material_now','new_network_collection_allowed_in_this_charter','new_raw_price_values_or_outcomes_exported','new_real_labels_allowed','new_models_or_scores_allowed','optional_feature_sweep_allowed','prior_risk_configuration_mutation_allowed']:
        ck('charter_forbidden_'+key,charter[key] is False)
    ck('source_paths_not_target_datasets',not any(Path(p).suffix in ['.sqlite','.db','.csv'] or '开发期结果隔离' in p or '逐日概率' in p for p in paths))
    report=(OUT/'下一阶段路线决策记录_v1.md').read_text()
    ck('report_preserves_no_current_or_new_label_claim','不新增市场数据、真实标签、模型、评分' in report and '不是新的市场预测' in report)
    ck('report_explains_scope_not_model_whitelist','不是新模型白名单' in report and '不是补造官方状态' in report)
    ck('report_preserves_receipt_vs_60day_boundary','不反向证明2023年可见' in report and '不算60个前向模拟交易日' in report and '观察期不能偷跑' in report)
    ck('report_keeps_user_risk_funds_limits','2000元累计已实现亏损暂停新增买入并复核' in report and '浮亏另列' in report and '未授权使用资金' in report)
    ck('report_does_not_claim_next_batch_or_36_gaps_done','不表示下一批台账、36项补缺或新模型已经完成' in report)
    ck('all_local_report_links_resolve',all((OUT/p).is_file() for p in re.findall(r'\]\((\.{1,2}/[^)]+)\)',report)))
    code=ROOT/'work/route_decision_nov04/build.py';tree=ast.parse(code.read_text())
    imports={n.names[0].name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import)}|{n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
    ck('build_uses_only_local_standard_library_no_DB_or_network',not(imports & {'sqlite3','requests','urllib','http','akshare','pandas','tushare','subprocess'}))
    guard()
    after={p:sha(ROOT/p) for p in protected}
    ck('all_222_sources_unchanged_after_independent_review',after==before==protected)
    stable=['下一阶段路线决策记录_v1.md','路线选择与准入门.json','下一批有限工程任务书.json','任务书来源存在性预检.json','本轮构建核验.json']
    delivery={str((OUT/n).relative_to(ROOT)):sha(OUT/n) for n in stable}
    result=dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,checked_at_local=checked.isoformat(),source_sha256_before=before,source_sha256_after=after,delivery_sha256=delivery,reviewed_pending_state_sha256=sha(OUT/'本轮状态与续作断点.json'),publication_completion_metadata_may_change=True,build_code_sha256=sha(code),audit_method='Independent source hashes and saved-review/route/charter semantic correspondence; no producer functions executed',actual_target_tables_read=False,new_real_labels=0,new_models_or_scores=0,outcomes_2025_2026_opened=False)
    guard();WORK.mkdir(parents=True,exist_ok=True)
    (WORK/'独立复核.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (WORK/'独立复核.md').write_text(f'''# 路线决策独立复核

2026-11-04，多伦多。{len(checks)}/{len(checks)}项对应检查通过。

R2有限必要输入证据工程与前三份审查一致。下一批固定五类OHLCV×两已存来源，共10组，2023—2024深交所计划日/状态来源索引，产出三项可恢复工程成果。15个固定来源及其哈希存在；最多5个额外已引用证据必须先登记再读，不能扩供应商或导出原价/结果。30分钟作业、至少10分钟核验保存，总计40分钟。一次固定集合检查后保留未知，无法恢复历史PIT则转有限前向首收设计，不能循环全面搜同一缺口。

222个保护源前后哈希一致；15组参数仍NULL，累计16不变。源码未执行，仅静态核查本地标准库和范围；没有查询真实目标表、生成标签或评分。下一批台账、36项补缺、历史PIT及当前预测均未被声明完成；前向首收不是预测/模拟或60日观察起点。

待发布状态审查为3/1、step4未完成；根在全部发布核验后才可改为4/0。状态的审核哈希单列，五份稳定主交付锁定于JSON的delivery_sha256。此前初稿的状态摘要超前、额外路径边界和保存预留已明确修订；原保护源未变。
''')
    print(json.dumps(dict(passed=len(checks),total=len(checks),all_checks_passed=True,protected_sources=len(protected)),ensure_ascii=False))

if __name__=='__main__':main()
