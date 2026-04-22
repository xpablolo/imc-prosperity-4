from __future__ import annotations

import json
from pathlib import Path
from io import StringIO

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter


TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "round_2"
OFFICIAL_LOG_PATH = ROUND_DIR / "official_result.log"
OUTPUT_DIR = ROUND_DIR / "plots"
DAY_ORDER = [-1, 0, 1]
DAY_COLORS = {-1: "#7C3AED", 0: "#2563EB", 1: "#10B981"}
OFFICIAL_TEST_COLOR = "#F59E0B"
DIAGNOSTIC_PRODUCTS = ("ASH_COATED_OSMIUM",)
PRODUCT_COLORS = {
    "ASH_COATED_OSMIUM": "#2563EB",
    "INTARIAN_PEPPER_ROOT": "#F97316",
}
MID_SMOOTH_WINDOW = 50
MID_Z_WINDOW = 100
ROLLING_EFFICIENCY_WINDOW = 200
FUTURE_HORIZON = 10
PRICE_COLUMNS = ["bid_price_1", "ask_price_1", "mid_price"]


def pretty_product(product: str) -> str:
    return product.replace("_", " ").title()


def configure_style() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update(
        {
            "figure.facecolor": "#FBFBFD",
            "axes.facecolor": "#FBFBFD",
            "axes.edgecolor": "#D6D9E0",
            "axes.labelcolor": "#1F2937",
            "axes.titleweight": "bold",
            "axes.titlecolor": "#111827",
            "grid.color": "#E5E7EB",
            "grid.alpha": 0.75,
            "grid.linewidth": 0.9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.facecolor": "#FBFBFD",
            "savefig.bbox": "tight",
            "legend.frameon": True,
            "legend.facecolor": "white",
            "legend.edgecolor": "#E5E7EB",
        }
    )


def safe_efficiency_ratio(series: pd.Series | np.ndarray | list[float]) -> float:
    values = pd.Series(series).dropna().astype(float)
    if len(values) < 2:
        return np.nan
    path_length = values.diff().abs().sum()
    if path_length == 0:
        return np.nan
    return abs(values.iloc[-1] - values.iloc[0]) / path_length


def rolling_efficiency_transform(series: pd.Series, window: int) -> pd.Series:
    min_periods = max(window // 4, 20)
    return series.rolling(window, min_periods=min_periods).apply(safe_efficiency_ratio, raw=False)


def variance_ratio(returns: pd.Series, horizon: int) -> float:
    values = returns.dropna().to_numpy(dtype=float)
    if len(values) <= horizon or horizon < 2:
        return np.nan
    mean_return = values.mean()
    one_step_var = np.sum((values - mean_return) ** 2) / (len(values) - 1)
    if one_step_var <= 0:
        return np.nan
    aggregated = np.array([values[index : index + horizon].sum() for index in range(len(values) - horizon + 1)])
    aggregated_var = np.sum((aggregated - horizon * mean_return) ** 2) / (len(aggregated) - 1)
    return aggregated_var / (horizon * one_step_var)


def fit_linear_trend(frame: pd.DataFrame, time_col: str, value_col: str = "mid_price") -> tuple[pd.DataFrame, float, float, float]:
    valid = frame[[time_col, value_col]].dropna().copy()
    if len(valid) < 2:
        valid["trend"] = np.nan
        valid["residual"] = np.nan
        return valid, np.nan, np.nan, np.nan

    x_values = valid[time_col].to_numpy(dtype=float)
    y_values = valid[value_col].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x_values, y_values, 1)
    trend = slope * x_values + intercept
    residual = y_values - trend
    ss_res = np.sum((y_values - trend) ** 2)
    ss_tot = np.sum((y_values - y_values.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    valid["trend"] = trend
    valid["residual"] = residual
    return valid, slope, intercept, r_squared


def half_life(series: pd.Series | np.ndarray) -> float:
    values = pd.Series(series).dropna().astype(float)
    if len(values) < 20:
        return np.nan
    lagged = values.shift(1)
    delta = values - lagged
    regression_frame = pd.concat([lagged, delta], axis=1).dropna()
    if len(regression_frame) < 10:
        return np.nan
    x_values = regression_frame.iloc[:, 0].to_numpy(dtype=float)
    y_values = regression_frame.iloc[:, 1].to_numpy(dtype=float)
    if np.isclose(np.var(x_values), 0.0):
        return np.nan
    beta = np.polyfit(x_values, y_values, 1)[0]
    if beta >= 0:
        return np.inf
    return -np.log(2) / beta


def residual_cross_rate(residual: pd.Series | np.ndarray) -> float:
    values = pd.Series(residual).dropna().astype(float)
    if values.empty:
        return np.nan
    signs = np.sign(values).replace(0, np.nan).ffill()
    flips = (signs * signs.shift(1) < 0).sum()
    return flips / max(len(signs), 1)


def compute_residual_metrics(frame: pd.DataFrame, time_col: str) -> dict[str, float]:
    trend_frame, slope, _, trend_r2 = fit_linear_trend(frame, time_col)
    residual = trend_frame["residual"]
    residual_std = residual.std()
    residual_half_life = half_life(residual)
    cross_rate = residual_cross_rate(residual)
    drift_per_10k_ts = slope * 10_000 if pd.notna(slope) else np.nan
    drift_noise_ratio = abs(drift_per_10k_ts) / residual_std if pd.notna(residual_std) and residual_std > 0 else np.nan
    return {
        "trend_per_10k_ts": drift_per_10k_ts,
        "trend_r2": trend_r2,
        "residual_std": residual_std,
        "residual_half_life": residual_half_life,
        "residual_cross_rate": cross_rate,
        "drift_noise_ratio": drift_noise_ratio,
    }


def classify_strategy(row: pd.Series) -> tuple[str, str]:
    trend_r2 = row.get("trend_r2", np.nan)
    smooth_efficiency = row.get("smooth_efficiency_50", np.nan)
    drift_noise_ratio = row.get("drift_noise_ratio", np.nan)
    residual_half_life = row.get("residual_half_life", np.nan)

    if pd.notna(trend_r2) and pd.notna(smooth_efficiency) and pd.notna(drift_noise_ratio):
        if trend_r2 >= 0.90 and smooth_efficiency >= 0.35 and drift_noise_ratio >= 1.00:
            if pd.notna(residual_half_life) and residual_half_life <= 1.50:
                return (
                    "Trend + pullback mean reversion",
                    "Usá una fair value móvil, sesgo de inventario a favor de la tendencia y entradas en pullbacks en vez de perseguir cada tick.",
                )
            return (
                "Directional trend following",
                "El edge está en seguir la deriva dominante; no conviene pelear la tendencia salvo en extremos muy claros.",
            )
        if trend_r2 <= 0.20 and smooth_efficiency <= 0.10 and drift_noise_ratio <= 0.10:
            return (
                "Stationary mean reversion / market making",
                "Conviene anclar a un fair value casi estático, capturar spread y desvanecer excursiones en vez de perseguir momentum.",
            )
        if pd.notna(residual_half_life) and residual_half_life <= 1.50 and drift_noise_ratio >= 0.30:
            return (
                "Moving-anchor mean reversion",
                "Hay drift, pero el mejor playbook es operar contra desvíos alrededor de una media que se mueve con la tendencia.",
            )
    return (
        "Mixed / regime-switching",
        "No hay una sola estructura dominante: conviene usar filtros de régimen antes de decidir entre follow o reversion.",
    )


def enrich_price_frame(prices: pd.DataFrame, day_offsets: dict[int, int]) -> pd.DataFrame:
    prices = prices.copy()
    empty_book = prices["bid_price_1"].isna() & prices["ask_price_1"].isna()
    prices.loc[empty_book, "mid_price"] = np.nan
    prices["global_ts"] = prices["timestamp"] + prices["day"].map(day_offsets)
    prices = prices.sort_values(["product", "day", "timestamp"]).reset_index(drop=True)

    prices["spread"] = prices["ask_price_1"] - prices["bid_price_1"]
    bid_volume = prices["bid_volume_1"].fillna(0)
    ask_volume = prices["ask_volume_1"].fillna(0)
    total_volume = bid_volume + ask_volume
    prices["top_level_imbalance"] = np.where(
        total_volume > 0,
        (bid_volume - ask_volume) / total_volume,
        np.nan,
    )

    prices["rolling_mid"] = prices.groupby(["product", "day"])["mid_price"].transform(
        lambda series: series.rolling(MID_SMOOTH_WINDOW, min_periods=1).mean()
    )
    prices["rolling_mean_100"] = prices.groupby(["product", "day"])["mid_price"].transform(
        lambda series: series.rolling(MID_Z_WINDOW, min_periods=max(MID_Z_WINDOW // 5, 20)).mean()
    )
    prices["rolling_std_100"] = prices.groupby(["product", "day"])["mid_price"].transform(
        lambda series: series.rolling(MID_Z_WINDOW, min_periods=max(MID_Z_WINDOW // 5, 20)).std()
    )
    prices["rolling_zscore_100"] = (prices["mid_price"] - prices["rolling_mean_100"]) / prices["rolling_std_100"]
    prices["rolling_efficiency_200"] = prices.groupby(["product", "day"])["mid_price"].transform(
        lambda series: rolling_efficiency_transform(series, ROLLING_EFFICIENCY_WINDOW)
    )
    prices["mid_change_1"] = prices.groupby(["product", "day"])["mid_price"].diff()
    prices[f"future_mid_change_{FUTURE_HORIZON}"] = prices.groupby(["product", "day"])["mid_price"].shift(
        -FUTURE_HORIZON
    ) - prices["mid_price"]

    first_mid = prices.groupby(["product", "day"])["mid_price"].transform("first")
    prices["intraday_move"] = prices["mid_price"] - first_mid
    prices["normalized_intraday"] = 100 * prices["mid_price"] / first_mid
    return prices


def load_prices() -> tuple[pd.DataFrame, int]:
    frames: list[pd.DataFrame] = []
    for day in DAY_ORDER:
        csv_path = DATA_DIR / f"prices_round_2_day_{day}.csv"
        df = pd.read_csv(csv_path, sep=";")
        for column in df.columns:
            if column != "product":
                df[column] = pd.to_numeric(df[column], errors="coerce")
        df["day"] = df["day"].astype(int)
        frames.append(df)

    prices = pd.concat(frames, ignore_index=True)
    step = int(prices["timestamp"].max()) + 100
    day_offsets = {day: index * step for index, day in enumerate(DAY_ORDER)}
    prices = enrich_price_frame(prices, day_offsets)
    return prices, step


def load_official_test_prices(step: int) -> tuple[pd.DataFrame, list[int]]:
    raw_log = json.loads(OFFICIAL_LOG_PATH.read_text(encoding="utf-8"))
    prices = pd.read_csv(StringIO(raw_log["activitiesLog"]), sep=";")
    for column in prices.columns:
        if column != "product":
            prices[column] = pd.to_numeric(prices[column], errors="coerce")
    prices["day"] = prices["day"].astype(int)

    official_days = sorted(prices["day"].dropna().unique().tolist())
    day_offsets = {day: (len(DAY_ORDER) + index) * step for index, day in enumerate(official_days)}
    prices = enrich_price_frame(prices, day_offsets)
    return prices, official_days


def load_trades(step: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    day_offsets = {day: index * step for index, day in enumerate(DAY_ORDER)}
    for day in DAY_ORDER:
        csv_path = DATA_DIR / f"trades_round_2_day_{day}.csv"
        df = pd.read_csv(csv_path, sep=";")
        for column in df.columns:
            if column not in {"buyer", "seller", "symbol", "currency"}:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        df["day"] = day
        df["global_ts"] = df["timestamp"] + day_offsets[day]
        frames.append(df)
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "day", "timestamp"])


def product_day_slice(df: pd.DataFrame, product: str, day: int) -> pd.DataFrame:
    product_column = "product" if "product" in df.columns else "symbol"
    return df[(df[product_column] == product) & (df["day"] == day)]


def session_move_and_range(mid_series: pd.Series) -> tuple[float, float]:
    valid_mid = mid_series.dropna()
    if valid_mid.empty:
        return np.nan, np.nan
    net_move = valid_mid.iloc[-1] - valid_mid.iloc[0] if len(valid_mid) >= 2 else np.nan
    session_range = valid_mid.max() - valid_mid.min()
    return net_move, session_range


def add_session_background(
    ax: plt.Axes,
    sessions: list[int],
    step: int,
    colors: dict[int, str],
    labels: dict[int, str] | None = None,
    alpha_by_session: dict[int, float] | None = None,
) -> None:
    labels = labels or {}
    alpha_by_session = alpha_by_session or {}
    for index, day in enumerate(sessions):
        start = index * step
        end = start + step
        ax.axvspan(start, end, color=colors[day], alpha=alpha_by_session.get(day, 0.04))
        if index < len(sessions) - 1:
            ax.axvline(end, color="#D1D5DB", linewidth=1.0, alpha=0.8)
        ax.text(
            start + step / 2,
            1.02,
            labels.get(day, f"day {day}"),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=11,
            color="#4B5563",
            weight="bold",
        )
    ax.set_xticks([step * index + step / 2 for index in range(len(sessions))])
    ax.set_xticklabels([labels.get(day, f"day {day}") for day in sessions])


def add_day_background(ax: plt.Axes, step: int) -> None:
    add_session_background(ax, DAY_ORDER, step, DAY_COLORS)


def save_figure(fig: plt.Figure, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_mid_price(prices: pd.DataFrame, product: str, step: int) -> None:
    product_prices = prices[prices["product"] == product]
    product_name = pretty_product(product)

    fig, ax = plt.subplots(figsize=(15.5, 5.4))
    add_day_background(ax, step)

    legend_handles = []
    for day in DAY_ORDER:
        day_df = product_day_slice(product_prices, product, day)
        color = DAY_COLORS[day]
        ax.plot(day_df["global_ts"], day_df["mid_price"], color=color, linewidth=1.4, alpha=0.55)
        ax.plot(day_df["global_ts"], day_df["rolling_mid"], color=color, linewidth=2.4, alpha=0.95)
        legend_handles.append(Line2D([0], [0], color=color, lw=2.4, label=f"mid · day {day}"))

    ax.set_title(f"{product_name} — mid price across round 1", loc="left", pad=14)
    ax.text(
        0,
        1.11,
        "Thin line = raw mid price · thick line = 50-tick rolling average · days stitched chronologically",
        transform=ax.transAxes,
        fontsize=11,
        color="#4B5563",
    )
    ax.set_xlabel("chronological time")
    ax.set_ylabel("mid price")
    ax.legend(handles=legend_handles, ncol=3, loc="upper left")

    output_path = OUTPUT_DIR / f"{product}_mid_price_day_-1_then_0_then_1.png"
    save_figure(fig, output_path)


def plot_mid_bid_ask(prices: pd.DataFrame, trades: pd.DataFrame, product: str, step: int) -> None:
    product_prices = prices[prices["product"] == product]
    product_trades = trades[trades["symbol"] == product]
    product_name = pretty_product(product)

    fig, ax = plt.subplots(figsize=(15.5, 5.8))
    add_day_background(ax, step)

    for day in DAY_ORDER:
        day_df = product_day_slice(product_prices, product, day)
        color = DAY_COLORS[day]
        valid_book = day_df["bid_price_1"].notna() & day_df["ask_price_1"].notna()
        if valid_book.any():
            ax.fill_between(
                day_df.loc[valid_book, "global_ts"],
                day_df.loc[valid_book, "bid_price_1"],
                day_df.loc[valid_book, "ask_price_1"],
                color=color,
                alpha=0.12,
            )
        ax.plot(day_df["global_ts"], day_df["bid_price_1"], color=color, linewidth=1.0, linestyle="--", alpha=0.6)
        ax.plot(day_df["global_ts"], day_df["ask_price_1"], color=color, linewidth=1.0, linestyle=":", alpha=0.7)
        ax.plot(day_df["global_ts"], day_df["mid_price"], color=color, linewidth=1.8, alpha=0.95)

    if not product_trades.empty:
        trade_colors = product_trades["day"].map(DAY_COLORS)
        ax.scatter(
            product_trades["global_ts"],
            product_trades["price"],
            s=product_trades["quantity"].fillna(1).clip(lower=1) * 7,
            c=trade_colors,
            alpha=0.25,
            linewidths=0,
            zorder=3,
        )

    day_handles = [Line2D([0], [0], color=DAY_COLORS[day], lw=2.0, label=f"day {day}") for day in DAY_ORDER]
    series_handles = [
        Line2D([0], [0], color="#111827", lw=1.8, linestyle="-", label="mid"),
        Line2D([0], [0], color="#111827", lw=1.2, linestyle="--", label="best bid"),
        Line2D([0], [0], color="#111827", lw=1.2, linestyle=":", label="best ask"),
        Patch(facecolor="#9CA3AF", alpha=0.18, label="bid/ask band"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#6B7280", markersize=8, alpha=0.4, label="trade prints"),
    ]
    legend_days = ax.legend(handles=day_handles, title="day", ncol=3, loc="upper left")
    ax.add_artist(legend_days)
    ax.legend(handles=series_handles, title="series", loc="upper right")

    ax.set_title(f"{product_name} — mid / best bid / best ask", loc="left", pad=14)
    ax.text(
        0,
        1.11,
        "Transparent band = spread when both sides exist · bubbles = traded prices sized by quantity",
        transform=ax.transAxes,
        fontsize=11,
        color="#4B5563",
    )
    ax.set_xlabel("chronological time")
    ax.set_ylabel("price")

    output_path = OUTPUT_DIR / f"{product}_mid_price_with_bid_ask_day_-1_then_0_then_1.png"
    save_figure(fig, output_path)


def plot_mid_only_small_multiples(prices: pd.DataFrame, product: str) -> None:
    product_prices = prices[prices["product"] == product]
    product_name = pretty_product(product)

    fig, axes = plt.subplots(1, 3, figsize=(18, 4.8), sharey=True)
    for ax, day in zip(axes, DAY_ORDER, strict=True):
        day_df = product_day_slice(product_prices, product, day)
        color = DAY_COLORS[day]
        valid_mid = day_df["mid_price"].dropna()
        net_move = valid_mid.iloc[-1] - valid_mid.iloc[0] if len(valid_mid) >= 2 else np.nan
        day_range = valid_mid.max() - valid_mid.min() if not valid_mid.empty else np.nan

        ax.plot(day_df["timestamp"], day_df["mid_price"], color=color, linewidth=1.2, alpha=0.45)
        ax.plot(day_df["timestamp"], day_df["rolling_mid"], color=color, linewidth=2.6, alpha=0.95)
        ax.set_title(f"day {day}")
        ax.set_xlabel("timestamp")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
        ax.text(
            0.02,
            0.96,
            f"net {net_move:+.1f}\nrange {day_range:.1f}",
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=10,
            color="#374151",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#E5E7EB", "alpha": 0.9},
        )
    axes[0].set_ylabel("mid price")

    fig.suptitle(f"{product_name} — historical mid price by day", x=0.01, y=0.98, ha="left", fontsize=20, fontweight="bold")
    fig.subplots_adjust(top=0.80, wspace=0.15)

    output_path = OUTPUT_DIR / f"{product}_mid_price_intraday_panels.png"
    save_figure(fig, output_path)


def plot_mid_only_regime_dashboard(prices: pd.DataFrame, metrics: pd.DataFrame, product: str, step: int) -> None:
    product_prices = prices[prices["product"] == product].copy()
    product_name = pretty_product(product)
    strategy_row = metrics[(metrics["product"] == product) & (metrics["day"] == "ALL")].iloc[0]

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax_norm, ax_trend, ax_resid, ax_eff = axes.flatten()

    for day in DAY_ORDER:
        day_df = product_day_slice(product_prices, product, day)
        color = DAY_COLORS[day]
        ax_norm.plot(day_df["timestamp"], day_df["normalized_intraday"], color=color, linewidth=2.2, label=f"day {day}")
    ax_norm.axhline(100, color="#9CA3AF", linewidth=1.0)
    ax_norm.set_title("Normalized intraday mid path (base = 100)")
    ax_norm.set_xlabel("timestamp")
    ax_norm.set_ylabel("normalized mid")
    ax_norm.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
    ax_norm.legend(ncol=3, loc="upper left")

    trend_frame, slope, _, r_squared = fit_linear_trend(product_prices, "global_ts")
    add_day_background(ax_trend, step)
    ax_trend.plot(trend_frame["global_ts"], trend_frame["mid_price"], color=PRODUCT_COLORS[product], linewidth=1.5, alpha=0.55)
    ax_trend.plot(trend_frame["global_ts"], trend_frame["trend"], color="#111827", linewidth=2.6, linestyle="--")
    ax_trend.set_title("Historical mid price vs fitted trend")
    ax_trend.set_xlabel("chronological time")
    ax_trend.set_ylabel("mid price")
    ax_trend.text(
        0.02,
        0.95,
        f"drift / 10k ts = {slope * 10_000:+.2f}\ntrend R² = {r_squared:.3f}",
        transform=ax_trend.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        color="#374151",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#E5E7EB", "alpha": 0.9},
    )

    residual_std = trend_frame["residual"].std()
    for day in DAY_ORDER:
        day_df = product_day_slice(product_prices, product, day)
        day_trend_frame, *_ = fit_linear_trend(day_df, "timestamp")
        ax_resid.plot(day_trend_frame["timestamp"], day_trend_frame["residual"], color=DAY_COLORS[day], linewidth=1.8, alpha=0.9, label=f"day {day}")
    for multiple, alpha in [(1, 0.16), (2, 0.08)]:
        ax_resid.axhspan(-multiple * residual_std, multiple * residual_std, color="#93C5FD", alpha=alpha)
    ax_resid.axhline(0, color="#111827", linewidth=1.0)
    ax_resid.set_title("Residual around each day trend")
    ax_resid.set_xlabel("timestamp")
    ax_resid.set_ylabel("mid - fitted trend")
    ax_resid.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
    ax_resid.legend(ncol=3, loc="upper left")

    for day in DAY_ORDER:
        day_df = product_day_slice(product_prices, product, day)
        ax_eff.plot(
            day_df["timestamp"],
            day_df["rolling_efficiency_200"],
            color=DAY_COLORS[day],
            linewidth=2.0,
            alpha=0.9,
            label=f"day {day}",
        )
    ax_eff.axhline(0.10, color="#9CA3AF", linewidth=1.0, linestyle="--")
    ax_eff.axhline(0.40, color="#9CA3AF", linewidth=1.0, linestyle=":")
    ax_eff.set_ylim(bottom=0)
    ax_eff.set_title("Rolling path efficiency (200 ticks)")
    ax_eff.set_xlabel("timestamp")
    ax_eff.set_ylabel("efficiency ratio")
    ax_eff.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
    ax_eff.text(0.02, 0.94, "≈0 => choppy / MR\n≈1 => straight trend", transform=ax_eff.transAxes, va="top", fontsize=10, color="#4B5563")

    fig.suptitle(f"{product_name} — mid-only regime dashboard", x=0.01, y=1.03, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.985,
        f"Suggested style: {strategy_row['suggested_strategy']} · {strategy_row['strategy_playbook']}",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.86, hspace=0.34, wspace=0.18)

    output_path = OUTPUT_DIR / f"{product}_mid_only_regime_dashboard.png"
    save_figure(fig, output_path)


def build_imbalance_deciles(product_prices: pd.DataFrame) -> pd.DataFrame:
    signal_df = product_prices[["top_level_imbalance", f"future_mid_change_{FUTURE_HORIZON}"]].dropna().copy()
    if signal_df.empty:
        return pd.DataFrame(columns=["decile", "avg_future_move"])
    signal_df["decile"] = pd.qcut(signal_df["top_level_imbalance"], 10, labels=False, duplicates="drop")
    grouped = (
        signal_df.groupby("decile", as_index=False)[f"future_mid_change_{FUTURE_HORIZON}"]
        .mean()
        .rename(columns={f"future_mid_change_{FUTURE_HORIZON}": "avg_future_move"})
    )
    grouped["decile"] = grouped["decile"] + 1
    return grouped


def plot_behavior_dashboard(prices: pd.DataFrame, trades: pd.DataFrame, product: str) -> None:
    product_prices = prices[prices["product"] == product].copy()
    product_trades = trades[trades["symbol"] == product].copy()
    product_name = pretty_product(product)

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax_intraday, ax_spread, ax_signal, ax_trades = axes.flatten()

    for day in DAY_ORDER:
        day_df = product_day_slice(product_prices, product, day)
        color = DAY_COLORS[day]
        ax_intraday.plot(day_df["timestamp"], day_df["intraday_move"], color=color, linewidth=2.0, label=f"day {day}")
    ax_intraday.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_intraday.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
    ax_intraday.set_title("Intraday move from first valid mid")
    ax_intraday.set_xlabel("timestamp")
    ax_intraday.set_ylabel("Δ mid price")
    ax_intraday.legend(ncol=3, loc="upper left")

    spread_df = product_prices[["day", "spread"]].dropna().copy()
    spread_df["day_label"] = spread_df["day"].map(lambda value: f"day {value}")
    if not spread_df.empty:
        sns.boxenplot(
            data=spread_df,
            x="day_label",
            y="spread",
            order=[f"day {day}" for day in DAY_ORDER],
            hue="day_label",
            palette={f"day {day}": DAY_COLORS[day] for day in DAY_ORDER},
            dodge=False,
            legend=False,
            ax=ax_spread,
        )
    ax_spread.set_title("Spread distribution by day")
    ax_spread.set_xlabel("day")
    ax_spread.set_ylabel("spread")

    deciles = build_imbalance_deciles(product_prices)
    if not deciles.empty:
        deciles["decile_label"] = deciles["decile"].astype(str)
        sns.barplot(
            data=deciles,
            x="decile_label",
            y="avg_future_move",
            hue="decile_label",
            palette=sns.color_palette("blend:#EF4444,#F59E0B,#10B981", n_colors=len(deciles)),
            dodge=False,
            legend=False,
            ax=ax_signal,
        )
    ax_signal.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_signal.set_title(f"Average {FUTURE_HORIZON}-tick mid move by imbalance bucket")
    ax_signal.set_xlabel("imbalance bucket (sell-heavy → buy-heavy)")
    ax_signal.set_ylabel("future mid move")

    trade_summary = (
        product_trades.groupby("day", as_index=False)
        .agg(total_qty=("quantity", "sum"), trade_count=("price", "size"), avg_trade_size=("quantity", "mean"))
        .sort_values("day")
    )
    if not trade_summary.empty:
        trade_summary["day_label"] = trade_summary["day"].map(lambda value: f"day {value}")
        sns.barplot(
            data=trade_summary,
            x="day_label",
            y="total_qty",
            order=[f"day {day}" for day in DAY_ORDER],
            hue="day_label",
            palette={f"day {day}": DAY_COLORS[day] for day in DAY_ORDER},
            dodge=False,
            legend=False,
            ax=ax_trades,
        )
        ax_trades.set_ylabel("total traded quantity")
        ax_trades.set_xlabel("day")
        ax_trades.set_title("Trade activity snapshot")
        twin = ax_trades.twinx()
        twin.plot(range(len(trade_summary)), trade_summary["trade_count"], color="#111827", marker="o", linewidth=2.0)
        twin.set_ylabel("trade count")
        for index, row in trade_summary.reset_index(drop=True).iterrows():
            ax_trades.text(index, row["total_qty"] + 18, f"avg size {row['avg_trade_size']:.1f}", ha="center", fontsize=10)
    else:
        ax_trades.set_title("Trade activity snapshot")
        ax_trades.text(0.5, 0.5, "No trades found", ha="center", va="center", transform=ax_trades.transAxes)

    fig.suptitle(f"{product_name} — behavior dashboard", x=0.01, y=1.02, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.985,
        "Useful to separate regime, liquidity, and signal strength instead of staring only at raw prices.",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.86, hspace=0.36, wspace=0.22)

    output_path = OUTPUT_DIR / f"{product}_behavior_dashboard.png"
    save_figure(fig, output_path)


def combine_train_and_official_prices(prices: pd.DataFrame, official_prices: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(
        [
            prices.assign(dataset="train"),
            official_prices.assign(dataset="official_test"),
        ],
        ignore_index=True,
        sort=False,
    )


def build_train_test_session_meta(official_days: list[int]) -> tuple[list[int], dict[int, str], dict[int, str], dict[int, float]]:
    session_order = DAY_ORDER + official_days
    session_colors = {**DAY_COLORS}
    session_labels = {day: f"train day {day}" for day in DAY_ORDER}
    session_alpha = {day: 0.04 for day in DAY_ORDER}

    for day in official_days:
        session_colors[day] = OFFICIAL_TEST_COLOR
        session_alpha[day] = 0.09
        if len(official_days) == 1:
            session_labels[day] = f"official test · day {day}"
        else:
            session_labels[day] = f"official · day {day}"

    return session_order, session_colors, session_labels, session_alpha


def plot_train_vs_official_test_mid(
    prices: pd.DataFrame,
    official_prices: pd.DataFrame,
    official_days: list[int],
    step: int,
) -> None:
    if official_prices.empty or not official_days:
        return

    combined = combine_train_and_official_prices(prices, official_prices)
    session_order, session_colors, session_labels, session_alpha = build_train_test_session_meta(official_days)

    ordered_products = [product for product in PRODUCT_COLORS if product in combined["product"].unique()]
    if not ordered_products:
        ordered_products = sorted(combined["product"].unique().tolist())

    fig, axes = plt.subplots(
        len(ordered_products),
        2,
        figsize=(18.5, 5.2 * len(ordered_products)),
        gridspec_kw={"width_ratios": [1.6, 1]},
        squeeze=False,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            color=session_colors[day],
            lw=3.0 if day in official_days else 2.2,
            label=session_labels[day],
        )
        for day in session_order
    ]

    for row_index, product in enumerate(ordered_products):
        product_name = pretty_product(product)
        product_prices = combined[combined["product"] == product].copy()
        ax_chrono, ax_overlay = axes[row_index]

        add_session_background(ax_chrono, session_order, step, session_colors, session_labels, session_alpha)

        for day in session_order:
            day_df = product_day_slice(product_prices, product, day).copy()
            if day_df.empty:
                continue

            color = session_colors[day]
            is_official = day in official_days
            raw_alpha = 0.26 if is_official else 0.16
            smooth_alpha = 1.0 if is_official else 0.95
            smooth_width = 3.2 if is_official else 2.2
            zorder = 5 if is_official else 3

            ax_chrono.plot(day_df["global_ts"], day_df["mid_price"], color=color, linewidth=1.15, alpha=raw_alpha, zorder=zorder - 1)
            smooth_line = ax_chrono.plot(
                day_df["global_ts"],
                day_df["rolling_mid"],
                color=color,
                linewidth=smooth_width,
                alpha=smooth_alpha,
                zorder=zorder,
            )[0]
            if is_official:
                smooth_line.set_path_effects([pe.Stroke(linewidth=smooth_width + 2.0, foreground="#FFF7ED"), pe.Normal()])
                valid_mid = day_df.dropna(subset=["mid_price"])
                if not valid_mid.empty:
                    endpoints = valid_mid.iloc[[0, -1]]
                    ax_chrono.scatter(
                        endpoints["global_ts"],
                        endpoints["mid_price"],
                        s=34,
                        color=color,
                        edgecolors="white",
                        linewidths=1.1,
                        zorder=zorder + 1,
                    )

            valid_mid = day_df["mid_price"].dropna()
            if valid_mid.empty:
                continue
            baseline = valid_mid.iloc[0]
            day_df["normalized_mid"] = 100 * day_df["mid_price"] / baseline
            overlay_line = ax_overlay.plot(
                day_df["timestamp"],
                day_df["normalized_mid"],
                color=color,
                linewidth=3.0 if is_official else 2.0,
                alpha=1.0 if is_official else 0.92,
                zorder=4 if is_official else 2,
            )[0]
            if is_official:
                overlay_line.set_path_effects([pe.Stroke(linewidth=5.0, foreground="#FFF7ED"), pe.Normal()])

        ax_chrono.set_title(f"{product_name} — train sessions stitched with the official test", loc="left", pad=14)
        ax_chrono.text(
            0.01,
            0.98,
            "Raw mid is faint · 50-tick rolling mid carries the structure · the official session is highlighted in amber.",
            transform=ax_chrono.transAxes,
            va="top",
            fontsize=9.8,
            color="#4B5563",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        )
        ax_chrono.set_xlabel("session chronology")
        ax_chrono.set_ylabel("mid price")

        train_moves = []
        for day in DAY_ORDER:
            day_df = product_day_slice(product_prices, product, day)
            move, _ = session_move_and_range(day_df["mid_price"])
            if pd.notna(move):
                train_moves.append(move)

        official_move, official_range = session_move_and_range(
            product_prices[product_prices["day"].isin(official_days)]["mid_price"]
        )
        train_avg_move = float(np.nanmean(train_moves)) if train_moves else np.nan
        ax_chrono.text(
            0.99,
            0.96,
            "\n".join(
                [
                    f"train avg Δ {train_avg_move:+.1f}" if pd.notna(train_avg_move) else "train avg Δ n/a",
                    f"official Δ {official_move:+.1f}" if pd.notna(official_move) else "official Δ n/a",
                    f"official range {official_range:.1f}" if pd.notna(official_range) else "official range n/a",
                ]
            ),
            transform=ax_chrono.transAxes,
            ha="right",
            va="top",
            fontsize=10,
            color="#1F2937",
            bbox={"boxstyle": "round,pad=0.42", "facecolor": "white", "edgecolor": "#E5E7EB", "alpha": 0.96},
        )

        ax_overlay.axhline(100, color="#9CA3AF", linewidth=1.0, linestyle="--")
        ax_overlay.set_title("Intraday overlay (base = 100)", loc="left", pad=14)
        ax_overlay.text(
            0.01,
            0.98,
            "Same session, rebased to 100 so shape differences stand out instead of absolute price level.",
            transform=ax_overlay.transAxes,
            va="top",
            fontsize=9.8,
            color="#4B5563",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        )
        ax_overlay.set_xlabel("timestamp")
        ax_overlay.set_ylabel("normalized mid")
        ax_overlay.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))

    fig.suptitle("Round 2 — train vs official test mid price dashboard", x=0.01, y=0.992, ha="left", fontsize=22, fontweight="bold")
    fig.text(
        0.01,
        0.958,
        "Left: the three local train sessions followed by the official IMC test session. Right: normalized overlays to compare path shape.",
        fontsize=11,
        color="#4B5563",
    )
    fig.legend(handles=legend_handles, ncol=len(legend_handles), loc="upper center", bbox_to_anchor=(0.5, 0.928), frameon=False)
    fig.subplots_adjust(top=0.81, hspace=0.38, wspace=0.16)

    output_path = OUTPUT_DIR / "train_vs_official_test_mid_price_dashboard.png"
    save_figure(fig, output_path)


def plot_product_train_vs_official_test_comparison(
    prices: pd.DataFrame,
    official_prices: pd.DataFrame,
    official_days: list[int],
    product: str,
    step: int,
) -> None:
    if official_prices.empty or not official_days:
        return

    combined = combine_train_and_official_prices(prices, official_prices)
    session_order, session_colors, session_labels, session_alpha = build_train_test_session_meta(official_days)
    product_prices = combined[combined["product"] == product].copy()
    product_name = pretty_product(product)

    fig, (ax_chrono, ax_overlay) = plt.subplots(
        1,
        2,
        figsize=(17.2, 5.8),
        gridspec_kw={"width_ratios": [1.55, 1]},
    )

    add_session_background(ax_chrono, session_order, step, session_colors, session_labels, session_alpha)

    legend_handles = []
    for day in session_order:
        day_df = product_day_slice(product_prices, product, day).copy()
        if day_df.empty:
            continue

        color = session_colors[day]
        is_official = day in official_days
        raw_alpha = 0.24 if is_official else 0.14
        smooth_width = 3.0 if is_official else 2.1

        ax_chrono.plot(day_df["global_ts"], day_df["mid_price"], color=color, linewidth=1.0, alpha=raw_alpha, zorder=2)
        smooth_line = ax_chrono.plot(
            day_df["global_ts"],
            day_df["rolling_mid"],
            color=color,
            linewidth=smooth_width,
            alpha=1.0 if is_official else 0.95,
            zorder=4 if is_official else 3,
        )[0]
        if is_official:
            smooth_line.set_path_effects([pe.Stroke(linewidth=smooth_width + 2.0, foreground="#FFF7ED"), pe.Normal()])

        valid_mid = day_df["mid_price"].dropna()
        if not valid_mid.empty:
            day_df["normalized_mid"] = 100 * day_df["mid_price"] / valid_mid.iloc[0]
            overlay_line = ax_overlay.plot(
                day_df["timestamp"],
                day_df["normalized_mid"],
                color=color,
                linewidth=3.0 if is_official else 2.0,
                alpha=1.0 if is_official else 0.9,
                zorder=4 if is_official else 2,
            )[0]
            if is_official:
                overlay_line.set_path_effects([pe.Stroke(linewidth=5.0, foreground="#FFF7ED"), pe.Normal()])

        legend_handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                lw=3.0 if is_official else 2.1,
                label=session_labels[day],
            )
        )

    ax_chrono.set_title(f"{product_name} — train sessions + official test", loc="left", pad=14)
    ax_chrono.text(
        0.01,
        0.98,
        "Train days stay in their own colors. The official test is highlighted in amber.",
        transform=ax_chrono.transAxes,
        va="top",
        fontsize=10,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax_chrono.set_xlabel("session chronology")
    ax_chrono.set_ylabel("mid price")

    ax_overlay.axhline(100, color="#9CA3AF", linewidth=1.0, linestyle="--")
    ax_overlay.set_title("Normalized overlay (base = 100)", loc="left", pad=14)
    ax_overlay.text(
        0.01,
        0.98,
        "Rebased paths make it obvious whether the official test behaves like the train sessions.",
        transform=ax_overlay.transAxes,
        va="top",
        fontsize=10,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax_overlay.set_xlabel("timestamp")
    ax_overlay.set_ylabel("normalized mid")
    ax_overlay.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))

    fig.suptitle(f"{product_name} — train vs official test", x=0.01, y=0.99, ha="left", fontsize=20, fontweight="bold")
    fig.legend(handles=legend_handles, ncol=min(len(legend_handles), 4), loc="upper center", bbox_to_anchor=(0.5, 0.94), frameon=False)
    fig.subplots_adjust(top=0.80, wspace=0.16)

    output_path = OUTPUT_DIR / f"{product}_train_vs_official_test_comparison.png"
    save_figure(fig, output_path)


def plot_product_train_vs_official_test_envelope(
    prices: pd.DataFrame,
    official_prices: pd.DataFrame,
    official_days: list[int],
    product: str,
) -> None:
    if official_prices.empty or not official_days:
        return

    product_name = pretty_product(product)
    train_product = prices[prices["product"] == product].copy()
    official_product = official_prices[official_prices["product"] == product].copy()
    if train_product.empty or official_product.empty:
        return

    train_sessions: list[pd.DataFrame] = []
    for day in DAY_ORDER:
        day_df = product_day_slice(train_product, product, day).copy()
        valid_mid = day_df["mid_price"].dropna()
        if valid_mid.empty:
            continue
        day_df["normalized_mid"] = 100 * day_df["mid_price"] / valid_mid.iloc[0]
        day_df["session_label"] = f"train day {day}"
        train_sessions.append(day_df[["timestamp", "normalized_mid", "session_label"]])

    official_sessions: list[pd.DataFrame] = []
    for day in official_days:
        day_df = product_day_slice(official_product, product, day).copy()
        valid_mid = day_df["mid_price"].dropna()
        if valid_mid.empty:
            continue
        day_df["normalized_mid"] = 100 * day_df["mid_price"] / valid_mid.iloc[0]
        day_df["session_label"] = f"official test · day {day}"
        official_sessions.append(day_df[["timestamp", "normalized_mid", "session_label"]])

    if not train_sessions or not official_sessions:
        return

    train_overlay = pd.concat(train_sessions, ignore_index=True)
    official_overlay = pd.concat(official_sessions, ignore_index=True)
    train_pivot = train_overlay.pivot(index="timestamp", columns="session_label", values="normalized_mid").sort_index()

    envelope = pd.DataFrame(index=train_pivot.index)
    envelope["train_mean"] = train_pivot.mean(axis=1)
    envelope["train_min"] = train_pivot.min(axis=1)
    envelope["train_max"] = train_pivot.max(axis=1)
    envelope["train_q25"] = train_pivot.quantile(0.25, axis=1)
    envelope["train_q75"] = train_pivot.quantile(0.75, axis=1)

    official_series = (
        official_overlay.groupby("timestamp", as_index=True)["normalized_mid"]
        .mean()
        .reindex(envelope.index)
    )
    if official_series.dropna().empty:
        return

    train_fill_color = "#94A3B8"
    train_mean_color = "#475569"
    fig, ax = plt.subplots(figsize=(14.2, 5.6))
    ax.fill_between(
        envelope.index,
        envelope["train_min"],
        envelope["train_max"],
        color=train_fill_color,
        alpha=0.10,
        label="train min-max range",
    )
    ax.fill_between(
        envelope.index,
        envelope["train_q25"],
        envelope["train_q75"],
        color=train_fill_color,
        alpha=0.20,
        label="train interquartile band",
    )
    ax.plot(
        envelope.index,
        envelope["train_mean"],
        color=train_mean_color,
        linewidth=2.6,
        label="train mean path",
    )

    for session_label, day_df in train_overlay.groupby("session_label"):
        ax.plot(day_df["timestamp"], day_df["normalized_mid"], color=train_fill_color, linewidth=1.0, alpha=0.28)

    official_line = ax.plot(
        official_series.index,
        official_series.values,
        color=OFFICIAL_TEST_COLOR,
        linewidth=3.2,
        label="official test path",
        zorder=5,
    )[0]
    official_line.set_path_effects([pe.Stroke(linewidth=5.2, foreground="#FFF7ED"), pe.Normal()])

    final_delta = official_series.iloc[-1] - envelope["train_mean"].iloc[-1]
    ax.text(
        0.99,
        0.95,
        f"final official vs train mean: {final_delta:+.2f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        color="#1F2937",
        bbox={"boxstyle": "round,pad=0.36", "facecolor": "white", "edgecolor": "#E5E7EB", "alpha": 0.95},
    )

    ax.axhline(100, color="#9CA3AF", linewidth=1.0, linestyle="--")
    ax.set_title(f"{product_name} — official test vs train envelope", loc="left", pad=14)
    ax.text(
        0.01,
        0.98,
        "Slate envelope = train behavior after rebasing to 100. Amber line = official test.",
        transform=ax.transAxes,
        va="top",
        fontsize=10.5,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax.set_xlabel("timestamp")
    ax.set_ylabel("normalized mid")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}k"))
    ax.legend(loc="upper left")

    output_path = OUTPUT_DIR / f"{product}_train_vs_official_test_envelope.png"
    save_figure(fig, output_path)


def build_product_session_summary(
    prices: pd.DataFrame,
    official_prices: pd.DataFrame,
    official_days: list[int],
    product: str,
) -> pd.DataFrame:
    _, session_colors, session_labels, _ = build_train_test_session_meta(official_days)
    rows: list[dict[str, float | int | str]] = []

    for day in DAY_ORDER:
        day_df = product_day_slice(prices, product, day).copy()
        valid_mid = day_df["mid_price"].dropna()
        if valid_mid.empty:
            continue
        rows.append(
            {
                "source": "train",
                "day": day,
                "session_label": session_labels[day],
                "color": session_colors[day],
                "start_mid": float(valid_mid.iloc[0]),
                "end_mid": float(valid_mid.iloc[-1]),
                "min_mid": float(valid_mid.min()),
                "max_mid": float(valid_mid.max()),
                "mean_mid": float(valid_mid.mean()),
                "median_mid": float(valid_mid.median()),
                "std_mid": float(valid_mid.std()),
            }
        )

    for day in official_days:
        day_df = product_day_slice(official_prices, product, day).copy()
        valid_mid = day_df["mid_price"].dropna()
        if valid_mid.empty:
            continue
        rows.append(
            {
                "source": "official_test",
                "day": day,
                "session_label": session_labels[day],
                "color": session_colors[day],
                "start_mid": float(valid_mid.iloc[0]),
                "end_mid": float(valid_mid.iloc[-1]),
                "min_mid": float(valid_mid.min()),
                "max_mid": float(valid_mid.max()),
                "mean_mid": float(valid_mid.mean()),
                "median_mid": float(valid_mid.median()),
                "std_mid": float(valid_mid.std()),
            }
        )

    summary = pd.DataFrame(rows)
    if not summary.empty:
        summary["session_index"] = range(len(summary))
        summary["range_mid"] = summary["max_mid"] - summary["min_mid"]
    return summary


def plot_product_session_gap_diagnostic(
    prices: pd.DataFrame,
    official_prices: pd.DataFrame,
    official_days: list[int],
    product: str,
) -> None:
    if official_prices.empty or not official_days:
        return

    summary = build_product_session_summary(prices, official_prices, official_days, product)
    if summary.empty or len(summary) < 2:
        return

    product_name = pretty_product(product)
    fig, (ax_sessions, ax_gaps) = plt.subplots(
        1,
        2,
        figsize=(16.8, 5.8),
        gridspec_kw={"width_ratios": [1.45, 1]},
    )

    for _, row in summary.iterrows():
        x_pos = row["session_index"]
        color = row["color"]
        ax_sessions.vlines(x_pos, row["min_mid"], row["max_mid"], color=color, alpha=0.20, linewidth=14, zorder=1)
        ax_sessions.plot(
            [x_pos, x_pos],
            [row["start_mid"], row["end_mid"]],
            color=color,
            linewidth=5,
            solid_capstyle="round",
            zorder=3,
        )
        ax_sessions.scatter(x_pos, row["start_mid"], color="white", edgecolors=color, s=95, linewidths=2.0, zorder=4)
        ax_sessions.scatter(x_pos, row["end_mid"], color=color, edgecolors="white", s=95, linewidths=1.2, marker="s", zorder=4)

    boundary_rows: list[dict[str, float | int | str]] = []
    ordered = summary.sort_values("session_index").reset_index(drop=True)
    for index in range(1, len(ordered)):
        prev_row = ordered.iloc[index - 1]
        curr_row = ordered.iloc[index]
        gap = float(curr_row["start_mid"] - prev_row["end_mid"])
        boundary_rows.append(
            {
                "boundary_label": (
                    f"train {int(prev_row['day'])}→test {int(curr_row['day'])}"
                    if curr_row["source"] == "official_test"
                    else f"train {int(prev_row['day'])}→{int(curr_row['day'])}"
                ),
                "gap": gap,
                "is_official_boundary": curr_row["source"] == "official_test",
            }
        )
        ax_sessions.plot(
            [prev_row["session_index"], curr_row["session_index"]],
            [prev_row["end_mid"], curr_row["start_mid"]],
            color=OFFICIAL_TEST_COLOR if curr_row["source"] == "official_test" else "#94A3B8",
            linewidth=2.0,
            linestyle="--",
            alpha=0.95,
            zorder=2,
        )

    boundary_df = pd.DataFrame(boundary_rows)
    boundary_df["bar_color"] = boundary_df["is_official_boundary"].map({True: OFFICIAL_TEST_COLOR, False: "#CBD5E1"})
    boundary_df["text_color"] = boundary_df["gap"].map(lambda value: "#B91C1C" if value < 0 else "#0F766E")
    boundary_df["x"] = range(len(boundary_df))

    ax_gaps.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_gaps.bar(boundary_df["x"], boundary_df["gap"], color=boundary_df["bar_color"], width=0.62)
    for _, row in boundary_df.iterrows():
        offset = -0.8 if row["gap"] < 0 else 0.8
        va = "top" if row["gap"] < 0 else "bottom"
        ax_gaps.text(
            row["x"],
            row["gap"] + offset,
            f"{row['gap']:+.1f}",
            ha="center",
            va=va,
            fontsize=11,
            color=row["text_color"],
            fontweight="bold",
        )
    ax_gaps.set_xticks(boundary_df["x"])
    ax_gaps.set_xticklabels(boundary_df["boundary_label"], rotation=12, ha="right")
    ax_gaps.set_ylabel("open - prior close")
    ax_gaps.set_title("Boundary gaps across sessions", loc="left", pad=14)
    ax_gaps.text(
        0.01,
        0.98,
        "The amber bar is the one that matters most here: last train close vs first official-test open.",
        transform=ax_gaps.transAxes,
        va="top",
        fontsize=10.2,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )

    last_boundary = boundary_df.iloc[-1]
    ax_sessions.set_title(f"{product_name} — session gap diagnostic", loc="left", pad=14)
    ax_sessions.text(
        0.01,
        0.98,
        "Each vertical band shows the full session range. Circle = open, square = close.",
        transform=ax_sessions.transAxes,
        va="top",
        fontsize=10.2,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax_sessions.text(
        0.99,
        0.96,
        f"official boundary gap: {last_boundary['gap']:+.1f} ticks",
        transform=ax_sessions.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        color="#1F2937",
        bbox={"boxstyle": "round,pad=0.36", "facecolor": "white", "edgecolor": "#E5E7EB", "alpha": 0.95},
    )
    ax_sessions.set_xticks(summary["session_index"])
    ax_sessions.set_xticklabels(summary["session_label"])
    ax_sessions.set_ylabel("mid price")

    fig.suptitle(f"{product_name} — close/open jump diagnostic", x=0.01, y=0.978, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.930,
        "Use this when you want to see whether the official test opens where training left off, or whether the session re-anchors.",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.76, wspace=0.18)

    output_path = OUTPUT_DIR / f"{product}_session_gap_diagnostic.png"
    save_figure(fig, output_path)


def plot_product_anchor_shift_dashboard(
    prices: pd.DataFrame,
    official_prices: pd.DataFrame,
    official_days: list[int],
    product: str,
) -> None:
    if official_prices.empty or not official_days:
        return

    product_name = pretty_product(product)
    train_product = prices[prices["product"] == product].copy()
    official_product = official_prices[official_prices["product"] == product].copy()
    if train_product.empty or official_product.empty:
        return

    train_mid = train_product["mid_price"].dropna().astype(float)
    official_mid = official_product["mid_price"].dropna().astype(float)
    if train_mid.empty or official_mid.empty:
        return

    session_summary = build_product_session_summary(prices, official_prices, official_days, product)
    official_open = float(official_mid.iloc[0])
    official_median = float(official_mid.median())
    train_mean = float(train_mid.mean())
    train_median = float(train_mid.median())
    train_std = float(train_mid.std())
    last_train_close = float(session_summary[session_summary["source"] == "train"].sort_values("day").iloc[-1]["end_mid"])
    open_zscore = (official_open - train_mean) / train_std if train_std > 0 else np.nan
    official_median_zscore = (official_median - train_mean) / train_std if train_std > 0 else np.nan
    last_close_zscore = (last_train_close - train_mean) / train_std if train_std > 0 else np.nan
    train_open_rank = float((train_mid <= official_open).mean())
    official_below_train_min = float((official_mid < train_mid.min()).mean())

    fig = plt.figure(figsize=(18.2, 6.1))
    grid = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.0, 0.9])
    ax_density = fig.add_subplot(grid[0, 0])
    ax_sessions = fig.add_subplot(grid[0, 1])
    ax_score = fig.add_subplot(grid[0, 2])

    sns.histplot(train_mid, bins=48, stat="density", color="#94A3B8", alpha=0.38, kde=True, ax=ax_density, label="train")
    sns.histplot(official_mid, bins=42, stat="density", color=OFFICIAL_TEST_COLOR, alpha=0.30, kde=True, ax=ax_density, label="official test")
    ax_density.axvline(train_median, color="#475569", linewidth=2.2, linestyle="--", label=f"train median {train_median:.1f}")
    ax_density.axvline(official_open, color=OFFICIAL_TEST_COLOR, linewidth=2.8, label=f"official open {official_open:.1f}")
    ax_density.axvline(official_median, color="#B45309", linewidth=2.2, linestyle=":", label=f"official median {official_median:.1f}")
    ax_density.set_title("Train vs official mid distribution", loc="left", pad=14)
    ax_density.text(
        0.01,
        0.98,
        "If the amber distribution sits away from the slate one, the session likely re-anchored.",
        transform=ax_density.transAxes,
        va="top",
        fontsize=10.2,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax_density.set_xlabel("mid price")
    ax_density.set_ylabel("density")
    ax_density.legend(loc="upper right")

    box_rows: list[pd.DataFrame] = []
    _, session_colors, session_labels, _ = build_train_test_session_meta(official_days)
    for day in DAY_ORDER:
        day_df = product_day_slice(train_product, product, day).copy()
        valid_mid = day_df["mid_price"].dropna()
        if not valid_mid.empty:
            box_rows.append(pd.DataFrame({"session_label": session_labels[day], "mid_price": valid_mid}))
    for day in official_days:
        day_df = product_day_slice(official_product, product, day).copy()
        valid_mid = day_df["mid_price"].dropna()
        if not valid_mid.empty:
            box_rows.append(pd.DataFrame({"session_label": session_labels[day], "mid_price": valid_mid}))

    if box_rows:
        box_df = pd.concat(box_rows, ignore_index=True)
        palette = {label: session_colors[day] for day, label in session_labels.items()}
        sns.boxenplot(
            data=box_df,
            x="session_label",
            y="mid_price",
            order=[session_labels[day] for day in DAY_ORDER + official_days if session_labels.get(day) in box_df["session_label"].unique()],
            hue="session_label",
            palette=palette,
            dodge=False,
            legend=False,
            ax=ax_sessions,
        )
    ax_sessions.set_title("Session level comparison", loc="left", pad=14)
    ax_sessions.text(
        0.01,
        0.98,
        "This isolates whether the official day sits on the same level as train, or on a different base price.",
        transform=ax_sessions.transAxes,
        va="top",
        fontsize=10.2,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax_sessions.set_xlabel("")
    ax_sessions.set_ylabel("mid price")
    ax_sessions.tick_params(axis="x", rotation=12)

    ax_score.axvspan(-1, 1, color="#DCFCE7", alpha=0.45)
    ax_score.axvspan(-2, 2, color="#F3F4F6", alpha=0.45)
    ax_score.axvline(0, color="#6B7280", linewidth=1.2)
    ax_score.axhline(0.55, color="#E5E7EB", linewidth=1.0)
    ax_score.axhline(0.0, color="#E5E7EB", linewidth=1.0)
    ax_score.axhline(-0.55, color="#E5E7EB", linewidth=1.0)
    ax_score.scatter([last_close_zscore], [0.55], s=110, color="#475569", edgecolors="white", linewidths=1.2, zorder=3)
    ax_score.scatter([official_median_zscore], [0.0], s=110, color="#B45309", edgecolors="white", linewidths=1.2, zorder=3)
    ax_score.scatter([open_zscore], [-0.55], s=150, color=OFFICIAL_TEST_COLOR, edgecolors="white", linewidths=1.2, zorder=4)
    ax_score.text(last_close_zscore, 0.69, "last train close", ha="center", fontsize=9.8, color="#334155")
    ax_score.text(official_median_zscore, 0.14, "official median", ha="center", fontsize=9.8, color="#334155")
    ax_score.text(open_zscore, -0.41, "official open", ha="center", fontsize=9.8, color="#334155")
    ax_score.set_title("Anchor-shift score", loc="left", pad=14)
    ax_score.text(
        0.01,
        0.98,
        "Everything here is measured as z-score distance relative to the full train distribution.",
        transform=ax_score.transAxes,
        va="top",
        fontsize=10.2,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax_score.text(
        0.99,
        0.75,
        "\n".join(
            [
                f"open z-score: {open_zscore:+.2f}",
                f"open vs last close: {official_open - last_train_close:+.1f}",
                f"train rank of open: {train_open_rank * 100:.2f}%",
                f"official below train min: {official_below_train_min * 100:.2f}%",
            ]
        ),
        transform=ax_score.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        color="#1F2937",
        bbox={"boxstyle": "round,pad=0.36", "facecolor": "white", "edgecolor": "#E5E7EB", "alpha": 0.95},
    )
    x_bound = max(3.0, float(np.nanmax(np.abs([open_zscore, official_median_zscore, last_close_zscore])) + 0.8))
    ax_score.set_xlim(-x_bound, x_bound)
    ax_score.set_ylim(-1.0, 1.0)
    ax_score.set_xlabel("z-score vs train")
    ax_score.set_yticks([])

    fig.suptitle(f"{product_name} — anchor shift dashboard", x=0.01, y=0.978, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.930,
        "This plot answers a more specific question than the comparison charts: did the official session open inside the train regime, or on a different price anchor?",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.76, wspace=0.18)

    output_path = OUTPUT_DIR / f"{product}_anchor_shift_dashboard.png"
    save_figure(fig, output_path)


def compute_metrics(prices: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []

    for product in sorted(prices["product"].unique()):
        product_prices = prices[prices["product"] == product].copy()
        product_trades = trades[trades["symbol"] == product].copy()
        grouped_frames = [(str(day), product_prices[product_prices["day"] == day], "timestamp") for day in DAY_ORDER]
        grouped_frames.append(("ALL", product_prices, "global_ts"))

        for day_label, day_df, time_col in grouped_frames:
            valid_mid = day_df["mid_price"].dropna()
            price_changes = day_df["mid_change_1"].dropna()
            correlation = day_df[["top_level_imbalance", f"future_mid_change_{FUTURE_HORIZON}"]].corr().iloc[0, 1]
            first_valid = valid_mid.iloc[0] if not valid_mid.empty else np.nan
            last_valid = valid_mid.iloc[-1] if not valid_mid.empty else np.nan
            day_range = valid_mid.max() - valid_mid.min() if not valid_mid.empty else np.nan
            net_move = last_valid - first_valid if not valid_mid.empty else np.nan
            net_move_to_range = abs(net_move) / day_range if pd.notna(day_range) and day_range > 0 else np.nan

            residual_metrics = compute_residual_metrics(day_df, time_col)
            smooth_efficiency = safe_efficiency_ratio(day_df["rolling_mid"])
            rolling_efficiency_mean = day_df["rolling_efficiency_200"].mean()
            zscore_p95 = day_df["rolling_zscore_100"].dropna().abs().quantile(0.95)
            raw_variance_ratio_20 = variance_ratio(price_changes, 20)

            trade_df = product_trades if day_label == "ALL" else product_trades[product_trades["day"] == int(day_label)]
            total_trade_qty = float(trade_df["quantity"].sum()) if not trade_df.empty else 0.0
            trade_count = int(trade_df["price"].size) if not trade_df.empty else 0
            vwap = (
                float((trade_df["price"] * trade_df["quantity"]).sum() / trade_df["quantity"].sum())
                if total_trade_qty > 0
                else np.nan
            )

            row = {
                "product": product,
                "day": day_label,
                "valid_quote_pct": day_df["mid_price"].notna().mean() * 100,
                "mid_mean": valid_mid.mean(),
                "mid_std": valid_mid.std(),
                "mid_min": valid_mid.min(),
                "mid_max": valid_mid.max(),
                "day_range": day_range,
                "start_mid": first_valid,
                "end_mid": last_valid,
                "net_move": net_move,
                "net_move_to_range": net_move_to_range,
                "avg_spread": day_df["spread"].mean(),
                "spread_p90": day_df["spread"].quantile(0.90),
                "avg_spread_bps": (day_df["spread"] / day_df["mid_price"]).mean() * 10_000,
                "mid_change_std": price_changes.std(),
                "lag1_mid_change_autocorr": price_changes.autocorr(lag=1) if len(price_changes) > 2 else np.nan,
                "raw_variance_ratio_20": raw_variance_ratio_20,
                "smooth_efficiency_50": smooth_efficiency,
                "rolling_efficiency_200_mean": rolling_efficiency_mean,
                "rolling_zscore_100_abs_p95": zscore_p95,
                "imbalance_mean": day_df["top_level_imbalance"].mean(),
                "imbalance_std": day_df["top_level_imbalance"].std(),
                f"imbalance_future_{FUTURE_HORIZON}_corr": correlation,
                "trade_count": trade_count,
                "total_trade_qty": total_trade_qty,
                "avg_trade_size": trade_df["quantity"].mean() if not trade_df.empty else np.nan,
                "trade_vwap": vwap,
                **residual_metrics,
            }
            suggested_strategy, strategy_playbook = classify_strategy(pd.Series(row))
            row["suggested_strategy"] = suggested_strategy
            row["strategy_playbook"] = strategy_playbook
            rows.append(row)

    metrics = pd.DataFrame(rows)
    numeric_columns = metrics.select_dtypes(include=[np.number]).columns
    metrics[numeric_columns] = metrics[numeric_columns].round(4)
    return metrics


def plot_cross_asset_comparison(prices: pd.DataFrame, metrics: pd.DataFrame, step: int) -> None:
    fig, (ax_price, ax_heatmap) = plt.subplots(1, 2, figsize=(17.5, 6.8), gridspec_kw={"width_ratios": [1.25, 1]})
    add_day_background(ax_price, step)

    overall_metrics = metrics[metrics["day"] == "ALL"].copy().set_index("product")
    for product, color in PRODUCT_COLORS.items():
        product_prices = prices[prices["product"] == product].copy()
        baseline = product_prices["mid_price"].dropna().iloc[0]
        product_prices["normalized_mid"] = 100 * product_prices["mid_price"] / baseline
        ax_price.plot(
            product_prices["global_ts"],
            product_prices["normalized_mid"],
            color=color,
            linewidth=2.4,
            label=pretty_product(product),
        )
    ax_price.set_title("Normalized price paths (base = 100)", loc="left", pad=14)
    ax_price.set_xlabel("chronological time")
    ax_price.set_ylabel("normalized mid price")
    ax_price.legend(loc="upper left")

    heatmap_columns = [
        "avg_spread_bps",
        "mid_change_std",
        "trend_r2",
        "smooth_efficiency_50",
        "drift_noise_ratio",
        "residual_half_life",
        f"imbalance_future_{FUTURE_HORIZON}_corr",
    ]
    heatmap_labels = {
        "avg_spread_bps": "avg spread (bps)",
        "mid_change_std": "tick vol (σ)",
        "trend_r2": "trend R²",
        "smooth_efficiency_50": "smooth eff50",
        "drift_noise_ratio": "drift / noise",
        "residual_half_life": "resid half-life",
        f"imbalance_future_{FUTURE_HORIZON}_corr": f"imbalance→future{FUTURE_HORIZON} corr",
    }
    actual_values = overall_metrics[heatmap_columns].rename(columns=heatmap_labels)
    standardized = (actual_values - actual_values.mean()) / actual_values.std(ddof=0).replace(0, 1)
    annotations = actual_values.apply(lambda column: column.map(lambda value: f"{value:.2f}"))
    sns.heatmap(
        standardized.rename(index=pretty_product),
        annot=annotations.rename(index=pretty_product),
        fmt="",
        cmap=sns.diverging_palette(245, 25, as_cmap=True),
        center=0,
        linewidths=1,
        linecolor="#FFFFFF",
        cbar_kws={"label": "column-standardized score"},
        ax=ax_heatmap,
    )
    ax_heatmap.set_title("Strategy-oriented asset metrics", loc="left", pad=14)
    ax_heatmap.set_xlabel("metric")
    ax_heatmap.set_ylabel("")

    fig.suptitle("Round 2 — cross-asset comparison", x=0.01, y=1.03, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.985,
        "Left: regime shape. Right: strategy metrics that separate stationary fair-value assets from directional ones.",
        fontsize=11,
        color="#4B5563",
    )

    output_path = OUTPUT_DIR / "cross_asset_comparison.png"
    save_figure(fig, output_path)


def plot_mid_only_strategy_map(metrics: pd.DataFrame) -> None:
    strategy_df = metrics[metrics["day"] == "ALL"].copy()
    strategy_df["bubble_size"] = 350 + 450 * np.clip(1 / strategy_df["residual_half_life"].replace(0, np.nan), 0, 3).fillna(0.5)
    strategy_colors = {
        "Stationary mean reversion / market making": "#2563EB",
        "Trend + pullback mean reversion": "#F97316",
        "Directional trend following": "#DC2626",
        "Moving-anchor mean reversion": "#059669",
        "Mixed / regime-switching": "#6B7280",
    }

    fig, ax = plt.subplots(figsize=(10.5, 7.5))
    ax.axvspan(0, 0.15, color="#DBEAFE", alpha=0.35)
    ax.axvspan(0.35, max(strategy_df["smooth_efficiency_50"].max() * 1.1, 1.0), color="#FEF3C7", alpha=0.35)
    ax.axhspan(0, 0.5, color="#F3F4F6", alpha=0.4)
    ax.axhspan(1.0, max(strategy_df["drift_noise_ratio"].max() * 1.1, 1.6), color="#DCFCE7", alpha=0.35)

    for _, row in strategy_df.iterrows():
        color = strategy_colors.get(row["suggested_strategy"], "#6B7280")
        ax.scatter(
            row["smooth_efficiency_50"],
            row["drift_noise_ratio"],
            s=row["bubble_size"],
            color=color,
            alpha=0.85,
            edgecolor="white",
            linewidth=1.5,
            zorder=3,
        )
        ax.text(
            row["smooth_efficiency_50"] + 0.02,
            row["drift_noise_ratio"] + 0.03,
            f"{pretty_product(row['product'])}\n{row['suggested_strategy']}",
            fontsize=10,
            color="#111827",
            va="bottom",
        )

    ax.text(0.03, 0.12, "flat fair value /\nmarket making", transform=ax.transAxes, color="#1F2937", fontsize=11)
    ax.text(0.64, 0.85, "strong drift /\ntrend-biased playbook", transform=ax.transAxes, color="#1F2937", fontsize=11)
    ax.set_title("Mid-only strategy map", loc="left", pad=14)
    ax.text(
        0,
        1.06,
        "x = directional efficiency of the smoothed mid · y = drift strength relative to residual noise",
        transform=ax.transAxes,
        fontsize=11,
        color="#4B5563",
    )
    ax.set_xlabel("smooth efficiency ratio (50-tick smoothed mid)")
    ax.set_ylabel("drift / residual-noise ratio")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    output_path = OUTPUT_DIR / "mid_only_strategy_map.png"
    save_figure(fig, output_path)


def save_metrics(metrics: pd.DataFrame) -> None:
    output_path = OUTPUT_DIR / "round_2_metrics_summary.csv"
    metrics.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")


def save_strategy_metrics(metrics: pd.DataFrame) -> None:
    strategy_columns = [
        "product",
        "day",
        "trend_per_10k_ts",
        "trend_r2",
        "smooth_efficiency_50",
        "rolling_efficiency_200_mean",
        "net_move_to_range",
        "drift_noise_ratio",
        "residual_std",
        "residual_half_life",
        "residual_cross_rate",
        "rolling_zscore_100_abs_p95",
        "raw_variance_ratio_20",
        "suggested_strategy",
        "strategy_playbook",
    ]
    output_path = OUTPUT_DIR / "round_2_strategy_metrics.csv"
    metrics[strategy_columns].to_csv(output_path, index=False)
    print(f"Saved: {output_path}")


def save_takeaways(metrics: pd.DataFrame, prices: pd.DataFrame) -> None:
    overall = metrics[metrics["day"] == "ALL"].set_index("product")
    daily = metrics[metrics["day"] != "ALL"].copy()
    ash = overall.loc["ASH_COATED_OSMIUM"]
    pepper = overall.loc["INTARIAN_PEPPER_ROOT"]
    ash_daily = daily[daily["product"] == "ASH_COATED_OSMIUM"]
    pepper_daily = daily[daily["product"] == "INTARIAN_PEPPER_ROOT"]
    pepper_avg_daily_move = float((pepper_daily["end_mid"] - pepper_daily["start_mid"]).mean())

    return_correlation = (
        prices.pivot_table(index=["day", "timestamp"], columns="product", values="mid_change_1")
        .corr()
        .iloc[0, 1]
    )

    lines = [
        "# Round 2 market takeaways",
        "",
        "## Cleaning note",
        "- Rows where both `bid_price_1` and `ask_price_1` were missing had `mid_price = 0.0`; those were treated as missing values before plotting or computing metrics.",
        "",
        "## Key observations",
        f"- **{pretty_product('ASH_COATED_OSMIUM')}** behaves like a stable anchor around **{ash['mid_mean']:.1f}**, with average spread **{ash['avg_spread']:.1f} ticks** (**{ash['avg_spread_bps']:.1f} bps**) and almost no directional drift (**{ash['trend_per_10k_ts']:.2f} price units per 10k timestamps**).",
        f"- **{pretty_product('INTARIAN_PEPPER_ROOT')}** trends hard intraday, climbing roughly **{pepper['trend_per_10k_ts']:.1f} price units per 10k timestamps**, which works out to about **{pepper_avg_daily_move:.1f} points per day** on average.",
        f"- Top-of-book imbalance is a REAL signal in both assets. Correlation with the next **{FUTURE_HORIZON}**-tick mid move is **{ash[f'imbalance_future_{FUTURE_HORIZON}_corr']:.3f}** for Ash Coated Osmium and **{pepper[f'imbalance_future_{FUTURE_HORIZON}_corr']:.3f}** for Intarian Pepper Root.",
        f"- Cross-asset return correlation is basically zero (**{return_correlation:.3f}**), so the two products look structurally different enough to model separately and diversify inventory risk.",
        "",
        "## Mid-only regime diagnostics",
        f"- **{pretty_product('ASH_COATED_OSMIUM')}**: `trend R² = {ash['trend_r2']:.3f}`, `smooth eff50 = {ash['smooth_efficiency_50']:.3f}`, `drift/noise = {ash['drift_noise_ratio']:.3f}`, `residual half-life = {ash['residual_half_life']:.2f}`. Eso grita **{ash['suggested_strategy']}**.",
        f"- **{pretty_product('INTARIAN_PEPPER_ROOT')}**: `trend R² = {pepper['trend_r2']:.3f}`, `smooth eff50 = {pepper['smooth_efficiency_50']:.3f}`, `drift/noise = {pepper['drift_noise_ratio']:.3f}`, `residual half-life = {pepper['residual_half_life']:.2f}`. Acá el mejor encuadre es **{pepper['suggested_strategy']}**.",
        f"- Ojo: los dos assets tienen lag-1 autocorrelation de cambios de mid cerca de **{ash['lag1_mid_change_autocorr']:.2f}** y **{pepper['lag1_mid_change_autocorr']:.2f}**. Eso significa que a micro-escala hay rebote de microestructura, incluso cuando el asset grande viene en tendencia.",
        "",
        "## How to use this",
        f"- **{pretty_product('ASH_COATED_OSMIUM')}** → {ash['strategy_playbook']}",
        f"- **{pretty_product('INTARIAN_PEPPER_ROOT')}** → {pepper['strategy_playbook']}",
        "- Traducido a ejecución: no uses el mismo fair value para ambos. Uno necesita ancla casi fija; el otro necesita ancla móvil y sesgo de inventario a favor del drift.",
    ]

    output_path = OUTPUT_DIR / "round_2_takeaways.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {output_path}")


def save_strategy_playbook(metrics: pd.DataFrame) -> None:
    strategy_df = metrics[metrics["day"] == "ALL"].copy().set_index("product")
    lines = [
        "# Round 2 strategy playbook (mid-only)",
        "",
        "## Metrics used",
        "- **trend R²**: cuánto de la trayectoria del mid se explica con una recta. Cerca de 1 = deriva limpia; cerca de 0 = más estacionario/choppy.",
        "- **smooth eff50**: eficiencia direccional del mid suavizado a 50 ticks. Cerca de 0 = ida y vuelta; cerca de 1 = movimiento limpio y tendencial.",
        "- **drift / residual-noise**: drift por 10k timestamps dividido por el ruido alrededor de la tendencia. Alto = conviene respetar la deriva.",
        "- **residual half-life**: velocidad con la que el precio vuelve hacia su tendencia local. Bajo = pullbacks cortos y operables.",
        "",
        "## Asset playbooks",
    ]

    for product, row in strategy_df.iterrows():
        lines.extend(
            [
                f"### {pretty_product(product)}",
                f"- Strategy: **{row['suggested_strategy']}**",
                f"- Why: trend R² **{row['trend_r2']:.3f}**, smooth eff50 **{row['smooth_efficiency_50']:.3f}**, drift/noise **{row['drift_noise_ratio']:.3f}**, residual half-life **{row['residual_half_life']:.2f}**.",
                f"- Playbook: {row['strategy_playbook']}",
                "",
            ]
        )

    output_path = OUTPUT_DIR / "round_2_strategy_playbook.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {output_path}")


def main() -> None:
    configure_style()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prices, step = load_prices()
    official_prices, official_days = load_official_test_prices(step)
    trades = load_trades(step)
    metrics = compute_metrics(prices, trades)

    for product in sorted(prices["product"].unique()):
        plot_mid_price(prices, product, step)
        plot_mid_bid_ask(prices, trades, product, step)
        plot_mid_only_small_multiples(prices, product)
        plot_mid_only_regime_dashboard(prices, metrics, product, step)
        plot_behavior_dashboard(prices, trades, product)
        plot_product_train_vs_official_test_comparison(prices, official_prices, official_days, product, step)
        plot_product_train_vs_official_test_envelope(prices, official_prices, official_days, product)
        if product in DIAGNOSTIC_PRODUCTS:
            plot_product_session_gap_diagnostic(prices, official_prices, official_days, product)
            plot_product_anchor_shift_dashboard(prices, official_prices, official_days, product)

    plot_train_vs_official_test_mid(prices, official_prices, official_days, step)
    plot_cross_asset_comparison(prices, metrics, step)
    plot_mid_only_strategy_map(metrics)
    save_metrics(metrics)
    save_strategy_metrics(metrics)
    save_takeaways(metrics, prices)
    save_strategy_playbook(metrics)


if __name__ == "__main__":
    main()
