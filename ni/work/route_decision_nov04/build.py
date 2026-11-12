"""Bounded route decision from saved reviews, with no market/target queries."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import hashlib,json,re,shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/下一阶段路线决策_20261104'
WORK=Path(__file__).resolve().parent
START=datetime.fromisoformat('2026-11-04T05:42:27.899369+00:00')
def guard():
 now=datetime.now(ZoneInfo('America/Toronto'))
 if now.hour>=5 or (now.hour==4 and now.minute>=45) or now.astimezone(timezone.utc)>START+timedelta(minutes=40):raise RuntimeError('Outside batch/window; save checkpoint only')
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,x):
 guard();p=Path(p);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n');t.replace(p)
def main():
 guard();OUT.mkdir(parents=True,exist_ok=True)
 olddir=ROOT/'outputs/时间执行与数据准入缺口矩阵_20261102'
 qa=read(olddir/'本轮交付核验.json');matrix=read(olddir/'完整缺口矩阵_v1.json')
 label=read(ROOT/'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json')
 evidence=read(ROOT/'outputs/研究证据与覆盖审查_20261101/16项研究变体完整台账.json')
 sources=dict(qa['protected_source_sha256'])
 for p,h in qa['delivery_sha256'].items():
  if p.startswith('outputs/时间执行与数据准入缺口矩阵_20261102/') or p.startswith('work/gap_matrix_nov02/'):sources[p]=h
 sources[str((olddir/'本轮交付核验.json').relative_to(ROOT))]=sha(olddir/'本轮交付核验.json')
 checks=[]
 def ck(name,ok):checks.append(dict(check=name,passed=bool(ok)));assert ok,name
 ck('previous_release_31_checks',qa['all_checks_passed'] and qa['passed']==qa['total']==31)
 ck('all_saved_sources_unchanged',all(sha(ROOT/p)==h for p,h in sources.items()))
 ck('16_prior_choices_and_36_gaps_retained',evidence['variant_count']==16 and matrix['matrix_row_count']==36)
 ck('15_parameters_still_unfrozen',len(label['pending_freeze'])==15 and all(v is None for v in label['pending_freeze'].values()))
 scope_paths=[
 'work/market_industry_oct22/manifest.json','work/market_industry_oct22/input_admission.json',
 'work/market_context_oct31/contract.json','outputs/统一数据底座_20261022/数据使用与准入规范.json',
 'work/market_warmup_finalize_oct22/manifest.json','work/market_warmup_finalize_oct22/summary.json',
 'outputs/高德红外数据库/calendar_audit_result.json','outputs/高德红外数据库/official_calendar_2023_to_20261015.json',
 'work/conditions_finish_oct22/summary.json','work/conditions_finish_oct22/rule_regimes.json',
 'work/conditions_finish_oct22/daily_trade_conditions_915.json','work/corporate_actions_refine_oct17/corporate_actions.json',
 'work/baseline_oct25/engineering_contract.json','outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json',
 'outputs/时间执行与数据准入缺口矩阵_20261102/来源索引与SHA256.json']
 charter=dict(charter_id='next_bounded_input_evidence_batch_v1',status='engineering_evidence_audit_only_not_model_protocol',symbol='002414.SZ',metadata_period=['2023-01-03','2024-12-31'],field_families=['raw_open','raw_high','raw_low','raw_close','raw_volume'],providers=['eastmoney_primary_saved_snapshot','tencent_comparison_saved_snapshot'],field_family_provider_pairs=10,exchange='SZSE',source_pass_limit=1,local_source_paths=scope_paths,local_source_path_cap=20,
  additional_referenced_evidence_file_cap=5,additional_path_policy='Only paths explicitly referenced by the 15 fixed sources; record path/reason before read, metadata or official evidence only; no provider expansion or price/outcome export; total path cap20',work_minutes_budget=30,verification_and_save_minutes_reserved=10,total_batch_minutes_cap=40,
  deliverables=['机器可读字段/来源/版本/as-of证据台账：10组全部保留，未知有原因','2023—2024深交所计划交易日及状态来源索引：逐日期/来源/认证/未知分开，不输出原价或未来结果','有限证据可恢复性结论：哪些已证实、哪些仍未知、下一步最小取证或前向首收设计'],
  evidence_columns=['field_family','provider','observation_scope','unit_status','source_path','source_sha256','captured_at','historical_first_available_at','revision_available_at','time_precision','evidence_kind','reason_unknown','admission_for_declared_use'],
  acceptance=['全部10组和声明日期均被记账，不因缺证据静默丢行','所有实际引用的本地原件/版本/SHA可定位；路径缺失留缺失，不扩大遍历范围','采集时刻不代替历史公开时刻，保守边界有来源而非统一猜滞后','计划日历不是股票观察日，月报未出现记录不等于逐日正常','所有正式/current/runtime门保持false；技术台账通过不等于PIT或预测通过'],
  stop_conditions=['一个固定本地来源集合扫完或单批约40分钟到达即保存，不重复全面搜同一缺口','原件不存在/时间未知时保留NULL和原因，不补0、不另找赢家来源','若不能恢复历史当时可得证据，下一步先写前向首收采集设计，不能宣称历史PIT补齐','若未在窗口完成则保存部分状态，不记完成批次'],
  required_user_material_now=False,new_network_collection_allowed_in_this_charter=False,new_raw_price_values_or_outcomes_exported=False,new_real_labels_allowed=False,new_models_or_scores_allowed=False,optional_feature_sweep_allowed=False,prior_risk_configuration_mutation_allowed=False)
 options=[
 dict(id='R1',route='现在继续叠加指标或优化旧分组',selected=False,reason='旧三轮未升级，目标仍为方向示例，关键时点/执行证据和15参数未定；继续扫14列会重复开发选择'),
 dict(id='R2',route='先做有边界的必要输入证据工程',selected=True,reason='优先回答买vs等需要哪些可证明输入；从固定旧来源产出可查询台账和日期索引，允许明确证据无法恢复'),
 dict(id='R3',route='立即开前向预测/模拟或新数据大采集',selected=False,reason='尚无冻结的预测协议和准入；可在历史证据不可恢复后先设计首收采集，但那不是预测或60日模拟起点'),
 dict(id='R4',route='扩大股票池、购数或补齐所有可选输入',selected=False,reason='未先定义总体/选择偏差和最小必要范围；渠道/费用未知，预算非采购授权；可选输入不应阻塞底座工程'),
 dict(id='R5',route='完全停止所有项目工作',selected=False,reason='已有可独立完成的证据与工程工作，不需要账户私有资料；无须把当前无升级依据推断为永远无用')]
 decision=dict(decision_id='002414_next_stage_route_20261104_v1',client_date='2026-11-04',basis='Three completed saved reviews only; no fresh market or regulatory assertion',selected_route='R2',options=options,user_confirmed_first_use_case=label['user_confirmed']['first_use_case'],pending_freeze=label['pending_freeze'],cumulative_registered_variants=16,old_failures_retained=True,
  gap_focus=['T01','T02','T03','D01','X01','X02','X03','D02','P01','P02','P03','P05'],
  admission_stages=['先完成下一批证据台账工程，未知诚实保留','另核选定字段的历史可用性或提出有边界的前向首收方案','明确并冻结买vs等的时间/分配/确认/费用/NAV或清算及风险口径','若仍有合理单一假设，再另行预登记新候选、共同基准、覆盖、验收和累计选择','后期目标阶段及前向模拟另立协议；不能因四份审查完成自动开放'],
  new_data_gaps_closed=0,new_real_labels=0,new_models_fitted=0,new_scores_calculated=0,model_input_approved=False,runtime_usable=False,current_forecast_generated=False,outcomes_2025_2026_opened=False,real_funds_authorized=False,prospective_forecast_started=False)
 write(OUT/'路线选择与准入门.json',decision);write(OUT/'下一批有限工程任务书.json',charter)
 source_inventory={p:dict(exists=(ROOT/p).is_file(),sha256=sha(ROOT/p) if (ROOT/p).is_file() else None) for p in scope_paths}
 write(OUT/'任务书来源存在性预检.json',dict(scope='Only file existence and fingerprints checked; contents not extracted into an evidence ledger this round',sources=source_inventory))
 ck('one_route_selected_no_market_admission',sum(o['selected'] for o in options)==1 and decision['selected_route']=='R2' and not decision['model_input_approved'])
 ck('finite_next_batch_10_pairs_15_paths_below_20_cap',len(charter['field_families'])*len(charter['providers'])==10 and len(scope_paths)==15<=charter['local_source_path_cap'])
 ck('no_new_labels_models_scores_or_later_targets',decision['new_real_labels']==decision['new_models_fitted']==decision['new_scores_calculated']==0 and not decision['outcomes_2025_2026_opened'])
 report='''# 下一阶段路线决策记录 v1

2026年11月4日，多伦多。依据已经独立核验的三份审查，完成第四份路线决策。本轮只作研究路线选择和下一批有限任务书，不新增市场数据、真实标签、模型、评分或当前买卖预测。

## 决定

当前采用 **R2：先做有边界的必要输入证据工程**。下一批应交付可查询的字段时点/版本台账和计划日历、状态来源索引，先确认现有资料究竟能证明什么。暂不再叠指标或重调旧分组，也不要求把所有筹码、行业与新闻资料先补全。

这不是把项目停在文档阶段：下一批必须将固定来源逐项落入机器可读台账，给出每组已证、未证、缺件和理由。一个固定来源集合检查完就作可恢复性结论；不能一轮轮重复全面搜同一个历史时间缺口。

## 为什么这样决定

1. 16项包括12个描述性信号和M0/M1/M2/M3四模型定义。M1、M2、M3在各自同日对照未取得升级依据；不能用技术核验或个别季度替代预测证据，也不能把全部这些信息宣判永远无用。
2. 用户确认的是“收盘后判断回落时该买入还是继续等待”。旧五观察日原价方向不是这两种动作的费用后财富比较。共同资金、共同终点、未触发/未成交、NAV与变现、权益/负债必须明确。
3. 第三份矩阵列36项缺口，但整理完成没有关闭数据缺口。历史首次可得、修订、日历/状态、费用和成交仍未完成正式准入；15组参数仍NULL。

依据：[研究证据审查](../研究证据与覆盖审查_20261101/研究证据与覆盖审查_v1.md)、[预测问题与标签审查](../预测问题与标签适用性审查_20261101/预测问题与标签适用性审查_v1.md)、[36项缺口矩阵](../时间执行与数据准入缺口矩阵_20261102/时间执行与数据准入缺口矩阵_v1.md)。这是从已保存证据作出的工程路线判断，不是新的市场预测或个股买卖建议。

## 比较过的路线

|路线|当前决定|理由|
|---|---|---|
|R1 继续叠指标/优化旧组|不选|目标和证据前提未定，不能把剩余14列逐个扫到出现赢家|
|R2 有限必要输入证据工程|选定|可独立产出实际台账、暴露无法恢复的历史证据，直接服务买vs等问题|
|R3 立即前向预测/模拟/大采集|不选|协议和准入未完成；首收数据设计是有条件后续方案，不是预测上线|
|R4 扩股票池或购买全量可选数据|不选|先限定必要范围；不按已知走势扩样，预算不是采购授权|
|R5 停止所有工作|不选|仍有不依赖用户账户资料的工程可推进，无须盲试或无期限等待|

## 下一批具体做什么

固定研究标识002414.SZ、仅2023—2024已存元数据。对原始O/H/L/C/成交量五字段族、东方财富主源及腾讯比较源两类，共10组建立来源/单位/版本/采集/历史首次可得/修订与未知原因台账。选这些字段是底座证据检查范围，不是新模型白名单、指标或用户期限确认。

同时建立深交所计划日及状态来源索引，声明范围内每个日期都记已证、未证或未知。日历不从后来出现的个股K线倒推；月报未查到不能当逐日正常；新行情不会自动补齐日历、状态、限价或费用。状态索引是来源/认证索引，不是补造官方状态。

本批只预检任务书15个固定本地来源路径及指纹，未将其内容抽成下一批台账；缺件预检如实记录，不在本轮临时换源扩范围。下一批以这15件为固定入口，最多另查5件由固定入口明确引用的元数据或官方证据；新增路径和理由须在读取前登记，总上限20件，不扩供应商。只过一遍，优先用已存原件和JSON；不联网新增数据、不解读真实结果表、不导出原始价格数值、不读取2025/2026目标，不运行模型。

交付三件可恢复成果：①10组字段证据台账；②计划日/状态来源日期索引；③有限历史证据可恢复性结论。每条引用都需源路径与SHA，所有组和日期均有去向；未知为NULL并写理由，不能删掉难做日期来制造完整覆盖。

## 做到哪里算完成、何时停止

技术台账完成须组别和日期记账齐、源文件与哈希可追溯、时间精度及缺失原因明确、无采集时刻替代历史公开/接收时刻。工程检查通过不认证历史PIT、执行或预测能力。用途依赖不是采集先后，账户费率未知不妨碍公共底座工程。

一个固定本地来源集合扫完、单批约40分钟或夜间窗口临近即保存；安排至多30分钟工作并明确预留至少10分钟核验/保存。不做密集重试、换供应商找好结果或循环全面查同一缺口。未完成部分有明确断点，不能记成完成。

如果检查后仍没有历史首次可得证据，结论允许是“旧资料只支持原有受限工程研究，历史PIT不可认证”。随后优先写前向首收日志和质量拒绝的有限采集设计，记录真实接收/版本，不反向证明2023年可见。该设计或采集本身不启动预测、模拟，也不算60个前向模拟交易日；模型及规则未验收，观察期不能偷跑。

## 进入新概率研究仍要经过什么

先有选定输入的用途证据，再明确并冻结买vs等的回落/确认、H及等待期限、截止/执行、共同终点、分配、费用/权益、风险与目标资格。新候选须有与旧尝试实质不同且有依据的单一假设，先登记共同样本、基准、指标、排除和验收，再计算；合理结论也可为暂不新增候选。不能以受限成本/成交场景冒充实际净收益。

2025/2026后期目标继续隔离，过去看过的年份不能重新称为全新独立测试；后期评估需另立协议。单股扩样要另定总体、选股时点与成员变更，不能挑成功股票。15组参数、原草案、风险口径及旧代码不改，累计16不重置。

## 分工及保存

助手负责下一批台账代码、固定来源映射、质量核对及可恢复保存。用户当前无需材料、账户操作、联系他人或购买服务；后续使用期限/风险偏好及精确账户净结果才按既有脱敏模板核最小信息。1万元试验意向、2000元累计已实现亏损暂停新增买入并复核、浮亏另列不变，未授权使用资金。

本轮四份审查已形成一条可执行工程路线，研究仍在原八步的第5步，预测和正式应用验收未通过。当前这份路线决策完成不表示下一批台账、36项补缺或新模型已经完成。

[路线选择与准入门](./路线选择与准入门.json) · [下一批有限工程任务书](./下一批有限工程任务书.json) · [来源存在性预检](./任务书来源存在性预检.json) · [续作断点](./本轮状态与续作断点.json)。完整保存成功以项目外20261104_路线决策完整保存/归档校验结果.json为准。
'''
 guard();(OUT/'下一阶段路线决策记录_v1.md').write_text(report)
 write(OUT/'旧来源保护清单.json',dict(sha256=sources))
 write(OUT/'本轮构建核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,protected_source_sha256=sources))
 summary=dict(review_steps_completed=3,review_steps_remaining=1,selected_route='bounded_input_evidence_first',cumulative_registered_variants=16,newly_closed_data_gaps=0,new_real_market_targets=0,new_model_variants=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,phase_promotion_approved=False,next_engineering_field_provider_pairs=10,next_source_path_count=15)
 write(OUT/'本轮状态与续作断点.json',dict(client_date='2026-11-04',origin='scheduled_heartbeat_a_with_human_status_query',research_stage=5,status='route_built_pending_independent_audit',review_package_step=4,review_package_step_completed=False,archive_summary=summary,pending_freeze=label['pending_freeze'],cumulative_registered_variants=16,new_models_fitted=0,new_scores_calculated=0,new_real_market_targets=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,old_protocol_or_risk_modified=False,source_hashes=sources,counts_as_completed_nightly_batch=False,next_checkpoint=['Implement only the finite local-input evidence charter: 10 OHLCV/provider families plus 2023-2024 SZSE planned-calendar/status-source index; no actual target/price-value export or scoring','After one fixed local-source pass, preserve unknown and make a recoverability decision; if PIT cannot be restored, design prospective first-receipt collection rather than retrying the same broad search','Do not sweep 14 remaining feature columns or open 2025/2026 targets; no model/forecast/simulation/funds use before separate protocol and acceptance']))
 print(json.dumps(dict(built=True,checks=len(checks),protected_sources=len(sources),source_precheck_missing=[p for p,v in source_inventory.items() if not v['exists']]),ensure_ascii=False))

if __name__=='__main__':main()
