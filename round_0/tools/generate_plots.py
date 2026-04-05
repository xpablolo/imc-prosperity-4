from pathlib import Path

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data_tutorial"
OUTPUT_DIR = DATA_DIR / "plots"


def load_day_prices(day: int) -> pd.DataFrame:
    csv_path = DATA_DIR / f"prices_round_0_day_{day}.csv"
    df = pd.read_csv(csv_path, sep=";")
    df = df[df["product"] == "TOMATOES"][["day", "timestamp", "mid_price"]].copy()
    df["day"] = df["day"].astype(int)
    df["timestamp"] = df["timestamp"].astype(float)
    df["mid_price"] = df["mid_price"].astype(float)
    return df


def main() -> None:
    sns.set_theme(style="whitegrid")

    days = [-2, -1]  # chronological: day -2 first, then day -1
    dfs = [load_day_prices(d) for d in days]
    all_df = pd.concat(dfs, ignore_index=True)

    # Offset timestamps so the x-axis is chronological across days.
    step = all_df["timestamp"].max() + 1
    min_day = min(days)
    all_df["global_ts"] = (all_df["day"] - min_day) * step + all_df["timestamp"]

    all_df = all_df.sort_values("global_ts")

    fig, ax = plt.subplots(figsize=(12, 4.8))
    sns.lineplot(
        data=all_df,
        x="global_ts",
        y="mid_price",
        hue="day",
        palette=["#d62728", "#1f77b4"],
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


if __name__ == "__main__":
    main()