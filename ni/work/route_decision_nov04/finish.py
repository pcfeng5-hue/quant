"""Publish an independently reviewed route; no new experiments or sources."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import hashlib,json,re,shutil

ROOT=Path(__file__).resolve().parents[2];WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/下一阶段路线决策_20261104'
START=datetime.fromisoformat('2026-11-04T05:42:27.899369+00:00')
def guard():
 n=datetime.now(ZoneInfo('America/Toronto'))
 if n.hour>=5 or (n.hour==4 and n.minute>=45) or n.astimezone(timezone.utc)>START+timedelta(minutes=40):raise RuntimeError('Window/batch limit: save unfinished state only')
 return n
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj):
 guard();p=Path(p);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n');t.replace(p)
def main():
 now=guard();checks=[]
 def ck(name,ok):checks.append(dict(check=name,passed=bool(ok)));assert ok,name
 build=read(OUT/'本轮构建核验.json');auditdir=ROOT/'work/route_review_nov04';audit=read(auditdir/'独立复核.json')
 ck('build_7_checks_passed',build['all_checks_passed'] and build['passed']==build['total']==7)
 ck('independent_audit_passed',audit['all_checks_passed'] and audit['passed']==audit['total'] and all(x['passed'] for x in audit['checks']))
 for p,h in audit.get('delivery_sha256',{}).items():
  path=Path(p) if p.startswith('/') else ROOT/p
  if not path.exists():path=OUT/p
  ck('independent_fingerprint_'+p,path.is_file() and sha(path)==h)
 for ext in ['json','md']:shutil.copy2(auditdir/f'独立复核.{ext}',OUT/f'独立复核.{ext}')
 decision=read(OUT/'路线选择与准入门.json');charter=read(OUT/'下一批有限工程任务书.json');state=read(OUT/'本轮状态与续作断点.json')
 ck('222_protected_sources_unchanged',len(build['protected_source_sha256'])==222 and all(sha(ROOT/p)==h for p,h in build['protected_source_sha256'].items()))
 ck('only_R2_selected',decision['selected_route']=='R2' and [r['id'] for r in decision['options'] if r['selected']]==['R2'])
 ck('no_new_market_or_predictive_approval',decision['new_data_gaps_closed']==decision['new_real_labels']==decision['new_models_fitted']==decision['new_scores_calculated']==0 and not any(decision[k] for k in ['model_input_approved','runtime_usable','current_forecast_generated','outcomes_2025_2026_opened','real_funds_authorized','prospective_forecast_started']))
 ck('15_pending_groups_NULL',len(decision['pending_freeze'])==15 and all(v is None for v in decision['pending_freeze'].values()))
 ck('finite_charter_not_an_experiment',charter['field_family_provider_pairs']==10 and len(charter['local_source_paths'])==15 and charter['source_pass_limit']==1 and not any(charter[k] for k in ['new_network_collection_allowed_in_this_charter','new_real_labels_allowed','new_models_or_scores_allowed','optional_feature_sweep_allowed']))
 report=OUT/'下一阶段路线决策记录_v1.md'
 ck('all_report_artifact_links_resolve',all((OUT/link).exists() for link in re.findall(r'\]\((\.{1,2}/[^)]+)\)',report.read_text())))
 state.update(status='fourth_route_review_complete_independently_checked',review_package_step_completed=True,saved_at_utc=now.astimezone(timezone.utc).isoformat(),counts_as_completed_nightly_batch=True,completed=['All four bounded reviews complete; R2 evidence-first route selected','Fixed next-batch charter, source existence/hash precheck and independent audit saved'],partial=['Next batch field/as-of ledger and planned-calendar/status index not yet implemented','36 data gaps and15-group parameter freeze remain; no new model or formal admission','Full archive is a separate final operation, confirmed by its external verification result'],blocked=['Formal historical input/execution/cost evidence and predictive acceptance remain unfulfilled'],independent_checks=dict(passed=audit['passed'],total=audit['total']))
 state['archive_summary'].update(review_steps_completed=4,review_steps_remaining=0)
 write(OUT/'本轮状态与续作断点.json',state)
 progress=ROOT/'outputs/项目进度与交易需求档案.md';folder=ROOT/'outputs/夜间自动推进_20261028';pointer=folder/'最新续作指针.json'
 backup=WORK/'发布前状态备份';backup.mkdir(exist_ok=True)
 for p in [progress,pointer,folder/'夜间调度健康状态.json']:
  if p.exists() and not (backup/p.name).exists():shutil.copy2(p,backup/p.name)
 text=progress.read_text();lines=text.splitlines();lines[2]='更新日期：2026年11月4日。夜间完成第4份路线决策并独立核验，四份有限审查已齐；选择先做固定范围输入时点/版本证据工程，下一批10组OHLCV/来源台账和深交所日历/状态来源索引。不新增模型、真实标签或评分，累计16和正式准入限制不变，仍在第5步。';text='\n'.join(lines)+'\n'
 note='\n- 2026/11/04夜间第1个完成批次：完成[下一阶段路线决策](./下一阶段路线决策_20261104/下一阶段路线决策记录_v1.md)，四份有限审查齐备。采用有边界的必要输入证据工程，不立即叠指标/开预测/扩股池或购数。下一批只核2023—2024五个原始字段族×两已有来源10组，并建深交所计划日/状态来源索引；15固定本地路径只过一遍，未知保留，历史PIT不能恢复则转前向首收设计，不反向认证或偷跑模拟观察期。源指纹及独立审查通过，15参数仍NULL、16旧变体及失败保留、2025/2026结果隔离；本批0新增数据缺口关闭/真实标签/模型/评分。用户中途询问状态，未改变本批自动来源或参数。\n'
 marker='## 本轮补充确认与记账口径\n'
 if '2026/11/04夜间第1个完成批次' not in text:text=text.replace(marker,marker+note,1)
 start=text.index('## 下次协作的起点\n');end=text.find('\n## ',start+5)
 if end<0:end=len(text)
 section='''## 下次协作的起点

以[11/04路线决策断点](./下一阶段路线决策_20261104/本轮状态与续作断点.json)为入口。四份审查已完成，路线R2：先实现固定范围输入证据台账及深交所计划日/状态来源索引，任务细则见同目录下一批有限工程任务书.json。下一批仅2023—2024、五字段族×两保存来源10组、15固定本地路径只过一遍，不读结果表、不导出原价值、不联网新采集、不跑模型或扫描14列。未知和缺件完整保留，历史可得性不能恢复则结束有限搜寻并先设计前向首收，不把采集算预测/模拟开始。累计16、15组参数NULL、全部失败和原风险口径/后期隔离不变。实际夜间已完成1批，此次数量不代表研究或预测验收。
'''
 guard();progress.write_text(text[:start]+section+text[end:])
 ptr=read(pointer);batch_id='a_20261104_route_decision_v1'
 oldcount=ptr.get('nightly_batches_completed_since_setup',0)
 count=oldcount if ptr.get('latest_batch_id')==batch_id else oldcount+1
 ptr.update(last_verified_research_state='outputs/下一阶段路线决策_20261104/本轮状态与续作断点.json',last_verified_research_report='outputs/下一阶段路线决策_20261104/下一阶段路线决策记录_v1.md',review_package_steps_completed=4,review_package_steps_remaining=0,research_variants_so_far=16,research_stage=5,nightly_batches_completed_since_setup=count,latest_batch_id=batch_id,latest_batch_origin='scheduled_heartbeat_a_with_human_status_query',latest_batch_client_date='2026-11-04',next_action=state['next_checkpoint'][0],next_engineering_charter='outputs/下一阶段路线决策_20261104/下一批有限工程任务书.json')
 write(pointer,ptr)
 log=folder/'执行日志/20261104_第1批_路线决策.json'
 write(log,dict(automation_id='a',batch_id=batch_id,status='completed_verified_route_review',client_date='2026-11-04',started_at_utc=START.isoformat(),completed_at_local=guard().isoformat(),counts_as_completed_nightly_batch=True,report=ptr['last_verified_research_report'],state=ptr['last_verified_research_state'],new_models_scored=0,new_real_market_targets=0,review_steps_completed=4,outcomes_2025_2026_opened=False,archive_pending_separate_verification=True))
 health=read(folder/'夜间调度健康状态.json');health.update(checked_at_local=guard().isoformat(),completed_nightly_batches_in_latest_pointer=count,last_verified_research_state=ptr['last_verified_research_state'],observed_issue='A verified nightly route-review batch has now completed; earlier outside-window skips remain historical records.',cause='Earlier scheduling/timing causes remain undiagnosed',research_started_this_turn=True,research_pointer_unchanged=False,last_completed_batch_id=batch_id,notification_decision_for_this_turn='NOTIFY_route_review_completed')
 write(folder/'夜间调度健康状态.json',health)
 ck('pointer_resolves_to_completed_review',read(ROOT/read(pointer)['last_verified_research_state'])==state and ptr['review_package_steps_completed']==4)
 ck('source_hashes_unchanged_at_freeze',all(sha(ROOT/p)==h for p,h in build['protected_source_sha256'].items()))
 files=[p for p in OUT.iterdir() if p.is_file() and p.name!='本轮交付核验.json']+[WORK/'build.py',WORK/'finish.py',progress,pointer,log,folder/'夜间调度健康状态.json']
 write(OUT/'本轮交付核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,independent_checks=dict(passed=audit['passed'],total=audit['total']),protected_source_sha256=build['protected_source_sha256'],delivery_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},archive_summary=state['archive_summary'],new_models_or_labels_or_scores=0))
 print(json.dumps(dict(saved=True,release_checks=len(checks),independent_checks=audit['passed'],nightly_batches=count,ready_for_frozen_archive=True),ensure_ascii=False))

if __name__=='__main__':main()
