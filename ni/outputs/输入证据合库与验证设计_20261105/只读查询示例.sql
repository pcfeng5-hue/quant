-- Read-only metadata inspection. No prices, returns or predictions are stored here.
SELECT field_family,provider,historical_first_available_at,earliest_model_use_timestamp FROM field_evidence ORDER BY provider,field_family;
SELECT planned_is_open,COUNT(*) FROM calendar_days GROUP BY planned_is_open;
SELECT trade_date,historical_st_status,daily_status_verified_normal,saved_execution_eligible FROM planned_open_status ORDER BY trade_date;
SELECT path,content_extracted_in_prior_pass FROM source_registry;
