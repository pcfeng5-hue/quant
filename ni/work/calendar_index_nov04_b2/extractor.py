"""Fixed-source calendar/status provenance index; no prices or target values.

Only the seven charter-registered JSON sources below may be read for content.
Full source objects are parsed, but numerical market/fee/quantity values are not
selected or exported. All dates/status facts are attributed to saved records,
not a new exchange certification or a reconstruction of individual fills.
"""
from pathlib import Path
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
from collections import Counter
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
START=datetime.fromisoformat('2026-11-04T06:00:38.423577+00:00')
SOURCES={
 'calendar_audit':'outputs/高德红外数据库/calendar_audit_result.json',
 'calendar_rows':'outputs/高德红外数据库/official_calendar_2023_to_20261015.json',
 'condition_summary':'work/conditions_finish_oct22/summary.json',
 'rule_regimes':'work/conditions_finish_oct22/rule_regimes.json',
 'daily_conditions':'work/conditions_finish_oct22/daily_trade_conditions_915.json',
 'corporate_action_dates':'work/corporate_actions_refine_oct17/corporate_actions.json',
 'label_contract':'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json'}
LO='2023-01-03';HI='2024-12-31';CONTEXT_LO='2023-01-01'

def guard():
 n=datetime.now(ZoneInfo('America/Toronto'))
 if n.hour>=5 or (n.hour==4 and n.minute>=45) or n.astimezone(timezone.utc)>START+timedelta(minutes=30):raise RuntimeError('Window/work deadline; preserve partial files and stop')
 return n
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 guard();p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def provenance(key,pointer,hashes):return dict(source_path=SOURCES[key],source_sha256=hashes[SOURCES[key]],json_pointer=pointer)
def main():
 started=guard();WORK.mkdir(exist_ok=True)
 hashes={p:sha(ROOT/p) for p in SOURCES.values()}
 data={k:json.loads((ROOT/p).read_text()) for k,p in SOURCES.items()}
 audit=data['calendar_audit'];calendar=data['calendar_rows'];conditions=data['daily_conditions'];regimes=data['rule_regimes']
 indexed_calendar={r['trade_date']:(i,r) for i,r in enumerate(calendar) if CONTEXT_LO<=r['trade_date']<=HI}
 indexed_conditions={r['trade_date']:(i,r) for i,r in enumerate(conditions) if LO<=r['trade_date']<=HI}
 indexed_rules={r['rule_id']:(i,r) for i,r in enumerate(regimes)}
 notices=audit['holiday_notices'];day=date.fromisoformat(CONTEXT_LO);end=date.fromisoformat(HI)
 all_dates=[]
 while day<=end:all_dates.append(day.isoformat());day+=timedelta(days=1)
 dates=[d for d in all_dates if d>=LO]
 output=[];actions=[]
 for i,r in enumerate(data['corporate_action_dates']):
  if not LO<=r.get('ex_date','')<=HI:continue
  actions.append(dict(event_id=r['event_id'],record_date=r.get('record_date'),ex_date=r['ex_date'],implementation_signature_date_candidate=r.get('implementation_signature_date'),first_publication_timestamp=r.get('first_publication_timestamp'),historical_feature_input_eligible=bool(r.get('historical_feature_input_eligible',False)),personal_receipt_verified=bool(r.get('trade_settlement_or_personal_receipt_verified',False)),provenance=provenance('corporate_action_dates',f'/{i}',hashes)))
 for d in all_dates:
  pair=indexed_calendar.get(d);ci,cr=pair if pair else (None,{})
  planned=bool(cr['is_scheduled_open']) if 'is_scheduled_open' in cr else None
  notice=notices.get(d[:4],{})
  # Original calendar is jointly scoped SSE,SZSE; retain that fact and select
  # only the stored SZSE notice URL for the target exchange's source index.
  szse_urls=[u for u in cr.get('source_urls',[]) if 'szse.cn' in u]
  if notice.get('szse_url') and notice['szse_url'] not in szse_urls:szse_urls.append(notice['szse_url'])
  pair=indexed_conditions.get(d);si,sr=pair if pair else (None,{})
  rule_pair=indexed_rules.get(sr.get('rule_id'));ri,rr=rule_pair if rule_pair else (None,{})
  has_status=si is not None
  row=dict(trade_date=d,target_exchange='SZSE',symbol='002414.SZ',planned_is_open=planned,
   calendar_evidence_status='SAVED_OFFICIAL_HOLIDAY_MANUAL_TRANSCRIPTION' if ci is not None else 'CALENDAR_RECORD_MISSING',
   original_calendar_exchange_scope=cr.get('exchange_scope'),calendar_version=cr.get('calendar_version'),is_weekend=cr.get('is_weekend'),is_announced_holiday=cr.get('is_announced_holiday'),closure_names=cr.get('closure_names'),
   szse_notice_urls=szse_urls,notice_published_date_candidate=notice.get('published_date'),notice_date_is_first_publication_certification=False,
   calendar_provenance=provenance('calendar_rows',f'/{ci}',hashes) if ci is not None else None,
   notice_metadata_provenance=provenance('calendar_audit','/holiday_notices/'+d[:4],hashes),
   calendar_source_audited_at_utc=audit.get('audited_at_utc'),calendar_unscheduled_closure_history_certified=False,
   stock_status_record_exists=has_status,stock_status_record_scope='SAVED_CONDITIONS_ROW_NOT_DAILY_NORMAL_CERTIFICATION' if has_status else 'NO_STATUS_RECORD_ON_PLANNED_CLOSED_DAY' if planned is False else 'STATUS_EVIDENCE_MISSING',
   condition_provenance=provenance('daily_conditions',f'/{si}',hashes) if has_status else None,
   selected_rule_id=sr.get('rule_id'),rule_effective_date_candidate=sr.get('rule_effective_date'),rule_publication_date_candidate=rr.get('published_date'),rule_review_status=rr.get('status'),rule_review_caveat=rr.get('caveat'),rule_change_chain_complete=False,
   rule_provenance=provenance('rule_regimes',f'/{ri}',hashes) if ri is not None else None,
   historical_st_status=sr.get('historical_st_status','UNKNOWN_NO_DAILY_RECORD'),intraday_suspension_status=sr.get('intraday_suspension_status','UNKNOWN_NO_DAILY_RECORD'),
   daily_status_verified_normal=sr.get('daily_status_verified_normal') if has_status else None,
   monthly_suspension_evidence=sr.get('monthly_suspension_evidence'),monthly_suspension_source_sha256=sr.get('suspension_month_source_sha256'),monthly_report_name=sr.get('month_report_name'),monthly_report_name_scope=sr.get('month_report_name_scope'),
   monthly_absence_certifies_daily_no_suspension=False,
   saved_positive_volume_flag=sr.get('observed_positive_day_volume'),saved_unadjusted_bar_available_flag=sr.get('unadjusted_daily_bar_available'),flags_recomputed_from_market_values=False,
   official_daily_limit_evidence_recorded=bool(sr.get('official_daily_upper_limit') is not None and sr.get('official_daily_lower_limit') is not None) if has_status else None,
   queue_or_fillability_status=sr.get('limit_up_queue_or_fillability','UNKNOWN_NO_DAILY_RECORD'),saved_execution_eligible=sr.get('execution_eligible') if has_status else None,saved_cost_model_complete=sr.get('cost_model_complete') if has_status else None,
   corporate_action_date_references=[dict(event_id=a['event_id'],provenance=a['provenance'],first_publication_timestamp=a['first_publication_timestamp'],historical_feature_input_eligible=a['historical_feature_input_eligible']) for a in actions if a['ex_date']==d],
   historical_first_available_timestamp=None,revision_first_available_timestamp=None,earliest_historical_model_use_timestamp=None,
   time_unknown_reason='Saved notice dates, rule dates and collection/audit timestamps do not certify all historical first-publication/receipt versions; no new source opened',
   formal_historical_input_approved=False,current_decision_approved=False,runtime_usable=False)
  output.append(row)
 context_only=[dict(r,context_only=True,counts_toward_main_scope=False) for r in output if r['trade_date']<LO]
 output=[r for r in output if r['trade_date']>=LO]
 open_rows=[r for r in output if r['planned_is_open'] is True]
 checks=[]
 def ck(name,ok,detail=None):checks.append(dict(check=name,passed=bool(ok),details=detail));assert ok,name
 ck('seven_registered_content_sources_only',len(SOURCES)==7)
 ck('729_main_calendar_days_exact_order_and_unique',[r['trade_date'] for r in output]==dates and len(dates)==729 and len(set(dates))==729)
 ck('two_prior_calendar_days_context_only_not_scope',len(context_only)==2 and [r['trade_date'] for r in context_only]==['2023-01-01','2023-01-02'] and all(r['counts_toward_main_scope'] is False and r['planned_is_open'] is False for r in context_only))
 ck('saved_calendar_has_no_missing_target_dates',len(indexed_calendar)==731 and all(r['calendar_provenance'] is not None for r in output))
 ck('no_duplicate_calendar_dates',len([r for r in calendar if CONTEXT_LO<=r['trade_date']<=HI])==len(indexed_calendar))
 ck('no_duplicate_condition_dates',len([r for r in conditions if LO<=r['trade_date']<=HI])==len(indexed_conditions))
 ck('484_planned_open_242_each_year',len(open_rows)==484 and Counter(r['trade_date'][:4] for r in open_rows)=={'2023':242,'2024':242})
 ck('245_main_planned_closed_days_retained',sum(r['planned_is_open'] is False for r in output)==245)
 ck('condition_record_dates_match_planned_open_dates',set(indexed_conditions)=={r['trade_date'] for r in open_rows})
 ck('no_closed_day_status_certification',all(r['stock_status_record_exists'] is False and r['daily_status_verified_normal'] is None for r in output if r['planned_is_open'] is False))
 ck('calendar_scope_not_rewritten_as_szse_only',all(r['original_calendar_exchange_scope']=='SSE,SZSE' for r in output))
 ck('every_date_has_only_szse_notice_urls',all(r['szse_notice_urls'] and all('szse.cn' in u for u in r['szse_notice_urls']) for r in output))
 ck('publication_candidate_is_not_first_available',all(r['notice_date_is_first_publication_certification'] is False and r['historical_first_available_timestamp'] is None and r['revision_first_available_timestamp'] is None and r['earliest_historical_model_use_timestamp'] is None for r in output))
 ck('two_historical_rule_families_no_2026_backfill',{r['selected_rule_id'] for r in open_rows}=={'SZSE_2021_SELECTED_A_SHARE_PROVISIONS','SZSE_2023'})
 ck('every_open_row_rule_effective_by_its_date',all(r['rule_effective_date_candidate']<=r['trade_date'] and not r['rule_change_chain_complete'] for r in open_rows))
 ck('all484_daily_normal_flags_false_not_monthly_upgraded',all(r['daily_status_verified_normal'] is False and not r['monthly_absence_certifies_daily_no_suspension'] for r in open_rows))
 ck('official_limit_evidence_unverified_without_numeric_export',all(r['official_daily_limit_evidence_recorded'] is False for r in open_rows))
 ck('all484_saved_execution_and_cost_flags_false',all(r['saved_execution_eligible'] is False and r['saved_cost_model_complete'] is False for r in open_rows))
 ck('no_actual_volume_recheck_or_stock_normal_inference',all(r['flags_recomputed_from_market_values'] is False for r in output))
 ck('two_corporate_action_dates_only_no_terms_or_amounts',len(actions)==2 and {a['ex_date'] for a in actions}=={'2023-06-20','2024-05-24'} and all(a['first_publication_timestamp'] is None and a['historical_feature_input_eligible'] is False for a in actions))
 ck('all_formal_current_runtime_gates_false',all(r['formal_historical_input_approved'] is False and r['current_decision_approved'] is False and r['runtime_usable'] is False for r in output))
 prohibited={'conditional_reference_close','candidate_normal_upper_limit','candidate_normal_lower_limit','official_daily_upper_limit','official_daily_lower_limit','stamp_tax_sell_rate','exchange_handling_each_side_rate','regulatory_each_side_rate_candidate','transfer_each_side_rate_candidate','cash_cny_per_10_shares_gross','transfer_shares_per_10','close','open','high','low','volume','outcome_sign','price_change_fraction','p','y'}
 ck('no_price_fee_corporate_amount_target_or_probability_fields_exported',all(not(prohibited&set(r)) for r in output) and all(not(prohibited&set(r)) for r in actions))
 ck('all_7_source_hashes_unchanged',{p:sha(ROOT/p) for p in SOURCES.values()}==hashes)
 manifest={key:dict(path=path,sha256=hashes[path],content_read_registered=True) for key,path in SOURCES.items()}
 summary=dict(target_period=[LO,HI],natural_days=729,context_only_prior_calendar_days=2,planned_open_days=484,planned_closed_days=245,planned_open_days_by_year=dict(Counter(r['trade_date'][:4] for r in open_rows)),saved_condition_records=484,missing_condition_records_on_open_days=0,daily_verified_normal_count=0,official_limit_evidence_count=0,saved_execution_eligible_count=0,saved_complete_cost_model_count=0,historical_first_availability_certified_count=0,corporate_action_dates_indexed=2,
  interpretation='Calendar is a saved official-holiday manual-transcription plan, not proof of unscheduled closure absence, stock normal trading, legal orders or fills. Source state flags are copied, not newly certified.')
 result=dict(index_id='002414_SZSE_planned_calendar_status_sources_2023_2024_20261104_b2',status='engineering_source_index_not_runtime_whitelist',created_at_utc=datetime.now(timezone.utc).isoformat(),source_manifest=manifest,summary=summary,all_calendar_days=output,planned_open_daily_index=open_rows,context_only_prior_calendar_days=context_only,corporate_action_date_index=actions,
  source_calendar_limitations=audit['limitations'],source_condition_summary_provenance=provenance('condition_summary','/',hashes),source_status_certification_counts_retained={k:data['condition_summary'][k] for k in ['actual_daily_verified_normal_count','official_daily_limit_price_count','execution_eligible_count','complete_account_cost_model_count']},
  no_new_real_labels=True,new_market_data=False,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,formal_historical_input_approved=False,current_decision_approved=False,runtime_usable=False)
 guard();write(WORK/'calendar_status_index.json',result)
 write(WORK/'checks.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_sha256_before=hashes,source_sha256_after={p:sha(ROOT/p) for p in SOURCES.values()},summary=summary,started_at_local=started.isoformat(),finished_at_local=guard().isoformat(),target_or_price_database_queries=0,new_market_or_real_target_values_exported=0))
 print(json.dumps(dict(summary=summary,checks=len(checks),output=str(WORK/'calendar_status_index.json')),ensure_ascii=False))

if __name__=='__main__':main()
