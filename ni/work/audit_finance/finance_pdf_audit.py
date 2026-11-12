"""Read-only audit of preserved issuer reports and provider financial versions.

Does not alter the master database. Fixtures are transcribed from the named
main-accounting-data tables, with Q3 income/cashflow metrics selected as YTD.
An explicit source-text check must pass for every fixture before it is exported.
Disclosure dates are provider metadata, not proven first public timestamps.
"""
import collections
import decimal
import json
import pathlib
import re
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent
DB = ROOT / "outputs/高德红外数据库/高德红外_2023起.sqlite"
C = sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True)
C.row_factory = sqlite3.Row

# report_date, art_code, revenue, parent_profit, deducted_parent_profit,
# operating_cashflow, basic/diluted EPS, weighted ROE %, total_assets,
# parent_owners_equity. These are the contemporaneous report's current-period
# columns, rather than today's adjusted comparative columns.
FIXTURES = [
 ("2022-12-31", "AN202304191585591293", "2528594160.19", "501954674.49", "447956744.83", "236346785.28", "0.1531", "6.94", "8887797506.62", "7072255453.37"),
 ("2023-03-31", "AN202304271585966254", "443288933.91", "63173059.18", "53790758.20", "170409059.75", "0.0192", "0.89", "8792309265.81", "7154514367.81"),
 ("2023-06-30", "AN202308301596833817", "1056863545.10", "207383444.23", "191240342.58", "38262653.70", "0.0486", "2.91", "8603082288.46", "6891800000.62"),
 ("2023-09-30", "AN202310311607042709", "1612820193.05", "285626628.00", "256619574.28", "-433906829.03", "0.0669", "4.02", "8781007435.54", "6990162744.70"),
 ("2023-12-31", "AN202404151630235965", "2415056559.62", "67698339.24", "19542949.53", "308949996.56", "0.0159", "0.98", "8622522232.32", "6785104250.92"),
 ("2024-03-31", "AN202404261631393985", "467973388.98", "8383466.62", "926481.15", "-206484280.14", "0.0020", "0.12", "8795284688.04", "6805998529.46"),
 ("2024-06-30", "AN202408261639461683", "1149736005.75", "17969843.71", "958826.93", "-124794287.51", "0.0042", "0.26", "8802172540.39", "6768087721.15"),
 ("2024-09-30", "AN202410281640541892", "1812411716.30", "50212286.28", "25549271.23", "-26241100.27", "0.0118", "0.74", "9511813306.01", "6812779486.51"),
 ("2024-12-31", "AN202504241661802959", "2677585112.73", "-447186667.61", "-494147570.34", "231544693.38", "-0.1047", "-6.83", "9236284847.06", "6324243204.44"),
 ("2025-03-31", "AN202504281663932495", "680759855.77", "83545903.88", "66287709.72", "41288114.68", "0.0196", "1.31", "9683068449.02", "6415871183.32"),
 ("2025-06-30", "AN202508251734295811", "1934291385.85", "180930230.30", "151569202.36", "10626704.26", "0.0424", "2.82", "9958154864.39", "6522885986.40"),
 ("2025-09-30", "AN202510271770001931", "3067951216.73", "581935613.80", "535552312.97", "1413649218.04", "0.1363", "8.78", "10534282721.24", "6928305784.01"),
 ("2025-12-31", "AN202604141821191363", "4618828060.31", "686192530.33", "618045417.92", "1608521596.25", "0.1607", "10.27", "10924719324.37", "7041200583.82"),
 ("2026-03-31", "AN202604201821335910", "1245942950.66", "365901530.75", "351779124.36", "-110318892.47", "0.0857", "5.06", "11303612273.25", "7407292641.85"),
 ("2026-06-30", "AN202608250006749021", "4215505171.94", "1351196450.09", "1314204344.68", "-67503738.78", "0.3164", "17.51", "11670676469.48", "8396223199.27"),
]
METRICS = [
 ("revenue_ytd", "营业收入", "CNY", "TOTALOPERATEREVE"),
 ("parent_net_profit_ytd", "归属于上市公司股东的净利润", "CNY", "PARENTNETPROFIT"),
 ("deducted_parent_net_profit_ytd", "归属于上市公司股东的扣除非经常性损益的净利润", "CNY", "KCFJCXSYJLR"),
 ("operating_cashflow_ytd", "经营活动产生的现金流量净额", "CNY", "NETCASH_OPERATE_PK"),
 ("basic_eps_ytd", "基本每股收益", "CNY/share", "EPSJB"),
 ("diluted_eps_ytd", "稀释每股收益", "CNY/share", "EPSXS"),
 ("weighted_roe_ytd", "加权平均净资产收益率", "percent", "ROEJQ"),
 ("total_assets", "总资产", "CNY", "TOTAL_ASSETS_PK"),
 ("parent_owners_equity", "归属于上市公司股东的净资产", "CNY", None),
]
ALIASES = {
 "parent_owners_equity": ["归属于上市公司股东的净资产", "归属于上市公司股东的所有者权益"],
 "weighted_roe_ytd": ["加权平均净资产收益率"],
}

def clean(s):
    # Keep adjacent numeric columns separated while removing wrapped Chinese
    # labels. Otherwise 1.23 4.56 would incorrectly become one 1.234.56 token.
    s = re.sub(r"(?<=\d)\s+(?=[-\d])", "|", s)
    return re.sub(r"\s+", "", s)

def value_text_evidence(pages, metric, label, expected):
    labels = ALIASES.get(metric, [label])
    # Search only the main-accounting table and its continuation. Page selection
    # avoids matching the same number in unrelated notes or parent-only tables.
    start = next(i for i, p in enumerate(pages) if "主要会计数据" in p["text"])
    scope = pages[start:start + 2]
    flat = "".join(clean(p["text"]) for p in scope)
    positions = [flat.find(x) for x in labels if flat.find(x) >= 0]
    if not positions:
        raise AssertionError((metric, "label missing"))
    pos = min(positions)
    end_positions = []
    for _, other, _, _ in METRICS:
        p = flat.find(other, pos + 1)
        if p > pos:
            end_positions.append(p)
    segment = flat[pos:min(end_positions) if end_positions else pos + 450]
    nums = re.findall(r"-?\d[\d,]*\.\d+", segment)
    wanted = decimal.Decimal(expected)
    matched = [n for n in nums if decimal.Decimal(n.replace(",", "")) == wanted]
    if not matched:
        raise AssertionError((metric, expected, segment[:650]))
    matching_pages = []
    for p in scope:
        tokens = re.findall(r"-?\d[\d,]*\.\d+", clean(p["text"]))
        if any(decimal.Decimal(n.replace(",", "")) == wanted for n in tokens):
            matching_pages.append(p["page_number"])
    return {"pdf_page_numbers": matching_pages, "table_segment": segment[:450]}

provider = {
 json.loads(r["payload_json"])["REPORT_DATE"][:10]: dict(r)
 for r in C.execute("select * from current_source_records where dataset='financial_main'")
}
observations = []
differences = []
for fixture in FIXTURES:
    period, art = fixture[:2]
    base_values = list(fixture[2:])
    # A common EPS value appears separately in basic and diluted headings.
    values = base_values[:5] + [base_values[4]] + base_values[5:]
    doc = dict(C.execute("select * from announcement_documents where art_code=?", (art,)).fetchone())
    pages = [dict(r) for r in C.execute("select page_number,text from announcement_pages where art_code=? and page_number<=10 order by page_number", (art,))]
    raw = json.loads(provider[period]["payload_json"])
    for (metric, label, unit, raw_field), value in zip(METRICS, values):
        evidence = value_text_evidence(pages, metric, label, value)
        current = raw.get(raw_field) if raw_field else None
        item = {
          "report_date": period, "metric": metric, "value_decimal": value,
          "unit": unit, "scope": "consolidated_parent_attributable" if "parent" in metric else "consolidated",
          "period_basis": "period_end" if metric in ("total_assets", "parent_owners_equity") else "year_to_date",
          "art_code": art, "source_title": doc["title"], "source_url": doc["url"],
          "source_sha256": doc["sha256"], "provider_notice_date": doc["notice_date"][:10],
          "publication_time_precision": "day_only_from_provider_metadata",
          "availability_status": "original_report_value_verified_first_public_timestamp_unverified",
          "value_evidence_status": "manual_current_period_column_selection_and_named_segment_value_check",
          "provider_field": raw_field, "provider_current_value": current,
          "provider_record_notice_date": raw["NOTICE_DATE"][:10],
          "provider_record_update_date": raw["UPDATE_DATE"][:10],
          **evidence,
        }
        observations.append(item)
        if raw_field and decimal.Decimal(str(current)) != decimal.Decimal(value):
            differences.append(item)

counts = {}
date_rows = []
for ds in ("financial_main", "balance_sheet", "income_statement", "cashflow_statement"):
    rows = [json.loads(r[0]) for r in C.execute("select payload_json from current_source_records where dataset=?", (ds,))]
    lookup = {f[0]: f[1] for f in FIXTURES}
    delayed = []
    for r in rows:
        art = lookup.get(r["REPORT_DATE"][:10])
        if art:
            first = C.execute("select notice_date from announcement_documents where art_code=?", (art,)).fetchone()[0][:10]
            if r["NOTICE_DATE"][:10] > first:
                delayed.append({"dataset": ds, "report_date": r["REPORT_DATE"][:10], "current_provider_notice_date": r["NOTICE_DATE"][:10], "corresponding_original_report_notice_date": first, "original_art_code": art})
    date_rows.extend(delayed)
    counts[ds] = {"current_rows": len(rows), "unique_report_periods": len({r["REPORT_DATE"][:10] for r in rows}), "records_with_provider_notice_later_than_original_report_metadata": len(delayed)}
    if ds == "financial_main":
        counts[ds]["update_date_later_than_notice_date"] = sum(r["UPDATE_DATE"][:10] > r["NOTICE_DATE"][:10] for r in rows)

future_fields = {}
for ds in ("block_trade", "dividends", "financial_main"):
    matched = collections.defaultdict(lambda: {"field_present_rows": 0, "non_null_rows": 0})
    for r in C.execute("select payload_json from current_source_records where dataset=?", (ds,)):
        for k, v in json.loads(r[0]).items():
            if re.search(r"CHANGE_RATE_\d+DAYS|(?:^|_)D\d+_CLOSE_ADJCHRATE|FCFF_FORWARD", k):
                matched[k]["field_present_rows"] += 1
                matched[k]["non_null_rows"] += int(v is not None)
    future_fields[ds] = dict(matched)

result = {
  "audit_scope": "read_only_manual_fixture_verification_of_15_preserved_issuer_reports",
  "database": str(DB), "report_count": len(FIXTURES), "verified_observation_count": len(observations),
  "provider_value_differences_count": len(differences), "dataset_version_audit": counts,
  "original_report_observations": observations, "provider_value_differences": differences,
  "delayed_comparative_disclosure_records": date_rows,
  "quarantine_candidate_fields": future_fields,
  "limits": [
    "PDF contents establish values and units but not exact first public timestamps; dates above are preserved provider metadata.",
    "Notice-date filtering returns comparison/restatement periods before 2023. Keep them, with report dates preserved.",
    "Current provider UPDATE_DATE does not prove every field was revised; original report values must be checked field by field.",
    "FCFF_FORWARD is an unverified provider formula field, not established as realized future performance; exclude until its formula and historical availability are verified.",
    "Forward return statistics in dividend/block tables must never become contemporaneous trading inputs.",
    "Fixtures verify nine important metrics per report, not every line item or every page in 312 filings.",
  ]
}
(OUT / "finance_pdf_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"reports": result["report_count"], "verified_observations": len(observations), "differences": len(differences), "date_audit": counts, "quarantine_candidate_fields": future_fields}, ensure_ascii=False, indent=2))
