"""Extract a ten-row metadata evidence ledger from seven fixed saved documents.

No raw market response, price table, target database, network, model or score is
opened. Manifest-recorded raw response hashes are citations, not hashes verified
by this extractor. Unknown history/units/mapping facts are retained as NULL.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import Counter
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
START = datetime.fromisoformat('2026-11-04T06:00:38.423577+00:00')
SOURCES = [
    'work/market_industry_oct22/manifest.json',
    'work/market_industry_oct22/input_admission.json',
    'work/market_context_oct31/contract.json',
    'outputs/统一数据底座_20261022/数据使用与准入规范.json',
    'work/market_warmup_finalize_oct22/manifest.json',
    'work/market_warmup_finalize_oct22/summary.json',
    'work/baseline_oct25/engineering_contract.json',
]
FIELDS = ['raw_open', 'raw_high', 'raw_low', 'raw_close', 'raw_volume']


def guard():
    now = datetime.now(ZoneInfo('America/Toronto'))
    if now.hour >= 5 or (now.hour == 4 and now.minute >= 45):
        raise RuntimeError('Outside permitted research window')
    if now.astimezone(timezone.utc) > START + timedelta(minutes=30):
        raise RuntimeError('Work reserve reached: save/verify only, no new extraction')
    return now


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp(value):
    # This validates the recorded collection stamp, never historical availability.
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('Naive recorded collection timestamp')
    return parsed


def ref(path, locator, source_hashes):
    return dict(path=path, sha256=source_hashes[path], json_locator=locator,
                reference_type='saved_metadata_document')


def main():
    now = guard()
    before = {path: sha(ROOT/path) for path in SOURCES}
    # One fixed content pass. Do not dereference raw_path, sdk_unit_source,
    # verification_path, source_database, or any URL contained in these objects.
    documents = {path: json.loads((ROOT/path).read_text()) for path in SOURCES}
    manifest = documents[SOURCES[0]]
    admission = documents[SOURCES[1]]
    prep = documents[SOURCES[2]]
    contract = documents[SOURCES[3]]
    warm_manifest = documents[SOURCES[4]]
    warm_summary = documents[SOURCES[5]]
    old_engineering = documents[SOURCES[6]]
    checks = []

    def ck(name, passed, details=None):
        checks.append(dict(check=name, passed=bool(passed), details=details))
        if not passed:
            raise AssertionError(name)

    selected = [(i, row) for i, row in enumerate(manifest['results'])
                if row.get('symbol') == '002414.SZ'
                and row.get('adjustment') == '0']
    ck('exact_two_saved_unadjusted_stock_snapshot_pointers',
       len(selected) == 2 and {r['provider'] for _, r in selected} == {'eastmoney','tencent'})
    ck('primary_and_comparison_roles_match_saved_preparation',
       prep['primary_provider'] == 'eastmoney' and prep['comparison_provider'] == 'tencent')
    ck('historical_first_availability_is_explicitly_unknown',
       admission['historical_first_availability_timestamp'] is None
       and not prep['historical_first_availability_certified'])
    ck('saved_admission_and_runtime_not_approved',
       admission['model_usable'] is False
       and prep['formal_historical_model_input_approved'] is False
       and prep['runtime_usable'] is False)
    expected_old_fields = ['open', 'high', 'low', 'close', 'volume_provider_native']
    ck('saved_project_comparison_names_all_five_fields',
       warm_summary['unadjusted_cross_source']['comparison_fields'] == expected_old_fields)
    ck('source_scope_2023_2024_only_is_old_development_definition',
       old_engineering['development_start'] == '2023-01-03'
       and old_engineering['development_end'] == '2024-12-31')
    ck('temporal_contract_forbids_capture_time_as_historical_proof',
       contract['temporal_contract']['null_time_is_not_midnight'] is True
       and 'now only' in contract['temporal_contract']['first_availability'])

    rows = []
    selected_manifest_pointers = []
    for index, snapshot in selected:
        provider = snapshot['provider']
        ck('recorded_stamp_order_'+provider,
           stamp(snapshot['requested_at_utc']) <= stamp(snapshot['finished_at_utc']))
        ck('recorded_manifest_hash_shape_'+provider,
           bool(re.fullmatch(r'[0-9a-f]{64}', snapshot['sha256'])))
        ck('manifest_endpoint_dates_encompass_metadata_scope_'+provider,
           snapshot['min_date'] <= '2023-01-03' <= '2024-12-31' <= snapshot['max_date'])
        ck('stock_snapshot_request_success_metadata_'+provider,
           snapshot['error'] is None and snapshot['status'] == 200
           and snapshot['rejected_rows'] == 0)
        selected_manifest_pointers.append(dict(
            provider=provider, manifest_path=SOURCES[0], json_locator=f'$.results[{index}]',
            raw_path_recorded=snapshot['raw_path'], raw_sha256_recorded=snapshot['sha256'],
            raw_content_read=False, raw_sha256_rehashed_this_batch=False,
            original_request_url=snapshot['url'],
            requested_at_utc_recorded=snapshot['requested_at_utc'],
            finished_at_utc_recorded=snapshot['finished_at_utc']))
        for field, normalized in zip(FIELDS, expected_old_fields):
            unit_ref = ref(SOURCES[3], '$.units_and_adjustment.stock_volume', before)
            if field == 'raw_volume':
                unit_status = dict(
                    provider_native_unit_certified=None,
                    project_convention='provider-native stock volume; SDK-explained hands × 100 to shares',
                    unit_definition_evidence='saved project contract quoting an inspected SDK mapping, not a formal provider contract',
                    conversion_is_formal_vendor_certification=False,
                    conversion_expression='native_hands * 100 = shares only under declared SDK convention',
                    sdk_source_url_recorded=warm_summary['sdk_unit_source'],
                    sdk_source_opened_this_batch=False,
                    source_reference=unit_ref,
                    unknown_reason='No formal per-endpoint provider unit contract in the fixed seven-source set; retain native precision and unit-status boundary.')
            else:
                unit_status = dict(
                    provider_native_unit_certified=None,
                    project_convention='unadjusted stock price per share; CNY/share project convention, not vendor-certified in this batch',
                    unit_definition_evidence='saved stock-snapshot identity and project raw-price handling; fixed sources do not supply a formal per-field provider unit definition',
                    conversion_is_formal_vendor_certification=False,
                    conversion_expression=None,
                    sdk_source_url_recorded=None,
                    sdk_source_opened_this_batch=False,
                    source_reference=ref(SOURCES[6], '$.price_handling', before),
                    unknown_reason='Provider-certified field currency/price-scale definition was not found in this bounded metadata set; do not elevate project convention into certification.')
            rows.append(dict(
                evidence_id=f'002414.SZ::{provider}::{field}',
                symbol='002414.SZ', field_family=field,
                provider=provider,
                provider_role='saved_primary' if provider == 'eastmoney' else 'saved_comparison',
                adjustment='0_unadjusted',
                requested_metadata_period=['2023-01-03','2024-12-31'],
                normalized_project_field_name=normalized,
                native_field_identifier=None,
                native_field_mapping_status='PROJECT_NORMALIZED_NAME_ONLY_NATIVE_MAPPING_NOT_CERTIFIED',
                native_field_mapping_unknown_reason='Manifest records response key and requested provider field list, but fixed seven-source documents do not individually certify this field-to-native-code/array-position map.',
                snapshot_source_reference=ref(SOURCES[0], f'$.results[{index}]', before),
                normalized_field_presence_reference=ref(SOURCES[5], '$.unadjusted_cross_source.comparison_fields', before),
                original_request_url=snapshot['url'],
                response_key_recorded=snapshot['response_key'],
                raw_response_path_recorded=snapshot['raw_path'],
                raw_response_sha256_recorded=snapshot['sha256'],
                raw_response_integrity_evidence='MANIFEST_RECORDED_ONLY_NOT_REHASHED_IN_THIS_SUBTASK',
                raw_response_content_read_this_batch=False,
                raw_response_rehashed_this_batch=False,
                requested_at_utc_recorded=snapshot['requested_at_utc'],
                collected_at_utc_recorded=snapshot['finished_at_utc'],
                collection_stamp_precision='explicit-offset saved request/completion timestamp',
                collection_stamp_is_historical_first_availability=False,
                snapshot_observed_date_bounds_recorded=[snapshot['min_date'], snapshot['max_date']],
                snapshot_accepted_source_rows_recorded=snapshot['accepted_rows'],
                scope_coverage_kind='Manifest date endpoints encompass requested metadata period; this extractor does not rebuild per-date raw rows or certify an exchange calendar.',
                source_vintage_kind='2026 retrospective provider snapshot recorded by project manifest',
                historical_first_available_at=None,
                historical_revision_available_at=None,
                earliest_model_use_timestamp=None,
                historical_time_precision=None,
                historical_time_evidence_status='UNKNOWN_NO_HISTORICAL_FIRST_AVAILABILITY_OR_REVISION_CHAIN',
                historical_time_unknown_reason=admission['price_snapshot_timing'],
                point_in_time_evidence_reference=ref(SOURCES[1], '$.historical_first_availability_timestamp', before),
                revision_status='Known recent snapshot comparisons and current source agreement cannot establish the 2023–2024 vintage or exact first-publication time.',
                unit_status=unit_status,
                decision_timestamp=None,
                eligible_at_historical_decision=None,
                evidence_kind='SAVED_MANIFEST_AND_PROJECT_CONTRACT_METADATA_ONLY',
                historical_first_availability_certified=False,
                formal_historical_input_approved=False,
                current_decision_approved=False,
                runtime_usable=False,
                actual_numeric_market_values_exported=False,
                actual_outcome_labels_exported=False,
            ))

    # Optional historical manifest citations are selected by their recorded date
    # ranges only. They are not read as raw files and do not add observations.
    previous_vintage_records=[]
    for index,snapshot in enumerate(warm_manifest['results']):
        if snapshot.get('adjustment_flag')!='0':
            continue
        if snapshot.get('provider') not in {'eastmoney','tencent'}:
            continue
        if snapshot.get('max_date','') < '2023-01-03' or snapshot.get('min_date','') > '2024-12-31':
            continue
        previous_vintage_records.append(dict(
            manifest_path=SOURCES[4], json_locator=f'$.results[{index}]',
            provider=snapshot['provider'], recorded_name=snapshot['name'],
            response_key_recorded=snapshot['response_key'],
            captured_at_utc_recorded=snapshot['finished_at_utc'],
            raw_path_recorded=snapshot['raw_path'],raw_sha256_recorded=snapshot['sha256'],
            recorded_date_bounds=[snapshot['min_date'],snapshot['max_date']],
            raw_content_read=False,raw_hash_reverified=False,
            proves_historical_revision_release_at=False))

    ck('exact_10_unique_field_provider_rows',len(rows)==10 and len({r['evidence_id'] for r in rows})==10)
    ck('complete_5_by_2_grid',Counter(r['provider'] for r in rows)=={'eastmoney':5,'tencent':5} and Counter(r['field_family'] for r in rows)=={f:2 for f in FIELDS})
    ck('all_unknown_history_and_native_mapping_preserved',all(r['historical_first_available_at'] is None and r['historical_revision_available_at'] is None and r['earliest_model_use_timestamp'] is None and r['native_field_identifier'] is None and r['eligible_at_historical_decision'] is None for r in rows))
    ck('all_formal_current_runtime_gates_remain_false',all(not r['historical_first_availability_certified'] and not r['formal_historical_input_approved'] and not r['current_decision_approved'] and not r['runtime_usable'] for r in rows))
    ck('no_original_raw_response_content_or_hash_read',all(not r['raw_response_content_read_this_batch'] and not r['raw_response_rehashed_this_batch'] for r in rows))
    ck('no_actual_market_values_or_outcome_export',all(not r['actual_numeric_market_values_exported'] and not r['actual_outcome_labels_exported'] for r in rows))
    ck('formal_provider_units_not_invented',all(r['unit_status']['provider_native_unit_certified'] is None and not r['unit_status']['conversion_is_formal_vendor_certification'] for r in rows))
    ck('capture_stamps_never_substituted_for_history',all(not r['collection_stamp_is_historical_first_availability'] for r in rows))
    after={path:sha(ROOT/path) for path in SOURCES}
    ck('seven_fixed_metadata_sources_unchanged',before==after)
    guard()
    result=dict(
        extraction_id='002414_five_raw_field_families_two_saved_providers_20261104_b2',
        client_date='2026-11-04',created_at_utc=now.astimezone(timezone.utc).isoformat(),
        scope='Fixed local metadata ledger only; no raw response, target database or network opened',
        requested_metadata_period=['2023-01-03','2024-12-31'],
        fixed_content_source_paths=SOURCES,extra_content_source_paths=[],
        source_sha256_before=before,source_sha256_after=after,
        selected_snapshot_pointers=selected_manifest_pointers,
        field_provider_rows=rows,previous_vintage_manifest_citations=previous_vintage_records,
        row_count=10,field_family_count=5,provider_count=2,
        exact_native_field_mapping_certified_rows=0,
        historical_first_availability_certified_rows=0,
        formal_historical_input_approved_rows=0,
        current_decision_approved_rows=0,
        recoverability_disposition='Fixed metadata set supplies current-snapshot provenance, not historical first-availability proof; all ten pairs remain unapproved and require explicit evidence/fallback design.',
        actual_raw_market_responses_read=0,actual_market_value_rows_exported=0,
        actual_target_tables_read=0,new_real_labels_generated=0,new_models_fitted=0,new_scores_calculated=0,
        outcomes_2025_2026_opened=False,cumulative_research_variants_unchanged=16,
        model_input_approved=False,runtime_usable=False)
    encode=lambda obj:json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    (OUT/'field_evidence.json').write_text(encode(result))
    (OUT/'metadata_checks.json').write_text(encode(dict(
        all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,
        extractor_sha256=sha(Path(__file__)),source_sha256_before=before,source_sha256_after=after,
        field_evidence_sha256=sha(OUT/'field_evidence.json'),
        raw_response_sha256_reverification_performed=False,
        actual_targets_or_prices_exported=False)))
    print(json.dumps(dict(rows=10,checks=len(checks),sources=7,historical_PIT_certified_rows=0,raw_response_hashes_reverified=False),ensure_ascii=False))


if __name__=='__main__':main()
