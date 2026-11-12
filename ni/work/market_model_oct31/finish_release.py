"""Verify and save the completed registered M3 round; no new research choices.

Full archive is a separate frozen-snapshot operation outside this project.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/市场环境候选验证_20261031'
PROGRESS = ROOT / 'outputs/项目进度与交易需求档案.md'
POINTER = ROOT / 'outputs/夜间自动推进_20261028/最新续作指针.json'
ARCHIVE = Path('/Users/puchun/Documents/Codex/项目归档/ni/20261031_市场环境候选验证完整保存')

def read(p): return json.loads(Path(p).read_text())
def write(p, value):
    p = Path(p)
    temporary = p.with_name(p.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(p)
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as stream:
        for b in iter(lambda: stream.read(1048576), b''): h.update(b)
    return h.hexdigest()
def main():
    checks = []
    def ck(name, ok, details=None):
        checks.append(dict(check=name, passed=bool(ok), details=details))
        if not ok: raise AssertionError(name)
    cfg = read(WORK / 'contract.json')
    receipt = read(WORK / 'registration_receipt.json')
    protected = receipt['protected_source_sha256']
    ck('frozen_model_and_contract', sha(WORK/'run_market_model.py') == receipt['producer_code_sha256'] and sha(WORK/'contract.json') == receipt['contract_sha256'])
    ck('all_25_protected_sources_unchanged_before_release', len(protected)==25 and all(sha(ROOT/p)==v for p,v in protected.items()))
    core = [p for p in OUT.iterdir() if p.suffix=='.csv'] + [OUT/name for name in ['市场状态候选开发验证.sqlite','预登记研究协议.json','运行与输入记录.json','描述性开发筛选.json','实现验证结果.json']]
    ck('sixteen_core_files_exist', len(core)==16 and all(p.is_file() for p in core))
    before = {p.name:sha(p) for p in core}
    rerun = subprocess.run([sys.executable, str(WORK/'run_market_model.py')], cwd=ROOT, capture_output=True, text=True)
    (WORK/'完整重跑标准输出.txt').write_text(rerun.stdout)
    (WORK/'完整重跑标准错误.txt').write_text(rerun.stderr)
    ck('frozen_producer_full_rerun_exit_zero', rerun.returncode==0)
    after = {p.name:sha(p) for p in core}
    ck('sixteen_core_files_byte_identical_after_full_rerun', before==after, after)
    prod = read(OUT/'实现验证结果.json')
    inp = read(ROOT/'work/market_model_input_oct31/选定市场输入核查.json')
    static = read(ROOT/'work/market_model_design_oct31/最终冻结前确认.json')
    audit = read(ROOT/'work/market_model_independent_oct31/独立复核.json')
    ck('producer_31_checks_passed', prod['all_checks_passed'] and prod['passed']==prod['total']==31)
    ck('input_22_independent_checks_passed', inp['passed'] and inp['check_count']==22 and all(r['passed'] for r in inp['checks']))
    ck('prefreeze_static_14_checks_passed', static['final_static_review_passed'] and len(static['checks'])==14 and all(r['passed'] for r in static['checks']))
    ck('independent_47_checks_and_final_guard_hash', audit['all_checks_passed'] and audit['passed']==audit['total']==47 and audit['strict_publication_guard_sha256']==sha(WORK/'strict_screen_review.py'))
    ck('independent_frozen_fingerprints_match', all(audit[k]==receipt[k] for k in ['producer_code_sha256','contract_sha256']) and audit['source_sha256_before']==audit['source_sha256_after']==protected)
    with sqlite3.connect((OUT/'市场状态候选开发验证.sqlite').as_uri()+'?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        ck('output_sqlite_quick_check', conn.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        rows = lambda table: [dict(r) for r in conn.execute('SELECT * FROM '+table)]
        comparisons, metrics, folds = rows('comparisons'), rows('metrics'), rows('folds')
        preds, fitted, features = rows('predictions'), rows('fitted'), rows('selected_input_features')
        exclusions, membership = rows('registered_source_exclusions'), rows('membership')
    spec=importlib.util.spec_from_file_location('release_strict_guard', WORK/'strict_screen_review.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    screen=guard.strict_screen(comparisons,cfg)
    guardchecks=guard.validate_guard(comparisons,cfg)
    ck('strict_fold_identity_guard_14_checks_passed', len(guardchecks)==14 and all(r['passed'] for r in guardchecks))
    ck('strict_screen_matches_frozen_result', screen==read(OUT/'描述性开发筛选.json'))
    strict_result=dict(all_checks_passed=True,passed=len(guardchecks),total=len(guardchecks),checks=guardchecks,strict_result=screen,matches_frozen_producer_result=True,producer_or_contract_modified=False,strict_guard_sha256=sha(WORK/'strict_screen_review.py'))
    write(OUT/'筛选身份与完整性严格复核.json',strict_result)
    ck('331_dates_662_predictions_and_shared_models', len(preds)==662 and len({r['signal_date'] for r in preds})==331 and all(sum(x['signal_date']==r['signal_date'] for x in preds)==2 for r in preds))
    ck('66_original_grid_dates', len({r['signal_date'] for r in preds if r['fixed_every_fifth_anchor']})==66)
    ck('six_folds_and_18_fitted_rows',len(folds)==6 and len(fitted)==18)
    ck('all_484_selected_features_and_15_source_exclusions',len(features)==484 and len(exclusions)==15)
    ck('coverage_366_validation_anchors_331_scores_35_exclusions',sum(r['validation_anchors'] for r in folds)==366 and sum(r['evaluated_dates'] for r in folds)==331 and sum(r['no_registered_label']+r['label_crosses_fold_end']+r['feature_not_ready']+r['insufficient_training'] for r in folds)==35)
    fm={r['fold_id']:r for r in folds}
    ck('all_training_and_scoring_maturity_boundaries',all(r['label_end']<fm[r['fold_id']]['validation_start'] for r in membership) and all(r['latest_training_label_end']<fm[r['fold_id']]['validation_start']<=r['signal_date']<r['entry_observation_date']<=r['outcome_observation_date']<=fm[r['fold_id']]['validation_end'] for r in preds))
    ck('no_later_target_dates_or_approved_flags',max(r['outcome_observation_date'] for r in preds)<='2024-12-31' and all(r['model_input_approved']==r['runtime_usable']==0 for r in preds) and all(r['historical_first_availability_certified']==r['model_input_approved']==r['runtime_usable']==0 for r in features) and all(r['promotion_approved']==0 for r in comparisons))
    pooled=[r for r in metrics if r['fold_id']=='POOLED']
    deltas=[r for r in comparisons if r['fold_id']=='POOLED']
    ck('failed_screen_retained_no_upgrade',screen['evaluable'] and not screen['passed'] and screen['lower_brier_fold_count']==3 and not any(screen['conditions'].values()))
    registry=read(WORK/'cumulative_registration.json')
    ck('cumulative_16_preserves_previous_15',registry['previous_registered_variants']==15 and registry['new_registered_model_variants']==1 and registry['cumulative_registered_variants']==16 and registry['old_negative_results_retained'])
    registry['new_experiment']['outcome']='No improvement against same-date M0; descriptive screen failed; not promoted or retuned'
    registry['new_experiment']['result_reference']='outputs/市场环境候选验证_20261031/同日模型对照.csv'
    registry['new_experiment']['primary_brier_delta']=deltas[0]['brier_delta_M3_minus_M0']
    registry['new_experiment']['outcomes_and_review_saved']=True
    write(OUT/'累计研究与本轮结论台账.json',registry)
    copies=[
        (WORK/'registration_receipt.json','登记回执.json'),
        (ROOT/'work/market_model_input_oct31/选定市场输入核查.json','选定市场输入独立核查.json'),
        (ROOT/'work/market_model_input_oct31/选定市场输入核查.md','选定市场输入独立核查.md'),
        (ROOT/'work/market_model_design_oct31/最终冻结前确认.json','冻结前设计核查.json'),
        (ROOT/'work/market_model_design_oct31/最终冻结前确认.md','冻结前设计核查.md'),
        (ROOT/'work/market_model_design_oct31/后续研究审查建议.md','后续研究审查建议.md'),
        (ROOT/'work/market_model_independent_oct31/独立复核.json','独立复核.json'),
        (ROOT/'work/market_model_independent_oct31/独立复核.md','独立复核.md')]
    for source,name in copies:shutil.copy2(source,OUT/name)
    ck('all_audit_copies_byte_identical',all(sha(source)==sha(OUT/name) for source,name in copies))
    next_steps=[
        'Pause new candidate scoring: prepare a bounded four-document review using saved evidence only, without scanning the remaining 14 prepared columns',
        'Deliver research evidence and coverage review: preserve 16 cumulative variants, all negative results and different common samples; no cross-round score ranking',
        'Deliver prediction question and label suitability review: distinguish 5-session price direction from buy/wait/hold/sell, net return and path risk; no real new outcome generation',
        'Deliver temporal, execution and input-admission gap matrix: PIT/revisions, daily ST/suspension/limits, costs/fills, ex dates, chips, events and historical industry membership',
        'Deliver next-stage route decision record; allow no new model until a distinct, economically meaningful, testable preregistered question is justified',
        'Keep 2025/2026 target outcomes isolated until a separately registered later-phase protocol and existing entry checks; previously viewed years are not untouched tests',
        'Retain existing product constraints and risk settings; no simulated use or real funds before research and predictive acceptance']
    state=dict(client_date='2026-10-31',saved_at_utc=datetime.now(timezone.utc).isoformat(),origin='direct_human_request_not_scheduled_heartbeat',research_stage=5,
        status='registered_market_state_candidate_complete_independently_verified_negative_result_saved',
        completion=dict(completed=['M3 frozen registration, full development execution, independent review, strict publication check, deterministic rerun and saved checkpoint'],partial=['Probability tool research remains in stage 5; engineering direction label is not a confirmed final action/profit target'],blocked=['Formal historical PIT/first availability, daily official trading states and true costs/fills not certified; events/chips/industry restrictions remain']),
        market_data_last_date='2026-10-21',new_network_or_market_collection=False,
        selected_feature_id=cfg['feature_id'],development_period=['2023-01-03','2024-12-31'],horizon_observed_sessions=5,
        development_target=cfg['event'],target_is_net_profit=False,original_anchors=484,available_source_labels=469,source_label_exclusions=15,validation_anchors=366,
        scoring_dates=331,prediction_rows=662,fixed_grid_dates=66,folds=folds,
        metrics=pooled,paired_comparisons=deltas,descriptive_development_screen=screen,
        previous_registered_variants=15,new_registered_model_variants=1,cumulative_registered_variants=16,
        prepared_candidate_definitions=15,prepared_definitions_scored_in_this_round=1,other_prepared_columns_scored=False,
        selected_inputs_independently_rebuilt=484,actual_dependency_rows_verified=9680,
        verification_counts=dict(producer=31,input_independent=22,prefreeze_static=14,model_independent=47,strict_publication_guard=14),
        contract_sha256=receipt['contract_sha256'],producer_code_sha256=receipt['producer_code_sha256'],strict_publication_guard_sha256=sha(WORK/'strict_screen_review.py'),
        protected_source_sha256=protected,core_output_sha256=after,
        future_targets_generated_or_scored=False,outcomes_2025_2026_opened=False,current_forecast_generated=False,
        statistical_or_profit_advantage_certified=False,historical_first_availability_certified=False,model_input_approved=False,runtime_usable=False,phase_promotion_approved=False,
        old_protocol_or_risk_modified=False,counts_as_completed_nightly_batch=False,
        confirmed_test_intent_cash_cny=10000,confirmed_test_pause_cumulative_realized_loss_cny=2000,floating_pnl_separate=True,real_trading_authorized=False,
        next_checkpoint=next_steps,
        archive_verification_path=str(ARCHIVE/'归档校验结果.json'),
        archive_status_at_project_freeze='Snapshot is a separate final operation; only the external verification result certifies completion, not this planned path')
    state['archive_summary']={k:state[k] for k in ['scoring_dates','prediction_rows','fixed_grid_dates','metrics','phase_promotion_approved','cumulative_registered_variants']}
    state['archive_summary'].update(development_screen_evaluable=screen['evaluable'],development_screen_passed=screen['passed'])
    write(OUT/'本轮状态与续作断点.json',state)
    fold_lines='\n'.join('| '+r['fold_id']+' | '+str(r['training_used'])+' | '+str(r['validation_anchors'])+' | '+str(r['evaluated_dates'])+' | '+str(r['no_registered_label'])+' | '+str(r['label_crosses_fold_end'])+' |' for r in folds)
    report=f'''# 单一市场环境候选验证与保存报告

2026年10月31日，人工协作批次。研究仍在第5步。本轮已完成一个预登记候选、独立复算与保存；未取得升级依据，没有当前买卖预测。

## 结果

在2023—2024开发期的331个共同评分日期上，按深成指收盘相对20日均线分组的M3，Brier为0.251373492，高于同日常数基准M0的0.248172063（越低越好，差+0.003201429）。对数损失也略差。固定原始日期每隔5个观察日的66例敏感性检查没有改善。六折仅3折Brier更低，事先固定的四项描述性筛选全部不通过。**保留否定结果，不升级、不改阈值重试。**

| 样本 | 日期数 | M0 Brier | M3 Brier | M3−M0 | M0对数损失 | M3对数损失 |
|---|---:|---:|---:|---:|---:|---:|
| 全部重叠窗口 | 331 | 0.248172063 | 0.251373492 | +0.003201429 | 0.689491998 | 0.695941264 |
| 固定原始日期网格 | 66 | 0.250172297 | 0.250411723 | +0.000239427 | 0.693494672 | 0.693962867 |

这不证明市场环境信息永远无用；只表示本次固定定义在已探索的开发资料中未比简单基准表现更好。331个重叠窗口不是331次独立机会，66例也未被认证独立；六折共享扩展训练。未做显著性或盈利声明。

## 本轮究竟检验了什么

唯一输入为399001.SZ的close/MA20−1，MA20含当日与此前19个观察收盘。大于0为均线上方，等于或小于0为另一组；无容差调组。只用这一列，没有扫描其余14个候选。选它的理由在结果前写入合同：深交所研究股票使用深成指作市场背景。

M0概率=(上涨次数+1)/(共同训练数+2)；M3组内概率=(组内上涨次数+20×M0)/(组内次数+20)。空组精确退回M0，训练少于100两者共同弃答。20和100是冻结工程选择，不代表统计样本充分。季度开始前只用标签已成熟的训练资料拟合一次，再冻结评分。两模型同训练池、同评分日期；本轮没有检验M3在M1或M2之上的条件增量。

目标沿用工程示例：信号后第5个观察日收盘/下一观察日开盘−1是否大于0。零变动计非正且单列。331例中正148、零5、负178。该标签不含费用、成交限制、持有期间风险或动作对照，不能等同净盈利概率、卖出成功概率或最佳买点。5日也不是用户已确认的正式持有期限。

## 覆盖与时间隔离

原始开发锚点484个，已有标签469个，原标签排除15个完整保留。六折验证范围366锚点，评分331个；10个无标签、25个结果越过季度边界而剔除。每折训练另有5个尚未成熟标签不使用。选定特征484日齐备，没有因本轮特征缺失再损失日期。

| 折 | 共同成熟训练 | 验证锚点 | 共同评分 | 无标签 | 跨折结果 |
|---|---:|---:|---:|---:|---:|
{fold_lines}

输出662条两模型预测、18条拟合参数、1554条累计训练成员和逐日排除台账。固定网格从全部484原始日期事先建立，不在筛选后重排或挑相位。与旧M1的308日、旧M2的298日不是同一个样本，不能直接用跨轮分数排名。累计研究选择由15增至16，旧结果和准备台账全部保留；重复M0不另计新变体。

本批代码只打开2023—2024目标。2025/2026后期目标继续隔离；原始行情用于核对不代表开放这些结果，也不能把过去看过的年份称为全新测试。沿用行情快照仍截至2026-10-21，没有新行情采集。

## 核验、技术边界与保存

生产实现31项、所选输入独立核查22项、冻结前静态核查14项、模型独立复核47项、严格发布门14项均通过。独立使用Fraction/Decimal重建469标签、484输入及9680条实际依赖，并逐行核对参数、成员、概率、排除、评分、校准、配对误差和11个CSV。完整重跑后16个核心文件逐字节一致；25个保护源哈希未变。

审计发现冻结生产器的独立筛选辅助函数对“等长度重复一折、缺一折”的身份校验不充分。实际结果六折完整，数值不受影响。保留原生产器、合同、登记和结果，另加必须经过的严格发布门：精确核对14个折/子集键、计数、有限指标及所有准入标记；空结果也不能自批准。该门及正反例独立复核通过。本轮没有改模型、参数、来源或筛选标准。复算正确只证明实现对应协议，不能证明预测有效。

已保存代码、冻结合同、登记回执、原始来源引用、11个CSV、SQLite、全部审计、累计台账及续作状态。完整项目和指定外部可视化另做全量归档，旧包保留；归档是否完成以外部[归档校验结果]({ARCHIVE/'归档校验结果.json'})为准。全量保存是已落盘本地资料，不含未取得数据或平台聊天全文导出。

## 仍然没有解决的限制

历史首次可得性与修订、逐日官方ST/停复牌/涨跌停、实际费用与成交尚未认证，所有正式输入和运行门保持false。事件事前已知性和行业历史成员限制继续保留。筹码摘要、自建估计、供应商完整原生价档分别保存；完整原生价档覆盖仍0，不把获利比例当上涨概率或真实机构仓位。无证券账户操作、采购或订单，旧协议和已确认风险口径未改。

用户的条件性1万元试验意向、累计已实现亏损2000元暂停新增买入并复核、浮亏另列继续保留，尚未进入试验阶段。

## 下次从哪里继续

暂停新增模型评分，先完成四份有边界的审查：研究证据与覆盖；预测问题与标签适用性；时间、执行和数据准入缺口矩阵；下一阶段路线决策记录。只使用已保存证据、定义和必要合成例子，不扫描其余14列、不生成新期限真实结果、不打开2025/2026目标。允许审查结论为暂不新增模型，先补证或明确问题。详见[后续研究审查建议](./后续研究审查建议.md)。

续作入口：[本轮状态与续作断点](./本轮状态与续作断点.json)。本批为用户直接请求，不计夜间自动完成次数。
'''
    (OUT/'本轮推进报告.md').write_text(report)
    (OUT/'复算说明.md').write_text('''# 复算与恢复

先恢复整个项目到独立目录，核对登记回执中25个保护源及合同、生产器SHA。保留现有结果作为对照，在恢复副本运行 work/market_model_oct31/run_market_model.py，然后运行 work/market_model_independent_oct31/audit.py 及严格发布门。脚本中的ROOT需按恢复位置检查，不能在原件上批量改路径。生产器仅查询开发期目标；不要扩大SQL日期。

finish_release.py只负责本次发布核验、报告和指针保存，执行会完整重跑冻结生产器；不应在已归档原件上无故重跑。当前16个核心文件的重跑前后哈希见本轮交付核验JSON。重新研究必须另立目录、合同与累计登记，不能覆盖本合同或修改源库。

完整归档在项目外，最终成功以其归档校验结果JSON为准；ZIP内的全文件清单和SHA用于恢复核验。先看本轮状态的next_checkpoint：下一批只做四份研究审查，不新增模型评分。
''')
    ck('state_and_report_saved_and_json_reloadable',read(OUT/'本轮状态与续作断点.json')==state and (OUT/'本轮推进报告.md').stat().st_size>1000)
    backups=WORK/'发布前状态备份';backups.mkdir(exist_ok=True)
    for source in [PROGRESS,POINTER]:
        dest=backups/source.name
        if not dest.exists():shutil.copy2(source,dest)
    progress=PROGRESS.read_text()
    lines=progress.splitlines()
    lines[2]='更新日期：2026年10月31日。人工协作完成单一市场环境M3验证与独立复核；331个共同日期未优于简单M0，累计16变体保留。下一批先审查研究问题、标签与证据，不新增评分，仍在第5步。'
    progress='\n'.join(lines)+'\n'
    marker='## 本轮补充确认与记账口径\n'
    note='\n- 2026/10/31人工续作（第二批）：完成[市场环境候选验证](./市场环境候选验证_20261031/本轮推进报告.md)。先冻结单一深成指MA20状态M3，再在331共同日期/662概率、66固定网格与重新拟合M0比较；Brier0.251373高于0.248172，四项描述性筛选均不通过，不升级不调参。实现31、输入22、静态14、独立47、严格发布14项核验及16核心文件完整重跑一致，25保护源未变；累计16变体全部保留。2025/2026目标隔离、正式准入和运行门仍关。用户随后要求额度前保存全部进度；本批收尾后不再新增研究。下一批只做研究证据、标签适用性、准入缺口和路线决策四份审查，不扫描其余14列。人工工作不计夜间自动完成。\n'
    if '人工续作（第二批）' not in progress:progress=progress.replace(marker,marker+note,1)
    start=progress.index('## 下次协作的起点\n')
    end=progress.find('\n## ',start+5)
    if end<0:end=len(progress)
    new_section='''## 下次协作的起点

以[10/31市场环境候选验证续作断点](./市场环境候选验证_20261031/本轮状态与续作断点.json)为当前入口。M3在331共同日期未优于同日M0，累计16变体及所有否定结果保留。下一批先完成四份有限审查：研究证据与覆盖、预测问题与标签适用性、时间/执行/数据准入缺口、下一阶段路线决策；只引用已有证据和定义，不扫描其余14候选列、不新增评分、不开放2025/2026后期目标。允许先补证或重新明确问题，不承诺必须再跑模型。事件、行业、筹码及正式准入限制继续保留，风险口径不变。最新指针为人工核验断点，夜间自动完成次数仍0。
'''
    PROGRESS.write_text(progress[:start]+new_section+progress[end:])
    pointer=read(POINTER)
    pointer.update(last_verified_research_state='outputs/市场环境候选验证_20261031/本轮状态与续作断点.json',last_verified_research_report='outputs/市场环境候选验证_20261031/本轮推进报告.md',research_stage=5,research_variants_so_far=16,nightly_batches_completed_since_setup=0,next_action=next_steps[0]+'; deliver the four bounded reviews listed in the checkpoint; no new scoring or later-period outcomes',prepared_candidate_definitions=15,prepared_definitions_scored=1,prepared_unscored_candidate_definitions=14,latest_batch_origin='direct_human_request',latest_batch_client_date='2026-10-31')
    write(POINTER,pointer)
    log=ROOT/'outputs/夜间自动推进_20261028/执行日志/20261031_人工协作市场环境候选验证.json'
    write(log,dict(origin='direct_human_request',client_date='2026-10-31',status=state['status'],counts_as_completed_nightly_batch=False,report=pointer['last_verified_research_report'],state=pointer['last_verified_research_state'],new_models_scored=1,cumulative_registered_variants=16,development_screen_passed=False,outcomes_2025_2026_opened=False,user_requested_save_before_token_end=True))
    ck('pointer_resolves_to_saved_verified_state',read(ROOT/read(POINTER)['last_verified_research_state'])==state)
    ck('manual_batch_not_counted_as_night_completion',read(POINTER)['nightly_batches_completed_since_setup']==0 and read(log)['counts_as_completed_nightly_batch'] is False)
    ck('all_25_protected_sources_unchanged_after_release',all(sha(ROOT/p)==v for p,v in protected.items()))
    saved=[OUT/'本轮推进报告.md',OUT/'本轮状态与续作断点.json',OUT/'复算说明.md',OUT/'累计研究与本轮结论台账.json',OUT/'筛选身份与完整性严格复核.json',PROGRESS,POINTER,log]+[OUT/name for source,name in copies]
    ck('all_delivery_files_saved',all(p.is_file() and p.stat().st_size for p in saved))
    release=dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,core_sha256_before_rerun=before,core_sha256_after_rerun=after,saved_delivery_sha256={str(p.relative_to(ROOT)):sha(p) for p in saved},verification_counts=state['verification_counts'],producer_code_sha256=receipt['producer_code_sha256'],contract_sha256=receipt['contract_sha256'],strict_publication_guard_sha256=sha(WORK/'strict_screen_review.py'),phase_promotion_approved=False,outcomes_2025_2026_opened=False)
    write(OUT/'本轮交付核验.json',release)
    print(json.dumps(dict(saved=True,release_checks=str(len(checks))+'/'+str(len(checks)),core_files_identical=len(core),model_independent_checks=audit['passed'],next_checkpoint=next_steps[0],archive_ready=True),ensure_ascii=False))

if __name__=='__main__':main()
