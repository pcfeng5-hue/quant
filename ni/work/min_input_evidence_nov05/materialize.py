"""Resume saved metadata products; no extraction, network, market or target query."""
from pathlib import Path
from datetime import datetime,timezone,timedelta,date
from zoneinfo import ZoneInfo
import hashlib,json,shutil,sqlite3,time

ROOT=Path(__file__).resolve().parents[2];WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/输入证据合库与验证设计_20261105'
PENDING=ROOT/'outputs/最小输入证据台账_20261104_批次02'
START=time.monotonic()
def guard():
 if time.monotonic()-START>40*60:raise RuntimeError('Manual batch exceeds40min; preserve checkpoint')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False)
def write(p,x):
 guard();p=Path(p);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n');t.replace(p)
def main():
 guard();OUT.mkdir(parents=True,exist_ok=True)
 pending=read(PENDING/'本轮状态与续作断点.json');charterpath=ROOT/'outputs/下一阶段路线决策_20261104/下一批有限工程任务书.json';charter=read(charterpath)
 checks=[]
 def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
 ck('saved_partial_artifact_hashes_match',all(sha(PENDING/p)==h for p,h in pending['artifact_sha256'].items()))
 fields=read(PENDING/'字段时点与版本台账_待独立复核.json');cal=read(PENDING/'计划日与状态来源索引_待独立复核.json')
 fq=read(PENDING/'字段提取子任务核查.json');cq=read(PENDING/'日历提取子任务核查.json')
 ck('saved_local_field_24_calendar_23_checks_passed',fq['all_checks_passed'] and fq['passed']==fq['total']==24 and cq['all_checks_passed'] and cq['passed']==cq['total']==23)
 allowed=charter['local_source_paths'];used=set(fields['fixed_content_source_paths'])|{r['path'] for r in cal['source_manifest'].values()}
 source_hashes={p:sha(ROOT/p) for p in allowed}
 ck('15_registered_paths_14_reused_content_sources_no_extra',len(allowed)==15 and len(used)==14 and used<=set(allowed) and fields['extra_content_source_paths']==[])
 ck('prior_source_fingerprints_match',all(source_hashes[p]==h for p,h in pending['source_hashes'].items()))
 fs=fields['field_provider_rows'];ds=cal['all_calendar_days'];ctx=cal['context_only_prior_calendar_days'];acts=cal['corporate_action_date_index']
 ck('10_exact_unique_field_provider_pairs',len(fs)==10 and {(r['field_family'],r['provider']) for r in fs}=={(f,p) for f in charter['field_families'] for p in ['eastmoney','tencent']})
 first=date.fromisoformat('2023-01-03');last=date.fromisoformat('2024-12-31');expected=[(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
 ck('729_exact_calendar_dates',len(ds)==729 and [r['trade_date'] for r in ds]==expected)
 ck('484_open_245_closed_two_context',sum(r['planned_is_open'] is True for r in ds)==484 and sum(r['planned_is_open'] is False for r in ds)==245 and len(ctx)==2 and all(r['context_only'] and not r['counts_toward_main_scope'] for r in ctx))
 ck('all_unknown_historical_field_times_preserved',all(r['historical_first_available_at'] is None and r['historical_revision_available_at'] is None and r['earliest_model_use_timestamp'] is None for r in fs))
 ck('native_mapping_units_not_invented',all(r['native_field_identifier'] is None and r['unit_status']['provider_native_unit_certified'] is None and r['historical_time_unknown_reason'] for r in fs))
 ck('manifest_raw_hashes_not_pretended_reverified',all(not r['raw_response_content_read_this_batch'] and not r['raw_response_rehashed_this_batch'] and r['raw_response_integrity_evidence']=='MANIFEST_RECORDED_ONLY_NOT_REHASHED_IN_THIS_SUBTASK' for r in fs))
 ck('formal_current_runtime_gates_false',all(not any(r[k] for k in ['formal_historical_input_approved','current_decision_approved','runtime_usable']) for r in fs+ds+ctx))
 ck('status_zero_certification_not_normalized_true',all(not r['daily_status_verified_normal'] and not r['official_daily_limit_evidence_recorded'] and not r['saved_execution_eligible'] and not r['saved_cost_model_complete'] and not r['monthly_absence_certifies_daily_no_suspension'] for r in ds))
 copies=[('字段时点与版本台账_待独立复核.json','字段时点与版本台账.json'),('计划日与状态来源索引_待独立复核.json','计划日与状态来源索引.json'),('字段提取子任务核查.json','字段提取核查.json'),('日历提取子任务核查.json','日历提取核查.json')]
 for src,dest in copies:shutil.copy2(PENDING/src,OUT/dest)
 ck('saved_JSON_products_copied_byte_identically',all(sha(PENDING/a)==sha(OUT/b) for a,b in copies))
 registry=read(ROOT/'work/min_input_evidence_nov04_b2/访问范围登记.json');write(OUT/'访问范围登记.json',dict(prior_registry=registry,actual_reused_scientific_content_sources=sorted(used),unused_registered_path=sorted(set(allowed)-used),extra_paths_used=[],original_extractor_rerun=False,source_integrity_hashes=source_hashes))
 db=OUT/'最小输入证据台账.sqlite'
 if db.exists():raise FileExistsError('Preserve prior build: '+str(db))
 tmp=db.with_name(db.name+'.pending')
 if tmp.exists():raise FileExistsError(tmp)
 with sqlite3.connect(tmp) as c:
  c.execute('CREATE TABLE field_evidence(evidence_id TEXT PRIMARY KEY,field_family TEXT,provider TEXT,source_metadata_path TEXT,source_metadata_sha256 TEXT,json_locator TEXT,collected_at_utc_recorded TEXT,historical_first_available_at TEXT,historical_revision_available_at TEXT,earliest_model_use_timestamp TEXT,native_field_identifier TEXT,unit_status_json TEXT,formal_historical_input_approved INTEGER,current_decision_approved INTEGER,runtime_usable INTEGER,record_json TEXT,UNIQUE(field_family,provider))')
  c.executemany('INSERT INTO field_evidence VALUES('+','.join('?'*16)+')',[(r['evidence_id'],r['field_family'],r['provider'],r['snapshot_source_reference']['path'],r['snapshot_source_reference']['sha256'],r['snapshot_source_reference']['json_locator'],r['collected_at_utc_recorded'],r['historical_first_available_at'],r['historical_revision_available_at'],r['earliest_model_use_timestamp'],r['native_field_identifier'],enc(r['unit_status']),int(r['formal_historical_input_approved']),int(r['current_decision_approved']),int(r['runtime_usable']),enc(r)) for r in fs])
  schema='(trade_date TEXT PRIMARY KEY,planned_is_open INTEGER,stock_status_record_exists INTEGER,historical_st_status TEXT,daily_status_verified_normal INTEGER,official_daily_limit_evidence_recorded INTEGER,saved_execution_eligible INTEGER,saved_cost_model_complete INTEGER,historical_first_available_timestamp TEXT,formal_historical_input_approved INTEGER,current_decision_approved INTEGER,runtime_usable INTEGER,record_json TEXT)'
  for name,rows in [('calendar_days',ds),('context_calendar_days',ctx)]:
   c.execute('CREATE TABLE '+name+schema)
   c.executemany('INSERT INTO '+name+' VALUES('+','.join('?'*13)+')',[(r['trade_date'],int(r['planned_is_open']),int(r['stock_status_record_exists']),r['historical_st_status'],r['daily_status_verified_normal'],r['official_daily_limit_evidence_recorded'],r['saved_execution_eligible'],r['saved_cost_model_complete'],r['historical_first_available_timestamp'],int(r['formal_historical_input_approved']),int(r['current_decision_approved']),int(r['runtime_usable']),enc(r)) for r in rows])
  c.execute('CREATE VIEW planned_open_status AS SELECT * FROM calendar_days WHERE planned_is_open=1')
  c.execute('CREATE TABLE corporate_action_dates(event_id TEXT PRIMARY KEY,record_date TEXT,ex_date TEXT,record_json TEXT)')
  c.executemany('INSERT INTO corporate_action_dates VALUES(?,?,?,?)',[(r['event_id'],r['record_date'],r['ex_date'],enc(r)) for r in acts])
  c.execute('CREATE TABLE source_registry(path TEXT PRIMARY KEY,sha256 TEXT,content_extracted_in_prior_pass INTEGER,source_kind TEXT)')
  c.executemany('INSERT INTO source_registry VALUES(?,?,?,?)',[(p,h,int(p in used),'registered_local_metadata_or_status_document') for p,h in source_hashes.items()])
  c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT)')
  meta=dict(charter_id=charter['charter_id'],status='engineering_metadata_only_not_model_input',actual_numeric_market_rows=0,new_real_labels=0,new_models=0,new_scores=0,formal_input_approved=False,current_decision_approved=False,runtime_usable=False,outcomes_2025_2026_opened=False)
  c.execute('INSERT INTO metadata VALUES(?,?)',('run',enc(meta)))
  ck('SQLite_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
  ck('SQLite_keys_counts_and_nulls',c.execute('SELECT count(*) FROM field_evidence').fetchone()[0]==10 and c.execute('SELECT count(*) FROM calendar_days').fetchone()[0]==729 and c.execute('SELECT count(*) FROM planned_open_status').fetchone()[0]==484 and c.execute('SELECT count(*) FROM context_calendar_days').fetchone()[0]==2 and c.execute('SELECT count(*) FROM field_evidence WHERE historical_first_available_at IS NOT NULL OR earliest_model_use_timestamp IS NOT NULL').fetchone()[0]==0)
  for name,rows in [('field_evidence',fs),('calendar_days',ds),('context_calendar_days',ctx),('corporate_action_dates',acts)]:
   actual=[json.loads(r[0]) for r in c.execute('SELECT record_json FROM '+name+' ORDER BY rowid')]
   ck('exact_JSON_record_correspondence_'+name,actual==rows)
 guard();tmp.replace(db)
 result=dict(scope='One fixed local metadata-source pass, reused saved products without re-extraction',engineering_inventory_complete=True,field_provider_rows=10,calendar_natural_days=729,planned_open_days=484,planned_closed_days=245,context_only_days=2,corporate_action_date_records=2,source_paths_registered=15,source_paths_content_used_in_prior_pass=14,extra_sources=0,historical_first_availability_certified_rows=0,native_field_mapping_certified_rows=0,formal_historical_input_approved_rows=0,calendar_daily_normal_certified_rows=0,official_daily_limit_certified_rows=0,conclusion='This bounded source set does not establish historical first-availability/revision proof or full daily execution/cost status. Unknowns are retained, not evidence that publication never occurred or recovery is impossible from every other source.',next_action='Freeze gated buy-versus-wait validation design with explicit pending parameters and prospective first-receipt evidence requirements; do not label, fit, score, simulate or trade',raw_original_integrity='Manifest-recorded SHA only, not rehashed this batch',all_formal_and_current_gates=False,new_real_labels=0,new_models=0,new_scores=0,outcomes_2025_2026_opened=False)
 write(OUT/'有限来源可恢复性结论.json',result)
 query='''-- Read-only metadata inspection. No prices, returns or predictions are stored here.
SELECT field_family,provider,historical_first_available_at,earliest_model_use_timestamp FROM field_evidence ORDER BY provider,field_family;
SELECT planned_is_open,COUNT(*) FROM calendar_days GROUP BY planned_is_open;
SELECT trade_date,historical_st_status,daily_status_verified_normal,saved_execution_eligible FROM planned_open_status ORDER BY trade_date;
SELECT path,content_extracted_in_prior_pass FROM source_registry;
'''
 (OUT/'只读查询示例.sql').write_text(query)
 report="""# 输入证据合库与验证设计：构建中间说明

2026年11月5日，多伦多。由用户手动续作；夜间自动任务已取消。本脚本复用11月4日批次02的已保存JSON，不重跑提取器，不扩大固定来源，不导出市场数值或目标。

已合并10组字段/来源、729自然日（484计划开市、245计划休市）、2条独立上下文日、2个公司行动日期及15条来源登记；完整原记录保存在record_json。正式历史输入、当前决策和运行门均保持关闭。历史首次可得/版本、原生字段映射/正式单位、逐日状态、成交/费用等证据不足，未知保留。原响应哈希仅沿旧清单记录，本批未读取或重核原响应。

本说明仅为构建中间状态；独立复核、正式可用范围矩阵、买vs等条件性验证设计、交付与恢复核验须另完成后发布。不得把本文件当作研究或预测有效性验收。
"""
 guard();(OUT/'本轮推进报告.md').write_text(report)
 ck('15_metadata_source_hashes_unchanged_after_materialization',all(sha(ROOT/p)==h for p,h in source_hashes.items()))
 write(OUT/'本轮构建核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_hashes=source_hashes,record_counts=result,inputs_reused=True,extractors_rerun=False))
 write(OUT/'本轮状态与续作断点.json',dict(client_date='2026-11-05',origin='direct_human_authorized_metadata_and_validation_design',status='metadata_materialized_pending_independent_audit',research_stage=5,complete=False,counts_as_completed_nightly_batch=False,source_hashes=source_hashes,completed=['10-field/provider and729-day metadata SQLite materialized from stable saved products'],partial=['Independent audit, use-admission matrix, gated validation design, release and recovery verification pending'],blocked=['Historical first-availability/native mapping/units and full trading/cost evidence remain uncertified'],archive_summary=result,cumulative_registered_variants=16,new_real_labels=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,next_checkpoint=['Complete independent metadata audit, explicit admission matrix and gated buy-versus-wait validation design; no market labels or models','Do not re-extract the completed fixed local source set, sweep14 optional columns or change15 pending parameters/risk settings'],old_pending_checkpoint_preserved=str(PENDING.relative_to(ROOT))+'/本轮状态与续作断点.json'))
 print(enc(dict(materialized=True,checks=len(checks),field_rows=10,calendar_rows=729,source_hashes=len(source_hashes))))

if __name__=='__main__':main()
