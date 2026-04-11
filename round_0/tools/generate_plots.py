from pathlib import Path

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "round_0"
OUTPUT_DIR = DATA_DIR / "plots"
DAY_COLORS = {-2: "#d62728", -1: "#1f77b4"}
PRICE_SERIES = {
    "mid_price": {"label": "mid_price", "linestyle": "-"},
    "bid_price_1": {"label": "best bid", "linestyle": "--"},
    "ask_price_1": {"label": "best ask", "linestyle": ":"},
}


def load_day_prices(day: int) -> pd.DataFrame:
    csv_path = DATA_DIR / f"prices_round_0_day_{day}.csv"
    df = pd.read_csv(csv_path, sep=";")
    df = df[df["product"] == "TOMATOES"][["day", "timestamp", "bid_price_1", "ask_price_1", "mid_price"]].copy()
    df["day"] = df["day"].astype(int)
    df["timestamp"] = df["timestamp"].astype(float)
    df["bid_price_1"] = df["bid_price_1"].astype(float)
    df["ask_price_1"] = df["ask_price_1"].astype(float)
    df["mid_price"] = df["mid_price"].astype(float)
    return df


def add_global_ts(df: pd.DataFrame, days: list[int]) -> pd.DataFrame:
    df = df.copy()
    step = df["timestamp"].max() + 1
    min_day = min(days)
    df["global_ts"] = (df["day"] - min_day) * step + df["timestamp"]
    return df.sort_values("global_ts")


def plot_mid_price(all_df: pd.DataFrame, days: list[int]) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.8))
    sns.lineplot(
        data=all_df,
        x="global_ts",
        y="mid_price",
        hue="day",
        hue_order=days,
        palette=[DAY_COLORS[d] for d in days],
        linewidth=1.8,
        ax=ax,
    )

    ax.set_title("TOMATOES mid_price (day -2 then day -1)")
    ax.set_xlabel("chronological timestamp (offset by day)")
    ax.set_ylabel("mid_price")
    ax.legend(title="day")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "TOMATOES_mid_price_day_-2_then_-1.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_mid_bid_ask(all_df: pd.DataFrame, days: list[int]) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.8))

    for day in days:
        day_df = all_df[all_df["day"] == day]
        for series_name, series_meta in PRICE_SERIES.items():
            ax.plot(
                day_df["global_ts"],
                day_df[series_name],
                color=DAY_COLORS[day],
                linestyle=series_meta["linestyle"],
                linewidth=1.6,
                alpha=0.9,
            )

    ax.set_title("TOMATOES mid/bid/ask (day -2 then day -1)")
    ax.set_xlabel("chronological timestamp (offset by day)")
    ax.set_ylabel("price")

    day_handles = [
        Line2D([0], [0], color=DAY_COLORS[day], lw=1.8, label=str(day))
        for day in days
    ]
    series_handles = [
        Line2D([0], [0], color="black", lw=1.8, linestyle=meta["linestyle"], label=meta["label"])
        for meta in PRICE_SERIES.values()
    ]
    day_legend = ax.legend(handles=day_handles, title="day", loc="upper right")
    ax.add_artist(day_legend)
    ax.legend(handles=series_handles, title="series", loc="lower right")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "TOMATOES_mid_price_with_bid_ask_day_-2_then_-1.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    print(f"Saved: {out_path}")


def main() -> None:
    sns.set_theme(style="whitegrid")

    days = [-2, -1]  # chronological: day -2 first, then day -1
    dfs = [load_day_prices(d) for d in days]
    all_df = add_global_ts(pd.concat(dfs, ignore_index=True), days)

    plot_mid_price(all_df, days)
    plot_mid_bid_ask(all_df, days)


if __name__ == "__main__":
    main()
