#!/usr/bin/env python3
"""Independent, outcome-blind audit of one frozen market-context input.

Uses Python standard library exact rational arithmetic and original saved provider
responses. Never imports the feature producer and never opens an outcome DB.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FEATURE = "399001.SZ:close_over_ma20_minus_one"
SYMBOL = "399001.SZ"
FIRST = "2023-01-03"
LAST = "2024-12-31"
DB = ROOT / "outputs/市场环境输入准备_20261031/市场环境工程输入.sqlite"
UNIFIED = ROOT / "outputs/统一数据底座_20261022/统一数据底座.sqlite"
NORMALIZED = ROOT / "work/market_industry_oct22/market_rows_unique.json"
MANIFEST = ROOT / "work/market_industry_oct22/manifest.json"
SPEC = ROOT / "outputs/市场环境输入准备_20261031/冻结工程规格.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ro(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def load(path: Path):
    return json.loads(path.read_text())


def main():
    manifest = load(MANIFEST)
    requests = {
        r["provider"]: r
        for r in manifest["results"]
        if r.get("symbol") == SYMBOL and r.get("adjustment") == "0"
        and r.get("provider") in ("eastmoney", "tencent")
    }
    assert set(requests) == {"eastmoney", "tencent"}
    raw_paths = {provider: Path(r["raw_path"]) for provider, r in requests.items()}
    source_paths = [DB, UNIFIED, NORMALIZED, MANIFEST, SPEC, *raw_paths.values()]
    before = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    checks = []

    def check(name, condition, detail=None):
        checks.append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(name)

    for provider, p in raw_paths.items():
        check(provider + "_original_response_hash", sha(p) == requests[provider]["sha256"])

    # Parse only the saved price/date fields needed here; never derive a forward
    # return, label, frequency or model score. Dates after 2024 are not analyzed.
    em_payload = load(raw_paths["eastmoney"])
    tx_payload = load(raw_paths["tencent"])
    check("raw_provider_instrument_identity",
          em_payload["data"]["code"] == "399001" and
          em_payload["data"]["market"] == 0 and
          "sz399001" in tx_payload["data"])
    em = {}
    em_row_index = {}
    for n, line in enumerate(em_payload["data"]["klines"]):
        fields = line.split(",")
        if fields[0] <= LAST:
            check("unique_em_date_" + fields[0], fields[0] not in em)
            em[fields[0]] = Fraction(fields[2])
            em_row_index[fields[0]] = n
    tx = {}
    for row in tx_payload["data"]["sz399001"]["day"]:
        if row[0] <= LAST:
            check("unique_tx_date_" + row[0], row[0] not in tx)
            tx[row[0]] = Fraction(row[2])
    # Consolidate repetitive uniqueness assertions in published checks.
    checks = [x for x in checks if not x["name"].startswith(("unique_em_date_", "unique_tx_date_"))]
    check("raw_dates_unique_matching_and_positive",
          len(em) == len(tx) == 726 and set(em) == set(tx) and
          all(x > 0 for x in em.values()) and all(x > 0 for x in tx.values()),
          {"price_dates_per_provider_through_2024": len(em)})
    conflicts = {d for d in em if em[d] != tx[d]}
    check("chosen_index_close_conflicts_absent_in_2022_2024", not conflicts,
          {"source_close_conflict_count": len(conflicts),
           "does_not_certify_provider_truth_or_source_independence": True})

    normalized = load(NORMALIZED)
    with ro(DB) as c, ro(UNIFIED) as u:
        records = [dict(r) for r in c.execute(
            "SELECT * FROM input_closes WHERE canonical_symbol=? AND trade_date<=? "
            "ORDER BY provider,trade_date", (SYMBOL, LAST))]
        check("saved_input_two_series_unique", len(records) == 1452 and
              len({(r["provider"], r["trade_date"]) for r in records}) == len(records))
        field_mapping = {
            "observation_id": "observation_id", "collection": "collection",
            "canonical_symbol": "canonical_symbol", "provider": "provider",
            "adjustment": "adjustment", "trade_date": "trade_date", "close": "close",
            "price_unit": "price_unit", "source_sha256": "source_sha256",
            "source_request_id": "source_request_id", "retrieved_at": "retrieved_at",
            "input_path": "input_path", "input_row_index": "input_row_index",
        }
        all_unified_equal = True
        all_normalized_equal = True
        all_raw_equal = True
        all_units_ids_times = True
        for r in records:
            d, provider = r["trade_date"], r["provider"]
            ur = u.execute("SELECT * FROM market_daily WHERE observation_id=?", (r["observation_id"],)).fetchone()
            all_unified_equal &= ur is not None and all(r[k] == ur[v] for k, v in field_mapping.items())
            nr = normalized[r["input_row_index"]]
            all_normalized_equal &= (
                r["observation_id"] == "market_industry_oct21:" + str(r["input_row_index"]) and
                nr["symbol"] == SYMBOL and nr["source"] == provider and
                nr["trade_date"] == d and nr["close"] == r["close"] and
                nr["source_sha256"] == r["source_sha256"] and
                nr["source_request_id"] == r["source_request_id"] and
                not nr["same_provider_duplicate_conflict"])
            source = em if provider == "eastmoney" else tx
            all_raw_equal &= Fraction(str(r["close"])) == source[d]
            all_units_ids_times &= (
                r["price_unit"] == "index_points" and r["adjustment"] == "0" and
                r["source_sha256"] == requests[provider]["sha256"] and
                r["source_request_id"] == requests[provider]["id"] and
                r["retrieved_at"] == requests[provider]["finished_at_utc"] and
                r["input_path"] == str(NORMALIZED.relative_to(ROOT)))
        check("saved_input_exact_match_unified_observations", all_unified_equal,
              {"observation_rows_verified": len(records)})
        check("observation_ids_normalized_row_and_identity", all_normalized_equal)
        check("closes_independently_equal_original_provider_strings", all_raw_equal)
        check("units_request_hash_retrieval_time_and_no_adjustment", all_units_ids_times)

        development_dates = [d for d in sorted(em) if FIRST <= d <= LAST]
        frows = [dict(r) for r in c.execute(
            "SELECT * FROM features WHERE feature_id=? AND signal_date BETWEEN ? AND ? "
            "ORDER BY signal_date", (FEATURE, FIRST, LAST))]
        check("484_development_dates_complete_unique_no_fill",
              len(development_dates) == 484 and
              [r["signal_date"] for r in frows] == development_dates and
              len({r["signal_date"] for r in frows}) == 484)
        cat = dict(c.execute("SELECT * FROM feature_catalog WHERE feature_id=?", (FEATURE,)).fetchone())
        check("feature_unit_fraction_and_preparation_gate",
              cat["subject_symbol"] == SYMBOL and cat["value_unit"] == "fraction" and
              cat["preparation_only"] == 1 and cat["model_input_approved"] == cat["runtime_usable"] == 0)
        pmap = {r["trade_date"]: r for r in records if r["provider"] == "eastmoney"}
        calc_dates = [d for d in sorted(em) if "2022-06-01" <= d <= LAST]
        indices = {d: i for i, d in enumerate(calc_dates)}
        max_abs_error = 0.0
        precise_values = {}
        dependency_rows = 0
        dependencies_ok = True
        values_ok = True
        flags_ok = True
        causality_ok = True
        for fr in frows:
            d = fr["signal_date"]
            i = indices[d]
            window = calc_dates[i - 19:i + 1]
            assert len(window) == 20
            exact_ma = sum((em[z] for z in window), Fraction()) / 20
            exact_value = em[d] / exact_ma - 1
            precise_values[d] = exact_value
            expected = float(exact_value)
            error = abs(fr["engineering_value"] - expected)
            max_abs_error = max(max_abs_error, error)
            values_ok &= (
                math.isfinite(fr["engineering_value"]) and error <= 5e-15 and
                fr["engineering_value"] == fr["diagnostic_value"])
            deps = [dict(r) for r in c.execute(
                "SELECT * FROM feature_dependencies WHERE feature_id=? AND signal_date=? "
                "ORDER BY dependency_order", (FEATURE, d))]
            dependency_rows += len(deps)
            dependencies_ok &= len(deps) == 20
            for j, (dep, wd) in enumerate(zip(deps, window)):
                pr = pmap[wd]
                dependencies_ok &= (
                    dep["dependency_order"] == j and dep["dependency_symbol"] == SYMBOL and
                    dep["dependency_date"] == wd and dep["observation_id"] == pr["observation_id"] and
                    dep["source_close"] == float(em[wd]) and
                    dep["source_sha256"] == pr["source_sha256"] and
                    dep["source_close_conflict"] == int(wd in conflicts))
            dependencies_ok &= (
                fr["dependency_n"] == 20 and fr["dependency_first_date"] == window[0] and
                fr["max_dependency_date"] == d and fr["close_source_conflict_n"] == 0)
            causality_ok &= all(z <= d for z in window) and window[-1] == d
            flags_ok &= (
                fr["engineering_ready"] == 1 and
                fr["status"] == "ENGINEERING_READY_NOT_FORMAL_PIT" and
                fr["historical_first_availability_certified"] == 0 and
                fr["model_input_approved"] == 0 and fr["runtime_usable"] == 0)
        check("484_values_recomputed_with_exact_rational_ma20", values_ok,
              {"max_absolute_float_error": max_abs_error, "absolute_comparison_tolerance": 5e-15})
        check("9680_exact_dependencies_observation_ids_and_current_included", dependencies_ok and dependency_rows == 9680,
              {"dependency_rows_verified": dependency_rows})
        check("no_dependency_after_signal_date", causality_ok)
        check("all_484_ready_only_engineering_and_formal_gates_false", flags_ok)
        check("selected_close_quarantine_absent_matches_independent_raw_comparison",
              c.execute("SELECT COUNT(*) FROM close_source_conflicts WHERE canonical_symbol=? AND trade_date<=?",
                        (SYMBOL, LAST)).fetchone()[0] == 0 and not conflicts)
        check("approved_context_view_empty",
              c.execute("SELECT COUNT(*) FROM approved_market_context_inputs").fetchone()[0] == 0)
        # Avoid a data-dependent epsilon threshold. Exactly at MA is the
        # nonpositive state; sign can be compared exactly as 20*C_t versus sum C.
        exact_zeros = [d for d, x in precise_values.items() if x == 0]
        sign_ok = all((r["engineering_value"] > 0) == (precise_values[r["signal_date"]] > 0)
                      for r in frows)
        check("exact_zero_boundary_and_saved_float_signs_agree", sign_ok,
              {"exact_zero_days": len(exact_zeros), "exact_zero_dates": exact_zeros,
               "minimum_absolute_exact_value": float(min(abs(x) for x in precise_values.values())),
               "threshold_rule": ">0 positive; <=0 nonpositive; NULL abstain; no fitted epsilon"})
        synthetic = []
        for current, expected in [(Fraction(100), "nonpositive"),
                                  (Fraction(100) + Fraction(1, 10**12), "positive"),
                                  (Fraction(100) - Fraction(1, 10**12), "nonpositive")]:
            xs = [Fraction(100)] * 19 + [current]
            x = current / (sum(xs) / 20) - 1
            state = "positive" if x > 0 else "nonpositive"
            synthetic.append({"current": str(current), "exact_value": str(x),
                              "state": state, "expected": expected})
        check("synthetic_exact_equal_and_both_sides_of_zero", all(x["state"] == x["expected"] for x in synthetic), synthetic)

    spec = load(SPEC)
    check("spec_requires_completed_current_close_and_uncertified_historical_availability",
          spec["information_time"].startswith("Completed same-date close") and
          spec["historical_first_availability_certified"] is False and
          spec["formal_historical_model_input_approved"] is False and spec["runtime_usable"] is False)
    after = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    check("all_source_files_unchanged_before_after", before == after)
    result = {
        "audit_id": "selected_market_input_independent_20261031_v1",
        "feature_id": FEATURE,
        "scope": "Outcome-blind input audit; 2023-2024 development dates; saved 2022 prices used only as warmup",
        "method": "Original saved EM/Tencent strings; exact fractions; no producer imports; readonly SQL",
        "passed": all(x["passed"] for x in checks),
        "check_count": len(checks),
        "checks": checks,
        "source_sha256_before": before,
        "source_sha256_after": after,
        "developer_input_dates": 484,
        "exact_dependency_rows_verified": dependency_rows,
        "raw_dates_per_provider_through_2024": len(em),
        "read_outcome_database": False,
        "read_candidate_frequency_or_score": False,
        "generated_forward_returns": False,
        "opened_2025_2026_outcomes": False,
        "new_model_scored_or_selected": False,
        "formal_historical_input_admission": False,
        "runtime_usable": False,
        "limitations": [
            "Saved responses were retrieved 2026-10-22, not archived historical publication-time snapshots.",
            "Same-day close and inclusive MA20 require completion of the signal-day session; cannot justify a same-close fill or intraday use.",
            "Index prices are index points; ratio is a dimensionless fraction, not money flow, total return, or industry membership.",
            "Agreement between two provider snapshots does not prove either true or independent.",
            "No input, signal effectiveness, probability reliability, or profitability is certified by these engineering checks.",
            "Only the prescribed index and 20-observation inclusive formula were audited; no alternate window or threshold chosen.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "选定市场输入核查.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    text = f"""# 选定市场输入独立核查

选定输入：`{FEATURE}`。仅审查2023—2024开发期及2022预热，不打开标签库，不读取新候选频率或评分。

- **{len(checks)}/{len(checks)}项核查通过**；484/484个开发日期完整，工程ready，不代表正式历史准入。
- 独立解析两家原始保存响应，在2022—2024每家726个日期核对收盘；选定指数这段没有收盘冲突。1452个来源观察与统一库、标准化行、原始响应、请求编号、抓取时间和SHA完全衔接。
- 直接以原始十进制字符串构造精确有理数，重算含当日20观察均价及`close/MA20-1`，核验9680条依赖。最大浮点表示差{max_abs_error:.3g}；全部依赖不晚于信号日，窗口包括当日。
- 输入价格单位为指数点，输出为无量纲小数，显示为百分比时乘100。没有使用指数成交量、金额或换手，也不将价格指数当成总回报。
- 零边界：`>0`为正，`<=0`为非正，缺值弃答；不从数据拟合容差。实际精确等零{len(exact_zeros)}天，浮点与精确符号全部一致；另以精确等均值、略高和略低合成例核验。此处“非正”不是“必然下跌”。
- 依赖含当日收盘，必须在当日收盘完成后才可能使用；不能据此宣称同收盘价成交或盘中信号。
- 该批原件在2026-10-22回采，历史首次发布时间未认证；484日正式输入准入、历史可得性和runtime标志仍全为0。可以在明确披露此限制的回溯工程研究中使用，不能静默解除正式门槛。
- 7个输入文件前后哈希不变。未读取未来结果、标签频率或评分，未改变任何旧文件，未对候选预测有效性作结论。

详细逐项检查、合成边界例和源哈希见同目录JSON；复算执行同目录`audit_selected_input.py`，仅需Python标准库。
"""
    (OUT / "选定市场输入核查.md").write_text(text)
    print(json.dumps({"passed": result["passed"], "checks": len(checks),
                      "development_dates": 484, "dependency_rows": dependency_rows,
                      "max_abs_error": max_abs_error, "exact_zero_days": len(exact_zeros)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
