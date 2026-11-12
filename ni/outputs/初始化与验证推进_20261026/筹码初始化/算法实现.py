#!/usr/bin/env python3
"""Common-origin, partially identified chip initialization, entirely local.

Only task-owned work/output directories are written. Observed mass is never
renormalized into a purported total distribution. No unknown-price support is
assumed. No vendor code is imported; this is an independent implementation.
"""
from __future__ import annotations

import argparse
import copy
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3

import numpy as np

VERSION = "common-origin-partial-identification-chip-v2"
START = "2022-06-01"
END = "2026-10-21"
RESEARCH_START = "2023-01-03"
STEP = 0.01
MULTIPLIERS = (0.5, 1.0, 1.5)
TARGETS = ("2023-01-03", "2023-06-19", "2023-06-20", "2023-06-21",
           "2024-05-23", "2024-05-24", "2024-05-27", "2026-09-21",
           "2026-09-22", "2026-09-23", "2026-10-16", "2026-10-21")
RAW_SQL = """SELECT observation_id,trade_date,open,high,low,close,turnover_pct,
adjustment,adjustment_vintage,turnover_unit,retrieved_at,source_sha256,
source_request_id,raw_row_index,input_path,input_row_index,model_input_approved,
has_price_source_conflict,has_volume_source_conflict
FROM stock_raw_reference
WHERE trade_date >= '2022-06-01' AND trade_date <= '2026-10-21'
ORDER BY trade_date"""


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def objhash(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def filehash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                   indent=2, allow_nan=False) + "\n", encoding="utf-8")


def variant(multiplier):
    return f"turnover_x{multiplier:g}"


def params(multiplier):
    return {"variant": variant(multiplier), "algorithm_version": VERSION,
            "common_origin_pretrade_date": START, "grid_origin_cny": 0,
            "grid_step_cny": STEP, "turnover_multiplier": multiplier,
            "turnover_rule": "u=clip(multiplier*turnover_pct/100,0,1)",
            "initial_unknown_mass_before_first_trade": 1.0,
            "initial_observed_mass_before_first_trade": 0.0,
            "first_day_turnover_included": True,
            "unknown_initial_price_support_assumed": False,
            "daily_allocation": "triangle(low,OHLC_mean,high); CDF-integrated fixed grid cells",
            "action_rule": "old observed prices (p-gross_cash_per_old_share)/(1+transfer_per_old_share) before ex-day turnover",
            "normalization_rule": "only daily D and separately labelled conditional-known distribution; never normalize observed subprobability Q",
            "model_input_approved": False, "native_supplier_bins_acquired": False}


def point_rebin(prices, weights):
    """Linearly split unnormalized mass at fixed nonnegative grid nodes."""
    prices, weights = np.asarray(prices, float), np.asarray(weights, float)
    positive = weights > 0
    prices, weights = prices[positive], weights[positive]
    if not len(prices):
        return np.zeros(1)
    if np.min(prices) < 0:
        raise ValueError("negative observed transformed cost requires an explicit grid policy")
    coords = prices / STEP
    left = np.floor(coords).astype(int)
    right_fraction = coords - left
    output = np.zeros(int(left.max()) + 2)
    np.add.at(output, left, weights * (1 - right_fraction))
    np.add.at(output, left + 1, weights * right_fraction)
    last = np.flatnonzero(output > 0)[-1] + 1
    return output[:last]


def triangle_cdf(x, low, mode, high):
    out = np.zeros_like(x, dtype=float)
    out[x >= high] = 1
    inside = (x > low) & (x < high)
    if mode <= low:
        out[inside] = 1 - ((high - x[inside]) / (high - low)) ** 2
    elif mode >= high:
        out[inside] = ((x[inside] - low) / (high - low)) ** 2
    else:
        left, right = inside & (x <= mode), inside & (x > mode)
        out[left] = (x[left] - low) ** 2 / ((high - low) * (mode - low))
        out[right] = 1 - (high - x[right]) ** 2 / ((high - low) * (high - mode))
    return out


def daily_allocation(row):
    low, high = float(row["low"]), float(row["high"])
    if not (0 <= low <= min(row["open"], row["close"]) <=
            max(row["open"], row["close"]) <= high):
        raise ValueError("invalid OHLC")
    if high == low:
        return point_rebin([low], [1.0])
    nodes = np.arange(math.ceil(high / STEP) + 1) * STEP
    mode = sum(row[k] for k in ("open", "high", "low", "close")) / 4
    mass = triangle_cdf(nodes + STEP / 2, low, mode, high) - triangle_cdf(nodes - STEP / 2, low, mode, high)
    if mass.min() < -1e-14 or not math.isfinite(float(mass.sum())):
        raise ValueError("invalid daily allocation")
    mass = np.maximum(mass, 0)
    mass /= mass.sum()
    return mass[:np.flatnonzero(mass > 0)[-1] + 1]


def apply_action(observed, unknown, event):
    before = float(observed.sum())
    nodes = np.flatnonzero(observed > 0)
    d, s = event["cash_cny_per_share_gross"], event["transfer_per_share"]
    moment_before = float(np.dot(np.arange(len(observed)) * STEP, observed))
    result = point_rebin((nodes * STEP - d) / (1 + s), observed[nodes])
    moment_after = float(np.dot(np.arange(len(result)) * STEP, result))
    expected = (moment_before - d * before) / (1 + s)
    return result, {"event_id": event["event_id"], "ex_date": event["ex_date"],
                    "cash_cny_per_share_gross": d, "transfer_per_share": s,
                    "observed_mass_before": before, "observed_mass_after": float(result.sum()),
                    "unknown_mass_before": unknown, "unknown_mass_after": unknown,
                    "observed_first_moment_before": moment_before,
                    "observed_first_moment_after": moment_after,
                    "expected_observed_first_moment_after": expected,
                    "absolute_first_moment_error": abs(moment_after - expected),
                    "unknown_price_coordinate_representation": "unspecified pushforward, no invented price bins",
                    "order": "action on old mass before ex-day turnover"}


def quantile_known_mass(observed, target):
    index = int(np.searchsorted(np.cumsum(observed), target, side="left"))
    return float(min(index, len(observed) - 1) * STEP)


def endpoint(kind, value=None):
    return {"kind": kind, "value_cny": value}


def quantile_bounds(observed, unknown, q):
    # All finite-x CDFs satisfy K(x) <= F(x) <= K(x)+U. No unknown support.
    known = float(observed.sum())
    lower = endpoint("negative_infinity") if q <= unknown else endpoint("finite", quantile_known_mass(observed, q - unknown))
    upper = endpoint("positive_infinity") if q > known else endpoint("finite", quantile_known_mass(observed, q))
    return {"q": q, "lower": lower, "upper": upper,
            "unknown_initial_price_support_assumed": False}


def summarize(observed, unknown, row, multiplier, count, audits, gaps):
    known = float(observed.sum())
    nodes = np.arange(len(observed)) * STEP
    profit_lower = float(observed[nodes <= row["close"] + 1e-12].sum())
    conditional = observed / known if known else None
    return {"asof_date": row["trade_date"], "variant": variant(multiplier),
            "common_origin_pretrade_date": START, "observed_trading_days": count,
            "close_raw_cny": row["close"], "unknown_initial_mass": unknown,
            "known_observed_contribution_mass": known,
            "known_plus_unknown_mass": known + unknown,
            "initialization_total_variation_diameter_upper_bound": unknown,
            "cdf_bound_max_width": unknown,
            "profit_mass_lower": profit_lower,
            "profit_mass_upper": min(1.0, profit_lower + unknown),
            "profit_bound_width": unknown,
            "total_distribution_mean_cny": None,
            "total_mean_identification": "no finite bounds without bounded unknown support or moment restrictions",
            "total_quantile_bounds": [quantile_bounds(observed, unknown, q) for q in (.05, .15, .5, .85, .95)],
            "known_only_conditional_mean_cny": float(np.dot(nodes, conditional)) if known else None,
            "known_only_conditional_median_cny": quantile_known_mass(conditional, .5) if known else None,
            "known_only_conditional_profit_fraction": profit_lower / known if known else None,
            "known_conditional_semantics": "conditional on turnover-created observed component under this model, not the total holder distribution",
            "unknown_initial_price_support_assumed": False,
            "known_only_saved_grid_max_cny": float(nodes[-1]),
            "total_distribution_mass_outside_saved_known_grid": "unknown; at most unknown_initial_mass",
            "known_coordinate_events_applied": len(audits),
            "unbridged_large_gap_count_since_common_origin": len(gaps),
            "early_history_warning": row["trade_date"] < "2024-01-01",
            "warmup_sufficiency_certified": False,
            "prediction_reliability_certified": False,
            "complete_corporate_action_coverage_certified": False,
            "historical_first_seen_certified": False,
            "estimate_status": "partial_identification_diagnostic_only",
            "model_input_approved": False, "native_supplier_bins_acquired": False}


def run_path(rows, actions, multiplier, target_dates=TARGETS):
    """Single forward pass; future rows/actions cannot affect any saved prefix."""
    if not rows or rows[0]["trade_date"] != START:
        raise ValueError("common-origin first daily bar missing")
    observed, unknown = np.zeros(1), 1.0
    active_actions = {a["ex_date"]: a for a in actions if START <= a["ex_date"] <= rows[-1]["trade_date"]}
    if len(active_actions) != len([a for a in actions if START <= a["ex_date"] <= rows[-1]["trade_date"]]):
        raise ValueError("multiple actions on a date require explicit composition")
    results, diagnostics, audits, gaps, prefix_rows = [], [], [], [], []
    previous = None
    for count, row in enumerate(rows, 1):
        date = row["trade_date"]
        if previous is not None and date <= previous["trade_date"]:
            raise ValueError("daily dates must be unique and strictly increasing")
        prefix_rows.append(row)
        action = active_actions.get(date)
        if action:
            observed, audit = apply_action(observed, unknown, action)
            audits.append(audit)
        elif previous is not None and abs(row["open"] / previous["close"] - 1) > .15:
            gaps.append({"trade_date": date, "previous_close": previous["close"],
                         "open": row["open"], "open_gap_fraction": row["open"] / previous["close"] - 1,
                         "status": "unbridged_gap_not_proof_of_corporate_action"})
        daily = daily_allocation(row)
        u = min(1.0, max(0.0, multiplier * row["turnover_pct"] / 100))
        new = np.zeros(max(len(observed), len(daily)))
        new[:len(observed)] += (1 - u) * observed
        new[:len(daily)] += u * daily
        observed = new
        unknown *= 1 - u
        known = float(observed.sum())
        diagnostics.append({"asof_date": date, "variant": variant(multiplier),
                            "observed_trading_days": count, "turnover_u": u,
                            "unknown_initial_mass": unknown,
                            "known_observed_contribution_mass": known,
                            "mass_sum_error": abs(known + unknown - 1),
                            "initialization_tv_upper_bound": unknown,
                            "cdf_and_profit_bound_width": unknown,
                            "research_918_scope": date >= RESEARCH_START,
                            "warmup_sufficiency_certified": False,
                            "prediction_reliability_certified": False,
                            "model_input_approved": False,
                            "native_supplier_bins_acquired": False})
        if date in target_dates:
            summary = summarize(observed, unknown, row, multiplier, count, audits, gaps)
            provenance = {"input_view": "stock_raw_reference", "input_max_trade_date": date,
                          "input_min_trade_date": START, "input_rows_sha256": objhash(prefix_rows),
                          "input_observation_ids": [r["observation_id"] for r in prefix_rows],
                          "input_raw_source_hashes": sorted({r["source_sha256"] for r in prefix_rows}),
                          "input_retrieved_at_values": sorted({r["retrieved_at"] for r in prefix_rows}),
                          "turnover_units": sorted({r["turnover_unit"] for r in prefix_rows}),
                          "actions_applied": copy.deepcopy(audits),
                          "applied_action_terms_sha256": objhash([a for a in actions if START <= a["ex_date"] <= date]),
                          "unbridged_large_gaps": copy.deepcopy(gaps),
                          "has_price_source_conflict_dates": [r["trade_date"] for r in prefix_rows if r["has_price_source_conflict"]],
                          "has_volume_source_conflict_dates": [r["trade_date"] for r in prefix_rows if r["has_volume_source_conflict"]]}
            results.append({"estimate_id": variant(multiplier) + ":" + date,
                            "params": params(multiplier), "summary": summary,
                            "provenance": provenance, "observed_mass": observed.copy()})
        previous = row
    return results, diagnostics


def load_sources(project):
    path = project / "outputs/统一数据底座_20261022/统一数据底座.sqlite"
    before_hash = filehash(path)
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(RAW_SQL)]
    actions, evidence_files = [], [path]
    for raw in conn.execute("SELECT * FROM corporate_actions ORDER BY ex_date"):
        action = dict(raw)
        action["cash_cny_per_share_gross"] = float(Decimal(action["cash_cny_per_10_gross"]) / 10)
        action["transfer_per_share"] = float(Decimal(action["transfer_shares_per_10"]) / 10)
        art_code = json.loads(action["payload_json"])["art_code"]
        filing = dict(conn.execute("SELECT * FROM filings WHERE art_code=?", (art_code,)).fetchone())
        original = project / filing["original_path"]
        actual = filehash(original)
        if actual != filing["original_sha256"]:
            raise ValueError("action original hash mismatch")
        action["source_filing"] = filing
        action["source_original_actual_sha256"] = actual
        evidence_files.append(original)
        actions.append(action)
    requests = [dict(r) for r in conn.execute("SELECT * FROM source_requests WHERE request_id='em_002414.SZ_0'")]
    for request in requests:
        original = project / request["raw_path"]
        if filehash(original) != request["source_sha256"]:
            raise ValueError("raw market original hash mismatch")
        evidence_files.append(original)
    conn.close()
    if len({r["trade_date"] for r in rows}) != len(rows):
        raise ValueError("duplicate dates")
    manifest = {"database_relative_path": str(path.relative_to(project)),
                "database_sha256_before": before_hash,
                "database_read_mode": "mode=ro&immutable=1", "raw_query": RAW_SQL,
                "raw_row_count": len(rows), "raw_min_date": rows[0]["trade_date"],
                "raw_max_date": rows[-1]["trade_date"], "raw_rows_sha256": objhash(rows),
                "raw_source_requests": requests, "corporate_actions": actions,
                "prior_script_read_only_sha256": filehash(project / "work/local_chip_estimate_oct25/build_chip_sample.py"),
                "prior_script_used": "read as reference only; no import or execution",
                "implementation": "independent local numpy implementation",
                "remote_code_executed": False, "network_used": False,
                "future_returns_read": False, "supplier_summary_fitting_used": False,
                "retrieval_and_first_seen_caveat": "bars retrieved in 2026; historical availability and minute-level filing first publication not certified",
                "model_input_approved": False, "native_supplier_bins_acquired": False}
    return rows, actions, manifest, evidence_files


def preserved_snapshot(project, evidence):
    paths = list(evidence)
    for folder in ("work/local_chip_estimate_oct25", "outputs/三线研究启动_20261025/自建筹码样本"):
        paths.extend(p for p in (project / folder).rglob("*") if p.is_file())
    return {str(p.relative_to(project)): filehash(p) for p in sorted(set(paths))}


def frozen_result(result):
    return {key: value.tolist() if isinstance(value, np.ndarray) else value for key, value in result.items()}


def validate(rows, actions, results, diagnostics):
    checks = []
    def add(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), **evidence})
    add("known_plus_unknown_mass_conserved_without_renormalizing_known",
        max(d["mass_sum_error"] for d in diagnostics) < 1e-12,
        max_absolute_error=max(d["mass_sum_error"] for d in diagnostics),
        checked_daily_states=len(diagnostics))
    add("observed_mass_nonnegative", all(float(r["observed_mass"].min()) >= 0 for r in results))
    product_errors = []
    monotone_ok = True
    for multiplier in MULTIPLIERS:
        own = [d for d in diagnostics if d["variant"] == variant(multiplier)]
        expected, previous = 1.0, 1.0
        for row, daily in zip(rows, own):
            expected *= 1 - min(1, max(0, row["turnover_pct"] / 100 * multiplier))
            product_errors.append(abs(expected - daily["unknown_initial_mass"]))
            monotone_ok &= daily["unknown_initial_mass"] <= previous
            previous = daily["unknown_initial_mass"]
    add("unknown_equals_product_of_one_minus_turnover", max(product_errors) < 1e-15,
        max_error=max(product_errors), includes_common_origin_first_day=True)
    add("unknown_monotone_in_absence_of_external_mass_events", monotone_ok,
        actions_preserve_unknown_weight=True)
    prefix_proofs, future_proofs = [], []
    # Every fixed date, each multiplier: compare full path with a prefix rerun.
    for result in results:
        date, mult = result["summary"]["asof_date"], result["params"]["turnover_multiplier"]
        prefix = [r for r in rows if r["trade_date"] <= date]
        prefix_actions = [a for a in actions if a["ex_date"] <= date]
        rerun = run_path(prefix, prefix_actions, mult, (date,))[0][0]
        a, b = objhash(frozen_result(result)), objhash(frozen_result(rerun))
        prefix_proofs.append({"estimate_id": result["estimate_id"], "full_sha256": a, "prefix_sha256": b, "equal": a == b})
        if date < END:
            poisoned_rows = copy.deepcopy(rows)
            for row in poisoned_rows:
                if row["trade_date"] > date:
                    for key in ("open", "high", "low", "close"):
                        row[key] *= 2
                    row["turnover_pct"] = 99
            poisoned_actions = copy.deepcopy(actions)
            for action in poisoned_actions:
                if action["ex_date"] > date:
                    action["cash_cny_per_share_gross"] = .2
                    action["transfer_per_share"] = .9
            altered = run_path(poisoned_rows, poisoned_actions, mult, (date,))[0][0]
            c = objhash(frozen_result(altered))
            future_proofs.append({"estimate_id": result["estimate_id"], "original_sha256": a, "future_poison_sha256": c, "equal": a == c})
    add("prefix_invariance_all_36_fixed_results", all(x["equal"] for x in prefix_proofs), proofs=prefix_proofs)
    add("future_price_turnover_and_action_mutation_invariance", all(x["equal"] for x in future_proofs),
        proofs=future_proofs, future_returns_loaded=False)
    audits = [a for r in results for a in r["provenance"]["actions_applied"]]
    add("three_corporate_actions_preserve_known_and_unknown_mass_and_first_moment",
        {a["ex_date"] for a in audits} == {"2023-06-20", "2024-05-24", "2026-09-22"}
        and all(abs(a["observed_mass_after"] - a["observed_mass_before"]) < 1e-12
                    and a["unknown_mass_before"] == a["unknown_mass_after"]
                    and a["absolute_first_moment_error"] < 1e-11 for a in audits),
        audited_applications=len(audits),
        max_first_moment_error=max(a["absolute_first_moment_error"] for a in audits))
    by_key = {(d["asof_date"], d["variant"]): d for d in diagnostics}
    add("all_three_turnover_multipliers_and_ordering", len(results) == 36 and
        all(by_key[(row["trade_date"], "turnover_x0.5")]["unknown_initial_mass"] >=
            by_key[(row["trade_date"], "turnover_x1")]["unknown_initial_mass"] >=
            by_key[(row["trade_date"], "turnover_x1.5")]["unknown_initial_mass"] for row in rows),
        multipliers=list(MULTIPLIERS))
    early = [r["summary"] for r in results if r["summary"]["asof_date"] <= "2023-06-21"]
    add("early_history_never_certified_or_unknown_hidden", all(s["unknown_initial_mass"] > 0 and
        s["known_observed_contribution_mass"] < 1 and s["early_history_warning"] and
        not s["warmup_sufficiency_certified"] and not s["model_input_approved"] for s in early),
        checked_early_results=len(early))
    add("no_total_mean_or_unknown_support_invented", all(r["summary"]["total_distribution_mean_cny"] is None and
        not r["summary"]["unknown_initial_price_support_assumed"] for r in results))
    add("cdf_profit_bounds_and_tv_width_equal_unknown", all(abs(
        r["summary"]["profit_mass_upper"] - r["summary"]["profit_mass_lower"] -
        r["summary"]["unknown_initial_mass"]) < 1e-12 for r in results))
    # Adversarial unknown atoms on either side of observed support attain the
    # arbitrary-support CDF bounds, TV diameter, and quantile endpoint formulas.
    toy = np.array([0, .2, .3, .1])
    toy_unknown = .4
    toy_cdf = np.cumsum(toy)
    add("unrestricted_unknown_cdf_envelope_attained_by_extreme_atoms",
        np.allclose(toy_cdf + toy_unknown, np.cumsum(np.r_[toy_unknown, toy])[1:]) and
        np.allclose(toy_cdf, np.cumsum(np.r_[toy, toy_unknown])[:-1]),
        unknown_mass=toy_unknown, tv_between_extreme_unknown_atoms=toy_unknown)
    qbounds = [quantile_bounds(toy, toy_unknown, q) for q in (.05, .5, .95)]
    add("quantile_bounds_include_unbounded_tail_cases",
        qbounds[0]["lower"]["kind"] == "negative_infinity" and
        qbounds[-1]["upper"]["kind"] == "positive_infinity" and
        qbounds[1]["lower"]["value_cny"] == STEP and qbounds[1]["upper"]["value_cny"] == 2 * STEP,
        bounds=qbounds)
    first_results = run_path(rows[:1], [], 1, (START,))[0]
    first = first_results[0]["summary"]
    add("first_day_turnover_not_an_implicit_unit_seed", abs(first["unknown_initial_mass"] - .992) < 1e-14 and
        abs(first["known_observed_contribution_mass"] - .008) < 1e-14,
        first_day_summary=first)
    point = daily_allocation({"low": 10.005, "high": 10.005, "open": 10.005, "close": 10.005})
    add("fixed_grid_flat_day_preserves_unit_mass_and_price", abs(point.sum() - 1) < 1e-14 and
        abs(np.dot(np.arange(len(point)) * STEP, point) - 10.005) < 1e-12)
    add("source_start_avoids_unbridged_20220526_without_claiming_full_action_coverage",
        rows[0]["trade_date"] == START and all(r["provenance"]["input_min_trade_date"] == START for r in results),
        prior_20220526_jump_not_crossed=True, complete_corporate_action_coverage_certified=False)
    add("all_918_days_diagnostics_only_each_multiplier",
        sum(d["research_918_scope"] for d in diagnostics) == 918 * 3 and
        all(not d["model_input_approved"] and not d["prediction_reliability_certified"] for d in diagnostics),
        research_daily_diagnostic_rows=sum(d["research_918_scope"] for d in diagnostics),
        saved_full_distribution_dates=list(TARGETS))
    add("gate_flags_remain_false", all(not r["summary"]["model_input_approved"] and
        not r["summary"]["native_supplier_bins_acquired"] for r in results))
    return checks


def write_sqlite(path, results, diagnostics, manifest, implementation_hash):
    path = Path(path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript("""
    PRAGMA page_size=4096;
    PRAGMA journal_mode=DELETE;
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
    CREATE TABLE estimate_runs(estimate_id TEXT PRIMARY KEY,asof_date TEXT NOT NULL,
       variant TEXT NOT NULL,unknown_initial_mass REAL NOT NULL,
       known_observed_mass REAL NOT NULL,params_json TEXT NOT NULL,
       summary_json TEXT NOT NULL,provenance_json TEXT NOT NULL,
       model_input_approved INTEGER NOT NULL CHECK(model_input_approved=0),
       native_supplier_bins_acquired INTEGER NOT NULL CHECK(native_supplier_bins_acquired=0));
    CREATE TABLE known_observed_bins(estimate_id TEXT NOT NULL,bin_index INTEGER NOT NULL,
       price_cny REAL NOT NULL,observed_contribution_mass REAL NOT NULL,
       conditional_known_mass REAL NOT NULL,total_cdf_lower REAL NOT NULL,
       total_cdf_upper REAL NOT NULL,PRIMARY KEY(estimate_id,bin_index));
    CREATE TABLE initialization_diagnostics(asof_date TEXT NOT NULL,variant TEXT NOT NULL,
       unknown_initial_mass REAL NOT NULL,known_observed_mass REAL NOT NULL,
       diagnostic_json TEXT NOT NULL,model_input_approved INTEGER NOT NULL CHECK(model_input_approved=0),
       native_supplier_bins_acquired INTEGER NOT NULL CHECK(native_supplier_bins_acquired=0),
       PRIMARY KEY(asof_date,variant));
    """)
    metadata = {"algorithm_version": VERSION, "source_manifest": manifest,
                "implementation_sha256": implementation_hash,
                "scope": {"full_observed_bins_dates": list(TARGETS), "multipliers": list(MULTIPLIERS),
                          "initialization_daily_count_per_multiplier": len(diagnostics) // 3,
                          "research_918_full_bins_built": False, "future_returns_read": False},
                "semantics": {"observed_contribution_mass": "subprobability; sum=known_observed_mass, never total mass 1",
                              "conditional_known_mass": "observed mass divided by known mass; only a conditional distribution",
                              "total_cdf_bounds_at_finite_x": "K_t(x) <= F_t(x) <= K_t(x)+unknown_initial_mass",
                              "below_saved_known_grid_cdf_bounds": "[0,unknown_initial_mass]",
                              "above_saved_known_grid_cdf_bounds": "[known_observed_mass,1]",
                              "unknown_price_support": "unrestricted; no finite total mean bounds",
                              "initialization_tv_diameter": "at most unknown_initial_mass; excludes all other model misspecification"}}
    for key in sorted(metadata):
        conn.execute("INSERT INTO metadata VALUES (?,?)", (key, canonical(metadata[key]).decode()))
    for result in results:
        summary, observed = result["summary"], result["observed_mass"]
        known, unknown = float(observed.sum()), summary["unknown_initial_mass"]
        conn.execute("INSERT INTO estimate_runs VALUES (?,?,?,?,?,?,?,?,0,0)",
                     (result["estimate_id"], summary["asof_date"], summary["variant"], unknown, known,
                      canonical(result["params"]).decode(), canonical(summary).decode(), canonical(result["provenance"]).decode()))
        cdf = np.cumsum(observed)
        conn.executemany("INSERT INTO known_observed_bins VALUES (?,?,?,?,?,?,?)",
                         ((result["estimate_id"], i, i * STEP, float(m), float(m / known),
                           min(1., max(0., float(cdf[i]))), min(1., max(0., float(cdf[i]) + unknown)))
                          for i, m in enumerate(observed)))
    for daily in diagnostics:
        conn.execute("INSERT INTO initialization_diagnostics VALUES (?,?,?,?,?,0,0)",
                     (daily["asof_date"], daily["variant"], daily["unknown_initial_mass"],
                      daily["known_observed_contribution_mass"], canonical(daily).decode()))
    conn.commit()
    conn.close()


def bound_text(bound):
    def fmt(e):
        return f"{e['value_cny']:.2f}" if e["kind"] == "finite" else "−∞" if e["kind"] == "negative_infinity" else "+∞"
    return fmt(bound["lower"]) + "—" + fmt(bound["upper"])


def mass_pct(value):
    # Scientific notation keeps nonzero stress-case residuals visibly nonzero.
    return f"{100 * value:.6e}%" if 0 < value < 1e-8 else f"{value:.6%}"


def report(results, diagnostics, checks, manifest, database_hash):
    base = [r for r in results if r["summary"]["variant"] == "turnover_x1"]
    lines = ["# 筹码初始化改进 v2：共同起点与未知质量边界", "",
             "研究日：2026-10-26。本轮只读取本地统一库，不联网、不采集新行情、不读取未来收益。固定2022-06-01为共同起点，逐交易日递推1064日；保存原定12技术日期×3换手倍率的36组已观察质量价档。2023-01-03—2026-10-21的918日仅扩展初始化诊断，不扩展为预测样本。", "",
             "本轮解决了滚动120日反复重置和240日跨越未知2022-05-26跳变的问题，但没有补齐真实初始持仓。所有记录 `model_input_approved=false`、`native_supplier_bins_acquired=false`；所有日期均未认证预热充分、预测可靠性或完整分派史。", "",
             "## 初始化定义与边界", "",
             "在2022-06-01交易前置未知质量U=1、已观察质量Q=0；首日同样使用当日换手。每日先按已知除权条款变换旧已观察质量的价格坐标，再递推 Q_t=(1−u_t)T_t Q_{t−1}+u_t D_t，U_t=(1−u_t)U_{t−1}=∏(1−u)。Q始终保留次概率质量，其和为1−U，绝不重新归一成总体筹码。日内D沿用明确的三角量价假设；固定0.01元网格、换手倍率0.5/1/1.5，均未根据未来结果或网页值选择。", "",
             "这里的“已观察”只指日线量价和换手在模型中新生成的贡献，不代表真实持有人逐笔账本；换手率不保证随机均匀替换旧持仓。未知初始价位不设点值、不设上下限，也不假设其位于起点当日高低价。", "",
             "对任意有限价格x，令K_t(x)=Σ_{p≤x}Q_t(p)，则总体CDF满足 K_t(x)≤F_t(x)≤K_t(x)+U_t；获利质量上下界是K_t(close)与K_t(close)+U_t。任意两种未知初始化在同一模型下的总变差距离≤U_t（总变差定义为sup_A|P(A)−P′(A)|）。这个界只量化初始化差异，不涵盖换手机制、日内分配或遗漏分派等误差。", "",
             "总体q分位下界为已观察累计质量到q−U的价位，q≤U时为−∞；上界为已观察累计质量到q的价位，q>1−U时为+∞。不限制未知初始支持或矩时，总体均值没有有限上下界，全部留空。已观察部分可另报条件均值/条件获利比例，但不能冒充总体值。", "",
             "## 基准倍率1的12个技术日期", "",
             "|日期|累计递推日|未知初始质量/TV上界|已观察质量|总体获利质量界|总体中位成本界（元）|已观察条件均值（元）|",
             "|---|---:|---:|---:|---|---|---:|"]
    for result in base:
        s = result["summary"]
        median = next(q for q in s["total_quantile_bounds"] if q["q"] == .5)
        lines.append(f"|{s['asof_date']}|{s['observed_trading_days']}|{mass_pct(s['unknown_initial_mass'])}|{s['known_observed_contribution_mass']:.6%}|{s['profit_mass_lower']:.4%}—{s['profit_mass_upper']:.4%}|{bound_text(median)}|{s['known_only_conditional_mean_cny']:.4f}|")
    lines += ["", "2023年早期仍有显著未知质量。累计交易日更长和未知质量下降仅表示本模型中初始状态被换手衰减，不能据此认证充分预热。本轮没有把≤1%或其他研究阈值当作可靠性通过线，也没有因未知质量很小就将其强制置零。", "",
              "## 换手倍率压力与除权", "",
              "|日期|倍率0.5未知质量|倍率1未知质量|倍率1.5未知质量|", "|---|---:|---:|---:|"]
    lookup = {(r["summary"]["asof_date"], r["summary"]["variant"]): r["summary"] for r in results}
    for date in TARGETS:
        vals = [lookup[(date, variant(mult))]["unknown_initial_mass"] for mult in MULTIPLIERS]
        lines.append(f"|{date}|{mass_pct(vals[0])}|{mass_pct(vals[1])}|{mass_pct(vals[2])}|")
    lines += ["", "极小未知残量以科学记数法显示；表中获利上下界经过四位小数百分数舍入，有时显示相同，机器文件仍保留其非零宽度。", "",
              "三项已知除权为2023-06-20（d=0.13元/旧股、s=0.3）、2024-05-24（d=0.014、s=0）、2026-09-22（d=0.1、s=0）。只在各除权日应用p′=(p−d)/(1+s)到当时旧已观察质量，并按固定网格线性分摊；保留质量和一阶矩。未知质量本身不因全体同权转增而改变，其未知价格只保留为未指定分布的坐标推前，不伪造价档。除权后再执行当日换手。", "",
              "共同起点选在2022-05-26未桥接跳变之后，因而没有拿未知分派条款反推或拼接早期价格；该起点是冻结的工程选择，并不认证2022-06-01以后分派史完全覆盖。历史原始行情于2026年取得、公告分钟级首发未认证，因此本轮证明的是数据计算前缀因果性，不能证明当时已收集到全部输入。", "",
              "## 验证与重建", "",
              f"{sum(c['passed'] for c in checks)}/{len(checks)}项针对性检查通过：已观察＋未知=1、未知等于∏(1−u)、未知单调、36组完整前缀不变、未来价格/换手/分派污染不变、三项除权守恒、三倍率顺序、早期不认证、CDF与分位边界、首日非单位seed、SQLite字节重跑和旧文件哈希前后不变。通过表示实现符合声明，不表示真实筹码或预测准确。", "",
              "- `初始化改进v2.sqlite`：36组已观察价档、逐格总体CDF界、3192条日诊断（其中2754条属918日研究范围）。",
              "- `固定日期结果.json`：36组摘要、价档、因果来源；价档总和是已观察质量。",
              "- `逐日初始化诊断.json`、`918日基准初始化诊断.csv`：仅初始化与质量诊断。",
              "- `基准12日摘要.csv`、`来源与参数.json`、`验证结果.json`、`旧原件哈希前后.json`。",
              "- `算法实现.py`、`重建说明.md`：本地可重复实现与命令。", "",
              f"只读统一库SHA-256：`{manifest['database_sha256_before']}`。新SQLite SHA-256：`{database_hash}`。旧输出与原库保留，未导入或执行旧算法及任何远程代码。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project = args.project_root.resolve()
    work = project / "work/chip_initialization_oct26"
    output = project / "outputs/初始化与验证推进_20261026/筹码初始化"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    rows, actions, manifest, evidence_files = load_sources(project)
    old_before = preserved_snapshot(project, evidence_files)
    implementation_hash = filehash(Path(__file__))
    results, diagnostics = [], []
    for mult in MULTIPLIERS:
        rr, dd = run_path(rows, actions, mult)
        results.extend(rr)
        diagnostics.extend(dd)
    checks = validate(rows, actions, results, diagnostics)
    db = output / "初始化改进v2.sqlite"
    repeat = work / "_repro_check.sqlite"
    write_sqlite(db, results, diagnostics, manifest, implementation_hash)
    write_sqlite(repeat, results, diagnostics, manifest, implementation_hash)
    db_hash, repeat_hash = filehash(db), filehash(repeat)
    checks.append({"name": "sqlite_deterministic_byte_rerun", "passed": db_hash == repeat_hash,
                   "first_sha256": db_hash, "repeat_sha256": repeat_hash})
    repeat.unlink()
    old_after = preserved_snapshot(project, evidence_files)
    checks.append({"name": "old_originals_database_script_and_outputs_hashes_unchanged",
                   "passed": old_before == old_after, "checked_files": len(old_before),
                   "changed_files": sorted(p for p in set(old_before) | set(old_after) if old_before.get(p) != old_after.get(p))})
    validation = {"algorithm_version": VERSION, "all_technical_checks_passed": all(c["passed"] for c in checks),
                  "checks": checks, "saved_full_distribution_runs": len(results),
                  "saved_full_distribution_dates": list(TARGETS),
                  "saved_daily_diagnostic_rows": len(diagnostics),
                  "research_918_daily_diagnostic_rows": sum(d["research_918_scope"] for d in diagnostics),
                  "future_returns_read": False, "model_input_approved": False,
                  "native_supplier_bins_acquired": False}
    write_json(output / "验证结果.json", validation)
    write_json(output / "旧原件哈希前后.json", {"before": old_before, "after": old_after, "all_unchanged": old_before == old_after})
    write_json(output / "来源与参数.json", {"source_manifest": manifest,
               "params": [params(m) for m in MULTIPLIERS], "implementation_sha256": implementation_hash,
               "python_version": platform.python_version(), "numpy_version": np.__version__,
               "sqlite_version": sqlite3.sqlite_version, "database_sha256": db_hash})
    write_json(output / "固定日期结果.json", {"algorithm_version": VERSION,
               "results": [frozen_result(r) for r in results], "full_total_distribution_identified": False,
               "model_input_approved": False, "native_supplier_bins_acquired": False})
    write_json(output / "逐日初始化诊断.json", {"algorithm_version": VERSION, "diagnostics": diagnostics,
               "future_returns_read": False, "model_input_approved": False, "native_supplier_bins_acquired": False})
    base = [r["summary"] for r in results if r["summary"]["variant"] == "turnover_x1"]
    simple_fields = [k for k in base[0] if k != "total_quantile_bounds"]
    with (output / "基准12日摘要.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=simple_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(base)
    dd = [d for d in diagnostics if d["variant"] == "turnover_x1" and d["research_918_scope"]]
    with (output / "918日基准初始化诊断.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dd[0]))
        writer.writeheader()
        writer.writerows(dd)
    (output / "筹码初始化改进v2报告.md").write_text(report(results, diagnostics, checks, manifest, db_hash), encoding="utf-8")
    (output / "算法实现.py").write_bytes(Path(__file__).read_bytes())
    readme = f"""# 本地重建

```sh
/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \\
  work/chip_initialization_oct26/build_initialization_v2.py \\
  --project-root /Users/puchun/Documents/Codex/2026-10-07/ni
```

依赖Python {platform.python_version()}、NumPy {np.__version__}、SQLite {sqlite3.sqlite_version}，不联网。只写本任务work与outputs/初始化与验证推进_20261026/筹码初始化。源统一库以只读immutable方式打开。

common_origin为2022-06-01交易前：未知质量1、已观察质量0；首日换手包含在乘积。每日子概率Q不重归一，U不硬置零。known_observed_bins.observed_contribution_mass求和为1−U；conditional_known_mass才另行归一，不能作为总体筹码。CDF上下界只依赖未知质量，不限制未知价格支持，网格外允许未知质量。总体均值空值，分位无穷界用kind标记。

SQL未读取未来收益表、网页筹码摘要或现时前复权序列。prefix测试是计算因果性证明；原始输入历史可用性未认证，模型门不因此开放。

源统一库SHA-256：{manifest['database_sha256_before']}。
脚本SHA-256：{implementation_hash}。
SQLite SHA-256：{db_hash}。
"""
    (output / "重建说明.md").write_text(readme, encoding="utf-8")
    (work / "README.md").write_text(readme, encoding="utf-8")
    write_json(work / "validation_summary.json", validation)
    if not validation["all_technical_checks_passed"]:
        raise SystemExit("technical validation failed; inspect 验证结果.json")
    print(json.dumps({"status": "complete", "output": str(output), "runs": len(results),
                      "diagnostics": len(diagnostics), "checks": len(checks),
                      "database_sha256": db_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
