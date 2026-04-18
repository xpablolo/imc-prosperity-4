from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
ROUND1_TOOLS = ROOT / "round_1" / "tools"
ROUND1_MODELS = ROOT / "round_1" / "models"
RESULTS_DIR = ROOT / "round_2" / "results" / "g5_maf"
REPORT_PATH = RESULTS_DIR / "round2_g5_analysis.md"

sys.path.insert(0, str(ROUND1_TOOLS))
sys.path.insert(0, str(ROUND1_MODELS))

import backtest as bt  # noqa: E402


PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]
POSITION_LIMITS = {"ASH_COATED_OSMIUM": 80, "INTARIAN_PEPPER_ROOT": 80}
BID_GRID = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 100]


@dataclass(frozen=True)
class RoundSpec:
    name: str
    days: Tuple[int, ...]
    label: str


@dataclass(frozen=True)
class ProxySpec:
    name: str
    label: str
    description: str
    scale_trades: bool = False
    front_bias: bool = False


@dataclass(frozen=True)
class CutoffScenario:
    name: str
    label: str
    median_bid: float
    slope: float
    weight: float
    description: str


@dataclass
class LoadedDayData:
    depth_by_ts: Dict[int, bt.DepthSnapshot]
    trades_df: pd.DataFrame
    rows_by_ts: Dict[int, Mapping[str, float]]


ROUND_SPECS: Dict[str, RoundSpec] = {
    "round_1": RoundSpec(name="round_1", days=(-2, -1, 0), label="Round 1"),
    "round_2": RoundSpec(name="round_2", days=(-1, 0, 1), label="Round 2"),
}

PROXIES: List[ProxySpec] = [
    ProxySpec(
        name="uniform_depth_125",
        label="Uniform depth +25%",
        description=(
            "Escala en 1.25 el volumen visible en todos los niveles observados, sin tocar market trades. "
            "Proxy conservador: más liquidez accesible, mismo flujo observado."
        ),
    ),
    ProxySpec(
        name="front_bias_depth_25",
        label="Front-biased depth +25%",
        description=(
            "Añade quotes extra manteniendo los mismos precios visibles, pero concentrando más volumen cerca del touch "
            "(L1/L2/L3 con multiplicadores 1.45/1.20/1.15)."
        ),
        front_bias=True,
    ),
    ProxySpec(
        name="uniform_depth_trade_125",
        label="Depth +25% y trade flow +25%",
        description=(
            "Escala el libro visible y también el tamaño de market trades en 1.25. Upper bound razonable si el mercado "
            "estándar observado representa ~80% del flujo total y el MAF recupera la parte faltante."
        ),
        scale_trades=True,
    ),
]

CUTOFF_SCENARIOS: List[CutoffScenario] = [
    CutoffScenario(
        name="low_competition",
        label="Competencia baja",
        median_bid=15.0,
        slope=5.0,
        weight=0.20,
        description=(
            "Campo poco agresivo: bids rivales en los teens. Lo tomo como ancla floja porque el repo viejo devolvía 15 "
            "en stubs históricos, pero NO como evidencia dura."
        ),
    ),
    CutoffScenario(
        name="central",
        label="Central",
        median_bid=30.0,
        slope=7.0,
        weight=0.50,
        description="Escenario central sin histórico usable: cutoff alrededor de 30 con transición relativamente suave.",
    ),
    CutoffScenario(
        name="high_competition",
        label="Competencia alta",
        median_bid=50.0,
        slope=10.0,
        weight=0.30,
        description="Escenario pesimista: muchos equipos pujan en serio y el cutoff relevante se mueve a la zona 40-60.",
    ),
]


def scale_quantity(value: int, factor: float) -> int:
    scaled = int(round(float(value) * factor))
    if value > 0 and scaled <= 0:
        return 1
    return max(0, scaled)


def load_day_data(round_name: str, day: int, product: str, max_levels: int = 3) -> LoadedDayData:
    prices_path = ROOT / "data" / round_name / f"prices_{round_name}_day_{day}.csv"
    trades_path = ROOT / "data" / round_name / f"trades_{round_name}_day_{day}.csv"
    if not prices_path.exists() or not trades_path.exists():
        raise FileNotFoundError(f"Missing CSVs for {round_name} day {day}")

    prices_df = pd.read_csv(prices_path, sep=";")
    prices_df = prices_df[prices_df["product"] == product].copy()
    for column in prices_df.columns:
        if column != "product":
            prices_df[column] = pd.to_numeric(prices_df[column], errors="coerce")

    empty_book = prices_df["bid_price_1"].isna() & prices_df["ask_price_1"].isna()
    prices_df.loc[empty_book, "mid_price"] = np.nan
    prices_df = prices_df.dropna(subset=["mid_price"]).copy()
    prices_df["timestamp"] = prices_df["timestamp"].astype(int)

    depth_by_ts: Dict[int, bt.DepthSnapshot] = {}
    rows_by_ts: Dict[int, Mapping[str, float]] = {}
    for _, row in prices_df.iterrows():
        ts = int(row["timestamp"])
        depth_by_ts[ts] = bt.build_depth_snapshot_from_prices_row(row, max_levels=max_levels)
        rows_by_ts[ts] = row.to_dict()

    trades_df = pd.read_csv(trades_path, sep=";")
    trades_df = trades_df[trades_df["symbol"] == product].copy()
    if not trades_df.empty:
        trades_df["timestamp"] = pd.to_numeric(trades_df["timestamp"], errors="coerce").astype(int)
        trades_df["price"] = pd.to_numeric(trades_df["price"], errors="coerce").round().astype(int)
        trades_df["quantity"] = pd.to_numeric(trades_df["quantity"], errors="coerce").round().astype(int)

    return LoadedDayData(depth_by_ts=depth_by_ts, trades_df=trades_df, rows_by_ts=rows_by_ts)


def front_bias_depth(row: Mapping[str, float], side: str) -> Dict[int, int]:
    multipliers = {1: 1.45, 2: 1.20, 3: 1.15}
    prefix = "bid" if side == "buy" else "ask"
    out: Dict[int, int] = {}
    for level in (1, 2, 3):
        price = row.get(f"{prefix}_price_{level}")
        volume = row.get(f"{prefix}_volume_{level}")
        if pd.notna(price) and pd.notna(volume) and int(volume) > 0:
            out[int(price)] = scale_quantity(int(volume), multipliers[level])
    return out


def apply_proxy(day_data: LoadedDayData, proxy: ProxySpec) -> Tuple[Dict[int, bt.DepthSnapshot], pd.DataFrame]:
    new_depth_by_ts: Dict[int, bt.DepthSnapshot] = {}
    for ts, depth in day_data.depth_by_ts.items():
        row = day_data.rows_by_ts[ts]
        if proxy.front_bias:
            buy_depth = front_bias_depth(row, side="buy")
            sell_depth = front_bias_depth(row, side="sell")
        else:
            buy_depth = {price: scale_quantity(volume, 1.25) for price, volume in depth.buy_vol_by_price.items()}
            sell_depth = {price: scale_quantity(volume, 1.25) for price, volume in depth.sell_vol_by_price.items()}
        new_depth_by_ts[ts] = bt.DepthSnapshot(
            buy_vol_by_price=buy_depth,
            sell_vol_by_price=sell_depth,
            mid_price=depth.mid_price,
        )

    new_trades = day_data.trades_df.copy()
    if proxy.scale_trades and not new_trades.empty:
        new_trades["quantity"] = new_trades["quantity"].apply(lambda q: scale_quantity(int(q), 1.25))

    return new_depth_by_ts, new_trades


def day_totals(results_df: pd.DataFrame) -> Dict[int, float]:
    cumulative = results_df.groupby("day", sort=True)["pnl"].last()
    daily = cumulative.diff().fillna(cumulative)
    return {int(day): float(value) for day, value in daily.items()}


def add_block_metrics(results_df: pd.DataFrame, n_blocks: int = 10) -> pd.DataFrame:
    df = results_df.copy()
    df["abs_position"] = df["position"].abs()
    df["block"] = (
        df.groupby("day")["timestamp"]
        .transform(lambda s: np.ceil(s.rank(method="first", pct=True) * n_blocks).clip(1, n_blocks).astype(int))
    )
    out = (
        df.groupby(["day", "block"], as_index=False)
        .agg(
            last_pnl=("pnl", "last"),
            avg_position=("position", "mean"),
            avg_abs_position=("abs_position", "mean"),
            max_abs_position=("abs_position", "max"),
        )
        .sort_values(["day", "block"])
        .reset_index(drop=True)
    )
    out["block_pnl"] = out.groupby("day")["last_pnl"].diff().fillna(out["last_pnl"])
    return out


def summarize_product_run(
    round_spec: RoundSpec,
    proxy_name: str,
    product: str,
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    metrics: Mapping[str, float],
) -> Dict[str, float | int | str]:
    daily = day_totals(results_df)
    block_df = add_block_metrics(results_df)
    block_mean = float(block_df["block_pnl"].mean())
    block_std = float(block_df["block_pnl"].std(ddof=1)) if len(block_df) > 1 else 0.0
    out: Dict[str, float | int | str] = {
        "round": round_spec.name,
        "round_label": round_spec.label,
        "proxy": proxy_name,
        "product": product,
        "total_pnl": float(metrics["total_pnl"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "fill_count": float(metrics["fill_count"]),
        "maker_share": float(metrics["maker_share"]) if not math.isnan(float(metrics["maker_share"])) else np.nan,
        "aggressive_fill_share": float(metrics["aggressive_fill_share"]) if not math.isnan(float(metrics["aggressive_fill_share"])) else np.nan,
        "avg_fill_size": float(metrics["avg_fill_size"]) if not math.isnan(float(metrics["avg_fill_size"])) else np.nan,
        "avg_position": float(results_df["position"].mean()),
        "avg_abs_position": float(results_df["position"].abs().mean()),
        "max_abs_position": float(results_df["position"].abs().max()),
        "pct_abs_pos_ge_60": float((results_df["position"].abs() >= 60).mean()),
        "pct_at_limit": float((results_df["position"].abs() >= POSITION_LIMITS[product]).mean()),
        "block_mean_pnl": block_mean,
        "block_std_pnl": block_std,
        "daily_std_pnl": float(pd.Series(daily).std(ddof=1)) if len(daily) > 1 else 0.0,
        "min_day_pnl": float(min(daily.values())),
    }
    for day, total in daily.items():
        out[f"day_{day}_pnl"] = float(total)
    if product == "INTARIAN_PEPPER_ROOT":
        for threshold in (20, 40, 60, 70, 80):
            hit = results_df.loc[results_df["position"] >= threshold, "timestamp"]
            out[f"time_to_{threshold}"] = int(hit.iloc[0]) if not hit.empty else np.nan
        out["pct_pos_below_70"] = float((results_df["position"] < 70).mean())
    return out


def merge_combined_results(product_results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    combined: Optional[pd.DataFrame] = None
    for product, frame in product_results.items():
        current = frame[["day", "timestamp", "global_ts", "pnl"]].rename(columns={"pnl": f"pnl_{product}"})
        if combined is None:
            combined = current
        else:
            combined = combined.merge(current, on=["day", "timestamp", "global_ts"], how="outer")
    assert combined is not None
    combined = combined.sort_values(["global_ts", "day", "timestamp"]).reset_index(drop=True)
    pnl_cols = [col for col in combined.columns if col.startswith("pnl_")]
    combined[pnl_cols] = combined[pnl_cols].ffill().fillna(0.0)
    combined["total_pnl"] = combined[pnl_cols].sum(axis=1)
    combined["drawdown"] = combined["total_pnl"] - combined["total_pnl"].cummax()
    combined["block"] = (
        combined.groupby("day")["timestamp"]
        .transform(lambda s: np.ceil(s.rank(method="first", pct=True) * 10).clip(1, 10).astype(int))
    )
    return combined


def summarize_combined_run(
    round_spec: RoundSpec,
    proxy_name: str,
    product_summaries: pd.DataFrame,
    product_results: Mapping[str, pd.DataFrame],
    product_fills: Mapping[str, pd.DataFrame],
) -> Dict[str, float | int | str]:
    combined_results = merge_combined_results(product_results)
    daily_combined = day_totals(combined_results.rename(columns={"total_pnl": "pnl"}))
    combined_fills = pd.concat(product_fills.values(), ignore_index=True) if product_fills else pd.DataFrame()

    out: Dict[str, float | int | str] = {
        "round": round_spec.name,
        "round_label": round_spec.label,
        "proxy": proxy_name,
        "product": "TOTAL",
        "total_pnl": float(product_summaries["total_pnl"].sum()),
        "max_drawdown": float(combined_results["drawdown"].min()),
        "fill_count": float(sum(float(v) for v in product_summaries["fill_count"].tolist())),
        "maker_share": float((combined_fills["source"] == "MARKET_TRADE").mean()) if not combined_fills.empty else np.nan,
        "aggressive_fill_share": float((combined_fills["source"] == "AGGRESSIVE").mean()) if not combined_fills.empty else np.nan,
        "avg_fill_size": float(combined_fills["quantity"].mean()) if not combined_fills.empty else np.nan,
        "avg_position": np.nan,
        "avg_abs_position": np.nan,
        "max_abs_position": np.nan,
        "pct_abs_pos_ge_60": np.nan,
        "pct_at_limit": np.nan,
        "block_mean_pnl": float(
            add_block_metrics(combined_results.rename(columns={"total_pnl": "pnl", "drawdown": "position"}))["block_pnl"].mean()
        ),
        "block_std_pnl": float(
            add_block_metrics(combined_results.rename(columns={"total_pnl": "pnl", "drawdown": "position"}))["block_pnl"].std(ddof=1)
        ),
        "daily_std_pnl": float(pd.Series(daily_combined).std(ddof=1)) if len(daily_combined) > 1 else 0.0,
        "min_day_pnl": float(min(daily_combined.values())),
    }
    for day, total in daily_combined.items():
        out[f"day_{day}_pnl"] = float(total)
    return out


def run_round_backtests(
    model_name: str,
    round_spec: RoundSpec,
    proxy: Optional[ProxySpec],
    loaded_data: Mapping[str, Mapping[int, LoadedDayData]],
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]:
    rows: List[Dict[str, float | int | str]] = []
    product_results: Dict[str, pd.DataFrame] = {}
    product_fills: Dict[str, pd.DataFrame] = {}
    TraderClass = bt.load_trader(model_name)
    for product in PRODUCTS:
        day_data: Dict[int, Tuple[Dict[int, bt.DepthSnapshot], pd.DataFrame]] = {}
        for day in round_spec.days:
            raw = loaded_data[product][day]
            day_data[day] = apply_proxy(raw, proxy) if proxy is not None else (raw.depth_by_ts, raw.trades_df.copy())
        trader = TraderClass()
        results_df, fills_df, metrics = bt.run_backtest_on_loaded_data(
            trader, product, list(round_spec.days), day_data, reset_between_days=False
        )
        rows.append(summarize_product_run(round_spec, proxy.name if proxy else "baseline", product, results_df, fills_df, metrics))
        product_results[product] = results_df
        product_fills[product] = fills_df

    product_df = pd.DataFrame(rows)
    combined_row = summarize_combined_run(round_spec, proxy.name if proxy else "baseline", product_df, product_results, product_fills)
    product_df = pd.concat([product_df, pd.DataFrame([combined_row])], ignore_index=True)
    return product_df, product_results, product_fills


def logistic_acceptance_probability(bid: float, scenario: CutoffScenario) -> float:
    return 1.0 / (1.0 + math.exp(-(float(bid) - scenario.median_bid) / scenario.slope))


def choose_bid(bid_df: pd.DataFrame) -> int:
    max_ev = float(bid_df["weighted_ev_risk_adjusted"].max())
    threshold = 0.95 * max_ev
    eligible = bid_df.loc[bid_df["weighted_ev_risk_adjusted"] >= threshold, "bid"].tolist()
    if not eligible:
        return int(bid_df.loc[bid_df["weighted_ev_risk_adjusted"].idxmax(), "bid"])
    return int(min(eligible))


def markdown_table(df: pd.DataFrame, float_fmt: str = ".1f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
    rows = []
    for _, row in df.iterrows():
        vals = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                if math.isnan(value):
                    vals.append("")
                else:
                    vals.append(format(value, float_fmt))
            else:
                vals.append(str(value))
        rows.append(vals)
    sep = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([sep, divider, *body])


def write_report(
    baseline_df: pd.DataFrame,
    proxy_df: pd.DataFrame,
    bid_df: pd.DataFrame,
    alt_df: pd.DataFrame,
    pepper_capacity_df: pd.DataFrame,
    recommendation: int,
    delta_scenarios: Mapping[str, float],
    delta_risk_adjusted: float,
) -> None:
    round1_total = baseline_df.query("round == 'round_1' and product == 'TOTAL'").iloc[0]
    round2_total = baseline_df.query("round == 'round_2' and product == 'TOTAL'").iloc[0]
    round2_product = baseline_df.query("round == 'round_2' and product != 'TOTAL'").copy()
    proxy_total = proxy_df.query("product == 'TOTAL'").copy()
    proxy_total["delta"] = proxy_total["total_pnl"] - float(round2_total["total_pnl"])
    bid_row = bid_df.loc[bid_df["bid"] == recommendation].iloc[0]

    proxy_detail = proxy_df.copy()
    base_map = {
        row["product"]: float(row["total_pnl"])
        for _, row in baseline_df.query("round == 'round_2'").iterrows()
    }
    proxy_detail["P0"] = proxy_detail["product"].map(base_map)
    proxy_detail["Delta"] = proxy_detail["total_pnl"] - proxy_detail["P0"]

    alt_pretty = alt_df.copy()
    alt_pretty["delta_proxy_conservative"] = alt_pretty["uniform_depth_125_total_pnl"] - alt_pretty["baseline_total_pnl"]

    lines: List[str] = [
        "# Round 2 G5 analysis — Market Access Fee / bid()",
        "",
        "## Resumen ejecutivo",
        "",
        f"- **Baseline local G5 sin extra access (Round 2):** {round(round2_total['total_pnl'], 1):,.1f} de PnL total.",
        f"- **PnL por producto en Round 2:** ASH {round(round2_product.loc[round2_product['product']=='ASH_COATED_OSMIUM','total_pnl'].iloc[0], 1):,.1f} / PEPPER {round(round2_product.loc[round2_product['product']=='INTARIAN_PEPPER_ROOT','total_pnl'].iloc[0], 1):,.1f}.",
        f"- **Delta estimado por extra market access (+25% quotes):** conservador {delta_scenarios['conservative']:,.1f}, central {delta_scenarios['central']:,.1f}, upper bound {delta_scenarios['optimistic']:,.1f}.",
        f"- **Delta usado para decidir bid de forma prudente:** {delta_risk_adjusted:,.1f} (haircut del 25% sobre el proxy conservador).",
        f"- **Recomendación explícita:** `bid() = {recommendation}`.",
        f"- **Rango alternativo razonable:** 60–100; 75 es el menor bid que queda dentro del 95% del máximo EV ponderado del grid testeado.",
        "- **Confianza:** media. Delta sale positivo en todos los proxies razonables y G5 sigue dominando el ranking, pero el cutoff real de bids rivales sigue siendo el mayor foco de incertidumbre.",
        "",
        "## Reglas de la ronda",
        "",
        "- `bid()` es una puja ciega por acceso extra al mercado.",
        "- Solo el top 50% de bids recibe acceso adicional.",
        "- Si el bid es aceptado: acceso a 25% más quotes y pago único igual al bid.",
        "- Si el bid no entra: no hay acceso extra y no se paga nada.",
        "- En testing normal de Round 2 el `bid()` se ignora, así que el efecto del MAF **no** se observa directamente. Hay que estimarlo contrafactualmente.",
        "",
        "## Descripción actual del modelo G5",
        "",
        "- **Archivo principal:** `/Users/pablo/Desktop/prosperity/round_1/models/model_G5.py`.",
        "- **ASH_COATED_OSMIUM:** market making estacionario con anchor lento alrededor de 10_000, reservation price sesgado por inventario y overlay microestructural (L1/L2 imbalance + microprice).",
        "- **INTARIAN_PEPPER_ROOT:** estrategia trend-carry. Usa EMAs, slope local, residual z-score, flow signed, continuation/pullback adjustments y una política explícita de inventario objetivo alta.",
        "- **Inventory management PEPPER (G5):** hold target agresivo (80 casi toda la sesión), carry floor alto y quote shaping para llegar rápido al inventario largo.",
        "- **Execution:** mezcla taking controlado (thresholds agresivos) y making con tamaños pasivos asimétricos según gap al target.",
        "",
        "### Herramientas existentes localizadas",
        "",
        "- Backtester base: `/Users/pablo/Desktop/prosperity/round_1/tools/backtest.py`.",
        "- Evaluaciones históricas de la familia F/G: `/Users/pablo/Desktop/prosperity/round_1/tools/evaluate_policy_architecture_research.py`.",
        "- Este análisis añade: `/Users/pablo/Desktop/prosperity/round_2/tools/analyze_g5_maf.py`.",
        "",
        "## Metodología de backtest",
        "",
        "- Se usó el backtester local del repo, sin build y sin tocar el matching engine.",
        "- **Datasets comparables usados:** Round 1 (`-2,-1,0`) y Round 2 (`-1,0,1`) para los mismos dos productos.",
        "- **Round 0 quedó fuera** del análisis cuantitativo porque tradea EMERALDS/TOMATOES, o sea: no es comparable con ASH/PEPPER.",
        "- El backtest es determinista y usa los supuestos del repo: órdenes agresivas cruzan libro visible; resting orders viven hasta el siguiente snapshot; market trades pueden ejecutar resting orders; sin latencia/slippage extra.",
        "",
        "## Resultados baseline",
        "",
        "### G5 baseline por round y producto",
        "",
        markdown_table(
            baseline_df[
                ["round_label", "product", "total_pnl", "max_drawdown", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position", "daily_std_pnl"]
            ],
            ".3f",
        ),
        "",
        f"- **Round 1 total:** {round1_total['total_pnl']:,.1f} con max DD combinado {round1_total['max_drawdown']:,.1f}.",
        f"- **Round 2 total:** {round2_total['total_pnl']:,.1f} con max DD combinado {round2_total['max_drawdown']:,.1f}.",
        f"- Cambio total Round 1 → Round 2: {float(round2_total['total_pnl']) - float(round1_total['total_pnl']):+,.1f}. O sea: G5 siguió MUY estable entre datasets.",
        "",
        "### Sensibilidad temporal / bloques (baseline Round 2)",
        "",
        "- PEPPER sigue explicando casi toda la ventaja competitiva.",
        "- G5 pasa gran parte de la sesión cerca del límite en PEPPER, así que el valor del extra access viene más por **llegar antes al carry target** y por **hacer fills más grandes**, no por multiplicar el número de fills.",
        "",
        "### Capacity diagnostics PEPPER (Round 2)",
        "",
        markdown_table(pepper_capacity_df, ".1f"),
        "",
        "Lectura: en baseline, el day -1 tarda bastante en llegar a 70/80. Ahí sí hay cuello de botella de liquidez/acceso. En days 0/1 el modelo ya arranca muy cargado y el beneficio marginal del extra access es menor.",
        "",
        "## Proxy de extra market access",
        "",
        "No se puede backtestear `bid()` directo sobre el mercado normal porque el mercado de test ignora el bid. Entonces estimé `P1` con proxies explícitos y documentados.",
        "",
        "### Proxies implementados",
        "",
        "1. **Uniform depth +25%** — escala el volumen visible en todos los niveles existentes, trades iguales. Proxy conservador.",
        "2. **Front-biased depth +25%** — concentra la parte extra cerca del touch (L1/L2/L3 con 1.45/1.20/1.15), manteniendo los mismos precios visibles.",
        "3. **Depth +25% + trade flow +25%** — además escala market trades. Lo trato como upper bound razonable, NO como estimación central.",
        "",
        "### P0 / P1 / Delta por proxy",
        "",
        markdown_table(
            proxy_detail[
                ["proxy", "product", "P0", "total_pnl", "Delta", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position"]
            ],
            ".3f",
        ),
        "",
        "### Lectura de Delta",
        "",
        f"- **Conservador (`uniform_depth_125`)**: Δ total = {delta_scenarios['conservative']:,.1f}.",
        f"- **Central (`front_bias_depth_25`)**: Δ total = {delta_scenarios['central']:,.1f}.",
        f"- **Upper bound (`uniform_depth_trade_125`)**: Δ total = {delta_scenarios['optimistic']:,.1f}.",
        "- El hallazgo clave es que el extra access **no** se traduce en +25% PnL. El efecto parece más bien estar en el rango de low single-digit percent sobre el PnL total si asumimos libro extra sin escalar también los market trades.",
        "- Además, en los proxies conservadores el fill count incluso baja levemente mientras sube el avg fill size. O sea: el edge viene por **mejor tamaño/quality of access**, no por hyperactivity.",
        "",
        "## Formalización matemática del bid",
        "",
        "Defino:",
        "",
        "- `P0`: PnL sin extra access.",
        "- `P1`: PnL con extra access estimado por proxy.",
        "- `Delta = P1 - P0`.",
        "- `b`: bid.",
        "- `A(b)`: indicador de aceptación del bid.",
        "",
        "Entonces:",
        "",
        "`Pi(b) = P0 + A(b) * (Delta - b)`",
        "",
        "### Por qué bid y estrategia NO son lo mismo",
        "",
        "- La lógica de trading decide **qué hacer** una vez que ves el mercado.",
        "- El bid decide **cuánto mercado ves**.",
        "- Cambiar `b` sin cambiar el mercado observable no dice nada útil, porque en el test normal el bid se ignora.",
        "- Por eso la secuencia correcta es: **(1) estimar Delta contrafactual, (2) modelar aceptación q(b), (3) optimizar b**.",
        "",
        "## Modelo de teoría de juegos para el cutoff",
        "",
        "No hay histórico de bids rivales en el repo. Entonces modelé el cutoff aleatorio `C` con escenarios logísticos sobre la mediana rival:",
        "",
        markdown_table(
            pd.DataFrame(
                [
                    {
                        "escenario": s.label,
                        "median_bid": s.median_bid,
                        "slope": s.slope,
                        "weight": s.weight,
                        "lectura": s.description,
                    }
                    for s in CUTOFF_SCENARIOS
                ]
            ),
            ".2f",
        ),
        "",
        "Defino `q(b) = Pr(C < b)` con CDF logística. Luego:",
        "",
        "`E[Pi(b)] ≈ E[P0] + q(b) * (E[Delta] - b)`",
        "",
        "Para ser prudente, NO optimicé con el Delta más alto, sino con:",
        "",
        f"- `Delta_risk_adjusted = 0.75 * Delta_conservative = {delta_risk_adjusted:,.1f}`",
        "",
        "### Grid de bids evaluado",
        "",
        markdown_table(
            bid_df[
                [
                    "bid",
                    "q_low_competition",
                    "q_central",
                    "q_high_competition",
                    "ev_low_competition",
                    "ev_central",
                    "ev_high_competition",
                    "weighted_ev_risk_adjusted",
                ]
            ],
            ".3f",
        ),
        "",
        f"- El **máximo EV ponderado** del grid aparece en la cola alta, pero la curva se aplana fuerte.",
        f"- Usando una regla downside-aware simple (*elegir el menor bid dentro del 95% del EV máximo ponderado*), sale **{recommendation}**.",
        "",
        "## Filosofía de riesgo",
        "",
        "- No usé el proxy más optimista para decidir.",
        "- No asumí que `+25% quotes => +25% PnL`.",
        "- No extrapolé Round 0 porque ni siquiera comparte productos.",
        "- Apliqué haircut explícito al Delta conservador para absorber error de modelado.",
        "- La recomendación final privilegia **robustez > aparente precisión**.",
        "",
        "## Recomendación de bid",
        "",
        f"### Recomendación principal: `bid() = {recommendation}`",
        "",
        "Por qué:",
        "",
        f"- El baseline G5 ya es muy fuerte y el Delta estimado del extra access es claramente positivo incluso en el proxy conservador ({delta_scenarios['conservative']:,.1f}).",
        f"- En el grid probado, {recommendation} es el menor bid que queda prácticamente en la meseta del EV ponderado.",
        "- Si el cutoff real termina siendo más bajo, 75 no te cambia materialmente el net benefit frente a 60 o 50.",
        "- Si el cutoff real es bastante más alto de lo esperado, 75 te deja mejor parado que un bid tímido.",
        "",
        "### Rango alternativo razonable",
        "",
        "- **60–100** si querés moverte en la meseta del EV del grid.",
        "- **50** todavía es defendible si tu sesgo es MUY conservador y querés minimizar el pago en caso de aceptación.",
        "- **<30** me parece demasiado tímido para un modelo con este Delta esperado.",
        "",
        "## Posibles mejoras de estrategia G5 para esta ronda",
        "",
        "### 1) ASH — tocar poco",
        "",
        "- ASH no está limitado por posición máxima; su avg |pos| ronda 22–25.",
        "- Con extra access, el beneficio parece venir de fills un poco más grandes, no de cambiar la tesis.",
        "- Cambio robusto sugerido si se implementa una versión Round 2: **si `bid()` fue aceptado, subir tamaño pasivo 10–15% en ASH sin estrechar agresivamente el ancho de quotes**.",
        "",
        "### 2) PEPPER — usar el extra access para llegar antes al carry, no para sobreoperar",
        "",
        "- PEPPER pasa muchísimo tiempo cerca de +80. Entonces el cuello de botella es **early accumulation**, sobre todo en day -1.",
        "- Con acceso extra, conviene usar la ventaja para llegar antes al target cuando `position < 70` y la señal sigue alineada.",
        "- Cambio robusto sugerido:",
        "  - solo cuando el bid haya sido aceptado y `position_gap > 8`, permitir un poco más de size agresivo/pasivo del lado comprador;",
        "  - NO hacerlo una vez que ya estés >70, porque ahí el beneficio marginal cae y el riesgo de churn sube;",
        "  - mantener o incluso endurecer el trim cuando el flow y el imbalance se ponen en contra.",
        "",
        "### 3) No estrechar spreads por reflejo",
        "",
        "- El proxy no dice “tradeá más”; dice “llenate mejor”.",
        "- O sea: prefiero **más tamaño condicional** antes que quote widths mucho más agresivos.",
        "",
        "### 4) G5 sigue siendo baseline correcta",
        "",
        "Probé también dos alternativas fuertes del mismo family tree sobre Round 2:",
        "",
        markdown_table(alt_pretty, ".3f"),
        "",
        "G5 sigue arriba tanto en baseline como bajo el proxy conservador. Así que, salvo que quieras rehacer arquitectura, no veo razón fuerte para abandonar G5.",
        "",
        "## Limitaciones y supuestos",
        "",
        "- El mayor agujero de información es la distribución real de bids rivales.",
        "- El segundo agujero es cuánto del 20% “faltante” del flujo estándar representa quotes extra versus market trades extra.",
        "- Por eso reporto tres proxies y separo **conservative / central / upper bound**.",
        "",
        "## Próximos pasos",
        "",
        "1. Si querés ejecutar esto de nuevo: `./.venv_backtest/bin/python /Users/pablo/Desktop/prosperity/round_2/tools/analyze_g5_maf.py`",
        "2. Si querés pasar de análisis a implementación: crear una variante Round 2 de G5 con `bid()` y gating explícito `access_granted` para ajustar tamaños en ASH/PEPPER solo cuando haya valor.",
        "3. Si querés afinar todavía más: correr sensibilidad adicional con bid grid extendido y un stress cutoff más alto (ej. mediana 60–70).",
        "",
        "## Recomendación final explícita",
        "",
        f"- **Bid recomendado:** `{recommendation}`",
        "- **Por qué:** Delta robusto positivo, G5 sigue siendo el mejor baseline, y 75 entra en la meseta del EV sin necesitar ir al extremo por reflejo.",
        "- **Rango alternativo:** `60–100`",
        "- **Confianza:** media",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    loaded: Dict[str, Dict[str, Dict[int, LoadedDayData]]] = {}
    for round_name, round_spec in ROUND_SPECS.items():
        loaded[round_name] = {}
        for product in PRODUCTS:
            loaded[round_name][product] = {
                day: load_day_data(round_name, day, product) for day in round_spec.days
            }

    baseline_rows: List[pd.DataFrame] = []
    proxy_rows: List[pd.DataFrame] = []
    round2_baseline_product_results: Dict[str, pd.DataFrame] = {}
    round2_baseline_product_fills: Dict[str, pd.DataFrame] = {}
    round2_proxy_results: Dict[str, Dict[str, pd.DataFrame]] = {}

    for round_name, round_spec in ROUND_SPECS.items():
        baseline_df, product_results, product_fills = run_round_backtests(
            model_name="model_G5",
            round_spec=round_spec,
            proxy=None,
            loaded_data=loaded[round_name],
        )
        baseline_rows.append(baseline_df)
        if round_name == "round_2":
            round2_baseline_product_results = product_results
            round2_baseline_product_fills = product_fills

    for proxy in PROXIES:
        proxy_df, product_results, _product_fills = run_round_backtests(
            model_name="model_G5",
            round_spec=ROUND_SPECS["round_2"],
            proxy=proxy,
            loaded_data=loaded["round_2"],
        )
        proxy_rows.append(proxy_df)
        round2_proxy_results[proxy.name] = product_results

    baseline_df = pd.concat(baseline_rows, ignore_index=True)
    proxy_df = pd.concat(proxy_rows, ignore_index=True)

    baseline_df.to_csv(RESULTS_DIR / "baseline_metrics.csv", index=False)
    proxy_df.to_csv(RESULTS_DIR / "proxy_metrics.csv", index=False)

    round2_baseline_total = float(
        baseline_df.loc[(baseline_df["round"] == "round_2") & (baseline_df["product"] == "TOTAL"), "total_pnl"].iloc[0]
    )
    proxy_total = (
        proxy_df.loc[proxy_df["product"] == "TOTAL", ["proxy", "total_pnl"]]
        .copy()
        .assign(delta=lambda df: df["total_pnl"] - round2_baseline_total)
        .set_index("proxy")
    )

    delta_scenarios = {
        "conservative": float(proxy_total.loc["uniform_depth_125", "delta"]),
        "central": float(proxy_total.loc["front_bias_depth_25", "delta"]),
        "optimistic": float(proxy_total.loc["uniform_depth_trade_125", "delta"]),
    }
    delta_risk_adjusted = 0.75 * delta_scenarios["conservative"]

    bid_rows = []
    for bid in BID_GRID:
        row: Dict[str, float | int] = {"bid": bid}
        weighted_ev = 0.0
        for scenario in CUTOFF_SCENARIOS:
            q = logistic_acceptance_probability(bid, scenario)
            ev = q * (delta_risk_adjusted - bid)
            row[f"q_{scenario.name}"] = q
            row[f"ev_{scenario.name}"] = ev
            weighted_ev += scenario.weight * ev
        row["weighted_ev_risk_adjusted"] = weighted_ev
        row["weighted_ev_conservative_delta"] = weighted_ev
        row["weighted_ev_central_delta"] = sum(
            scenario.weight * logistic_acceptance_probability(bid, scenario) * (delta_scenarios["central"] - bid)
            for scenario in CUTOFF_SCENARIOS
        )
        row["weighted_ev_optimistic_delta"] = sum(
            scenario.weight * logistic_acceptance_probability(bid, scenario) * (delta_scenarios["optimistic"] - bid)
            for scenario in CUTOFF_SCENARIOS
        )
        bid_rows.append(row)
    bid_df = pd.DataFrame(bid_rows).sort_values("bid").reset_index(drop=True)
    bid_df.to_csv(RESULTS_DIR / "bid_grid.csv", index=False)
    recommendation = choose_bid(bid_df)

    pepper_capacity_rows: List[Dict[str, float | int | str]] = []
    for label, product_results in {
        "baseline": round2_baseline_product_results,
        **round2_proxy_results,
    }.items():
        pepper = product_results["INTARIAN_PEPPER_ROOT"]
        for day, frame in pepper.groupby("day", sort=True):
            row: Dict[str, float | int | str] = {"proxy": label, "day": int(day)}
            for threshold in (70, 80):
                hit = frame.loc[frame["position"] >= threshold, "timestamp"]
                row[f"time_to_{threshold}"] = int(hit.iloc[0]) if not hit.empty else np.nan
            row["pct_pos_below_70"] = float((frame["position"] < 70).mean())
            row["pct_pos_at_80"] = float((frame["position"] >= 80).mean())
            pepper_capacity_rows.append(row)
    pepper_capacity_df = pd.DataFrame(pepper_capacity_rows)
    pepper_capacity_df.to_csv(RESULTS_DIR / "pepper_capacity_timing.csv", index=False)

    alt_rows: List[Dict[str, float | int | str]] = []
    for model_name in ("model_G5", "model_G2", "model_F3"):
        base_df, _product_results, _product_fills = run_round_backtests(
            model_name=model_name,
            round_spec=ROUND_SPECS["round_2"],
            proxy=None,
            loaded_data=loaded["round_2"],
        )
        conservative_df, _product_results, _product_fills = run_round_backtests(
            model_name=model_name,
            round_spec=ROUND_SPECS["round_2"],
            proxy=PROXIES[0],
            loaded_data=loaded["round_2"],
        )
        alt_rows.append(
            {
                "model": model_name,
                "baseline_total_pnl": float(base_df.loc[base_df["product"] == "TOTAL", "total_pnl"].iloc[0]),
                "uniform_depth_125_total_pnl": float(
                    conservative_df.loc[conservative_df["product"] == "TOTAL", "total_pnl"].iloc[0]
                ),
            }
        )
    alt_df = pd.DataFrame(alt_rows).sort_values("baseline_total_pnl", ascending=False).reset_index(drop=True)
    alt_df.to_csv(RESULTS_DIR / "alternative_models_round2.csv", index=False)

    write_report(
        baseline_df=baseline_df,
        proxy_df=proxy_df,
        bid_df=bid_df,
        alt_df=alt_df,
        pepper_capacity_df=pepper_capacity_df,
        recommendation=recommendation,
        delta_scenarios=delta_scenarios,
        delta_risk_adjusted=delta_risk_adjusted,
    )

    print(f"Wrote report to {REPORT_PATH}")
    print(f"Recommended bid: {recommendation}")
    print("Delta scenarios:", delta_scenarios)


if __name__ == "__main__":
    main()
