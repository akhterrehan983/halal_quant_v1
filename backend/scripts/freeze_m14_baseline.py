"""Freeze / compare a deterministic M14 backtest baseline (demo data, in-memory mode only).

Why a script: demo prices are generated relative to *today*, so raw demo runs drift from day to day.
This script re-anchors the same seeded demo series to a fixed calendar date, forces in-memory mode
(never touches PostgreSQL), runs a small fixed set of scenarios, and writes a JSON baseline that later
phases can be diffed against.

This is a software-regression artifact. It is NOT evidence of strategy performance (data is synthetic).

Usage (from ``backend/``):

    # freeze (run BEFORE any Phase 1 code change)
    .venv/bin/python -m scripts.freeze_m14_baseline --out tests/baselines/m14_pre_phase1.json

    # after the change, write a second file and diff
    .venv/bin/python -m scripts.freeze_m14_baseline --out tests/baselines/m14_post_phase1.json
    .venv/bin/python -m scripts.freeze_m14_baseline --compare tests/baselines/m14_pre_phase1.json tests/baselines/m14_post_phase1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

# Must be set before any ``app`` import: forces in-memory demo mode regardless of .env.
os.environ["DATABASE_URL"] = ""

ANCHOR = date(2026, 11, 20)  # fixed last bar for every demo series (a Friday)
WINDOW = (date(2026, 8, 3), date(2026, 10, 30))

SCENARIOS: dict[str, dict[str, str]] = {
    "A_research_only_zero_cost": {"shariah_mode": "RESEARCH_ONLY", "cost_scenario": "ZERO"},
    "B_research_only_realistic_cost": {"shariah_mode": "RESEARCH_ONLY", "cost_scenario": "REALISTIC"},
    "C_strict_zero_cost": {"shariah_mode": "STRICT", "cost_scenario": "ZERO"},
}

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_OUT = BACKEND_DIR / "tests" / "baselines" / "m14_pre_phase1.json"

METRIC_KEYS_FOR_DIFF = (
    "total_return",
    "cagr",
    "max_drawdown",
    "volatility",
    "sharpe",
    "win_rate",
    "profit_factor",
    "total_trades",
    "transaction_costs",
    "shariah_rejections",
    "risk_rejections",
    "ownership_blocked_exits",
    "unfilled_orders",
)


def _install_fixed_histories() -> list[str]:
    import pandas as pd

    from app.data import sample_data

    symbols = list(sample_data.SYMBOLS)
    fixed = {}
    for sym in symbols:
        df = sample_data.make_history(sym).copy()
        df["date"] = pd.bdate_range(end=pd.Timestamp(ANCHOR), periods=len(df))
        fixed[sym] = df
    sample_data.HISTORIES = fixed
    return symbols


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - metadata only
        return None


def _meta(symbols: list[str]) -> dict:
    import numpy
    import pandas

    app_dirty = _git("status", "--porcelain", "--", "backend/app")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "anchor_last_bar": ANCHOR.isoformat(),
        "window": [WINDOW[0].isoformat(), WINDOW[1].isoformat()],
        "demo_symbols": symbols,
        "git_commit": _git("rev-parse", "HEAD"),
        "backend_app_has_uncommitted_changes": (None if app_dirty is None else bool(app_dirty)),
        "python": sys.version.split()[0],
        "pandas": pandas.__version__,
        "numpy": numpy.__version__,
        "platform": platform.platform(),
        "note": "Synthetic demo data. Software-regression baseline only; not performance evidence.",
    }


def _equity_digest(curve: list[dict]) -> dict:
    h = hashlib.sha256()
    for p in curve:
        h.update(f"{p['date']}|{p['equity']}|{p['cash']}|{p['invested']}\n".encode())
    return {
        "points": len(curve),
        "first": curve[0] if curve else None,
        "last": curve[-1] if curve else None,
        "sha256": h.hexdigest(),
    }


def _run_scenario(name: str, spec: dict[str, str], explicit_symbols: list[str] | None = None) -> dict:
    from app.backtesting.schemas import BacktestConfig, CostScenario, ShariahBacktestMode
    from app.backtesting.simulator import run_backtest

    cfg = BacktestConfig(
        name=f"m14_baseline_{name}",
        start_date=WINDOW[0],
        end_date=WINDOW[1],
        horizon="swing",
        shariah_mode=ShariahBacktestMode(spec["shariah_mode"]),
        cost_scenario=CostScenario(spec["cost_scenario"]),
        max_positions=3,
        slippage_bps=10,
        symbols=explicit_symbols,
    )
    t0 = time.time()
    run = run_backtest(cfg)
    elapsed = round(time.time() - t0, 1)
    body = run.model_dump(mode="json")
    curve = body.pop("equity_curve")
    return {"elapsed_seconds": elapsed, "run": body, "equity": _equity_digest(curve)}


def _scenarios_hash(scenarios: dict) -> str:
    stripped = json.loads(json.dumps(scenarios))
    for s in stripped.values():
        s.pop("elapsed_seconds", None)
        s["run"].pop("created_at", None)
        s["run"].pop("completed_at", None)
    blob = json.dumps(stripped, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def freeze(out_path: Path, explicit_symbols: list[str] | None = None) -> int:
    from app.core.config import settings

    if settings.database_enabled:
        print("ABORT: database is enabled; this script must run in in-memory demo mode.")
        return 2
    warnings.filterwarnings("ignore")
    symbols = _install_fixed_histories()
    scenarios: dict[str, dict] = {}
    for name, spec in SCENARIOS.items():
        print(f"[run] {name} ...", flush=True)
        scenarios[name] = _run_scenario(name, spec, explicit_symbols)
        m = scenarios[name]["run"].get("metrics") or {}
        print(
            f"      trades={m.get('total_trades')} total_return={m.get('total_return')} "
            f"shariah_rejections={m.get('shariah_rejections')} elapsed={scenarios[name]['elapsed_seconds']}s",
            flush=True,
        )
    meta = _meta(symbols)
    if explicit_symbols:
        meta["explicit_symbols"] = explicit_symbols  # ablation run: not a full-universe baseline
    payload = {
        "meta": meta,
        "scenarios": scenarios,
        "scenarios_sha256": _scenarios_hash(scenarios),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    print(f"[ok] wrote {out_path}")
    print(f"[ok] scenarios_sha256 = {payload['scenarios_sha256']}")
    return 0


def _trade_key(t: dict) -> tuple:
    return (
        t.get("symbol"),
        t.get("entry_date"),
        t.get("exit_date"),
        t.get("quantity"),
        str(t.get("entry_price")),
        str(t.get("exit_price")),
    )


def compare(a_path: Path, b_path: Path) -> int:
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())
    print(f"A: {a_path}  (commit {a['meta'].get('git_commit')})")
    print(f"B: {b_path}  (commit {b['meta'].get('git_commit')})")
    print(f"scenarios_sha256 equal: {a.get('scenarios_sha256') == b.get('scenarios_sha256')}")
    for name, sa in a["scenarios"].items():
        sb = b["scenarios"].get(name)
        print(f"\n=== {name} ===")
        if sb is None:
            print("  missing in B")
            continue
        ma, mb = (sa["run"].get("metrics") or {}), (sb["run"].get("metrics") or {})
        any_diff = False
        for k in METRIC_KEYS_FOR_DIFF:
            if ma.get(k) != mb.get(k):
                any_diff = True
                print(f"  metric {k}: {ma.get(k)} -> {mb.get(k)}")
        ta = {_trade_key(t) for t in sa["run"].get("trades", [])}
        tb = {_trade_key(t) for t in sb["run"].get("trades", [])}
        only_a, only_b = sorted(ta - tb), sorted(tb - ta)
        if only_a or only_b:
            any_diff = True
            print(f"  trades only in A: {len(only_a)}  only in B: {len(only_b)}")
            for t in only_a[:5]:
                print(f"    A-only {t}")
            for t in only_b[:5]:
                print(f"    B-only {t}")
        ea, eb = sa["equity"], sb["equity"]
        if ea["sha256"] != eb["sha256"]:
            any_diff = True
            print(f"  equity curve differs (points {ea['points']} -> {eb['points']})")
        print("  (no differences)" if not any_diff else "  -> differences above need an explanation (finding ID)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="baseline JSON path to write")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"), help="diff two baseline JSON files")
    ap.add_argument(
        "--symbols",
        default=None,
        help="comma-separated explicit symbols (ablation only, e.g. TCS,INFY,RELIANCE,HDFCBANK); default is the full universe",
    )
    args = ap.parse_args()
    if args.compare:
        return compare(args.compare[0], args.compare[1])
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    return freeze(args.out, symbols)


if __name__ == "__main__":
    raise SystemExit(main())
