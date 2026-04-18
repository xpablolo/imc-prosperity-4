from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "round_2" / "results" / "model_kiko"
REPORT_PATH = RESULTS_DIR / "model_kiko_analysis.md"

sys.path.insert(0, str(ROOT / "round_2" / "tools"))
sys.path.insert(0, str(ROOT / "round_2" / "models"))
sys.path.insert(0, str(ROOT / "round_1" / "tools"))
sys.path.insert(0, str(ROOT / "round_1" / "models"))

import analyze_g5_maf as ag  # noqa: E402
import backtest as bt  # noqa: E402


MODEL_PATHS = {
    "model_kiko": ROOT / "round_2" / "models" / "model_kiko.py",
    "model_G5": ROOT / "round_1" / "models" / "model_G5.py",
    "model_G2": ROOT / "round_1" / "models" / "model_G2.py",
    "model_F3": ROOT / "round_1" / "models" / "model_F3.py",
}

ROUND_SPECS = {
    "round_1": {"days": [-2, -1, 0], "label": "Round 1"},
    "round_2": {"days": [-1, 0, 1], "label": "Round 2"},
}


def markdown_table(df: pd.DataFrame, float_fmt: str = ".1f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
    rows: List[str] = []
    for _, row in df.iterrows():
        vals: List[str] = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                if math.isnan(value):
                    vals.append("")
                else:
                    vals.append(format(value, float_fmt))
            else:
                vals.append(str(value))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *rows,
        ]
    )


def load_trader_class(model_name: str):
    path = MODEL_PATHS[model_name]
    spec = importlib.util.spec_from_file_location(model_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.Trader


def load_cache():
    cache: Dict[str, Dict[str, Dict[int, Tuple[dict, pd.DataFrame]]]] = {}
    for round_name, spec in ROUND_SPECS.items():
        cache[round_name] = {}
        for product in ag.PRODUCTS:
            cache[round_name][product] = {}
            for day in spec["days"]:
                loaded = ag.load_day_data(round_name, day, product)
                cache[round_name][product][day] = (loaded.depth_by_ts, loaded.trades_df)
    return cache


def run_model(model_name: str, cache) -> pd.DataFrame:
    Trader = load_trader_class(model_name)
    rows: List[dict] = []
    for round_name, spec in ROUND_SPECS.items():
        combo = None
        total_pnl = 0.0
        for product in ag.PRODUCTS:
            results_df, fills_df, metrics = bt.run_backtest_on_loaded_data(
                Trader(),
                product,
                spec["days"],
                cache[round_name][product],
                reset_between_days=False,
            )
            daily = results_df.groupby("day")["pnl"].last().diff().fillna(results_df.groupby("day")["pnl"].last())
            total_pnl += float(metrics["total_pnl"])
            rows.append(
                {
                    "model": model_name,
                    "round": round_name,
                    "round_label": spec["label"],
                    "product": product,
                    "total_pnl": float(metrics["total_pnl"]),
                    "max_drawdown": float(metrics["max_drawdown"]),
                    "fill_count": float(metrics["fill_count"]),
                    "maker_share": float(metrics["maker_share"]),
                    "avg_fill_size": float(metrics["avg_fill_size"]),
                    "avg_abs_position": float(results_df["position"].abs().mean()),
                    "max_abs_position": float(results_df["position"].abs().max()),
                    "day_1": float(daily.iloc[0]),
                    "day_2": float(daily.iloc[1]),
                    "day_3": float(daily.iloc[2]),
                }
            )
            tmp = results_df[["global_ts", "pnl"]].rename(columns={"pnl": product})
            combo = tmp if combo is None else combo.merge(tmp, on="global_ts", how="outer")

        assert combo is not None
        combo = combo.sort_values("global_ts").reset_index(drop=True)
        combo[ag.PRODUCTS] = combo[ag.PRODUCTS].ffill().fillna(0.0)
        combo["total"] = combo[ag.PRODUCTS].sum(axis=1)
        rows.append(
            {
                "model": model_name,
                "round": round_name,
                "round_label": spec["label"],
                "product": "TOTAL",
                "total_pnl": total_pnl,
                "max_drawdown": float((combo["total"] - combo["total"].cummax()).min()),
                "fill_count": float("nan"),
                "maker_share": float("nan"),
                "avg_fill_size": float("nan"),
                "avg_abs_position": float("nan"),
                "max_abs_position": float("nan"),
                "day_1": float("nan"),
                "day_2": float("nan"),
                "day_3": float("nan"),
            }
        )
    return pd.DataFrame(rows)


def write_report(metrics_df: pd.DataFrame) -> None:
    kiko = metrics_df[metrics_df["model"] == "model_kiko"].copy()
    benchmarks = metrics_df[metrics_df["product"] == "TOTAL"].copy()
    totals = benchmarks.pivot(index="model", columns="round_label", values="total_pnl").reset_index()
    totals = totals.sort_values(["Round 2", "Round 1"], ascending=False).reset_index(drop=True)

    kiko_vs_g5 = (
        metrics_df[metrics_df["model"].isin(["model_kiko", "model_G5"])]
        .copy()
        .pivot(index=["round_label", "product"], columns="model", values="total_pnl")
        .reset_index()
    )
    kiko_vs_g5["delta_kiko_minus_g5"] = kiko_vs_g5["model_kiko"] - kiko_vs_g5["model_G5"]

    round2_totals = totals[["model", "Round 2"]].copy().sort_values("Round 2", ascending=False)
    round1_totals = totals[["model", "Round 1"]].copy().sort_values("Round 1", ascending=False)

    kiko_round2_total = float(
        kiko.loc[(kiko["round"] == "round_2") & (kiko["product"] == "TOTAL"), "total_pnl"].iloc[0]
    )
    kiko_round1_total = float(
        kiko.loc[(kiko["round"] == "round_1") & (kiko["product"] == "TOTAL"), "total_pnl"].iloc[0]
    )
    g5_round2_total = float(
        metrics_df.loc[
            (metrics_df["model"] == "model_G5") & (metrics_df["round"] == "round_2") & (metrics_df["product"] == "TOTAL"),
            "total_pnl",
        ].iloc[0]
    )
    g5_round1_total = float(
        metrics_df.loc[
            (metrics_df["model"] == "model_G5") & (metrics_df["round"] == "round_1") & (metrics_df["product"] == "TOTAL"),
            "total_pnl",
        ].iloc[0]
    )

    round2_product = kiko[kiko["round"] == "round_2"][["product", "total_pnl", "max_drawdown", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position"]]
    round1_product = kiko[kiko["round"] == "round_1"][["product", "total_pnl", "max_drawdown", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position"]]

    lines = [
        "# model_kiko — análisis y backtest simple",
        "",
        "## Qué analicé",
        "",
        f"- Modelo nuevo: `{MODEL_PATHS['model_kiko']}`",
        "- Backtest local determinista con la misma lógica base usada en tus análisis anteriores.",
        "- Datasets usados:",
        "  - Round 1: días `-2, -1, 0`",
        "  - Round 2: días `-1, 0, 1`",
        "",
        "## Resumen ejecutivo",
        "",
        f"- **model_kiko gana a G5 en el backtest local en ambas rondas**.",
        f"- Round 1 total: `model_kiko = {kiko_round1_total:,.1f}` vs `G5 = {g5_round1_total:,.1f}` → delta `{kiko_round1_total - g5_round1_total:+,.1f}`",
        f"- Round 2 total: `model_kiko = {kiko_round2_total:,.1f}` vs `G5 = {g5_round2_total:,.1f}` → delta `{kiko_round2_total - g5_round2_total:+,.1f}`",
        "- La mejora viene **casi toda por PEPPER**. En ASH rinde parecido o un poco peor.",
        "- Arquitectónicamente, `model_kiko` es **más simple y más prior-driven** que tus modelos G/F; justamente por eso parece capturar muy bien el drift lineal de PEPPER, pero también me deja más alerta por posible fragilidad si cambia el régimen.",
        "",
        "## Resultados de model_kiko",
        "",
        "### Round 1",
        "",
        markdown_table(round1_product, ".3f"),
        "",
        "### Round 2",
        "",
        markdown_table(round2_product, ".3f"),
        "",
        "## Ranking rápido contra tus benchmarks",
        "",
        "### Totales Round 2",
        "",
        markdown_table(round2_totals, ".1f"),
        "",
        "### Totales Round 1",
        "",
        markdown_table(round1_totals, ".1f"),
        "",
        "## model_kiko vs G5",
        "",
        markdown_table(kiko_vs_g5, ".1f"),
        "",
        "## Diferencias estratégicas más relevantes",
        "",
        "### 1) Estructura general",
        "",
        "- **model_kiko** está organizado en dos engines simples (`OsmiumEngine` y `PepperEngine`) con operaciones compartidas de libro.",
        "- **Tus modelos G/F** tienen mucha más lógica de estado, más capas de señales y un control de inventario bastante más sofisticado.",
        "",
        "### 2) ASH_COATED_OSMIUM",
        "",
        "- **model_kiko** usa una tesis bastante clásica: fair value por **EWMA del mid**, reservation price con skew por inventario y making/taking relativamente simples.",
        "- **G5** usa una tesis más rica: anchor lento alrededor de 10k, señales L1/L2, microprice, repair logic y directional overlays.",
        "- Traducción práctica: en ASH, `model_kiko` me parece **más simple y menos fino**. Y eso se ve en los números: no mejora contra G5.",
        "",
        "### 3) INTARIAN_PEPPER_ROOT",
        "",
        "- Acá está toda la gracia de `model_kiko`.",
        "- Usa una fair value **muy explícita y muy fuerte** basada en:",
        "  - `price_slope ≈ 0.00100001` por timestamp",
        "  - una `base_price` que se va actualizando",
        "  - un `alpha` que mezcla `forward_edge - residual - inventory_skew`",
        "- O sea: está modelando PEPPER como un activo con **drift lineal casi conocido de antemano**.",
        "- **Tus modelos G/F**, en cambio, son más adaptativos:",
        "  - EMAs",
        "  - slope estimado",
        "  - continuation / pullback",
        "  - flow reciente",
        "  - targets y carry floors explícitos",
        "",
        "### 4) Filosofía de inventario",
        "",
        "- **G5** fuerza mucho más una política de carry / warehouse, con targets temporales altos y reglas de sostén de inventario.",
        "- **model_kiko** parece menos barroco: deja que el `alpha` y el skew de inventario gobiernen más directamente el pricing.",
        "- Resultado observado: en PEPPER, `model_kiko` consigue **más fills**, un maker share algo mayor y aun así carga un poco menos de inventario absoluto promedio que G5.",
        "",
        "## Valoración del modelo",
        "",
        "### Lo bueno",
        "",
        "- **Rinde mejor que G5 localmente** en Round 1 y Round 2.",
        "- La mejora viene por donde importa: **PEPPER**.",
        "- Tiene una arquitectura más compacta y fácil de razonar.",
        "- Parece estar muy bien calibrado para el régimen lineal de PEPPER que muestran ambas rondas.",
        "",
        "### Lo que me preocupa",
        "",
        "- **Está más hardcodeado al patrón de PEPPER.** Ese `price_slope` casi exacto me grita que el modelo está muy alineado con el drift observado.",
        "- Eso puede ser fantástico si el régimen se mantiene… y una trampa si el slope cambia o si el flujo real en simulación oficial no acompaña igual.",
        "- En ASH no me parece superior; de hecho, ahí G5 me sigue pareciendo conceptualmente más sólido.",
        "",
        "### Mi veredicto",
        "",
        "- **model_kiko es prometedor y merece atención seria.**",
        "- Si solo miro el backtest local, hoy **lo valoraría por encima de G5**.",
        "- Pero no lo trataría como victoria definitiva todavía, porque la ventaja parece apoyarse bastante en una hipótesis muy fuerte sobre el drift de PEPPER.",
        "",
        "## Recomendación práctica",
        "",
        "- **No descartaría G5 todavía**, pero sí pondría `model_kiko` en el top de candidatos.",
        "- Si querés ser prudente: lo usaría como **benchmark fuerte / candidato principal**, pero revisando muy bien cuánto depende del `price_slope` fijo.",
        "- Si querés el resumen en una línea: **me gusta más que G5 en PnL local, pero me da menos sensación de robustez estructural**.",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_cache()

    frames = [run_model(model_name, cache) for model_name in MODEL_PATHS]
    metrics_df = pd.concat(frames, ignore_index=True)
    metrics_df.to_csv(RESULTS_DIR / "model_kiko_benchmark_metrics.csv", index=False)

    write_report(metrics_df)
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
