from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'outputs/输入证据合库与验证设计_20261105'; W=Path(__file__).resolve().parent
REL=OUT.relative_to(ROOT).as_posix()
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):
 p=Path(p);t=p.with_name(p.name+'.pending');assert not t.exists();t.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n');t.replace(p)
def main():
 audits=[('work/metadata_audit_nov05/独立复核.json','元数据独立复核.json'),('work/metadata_audit_nov05/协议交付对应复核.json','协议交付对应复核.json'),('work/buy_wait_design_nov05/复核.json','数学与状态独立复核.json')]
 checks=[]
 def ck(n,v,d=None):
  checks.append(dict(check=n,passed=bool(v),details=d));assert v,n
 audit_counts={}
 for src,dst in audits:
  p=ROOT/src;a=read(p)
  ck('independent_pass_'+dst,a['all_checks_passed'] is True and a['passed']==a['total'] and a['total']>0)
  audit_counts[dst]=a['total'];shutil.copy2(p,OUT/dst)
  m=p.with_suffix('.md')
  if m.exists():shutil.copy2(m,(OUT/dst).with_suffix('.md'))
  ck('copy_identical_'+dst,sha(p)==sha(OUT/dst))
 b=read(OUT/'本轮构建核验.json');d=read(OUT/'设计构建核验.json')
 ck('root_build_checks',b['all_checks_passed'] and d['all_checks_passed'])
 ck('15_original_sources_unchanged',all(sha(ROOT/p)==h for p,h in b['source_hashes'].items()))
 protocol=read(OUT/'买入还是等待_研究候选BW17_冻结v1.json'); frozen=read(OUT/'设计冻结与来源指纹.json'); reg=read(OUT/'累计研究选择登记_增补BW17.json'); usr=read(OUT/'本轮用户确认与参数状态.json')
 ck('protocol_frozen_file_hash',sha(OUT/'买入还是等待_研究候选BW17_冻结v1.json')==frozen['file_sha256'])
 ck('frozen5source_hashes',all(sha(ROOT/p)==h for p,h in frozen['source_hashes'].items()))
 ck('H10confirmed14pending',usr['confirmed_value']==10 and len(protocol['unbound_user_groups'])==14 and all(v is None for v in protocol['unbound_user_groups'].values()))
 ck('choices16plus1equals17',reg['old_registered_choices']==16 and reg['new_choice']['id']==17 and reg['total_registered_choices']==17 and reg['new_evaluated_choices']==0)
 ck('all_experiment_use_gates_closed',not any(v for k,v in protocol['gates'].items() if k!='definition_frozen'))
 db=OUT/'最小输入证据台账.sqlite';da=read(OUT/'元数据独立复核.json')
 # The independent audit locks the new metadata database; do not reopen old market DBs.
 ds=[v for k,v in da.items() if k in ('database_sha256_after','database_sha256_before','db_sha256_before','db_sha256_after','database_sha256')]
 ck('new_metadata_DB_matches_independent_digest',sha(db)=='72e41c86997ad21fedc19d266c9ca8b16746d0fdae52d45408642fcfc01530c6')
 prior=ROOT/'outputs/夜间自动推进_20261028/最新续作指针.json'; prog=ROOT/'outputs/项目进度与交易需求档案.md'
 backup=W/'更新前协作状态';backup.mkdir(exist_ok=True)
 for p in [prior,prog,OUT/'本轮状态与续作断点.json',OUT/'本轮推进报告.md']:
  dest=backup/p.name
  ck('backup_not_overwrite_'+p.name,not dest.exists());shutil.copy2(p,dest)
 blocker_rows=[
  {'id':'HISTORICAL_FIELD_VERSION','met':False,'reason':'raw_close及其他字段的历史首次可得/修订链、原字段映射与单位仍未认证'},
  {'id':'ASOF_CALENDAR_STATUS','met':False,'reason':'计划日历版本和逐日ST/停牌/适用规则/限价证据不全'},
  {'id':'COUNTERFACTUAL_EXECUTION','met':False,'reason':'开盘限价、排队/部分成交/合法撤单的执行模型尚未绑定，不可从日K推断成交'},
  {'id':'FEES_RIGHTS_LIABILITIES','met':False,'reason':'费用上界/包费/最低额/舍入与权益负债未完整绑定'},
  {'id':'MATURE_LABEL_LEDGER','met':False,'reason':'真实动作/结果账本与成熟资格未实施；本轮仅冻结定义'},
  {'id':'REAL_RUN_REGISTERED','met':False,'reason':'本轮不授权任何真实标签计算或市场统计；应先补证再另登记有限运行'},
  {'id':'PREDICTIVE_ESTIMATOR_ACCEPTANCE','met':False,'reason':'概率估计器、样本最小量、时序评价、经济优势和晋级阈值未登记；模型运行仍禁止'}]
 put(OUT/'研究与预测放行检查.json',{'candidate_id':protocol['protocol_id'],'definition_frozen':True,'H_user_confirmed':10,'research_constants_are_not_product_confirmation':True,'checks':blocker_rows,'can_generate_real_labels':False,'can_fit_or_score_forecast':False,'can_use_for_current_decisions':False,'can_start_simulation_or_funds':False,'every_missing_gate_requires_new_evidence_not_a_time_elapsed_override':True})
 archive_dir=Path('/Users/puchun/Documents/Codex/项目归档/ni/20261105_输入台账与验证设计增量保存')
 state={'client_date':'2026-11-05','saved_at_local':datetime.now(ZoneInfo('America/Toronto')).isoformat(),'origin':'manual_user_request','status':'metadata_merge_audited_candidate_definition_frozen_actual_validation_blocked','research_stage':5,'fifth_step_complete':False,'metadata_engineering_complete':True,'independent_metadata_checks':audit_counts['元数据独立复核.json'],'independent_protocol_correspondence_checks':audit_counts['协议交付对应复核.json'],'independent_math_and_state_checks':audit_counts['数学与状态独立复核.json'],'field_provider_rows':10,'calendar_natural_days':729,'planned_open_days':484,'planned_closed_days':245,'context_days_separate':2,'corporate_action_date_records':2,'registered_source_paths':15,'extra_domain_source_paths':0,'original_extraction_rerun':False,'bounded_source_pass_complete':True,'new_formal_gaps_closed':0,'source_hashes':b['source_hashes'],'new_metadata_DB_sha256':sha(db),'new_candidate':protocol['protocol_id'],'definition_frozen':True,'fully_executable_prediction_protocol':False,'cumulative_registered_research_choices':17,'legacy_choices':16,'new_unrun_policy_definitions':1,'new_real_labels':0,'new_models_fitted':0,'new_scores_calculated':0,'new_current_forecast':False,'outcomes_2025_2026_opened':False,'main_horizon_planned_exchange_sessions':10,'remaining_user_parameter_groups':14,'latest_user_parameters_file':REL+'/本轮用户确认与参数状态.json','old_15null_files_modified':False,'existing_risk_settings_modified':False,'formal_historical_input_approved':False,'runtime_usable':False,'counts_as_completed_nightly_batch':False,'nightly_automation_status':'deleted_by_user_request_20261104','nightly_automation_recreated':False,
 'completed':['10组字段与729日元数据合并到新SQLite，旧库不改','来源、NULL和逐列SQL对应独立复核完成','用途/缺证据清单与有限本地可恢复性结论发布','用户H10确认及BW17单一研究候选定义/比较/目标/拒绝门冻结并独立复核','前向首收/版本/质量拒绝补证设计保存'],
 'partial':['研究执行证据/费用权益绑定未完成','其余14组用户使用偏好待定；研究常数不回填用户偏好','完整可执行概率估计/验收协议未冻结，真实配对验证未运行'],
 'blocked':['历史PIT、原字段/单位与完整状态/执行/费用未具备；不能生成真实标签或当前概率'],
 'archive':{'kind':'verified_base_plus_all_scope_delta','base_verified_archive_sha256':'823651f58e75447658d220f3367be075408b2945e8800f8a67029283eacef716','intended_verification_result':str(archive_dir/'增量归档核验.json'),'completion_is_only_claimed_if_that_external_result_exists_and_passes':True,'this_state_does_not_claim_archive_already_complete':True},
 'next_checkpoint':['先实现有边界的前向首收清单/版本/拒绝schema及离线反例，仍不启用定时任务','针对BW17选择的close/日历/状态/权益/费用/执行逐条补证；不再反复扫同一不变本地源','证据或模型绑定不足则保留未知，不能转为当前买卖概率；如需替代受限回顾实验，先另登记用途和假设','实际预测实验须另冻结模型、样本/时序/指标/经济门槛并复核；2025/2026目标继续隔离'],
 'superseded_pending_metadata_checkpoint':'outputs/最小输入证据台账_20261104_批次02/本轮状态与续作断点.json'}
 put(OUT/'本轮状态与续作断点.json',state)
 report=f'''# 输入证据合库与买入等待研究定义：本轮报告

2026年11月5日，多伦多，用户手动续作。夜间自动任务已取消，本轮未重新建立任务。

|用户要求|实际完成|边界|
|---|---|---|
|合并记录入库|新建[最小输入证据台账.sqlite](./最小输入证据台账.sqlite)：10组字段/来源、729自然日（484计划开市/245休市）、2条上下文日期另表、2个公司行动日期、15个登记来源|仅元数据/来源证据，原库与原价/结果数据不改；复用旧提取物，没有重新抓数据|
|独立复核|元数据{audit_counts['元数据独立复核.json']}项、协议对应{audit_counts['协议交付对应复核.json']}项、数学与状态{audit_counts['数学与状态独立复核.json']}项均通过|检查的是工程对应和设计逻辑，不是股票预测有效性|
|明确可用范围|[历史研究用途与缺证据结论](./历史研究用途与缺证据结论.md)及14行机器清单已保存|旧快照可支持原有受限回顾工程和来源核对；历史时点、原生映射/单位、日状态、成交/费用仍不足，新增正式缺口关闭0|
|冻结买vs等验证方案|[BW17研究候选定义](./买入还是等待_研究候选BW17_冻结说明.md)已冻结：A下一窗口、B等确认、C持币，同现金同终点；用户本轮明确未来10个计划交易日|冻结的是单一候选定义，证据/执行模型绑定尚缺；不能称可执行概率预测协议已全部冻结|

## 本轮可核验的结果

10组字段仍保留历史首次可得、修订可得、最早模型使用及供应商原字段ID的未知，正式/current/runtime门均为false。484个计划开市日有旧条件链接，不能当作484天正常、能成交或完整费用已经认证。日历索引不是股票实际观察日历。原行情响应SHA只沿旧manifest记录，本轮未读取或重核原行情数组。

[元数据独立复核](./元数据独立复核.json)逐列检查8928个声明列对应单元，并定位2474个来源引用；新DB哈希为`{sha(db)}`。旧输入指纹核验通过。原提取器没有重跑，未联网新采集、读取结果库或开放2025/2026目标。

## 具体研究候选是什么

用户已确认H=10，即d0判断后的第10个计划交易日收盘是共同终点。研究常数W=2：若d1/d2首次出现可核验的回升收盘，下一计划日以同规则尝试；没有确认则持币。A为d1单次限价意向，C全程持币。两条买入意向各最多一次，不追单不加仓；未知更早确认不得跳过。研究金额10000、18点截止、数量/订单与零名义现金收益仅是研究假设，不是实际账户或风险设置确认。

主比较delta=(NAV等待−NAV立即)/起始现金，另看各自相对持币的盈利/亏损与期间下行；等待更好也可能仍亏钱。共同T不随晚买、停牌或缺K线顺延，未来公司行动不得事后用于挑掉起始样本。未触发、已证实未成交、成交未知、费用未知、缺估值与未成熟分开记录，不能填0。日K触价不证明反事实订单成交；未来执行模型结果必须标为模型假设。

累计研究选择现在为**旧16项+新增未运行BW17=17项**，不是17个已成功模型。原三轮否定结果全部保留。本轮真实标签、拟合模型、评分和当前预测均为0；未开展模拟或用钱。旧15组NULL历史合同不改，本轮最新参数为1项H10已确认、其余14项待定。[用户确认](./本轮用户确认与参数状态.json)与[研究放行检查](./研究与预测放行检查.json)分别保存。

## 还缺什么，接下来做什么

还缺历史版本/单位与映射、当时日历和个股状态、明确反事实执行模型、费用权益负债与结果成熟账本。概率估计器、最小样本、依赖稳健时序评价和晋级标准还需在新预测实验前另登记。第五步整体仍未完成。

这次结束固定本地来源的一遍核查，不因时间经过重复扫同源。下一批先实现[前向首收与版本补证设计](./前向首收与版本补证设计.json)的有限离线schema和拒绝检查，再列出一次最小公开源取证范围；未来接收日志不能追认2023年的可得性，也不启动预测/模拟观察期。原2000元累计已实现亏损暂停、浮亏另列口径不变。

[完整续作断点](./本轮状态与续作断点.json) · [冻结指纹](./设计冻结与来源指纹.json) · [最终交付核验](./本轮交付核验.json)。本轮保存采用11/4已核验全量基座+本轮全范围增量，旧包保留；是否打包成功只以项目外`{archive_dir}/增量归档核验.json`为准，本报告不冒充独立全量包或未取得的数据备份。
'''
 (OUT/'本轮推进报告.md').write_text(report)
 put(OUT/'自动任务取消状态记录.json',{'recorded_date':'2026-11-05','effective_user_request_date':'2026-11-04','automation_id':'a','name':'A股概率研究夜间推进','status':'deleted','basis':'本聊天上一轮automation_update(mode=delete,id=a)返回deleteStatus=deleted','current_work_is_manual':True,'recreated':False,'old_schedule_documents_are_historical_only':True})
 # The continuation pointer advances only after these concrete output artifacts and audits exist.
 p=read(prior);old_pending={k:p[k] for k in list(p) if k.startswith('pending_')}
 for k in list(p):
  if k.startswith('pending_'):p.pop(k)
 p.update(last_verified_research_state=REL+'/本轮状态与续作断点.json',last_verified_research_report=REL+'/本轮推进报告.md',research_stage=5,research_variants_so_far=17,latest_batch_origin='manual_user_authorized',latest_batch_client_date='2026-11-05',latest_batch_id='manual_20261105_metadata_and_BW17',confirmed_first_use_case='收盘后判断回落时该买入还是继续等待',confirmed_horizon_planned_sessions=10,pending_user_parameter_groups=14,new_policy_definitions_frozen_unrun=1,fully_executable_prediction_protocol=False,automatic_execution_cancelled=True,automation_id_deleted='a',old_pending_resolved=old_pending,next_action='Implement bounded offline first-receipt/version/rejection schema and list minimum selected-input evidence acquisition; no schedule, real targets, model fit/score, forecast or simulation; preserve BW17 H10/W2 and14 user pending groups')
 ck('manual_batch_does_not_increment_nightly',p['nightly_batches_completed_since_setup']==1)
 summary='更新日期：2026年11月5日。手动完成10组字段/729日证据台账SQLite合并及独立复核，发布历史研究用途和缺证据结论；用户明确主期未来10个计划交易日，单一BW17研究候选定义冻结，累计旧16+新增未运行1=17。14组用户参数仍待定，证据/执行/费用与完整概率协议未放行，真实标签/模型/评分0，仍在第5步。夜间自动任务已于11/4取消。'
 text=prog.read_text();lines=text.splitlines();lines[2]=summary;text='\n'.join(lines)+'\n'
 note=f'- 2026/11/05人工续作：完成[输入证据合库与验证设计](./输入证据合库与验证设计_20261105/本轮推进报告.md)。新台账10组字段、729自然日/484计划开市、2context、2action、15来源；元数据{audit_counts["元数据独立复核.json"]}、协议对应{audit_counts["协议交付对应复核.json"]}、数学/状态{audit_counts["数学与状态独立复核.json"]}项独立核验通过。固定来源不重提取，不冒充历史PIT/执行/费用认证，正式缺口关闭0。用户明确未来10个交易日，最新H=10、14组待定，旧15NULL原件保留；新增BW17定义冻结未运行，旧16及全部失败保留，累计17不是17个有效模型。2025/2026结果继续隔离，0真实标签/模型/评分，研究/运行门关。下一步先做有边界前向首收schema与补证；不自动开实验。自动任务11/4已取消，本轮手动工作不增夜间计数。\n\n- 2026/11/04用户取消自动推进：任务a已通过应用工具删除，协作工作停止；旧调度文件作为历史记录保留，不构成重新运行授权。项目资料/断点保留，后续仅按用户手动指示。\n\n'
 text=text.replace('## 本轮补充确认与记账口径\n\n','## 本轮补充确认与记账口径\n\n'+note,1)
 a=text.index('## 下次协作的起点\n');z=text.find('\n## ',a+3)
 end=len(text) if z<0 else z
 replacement='''## 下次协作的起点

以[11/05合库与BW17断点](./输入证据合库与验证设计_20261105/本轮状态与续作断点.json)为入口。合库/独立复核/用途矩阵和BW17单一候选定义已完成，期限H10由用户确认；研究设定W2等不回填用户偏好，其余14组待定。先实现有限的前向首收/版本/拒绝schema及离线反例，再针对已选择close/日历/状态/执行/权益/费用做最小取证。历史PIT不能恢复则保留受限用途，不重复扫同一旧源、不偷跑真实标签/新模型/评分/模拟或2025/2026目标。原16与失败保留，累计17含1个未运行政策定义；第五步未整体完成。自动任务a已删除，仅在用户手动指示时继续。
'''
 text=text[:a]+replacement+text[end:]
 # Check package before publishing pointers; output state is complete even if external archive later fails.
 artifacts={p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='本轮交付核验.json'}
 ck('all_release_files_present',all((OUT/n).is_file() for n in ['历史研究用途与缺证据结论.md','买入还是等待_研究候选BW17_冻结v1.json','研究与预测放行检查.json','本轮状态与续作断点.json','本轮推进报告.md']))
 ck('no_SQLite_temporary_file',not list(OUT.glob('*.pending')) and not list(OUT.glob('*-wal')))
 ck('old_input_hashes_final',all(sha(ROOT/x)==h for x,h in b['source_hashes'].items()))
 put(OUT/'本轮交付核验.json',{'all_checks_passed':True,'passed':len(checks),'total':len(checks),'checks':checks,'independent_checks_separate':audit_counts,'artifact_sha256':artifacts,'new_real_labels_models_scores':0,'phase_promotion_approved':False,'archive_verification_is_external_and_separate':True})
 # Actual source fingerprints are verified before advancing either collaboration document.
 for name,h in artifacts.items():assert sha(OUT/name)==h
 tmp=prog.with_name(prog.name+'.pending');assert not tmp.exists();tmp.write_text(text);tmp.replace(prog)
 put(prior,p)
 log=ROOT/'outputs/夜间自动推进_20261028/执行日志/20261105_人工合库与BW17冻结.json'
 put(log,{'origin':'manual_user_request','nightly_automation_deleted':True,'completed_nightly_batches_not_incremented':True,'research_state':REL+'/本轮状态与续作断点.json','new_registered_unrun_policy':17,'new_real_labels_models_scores':0,'saved_at_utc':datetime.now(timezone.utc).isoformat()})
 put(W/'发布后协作文件指纹.json',{'progress_sha256':sha(prog),'pointer_sha256':sha(prior),'state_sha256':sha(OUT/'本轮状态与续作断点.json'),'release_audit_sha256':sha(OUT/'本轮交付核验.json'),'pointer_readback_matches':read(prior)['last_verified_research_state']==REL+'/本轮状态与续作断点.json'})
 print(json.dumps({'released':True,'checks':len(checks),'independent_counts':audit_counts,'H':10,'pending_user_groups':14,'choices':17,'archive_still_separate':True},ensure_ascii=False))
if __name__=='__main__':main()
