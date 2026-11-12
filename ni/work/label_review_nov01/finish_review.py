"""Save the independently checked label design and the next review checkpoint."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/预测问题与标签适用性审查_20261101'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def main():
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
 build=read(OUT/'本轮构建核验.json');cfg=read(OUT/'审查范围与设计合同.json');state=read(OUT/'本轮状态与续作断点.json')
 ck('nine_build_checks_passed',build['all_checks_passed'] and build['passed']==build['total']==9)
 audit_counts={}
 for folder,filename,label in [('label_math_nov01','交付独立复核','数学交付独立复核'),('label_timing_nov01','交付对应核验','时间制度交付对应核验')]:
  data=read(ROOT/f'work/{folder}/{filename}.json')
  ck(label+'_all_checks_passed',data['all_checks_passed'] and data['passed']==data['total'] and all(c['passed'] for c in data['checks']))
  audit_counts[label]=dict(passed=data['passed'],total=data['total'])
  # Reviewers retain source fingerprints in their own schema. Check any named
  # delivery hash map here as well; each one must address an existing file.
  for key in ['delivery_sha256','delivery_sha256_before','delivery_sha256_after']:
   if key not in data:continue
   for rel,h in data[key].items():
    p=Path(rel) if str(rel).startswith('/') else ROOT/rel
    if not p.is_file():p=OUT/rel
    ck(label+'_fingerprint_'+str(rel),p.is_file() and sha(p)==h)
  for ext in ['json','md']:shutil.copy2(ROOT/f'work/{folder}/{filename}.{ext}',OUT/f'{label}.{ext}')
 synth=read(OUT/'合成案例与精确计算.json');sv=read(OUT/'合成案例核验.json');dictionary=read(OUT/'预测事件字典_v1.json')
 ck('21_cases_are_synthetic_only',synth['real_market_observations_used']==0 and len(synth['cases'])==21 and all(r['all_inputs_are_synthetic'] and r['not_a_market_forecast'] for r in synth['cases']))
 ck('23_synthetic_formula_checks_passed',sv['all_checks_passed'] and sv['passed']==sv['total']==23)
 ck('twelve_event_definitions_and_five_status_axes',len(dictionary['events'])==12 and len(read(OUT/'状态与资格字典.json')['independent_axes'])==5)
 ck('fifteen_parameter_groups_still_NULL',len(cfg['pending_freeze'])==15 and all(v is None for v in cfg['pending_freeze'].values()))
 ck('user_confirmation_limited_to_selected_question',cfg['user_confirmed']['first_use_case']=='收盘后判断回落时该买入还是继续等待' and 'starting_comparison_state' not in cfg['user_confirmed'] and len(read(OUT/'本次用户确认与待定参数.json')['confirmed'])==1)
 ck('all_144_immutable_prior_sources_unchanged',len(build['protected_source_sha256'])==144 and all(sha(ROOT/p)==h for p,h in build['protected_source_sha256'].items()))
 report=OUT/'预测问题与标签适用性审查_v1.md'
 ck('all_local_report_links_resolve',all((OUT/p).is_file() for p in re.findall(r'\]\((\./[^)]+)\)',report.read_text())))
 ck('no_new_actual_labels_models_scores_or_forecast',all(state[k]==0 for k in ['new_registered_model_variants','new_real_market_targets','new_models_fitted','new_scores_calculated']) and not any(state[k] for k in ['outcomes_2025_2026_opened','current_forecast_generated','model_input_approved','runtime_usable','phase_promotion_approved','old_protocol_or_risk_modified']))
 state.update(status='step_2_prediction_question_and_label_design_review_complete_independently_checked',review_package_step_completed=True,saved_at_utc=datetime.now(timezone.utc).isoformat(),independent_delivery_checks=audit_counts,
  completed=['User confirmation of after-close pullback buy-versus-wait priority, without inferring account positions','Old-label scope, paired-action time/wealth definitions, 12 event definitions and five status axes reviewed','21 synthetic examples with exact arithmetic and independent negative/boundary review','Official temporal/execution-source review and prior-source hash preservation','Final report, design dictionary and continuation checkpoint saved'],
  partial=['15 parameter groups remain unconfirmed/unfrozen; review completion is not an experiment protocol freeze','Input-admission gap matrix and route decision remain; archive success certified by separate external result'],
  blocked=['Formal PIT, historical trading states and actual fees/fills/rights unresolved; no new model or real-money acceptance'])
 write(OUT/'本轮状态与续作断点.json',state)
 progress=ROOT/'outputs/项目进度与交易需求档案.md';pointer=ROOT/'outputs/夜间自动推进_20261028/最新续作指针.json'
 before=WORK/'发布前状态备份';before.mkdir(exist_ok=True)
 for p in [progress,pointer]:
  dst=before/p.name
  if not dst.exists():shutil.copy2(p,dst)
 text=progress.read_text();lines=text.splitlines();lines[2]='更新日期：2026年11月1日。完成第2份预测问题与标签适用性审查；用户确认首版优先收盘后回落买入vs等待，15组参数仍未冻结。12事件、五类状态维度和21个合成反例独立核验保存，无新真实标签、模型或评分；仍在第5步。';text='\n'.join(lines)+'\n'
 note='\n- 2026/11/01人工指定第2步：完成[预测问题与标签适用性审查](./预测问题与标签适用性审查_20261101/预测问题与标签适用性审查_v1.md)。用户明确选择首版优先“收盘后判断回落时该买入还是继续等待”；账户实际空仓/仓位、H、确认/等待、终点及费用未据此确认，15组仍NULL。旧5观察日原价标签不等于费后盈利或等待优势；新设计共资金、共信息和共终点，NAV/实现现金、无触发/未成交/未知分开。12事件、五状态轴、21合成反例及独立数学/时间对应复核完成，144保护源未改；现行盘后与日量可得时间的制度边界已留官方证据，不能回填旧年份。累计16不变、2025/2026目标隔离、无新真实标签/模型/评分。下一批只做第3份时间/执行/输入准入缺口矩阵，第4份路线决策待后续。人工工作不计夜间自动完成。\n'
 marker='## 本轮补充确认与记账口径\n'
 if '2026/11/01人工指定第2步' not in text:text=text.replace(marker,marker+note,1)
 start=text.index('## 下次协作的起点\n');end=text.find('\n## ',start+5)
 if end<0:end=len(text)
 section='''## 下次协作的起点

以[11/01预测问题与标签适用性审查断点](./预测问题与标签适用性审查_20261101/本轮状态与续作断点.json)为当前入口。四份有限审查已完成前两份：证据覆盖、预测问题与标签适用性；用户确认首版收盘后回落买入vs等待，实际账户持仓、15组研究参数未据此确认或冻结。下一批只做第3份时间、执行与数据准入缺口矩阵：逐项列证据、未知、受影响问题、最小补证、可独立推进项和用户参与；不新生成真实目标或评分。随后第4份路线决策才能讨论是否登记新假设。保留全部16研究定义和否定结果、原协议与风险口径，2025/2026目标隔离，不扫描剩余14列。人工完成，夜间完成次数仍0。
'''
 progress.write_text(text[:start]+section+text[end:])
 ptr=read(pointer);ptr.update(last_verified_research_state='outputs/预测问题与标签适用性审查_20261101/本轮状态与续作断点.json',last_verified_research_report='outputs/预测问题与标签适用性审查_20261101/预测问题与标签适用性审查_v1.md',research_stage=5,research_variants_so_far=16,nightly_batches_completed_since_setup=0,latest_batch_origin='direct_human_request',latest_batch_client_date='2026-11-01',review_package_steps_completed=2,review_package_steps_remaining=2,confirmed_first_use_case=cfg['user_confirmed']['first_use_case'],next_action=state['next_checkpoint'][0]+'; no new candidate or later target opening')
 write(pointer,ptr)
 log=ROOT/'outputs/夜间自动推进_20261028/执行日志/20261101_人工协作预测问题审查.json'
 write(log,dict(origin='direct_human_request',client_date='2026-11-01',status=state['status'],counts_as_completed_nightly_batch=False,report=ptr['last_verified_research_report'],state=ptr['last_verified_research_state'],review_steps_completed=2,new_real_market_targets=0,new_models_scored=0,cumulative_registered_variants=16,outcomes_2025_2026_opened=False,user_confirmed_first_use_case=cfg['user_confirmed']['first_use_case']))
 ck('saved_pointer_resolves_to_complete_second_review',read(ROOT/read(pointer)['last_verified_research_state'])==state and state['review_package_step_completed'])
 ck('manual_work_not_credited_as_night_research',read(pointer)['nightly_batches_completed_since_setup']==0 and read(pointer)['review_package_steps_completed']==2 and read(pointer)['review_package_steps_remaining']==2)
 ck('immutable_sources_unchanged_at_freeze',all(sha(ROOT/p)==h for p,h in build['protected_source_sha256'].items()))
 files=[p for p in OUT.iterdir() if p.is_file() and p.name!='本轮交付核验.json']+[WORK/'review_contract.json',WORK/'synthetic_examples.py',WORK/'build_review.py',WORK/'finish_review.py',progress,pointer,log]
 ck('all_delivery_files_nonempty',all(p.stat().st_size for p in files))
 write(OUT/'本轮交付核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,independent_design_checks=dict(math=26,timing=22),independent_delivery_checks=audit_counts,synthetic_cases=21,synthetic_checks=23,protected_source_sha256=build['protected_source_sha256'],delivery_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},archive_summary=state['archive_summary'],new_real_market_targets=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,phase_promotion_approved=False))
 print(json.dumps(dict(saved=True,release_checks=len(checks),independent_delivery_checks=audit_counts,ready_for_frozen_archive=True),ensure_ascii=False))

if __name__=='__main__':main()
