#!/usr/bin/env python3
"""
Historical replay via prosperity3bt.

Replays the tutorial days exactly as recorded in data/round_0/.
Each run gives a single deterministic PnL — use this to validate logic changes.

Usage:
    python round_0/tools/replay.py <model>               # both days (default)
    python round_0/tools/replay.py <model> 0--2          # round 0, day -2 only
    python round_0/tools/replay.py <model> 0--2 0--1     # explicit both days
    python round_0/tools/replay.py <model> --no-out      # skip log file
    python round_0/tools/replay.py <model> --merge-pnl   # cumulative PnL

Day format: <round>--<day>  e.g. 0--2  0--1
"""

import sys
from contextlib import contextmanager
from datetime import datetime
from functools import reduce
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / "models"
DATA_DIR = PROJECT_ROOT / "data" / "round_0"

# prosperity3bt is installed in the venv.
# MODELS_DIR is added so models can resolve `from datamodel import ...`.
sys.path.insert(0, str(MODELS_DIR))


# ── Custom FileReader: maps round0/ → data/round_0/ ────────────────────────

from prosperity3bt.file_reader import FileReader

class Round0Reader(FileReader):
    """Maps prosperity3bt's round0/ path prefix to our data/round_0/ directory."""
    def __init__(self, root: Path):
        self._root = root  # data/  (parent of round_0)

    @contextmanager
    def file(self, path_parts: list[str]):
        mapped = ["round_0" if p == "round0" else p for p in path_parts]
        path = self._root
        for part in mapped:
            path = path / part
        yield path if path.is_file() else None


# ── Helpers (mirrors prosperity3bt.__main__) ────────────────────────────────

def parse_days(reader: Round0Reader, day_args: list[str]) -> list[tuple[int, int]]:
    from prosperity3bt.data import has_day_data
    parsed = []
    for arg in day_args:
        if "--" in arg:
            round_str, day_str = arg.split("--", 1)
            parsed.append((int(round_str), int(f"-{day_str}")))
        elif arg.lstrip("-").isdigit():
            round_num = int(arg)
            for day_num in range(-5, 10):
                if has_day_data(reader, round_num, day_num):
                    parsed.append((round_num, day_num))
    return parsed


def print_day_summary(result) -> None:
    last_ts = result.activity_logs[-1].timestamp
    lines, total = [], 0
    for row in reversed(result.activity_logs):
        if row.timestamp != last_ts:
            break
        lines.append(f"{row.columns[2]}: {row.columns[-1]:,.0f}")
        total += row.columns[-1]
    for line in reversed(lines):
        print(line)
    print(f"Total profit: {total:,.0f}")


def write_log(output_file: Path, result) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        f.write("Sandbox logs:\n")
        for row in result.sandbox_logs:
            f.write(str(row))
        f.write("\n\n\nActivities log:\n")
        f.write("day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;"
                "bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;"
                "ask_price_3;ask_volume_3;mid_price;profit_and_loss\n")
        f.write("\n".join(map(str, result.activity_logs)))
        f.write("\n\n\n\n\nTrade History:\n[\n")
        f.write(",\n".join(map(str, result.trades)))
        f.write("]")


# ── Entry point ─────────────────────────────────────────────────────────────

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

    remaining = args[1:]
    day_args, flags = [], {}
    i = 0
    while i < len(remaining):
        arg = remaining[i]
        if not arg.startswith("-") and ("--" in arg or arg.lstrip("-").isdigit()):
            day_args.append(arg)
        elif arg == "--no-out":
            flags["no_out"] = True
        elif arg == "--merge-pnl":
            flags["merge_pnl"] = True
        i += 1

    if not day_args:
        day_args = ["0--2", "0--1"]

    reader = Round0Reader(DATA_DIR.parent)

    import importlib.util
    spec = importlib.util.spec_from_file_location("trader_module", model_path)
    trader_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trader_module)

    from prosperity3bt.runner import run_backtest
    from prosperity3bt.models import TradeMatchingMode

    parsed_days = parse_days(reader, day_args)
    results = []
    for round_num, day_num in parsed_days:
        print(f"Backtesting {model_name} on round {round_num} day {day_num}")
        result = run_backtest(
            trader_module.Trader(),
            reader,
            round_num,
            day_num,
            print_output=False,
            trade_matching_mode=TradeMatchingMode.all,
            no_names=True,
            show_progress_bar=True,
        )
        print_day_summary(result)
        if len(parsed_days) > 1:
            print()
        results.append(result)

    if len(parsed_days) > 1:
        total = sum(
            sum(r.columns[-1] for r in reversed(res.activity_logs) if r.timestamp == res.activity_logs[-1].timestamp)
            for res in results
        )
        print(f"Total profit: {total:,.0f}")

    if not flags.get("no_out"):
        logs_dir = ROUND_DIR / "results" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        day_tag = "_".join(d.replace("--", "n") for d in day_args)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = logs_dir / f"{model_name}_{day_tag}_{timestamp}.log"

        def merge(a, b, merge_pnl=False):
            from collections import defaultdict
            from prosperity3bt.models import BacktestResult
            offset = a.activity_logs[-1].timestamp + 100
            pnl_off = defaultdict(float)
            if merge_pnl:
                last_ts = a.activity_logs[-1].timestamp
                for row in reversed(a.activity_logs):
                    if row.timestamp != last_ts:
                        break
                    pnl_off[row.columns[2]] = row.columns[-1]
            return BacktestResult(
                a.round_num, a.day_num,
                a.sandbox_logs + [r.with_offset(offset) for r in b.sandbox_logs],
                a.activity_logs + [r.with_offset(offset, pnl_off[r.columns[2]]) for r in b.activity_logs],
                a.trades + [r.with_offset(offset) for r in b.trades],
            )

        merged = reduce(lambda a, b: merge(a, b, flags.get("merge_pnl", False)), results)
        write_log(log_path, merged)
        print(f"\nSaved backtest log to {log_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
