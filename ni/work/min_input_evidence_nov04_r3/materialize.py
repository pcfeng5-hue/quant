"""Resume saved metadata products; no extraction, network, market or target query."""
from pathlib import Path
from datetime import datetime,timezone,timedelta,date
from zoneinfo import ZoneInfo
import hashlib,json,shutil,sqlite3

ROOT=Path(__file__).resolve().parents[2];WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/最小输入证据台账_20261104_续作03'
PENDING=ROOT/'outputs/最小输入证据台账_20261104_批次02'
START=datetime.fromisoformat('2026-11-04T07:09:07.509852+00:00')
def guard():
 if datetime.now(timezone.utc)>START+timedelta(minutes=40):raise RuntimeError('Resume batch limit; save unfinished checkpoint instead of extending')
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
 result=dict(scope='One fixed local metadata-source pass, reused saved products without re-extraction',engineering_inventory_complete=True,field_provider_rows=10,calendar_natural_days=729,planned_open_days=484,planned_closed_days=245,context_only_days=2,corporate_action_date_records=2,source_paths_registered=15,source_paths_content_used_in_prior_pass=14,extra_sources=0,historical_first_availability_certified_rows=0,native_field_mapping_certified_rows=0,formal_historical_input_approved_rows=0,calendar_daily_normal_certified_rows=0,official_daily_limit_certified_rows=0,conclusion='This bounded source set does not establish historical first-availability/revision proof or full daily execution/cost status. Unknowns are retained, not evidence that publication never occurred or recovery is impossible from every other source.',next_action='Prepare a bounded prospective first-receipt/version capture and quality-rejection design; do not repeat this same broad local search or start forecasts/simulation',raw_original_integrity='Manifest-recorded SHA only, not rehashed this batch',all_formal_and_current_gates=False,new_real_labels=0,new_models=0,new_scores=0,outcomes_2025_2026_opened=False)
 write(OUT/'有限来源可恢复性结论.json',result)
 query='''-- Read-only metadata inspection. No prices, returns or predictions are stored here.
SELECT field_family,provider,historical_first_available_at,earliest_model_use_timestamp FROM field_evidence ORDER BY provider,field_family;
SELECT planned_is_open,COUNT(*) FROM calendar_days GROUP BY planned_is_open;
SELECT trade_date,historical_st_status,daily_status_verified_normal,saved_execution_eligible FROM planned_open_status ORDER BY trade_date;
SELECT path,content_extracted_in_prior_pass FROM source_registry;
'''
 (OUT/'只读查询示例.sql').write_text(query)
 report='''# 最小输入证据台账：续作03

2026年11月4日，多伦多。按用户“继续下一步、额度结束前保存”的指示，复用批次02中间提取物，完成元数据SQLite合并。没有重跑旧提取器、扩大来源、联网采集、读取原始行情响应或结果数据库，也没有新增真实标签、模型或评分。

## 本轮具体产物

|产物|实际内容|
|---|---|
|字段证据台账|O/H/L/C/成交量五字段族×东方财富主源/腾讯比较源，共10组；保存版本、请求/采集时刻、源路径SHA、JSON定位、单位与未知理由|
|计划日和状态来源索引|2023-01-03—2024-12-31共729自然日，484计划开市、245计划休市；两条Jan1/2仅上下文，另表保存|
|开市日状态视图|484条均关联已保存交易条件记录；这些关联不等于484天已认证正常或订单可成交|
|公司行动日期索引|2个研究期内已有事件的登记/除权日期与来源；没有导出现金/股数条款或收益|
|来源登记|15个已登记路径，原提取逻辑用到14个，另一个未作科学内容提取；本批使用额外来源0|

数据库：[最小输入证据台账.sqlite](./最小输入证据台账.sqlite)。JSON：[字段台账](./字段时点与版本台账.json)、[日期与状态索引](./计划日与状态来源索引.json)。[只读查询示例](./只读查询示例.sql)可以直接查每个未知和日期，不用再从分散报告寻找。

## 有什么证据，仍没有什么证据

可追溯到2026回采快照的请求/完成时间及旧manifest原件记录，但采集时刻不能代替2023—2024的首次公开/接收时间。10组历史首可得、修订可得、最早模型使用时刻、原生字段ID均保留NULL；字段族和项目标准名不冒充供应商原字段映射已认证。

价格单位仅记录项目约定；成交量SDK映射是旧定义引用，不是供应商正式单位证书。原始响应的SHA明确标为manifest-recorded、本批未重哈希，也没有读取原始价量数组；不能用保存的哈希字符串冒充本批已重新核验内容。

日历保存的是已存官方休市人工转录计划，并非异常临时闭市全集。484个开市日关联旧条件行，但日级正常、官方限价、执行、完整费用及历史首次可得认证仍为0；月报没出现记录不能升级成全天正常，休市日没有个股状态记录也不填“正常”。公告日、候选生效日和完整历史规则链分开。

结论：固定来源的一遍工程整理已得到可查询结果，但这个来源集合没有恢复所需历史PIT及完整执行/费用证据。这里的“未找到”不是证明信息从未公布或任何渠道都不可能恢复；也不把未知填零或静默删日来制造完整率。

## 下一步与限制

按已冻结的工程任务书结束本次有限本地搜寻。下一批先设计有边界的前向首收/版本采集和质量拒绝流程，明确字段、时区、原件、修订、缺失、时点与保存；设计不等于开始采集，更不是预测上线、模拟开始或60日观察期起点。历史证据不因未来开始留日志而追认通过。

首版优先仍是收盘后回落买入vs等待；15组期限/确认/分配/费用等参数仍未冻结，累计16个研究定义及旧失败保留。2025/2026目标继续隔离，所有正式历史/current/runtime门保持关闭，没有当前买卖预测、采购、证券账户操作或资金使用。原库、旧代码、旧风险设置和批次02中间保存均保留。

本轮技术合并与独立核验只认证“元数据记录与已有证据对应”，不证明股票预测有效。[有限来源可恢复性结论](./有限来源可恢复性结论.json) · [访问范围登记](./访问范围登记.json) · [续作状态](./本轮状态与续作断点.json)。保存采用已有00:59全量包叠加本轮增量包，不每小时重复压缩全历史；最终恢复校验见项目外本轮增量归档结果。
'''
 guard();(OUT/'本轮推进报告.md').write_text(report)
 ck('15_metadata_source_hashes_unchanged_after_materialization',all(sha(ROOT/p)==h for p,h in source_hashes.items()))
 write(OUT/'本轮构建核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_hashes=source_hashes,record_counts=result,inputs_reused=True,extractors_rerun=False))
 write(OUT/'本轮状态与续作断点.json',dict(client_date='2026-11-04',origin='direct_human_resume_of_partial_b2',status='metadata_materialized_pending_independent_audit',research_stage=5,complete=False,counts_as_completed_nightly_batch=False,source_hashes=source_hashes,completed=['10-field/provider and729-day metadata SQLite materialized from stable saved products'],partial=['Final independent audit, release and incremental recovery verification pending'],blocked=['Historical first-availability/native mapping/units and full trading/cost evidence remain uncertified'],archive_summary=result,cumulative_registered_variants=16,new_real_labels=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,next_checkpoint=['Prepare bounded prospective first-receipt/version capture and quality-rejection design only, without live capture, targets, forecasts or simulation','Do not re-extract the completed fixed local source set, sweep14 optional columns or change15 pending parameters/risk settings'],old_pending_checkpoint_preserved=str(PENDING.relative_to(ROOT))+'/本轮状态与续作断点.json'))
 print(enc(dict(materialized=True,checks=len(checks),field_rows=10,calendar_rows=729,source_hashes=len(source_hashes))))

if __name__=='__main__':main()
