"""Reproducible integrity and coverage checks; does not certify completeness."""
import hashlib
import json
import sqlite3
from decimal import Decimal
from scope_config import read_scope
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    c = sqlite3.connect(ROOT/'高德红外_2023起.sqlite')
    c.row_factory = sqlite3.Row
    scope=read_scope(c)
    failed = []
    checks = {}
    checks['sqlite_integrity'] = c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    checks['daily_date_bounds'] = c.execute('SELECT COUNT(*) FROM current_daily_bars WHERE trade_date<? OR trade_date>?',(scope['start'],scope['end'])).fetchone()[0] == 0
    checks['record_date_bounds'] = c.execute('SELECT COUNT(*) FROM current_source_records WHERE reference_date<? OR reference_date>?',(scope['start'],scope['end'])).fetchone()[0] == 0
    checks['ohlc_consistency'] = c.execute('SELECT COUNT(*) FROM current_daily_bars WHERE low<=0 OR low>open OR low>close OR high<open OR high<close OR volume<0 OR amount<0 OR turnover<0').fetchone()[0] == 0
    checks['no_duplicate_source_dates'] = not list(c.execute('SELECT source,symbol,trade_date,COUNT(*) FROM current_daily_bars GROUP BY source,symbol,trade_date HAVING COUNT(*)>1'))
    checks['quality_issues_empty'] = c.execute('SELECT COUNT(*) FROM quality_issues').fetchone()[0] == 0
    hashes = []
    for r in c.execute('SELECT raw_path,sha256 FROM source_snapshots WHERE raw_path IS NOT NULL'):
        p = ROOT/r['raw_path']
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:
            hashes.append(r['raw_path'])
    checks['source_hashes_match'] = not hashes
    pdf_errors = []
    for r in c.execute('SELECT art_code,relative_path,sha256 FROM announcement_documents WHERE error IS NULL'):
        p = ROOT/r['relative_path']; payload = p.read_bytes() if p.exists() else b''
        if not payload.startswith(b'%PDF-') or hashlib.sha256(payload).hexdigest()!=r['sha256']:
            pdf_errors.append(r['art_code'])
    checks['pdf_headers_and_hashes_match'] = not pdf_errors
    em = {r['trade_date']:r for r in c.execute("SELECT * FROM current_daily_bars WHERE source='em_daily_0'")}
    tx = {r['trade_date']:r for r in c.execute("SELECT * FROM current_daily_bars WHERE source LIKE 'tencent_daily%'")}
    mismatch = [d for d in set(em)&set(tx) if any(abs(em[d][k]-tx[d][k])>0.005 for k in ('open','high','low','close','volume'))]
    checks['price_sources_date_sets_match'] = set(em)==set(tx)
    checks['unadjusted_ohlcv_sources_match'] = not mismatch
    scheduled={r[0] for r in c.execute('SELECT trade_date FROM trading_calendar WHERE is_scheduled_open=1')}
    checks['official_calendar_matches_daily_dates'] = scheduled==set(em)
    reconciliation=dict(c.execute('SELECT status,COUNT(*) FROM current_announcement_reconciliation GROUP BY status'))
    checks['cninfo_catalogue_all_matched'] = reconciliation.get('date_and_normalized_title_match')==308 and not reconciliation.get('cninfo_missing_in_eastmoney')
    checks['cninfo_investor_activity_all_matched'] = c.execute('SELECT COUNT(*) FROM current_announcement_ir_reconciliation').fetchone()[0]==4
    observations=list(c.execute('SELECT * FROM original_report_observations'))
    checks['original_report_observations_135'] = len(observations)==135 and len(set(r['art_code'] for r in observations))==15
    checks['original_report_evidence_hashes_match'] = all(c.execute('SELECT sha256 FROM announcement_documents WHERE art_code=?',(r['art_code'],)).fetchone()[0]==r['source_sha256'] for r in observations)
    checks['all_current_source_records_have_temporal_audit'] = c.execute("SELECT COUNT(*) FROM current_source_records r LEFT JOIN record_temporal_audit a ON r.snapshot_id=a.snapshot_id AND r.row_hash=a.row_hash AND a.audit_version='supplement-audit-v1' WHERE a.row_hash IS NULL").fetchone()[0]==0
    checks['unverified_records_not_approved_as_historical_inputs'] = c.execute('SELECT COUNT(*) FROM reviewed_historical_source_records').fetchone()[0]==0
    policy_errors=[]
    for r in c.execute('SELECT document_id,source_sha256,relative_path FROM public_document_samples'):
        p=ROOT/r['relative_path']
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['source_sha256']:policy_errors.append(r['document_id'])
    checks['policy_sample_hashes_match'] = not policy_errors
    checks['request_parameters_preserved_for_cninfo'] = c.execute("SELECT COUNT(*) FROM latest_successful_snapshots s LEFT JOIN source_requests r USING(snapshot_id) WHERE s.dataset LIKE 'cninfo_announcements%' AND (r.method!='POST' OR r.parameters_json IS NULL)").fetchone()[0]==0
    checks['forward_return_fields_restricted'] = c.execute("SELECT SUM(non_null_records) FROM restricted_source_fields WHERE reason='forward_return_statistic'").fetchone()[0]==318
    checks['corporate_action_originals_three_verified'] = c.execute('SELECT COUNT(*) FROM corporate_action_observations').fetchone()[0]==3
    checks['capital_share_components_sum'] = all(json.loads(r[0])['TOTAL_SHARES']==json.loads(r[0])['LIMITED_A_SHARES']+json.loads(r[0])['LISTED_A_SHARES'] for r in c.execute("SELECT payload_json FROM current_source_records WHERE dataset='capital_structure'"))
    primary=list(c.execute('SELECT * FROM primary_document_checks'))
    checks['primary_counterparts_22_identical'] = len(primary)==22 and all(r['comparison']=='identical_bytes' for r in primary)
    checks['primary_counterpart_files_hash_match'] = all((ROOT/r['relative_path']).exists() and hashlib.sha256((ROOT/r['relative_path']).read_bytes()).hexdigest()==r['source_sha256'] for r in primary)
    checks['text_retry_all_185_accounted'] = c.execute("SELECT COUNT(*) FROM announcement_text_retries WHERE status='still_empty_text_layer'").fetchone()[0]==185
    checks['candidate_events_remain_unapproved'] = c.execute('SELECT COUNT(*) FROM announcement_event_candidates WHERE historical_input_eligible!=0').fetchone()[0]==0
    checks['manual_fields_attached_to_original_hash'] = all(c.execute('SELECT sha256 FROM announcement_documents WHERE art_code=?',(r[0],)).fetchone()[0]==r[1] for r in c.execute('SELECT art_code,source_sha256 FROM manual_document_observations'))
    reviews=list(c.execute("SELECT * FROM announcement_candidate_reviews WHERE audit_version='round4-disclosure-audit-v1'"))
    checks['all_52_candidates_have_classification_review'] = len(reviews)==52 and {r['candidate_id'] for r in reviews}=={r[0] for r in c.execute('SELECT candidate_id FROM announcement_event_candidates')}
    checks['candidate_review_original_hashes_match'] = all(c.execute('SELECT source_sha256 FROM announcement_event_candidates WHERE candidate_id=?',(r['candidate_id'],)).fetchone()[0]==r['source_sha256'] for r in reviews)
    additions=list(c.execute("SELECT * FROM supplemental_disclosure_observations WHERE audit_version='round4-disclosure-audit-v1'"))
    checks['disclosure_reviews_remain_historical_unapproved'] = len(additions)==49 and all(r['historical_input_eligible']==0 for r in additions) and all(r['historical_input_eligible']==0 for r in reviews)
    checks['disclosure_evidence_pages_and_hashes_linked'] = c.execute('''SELECT COUNT(*) FROM supplemental_disclosure_evidence e LEFT JOIN announcement_pages p
       ON e.art_code=p.art_code AND e.page_number=p.page_number AND e.source_sha256=p.source_sha256 WHERE p.art_code IS NULL''').fetchone()[0]==0 and not list(c.execute('''SELECT o.observation_id FROM supplemental_disclosure_observations o LEFT JOIN supplemental_disclosure_evidence e
       ON o.observation_id=e.observation_id AND o.audit_version=e.audit_version GROUP BY o.observation_id,o.audit_version HAVING COUNT(e.art_code)=0'''))
    adjustment_rows=[json.loads(r['payload_json']) for r in additions if r['kind']=='accounting_adjustment']
    known=[r for r in adjustment_rows if r['before_decimal'] is not None]
    checks['accounting_24_known_before_values_add_correctly'] = len(known)==24 and all(Decimal(r['before_decimal'])+Decimal(r['adjustment_decimal'])==Decimal(r['after_decimal']) for r in known)
    checks['accounting_four_blank_before_values_remain_null'] = len(adjustment_rows)==28 and len([r for r in adjustment_rows if r['before_decimal'] is None])==4
    capitals=[json.loads(r['payload_json']) for r in additions if r['kind']=='capital_period']
    checks['eight_report_capital_observations_sum'] = len(capitals)==8 and all(r['total_shares']==r['limited_shares']+r['unlimited_shares'] and r['daily_effective_date'] is None and not r['daily_float_pit_eligible'] for r in capitals)
    transfers=[json.loads(r['payload_json']) for r in additions if r['kind']=='employee_nontrade_transfer']
    checks['three_employee_transfers_not_inferred_capital_creation'] = len(transfers)==3 and all(Decimal(r['shares_original'])*10000==r['shares'] and r['total_capital_change'] is None and r['unlimited_share_change'] is None for r in transfers)
    checks['existing_action_phases_not_duplicate_events'] = len([r for r in additions if r['kind']=='existing_action_phase'])==5 and all(json.loads(r['payload_json'])['new_independent_event_count']==0 for r in additions if r['kind']=='existing_action_phase')
    ocr=list(c.execute('SELECT * FROM announcement_ocr_texts'))
    pending_pages={tuple(r) for r in c.execute("SELECT art_code,page_number,source_sha256 FROM announcement_pages WHERE status='needs_ocr'")}
    checks['ocr_covers_all_185_original_pending_pages'] = len(ocr)==185 and {(r['art_code'],r['page_number'],r['source_sha256']) for r in ocr}==pending_pages
    checks['ocr_text_and_numbers_not_manually_approved'] = all(r['status']=='ocr_extracted_unverified' and r['text'].strip() and not json.loads(r['payload_json'])['numeric_facts_verified'] and not json.loads(r['payload_json'])['historical_input_eligible'] and json.loads(r['payload_json'])['manual_review_status']=='not_reviewed' for r in ocr)
    checks['ocr_result_archives_hash_match'] = all(hashlib.sha256((ROOT/r['relative_path']).read_bytes()).hexdigest()==r['result_sha256'] for r in c.execute('SELECT * FROM announcement_ocr_text_runs'))
    checks['available_machine_text_4253_pages_unique'] = c.execute('SELECT COUNT(*) FROM available_announcement_text').fetchone()[0]==4253 and not list(c.execute('SELECT art_code,page_number,source_sha256,COUNT(*) FROM available_announcement_text GROUP BY art_code,page_number,source_sha256 HAVING COUNT(*)>1'))
    checks['supplier_chip_data_still_not_fabricated'] = c.execute('SELECT COUNT(*) FROM chip_estimates').fetchone()[0]==0
    checks['active_index_calendar_dates_complete'] = all({r[0] for r in c.execute('SELECT trade_date FROM current_daily_bars WHERE source=?',(source,))}==scheduled for source in scope['index_sources'].values())
    latest_flows=list(c.execute('SELECT * FROM latest_available_fund_flow'))
    acquired_flow_dates={r[0] for r in c.execute("SELECT DISTINCT reference_date FROM source_records WHERE dataset='fund_flow_proxy'")}
    checks['rolling_fund_flow_history_retained_without_duplicate_dates'] = len(latest_flows)==len(acquired_flow_dates) and {r['trade_date'] for r in latest_flows}==acquired_flow_dates
    shareholders=list(c.execute('SELECT * FROM shareholder_history_observations'))
    checks['shareholder_rows_have_source_hashes_and_unapproved_times'] = len(shareholders)==170 and all(r['historical_input_eligible']==0 and json.loads(r['payload_json'])['source_sha256']==c.execute('SELECT sha256 FROM source_snapshots WHERE snapshot_id=?',(r['snapshot_id'],)).fetchone()[0] for r in shareholders)
    checks['shareholder_periodic_partial_lists_not_conflated'] = dict(c.execute('SELECT observation_scope,COUNT(*) FROM shareholder_history_observations GROUP BY observation_scope'))=={'periodic_top10':150,'nonperiodic_partial_holders_only':20}
    checks['shareholder_original_links_unapproved_and_hashed'] = c.execute('SELECT COUNT(*) FROM shareholder_disclosure_links').fetchone()[0]==3 and all(r[2]==0 and c.execute('SELECT sha256 FROM announcement_documents WHERE art_code=?',(r[0],)).fetchone()[0]==r[1] for r in c.execute('SELECT art_code,source_sha256,historical_input_eligible FROM shareholder_disclosure_links'))
    expected_index_differences={}
    for new_source,old_source in [('tencent_index_sh000001','index_1.000001'),('tencent_index_sz399001','index_0.399001')]:
        old={r['trade_date']:r for r in c.execute('SELECT * FROM current_daily_bars WHERE source=?',(old_source,))}
        new={r['trade_date']:r for r in c.execute('SELECT * FROM current_daily_bars WHERE source=?',(new_source,))}
        for day in set(old)&set(new):
            fields=[k for k in ('open','high','low','close','volume') if (old[day][k] is None)!=(new[day][k] is None) or
                    (old[day][k] is not None and new[day][k] is not None and abs(Decimal(str(old[day][k]))-Decimal(str(new[day][k])))>Decimal('0.005'))]
            if fields: expected_index_differences[(new_source,day)]={'old':old[day],'new':new[day],'fields':fields}
    retained_index_differences={(r['dataset'],r['reference_date']):r for r in c.execute("SELECT * FROM data_source_discrepancies WHERE run_id='refresh-20261015-v1'")}
    checks['index_discrepancies_retained_as_unresolved'] = set(expected_index_differences)==set(retained_index_differences) and all(
        retained_index_differences[key]['status']=='unresolved_provider_difference_originals_retained' and
        all(json.loads(retained_index_differences[key]['payload_json'])[version][field]==expected[version][field]
            for version in ('old','new') for field in expected['fields']) for key,expected in expected_index_differences.items())
    for key,passed in checks.items():
        if not passed: failed.append(key)
    report = dict(scope=scope,checks=checks,failed=failed,hash_errors=hashes,pdf_errors=pdf_errors,
                  common_dates=len(set(em)&set(tx)),price_mismatch_dates=mismatch,policy_hash_errors=policy_errors,
                  announcement_reconciliation=reconciliation,original_finance_observations=len(observations),
                  daily_coverage=[dict(r) for r in c.execute('SELECT source,adjustment,COUNT(*) n,MIN(trade_date) start,MAX(trade_date) end FROM current_daily_bars GROUP BY source,adjustment')],
                  dataset_coverage=[dict(r) for r in c.execute('SELECT dataset,COUNT(*) n,MIN(reference_date) start,MAX(reference_date) end FROM current_source_records GROUP BY dataset')],
                  pdf_status=dict(c.execute('SELECT CASE WHEN error IS NULL THEN "success" ELSE "failed" END,COUNT(*) FROM announcement_documents GROUP BY 1')),
                  text_status=dict(c.execute('SELECT status,COUNT(*) FROM announcement_pages GROUP BY status')),
                  ocr_text_status=dict(c.execute('SELECT status,COUNT(*) FROM announcement_ocr_texts GROUP BY status')),
                  supplemental_disclosures=dict(c.execute('SELECT kind,COUNT(*) FROM supplemental_disclosure_observations GROUP BY kind')),
                  retained_fund_flow_dates=len(latest_flows),shareholder_observations=len(shareholders),
                  index_difference_source_dates=len(expected_index_differences),
                  index_difference_fields=sum(len(r['fields']) for r in expected_index_differences.values()),
                  gaps=[dict(r) for r in c.execute('SELECT * FROM coverage_gaps')],
                  warning='Not certification of original disclosure truth, point-in-time vintages, complete news or source rights.')
    (ROOT/'质量核对结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'checks':checks,'common_dates':report['common_dates'],'pdf_status':report['pdf_status'],'text_status':report['text_status']},ensure_ascii=False,indent=2))
    c.close()
    if failed: raise SystemExit(1)


if __name__ == '__main__': main()
