# Round 2 — análisis MAF para model_kiko con unidad estadística corregida

## A. Resumen ejecutivo

- Nueva unidad estadística usada: **1 día = 1 ronda comparable live**.
- `P0_d` total (TOTAL) — media **102,898.8**, mediana **103,370.5**, mínimo **101,456.0**.
- `Delta_central` por ronda: **1,609.8**.
- `Delta_conservative` por ronda: **1,005.2**.
- `Delta_downside` por ronda: **851.0**.
- Rango de bids razonable: **100–125**.
- Bid recomendado final: **`125`**.
- A `bid=125`, el uplift neto condicional es **0.86%** (conservative) a **1.44%** (central) sobre `P0_mean`.

## B. Corrección metodológica

### Por qué `día = ronda`

| source | official_day_count | official_days | official_products | activity_rows | activity_rows_per_product | decision_timestamps | timestamp_min | timestamp_max | timestamp_step | engine_log_rows | trade_history_rows | submission_trade_rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| /Users/pablo/Desktop/prosperity/round_1/official_result.log | 1 | 1 | ASH_COATED_OSMIUM,INTARIAN_PEPPER_ROOT | 20000 | 10000 | 10000 | 0 | 999900 | 100 | 10000 | 1352 | 1225 |

El `official_result.log` de Round 1 confirma una sola sesión oficial con 10,000 decision timestamps (`0 -> 999900`, step 100). Los CSV locales de Round 2 tienen exactamente esa estructura por día. Por lo tanto, cada día de Round 2 es el análogo correcto de una ronda live completa.

### Por qué NO agregar 3 días como una sola ronda

Agregar tres días como si fueran una única sesión cambia la unidad de decisión del bid y mezcla paths independientes. El fee se paga una sola vez por ronda oficial, así que la variable relevante es el valor del extra access **por día/path**, no el total concatenado de tres paths distintos.

### Por qué NO reescalar a 1M timestamps

No hace falta reescalar temporalmente: cada día ya cubre el horizonte oficial comparable (`0 -> 999900`). La proyección correcta es **cross-sectional entre días**, no una multiplicación artificial por tiempo.

## C. Resultados por día

### Baseline por día (`P0_d`)

| day | product_label | P0_d | drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position | pct_time_abs_ge_70 | pct_time_at_limit | time_to_50 | time_to_70 | time_to_80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| -1 | ASH | 22167.000 | -1620.000 | 669.000 | 0.665 | 5.679 | 41.554 | 0.071 | 0.024 |  |  |  |
| -1 | PEPPER | 81203.500 | -1360.000 | 500.000 | 0.390 | 5.294 | 73.054 | 0.706 | 0.306 | 2700.000 | 5700.000 | 12600.000 |
| -1 | TOTAL | 103370.500 | -1825.500 | 1169.000 | 0.547 | 5.514 |  |  |  |  |  |  |
| 0 | ASH | 22848.000 | -1600.000 | 680.000 | 0.674 | 5.688 | 17.929 | 0.029 | 0.010 |  |  |  |
| 0 | PEPPER | 81022.000 | -1520.000 | 516.000 | 0.370 | 5.457 | 71.387 | 0.647 | 0.238 | 1000.000 | 9900.000 | 14400.000 |
| 0 | TOTAL | 103870.000 | -1850.000 | 1196.000 | 0.543 | 5.589 |  |  |  |  |  |  |
| 1 | ASH | 21818.000 | -1600.000 | 678.000 | 0.661 | 5.695 | 21.625 | 0.038 | 0.017 |  |  |  |
| 1 | PEPPER | 79638.000 | -1680.000 | 523.000 | 0.388 | 5.415 | 67.968 | 0.544 | 0.226 | 14400.000 | 19900.000 | 23100.000 |
| 1 | TOTAL | 101456.000 | -1710.000 | 1201.000 | 0.542 | 5.573 |  |  |  |  |  |  |

### `P0_d`, `P1_d`, `Delta_d` por día — TOTAL

| day | scenario_label | P0_d | P1_d | Delta_d | fill_count_change | maker_share_change | avg_fill_size_change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -1 | Uniform depth +25% | 103370.500 | 104346.500 | 976.000 | -10.000 | -0.002 | 0.712 |
| 0 | Uniform depth +25% | 103870.000 | 104721.000 | 851.000 | -13.000 | 0.001 | 0.695 |
| 1 | Uniform depth +25% | 101456.000 | 102644.500 | 1188.500 | -7.000 | -0.001 | 0.724 |
| -1 | Front-biased depth +25% | 103370.500 | 104968.000 | 1597.500 | -10.000 | -0.004 | 1.213 |
| 0 | Front-biased depth +25% | 103870.000 | 105190.000 | 1320.000 | -19.000 | 0.002 | 1.226 |
| 1 | Front-biased depth +25% | 101456.000 | 103368.000 | 1912.000 | -8.000 | -0.005 | 1.257 |
| -1 | Depth +25% + trades +25% | 103370.500 | 109785.500 | 6415.000 | -7.000 | -0.000 | 1.390 |
| 0 | Depth +25% + trades +25% | 103870.000 | 110080.000 | 6210.000 | -10.000 | -0.000 | 1.408 |
| 1 | Depth +25% + trades +25% | 101456.000 | 108322.500 | 6866.500 | -6.000 | -0.003 | 1.451 |

### `Delta_d` por producto y microestructura

| day | scenario_label | product_label | P0_d | P1_d | Delta_d | fill_count_change | maker_share_change | avg_fill_size_change | avg_abs_position_change | time_to_70_change | time_to_80_change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| -1 | Uniform depth +25% | ASH | 22167.000 | 23041.000 | 874.000 | 0.000 | -0.004 | 0.571 | -1.090 |  |  |
| -1 | Uniform depth +25% | PEPPER | 81203.500 | 81305.500 | 102.000 | -10.000 | -0.002 | 0.900 | -0.206 | 0.000 | -1300.000 |
| 0 | Uniform depth +25% | ASH | 22848.000 | 23530.000 | 682.000 | -4.000 | 0.003 | 0.547 | 0.820 |  |  |
| 0 | Uniform depth +25% | PEPPER | 81022.000 | 81191.000 | 169.000 | -9.000 | -0.003 | 0.890 | -0.128 | 0.000 | -1800.000 |
| 1 | Uniform depth +25% | ASH | 21818.000 | 22505.000 | 687.000 | 1.000 | -0.002 | 0.579 | 2.176 |  |  |
| 1 | Uniform depth +25% | PEPPER | 79638.000 | 80139.500 | 501.500 | -8.000 | -0.002 | 0.913 | 0.312 | -2500.000 | -3200.000 |
| -1 | Front-biased depth +25% | ASH | 22167.000 | 23721.000 | 1554.000 | 0.000 | -0.006 | 1.037 | -2.302 |  |  |
| -1 | Front-biased depth +25% | PEPPER | 81203.500 | 81247.000 | 43.500 | -10.000 | -0.004 | 1.449 | -0.514 | -3000.000 | -6900.000 |
| 0 | Front-biased depth +25% | ASH | 22848.000 | 24166.000 | 1318.000 | -3.000 | 0.002 | 1.005 | 2.951 |  |  |
| 0 | Front-biased depth +25% | PEPPER | 81022.000 | 81024.000 | 2.000 | -16.000 | -0.002 | 1.523 | -0.715 | -7200.000 | -4500.000 |
| 1 | Front-biased depth +25% | ASH | 21818.000 | 23147.000 | 1329.000 | 3.000 | -0.006 | 1.057 | 2.956 |  |  |
| 1 | Front-biased depth +25% | PEPPER | 79638.000 | 80221.000 | 583.000 | -11.000 | -0.007 | 1.519 | 0.072 | -2500.000 | -3200.000 |
| -1 | Depth +25% + trades +25% | ASH | 22167.000 | 27594.000 | 5427.000 | 0.000 | -0.003 | 1.365 | -1.968 |  |  |
| -1 | Depth +25% + trades +25% | PEPPER | 81203.500 | 82191.500 | 988.000 | -7.000 | 0.001 | 1.422 | -1.017 | 0.000 | 1800.000 |
| 0 | Depth +25% + trades +25% | ASH | 22848.000 | 28159.000 | 5311.000 | -4.000 | 0.001 | 1.383 | 1.838 |  |  |
| 0 | Depth +25% + trades +25% | PEPPER | 81022.000 | 81921.000 | 899.000 | -6.000 | -0.003 | 1.441 | -1.122 | 0.000 | -1800.000 |
| 1 | Depth +25% + trades +25% | ASH | 21818.000 | 26855.000 | 5037.000 | 1.000 | -0.004 | 1.398 | 2.136 |  |  |
| 1 | Depth +25% + trades +25% | PEPPER | 79638.000 | 81467.500 | 1829.500 | -7.000 | -0.004 | 1.517 | -0.395 | -2500.000 | -3200.000 |

### Resumen entre días de `Delta_d` (TOTAL)

| proxy | Delta_mean | Delta_median | Delta_min | Delta_max | Delta_std | Delta_p25 |
| --- | --- | --- | --- | --- | --- | --- |
| Uniform depth +25% | 1005.167 | 976.000 | 851.000 | 1188.500 | 170.630 | 913.500 |
| Front-biased depth +25% | 1609.833 | 1597.500 | 1320.000 | 1912.000 | 296.193 | 1458.750 |
| Depth +25% + trades +25% | 6497.167 | 6415.000 | 6210.000 | 6866.500 | 335.874 | 6312.500 |

## D. Robustez entre días

### Dispersión de `P0_d` y `Delta_d`

| product | P0_mean | P0_median | P0_min | P0_max | P0_std | P0_cv | P0_p25 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ASH | 22277.667 | 22167.000 | 21818.000 | 22848.000 | 523.842 | 0.024 | 21992.500 |
| PEPPER | 80621.167 | 81022.000 | 79638.000 | 81203.500 | 856.270 | 0.011 | 80330.000 |
| TOTAL | 102898.833 | 103370.500 | 101456.000 | 103870.000 | 1274.245 | 0.012 | 102413.250 |

### Análisis por día para bids 100 / 125 / 150 (proxy conservador)

| day | bid | P0_d | Delta_d | net_gain_if_accepted_d | uplift_pct_vs_base_d | fee_roi_d |
| --- | --- | --- | --- | --- | --- | --- |
| -1.000 | 100.000 | 103370.500 | 976.000 | 876.000 | 0.008 | 8.760 |
| -1.000 | 125.000 | 103370.500 | 976.000 | 851.000 | 0.008 | 6.808 |
| -1.000 | 150.000 | 103370.500 | 976.000 | 826.000 | 0.008 | 5.507 |
| 0.000 | 100.000 | 103870.000 | 851.000 | 751.000 | 0.007 | 7.510 |
| 0.000 | 125.000 | 103870.000 | 851.000 | 726.000 | 0.007 | 5.808 |
| 0.000 | 150.000 | 103870.000 | 851.000 | 701.000 | 0.007 | 4.673 |
| 1.000 | 100.000 | 101456.000 | 1188.500 | 1088.500 | 0.011 | 10.885 |
| 1.000 | 125.000 | 101456.000 | 1188.500 | 1063.500 | 0.010 | 8.508 |
| 1.000 | 150.000 | 101456.000 | 1188.500 | 1038.500 | 0.010 | 6.923 |

### Leave-one-day-out (proxy conservador)

| days | P0_mean_subset | Delta_mean_subset | best_bid | smallest_bid_95pct | smallest_bid_90pct |
| --- | --- | --- | --- | --- | --- |
| -1,0 | 103620.250 | 913.500 | 175 | 125 | 100 |
| -1,1 | 102413.250 | 1082.250 | 175 | 125 | 125 |
| 0,1 | 102663.000 | 1019.750 | 175 | 125 | 100 |

### Worst-day analysis

| day | bid | P0_d | Delta_d | net_gain_if_accepted | uplift_pct_vs_base | fee_roi | EV_uplift_weighted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.000 | 100.000 | 103870.000 | 851.000 | 751.000 | 0.007 | 7.510 | 607.558 |
| 0.000 | 125.000 | 103870.000 | 851.000 | 726.000 | 0.007 | 5.808 | 643.583 |
| 0.000 | 150.000 | 103870.000 | 851.000 | 701.000 | 0.007 | 4.673 | 659.892 |

En el peor día observado, con `bid=125`, `Delta_d - b = 726.0`, uplift neto = **0.70%**, fee ROI = **5.81x**.

### Comparación de variantes risk-adjusted

| variant | definition | value | comment |
| --- | --- | --- | --- |
| Delta_RA_1 | 0.7 * Delta_conservative | 703.617 | Haircut legacy; útil como comparación pero arbitrario. |
| Delta_RA_2 | min daily Delta_conservative | 851.000 | Stress observado más transparente; lo uso como guardrail principal. |
| Delta_RA_3 | p25 daily Delta_conservative | 913.500 | Cuantil downside interesante, pero con n=3 depende mucho de interpolación. |

Mi lectura: `RA_1` sirve solo como benchmark histórico porque el haircut es arbitrario. `RA_3` es interesante, pero con 3 días el percentil 25 depende demasiado de interpolación. La mejor variante para un guardrail de decisión es **`RA_2 = min daily Delta_conservative`**: es simple, observable y directamente alineada con la pregunta de robustez por ronda.

## E. Game theory del cutoff

Escenarios de cutoff asumidos:

| escenario | median_bid | slope | weight | lectura |
| --- | --- | --- | --- | --- |
| Competencia baja | 20.000 | 6.000 | 0.150 | Cutoff bajo, bids rivales en la zona de 20. |
| Central | 45.000 | 9.000 | 0.400 | Escenario base: cutoff alrededor de 45. |
| Competencia alta | 80.000 | 14.000 | 0.300 | Escenario competitivo serio: bids relevantes ya están en 70-100. |
| Stress | 140.000 | 20.000 | 0.150 | Stress duro: cutoff rival muy alto, empuja a considerar 150+ si la prioridad es aceptación. |

### `q(b)` por bid

| bid | q_low | q_central | q_high | q_stress | q_weighted |
| --- | --- | --- | --- | --- | --- |
| 0.000 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 |
| 10.000 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 |
| 20.000 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 |
| 30.000 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 |
| 40.000 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 |
| 50.000 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 |
| 60.000 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 |
| 75.000 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 |
| 100.000 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 |
| 125.000 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 |
| 150.000 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 |
| 175.000 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 |
| 200.000 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 |

### EV por bid y variante de Delta

| delta_label | bid | q_low | q_central | q_high | q_stress | q_weighted | net_gain_if_accepted | uplift_pct_vs_base | fee_roi | EV_uplift_weighted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Delta_central | 0 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 | 1609.833 | 1.564 |  | 14.435 |
| Delta_central | 10 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 | 1599.833 | 1.555 | 159.983 | 54.533 |
| Delta_central | 20 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 | 1589.833 | 1.545 | 79.492 | 163.528 |
| Delta_central | 30 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 | 1579.833 | 1.535 | 52.661 | 313.647 |
| Delta_central | 40 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 | 1569.833 | 1.526 | 39.246 | 483.449 |
| Delta_central | 50 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 | 1559.833 | 1.516 | 31.197 | 680.577 |
| Delta_central | 60 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 | 1549.833 | 1.506 | 25.831 | 847.691 |
| Delta_central | 75 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 | 1534.833 | 1.492 | 20.464 | 1021.126 |
| Delta_central | 100 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 | 1509.833 | 1.467 | 15.098 | 1221.453 |
| Delta_central | 125 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 | 1484.833 | 1.443 | 11.879 | 1316.273 |
| Delta_central | 150 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 | 1459.833 | 1.419 | 9.732 | 1374.225 |
| Delta_central | 175 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 | 1434.833 | 1.394 | 8.199 | 1402.484 |
| Delta_central | 200 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 | 1409.833 | 1.370 | 7.049 | 1399.724 |
| Delta_conservative | 0 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 | 1005.167 | 0.977 |  | 9.013 |
| Delta_conservative | 10 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 | 995.167 | 0.967 | 99.517 | 33.922 |
| Delta_conservative | 20 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 | 985.167 | 0.957 | 49.258 | 101.333 |
| Delta_conservative | 30 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 | 975.167 | 0.948 | 32.506 | 193.602 |
| Delta_conservative | 40 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 | 965.167 | 0.938 | 24.129 | 297.234 |
| Delta_conservative | 50 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 | 955.167 | 0.928 | 19.103 | 416.752 |
| Delta_conservative | 60 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 | 945.167 | 0.919 | 15.753 | 516.965 |
| Delta_conservative | 75 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 | 930.167 | 0.904 | 12.402 | 618.841 |
| Delta_conservative | 100 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 | 905.167 | 0.880 | 9.052 | 732.278 |
| Delta_conservative | 125 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 | 880.167 | 0.855 | 7.041 | 780.249 |
| Delta_conservative | 150 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 | 855.167 | 0.831 | 5.701 | 805.018 |
| Delta_conservative | 175 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 | 830.167 | 0.807 | 4.744 | 811.450 |
| Delta_conservative | 200 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 | 805.167 | 0.782 | 4.026 | 799.393 |
| Delta_downside | 0 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 | 851.000 | 0.827 |  | 7.631 |
| Delta_downside | 10 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 | 841.000 | 0.817 | 84.100 | 28.667 |
| Delta_downside | 20 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 | 831.000 | 0.808 | 41.550 | 85.476 |
| Delta_downside | 30 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 | 821.000 | 0.798 | 27.367 | 162.995 |
| Delta_downside | 40 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 | 811.000 | 0.788 | 20.275 | 249.757 |
| Delta_downside | 50 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 | 801.000 | 0.778 | 16.020 | 349.487 |
| Delta_downside | 60 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 | 791.000 | 0.769 | 13.183 | 432.642 |
| Delta_downside | 75 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 | 776.000 | 0.754 | 10.347 | 516.273 |
| Delta_downside | 100 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 | 751.000 | 0.730 | 7.510 | 607.558 |
| Delta_downside | 125 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 | 726.000 | 0.706 | 5.808 | 643.583 |
| Delta_downside | 150 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 | 701.000 | 0.681 | 4.673 | 659.892 |
| Delta_downside | 175 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 | 676.000 | 0.657 | 3.863 | 660.759 |
| Delta_downside | 200 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 | 651.000 | 0.633 | 3.255 | 646.332 |
| Delta_RA_1 | 0 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 | 703.617 | 0.684 |  | 6.309 |
| Delta_RA_1 | 10 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 | 693.617 | 0.674 | 69.362 | 23.643 |
| Delta_RA_1 | 20 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 | 683.617 | 0.664 | 34.181 | 70.316 |
| Delta_RA_1 | 30 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 | 673.617 | 0.655 | 22.454 | 133.734 |
| Delta_RA_1 | 40 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 | 663.617 | 0.645 | 16.590 | 204.369 |
| Delta_RA_1 | 50 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 | 653.617 | 0.635 | 13.072 | 285.182 |
| Delta_RA_1 | 60 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 | 643.617 | 0.625 | 10.727 | 352.030 |
| Delta_RA_1 | 75 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 | 628.617 | 0.611 | 8.382 | 418.219 |
| Delta_RA_1 | 100 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 | 603.617 | 0.587 | 6.036 | 488.325 |
| Delta_RA_1 | 125 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 | 578.617 | 0.562 | 4.629 | 512.931 |
| Delta_RA_1 | 150 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 | 553.617 | 0.538 | 3.691 | 521.151 |
| Delta_RA_1 | 175 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 | 528.617 | 0.514 | 3.021 | 516.699 |
| Delta_RA_1 | 200 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 | 503.617 | 0.489 | 2.518 | 500.005 |
| Delta_RA_2 | 0 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 | 851.000 | 0.827 |  | 7.631 |
| Delta_RA_2 | 10 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 | 841.000 | 0.817 | 84.100 | 28.667 |
| Delta_RA_2 | 20 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 | 831.000 | 0.808 | 41.550 | 85.476 |
| Delta_RA_2 | 30 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 | 821.000 | 0.798 | 27.367 | 162.995 |
| Delta_RA_2 | 40 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 | 811.000 | 0.788 | 20.275 | 249.757 |
| Delta_RA_2 | 50 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 | 801.000 | 0.778 | 16.020 | 349.487 |
| Delta_RA_2 | 60 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 | 791.000 | 0.769 | 13.183 | 432.642 |
| Delta_RA_2 | 75 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 | 776.000 | 0.754 | 10.347 | 516.273 |
| Delta_RA_2 | 100 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 | 751.000 | 0.730 | 7.510 | 607.558 |
| Delta_RA_2 | 125 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 | 726.000 | 0.706 | 5.808 | 643.583 |
| Delta_RA_2 | 150 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 | 701.000 | 0.681 | 4.673 | 659.892 |
| Delta_RA_2 | 175 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 | 676.000 | 0.657 | 3.863 | 660.759 |
| Delta_RA_2 | 200 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 | 651.000 | 0.633 | 3.255 | 646.332 |
| Delta_RA_3 | 0 | 0.034 | 0.007 | 0.003 | 0.001 | 0.009 | 913.500 | 0.888 |  | 8.191 |
| Delta_RA_3 | 10 | 0.159 | 0.020 | 0.007 | 0.002 | 0.034 | 903.500 | 0.878 | 90.350 | 30.797 |
| Delta_RA_3 | 20 | 0.500 | 0.059 | 0.014 | 0.002 | 0.103 | 893.500 | 0.868 | 44.675 | 91.904 |
| Delta_RA_3 | 30 | 0.841 | 0.159 | 0.027 | 0.004 | 0.199 | 883.500 | 0.859 | 29.450 | 175.403 |
| Delta_RA_3 | 40 | 0.966 | 0.365 | 0.054 | 0.007 | 0.308 | 873.500 | 0.849 | 21.837 | 269.005 |
| Delta_RA_3 | 50 | 0.993 | 0.635 | 0.105 | 0.011 | 0.436 | 863.500 | 0.839 | 17.270 | 376.757 |
| Delta_RA_3 | 60 | 0.999 | 0.841 | 0.193 | 0.018 | 0.547 | 853.500 | 0.829 | 14.225 | 466.827 |
| Delta_RA_3 | 75 | 1.000 | 0.966 | 0.412 | 0.037 | 0.665 | 838.500 | 0.815 | 11.180 | 557.855 |
| Delta_RA_3 | 100 | 1.000 | 0.998 | 0.807 | 0.119 | 0.809 | 813.500 | 0.791 | 8.135 | 658.120 |
| Delta_RA_3 | 125 | 1.000 | 1.000 | 0.961 | 0.321 | 0.886 | 788.500 | 0.766 | 6.308 | 698.988 |
| Delta_RA_3 | 150 | 1.000 | 1.000 | 0.993 | 0.622 | 0.941 | 763.500 | 0.742 | 5.090 | 718.727 |
| Delta_RA_3 | 175 | 1.000 | 1.000 | 0.999 | 0.852 | 0.977 | 738.500 | 0.718 | 4.220 | 721.850 |
| Delta_RA_3 | 200 | 1.000 | 1.000 | 1.000 | 0.953 | 0.993 | 713.500 | 0.693 | 3.567 | 708.384 |

- Bid que maximiza EV medio (`Delta_central`): **175**.
- Menor bid dentro del 95% del EV máximo (`Delta_conservative`): **125**.
- Menor bid dentro del 90% del EV máximo (`Delta_conservative`): **100**.
- Mejor bid en downside (`Delta_downside`): **175**.
- Mejor bid en worst-day guardrail (`Delta_RA_2`): **175**.

## F. Visualizaciones

Plots generados en `/Users/pablo/Desktop/prosperity/round_2/results/kiko_maf_day_unit/plots/`:

1. `p0_p1_by_day.png` — compara P0_d y P1_d por día; ayuda a ver cuánto cambia el valor por ronda real.
2. `delta_by_day.png` — muestra `Delta_d` por día y proxy; sirve para ver dispersión y estabilidad entre rondas.
3. `delta_violin.png` — resume la distribución de `Delta_d`; útil para comparar central tendency vs downside.
4. `pnl_cumulative_by_day.png` — compara PnL acumulado baseline vs proxies para cada día/path.
5. `delta_cumulative_by_day.png` — muestra dónde aparece el valor del extra access dentro de cada ronda.
6. `pepper_inventory_by_day.png` — permite ver si el proxy central acelera llegar a 50/70/80 en PEPPER y cuánto cambia realmente la trayectoria.
7. `bid_ev_curves.png` — combina EV por bid según variante de Delta y según escenario de cutoff.
8. `acceptance_probability_qb.png` — visualiza `q(b)` por escenario rival.
9. `uplift_fee_roi_by_bid.png` — muestra uplift % y ROI del fee, con foco visual en 100 / 125 / 150.
10. `bid_sensitivity_heatmap.png` — heatmap Delta asumido vs cutoff rival; ayuda a ver cuándo la recomendación se movería de 125 hacia 150.

## G. Recomendación final

- Bid recomendado: **`125`**.
- Rango alternativo razonable: **`100`–`125`**.
- Subiría a `150` si tu prior es que el cutoff real está mucho más cerca del escenario `stress` y querés comprar probabilidad de aceptación aun pagando más.
- Bajaría a `100` si querés minimizar fee y asumís que el cutoff real se parece más a `low/central`.

Tratando cada día como una ronda independiente, el valor del extra access para `model_kiko` es de **851.0 a 1,609.8 por ronda**, con estimación conservadora media de **1,005.2**.
En el peor día, el uplift neto con bid 125 es **0.70%** y el fee ROI es **5.81x**.
El bid 125 **sí sigue siendo robusto** cuando la unidad estadística correcta es `día = ronda`.
La razón principal es que el MAF sigue generando Delta positivo en los tres días, el worst-day sigue dejando margen amplio después de pagar 125, y 125 cae consistentemente dentro de la meseta del 95% del EV sin exigir pagar de más como reacción automática.