"""Publish the audited evidence inventory and save the continuation pointer."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shutil,sqlite3

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/研究证据与覆盖审查_20261101'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def main():
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details))
  if not ok:raise AssertionError(name)
 build=read(OUT/'本轮构建核验.json')
 ck('build_checks_all_passed',build['all_checks_passed'] and build['passed']==build['total']==22)
 audit_counts={}
 for agent,name in [('evidence_signals_nov01','12信号交付对应核验'),('evidence_models_nov01','三轮模型交付对应核验')]:
  data=read(ROOT/f'work/{agent}/交付对应核验.json')
  ck(name+'_all_passed',data['all_checks_passed'] and data['passed']==data['total'] and all(r['passed'] for r in data['checks']))
  audit_counts[name]=dict(passed=data['passed'],total=data['total'])
  for ext in ['json','md']:shutil.copy2(ROOT/f'work/{agent}/交付对应核验.{ext}',OUT/f'{name}.{ext}')
 ledger=read(OUT/'16项研究变体完整台账.json');state=read(OUT/'本轮状态与续作断点.json')
 ck('all_sixteen_types_and_registration_order',ledger['variant_count']==16 and [r['variant_id'] for r in ledger['variants']]==list(range(1,17)) and ledger['descriptive_signal_definitions']==12 and ledger['unique_model_definitions']==4)
 ck('all_98_scores_70_comparisons_18_folds_preserved',sum(len(r['metrics']) for r in ledger['model_rounds'].values())==98 and sum(len(r['comparisons']) for r in ledger['model_rounds'].values())==70 and sum(len(r['folds']) for r in ledger['model_rounds'].values())==18)
 ck('new_models_scores_targets_and_approval_remain_false',ledger['new_models_fitted']==ledger['new_scores_calculated']==0 and not any(ledger[k] for k in ['new_target_labels_generated','outcomes_2025_2026_opened','current_forecast_generated','formal_model_input_approved','runtime_usable']))
 with sqlite3.connect((OUT/'研究证据汇总.sqlite').as_uri()+'?mode=ro',uri=True) as c:
  ck('saved_database_is_healthy',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
  ck('2172_saved_prediction_rows_and_sixteen_variants',c.execute("SELECT count(*) FROM saved_result_rows WHERE table_name='predictions'").fetchone()[0]==2172 and c.execute('SELECT count(*) FROM variants').fetchone()[0]==16)
 manifest=read(OUT/'原有结果文件清单与SHA256.json')
 ck('88_original_file_snapshots_match_source_hashes',len(manifest['files'])==88 and all(sha(OUT/r['snapshot'])==sha(ROOT/r['source'])==r['sha256'] for r in manifest['files']))
 ck('117_protected_sources_unchanged',len(build['protected_source_sha256'])==117 and all(sha(ROOT/p)==v for p,v in build['protected_source_sha256'].items()))
 report=OUT/'研究证据与覆盖审查_v1.md'
 text=report.read_text()
 ck('all_report_artifact_links_resolve',all((OUT/link).exists() for link in re.findall(r'\]\((\./[^)]+)\)',text)))
 state.update(status='step_1_existing_research_evidence_review_complete_independently_checked',review_package_step_completed=True,review_package_step_completed_pending_audit=False,saved_at_utc=datetime.now(timezone.utc).isoformat(),independent_correspondence_checks=audit_counts,
  completed=['All 16 original research choices and all four saved result packages inventoried','Every quarter/grid metric, original parameter/calibration row, scored date, training member and exclusion retained','Independent signal and model correspondence checks passed; original sources unchanged','Current report, evidence database and continuation checkpoint saved'],
  partial=['Prediction-question and label-suitability review, admission-gap matrix and route decision remain to be done','Full project archive is a separate final operation, certified only by the external archive-verification result'])
 state['archive_summary']['review_step_completed']=1
 state['archive_summary']['review_steps_remaining']=3
 write(OUT/'本轮状态与续作断点.json',state)
 progress=ROOT/'outputs/项目进度与交易需求档案.md';pointer=ROOT/'outputs/夜间自动推进_20261028/最新续作指针.json'
 backups=WORK/'发布前状态备份';backups.mkdir(exist_ok=True)
 for path in [progress,pointer]:
  dest=backups/path.name
  if not dest.exists():shutil.copy2(path,dest)
 text=progress.read_text();lines=text.splitlines();lines[2]='更新日期：2026年11月1日。完成人工指定的第1项研究证据与覆盖审查：16定义、88旧结果文件、全部评分/样本与独立对应核验已保存；M1/M2/M3均无升级依据。下一步为预测问题与标签适用性审查，仍在第5步。';text='\n'.join(lines)+'\n'
 marker='## 本轮补充确认与记账口径\n'
 note='\n- 2026/11/01人工指定第1步：完成[研究证据与覆盖审查](./研究证据与覆盖审查_20261101/研究证据与覆盖审查_v1.md)。累计16=12描述信号+M0/M1/M2/M3四模型定义；重复对照不重复计数。原样保存四个旧结果目录88文件，汇总全部98评分、70对照、18折及2172旧概率记录；308/298/331日期不能跨轮排名。信号35、模型54项独立整理核查与两组最终交付对应核验通过，117保护源未改，无新模型、评分或目标，2025/2026结果继续隔离。用户要求额度前存档，收尾后本批停止新增研究。其余3份审查仍未完成；下次先做预测问题与标签适用性，不扫描14准备列。人工工作不计夜间自动完成。\n'
 if '2026/11/01人工指定第1步' not in text:text=text.replace(marker,marker+note,1)
 start=text.index('## 下次协作的起点\n');end=text.find('\n## ',start+5)
 if end<0:end=len(text)
 section='''## 下次协作的起点

以[11/01研究证据与覆盖审查续作断点](./研究证据与覆盖审查_20261101/本轮状态与续作断点.json)为当前入口。四份有限审查中的第1份已经完成：16研究定义及全部旧样本/结果、独立对应核验和原样快照保存。下一批只做第2份“预测问题与标签适用性审查”，用已有定义和合成例子明确买/等/持/卖、期限、净收益和路径风险；不批量生成真实新标签或评分。第3份准入缺口矩阵和第4份路线决策仍待完成。累计16、全部否定结果、原风险口径继续保留，2025/2026目标隔离；不扫描其余14候选列。最新断点为人工完成，夜间完成次数仍0。
'''
 progress.write_text(text[:start]+section+text[end:])
 ptr=read(pointer);ptr.update(last_verified_research_state='outputs/研究证据与覆盖审查_20261101/本轮状态与续作断点.json',last_verified_research_report='outputs/研究证据与覆盖审查_20261101/研究证据与覆盖审查_v1.md',research_stage=5,research_variants_so_far=16,nightly_batches_completed_since_setup=0,latest_batch_origin='direct_human_request',latest_batch_client_date='2026-11-01',review_package_steps_completed=1,review_package_steps_remaining=3,next_action=state['next_checkpoint'][0]+'; keep all previous negative results and 16 variants; do not run a new candidate')
 write(pointer,ptr)
 log=ROOT/'outputs/夜间自动推进_20261028/执行日志/20261101_人工协作研究证据审查.json'
 write(log,dict(origin='direct_human_request',client_date='2026-11-01',status=state['status'],counts_as_completed_nightly_batch=False,report=ptr['last_verified_research_report'],state=ptr['last_verified_research_state'],new_models_scored=0,new_scores_calculated=0,cumulative_registered_variants=16,outcomes_2025_2026_opened=False,user_requested_save_before_token_end=True))
 ck('pointer_points_to_complete_review',read(ROOT/read(pointer)['last_verified_research_state'])==state and state['review_package_step_completed'])
 ck('only_first_review_marked_complete_no_nightly_credit',read(pointer)['review_package_steps_completed']==1 and read(pointer)['review_package_steps_remaining']==3 and read(pointer)['nightly_batches_completed_since_setup']==0)
 ck('protected_sources_unchanged_after_publication',all(sha(ROOT/p)==v for p,v in build['protected_source_sha256'].items()))
 files=[p for p in OUT.iterdir() if p.is_file() and p.name!='本轮交付核验.json']+[progress,pointer,log,WORK/'build_review.py',WORK/'finish_review.py']
 ck('all_deliveries_are_nonempty',all(p.stat().st_size>0 for p in files))
 write(OUT/'本轮交付核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,build_checks=22,independent_inventory_checks=dict(signals=35,models=54),independent_delivery_checks=audit_counts,protected_source_sha256=build['protected_source_sha256'],delivery_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},archive_summary=state['archive_summary'],new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,phase_promotion_approved=False))
 print(json.dumps(dict(saved=True,release_checks=len(checks),independent_delivery_checks=audit_counts,ready_for_frozen_archive=True),ensure_ascii=False))

if __name__=='__main__':main()
