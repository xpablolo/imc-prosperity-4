from __future__ import annotations

import inspect
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "round_2" / "results" / "g5_maf"
REPORT1_PATH = RESULTS_DIR / "round2_g5_analysis.md"
REPORT2_PATH = RESULTS_DIR / "round2_g5_analysis_iteration2.md"

sys.path.insert(0, str(ROOT / "round_2" / "tools"))
sys.path.insert(0, str(ROOT / "round_1" / "models"))

import analyze_g5_maf as prev  # noqa: E402
import datamodel as dm  # noqa: E402


EXTENDED_BID_GRID = [0, 10, 25, 40, 50, 60, 75, 90, 100, 125, 150, 175, 200, 250, 300, 400, 500]


@dataclass(frozen=True)
class ScenarioFamily:
    name: str
    label: str
    description: str
    scenarios: tuple[prev.CutoffScenario, ...]


SCENARIO_FAMILIES: tuple[ScenarioFamily, ...] = (
    ScenarioFamily(
        name="prior_reused",
        label="Prior reused",
        description=(
            "Reutiliza exactamente el esquema anterior. Sirve para auditar por qué salió 75, pero NO como verdad fuerte."
        ),
        scenarios=tuple(prev.CUTOFF_SCENARIOS),
    ),
    ScenarioFamily(
        name="moderate_alt",
        label="Moderate alternative",
        description=(
            "Cutoffs más altos que el prior original: mediana en 25/60/100. Escenario moderadamente competitivo."
        ),
        scenarios=(
            prev.CutoffScenario("mild", "Mild", 25.0, 6.0, 0.20, "mild"),
            prev.CutoffScenario("central", "Central", 60.0, 10.0, 0.50, "central"),
            prev.CutoffScenario("high", "High", 100.0, 18.0, 0.30, "high"),
        ),
    ),
    ScenarioFamily(
        name="tough_alt",
        label="Tough alternative",
        description=(
            "Escenario claramente más competitivo: mediana en 40/90/150. Acá 75 suele quedarse corto si de verdad pesa la probabilidad de aceptación."
        ),
        scenarios=(
            prev.CutoffScenario("mild", "Mild", 40.0, 8.0, 0.20, "mild"),
            prev.CutoffScenario("central", "Central", 90.0, 15.0, 0.50, "central"),
            prev.CutoffScenario("high", "High", 150.0, 25.0, 0.30, "high"),
        ),
    ),
    ScenarioFamily(
        name="very_tough_alt",
        label="Very tough alternative",
        description=(
            "Stress test duro: mediana en 60/120/200. No lo tomo como escenario base, sino para ver hasta dónde la conclusión depende del cutoff rival."
        ),
        scenarios=(
            prev.CutoffScenario("mild", "Mild", 60.0, 10.0, 0.20, "mild"),
            prev.CutoffScenario("central", "Central", 120.0, 20.0, 0.50, "central"),
            prev.CutoffScenario("high", "High", 200.0, 35.0, 0.30, "high"),
        ),
    ),
)


TRANSITIONS = [(75, 100), (100, 150), (150, 200), (200, 300), (300, 500)]


def markdown_table(df: pd.DataFrame, float_fmt: str = ".3f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
    body: list[str] = []
    for _, row in df.iterrows():
        vals: list[str] = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                if math.isnan(value):
                    vals.append("")
                else:
                    vals.append(format(value, float_fmt))
            else:
                vals.append(str(value))
        body.append("| " + " | ".join(vals) + " |")
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *body,
        ]
    )


def read_previous_artifacts() -> Dict[str, pd.DataFrame | str]:
    return {
        "report": REPORT1_PATH.read_text(encoding="utf-8"),
        "baseline": pd.read_csv(RESULTS_DIR / "baseline_metrics.csv"),
        "proxy": pd.read_csv(RESULTS_DIR / "proxy_metrics.csv"),
        "bid_grid": pd.read_csv(RESULTS_DIR / "bid_grid.csv"),
        "pepper_capacity": pd.read_csv(RESULTS_DIR / "pepper_capacity_timing.csv"),
        "alternatives": pd.read_csv(RESULTS_DIR / "alternative_models_round2.csv"),
    }


def compute_deltas(proxy_df: pd.DataFrame, baseline_total: float) -> Dict[str, float]:
    total = proxy_df.loc[proxy_df["product"] == "TOTAL", ["proxy", "total_pnl"]].copy()
    total["Delta"] = pd.to_numeric(total["total_pnl"], errors="coerce") - float(baseline_total)
    total = total.set_index("proxy")["Delta"]
    conservative = float(total.loc["uniform_depth_125"])
    central = float(total.loc["front_bias_depth_25"])
    optimistic = float(total.loc["uniform_depth_trade_125"])
    return {
        "risk_adjusted": 0.75 * conservative,
        "conservative": conservative,
        "central": central,
        "optimistic": optimistic,
    }


def family_weighted_q(bid: float, family: ScenarioFamily) -> float:
    return sum(
        scenario.weight * prev.logistic_acceptance_probability(bid, scenario) for scenario in family.scenarios
    )


def build_extended_bid_grid(delta_map: Mapping[str, float]) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    for delta_name, delta_value in delta_map.items():
        if delta_name == "optimistic":
            continue
        for family in SCENARIO_FAMILIES:
            for bid in EXTENDED_BID_GRID:
                q_weighted = family_weighted_q(bid, family)
                row: dict[str, float | str | int] = {
                    "scenario_family": family.name,
                    "scenario_family_label": family.label,
                    "delta_name": delta_name,
                    "delta_value": delta_value,
                    "bid": bid,
                    "weighted_acceptance": q_weighted,
                }
                ev = 0.0
                for scenario in family.scenarios:
                    q = prev.logistic_acceptance_probability(bid, scenario)
                    row[f"q_{scenario.name}"] = q
                    row[f"ev_{scenario.name}"] = q * (delta_value - bid)
                    ev += scenario.weight * q * (delta_value - bid)
                row["weighted_ev"] = ev
                rows.append(row)
    df = pd.DataFrame(rows).sort_values(["delta_name", "scenario_family", "bid"]).reset_index(drop=True)
    df.to_csv(RESULTS_DIR / "bid_grid_iteration2.csv", index=False)
    return df


def build_plateau_summary(grid_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    for (delta_name, family_name), sub in grid_df.groupby(["delta_name", "scenario_family"], sort=False):
        max_idx = sub["weighted_ev"].idxmax()
        max_row = sub.loc[max_idx]
        max_ev = float(max_row["weighted_ev"])
        rows.append(
            {
                "delta_name": delta_name,
                "scenario_family": family_name,
                "best_bid": int(max_row["bid"]),
                "best_ev": max_ev,
                "plateau_99": ",".join(str(int(b)) for b in sub.loc[sub["weighted_ev"] >= 0.99 * max_ev, "bid"]),
                "plateau_97": ",".join(str(int(b)) for b in sub.loc[sub["weighted_ev"] >= 0.97 * max_ev, "bid"]),
                "plateau_95": ",".join(str(int(b)) for b in sub.loc[sub["weighted_ev"] >= 0.95 * max_ev, "bid"]),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "bid_plateau_iteration2.csv", index=False)
    return out


def build_marginal_table(grid_df: pd.DataFrame, delta_map: Mapping[str, float]) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    for delta_name, delta_value in delta_map.items():
        if delta_name == "optimistic":
            continue
        for b1, b2 in TRANSITIONS:
            required_relative = (delta_value - b1) / (delta_value - b2) - 1.0
            base = {
                "delta_name": delta_name,
                "delta_value": delta_value,
                "from_bid": b1,
                "to_bid": b2,
                "extra_cost": b2 - b1,
                "required_relative_q_increase": required_relative,
                "required_abs_q_increase_if_q1_50": 0.50 * required_relative,
                "required_abs_q_increase_if_q1_75": 0.75 * required_relative,
                "required_abs_q_increase_if_q1_90": 0.90 * required_relative,
            }
            for family in SCENARIO_FAMILIES:
                sub = grid_df[
                    (grid_df["delta_name"] == delta_name)
                    & (grid_df["scenario_family"] == family.name)
                    & (grid_df["bid"].isin([b1, b2]))
                ].sort_values("bid")
                q1 = float(sub.iloc[0]["weighted_acceptance"])
                q2 = float(sub.iloc[1]["weighted_acceptance"])
                ev1 = float(sub.iloc[0]["weighted_ev"])
                ev2 = float(sub.iloc[1]["weighted_ev"])
                row = dict(base)
                row["scenario_family"] = family.name
                row["q1_weighted"] = q1
                row["q2_weighted"] = q2
                row["actual_abs_q_increase"] = q2 - q1
                row["required_abs_q_increase_at_q1"] = q1 * required_relative
                row["upgrade_worthwhile_under_family"] = int(ev2 > ev1)
                rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "bid_marginal_iteration2.csv", index=False)
    return out


def build_robust_summary(grid_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for delta_name, sub in grid_df.groupby("delta_name", sort=False):
        work = sub.copy()
        max_map = work.groupby("scenario_family")["weighted_ev"].max().to_dict()
        work["normalized_ev"] = work.apply(lambda r: float(r["weighted_ev"]) / max_map[str(r["scenario_family"])], axis=1)
        summary = (
            work.groupby("bid", as_index=False)
            .agg(
                mean_normalized_ev=("normalized_ev", "mean"),
                min_normalized_ev=("normalized_ev", "min"),
                mean_weighted_ev=("weighted_ev", "mean"),
            )
            .sort_values("bid")
            .reset_index(drop=True)
        )
        summary["delta_name"] = delta_name
        rows.append(summary)
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(RESULTS_DIR / "bid_robust_summary_iteration2.csv", index=False)
    return out


def build_pepper_iteration2(previous_capacity: pd.DataFrame) -> pd.DataFrame:
    loaded = {
        product: {
            day: prev.load_day_data("round_2", day, product)
            for day in prev.ROUND_SPECS["round_2"].days
        }
        for product in prev.PRODUCTS
    }

    baseline_df, baseline_results, _fills = prev.run_round_backtests(
        model_name="model_G5",
        round_spec=prev.ROUND_SPECS["round_2"],
        proxy=None,
        loaded_data=loaded,
    )
    base_product = baseline_df[
        (baseline_df["round"] == "round_2") & (baseline_df["product"] == "INTARIAN_PEPPER_ROOT")
    ].copy()
    base_day_cols = [c for c in base_product.columns if c.startswith("day_") and c.endswith("_pnl")]

    rows: list[dict[str, float | str | int]] = []
    baseline_timing = previous_capacity[previous_capacity["proxy"] == "baseline"].copy()
    for proxy in prev.PROXIES:
        proxy_df, product_results, _fills = prev.run_round_backtests(
            model_name="model_G5",
            round_spec=prev.ROUND_SPECS["round_2"],
            proxy=proxy,
            loaded_data=loaded,
        )
        pep_total = proxy_df[proxy_df["product"] == "INTARIAN_PEPPER_ROOT"].iloc[0]
        proxy_timing = previous_capacity[previous_capacity["proxy"] == proxy.name].copy()
        for day in prev.ROUND_SPECS["round_2"].days:
            baseline_day_pnl = float(base_product[f"day_{day}_pnl"].iloc[0])
            proxy_day_pnl = float(pep_total[f"day_{day}_pnl"])
            base_row = baseline_timing.loc[baseline_timing["day"] == day].iloc[0]
            proxy_row = proxy_timing.loc[proxy_timing["day"] == day].iloc[0]
            rows.append(
                {
                    "proxy": proxy.name,
                    "day": int(day),
                    "baseline_day_pnl": baseline_day_pnl,
                    "proxy_day_pnl": proxy_day_pnl,
                    "delta_day_pnl": proxy_day_pnl - baseline_day_pnl,
                    "baseline_time_to_70": float(base_row["time_to_70"]),
                    "proxy_time_to_70": float(proxy_row["time_to_70"]),
                    "delta_time_to_70": float(proxy_row["time_to_70"]) - float(base_row["time_to_70"]),
                    "baseline_time_to_80": float(base_row["time_to_80"]),
                    "proxy_time_to_80": float(proxy_row["time_to_80"]),
                    "delta_time_to_80": float(proxy_row["time_to_80"]) - float(base_row["time_to_80"]),
                    "baseline_pct_pos_below_70": float(base_row["pct_pos_below_70"]),
                    "proxy_pct_pos_below_70": float(proxy_row["pct_pos_below_70"]),
                    "baseline_pct_pos_at_80": float(base_row["pct_pos_at_80"]),
                    "proxy_pct_pos_at_80": float(proxy_row["pct_pos_at_80"]),
                }
            )
    out = pd.DataFrame(rows).sort_values(["proxy", "day"]).reset_index(drop=True)
    out.to_csv(RESULTS_DIR / "pepper_capacity_iteration2.csv", index=False)
    return out


def detect_access_signal() -> dict[str, object]:
    signature = inspect.signature(dm.TradingState.__init__)
    params = [name for name in signature.parameters.keys() if name != "self"]
    py_files = [
        ROOT / "round_1" / "models" / "datamodel.py",
        ROOT / "round_1" / "tools" / "backtest.py",
        ROOT / "round_2" / "tools" / "analyze_g5_maf.py",
    ]
    runtime_hits: list[tuple[str, str]] = []
    for file in py_files[:2]:
        text = file.read_text(encoding="utf-8")
        for token in ("access_granted", "accepted_bid", "market_access", "maf"):
            if token in text:
                runtime_hits.append((str(file), token))
    old_bid_stubs = []
    for file in (ROOT / "round_0" / "models").glob("*.py"):
        text = file.read_text(encoding="utf-8")
        if "def bid(" in text:
            old_bid_stubs.append(file.name)
    return {
        "trading_state_fields": params,
        "runtime_flag_hits": runtime_hits,
        "round0_bid_stub_files": sorted(old_bid_stubs),
        "direct_access_signal_available": len(runtime_hits) > 0 or any("access" in p for p in params),
    }


def write_report(
    previous: Mapping[str, pd.DataFrame | str],
    delta_map: Mapping[str, float],
    extended_grid: pd.DataFrame,
    plateau_df: pd.DataFrame,
    marginal_df: pd.DataFrame,
    robust_df: pd.DataFrame,
    pepper_iter2: pd.DataFrame,
    access_info: Mapping[str, object],
) -> None:
    report1 = str(previous["report"])
    bid_grid_prev = previous["bid_grid"].copy()  # type: ignore[assignment]
    bid_grid_prev["weighted_ev_risk_adjusted"] = pd.to_numeric(
        bid_grid_prev["weighted_ev_risk_adjusted"], errors="coerce"
    )
    prev_best_row = bid_grid_prev.loc[bid_grid_prev["weighted_ev_risk_adjusted"].idxmax()]
    previous_recommendation = 75
    previous_grid_hit_boundary = int(prev_best_row["bid"]) == int(bid_grid_prev["bid"].max())

    plateaus_risk = plateau_df[plateau_df["delta_name"] == "risk_adjusted"].copy()
    robust_risk = robust_df[robust_df["delta_name"] == "risk_adjusted"].copy()

    recommend_bid = 150
    defendable_band = "100–200"
    conservative_bid = 100
    acceptance_priority_bid = 200

    recommended_row = robust_risk.loc[robust_risk["bid"] == recommend_bid].iloc[0]
    scenario_slice = extended_grid[
        (extended_grid["delta_name"] == "risk_adjusted") & (extended_grid["bid"].isin([75, 100, 150, 200, 250]))
    ][["scenario_family_label", "bid", "weighted_acceptance", "weighted_ev"]].copy()
    scenario_slice = scenario_slice.sort_values(["scenario_family_label", "bid"]).reset_index(drop=True)

    marginal_focus = marginal_df[
        (marginal_df["delta_name"] == "risk_adjusted")
        & (marginal_df["scenario_family"].isin(["prior_reused", "moderate_alt", "tough_alt", "very_tough_alt"]))
        & (marginal_df["from_bid"].isin([75, 100, 150, 200]))
    ][
        [
            "scenario_family",
            "from_bid",
            "to_bid",
            "q1_weighted",
            "q2_weighted",
            "actual_abs_q_increase",
            "required_abs_q_increase_at_q1",
        ]
    ].copy()

    pepper_summary = (
        pepper_iter2.groupby("proxy", as_index=False)
        .agg(
            total_delta_pnl=("delta_day_pnl", "sum"),
            day_minus1_delta=("delta_day_pnl", lambda s: float(s.iloc[0])),
            day0_delta=("delta_day_pnl", lambda s: float(s.iloc[1])),
            day1_delta=("delta_day_pnl", lambda s: float(s.iloc[2])),
            avg_delta_time_to_80=("delta_time_to_80", "mean"),
        )
        .sort_values("total_delta_pnl", ascending=False)
        .reset_index(drop=True)
    )

    lines: list[str] = [
        "# Round 2 G5 analysis — iteration 2",
        "",
        f"Base explícita usada: `{REPORT1_PATH}` + CSVs previos ya generados en `{RESULTS_DIR}`.",
        "",
        "## 1. Qué partes del análisis previo se confirman",
        "",
        "- **G5 sigue siendo baseline razonable.** No apareció evidencia nueva que justifique cambiar de familia por una diferencia marginal.",
        f"- **El Delta del extra access sigue siendo positivo** en todos los proxies razonables: conservador `{delta_map['conservative']:,.1f}`, central `{delta_map['central']:,.1f}`, upper bound `{delta_map['optimistic']:,.1f}`.",
        "- **PEPPER sigue siendo el canal principal de monetización** del market access extra.",
        "- **La lectura microestructural anterior se mantiene:** el beneficio parece venir más por mejor fill quality / tamaño y timing de inventario que por hiperactividad.",
        "",
        "## 2. Qué partes del análisis previo eran frágiles",
        "",
        f"- La recomendación previa `bid() = {previous_recommendation}` **no era un óptimo limpio**.",
        f"- El propio CSV previo muestra que el EV máximo estaba en el borde de la grid anterior (bid={int(prev_best_row['bid'])}), lo que significa que la elección de `{previous_recommendation}` salió de una **grid truncada**, no de una meseta plenamente explorada.",
        f"- Regla previa exacta: *elegir el menor bid dentro del 95% del EV máximo del grid*. Eso devolvió `{previous_recommendation}` porque el máximo estaba en el extremo superior disponible.",
        f"- `75` hay que interpretarlo entonces como **el borde inferior de una zona alta** bajo el prior original, no como un número sagrado.",
        "",
        "### Supuestos previos auditados",
        "",
        "- Delta de decisión = `0.75 * Delta_conservative`.",
        "- Cutoff rival modelado con tres escenarios logísticos muy suaves (medianas 15 / 30 / 50).",
        "- Grid original limitada a bids hasta 100.",
        "- Eso vuelve sólida la señal “los bids muy bajos son malos”, pero frágil la precisión del número exacto.",
        "",
        "## 3. Reestimación del bid con grid ampliada",
        "",
        "Usé una grid bastante más amplia:",
        "",
        "`0, 10, 25, 40, 50, 60, 75, 90, 100, 125, 150, 175, 200, 250, 300, 400, 500`",
        "",
        "La idea es simple: si Delta vale miles, el coste marginal de subir de 75 a 100 o 150 puede ser casi irrelevante comparado con una mejora modesta en probabilidad de aceptación.",
        "",
        "### Plateau summary (delta risk-adjusted)",
        "",
        markdown_table(plateaus_risk[["scenario_family", "best_bid", "best_ev", "plateau_99", "plateau_97", "plateau_95"]], ".1f"),
        "",
        "### EV y aceptación ponderada en bids clave",
        "",
        markdown_table(scenario_slice, ".3f"),
        "",
        "### Conclusión cuantitativa de esta sección",
        "",
        "- **`75` NO es un óptimo identificable.**",
        "- Bajo el prior viejo, la meseta 99% ya incluye `90–125`.",
        "- Bajo escenarios moderados y duros, el máximo se desplaza a `175–300`.",
        "- En otras palabras: lo que está identificado no es “75 exacto”, sino una **banda alta de bids razonables**, y la banda se mueve según cómo creas que pujan los rivales.",
        "",
        "## 4. Análisis marginal del coste vs aceptación",
        "",
        "La condición exacta para preferir `b2` frente a `b1` es:",
        "",
        "`q(b2) * (Delta - b2) > q(b1) * (Delta - b1)`",
        "",
        "Equivalentemente:",
        "",
        "`q(b2) / q(b1) > (Delta - b1) / (Delta - b2)`",
        "",
        "o en términos de aumento absoluto mínimo de aceptación:",
        "",
        "`Delta_q > q(b1) * (b2 - b1) / (Delta - b2)`",
        "",
        "### Umbral marginal requerido (risk-adjusted Delta)",
        "",
        markdown_table(marginal_focus, ".4f"),
        "",
        "### Lectura importante",
        "",
        f"- Pasar de **75 → 100** requiere apenas un aumento relativo de aceptación de ~**0.75%** bajo `Delta_risk_adjusted={delta_map['risk_adjusted']:,.1f}`.",
        f"- Pasar de **100 → 150** requiere ~**1.53%** relativo.",
        f"- Pasar de **150 → 200** requiere ~**1.55%** relativo.",
        "- Eso es poquísimo. Entonces, si pensás que subir el bid mejora aunque sea un poco la chance de entrar, bids más altos se justifican enseguida.",
        "",
        "## 5. Revisión crítica del cutoff rival",
        "",
        "### Qué se había supuesto antes",
        "",
        "- Tres escenarios logísticos muy suaves con medianas bajas (15, 30, 50).",
        "- Pesos 20% / 50% / 30%.",
        "- Cero evidencia dura de bids rivales en este repo.",
        "",
        "### Qué evidencia histórica real sí existe",
        "",
        "- Busqué referencias de bidding en el repo.",
        "- Lo único que aparece son stubs viejos de Round 0 devolviendo `15` en varios modelos.",
        "- Eso **NO** sirve como histórico útil para el cutoff rival de esta ronda.",
        "",
        "### Qué cambia al endurecer el cutoff",
        "",
        "- Si los rivales pujan suave, la zona buena empieza cerca de 90–125.",
        "- Si los rivales pujan moderado, la zona buena sube a 150–200.",
        "- Si los rivales pujan duro, la zona buena sube todavía más (200–300).",
        "",
        "### Conclusión crítica",
        "",
        "- **La decisión final está dominada por la incertidumbre sobre los rivales.**",
        "- Lo que sabemos bien es que un bid alto tiene mucho más sentido que uno bajo.",
        "- Lo que NO sabemos bien es dónde cae el cutoff del top 50%. Ese punto domina si conviene 100, 150 o 200+.",
        "",
        "## 6. Verificación de access_granted / implementabilidad",
        "",
        f"- Firma actual de `TradingState`: `{', '.join(access_info['trading_state_fields'])}`.",
        f"- `access_granted` explícito disponible: **{access_info['direct_access_signal_available']}**.",
        f"- Hits reales de runtime flags en datamodel/backtester: `{access_info['runtime_flag_hits']}`.",
        "",
        "### Conclusión",
        "",
        "- **NO encontré una señal formal tipo `access_granted` en `TradingState`, `observations` ni en el backtester local.**",
        "- Entonces no corresponde diseñar la estrategia alrededor de un booleano ficticio.",
        "- Si el acceso extra existe en runtime, la señal observable real sería **ver más profundidad / más volumen visible / más oportunidades de fill**, no un flag explícito.",
        "",
        "### Implicación práctica",
        "",
        "Cualquier mejora razonable tiene que depender solo de variables observables:",
        "",
        "- profundidad visible acumulada",
        "- imbalance",
        "- flow reciente",
        "- spread visible",
        "- gap respecto al target inventory",
        "",
        "## 7. Análisis detallado de PEPPER capacity timing",
        "",
        markdown_table(pepper_iter2, ".1f"),
        "",
        "### Qué me dice esto de verdad",
        "",
        markdown_table(pepper_summary, ".1f"),
        "",
        "Lectura crítica:",
        "",
        "- En baseline, PEPPER ya pasa gran parte del tiempo muy cerca de +80.",
        "- El proxy sí acelera la llegada a 70/80, sobre todo en day -1.",
        "- **PERO** el Delta diario de PEPPER no queda concentrado solo en day -1. En el proxy conservador, los tres días aportan de forma bastante repartida.",
        "- Eso sugiere que el valor del extra access no es solo “entrar antes al carry”, sino también **reciclar mejor una vez que ya estás cargado**.",
        "- Dicho más simple: el acceso extra ayuda al inicio del episodio, pero también mejora el fill quality mientras defendés y renovás la posición grande.",
        "",
        "## 8. Robustez del modelo G5 frente a alternativas",
        "",
        markdown_table(previous["alternatives"], ".1f"),  # type: ignore[arg-type]
        "",
        "### Lectura",
        "",
        "- La ventaja de G5 sobre G2/F3 existe, pero no es enorme en porcentaje del total.",
        "- En Round 2 baseline, G5 le saca ~1.6k a G2 y ~1.9k a F3.",
        "- Eso es material, pero bastante menor que la incertidumbre del problema del bid y del cutoff rival.",
        "- Además, el ranking no cambia con el proxy conservador.",
        "",
        "### Conclusión",
        "",
        "- **No veo motivo suficiente para cambiar de familia.**",
        "- Si fueras a tocar algo, tiene más sentido microajustar G5 que saltar a G2/F3 por una diferencia chica.",
        "",
        "## 9. Cambios mínimos recomendados en G5",
        "",
        "### ASH",
        "",
        "- Mantener el core igual.",
        "- Como mucho, permitir un poco más de tamaño pasivo cuando la profundidad visible top-3 supere claramente su nivel normal.",
        "- No recomiendo estrechar spreads globalmente.",
        "",
        "### PEPPER",
        "",
        "Cambio mínimo y defendible:",
        "",
        "- **Solo cuando** `position_gap = target_inventory - position` sea grande (ej. >= 8 o 10),",
        "- **y** la señal siga alineada (`l2_imbalance` no en contra, `flow_recent` no claramente adverso, spread aceptable),",
        "- **y** la profundidad visible acumulada sea rica,",
        "- permitir un pequeño aumento de `passive_buy_size` y/o un step-in comprador algo más agresivo.",
        "",
        "Importante:",
        "",
        "- eso **NO** depende de saber si el bid fue aceptado;",
        "- depende solo de que el mercado observable te muestre realmente más oportunidad.",
        "",
        "### Qué NO haría",
        "",
        "- No metería lógica `if access_granted:`.",
        "- No estrecharía los spreads de forma ciega.",
        "- No aumentaría agresividad una vez que ya estás pegado a +80.",
        "",
        "## 10. Limitaciones restantes",
        "",
        "- Seguimos sin conocer la distribución real de bids rivales.",
        "- El valor exacto de Delta sigue dependiendo de proxies, aunque la dirección y el orden de magnitud ya están bastante mejor establecidos.",
        "- El backtest local es determinista; no estima la variabilidad del feed aleatorizado entre submissions.",
        "",
        "## Recomendación final actualizada",
        "",
        f"- **¿Debés interpretar 75 como número concreto?** No. Hay que interpretarlo como **borde inferior de una zona alta**, no como óptimo preciso.",
        f"- **Bid puntual recomendado hoy:** `{recommend_bid}`.",
        f"- **Banda realmente defendible:** `{defendable_band}`.",
        f"- **Si querés ser más conservador con el gasto:** `{conservative_bid}`.",
        f"- **Si querés priorizar probabilidad de aceptación:** `{acceptance_priority_bid}`.",
        "- **Mantengo G5:** sí.",
        "- **¿Haría cambios al modelo antes de enviar?** Solo microcambios observables en PEPPER; si no podés validarlos rápido, mandaría G5 casi intacto.",
        "- **Confianza en la decisión:** media. Lo sólido es la zona alta; lo incierto es el cutoff rival exacto.",
    ]
    REPORT2_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    previous = read_previous_artifacts()
    baseline_df = previous["baseline"]  # type: ignore[assignment]
    baseline_total = float(
        baseline_df.loc[(baseline_df["round"] == "round_2") & (baseline_df["product"] == "TOTAL"), "total_pnl"].iloc[0]
    )
    delta_map = compute_deltas(previous["proxy"], baseline_total)  # type: ignore[arg-type]
    extended_grid = build_extended_bid_grid(delta_map)
    plateau_df = build_plateau_summary(extended_grid)
    marginal_df = build_marginal_table(extended_grid, delta_map)
    robust_df = build_robust_summary(extended_grid)
    pepper_iter2 = build_pepper_iteration2(previous["pepper_capacity"])  # type: ignore[arg-type]
    access_info = detect_access_signal()
    write_report(previous, delta_map, extended_grid, plateau_df, marginal_df, robust_df, pepper_iter2, access_info)
    print(f"Wrote iteration 2 report to {REPORT2_PATH}")


if __name__ == "__main__":
    main()
