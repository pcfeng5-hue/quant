# 统一数据底座独立只读核验

核验日期：2026-10-22。通过 36 / 37 项。

主统一库 SHA-256：`6c0b72ac4e3b0772b42169b9dcbed32f65fb764db25c9d70da0d424bdcaf0fcb`

逐行与原数据库/JSON核对行情价格、成交量、成交额、换手率；独立核对条件原载荷、历史页面、财务事实、事件与受限字段隔离的全量多重集合。未联网，未改数据库。

| 检查 | 结果 |
|---|---|
| all_databases_quick_check_ok | 通过 |
| market_total_37714 | 通过 |
| market_collection_accounting | 通过 |
| all_market_source_values_exact | 通过 |
| stock_raw_reference_exact_dates_and_close | 通过 |
| reference_split_918_research_242_warmup | 通过 |
| market_reference_preserves_explicit_source | 通过 |
| reference_not_model_approval | 通过 |
| conditions_915_payloads_unchanged | 通过 |
| conditions_all_current_bars_available | 通过 |
| oct16_context_supplement_preserves_original | 通过 |
| first_previous_close_matches_warmup | 通过 |
| conditions_no_upgrade_to_official_limits_or_executability | 通过 |
| exdate_reference_not_naively_computed | 通过 |
| blocked_field_keys_absent_even_in_encoded_source_json | 通过 |
| all_restricted_cells_recoverable_exact_multiset | 通过 |
| legacy4094_clean_payloads_and_wrapper_exact | 通过 |
| quarantine6133_is_cells_not_labels | 通过 |
| filings312_pages4253_finance135 | 通过 |
| all_document_page_records_exact | 通过 |
| all_financial_original_observations_exact | 通过 |
| events67_episode59_original_payloads_exact | 通过 |
| event_first_publication_and_model_gates_preserved | 通过 |
| three_distributions_not11_distinct_episodes | 通过 |
| all_indexed_file_assets_exist_and_match_current_hash | 通过 |
| all_market_source_sha_references_resolve | 通过 |
| all_market_typed_retrieval_timestamps_populated | 通过 |
| chip_accepted_dates_and_gates | 通过 |
| chip_accepted_capture_dates_synchronized | 通过 |
| all950_standard_chip_attempt_payloads_preserved | 通过 |
| round1_four_observations_in_typed_store | 待修复 |
| dedicated_chip_evidence_files_table_present | 通过 |
| chip_evidence_paths_and_hashes_exact | 通过 |
| accepted_chips_have_linked_evidence | 通过 |
| only_rejected_round2_attempt_has_missing_evidence | 通过 |
| nonempty_market_unit_labels | 通过 |
| all_audited_databases_unchanged_during_audit | 通过 |

语义边界：

- market_reference and stock references are explicit browsing selections; model_input_approved remains0. Source conflict flags are not recommendations.
- 37714 is version/source rows, not independent outcomes. 1160dates include242warmup; research dates918, not918 independent trials.
- previous_close_unadjusted_candidate is raw previous close only; ex-rights exchange reference and official daily limits remain null.
- 6133 quarantined cells include3054 duplicated tuples, unknown-formula fields, and one null; not6133 result labels or independent samples.
- retrieved_at is acquisition metadata, not first publication. Current official notice existence does not prove a historical pre-event timestamp.
- Names amount_cny/turnover_pct express normalized locations; accompanying source unit labels keep unverified index scope/definitions visible.
- 5390file index verifies its registered scope, not a proof every project file or all historical market data is covered.
- Financial numeric facts and page/OCR text retain existing verification boundaries; no whole-dataset historical input approval follows from exact copying.
