"""Publish the checked gap inventory, preserving original research and gates."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/时间执行与数据准入缺口矩阵_20261102'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def main():
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
 build=read(OUT/'本轮构建核验.json');matrix=read(OUT/'完整缺口矩阵_v1.json');state=read(OUT/'本轮状态与续作断点.json')
 ck('16_build_and_negative_checks_passed',build['all_checks_passed'] and build['passed']==build['total']==16)
 audits={}
 for folder,label in [('gap_core_nov02','核心交付对应核验'),('gap_features_nov02','特征交付对应核验')]:
  audit=read(ROOT/f'work/{folder}/交付对应核验.json')
  ck(label+'_passed',audit['all_checks_passed'] and audit['passed']==audit['total'] and all(c['passed'] for c in audit['checks']))
  audits[label]=dict(passed=audit['passed'],total=audit['total'])
  for key in ['delivery_sha256','delivery_sha256_before','delivery_sha256_after']:
   for rel,h in audit.get(key,{}).items():
    p=Path(rel) if str(rel).startswith('/') else ROOT/rel
    if not p.is_file():p=OUT/rel
    ck(label+'_hash_'+str(rel),p.is_file() and sha(p)==h)
  for ext in ['json','md']:shutil.copy2(ROOT/f'work/{folder}/交付对应核验.{ext}',OUT/f'{label}.{ext}')
 ck('36_unique_rows_16_core_15_features_5_controls',matrix['matrix_row_count']==len(matrix['gaps'])==36 and len({r['gap_id'] for r in matrix['gaps']})==36 and matrix['counts_by_group']=={'core_temporal_execution':16,'optional_feature':15,'research_and_use_control':5})
 ck('all_36_have_evidence_minimum_acceptance_owner',all(r['source_reference_ids'] and r['missing_evidence'] and r['minimum_completion_evidence'] and r['completion_criterion'] and r['independent_work_possible_now'] and r['owner'] for r in matrix['gaps']))
 ck('no_new_data_gaps_closed_or_research_admitted',matrix['new_gaps_closed']==0 and not matrix['new_market_data_acquired'] and matrix['new_models_fitted']==matrix['new_target_labels_generated']==matrix['new_scores_calculated']==0 and not any(matrix[k] for k in ['formal_model_input_approved','runtime_usable','current_forecast_generated','outcomes_2025_2026_opened']))
 ck('no_user_private_material_required_now',all(r['user_participation']['required_now'] is False for r in matrix['gaps']) and read(OUT/'后续脱敏资料字段模板.json')['required_now'] is False)
 refs=read(OUT/'来源索引与SHA256.json')
 ck('all_named_evidence_references_still_match',all(sha(ROOT/r['path'])==r['sha256'] for r in refs['evidence_references'].values()))
 ck('all_201_protected_sources_unchanged',len(build['protected_source_sha256'])==201 and all(sha(ROOT/p)==h for p,h in build['protected_source_sha256'].items()))
 label=read(ROOT/'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json')
 ck('confirmed_question_and_15_unfrozen_groups_preserved',state['user_confirmed_first_use_case']==label['user_confirmed']['first_use_case'] and state['pending_freeze']==label['pending_freeze'] and len(state['pending_freeze'])==15 and all(v is None for v in state['pending_freeze'].values()))
 for name in ['时间执行与数据准入缺口矩阵_v1.md','缺口矩阵总表.md','最小补证作业清单_v1.md']:
  ck('local_links_resolve_'+name,all((OUT/p).exists() for p in re.findall(r'\]\((\./[^)]+)\)',(OUT/name).read_text())))
 state.update(status='step_3_temporal_execution_and_admission_gap_matrix_complete_independently_checked',review_package_step_completed=True,saved_at_utc=datetime.now(timezone.utc).isoformat(),independent_delivery_checks=audits,
  completed=['All 36 gaps, evidence dates and versions, affected uses and minimum completion/acceptance criteria checked','Responsibility, private-evidence timing, nonblocking optional scope, dependency semantics and bounded work list saved','Independent core and feature correspondence audits passed; old sources and protocol/risk settings unchanged','Matrix report, full row records, provenance and continuation checkpoint saved'],
  partial=['Actual gap closure and 15-group parameter freeze are not performed; no historical/current model admission','Fourth route-decision review remains to be done','Full archive is separate and certified only by its external verification result'],
  blocked=['Formal first-availability/trading-state/cost/fill evidence and predictive acceptance remain unfulfilled; current forecasts and funds use not approved'])
 write(OUT/'本轮状态与续作断点.json',state)
 progress=ROOT/'outputs/项目进度与交易需求档案.md';pointer=ROOT/'outputs/夜间自动推进_20261028/最新续作指针.json'
 backup=WORK/'发布前状态备份';backup.mkdir(exist_ok=True)
 for path in [progress,pointer]:
  dest=backup/path.name
  if not dest.exists():shutil.copy2(path,dest)
 text=progress.read_text();lines=text.splitlines();lines[2]='更新日期：2026年11月2日。人工完成第3份时间、执行与数据准入缺口矩阵：36项证据/未知/最小补证/合格条件/责任和用途，独立对应核验保存。矩阵完成不等于数据补齐，新增关闭缺口0、无新真实标签/模型/评分；下一步第4份路线决策，仍在第5步。';text='\n'.join(lines)+'\n'
 note='\n- 2026/11/02人工指定第3步：完成[时间、执行与数据准入缺口矩阵](./时间执行与数据准入缺口矩阵_20261102/时间执行与数据准入缺口矩阵_v1.md)，36=16核心+15条件性特征+5研究/使用控制。每条给旧证据/未知/影响/最小补证/验收/责任/用户参与/用途和依赖；日历机器件10/15的914日与旧MD10/13的912日分别保留，交易条件10/16和行情10/21不混同。条件性特征不阻独立底座准备，依赖是用途放行而非采集先后；用户当前不必提供账户材料。201保护源未改，矩阵未关闭数据缺口或新放行，15组参数仍NULL、累计16与后期目标隔离不变，无新真实标签/模型/评分。下一批只完成第4份路线决策，不因文档完成自动跑模型。人工完成不计夜间自动完成。\n'
 marker='## 本轮补充确认与记账口径\n'
 if '2026/11/02人工指定第3步' not in text:text=text.replace(marker,marker+note,1)
 start=text.index('## 下次协作的起点\n');end=text.find('\n## ',start+5)
 if end<0:end=len(text)
 section='''## 下次协作的起点

以[11/02时间执行与准入缺口矩阵断点](./时间执行与数据准入缺口矩阵_20261102/本轮状态与续作断点.json)为当前入口。四份有限审查已完成前三份：研究证据与覆盖、预测问题与标签适用性、36项时间/执行/准入缺口矩阵。矩阵整理完成不表示数据补齐或正式准入，用户当前无需提供私有材料，实际空仓和15组研究参数均不据此确认。下一批只完成第4份“下一阶段路线决策记录”：按前三份证据决定先做有限补证、调整问题、等待，或是否有理由另行登记单一新假设；允许暂不开模型。保持累计16和全部失败、原风险口径及2025/2026结果隔离，不扫描其余14列。首版优先仍是收盘后回落买入vs等待。人工批次，夜间完成次数仍0。
'''
 progress.write_text(text[:start]+section+text[end:])
 ptr=read(pointer);ptr.update(last_verified_research_state='outputs/时间执行与数据准入缺口矩阵_20261102/本轮状态与续作断点.json',last_verified_research_report='outputs/时间执行与数据准入缺口矩阵_20261102/时间执行与数据准入缺口矩阵_v1.md',research_stage=5,research_variants_so_far=16,nightly_batches_completed_since_setup=0,latest_batch_origin='direct_human_request',latest_batch_client_date='2026-11-02',review_package_steps_completed=3,review_package_steps_remaining=1,next_action=state['next_checkpoint'][0]+'; no new candidate or later target opening')
 write(pointer,ptr)
 log=ROOT/'outputs/夜间自动推进_20261028/执行日志/20261102_人工协作时间执行准入矩阵.json'
 write(log,dict(origin='direct_human_request',client_date='2026-11-02',status=state['status'],counts_as_completed_nightly_batch=False,report=ptr['last_verified_research_report'],state=ptr['last_verified_research_state'],review_steps_completed=3,matrix_rows=36,newly_closed_data_gaps=0,new_real_market_targets=0,new_models_scored=0,cumulative_registered_variants=16,outcomes_2025_2026_opened=False,heartbeat_time_check_was_preempted_by_explicit_human_request=True))
 ck('pointer_resolves_to_complete_third_review',read(ROOT/read(pointer)['last_verified_research_state'])==state and state['review_package_step_completed'])
 ck('manual_research_not_credited_to_night_count',read(pointer)['nightly_batches_completed_since_setup']==0 and read(pointer)['review_package_steps_completed']==3 and read(pointer)['review_package_steps_remaining']==1)
 ck('protected_sources_unchanged_at_freeze',all(sha(ROOT/p)==h for p,h in build['protected_source_sha256'].items()))
 files=[p for p in OUT.iterdir() if p.is_file() and p.name!='本轮交付核验.json']+[WORK/'build_matrix.py',WORK/'finish_review.py',WORK/'官方规则核查原响应.json',progress,pointer,log]
 ck('all_delivery_files_nonempty',all(p.stat().st_size for p in files))
 write(OUT/'本轮交付核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,build_checks=16,independent_inventory_checks=dict(core=27,features=12),independent_delivery_checks=audits,protected_source_sha256=build['protected_source_sha256'],delivery_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},archive_summary=state['archive_summary'],matrix_rows=36,newly_closed_data_gaps=0,new_real_market_targets=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,phase_promotion_approved=False))
 print(json.dumps(dict(saved=True,release_checks=len(checks),independent_delivery_checks=audits,ready_for_frozen_archive=True),ensure_ascii=False))

if __name__=='__main__':main()
