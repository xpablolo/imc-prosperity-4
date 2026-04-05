#!/usr/bin/env python3
"""
Monte Carlo backtest via prosperity4mcbt.

Runs N synthetic sessions using the Rust simulator calibrated from the tutorial
CSV data. Each session generates a different price path, giving a PnL distribution
rather than a single replay number. Use this to test robustness.

Requires: Rust/Cargo installed (rustup.rs). The Rust binary is compiled on first run.

Usage:
    python round_0/tools/montecarlo.py <model>              # 100 sessions (default)
    python round_0/tools/montecarlo.py <model> --quick      # 100 sessions, 10 traces
    python round_0/tools/montecarlo.py <model> --heavy      # 1000 sessions, 100 traces
    python round_0/tools/montecarlo.py <model> --sessions N

Output:
    round_0/results/montecarlo/<model>/<timestamp>/
        session_summary.csv   — per-session PnL
        run_summary.csv       — per-day PnL within each session
        dashboard.json        — full stats bundle
        static_charts/        — SVG path band charts
        plots/                — matplotlib PNG plots (via mc_plots.py)
"""

import sys
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / "models"
DATA_DIR = PROJECT_ROOT / "data" / "round_0"

sys.path.insert(0, str(MODELS_DIR))


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    model_name = args[0]
    model_path = MODELS_DIR / f"{model_name}.py"
    if not model_path.exists():
        available = sorted(p.stem for p in MODELS_DIR.glob("*.py") if p.stem != "datamodel")
        print(f"Model '{model_name}' not found. Available: {', '.join(available)}")
        sys.exit(1)

    # Parse flags
    remaining = args[1:]
    sessions = 100
    sample_sessions = 10
    for i, arg in enumerate(remaining):
        if arg == "--quick":
            sessions, sample_sessions = 100, 10
        elif arg == "--heavy":
            sessions, sample_sessions = 1000, 100
        elif arg == "--sessions" and i + 1 < len(remaining):
            sessions = int(remaining[i + 1])

    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROUND_DIR / "results" / "montecarlo" / model_name / timestamp
    dashboard_path = out_dir / "dashboard.json"

    print(f"Running Monte Carlo: {model_name}")
    print(f"  Sessions:       {sessions}")
    print(f"  Sample traces:  {sample_sessions}")
    print(f"  Output:         {out_dir.relative_to(PROJECT_ROOT)}")
    print()

    from prosperity3bt.monte_carlo import run_monte_carlo_mode

    dashboard = run_monte_carlo_mode(
        algorithm=model_path,
        dashboard_path=dashboard_path,
        data_root=DATA_DIR,    # resolve_actual_dir falls back to DATA_DIR directly
        sessions=sessions,
        fv_mode="simulate",
        trade_mode="simulate",
        tomato_support="quarter",
        seed=20260401,
        python_bin=sys.executable,
        sample_sessions=sample_sessions,
    )

    total = dashboard["overall"]["totalPnl"]
    print(f"\nResults ({sessions} sessions):")
    print(f"  Mean PnL:   {total['mean']:>10,.0f}")
    print(f"  Median:     {total['p50']:>10,.0f}")
    print(f"  Std:        {total['std']:>10,.0f}")
    print(f"  P05–P95:    {total['p05']:>10,.0f}  to  {total['p95']:,.0f}")
    print(f"  Win rate:   {total['positiveRate']*100:>9.1f}%")

    em = dashboard["overall"]["emeraldPnl"]
    to = dashboard["overall"]["tomatoPnl"]
    print(f"\n  EMERALDS mean: {em['mean']:,.0f}   TOMATOES mean: {to['mean']:,.0f}")
    print(f"\nSaved to: {out_dir.relative_to(PROJECT_ROOT)}")

    # Generate matplotlib plots
    print("\nGenerating plots...")
    import subprocess
    subprocess.run(
        [sys.executable, str(TOOLS_DIR / "mc_plots.py"), str(out_dir)],
        check=True,
    )


if __name__ == "__main__":
    main()
