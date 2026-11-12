#!/usr/bin/env python3
"""Causal, explicitly hypothetical chip-cost distributions; no vendor-bin claim.

Run with the pinned Python shown in README.md. The source database is opened as
an immutable read-only URI. Only the two task-owned directories are written.
No AKShare or downloaded source code is imported or executed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path
import platform
import sqlite3
import sys

import numpy as np

VERSION = "causal-triangular-chip-sample-v1"
STUDY_DATE = "2026-10-25"
TARGETS = (
    "2023-01-03", "2023-06-19", "2023-06-20", "2023-06-21",
    "2024-05-23", "2024-05-24", "2024-05-27",
    "2026-09-21", "2026-09-22", "2026-09-23",
    "2026-10-16", "2026-10-21",
)
RAW_SQL = """SELECT observation_id,trade_date,open,high,low,close,turnover_pct,
    adjustment,adjustment_vintage,turnover_unit,retrieved_at,source_sha256,
    source_request_id,raw_row_index,input_path,input_row_index,model_input_approved,
    has_price_source_conflict,has_volume_source_conflict
    FROM stock_raw_reference WHERE trade_date <= '2026-10-21' ORDER BY trade_date"""


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def objhash(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def filehash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Params:
    variant: str = "base_120d_1cent_tri_seed"
    window_days: int = 120
    grid_step_cny: float = 0.01
    grid_origin_cny: float = 0.0
    seed: str = "first_day_triangle"
    turnover_multiplier: float = 1.0
    turnover_treatment: str = "u=clip(multiplier*provider_turnover_pct/100,0,1)"
    distribution: str = "triangle(low, mode=(open+high+low+close)/4, high)"
    daily_allocation: str = "triangle_CDF_integrated_over_fixed_grid_Voronoi_cells"
    corporate_action_rule: str = "before_ex_day_turnover: p_new=(p_old-d)/(1+s)"
    grid_rebin_rule: str = "linear_barycentric_mass_split_preserving_first_moment"
    price_basis: str = "unadjusted_raw_then_causal_ex_day_coordinate_changes"
    initialization: str = "unit_mass_at_first_window_day; no unknown_prehistory_inferred"
    outside_saved_domain_mass: float = 0.0
    model_input_approved: bool = False
    native_supplier_bins_acquired: bool = False


BASE = Params()
VARIANTS = (
    BASE,
    replace(BASE, variant="window_240d", window_days=240),
    replace(BASE, variant="grid_half_cent", grid_step_cny=0.005),
    replace(BASE, variant="grid_five_cents", grid_step_cny=0.05),
    replace(BASE, variant="seed_first_close", seed="first_day_close_point"),
    replace(BASE, variant="turnover_half", turnover_multiplier=0.5),
    replace(BASE, variant="turnover_one_and_half", turnover_multiplier=1.5),
)


def normalize(mass: np.ndarray) -> np.ndarray:
    if np.min(mass) < -1e-13:
        raise ValueError("negative probability mass")
    mass = np.maximum(mass, 0.0)
    total = float(mass.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("empty distribution")
    return mass / total


def point_to_grid(prices, weights, step: float) -> np.ndarray:
    """A point between two frozen grid nodes is split linearly, without clipping."""
    prices = np.asarray(prices, dtype=float)
    weights = np.asarray(weights, dtype=float)
    active = weights > 0
    prices, weights = prices[active], weights[active]
    if len(prices) == 0 or float(prices.min()) < 0:
        raise ValueError("nonpositive-cost corporate-action case needs explicit policy")
    coords = prices / step
    left = np.floor(coords).astype(int)
    right_share = coords - left
    out = np.zeros(int(np.max(left)) + 2, dtype=float)
    np.add.at(out, left, weights * (1.0 - right_share))
    np.add.at(out, left + 1, weights * right_share)
    # Preserve every internal zero bin; a trailing exactly-zero node is redundant.
    end = int(np.flatnonzero(out > 0)[-1]) + 1
    return normalize(out[:end])


def triangle_cdf(x: np.ndarray, lo: float, mode: float, hi: float) -> np.ndarray:
    out = np.zeros_like(x, dtype=float)
    out[x >= hi] = 1.0
    inside = (x > lo) & (x < hi)
    if mode <= lo:
        out[inside] = 1.0 - ((hi - x[inside]) / (hi - lo)) ** 2
    elif mode >= hi:
        out[inside] = ((x[inside] - lo) / (hi - lo)) ** 2
    else:
        left = inside & (x <= mode)
        right = inside & (x > mode)
        out[left] = (x[left] - lo) ** 2 / ((hi - lo) * (mode - lo))
        out[right] = 1.0 - (hi - x[right]) ** 2 / ((hi - lo) * (hi - mode))
    return out


def daily_allocation(row: dict, params: Params) -> np.ndarray:
    lo, hi = row["low"], row["high"]
    if hi == lo:
        return point_to_grid([lo], [1.0], params.grid_step_cny)
    mode = sum(row[k] for k in ("open", "high", "low", "close")) / 4.0
    step = params.grid_step_cny
    # Grid spacing and origin are fixed constants, not functions of any future range.
    count = int(math.ceil(hi / step)) + 1
    nodes = np.arange(count, dtype=float) * step
    upper = triangle_cdf(nodes + step / 2.0, lo, mode, hi)
    lower = triangle_cdf(nodes - step / 2.0, lo, mode, hi)
    mass = normalize(upper - lower)
    end = int(np.flatnonzero(mass > 0)[-1]) + 1
    return mass[:end]


def blend(old: np.ndarray, new: np.ndarray, u: float) -> np.ndarray:
    size = max(len(old), len(new))
    result = np.zeros(size, dtype=float)
    result[:len(old)] += old * (1.0 - u)
    result[:len(new)] += new * u
    return normalize(result)


def mean_cost(mass: np.ndarray, step: float) -> float:
    return float(np.dot(np.arange(len(mass)) * step, mass))


def quantile_cost(mass: np.ndarray, step: float, quantile: float) -> float:
    index = int(np.searchsorted(np.cumsum(mass), quantile, side="left"))
    return float(min(index, len(mass) - 1) * step)


def transform_action(mass: np.ndarray, step: float, event: dict):
    d, s = event["cash_cny_per_share_gross"], event["transfer_per_share"]
    before = mean_cost(mass, step)
    active = np.flatnonzero(mass > 0)
    prices_new = (active * step - d) / (1.0 + s)
    result = point_to_grid(prices_new, mass[active], step)
    after = mean_cost(result, step)
    audit = {
        "event_id": event["event_id"], "ex_date": event["ex_date"],
        "cash_cny_per_share_gross": d, "transfer_per_share": s,
        "pre_action_mean_cny": before, "post_action_old_mass_mean_cny": after,
        "expected_mean_cny": (before - d) / (1.0 + s),
        "mass_before": float(mass.sum()), "mass_after": float(result.sum()),
        "absolute_mean_error_cny": abs(after - (before - d) / (1.0 + s)),
        "share_mass_reason": "uniform_transfer_scales_all_holders_equally; normalized_weights_unchanged",
    }
    return result, audit


def estimate(rows: list[dict], actions: list[dict], asof: str, params: Params):
    # Filtering precedes window selection, discontinuity scanning, and grid creation.
    prefix = [r for r in rows if r["trade_date"] <= asof]
    if not prefix or prefix[-1]["trade_date"] != asof:
        raise ValueError("requested date has no raw daily bar")
    window = prefix[-params.window_days:]
    first = window[0]
    if params.seed == "first_day_triangle":
        mass = daily_allocation(first, params)
    elif params.seed == "first_day_close_point":
        mass = point_to_grid([first["close"]], [1.0], params.grid_step_cny)
    else:
        raise ValueError("unknown seed")
    seed_weight = 1.0
    active_actions = [a for a in actions if first["trade_date"] < a["ex_date"] <= asof]
    action_map = {a["ex_date"]: a for a in active_actions}
    audits, unknown_discontinuities = [], []
    for previous, row in zip(window, window[1:]):
        date = row["trade_date"]
        if date in action_map:
            mass, audit = transform_action(mass, params.grid_step_cny, action_map[date])
            audits.append(audit)
        elif abs(row["open"] / previous["close"] - 1.0) > 0.15:
            unknown_discontinuities.append({
                "trade_date": date, "previous_close": previous["close"],
                "open": row["open"], "open_gap_fraction": row["open"] / previous["close"] - 1.0,
                "status": "unbridged_large_gap_not_proof_of_corporate_action",
            })
        u = min(1.0, max(0.0, row["turnover_pct"] / 100.0 * params.turnover_multiplier))
        seed_weight *= 1.0 - u
        mass = blend(mass, daily_allocation(row, params), u)
    step = params.grid_step_cny
    close = prefix[-1]["close"]
    nodes = np.arange(len(mass)) * step
    c70lo, c70hi = quantile_cost(mass, step, .15), quantile_cost(mass, step, .85)
    c90lo, c90hi = quantile_cost(mass, step, .05), quantile_cost(mass, step, .95)
    summary = {
        "asof_date": asof, "variant": params.variant, "close_raw_cny": close,
        "mean_cost_cny": mean_cost(mass, step),
        "median_cost_cny": quantile_cost(mass, step, .5),
        "profit_mass_fraction_cost_le_close": float(mass[nodes <= close + 1e-12].sum()),
        "cost70_low_cny": c70lo, "cost70_high_cny": c70hi,
        "cost90_low_cny": c90lo, "cost90_high_cny": c90hi,
        "concentration70_fraction": (c70hi - c70lo) / (c70hi + c70lo),
        "concentration90_fraction": (c90hi - c90lo) / (c90hi + c90lo),
        "seed_mass_remaining_fraction": seed_weight,
        "window_start": first["trade_date"], "window_end": asof,
        "requested_window_days": params.window_days, "actual_window_days": len(window),
        "available_prefix_days": len(prefix),
        "warmup_insufficient": len(prefix) < params.window_days,
        "prehistoric_holder_costs_observed": False,
        "unbridged_large_gap_count": len(unknown_discontinuities),
        "known_coordinate_events_applied_and_no_flagged_gap": not unknown_discontinuities,
        "complete_corporate_action_coverage_certified": False,
        "mass_sum": float(mass.sum()), "bin_count_including_zeros": len(mass),
        "grid_domain_low_cny": 0.0, "grid_domain_high_cny": float(nodes[-1]),
        "outside_saved_domain_mass": 0.0,
        "estimate_status": "diagnostic_scale_bridge_unresolved" if unknown_discontinuities else "hypothetical_unapproved_estimate",
        "model_input_approved": False, "native_supplier_bins_acquired": False,
    }
    provenance = {
        "input_view": "stock_raw_reference", "prefix_rows_sha256": objhash(prefix),
        "window_rows_sha256": objhash(window),
        "window_observation_ids": [r["observation_id"] for r in window],
        "input_max_trade_date": prefix[-1]["trade_date"],
        "raw_source_hashes": sorted({r["source_sha256"] for r in window}),
        "raw_retrieved_at_values": sorted({r["retrieved_at"] for r in window}),
        "historical_first_seen_certified": False,
        "turnover_units": sorted({r["turnover_unit"] for r in window}),
        "price_source_conflict_days_in_window": [r["trade_date"] for r in window if r["has_price_source_conflict"]],
        "volume_source_conflict_days_in_window": [r["trade_date"] for r in window if r["has_volume_source_conflict"]],
        "applied_actions_sha256": objhash(active_actions),
        "action_audits": audits,
        "unbridged_large_gaps": unknown_discontinuities,
    }
    return {"estimate_id": params.variant + ":" + asof, "params": asdict(params),
            "summary": summary, "provenance": provenance, "mass": mass}


def frozen_result(result):
    return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in result.items()}


def load_sources(project: Path):
    path = project / "outputs/统一数据底座_20261022/统一数据底座.sqlite"
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    rows = [dict(r) for r in connection.execute(RAW_SQL)]
    actions = []
    for raw in connection.execute("SELECT * FROM corporate_actions ORDER BY ex_date"):
        a = dict(raw)
        a["cash_cny_per_share_gross"] = float(Decimal(a["cash_cny_per_10_gross"]) / Decimal(10))
        a["transfer_per_share"] = float(Decimal(a["transfer_shares_per_10"]) / Decimal(10))
        a["cash_definition"] = "gross_cash_per_old_share; not_personal_after_tax_payment"
        payload = json.loads(a["payload_json"])
        filing = connection.execute("SELECT * FROM filings WHERE art_code=?", (payload["art_code"],)).fetchone()
        a["filing"] = dict(filing) if filing else None
        if filing:
            time_payload = json.loads(filing["time_payload_json"])
            a["official_original_url"] = time_payload.get("official_original_url")
            original = project / filing["original_path"]
            a["local_original_actual_sha256"] = filehash(original)
            if a["local_original_actual_sha256"] != filing["original_sha256"]:
                raise ValueError("corporate action original file hash mismatch")
        actions.append(a)
    request = [dict(r) for r in connection.execute("SELECT * FROM source_requests WHERE request_id='em_002414.SZ_0'")]
    ingress = [dict(r) for r in connection.execute("SELECT * FROM ingestion_sources WHERE dataset_id IN ('market_industry_oct21','corporate_actions') ORDER BY dataset_id")]
    metadata = [dict(r) for r in connection.execute("SELECT * FROM metadata WHERE key IN ('build','selection_policy') ORDER BY key")]
    connection.close()
    manifest = {
        "database_relative_path": str(path.relative_to(project)),
        "database_sha256_before": filehash(path), "read_mode": "file_URI_mode=ro&immutable=1",
        "raw_query": RAW_SQL, "raw_row_count": len(rows),
        "raw_min_date": rows[0]["trade_date"], "raw_max_date": rows[-1]["trade_date"],
        "raw_rows_sha256": objhash(rows), "source_requests": request,
        "ingestion_sources": ingress, "database_source_metadata": metadata,
        "source_raw_file_actual_sha256": [],
        "corporate_actions": actions,
        "code_reference": {
            "local_path": "work/collector/stock_cyq_em.py",
            "local_sha256": filehash(project / "work/collector/stock_cyq_em.py"),
            "official_source_url": "https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_cyq_em.py",
            "official_source_inspected_study_date": STUDY_DATE,
            "method": "read_for_technical_context_only; independently_implemented_numpy_algorithm",
            "downloaded_code_executed": False,
        },
        "historical_timestamp_certification": "raw bars were retrieved in 2026; historical first_seen not certified; action first_publication minute unknown",
        "model_input_approved": False, "native_supplier_bins_acquired": False,
    }
    for r in request:
        p = project / r["raw_path"]
        actual = filehash(p)
        if actual != r["source_sha256"]:
            raise ValueError("raw source response hash mismatch")
        manifest["source_raw_file_actual_sha256"].append({"path": r["raw_path"], "sha256": actual})
    return path, rows, actions, manifest


def compare_to_base(result, base):
    a, b = result["summary"], base["summary"]
    return {
        "asof_date": a["asof_date"], "variant": a["variant"],
        "mean_delta_cny": a["mean_cost_cny"] - b["mean_cost_cny"],
        "median_delta_cny": a["median_cost_cny"] - b["median_cost_cny"],
        "profit_mass_delta_percentage_points": 100 * (a["profit_mass_fraction_cost_le_close"] - b["profit_mass_fraction_cost_le_close"]),
        "cost90_low_delta_cny": a["cost90_low_cny"] - b["cost90_low_cny"],
        "cost90_high_delta_cny": a["cost90_high_cny"] - b["cost90_high_cny"],
        "seed_mass_remaining_fraction": a["seed_mass_remaining_fraction"],
        "unbridged_large_gap_count": a["unbridged_large_gap_count"],
        "comparison_status": "diagnostic_only_unbridged_historical_gap" if a["unbridged_large_gap_count"] else "parameter_sensitivity_not_fit_quality",
    }


def write_sqlite(path, results, manifest, script_hash):
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA page_size=4096;
        PRAGMA journal_mode=DELETE;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
        CREATE TABLE estimate_runs(
            estimate_id TEXT PRIMARY KEY,asof_date TEXT NOT NULL,variant TEXT NOT NULL,
            params_json TEXT NOT NULL,summary_json TEXT NOT NULL,provenance_json TEXT NOT NULL,
            model_input_approved INTEGER NOT NULL CHECK(model_input_approved=0),
            native_supplier_bins_acquired INTEGER NOT NULL CHECK(native_supplier_bins_acquired=0),
            UNIQUE(asof_date,variant));
        CREATE TABLE estimated_price_bins(
            estimate_id TEXT NOT NULL,bin_index INTEGER NOT NULL,price_cny REAL NOT NULL,
            estimated_mass_fraction REAL NOT NULL CHECK(estimated_mass_fraction>=0),
            PRIMARY KEY(estimate_id,bin_index),
            FOREIGN KEY(estimate_id) REFERENCES estimate_runs(estimate_id));
    """)
    entries = {"algorithm_version": VERSION, "study_date": STUDY_DATE,
               "source_manifest": manifest, "implementation_sha256": script_hash,
               "scope": {"saved_dates": sorted({r["summary"]["asof_date"] for r in results}),
                         "all_918_daily_distributions_built": False,
                         "bins_semantics": "complete evaluated fixed-grid domain from 0 through saved maximum; all outside mass exactly zero",
                         "model_input_approved": False, "native_supplier_bins_acquired": False}}
    for key in sorted(entries):
        connection.execute("INSERT INTO metadata VALUES (?,?)", (key, canonical(entries[key]).decode()))
    for r in results:
        s = r["summary"]
        connection.execute("INSERT INTO estimate_runs VALUES (?,?,?,?,?,?,0,0)",
                           (r["estimate_id"], s["asof_date"], s["variant"], canonical(r["params"]).decode(),
                            canonical(s).decode(), canonical(r["provenance"]).decode()))
        step = r["params"]["grid_step_cny"]
        connection.executemany("INSERT INTO estimated_price_bins VALUES (?,?,?,?)",
                               ((r["estimate_id"], i, i * step, float(weight)) for i, weight in enumerate(r["mass"])))
    connection.commit()
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    connection.close()
    if integrity != "ok":
        raise ValueError("output SQLite integrity check failed")


def validate(rows, actions, results):
    checks = []
    dates = [r["trade_date"] for r in rows]
    input_ok = (len(rows) == 1160 and len(set(dates)) == len(rows) and dates == sorted(dates)
                and all(r["adjustment"] == "0" and r["model_input_approved"] == 0 for r in rows)
                and all(0 < r["low"] <= min(r["open"], r["close"]) <= max(r["open"], r["close"]) <= r["high"] for r in rows)
                and all(math.isfinite(r["turnover_pct"]) and r["turnover_pct"] >= 0 for r in rows))
    checks.append({"name": "input_contract", "passed": input_ok, "rows": len(rows), "min_date": dates[0], "max_date": dates[-1]})
    max_sum_error = max(abs(float(r["mass"].sum()) - 1) for r in results)
    checks.append({"name": "mass_sums_to_one", "passed": max_sum_error < 1e-12, "max_absolute_error": max_sum_error, "runs": len(results)})
    min_mass = min(float(np.min(r["mass"])) for r in results)
    checks.append({"name": "all_bins_nonnegative_and_finite", "passed": min_mass >= 0 and all(np.isfinite(r["mass"]).all() for r in results), "min_mass": min_mass})
    prefix_failures, future_mutation_failures, rerun_failures = [], [], []
    for result in results:
        s = result["summary"]
        params = next(p for p in VARIANTS if p.variant == s["variant"])
        asof = s["asof_date"]
        original = canonical(frozen_result(result))
        prefix = [r for r in rows if r["trade_date"] <= asof]
        past_actions = [a for a in actions if a["ex_date"] <= asof]
        if canonical(frozen_result(estimate(prefix, past_actions, asof, params))) != original:
            prefix_failures.append(result["estimate_id"])
        poisoned = [({**r, "open": 9999.0, "high": 9999.0, "low": .01, "close": 8888.0,
                      "turnover_pct": 999.0} if r["trade_date"] > asof else r) for r in rows]
        poisoned_actions = [({**a, "cash_cny_per_share_gross": 10000.0} if a["ex_date"] > asof else a) for a in actions]
        if canonical(frozen_result(estimate(poisoned, poisoned_actions, asof, params))) != original:
            future_mutation_failures.append(result["estimate_id"])
        if canonical(frozen_result(estimate(rows, actions, asof, params))) != original:
            rerun_failures.append(result["estimate_id"])
    checks.append({"name": "causal_prefix_invariance", "passed": not prefix_failures, "runs": len(results), "failures": prefix_failures})
    checks.append({"name": "future_price_turnover_action_mutation_invariance", "passed": not future_mutation_failures, "runs": len(results), "failures": future_mutation_failures})
    checks.append({"name": "deterministic_algorithm_rerun", "passed": not rerun_failures, "runs": len(results), "failures": rerun_failures})
    unit_expected = {"2023-06-20": (.13, .3), "2024-05-24": (.014, 0), "2026-09-22": (.1, 0)}
    unit_ok = all((a["cash_cny_per_share_gross"], a["transfer_per_share"]) == unit_expected[a["ex_date"]] for a in actions)
    synthetic_audits = []
    for a in actions:
        mass = point_to_grid([5., 10., 20.], [.2, .5, .3], .01)
        _, audit = transform_action(mass, .01, a)
        synthetic_audits.append(audit)
    real_audits = [a for r in results if r["summary"]["variant"] == BASE.variant for a in r["provenance"]["action_audits"]]
    action_ok = unit_ok and all(a["absolute_mean_error_cny"] < 1e-12 and abs(a["mass_after"] - 1) < 1e-12 for a in synthetic_audits + real_audits)
    checks.append({"name": "corporate_action_units_and_price_coordinate_mass_mean", "passed": action_ok,
                   "cash_and_transfer_per_10_divided_by_10": unit_ok,
                   "synthetic_audits": synthetic_audits, "real_window_audit_count": len(real_audits)})
    probe = estimate(rows[:1], [], dates[0], BASE)["summary"]
    checks.append({"name": "insufficient_initial_history_flag", "passed": probe["warmup_insufficient"] and probe["seed_mass_remaining_fraction"] == 1.0,
                   "probe_date": dates[0], "available_days": 1, "requested_days": 120, "saved_as_sample": False})
    # CDF-integrated allocation covers limiting cases, one-price bars, and all grids.
    fixtures = [dict(open=10., high=10., low=10., close=10.),
                dict(open=8., high=12., low=8., close=8.),
                dict(open=12., high=12., low=8., close=12.),
                dict(open=10., high=12., low=8., close=10.)]
    fixture_masses = [daily_allocation(f, p) for f in fixtures for p in VARIANTS]
    checks.append({"name": "triangle_allocation_and_one_price_edge_cases", "passed": all(abs(float(m.sum()) - 1) < 1e-12 and float(m.min()) >= 0 for m in fixture_masses), "cases": len(fixture_masses)})
    checks.append({"name": "fixed_grid_not_full_sample_extrema", "passed": all(p.grid_origin_cny == 0 and p.grid_step_cny in (.005, .01, .05) for p in VARIANTS),
                   "grid_definition": "origin=0, step frozen in params; node count grows only from already processed prices"})
    return checks


def build_report(results, sensitivity, checks, manifest, db_hash):
    base = [r for r in results if r["summary"]["variant"] == BASE.variant]
    lines = ["# 自建筹码成本小样本：量价情景估计", "",
        "研究日：2026-10-25。读取统一库不复权参考行情1160日（2022-01-04—2026-10-21），仅保存预先固定的12个技术日期、7种参数情景，共84组估计。",
        "这是一套可解释的成本分布假设，不是实际持有人账本或供应商原生价档；完整原生筹码缺口仍未补齐。所有记录保留 `model_input_approved=false`、`native_supplier_bins_acquired=false`。", "",
        "## 算法与标尺", "",
        "价格网格原点固定0元，基准间距0.01元；网格定义不依赖任何全样本高低价。每日在当日low—high之间放置三角密度，峰值位于OHLC均值，按固定网格单元的CDF差积分成质量，一字价用相邻网格点分摊。",
        "基准窗口120个已发生交易日，首日三角分布初始化为总质量1，此后用 P_t=(1-u_t)P_{t-1}+u_t D_t，u_t=clip(换手百分数/100,0,1)。换手分母与口径未获正式认证，因此这是条件性情景；没有用未认证成交量单位反推出股数。固定窗口意味着每个目标日都从自己的窗口首日重建。",
        "除权日先变换旧筹码 p′=(p-d)/(1+s)，再加入当日原价分布；d为每旧股税前现金，s为每旧股转增比例。相邻网格线性分摊保持质量与一阶矩。未读取现时前复权序列，也未用现时前复权值回填历史。", "",
        "|除权日|每10股现金/转增|d（元/旧股）|s|", "|---|---:|---:|---:|"]
    for a in manifest["corporate_actions"]:
        lines.append(f"|{a['ex_date']}|{a['cash_cny_per_10_gross']}元 / {a['transfer_shares_per_10']}股|{a['cash_cny_per_share_gross']}|{a['transfer_per_share']}|")
    lines += ["", "均值成本是ΣpP(p)；中位成本是50%分位；70%/90%区间分别为15%—85%、5%—95%等尾区间；获利质量是成本≤当日收盘价的估计占比，未计税费。集中度=(上界−下界)/(上界+下界)。这些字段是算法定义，不认证为网页供应商公式。", "",
              "## 基准技术日期", "", "|日期|收盘|均值成本|中位成本|90%区间|获利质量|初始化残存|", "|---|---:|---:|---:|---|---:|---:|"]
    for r in base:
        s = r["summary"]
        lines.append(f"|{s['asof_date']}|{s['close_raw_cny']:.2f}|{s['mean_cost_cny']:.4f}|{s['median_cost_cny']:.2f}|{s['cost90_low_cny']:.2f}—{s['cost90_high_cny']:.2f}|{s['profit_mass_fraction_cost_le_close']:.2%}|{s['seed_mass_remaining_fraction']:.2%}|")
    seed_min = min(r["summary"]["seed_mass_remaining_fraction"] for r in base)
    seed_max = max(r["summary"]["seed_mass_remaining_fraction"] for r in base)
    lines += ["", f"12个基准日期均有120日窗口，但初始化质量仍残存{seed_min:.2%}—{seed_max:.2%}。窗口齐全不等于真实历史持仓已观测；此前持有人成本未知，不能据此宣称充分预热。输入首日的专门测试仅有1天，已触发历史不足标记。", "",
              "## 敏感性", "", "参数先固定，不读取未来收益、不对网页值调参。下表给出各敏感性情景相对基准的最大绝对变化；240日情景剔除1组已标记的标尺桥未解决诊断结果，其余各行使用全部12日。没有发现大幅跳变不等于认证了完整分派史。", "",
              "|情景|均值成本最大变化（元）|中位成本最大变化（元）|获利质量最大变化（百分点）|", "|---|---:|---:|---:|"]
    for p in VARIANTS[1:]:
        ss = [s for s in sensitivity if s["variant"] == p.variant and s["unbridged_large_gap_count"] == 0]
        lines.append(f"|{p.variant}|{max(abs(s['mean_delta_cny']) for s in ss):.4f}|{max(abs(s['median_delta_cny']) for s in ss):.4f}|{max(abs(s['profit_mass_delta_percentage_points']) for s in ss):.3f}|")
    lines += ["", "240日情景在2023-01-03从2022-01-07开始，穿越2022-05-26约−29.58%的隔夜开盘跳变；统一库的三项分派条款没有覆盖该日，不能仅凭跳变反推出分派。该组标记为标尺桥未解决的诊断情景，不能解读为有效的初始化改善。120日基准该日从2022-07-11开始，没有穿越该跳变。", "",
              "## 验证与文件", "", f"{sum(c['passed'] for c in checks)}/{len(checks)}项技术检查通过：因果前缀不变、未来行情/换手/分派污染不变、质量和为1、非负、算法重跑及SQLite字节重跑、三项除权单位与标尺、历史不足、三角与一字价边界、冻结网格、初始化/网格/换手敏感性。通过这些检查只表示实现符合声明的算法，不表示估计等于真实筹码。", "",
              "- `自建筹码小样本.sqlite`：84组元数据及完整估计网格（含内部零质量格，域外质量为0）。",
              "- `样本摘要.json`、`基准摘要.csv`：技术日期摘要与全部情景参数。",
              "- `敏感性.json`、`验证结果.json`：逐日变化和可核验测试证据。",
              "- `来源与参数.json`：只读SQL、原始抓取时间、行情源哈希、分派原件哈希、代码哈希。",
              "- `重建说明.md`、`算法实现.py`：固定依赖、重建方法与完整实现。", "",
              "AKShare源码仅供技术思路阅读：其展示成本字段与日内分配可作为参考，本实现独立编写，未执行其代码，也不声称复刻东方财富。参考：[官方AKShare源码](https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_cyq_em.py)。", "",
              "行情原件抓取时间为2026-10-22，分派公告首次发布时间的分钟级与历史原版可用性未认证。本样本仅能证明数据计算的前缀因果性，不能证明这些历史输入在当时已被系统收集。网页摘要没有参与算法、参数选择或拟合，本次不做网页数值吻合验证。", "",
              f"统一库读取前后SHA-256均为 `{manifest['database_sha256_before']}`；原库未写入。样本SQLite SHA-256为 `{db_hash}`。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve()
    work = project / "work/local_chip_estimate_oct25"
    output = project / "outputs/三线研究启动_20261025/自建筹码样本"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    db_path, rows, actions, manifest = load_sources(project)
    script_hash = filehash(Path(__file__))
    present = {r["trade_date"] for r in rows}
    targets = [d for d in TARGETS if d in present]
    results = [estimate(rows, actions, d, p) for p in VARIANTS for d in targets]
    checks = validate(rows, actions, results)
    bases = {r["summary"]["asof_date"]: r for r in results if r["summary"]["variant"] == BASE.variant}
    sensitivity = [compare_to_base(r, bases[r["summary"]["asof_date"]]) for r in results if r["summary"]["variant"] != BASE.variant]
    checks.append({"name": "initialization_grid_turnover_sensitivity_exercised", "passed": len(sensitivity) == 6 * len(targets)
                   and {s["variant"] for s in sensitivity} == {p.variant for p in VARIANTS[1:]},
                   "comparisons": len(sensitivity), "parameters_fixed_before_comparison": True,
                   "future_returns_read": False, "web_summary_fit_used": False})
    database = output / "自建筹码小样本.sqlite"
    write_sqlite(database, results, manifest, script_hash)
    repeat_path = work / "_repro_check.sqlite"
    write_sqlite(repeat_path, results, manifest, script_hash)
    output_db_hash = filehash(database)
    checks.append({"name": "sqlite_deterministic_byte_rerun", "passed": filehash(repeat_path) == output_db_hash,
                   "first_sha256": output_db_hash, "repeat_sha256": filehash(repeat_path)})
    repeat_path.unlink()
    after_hash = filehash(db_path)
    checks.append({"name": "source_database_hash_unchanged", "passed": after_hash == manifest["database_sha256_before"],
                   "before_sha256": manifest["database_sha256_before"], "after_sha256": after_hash})
    validation = {"algorithm_version": VERSION, "all_technical_checks_passed": all(c["passed"] for c in checks),
                  "checks": checks, "requested_dates": list(TARGETS), "actual_saved_dates": targets,
                  "missing_requested_dates": sorted(set(TARGETS) - set(targets)),
                  "saved_estimate_runs": len(results), "saved_distinct_dates": len(targets),
                  "saved_price_bin_rows": sum(len(r["mass"]) for r in results),
                  "source_database_sha256_before": manifest["database_sha256_before"],
                  "source_database_sha256_after": after_hash,
                  "model_input_approved": False, "native_supplier_bins_acquired": False}
    summaries = {"algorithm_version": VERSION, "study_date": STUDY_DATE,
                 "params": [asdict(p) for p in VARIANTS],
                 "summaries": [r["summary"] for r in results],
                 "model_input_approved": False, "native_supplier_bins_acquired": False}
    write_json(output / "样本摘要.json", summaries)
    write_json(output / "敏感性.json", {"comparisons": sensitivity, "not_a_fit_exercise": True})
    write_json(output / "来源与参数.json", {"manifest": manifest, "params": [asdict(p) for p in VARIANTS],
               "implementation_sha256": script_hash, "python_version": platform.python_version(),
               "numpy_version": np.__version__, "sqlite_version": sqlite3.sqlite_version})
    write_json(output / "验证结果.json", validation)
    base_summaries = [r["summary"] for r in results if r["summary"]["variant"] == BASE.variant]
    with (output / "基准摘要.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(base_summaries[0]))
        writer.writeheader()
        writer.writerows(base_summaries)
    report = build_report(results, sensitivity, checks, manifest, output_db_hash)
    (output / "自建筹码估计报告.md").write_text(report, encoding="utf-8")
    (output / "算法实现.py").write_bytes(Path(__file__).read_bytes())
    readme = f"""# 重建说明

在同一项目和相同只读源库上运行：

```sh
/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \\
  work/local_chip_estimate_oct25/build_chip_sample.py \\
  --project-root /Users/puchun/Documents/Codex/2026-10-07/ni
```

依赖：Python {platform.python_version()}、NumPy {np.__version__}、标准库sqlite3（SQLite {sqlite3.sqlite_version}）。不需要联网或AKShare。运行将只重建本任务输出目录中的文件，并在本任务work目录创建后删除一次字节复验用SQLite。原库使用mode=ro&immutable=1，只读查询stock_raw_reference、corporate_actions和来源信息。

`estimated_price_bins`中的质量为0—1小数。每个estimate_id保存从原点0至因果计算中活动上界的全部网格格点，包含内部零质量，域外质量为0。网格间距在estimate_runs.params_json，摘要与来源分别在summary_json和provenance_json。不要将自建字段写成供应商原生筹码。

固定源库SHA-256：{manifest['database_sha256_before']}。
完整代码SHA-256：{script_hash}。

算法仅是量价情景。换手口径、初始化前真实持仓、历史首次可用性未认证；model_input_approved=false，native_supplier_bins_acquired=false。
"""
    (output / "重建说明.md").write_text(readme, encoding="utf-8")
    (work / "README.md").write_text(readme, encoding="utf-8")
    write_json(work / "validation_summary.json", validation)
    if not validation["all_technical_checks_passed"]:
        raise SystemExit("one or more technical checks failed; see 验证结果.json")
    print(json.dumps({"status": "complete", "output": str(output), "runs": len(results),
                      "dates": len(targets), "price_bin_rows": validation["saved_price_bin_rows"],
                      "checks_passed": len(checks), "source_hash_unchanged": True,
                      "output_sqlite_sha256": output_db_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
