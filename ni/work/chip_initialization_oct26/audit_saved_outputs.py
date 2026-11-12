#!/usr/bin/env python3
"""Independent stdlib-only saved-output audit; never imports the estimator."""
import bisect
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
OUT = PROJECT / "outputs/初始化与验证推进_20261026/筹码初始化"
SOURCE = PROJECT / "outputs/统一数据底座_20261022/统一数据底座.sqlite"
SCRIPT = PROJECT / "work/chip_initialization_oct26/build_initialization_v2.py"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonwrite(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def main():
    checks = []
    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), **evidence})
    conn = sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    rows = conn.execute("SELECT trade_date,turnover_pct FROM stock_raw_reference WHERE trade_date >= '2022-06-01' AND trade_date <= '2026-10-21' ORDER BY trade_date").fetchall()
    conn.close()
    expected = {}
    with localcontext() as ctx:
        ctx.prec = 60
        for mult in (Decimal("0.5"), Decimal("1"), Decimal("1.5")):
            u = Decimal(1)
            name = f"turnover_x{mult:g}"
            for date, turnover in rows:
                amount = min(Decimal(1), max(Decimal(0), mult * Decimal(str(turnover)) / 100))
                u *= 1 - amount
                expected[(date, name)] = float(u)
    saved = json.loads((OUT / "逐日初始化诊断.json").read_text())["diagnostics"]
    errors = [abs(d["unknown_initial_mass"] - expected[(d["asof_date"], d["variant"])]) for d in saved]
    check("independent_60_digit_decimal_unknown_product_all_days", len(saved) == 3192 and max(errors) < 2e-15,
          checked_states=len(saved), max_float_absolute_error=max(errors))
    check("no_unknown_mass_hard_zero", all(d["unknown_initial_mass"] > 0 for d in saved),
          minimum_unknown_mass=min(d["unknown_initial_mass"] for d in saved))
    db = sqlite3.connect((OUT / "初始化改进v2.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    check("sqlite_integrity", db.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    results = json.loads((OUT / "固定日期结果.json").read_text())["results"]
    max_mass_error = max_conditional_error = max_cdf_error = 0
    bounds_ok = gates_ok = True
    for result in results:
        s = result["summary"]
        bins = db.execute("SELECT price_cny,observed_contribution_mass,conditional_known_mass,total_cdf_lower,total_cdf_upper FROM known_observed_bins WHERE estimate_id=? ORDER BY bin_index", (result["estimate_id"],)).fetchall()
        known = sum(r[1] for r in bins)
        unknown = s["unknown_initial_mass"]
        max_mass_error = max(max_mass_error, abs(known + unknown - 1))
        max_conditional_error = max(max_conditional_error, abs(sum(r[2] for r in bins) - 1))
        cumulative, prices = [], []
        total = 0
        for price, mass, conditional, lower, upper in bins:
            total += mass
            cumulative.append(total)
            prices.append(price)
            max_cdf_error = max(max_cdf_error, abs(lower - total), abs(upper - min(1, total + unknown)),
                                abs(conditional * known - mass))
        for qbound in s["total_quantile_bounds"]:
            q, lower, upper = qbound["q"], qbound["lower"], qbound["upper"]
            if q <= unknown:
                bounds_ok &= lower == {"kind": "negative_infinity", "value_cny": None}
            else:
                price = prices[min(len(prices) - 1, bisect.bisect_left(cumulative, q - unknown))]
                bounds_ok &= lower["kind"] == "finite" and abs(lower["value_cny"] - price) < 1e-12
            if q > known:
                bounds_ok &= upper == {"kind": "positive_infinity", "value_cny": None}
            else:
                price = prices[min(len(prices) - 1, bisect.bisect_left(cumulative, q))]
                bounds_ok &= upper["kind"] == "finite" and abs(upper["value_cny"] - price) < 1e-12
        profit = sum(mass for price, mass, *_ in bins if price <= s["close_raw_cny"] + 1e-12)
        bounds_ok &= abs(profit - s["profit_mass_lower"]) < 1e-12
        bounds_ok &= abs(profit + unknown - s["profit_mass_upper"]) < 1e-12
        bounds_ok &= s["total_distribution_mean_cny"] is None
        gates_ok &= all(s[key] is False for key in ("model_input_approved", "native_supplier_bins_acquired",
                                                    "warmup_sufficiency_certified", "prediction_reliability_certified",
                                                    "unknown_initial_price_support_assumed"))
    check("saved_subprobability_not_total_distribution", max_mass_error < 1e-12,
          max_mass_sum_error=max_mass_error)
    check("conditional_normalization_separately_labelled", max_conditional_error < 1e-12,
          max_conditional_sum_error=max_conditional_error)
    check("stored_cdf_envelope_matches_observed_plus_unknown", max_cdf_error < 1e-12,
          max_cdf_or_conditional_error=max_cdf_error)
    check("independent_saved_bin_quantile_profit_and_mean_checks", bounds_ok,
          saved_runs=len(results), saved_quantiles=sum(len(r["summary"]["total_quantile_bounds"]) for r in results))
    check("all_gates_and_support_assumption_remain_false", gates_ok)
    preserved = json.loads((OUT / "旧原件哈希前后.json").read_text())
    changed = [path for path, sha in preserved["before"].items() if digest(PROJECT / path) != sha]
    check("all_old_artifacts_still_match_original_hashes", not changed,
          checked_files=len(preserved["before"]), changed_files=changed)
    db.close()
    # Rebuild from the immutable original source and compare all preexisting
    # generated files. Audit files are written only after this comparison.
    before = {p.name: digest(p) for p in OUT.iterdir() if p.is_file()}
    run = subprocess.run([sys.executable, str(SCRIPT), "--project-root", str(PROJECT)],
                         check=True, text=True, capture_output=True)
    after = {p.name: digest(p) for p in OUT.iterdir() if p.is_file()}
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    check("full_command_rerun_all_artifacts_byte_identical", before == after,
          compared_files=len(before), changed_files=changed, command_stdout=run.stdout.strip(),
          files_before=before, files_after=after)
    result = {"audit_implementation_sha256": digest(Path(__file__)), "estimator_imported": False,
              "stdlib_only": True, "network_used": False, "future_returns_read": False,
              "all_checks_passed": all(c["passed"] for c in checks), "checks": checks,
              "model_input_approved": False, "native_supplier_bins_acquired": False}
    jsonwrite(OUT / "独立本地核验与完整重跑.json", result)
    jsonwrite(PROJECT / "work/chip_initialization_oct26/audit_summary.json", result)
    print(json.dumps({"all_checks_passed": result["all_checks_passed"], "checks": len(checks),
                      "full_rerun_files": len(before)}, ensure_ascii=False))
    if not result["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
