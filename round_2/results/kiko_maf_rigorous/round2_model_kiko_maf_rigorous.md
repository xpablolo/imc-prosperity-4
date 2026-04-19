# Round 2 — análisis cuantitativo riguroso del MAF para model_kiko

## A. Resumen ejecutivo

- `P0_sample` observado de `model_kiko` en los 3 días de Round 2 (días independientes, arrancando flat): **308,696.5**.
- `P0_1M` usado para valorar una ronda de ~1M timestamps: **102,898.8** por día. Esto surge del promedio de tres días locales que ya cubren `timestamp = 0 → 999900`.
- `Delta_1M` estimado por extra access: **conservador 1,005.2**, **central 1,609.8**, **agresivo 6,497.2**.
- Haircut prudente para decisión de bid: **risk-adjusted = 703.6** (= 70% del proxy conservador).
- Con el bid recomendado `125`, el uplift neto condicional si el bid entra es **0.86%** a **1.44%** sobre `P0_1M` (conservador → central).
- Con ese mismo bid, el ROI del fee es **7.04x** a **11.88x** si el bid es aceptado.
- Rango razonable de bids: **100–150**.
- Bid robusto recomendado: **`125`**.
- Razón principal: el valor del MAF en `model_kiko` sale positivo y robusto, pero está **MUY** lejos de +25% PnL; además, el uplift viene sobre todo de **ASH** (74% del Delta conservador y 87% del Delta central), no de desbloquear un edge nuevo enorme en PEPPER.

## B. Formalización matemática

Definiciones usadas:

- `P0`: PnL sin extra access.
- `P1`: PnL con extra access bajo un proxy contrafactual explícito.
- `Delta = P1 - P0`.
- `b`: bid.
- `A(b)`: indicador de aceptación del bid, con `A(b)=1` si el bid entra en el top 50%.
- `q(b) = Prob(C < b)`, donde `C` es el cutoff rival modelado como variable aleatoria.

Fórmulas exactas:

- `Pi(b) = P0 + A(b) * (Delta - b)`
- `net_gain_if_accepted = Delta - b`
- `uplift_pct_vs_base = (Delta - b) / P0`
- `fee_roi = (Delta - b) / b`
- `EV(b) = P0 + q(b) * (Delta - b)`

Separación lógica que respeté durante todo el análisis:

1. Primero fijé la lógica de trading de `model_kiko` y medí `P0` y `P1`.
2. Recién después modelé la aceptación del bid vía `q(b)`.
3. No mezclé la valuación del access extra con rediseños de estrategia.

## C. Resultados por proxy

### Baseline limpio de `model_kiko`

| product | P0_sample | P0_1M | drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position | pct_time_abs_ge_70 | pct_time_at_limit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ASH | 66833.000 | 22277.667 | -1620.000 | 2027.000 | 0.667 | 5.687 | 27.038 | 0.046 | 0.017 |
| PEPPER | 241863.500 | 80621.167 | -1680.000 | 1539.000 | 0.383 | 5.390 | 70.803 | 0.632 | 0.257 |
| TOTAL | 308696.500 | 102898.833 | -1850.000 | 3566.000 | 0.544 | 5.559 |  |  |  |

### Timing e inventario de PEPPER en baseline (cada día arranca flat)

| scenario_label | day | day_pnl | avg_position | pct_time_pos_ge_70 | pct_time_pos_at_80 | time_to_50 | time_to_70 | time_to_80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | -1 | 81203.5 | 73.1 | 0.7 | 0.3 | 2700.0 | 5700.0 | 12600.0 |
| Baseline | 0 | 81022.0 | 71.4 | 0.6 | 0.2 | 1000.0 | 9900.0 | 14400.0 |
| Baseline | 1 | 79638.0 | 68.0 | 0.5 | 0.2 | 14400.0 | 19900.0 | 23100.0 |

Lectura baseline: PEPPER ya pasa **63.2%** del tiempo en `>=70` y **25.7%** exactamente en `80`. O sea: la saturación existe, pero en `model_kiko` el cuello marginal del MAF NO está dominado por PEPPER; está más en ASH/fill quality.

### `P0`, `P1` y `Delta` por proxy (TOTAL)

| proxy | P0_sample | P1_sample | Delta_sample | P0_1m | P1_1M_equiv | Delta_1m | fill_count_change | maker_share_change | avg_fill_size_change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Uniform depth +25% | 308696.500 | 311712.000 | 3015.500 | 102898.833 | 103904.000 | 1005.167 | -30.000 | -0.001 | 0.710 |
| Front-biased depth +25% | 308696.500 | 313526.000 | 4829.500 | 102898.833 | 104508.667 | 1609.833 | -37.000 | -0.002 | 1.232 |
| Depth +25% + trades +25% | 308696.500 | 328188.000 | 19491.500 | 102898.833 | 109396.000 | 6497.167 | -23.000 | -0.001 | 1.417 |

### Descomposición por producto

| proxy | product | P0_sample | P1_sample | Delta_sample | P0_1m_product | P1_1M_equiv | Delta_1m | fill_count_change | maker_share_change | avg_fill_size_change | avg_abs_position_change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Uniform depth +25% | ASH | 66833.000 | 69076.000 | 2243.000 | 22277.667 | 23025.333 | 747.667 | -3.000 | -0.001 | 0.566 | 0.635 |
| Uniform depth +25% | PEPPER | 241863.500 | 242636.000 | 772.500 | 80621.167 | 80878.667 | 257.500 | -27.000 | -0.002 | 0.901 | -0.008 |
| Front-biased depth +25% | ASH | 66833.000 | 71034.000 | 4201.000 | 22277.667 | 23678.000 | 1400.333 | 0.000 | -0.003 | 1.033 | 1.201 |
| Front-biased depth +25% | PEPPER | 241863.500 | 242492.000 | 628.500 | 80621.167 | 80830.667 | 209.500 | -37.000 | -0.005 | 1.497 | -0.386 |
| Depth +25% + trades +25% | ASH | 66833.000 | 82608.000 | 15775.000 | 22277.667 | 27536.000 | 5258.333 | -3.000 | -0.002 | 1.382 | 0.668 |
| Depth +25% + trades +25% | PEPPER | 241863.500 | 245580.000 | 3716.500 | 80621.167 | 81860.000 | 1238.833 | -20.000 | -0.002 | 1.461 | -0.845 |

### Cambios de timing/inventario en PEPPER

| scenario_label | day | day_pnl | avg_position | pct_time_pos_ge_70 | pct_time_pos_at_80 | time_to_50 | time_to_70 | time_to_80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Uniform depth +25% | -1 | 81305.5 | 72.8 | 0.7 | 0.3 | 1400.0 | 5700.0 | 11300.0 |
| Uniform depth +25% | 0 | 81191.0 | 71.3 | 0.7 | 0.3 | 1000.0 | 9900.0 | 12600.0 |
| Uniform depth +25% | 1 | 80139.5 | 68.3 | 0.6 | 0.3 | 14400.0 | 17400.0 | 19900.0 |
| Front-biased depth +25% | -1 | 81247.0 | 72.5 | 0.7 | 0.3 | 1500.0 | 2700.0 | 5700.0 |
| Front-biased depth +25% | 0 | 81024.0 | 70.7 | 0.6 | 0.3 | 400.0 | 2700.0 | 9900.0 |
| Front-biased depth +25% | 1 | 80221.0 | 68.0 | 0.6 | 0.3 | 14400.0 | 17400.0 | 19900.0 |
| Depth +25% + trades +25% | -1 | 82191.5 | 72.0 | 0.7 | 0.3 | 1400.0 | 5700.0 | 14400.0 |
| Depth +25% + trades +25% | 0 | 81921.0 | 70.3 | 0.6 | 0.3 | 1000.0 | 9900.0 | 12600.0 |
| Depth +25% + trades +25% | 1 | 81467.5 | 67.6 | 0.5 | 0.3 | 14400.0 | 17400.0 | 19900.0 |

Hallazgo clave: el proxy conservador suma **1,005.2** por ~1M timestamps y el central **1,609.8**; pero la parte de PEPPER es chica frente a ASH. Con el proxy central, ASH explica ~**87%** del Delta. Así que para `model_kiko` el MAF es más una mejora de acceso/calidad de ejecución que un cambio estructural del carry de PEPPER.

## D. Escalado a 1M timestamps

No hice `Delta_1M = Delta_sample * (1,000,000 / T_sample)` porque sería metodológicamente flojo. De hecho, los CSV locales ya recorren `timestamp = 0 → 999900` por día, con saltos de 100. O sea: **cada día ya cubre ~1M unidades de timestamp**. Lo correcto es tratar los tres días como tres draws de una ronda ~1M arrancando flat y estimar `Delta_1M` desde la distribución diaria, no reescalar el total de 3 días linealmente.

Resultado explícito: `Delta_1M_conservative = 1,005.2`, `Delta_1M_central = 1,609.8`, `Delta_1M_aggressive = 6,497.2`.

### Delta incremental por bloques (promedio por día, TOTAL)

| bucket | Depth +25% + trades +25% | Front-biased depth +25% | Uniform depth +25% |
| --- | --- | --- | --- |
| 1.0 | 700.8 | 310.8 | 170.2 |
| 2.0 | 482.3 | 114.8 | 89.8 |
| 3.0 | 365.2 | 57.2 | 28.5 |
| 4.0 | 712.0 | 85.2 | 81.2 |
| 5.0 | 925.0 | 77.0 | 37.3 |
| 6.0 | 569.8 | 50.8 | 27.3 |
| 7.0 | 686.7 | 161.7 | 42.0 |
| 8.0 | 772.7 | 311.8 | 247.3 |
| 9.0 | 578.8 | 163.3 | 107.3 |
| 10.0 | 703.8 | 277.2 | 174.2 |

### Comparativa de funciones de scaling para la forma de `Delta(t)` dentro del día

| model | avg_rmse | max_rmse |
| --- | --- | --- |
| capped_linear | 0.10366 | 0.10835 |
| linear | 0.10366 | 0.10835 |
| log | 0.10424 | 0.10895 |
| piecewise_saturation | 0.10817 | 0.11314 |
| sqrt | 0.24049 | 0.24634 |

La función más defendible es **`linear`**. La mejor lectura empírica es casi lineal dentro del día: no aparece evidencia fuerte de una saturación pronunciada del Delta. Hay concentración de valor en algunos buckets, pero no la suficiente como para defender un crecimiento log/capped fuerte. Como cada día ya es un horizonte ~1M, esta comparación sirve para entender la forma de `Delta(t)`, no para extrapolar mecánicamente el Delta local 100x.

## E. Análisis game theoretic del cutoff

No observamos bids rivales, así que modelé el cutoff `C` con una mezcla de escenarios logísticos simples y explicables:

| escenario | median_bid | slope | weight | lectura |
| --- | --- | --- | --- | --- |
| Competencia baja | 20.000 | 6.000 | 0.150 | Campo poco agresivo: el cutoff efectivo está en la zona de los 20s. |
| Central | 45.000 | 9.000 | 0.400 | Escenario base: cutoff en torno a 45 con transición relativamente suave. |
| Competencia alta | 80.000 | 14.000 | 0.300 | Escenario competitivo serio: muchos equipos dispuestos a pagar en la zona 70–100. |
| Stress muy alto | 120.000 | 20.000 | 0.150 | Stress test duro: la mediana rival ya se mueve a tres cifras. |

Para decidir el bid usé `Delta_risk_adjusted = 703.6`. También reporto sensibilidad con `Delta` conservador y central.

### Grid de bids

| delta_name | bid | q_low | q_central | q_high | q_stress | q_weighted | net_gain_if_accepted | uplift_pct_vs_base_if_accepted | fee_roi_if_accepted | EV_uplift_weighted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| central | 0 | 0.034 | 0.007 | 0.003 | 0.002 | 0.009 | 1609.833 | 1.564 |  | 14.812 |
| central | 10 | 0.159 | 0.020 | 0.007 | 0.004 | 0.034 | 1599.833 | 1.555 | 159.983 | 55.149 |
| central | 20 | 0.500 | 0.059 | 0.014 | 0.007 | 0.103 | 1589.833 | 1.545 | 79.492 | 164.535 |
| central | 30 | 0.841 | 0.159 | 0.027 | 0.011 | 0.200 | 1579.833 | 1.535 | 52.661 | 315.286 |
| central | 40 | 0.966 | 0.365 | 0.054 | 0.018 | 0.310 | 1569.833 | 1.526 | 39.246 | 486.108 |
| central | 50 | 0.993 | 0.635 | 0.105 | 0.029 | 0.439 | 1559.833 | 1.516 | 31.197 | 684.864 |
| central | 60 | 0.999 | 0.841 | 0.193 | 0.047 | 0.551 | 1549.833 | 1.506 | 25.831 | 854.535 |
| central | 75 | 1.000 | 0.966 | 0.412 | 0.095 | 0.674 | 1534.833 | 1.492 | 20.464 | 1034.484 |
| central | 100 | 1.000 | 0.998 | 0.807 | 0.269 | 0.831 | 1509.833 | 1.467 | 15.098 | 1255.365 |
| central | 125 | 1.000 | 1.000 | 0.961 | 0.562 | 0.923 | 1484.833 | 1.443 | 11.879 | 1370.029 |
| central | 150 | 1.000 | 1.000 | 0.993 | 0.818 | 0.971 | 1459.833 | 1.419 | 9.732 | 1416.951 |
| central | 200 | 1.000 | 1.000 | 1.000 | 0.982 | 0.997 | 1409.833 | 1.370 | 7.049 | 1405.950 |
| conservative | 0 | 0.034 | 0.007 | 0.003 | 0.002 | 0.009 | 1005.167 | 0.977 |  | 9.249 |
| conservative | 10 | 0.159 | 0.020 | 0.007 | 0.004 | 0.034 | 995.167 | 0.967 | 99.517 | 34.305 |
| conservative | 20 | 0.500 | 0.059 | 0.014 | 0.007 | 0.103 | 985.167 | 0.957 | 49.258 | 101.957 |
| conservative | 30 | 0.841 | 0.159 | 0.027 | 0.011 | 0.200 | 975.167 | 0.948 | 32.506 | 194.613 |
| conservative | 40 | 0.966 | 0.365 | 0.054 | 0.018 | 0.310 | 965.167 | 0.938 | 24.129 | 298.869 |
| conservative | 50 | 0.993 | 0.635 | 0.105 | 0.029 | 0.439 | 955.167 | 0.928 | 19.103 | 419.378 |
| conservative | 60 | 0.999 | 0.841 | 0.193 | 0.047 | 0.551 | 945.167 | 0.919 | 15.753 | 521.138 |
| conservative | 75 | 1.000 | 0.966 | 0.412 | 0.095 | 0.674 | 930.167 | 0.904 | 12.402 | 626.936 |
| conservative | 100 | 1.000 | 0.998 | 0.807 | 0.269 | 0.831 | 905.167 | 0.880 | 9.052 | 752.609 |
| conservative | 125 | 1.000 | 1.000 | 0.961 | 0.562 | 0.923 | 880.167 | 0.855 | 7.041 | 812.114 |
| conservative | 150 | 1.000 | 1.000 | 0.993 | 0.818 | 0.971 | 855.167 | 0.831 | 5.701 | 830.046 |
| conservative | 200 | 1.000 | 1.000 | 1.000 | 0.982 | 0.997 | 805.167 | 0.782 | 4.026 | 802.949 |
| risk_adjusted | 0 | 0.034 | 0.007 | 0.003 | 0.002 | 0.009 | 703.617 | 0.684 |  | 6.474 |
| risk_adjusted | 10 | 0.159 | 0.020 | 0.007 | 0.004 | 0.034 | 693.617 | 0.674 | 69.362 | 23.910 |
| risk_adjusted | 20 | 0.500 | 0.059 | 0.014 | 0.007 | 0.103 | 683.617 | 0.664 | 34.181 | 70.749 |
| risk_adjusted | 30 | 0.841 | 0.159 | 0.027 | 0.011 | 0.200 | 673.617 | 0.655 | 22.454 | 134.433 |
| risk_adjusted | 40 | 0.966 | 0.365 | 0.054 | 0.018 | 0.310 | 663.617 | 0.645 | 16.590 | 205.493 |
| risk_adjusted | 50 | 0.993 | 0.635 | 0.105 | 0.029 | 0.439 | 653.617 | 0.635 | 13.072 | 286.979 |
| risk_adjusted | 60 | 0.999 | 0.841 | 0.193 | 0.047 | 0.551 | 643.617 | 0.625 | 10.727 | 354.872 |
| risk_adjusted | 75 | 1.000 | 0.966 | 0.412 | 0.095 | 0.674 | 628.617 | 0.611 | 8.382 | 423.690 |
| risk_adjusted | 100 | 1.000 | 0.998 | 0.807 | 0.269 | 0.831 | 603.617 | 0.587 | 6.036 | 501.883 |
| risk_adjusted | 125 | 1.000 | 1.000 | 0.961 | 0.562 | 0.923 | 578.617 | 0.562 | 4.629 | 533.879 |
| risk_adjusted | 150 | 1.000 | 1.000 | 0.993 | 0.818 | 0.971 | 553.617 | 0.538 | 3.691 | 537.354 |
| risk_adjusted | 200 | 1.000 | 1.000 | 1.000 | 0.982 | 0.997 | 503.617 | 0.489 | 2.518 | 502.229 |

- Bid que maximiza el EV ponderado (risk-adjusted): **150**.
- Menor bid dentro del 95% del EV máximo: **125**.
- Menor bid dentro del 90% del EV máximo: **100**.
- Bid robusto bajo escenario pesimista (95% del máximo high+stress): **150**.
- En el bid recomendado `125`, `q(b)` ponderado ≈ **92.3%** y el EV incremental risk-adjusted es **533.9**.

### Sensibilidad de la recomendación

| cutoff_median | 600.0 | 800.0 | 1000.0 | 1200.0 | 1600.0 | 2000.0 |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | 40 | 40 | 40 | 40 | 40 | 40 |
| 40 | 60 | 60 | 60 | 60 | 60 | 60 |
| 60 | 100 | 100 | 100 | 100 | 100 | 100 |
| 80 | 125 | 125 | 125 | 125 | 125 | 125 |
| 100 | 150 | 150 | 150 | 150 | 150 | 150 |
| 120 | 175 | 175 | 175 | 175 | 175 | 175 |
| 140 | 200 | 200 | 200 | 200 | 200 | 200 |

Lectura: la meseta de EV es bastante ancha. Por eso NO elijo el máximo puntual del EV sin más. Prefiero el menor bid que ya entra en esa meseta, porque eso captura casi todo el valor esperado sin regalar fee innecesario.

## F. Visualizaciones

Archivos generados en `/Users/pablo/Desktop/prosperity/round_2/results/kiko_maf_rigorous/plots/`:

1. `pnl_cumulative_baseline_vs_proxies.png` — compara PnL acumulado total y por producto; muestra que el uplift bajo proxies razonables es positivo pero moderado, y que ASH explica gran parte del gap.
2. `delta_cumulative_curve.png` — curva `Delta(t)` acumulada; permite ver cuándo nace el valor del extra access y si se acumula de forma frontal o más homogénea a lo largo del día.
3. `delta_incremental_blocks.png` — Delta incremental por bloques; sirve para detectar la caída del valor marginal y dónde se concentra el edge del MAF.
4. `pepper_inventory_trajectory.png` — trayectoria de inventario de PEPPER con líneas en 50/70/80; muestra que el extra access acelera algunos hitos, pero no cambia dramáticamente el régimen final.
5. `pepper_inventory_heatmap.png` — heatmap del tiempo por bin de inventario; cuantifica la saturación cerca de 70–80.
6. `delta_marginal_vs_inventory.png` — Delta marginal vs inventario baseline de PEPPER; ayuda a ver si el valor marginal cae cuando la posición ya está alta.
7. `bid_ev_curves.png` — EV incremental del bid por escenario de cutoff + mezcla ponderada; marca la meseta del 95%.
8. `acceptance_probability_by_bid.png` — `q(b)` por bid; visualiza el trade-off entre pagar más y comprar más probabilidad de aceptación.
9. `uplift_and_fee_roi_by_bid.png` — uplift % condicional y ROI del fee por bid; deja claro qué bids siguen siendo muy rentables si son aceptados.
10. `bid_sensitivity_heatmap.png` — sensibilidad del bid recomendado a `Delta_1M` y a la mediana del cutoff rival.
11. `delta_scaling_model_fit.png` — compara el `Delta(t)` normalizado con la mejor función de scaling dentro del día y con una recta lineal.

## G. Recomendación final

- **Bid recomendado:** `125`.
- **Intervalo alternativo razonable:** `100`–`150`.
- **Subiría el bid** hacia `150` si creés que el campo rival se parece más a los escenarios `high/stress` o si tenés evidencia externa de que los equipos van a pagar tres cifras.
- **Bajaría el bid** hacia `100` si querés minimizar fee y tu prior es que el cutoff real está bastante por debajo de 80.

Con estos resultados para `model_kiko`, el uplift neto condicional a ser aceptado es de **0.86%** a **1.44%** sobre baseline.
El ROI del fee es de **7.04x** a **11.88x**.
El bid robusto recomendado es **125**.
La principal razón es que el MAF sí agrega valor, pero en `model_kiko` ese valor es **moderado, no explosivo**, viene mayormente de **ASH/fill quality**, y la curva de EV es lo bastante plana como para priorizar robustez y no sobrepagar.