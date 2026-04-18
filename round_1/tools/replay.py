#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import argparse

TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / "models"
DATA_DIR = PROJECT_ROOT / "data" / "round_1"
RESULTS_DIR = ROUND_DIR / "results"

sys.path.insert(0, str(MODELS_DIR))

from prosperity3bt.file_reader import FileReader  # type: ignore


ROUND1_LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
}


class Round1Reader(FileReader):
    def __init__(self, root: Path):
        self._root = root

    @contextmanager
    def file(self, path_parts: list[str]):
        mapped = ["round_1" if part == "round1" else part for part in path_parts]
        path = self._root
        for part in mapped:
            path = path / part
        yield path if path.is_file() else None


def parse_days(day_args: List[str]) -> List[Tuple[int, int]]:
    parsed: List[Tuple[int, int]] = []
    for arg in day_args:
        if "--" in arg:
            round_str, day_str = arg.split("--", 1)
            parsed.append((int(round_str), int(f"-{day_str}")))
    return parsed


def write_log(output_file: Path, result) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write("Sandbox logs:\n")
        for row in result.sandbox_logs:
            handle.write(str(row))
        handle.write("\n\n\nActivities log:\n")
        handle.write(
            "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;"
            "bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;"
            "ask_price_3;ask_volume_3;mid_price;profit_and_loss\n"
        )
        handle.write("\n".join(map(str, result.activity_logs)))
        handle.write("\n\n\nTrade History:\n[\n")
        handle.write(",\n".join(map(str, result.trades)))
        handle.write("]")


def summarize_result(result, product: str) -> Dict[str, float | int]:
    if not result.activity_logs:
        return {"day": result.day_num, "product": product, "final_pnl": 0.0}
    last_ts = result.activity_logs[-1].timestamp
    final_rows = [row for row in result.activity_logs if row.timestamp == last_ts and row.columns[2] == product]
    final_pnl = float(final_rows[-1].columns[-1]) if final_rows else 0.0
    return {"day": int(result.day_num), "product": product, "final_pnl": final_pnl}


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay round_1 single-product models with prosperity3bt.")
    parser.add_argument("model", help="Model filename under round_1/models.")
    parser.add_argument("days", nargs="*", default=["1--2", "1--1", "1--0"], help="Replay day specifiers like 1--2 1--1 1--0")
    parser.add_argument("--product", default="ASH_COATED_OSMIUM", help="Product to summarize from activity logs.")
    parser.add_argument("--summary-name", default="replay_summary.csv", help="Output CSV filename inside the model results directory.")
    cli_args = parser.parse_args()

    model_name = cli_args.model
    model_path = MODELS_DIR / f"{model_name}.py"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    day_args = cli_args.days
    parsed_days = parse_days(day_args)

    import importlib.util
    import prosperity3bt.data as p3data  # type: ignore
    from prosperity3bt.models import TradeMatchingMode  # type: ignore
    from prosperity3bt.runner import run_backtest  # type: ignore

    p3data.LIMITS.update(ROUND1_LIMITS)

    spec = importlib.util.spec_from_file_location("round1_trader_module", model_path)
    trader_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(trader_module)

    reader = Round1Reader(DATA_DIR.parent)
    per_day_summary: List[Dict[str, float | int]] = []
    all_results = []
    for round_num, day_num in parsed_days:
        print(f"Replay {model_name} on round {round_num} day {day_num}")
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
        all_results.append(result)
        day_summary = summarize_result(result, cli_args.product)
        per_day_summary.append(day_summary)
        print(f"  final {cli_args.product} PnL: {day_summary['final_pnl']:,.0f}")

    total_pnl = sum(float(row["final_pnl"]) for row in per_day_summary)
    print(f"\nTotal replay PnL ({cli_args.product}): {total_pnl:,.0f}")

    output_dir = RESULTS_DIR / model_name
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / cli_args.summary_name
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["day", "product", "final_pnl"])
        writer.writeheader()
        writer.writerows(per_day_summary)
        writer.writerow({"day": "ALL", "product": cli_args.product, "final_pnl": total_pnl})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for result in all_results:
        log_path = RESULTS_DIR / "logs" / f"{model_name}_replay_day_{result.day_num}_{timestamp}.log"
        write_log(log_path, result)
        print(f"Saved log: {log_path.relative_to(PROJECT_ROOT)}")

    print(f"Saved replay summary: {summary_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
