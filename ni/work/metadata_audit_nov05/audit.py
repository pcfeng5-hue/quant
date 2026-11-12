"""Independent read-only metadata materialization audit. No market/target queries."""
from pathlib import Path
from datetime import date,timedelta,datetime,timezone
import hashlib,json,re,sqlite3
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/输入证据合库与验证设计_20261105'
OLD=ROOT/'outputs/最小输入证据台账_20261104_批次02'
checks=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def check(name,condition,detail=None):
 checks.append(dict(check=name,passed=bool(condition),details=detail))
def norm(v):return int(v) if isinstance(v,bool) else v
charter=read(ROOT/'outputs/下一阶段路线决策_20261104/下一批有限工程任务书.json')
allowed=charter['local_source_paths']
source_hashes={p:sha(ROOT/p) for p in allowed}
state=read(OLD/'本轮状态与续作断点.json')
f=read(OLD/'字段时点与版本台账_待独立复核.json')
d=read(OLD/'计划日与状态来源索引_待独立复核.json')
check('15_registered_sources',len(allowed)==len(set(allowed))==15)
check('14_prior_fingerprints_match',len(state['source_hashes'])==14 and all(source_hashes[p]==h for p,h in state['source_hashes'].items()))
check('4_prior_artifact_fingerprints',len(state['artifact_sha256'])==4 and all(sha(OLD/p)==h for p,h in state['artifact_sha256'].items()))
field_src=f['field_provider_rows'];day_src=d['all_calendar_days'];ctx_src=d['context_only_prior_calendar_days'];act_src=d['corporate_action_date_index']
used=set(f['fixed_content_source_paths'])|{r['path'] for r in d['source_manifest'].values()}
check('14_used_registered_only_no_extra',len(used)==14 and used<=set(allowed) and f['extra_content_source_paths']==[])
log=read(OUT/'访问范围登记.json')
check('access_log_concordance',set(log['actual_reused_scientific_content_sources'])==used and log['unused_registered_path']==sorted(set(allowed)-used) and log['extra_paths_used']==[] and log['original_extractor_rerun'] is False and log['source_integrity_hashes']==source_hashes)
check('copied_fields_identical',sha(OLD/'字段时点与版本台账_待独立复核.json')==sha(OUT/'字段时点与版本台账.json'))
check('copied_calendar_identical',sha(OLD/'计划日与状态来源索引_待独立复核.json')==sha(OUT/'计划日与状态来源索引.json'))
p=OUT/'最小输入证据台账.sqlite';before=sha(p)
c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
c.execute('PRAGMA query_only=ON')
check('read_only_query_only',c.execute('PRAGMA query_only').fetchone()[0]==1)
check('SQLite_quick_check',c.execute('PRAGMA quick_check').fetchall()[0][0]=='ok')
tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
check('exact_metadata_tables',tables=={'field_evidence','calendar_days','context_calendar_days','corporate_action_dates','source_registry','metadata'})
rows={n:[dict(r) for r in c.execute('select * from '+n+' order by rowid')] for n in tables}
for n,old,key in [('field_evidence',field_src,'evidence_id'),('calendar_days',day_src,'trade_date'),('context_calendar_days',ctx_src,'trade_date'),('corporate_action_dates',act_src,'event_id')]:
 decoded=[json.loads(r['record_json']) for r in rows[n]]
 check(n+'_record_json_exact',decoded==old)
 check(n+'_unique_keys',len({r[key] for r in rows[n]})==len(rows[n]))
# Independently specify projection from original records, rather than importing builder.
fm={
 'evidence_id':lambda r:r['evidence_id'],'field_family':lambda r:r['field_family'],'provider':lambda r:r['provider'],
 'source_metadata_path':lambda r:r['snapshot_source_reference']['path'],'source_metadata_sha256':lambda r:r['snapshot_source_reference']['sha256'],
 'json_locator':lambda r:r['snapshot_source_reference']['json_locator'],'collected_at_utc_recorded':lambda r:r['collected_at_utc_recorded'],
 'historical_first_available_at':lambda r:r['historical_first_available_at'],'historical_revision_available_at':lambda r:r['historical_revision_available_at'],
 'earliest_model_use_timestamp':lambda r:r['earliest_model_use_timestamp'],'native_field_identifier':lambda r:r['native_field_identifier'],
 'unit_status_json':lambda r:r['unit_status'],'formal_historical_input_approved':lambda r:norm(r['formal_historical_input_approved']),
 'current_decision_approved':lambda r:norm(r['current_decision_approved']),'runtime_usable':lambda r:norm(r['runtime_usable'])}
projection_cells=0
for col,getter in fm.items():
 check('field_column_'+col,all((json.loads(db[col]) if col=='unit_status_json' else db[col])==getter(src) for db,src in zip(rows['field_evidence'],field_src)))
 projection_cells+=len(field_src)
calendar_columns=['trade_date','planned_is_open','stock_status_record_exists','historical_st_status','daily_status_verified_normal','official_daily_limit_evidence_recorded','saved_execution_eligible','saved_cost_model_complete','historical_first_available_timestamp','formal_historical_input_approved','current_decision_approved','runtime_usable']
for table,src in [('calendar_days',day_src),('context_calendar_days',ctx_src)]:
 for col in calendar_columns:
  check(table+'_column_'+col,all(db[col]==norm(raw[col]) for db,raw in zip(rows[table],src)))
  projection_cells+=len(src)
for col in ['event_id','record_date','ex_date']:
 check('action_column_'+col,all(db[col]==raw[col] for db,raw in zip(rows['corporate_action_dates'],act_src)))
 projection_cells+=len(act_src)
check('exact_10_field_provider_pairs',len(rows['field_evidence'])==10 and {(r['field_family'],r['provider']) for r in rows['field_evidence']}=={(x,y) for x in ['raw_open','raw_high','raw_low','raw_close','raw_volume'] for y in ['eastmoney','tencent']})
expected_dates=[(date(2023,1,3)+timedelta(days=i)).isoformat() for i in range((date(2024,12,31)-date(2023,1,3)).days+1)]
check('729_contiguous_main_dates',len(day_src)==729 and [r['trade_date'] for r in rows['calendar_days']]==expected_dates)
check('484_open_245_closed',sum(r['planned_is_open']==1 for r in rows['calendar_days'])==484 and sum(r['planned_is_open']==0 for r in rows['calendar_days'])==245)
check('two_context_excluded',len(ctx_src)==2 and [r['trade_date'] for r in ctx_src]==['2023-01-01','2023-01-02'] and all(r['context_only'] is True and r['counts_toward_main_scope'] is False for r in ctx_src))
check('two_company_actions',len(act_src)==2 and all(r['first_publication_timestamp'] is None and r['historical_feature_input_eligible'] is False for r in act_src))
view=[dict(r) for r in c.execute('select * from planned_open_status order by trade_date')]
check('open_view_exact_all_columns',view==[r for r in rows['calendar_days'] if r['planned_is_open']==1])
for col in ['historical_first_available_at','historical_revision_available_at','earliest_model_use_timestamp','native_field_identifier']:
 check('field_unknown_NULL_'+col,all(r[col] is None for r in rows['field_evidence']))
check('field_units_uncertified',all(r['unit_status']['provider_native_unit_certified'] is None and r['unit_status']['conversion_is_formal_vendor_certification'] is False and r['unit_status']['unknown_reason'] for r in field_src))
check('all_formal_current_runtime_closed',all(r[k]==0 for n in ['field_evidence','calendar_days','context_calendar_days'] for r in rows[n] for k in ['formal_historical_input_approved','current_decision_approved','runtime_usable']))
check('all_daily_certifications_zero',all(r[k] is not True and r[k] != 1 for r in day_src+ctx_src for k in ['daily_status_verified_normal','official_daily_limit_evidence_recorded','saved_execution_eligible','saved_cost_model_complete','monthly_absence_certifies_daily_no_suspension']))
check('closed_days_missing_status_is_NULL',all(r['daily_status_verified_normal'] is None and r['saved_execution_eligible'] is None and r['historical_st_status']=='UNKNOWN_NO_DAILY_RECORD' for r in day_src+ctx_src if not r['planned_is_open']))
check('plan_not_observation_or_status_certification',all(r['calendar_evidence_status']=='SAVED_OFFICIAL_HOLIDAY_MANUAL_TRANSCRIPTION' and r['calendar_unscheduled_closure_history_certified'] is False and r['notice_date_is_first_publication_certification'] is False for r in day_src+ctx_src))
check('raw_response_only_recorded_not_verified',all(r['raw_response_content_read_this_batch'] is False and r['raw_response_rehashed_this_batch'] is False and r['raw_response_integrity_evidence']=='MANIFEST_RECORDED_ONLY_NOT_REHASHED_IN_THIS_SUBTASK' and re.fullmatch('[0-9a-f]{64}',r['raw_response_sha256_recorded']) for r in field_src))
check('source_registry_all_columns',len(rows['source_registry'])==15 and {r['path']:r['sha256'] for r in rows['source_registry']}==source_hashes and all(r['content_extracted_in_prior_pass']==int(r['path'] in used) and r['source_kind']=='registered_local_metadata_or_status_document' for r in rows['source_registry']))
run=json.loads(rows['metadata'][0]['value_json'])
check('run_metadata_one_row',len(rows['metadata'])==1 and rows['metadata'][0]['key']=='run')
check('metadata_no_market_target_model_score',all(run[k]==0 for k in ['actual_numeric_market_rows','new_real_labels','new_models','new_scores']) and all(run[k] is False for k in ['formal_input_approved','current_decision_approved','runtime_usable','outcomes_2025_2026_opened']) and run['charter_id']==charter['charter_id'])
# Resolve only reference locations in the registered metadata documents. Never open raw_path.
cache={}
def source(path):
 assert path in allowed,path
 if path not in cache:cache[path]=read(ROOT/path)
 return cache[path]
def locate(obj,ptr):
 if ptr.startswith('/'):
  tokens=[x.replace('~1','/').replace('~0','~') for x in ptr[1:].split('/')]
 elif ptr.startswith('$'):
  tokens=re.findall(r'\.([^\.\[\]]+)|\[(\d+)\]',ptr[1:]);tokens=[a or b for a,b in tokens]
 else:raise ValueError(ptr)
 for t in tokens:obj=obj[int(t)] if isinstance(obj,list) else obj[t]
 return obj
refs=[]
def walk(x):
 if isinstance(x,dict):
  if {'source_path','source_sha256','json_pointer'}<=x.keys():refs.append((x['source_path'],x['source_sha256'],x['json_pointer']))
  if {'path','sha256','json_locator'}<=x.keys():refs.append((x['path'],x['sha256'],x['json_locator']))
  for y in x.values():walk(y)
 elif isinstance(x,list):
  for y in x:walk(y)
for xs in [field_src,day_src,ctx_src,act_src]:walk(xs)
resolved=0;errors=[]
for path,h,ptr in refs:
 try:
  assert path in allowed and h==source_hashes[path]
  locate(source(path),ptr);resolved+=1
 except Exception as e:errors.append(dict(path=path,pointer=ptr,error=repr(e)))
check('all_registered_JSON_references_resolve',len(refs)>2400 and not errors,dict(total=len(refs),resolved=resolved,errors=errors))
manifest=source('work/market_industry_oct22/manifest.json')
check('provider_snapshot_manifest_concordance',all((lambda m:m['raw_path']==r['raw_response_path_recorded'] and m['sha256']==r['raw_response_sha256_recorded'] and m['url']==r['original_request_url'] and m['requested_at_utc']==r['requested_at_utc_recorded'] and m['finished_at_utc']==r['collected_at_utc_recorded'])(locate(manifest,r['snapshot_source_reference']['json_locator'])) for r in field_src))
c.close()
check('readonly_DB_hash_unchanged',sha(p)==before)
check('all_15_source_hashes_unchanged',all(sha(ROOT/p)==h for p,h in source_hashes.items()))
result=dict(audit_id='independent_metadata_projection_20261105',created_at_utc=datetime.now(timezone.utc).isoformat(),independent_from_builder=True,all_checks_passed=all(x['passed'] for x in checks),passed=sum(x['passed'] for x in checks),total=len(checks),checks=checks,declared_projection_cells_checked=projection_cells,reference_locations_checked=len(refs),database_sha256=before,source_hashes=source_hashes,scientific_sources_read=sorted(cache),raw_price_responses_read=False,target_databases_read=False,new_labels=0,new_models=0,new_scores=0,outcomes_2025_2026_opened=False,interpretation='Certifies metadata source/NULL/projection correspondence only; no historical PIT, execution/cost or predictive certification.')
(WORK/'独立复核.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(WORK/'独立复核.md').write_text(f'''# 元数据合库独立复核

2026年11月5日。只读SQLite，未导入或调用合库脚本；逐列从旧JSON独立构造对应关系。

结果：{result['passed']}/{result['total']}检查通过；声明列对应{projection_cells}个单元，来源定位{len(refs)}项。包含10组字段、729主范围日期（484计划开市/245计划休市）、2上下文日、2公司行动、15来源。全部record_json与旧提取物完全对应，SQL声明列与原记录逐列对应。NULL、未认证和正式/current/runtime关闭状态未被填0或升级。

旧14已用来源hash与中间状态一致，15登记来源在复核前后未变。原行情响应SHA只核对清单记录，未打开或重新计算原行情响应；没有查询目标库、新增标签、模型或评分，2025/2026目标未打开。

本核验认证工程对应，不认证历史当时可得、完整交易/成本、可成交或概率预测有效性。详细证据见同目录JSON和audit.py。
''')
print(json.dumps({k:result[k] for k in ['all_checks_passed','passed','total','declared_projection_cells_checked','reference_locations_checked','database_sha256']},ensure_ascii=False))
if not result['all_checks_passed']:raise SystemExit(1)
