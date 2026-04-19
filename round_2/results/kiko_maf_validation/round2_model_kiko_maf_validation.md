# Validación final y revisión crítica del MAF de Round 2 para `model_kiko`

## A. Resumen ejecutivo

- Resultado de la revisión: **la recomendación de `125` ya NO sale robusta** una vez que se modela bunching discreto rival en `125` y `150`.
- Bid final recomendado: **`150`**.
- Rango alternativo: **`125–150`**.
- ¿`125` aguanta o no? **Aguanta como opción prudente de costo, pero deja de ser la mejor opción robusta global**.

## B. Revisión metodológica crítica

### Fortalezas
- La unidad estadística correcta sigue siendo `1 día = 1 ronda comparable live`.
- `Delta` está anclado en datos observados por día y tiene downside explícito (`Delta_downside = 851`).
- La comparación `100/125/150` ya no depende solo de una logística suave: ahora incluye bunching discreto y desempate en el cutoff.

### Debilidades
- La parte más frágil sigue siendo `q(b)`, no `Delta`.
- Los escenarios discretos rivales son plausibles, pero siguen siendo modelados; no observamos bids reales.
- El tamaño real del field y la regla exacta de desempate no son conocidos; acá se normalizó a 100 participantes y tie-break uniforme.

### Riesgos residuales
- Si el field real NO presenta bunching importante, el premium de `150` puede terminar siendo sobrepago.
- Si sí hay bunching en `125` o `150`, el costo de quedarse en `125` puede ser grande en aceptación y EV.

## C. Tests adicionales

### Stress Delta
| stress_pct | 100 | 125 | 150 |
| --- | --- | --- | --- |
| 0.0 | 732.28 | 780.25 | 805.02 |
| 0.1 | 650.96 | 691.14 | 710.4 |
| 0.2 | 569.64 | 602.04 | 615.77 |
| 0.3 | 488.32 | 512.93 | 521.15 |
| 0.4 | 407.01 | 423.83 | 426.53 |

Hallazgos:
- `125` sigue superando a `100` incluso con haircut de 40%.
- `150` deja de tener ventaja clara sobre `125` cuando `Delta` cae hacia `~553.8`.
- O sea: por Delta solo, `125` se defiende bastante bien.

### Stress q(b)
| stress_pct | 100 | 125 | 150 |
| --- | --- | --- | --- |
| 0.0 | 732.28 | 780.25 | 805.02 |
| 0.05 | 695.66 | 741.24 | 764.77 |
| 0.1 | 659.05 | 702.22 | 724.52 |
| 0.15 | 622.44 | 663.21 | 684.27 |

Hallazgo:
- Un haircut uniforme en `q(b)` no cambia el ranking; el problema real es la **forma** de `q(b)` cuando aparece bunching.

### Worst-case combo
| scenario | scenario_label | q_penalty | bid | q_base_discrete | q_used | delta_assumed | net_gain_if_accepted | uplift_pct_vs_base | fee_roi | ev_uplift | ev_total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C_masa_150 | Escenario C — masa en 150 | 0.15 | 100 | 0.0 | 0.0 | 851.0 | 751.0 | 0.0073 | 7.51 | 0.0 | 102898.8333 |
| C_masa_150 | Escenario C — masa en 150 | 0.15 | 125 | 0.0204 | 0.0174 | 851.0 | 726.0 | 0.0071 | 5.808 | 12.602 | 102911.4354 |
| C_masa_150 | Escenario C — masa en 150 | 0.15 | 150 | 0.8451 | 0.7184 | 851.0 | 701.0 | 0.0068 | 4.6733 | 503.5758 | 103402.4091 |

Resultado:
- En el combo duro (`Delta_downside` + masa en `150` + penalización adicional de q), **`150` domina claramente**.

### Gap marginal de EV
| context | ev_125_minus_100 | ev_150_minus_125 | q_125_minus_100 | q_150_minus_125 |
| --- | --- | --- | --- | --- |
| Logistic mix (weighted) — Delta_conservative | 47.97 | 24.769 | 0.077 | 0.055 |
| Escenario A — masa en 100 — Delta_conservative | 352.115 | -25.0 | 0.417 | 0.0 |
| Escenario B — masa en 125 — Delta_conservative | 722.111 | 111.085 | 0.821 | 0.155 |
| Escenario C — masa en 150 — Delta_conservative | 17.974 | 704.76 | 0.02 | 0.825 |
| Escenario D — mezcla heterogénea — Delta_conservative | 728.396 | 26.92 | 0.831 | 0.059 |

Lectura:
- En el modelo logístico original, el salto `125 -> 150` compraba solo **0.055** de aceptación extra y **24.8** de EV adicional.
- Pero bajo bunching en `125`, ese salto compra **0.155** de aceptación y **111.1** de EV.
- Bajo bunching en `150`, ese salto compra **0.825** de aceptación y **704.8** de EV.
- Esto cambia mucho la historia: **si bunching agresivo es plausible, `150` funciona como seguro, no como mero lujo**.

## D. Distribución esperada de bids rivales

### Cutoff inducido
| scenario | scenario_label | cutoff_mean | cutoff_median | cutoff_p25 | cutoff_p75 |
| --- | --- | --- | --- | --- | --- |
| A_masa_100 | Escenario A — masa en 100 | 99.98 | 100.0 | 100.0 | 100.0 |
| B_masa_125 | Escenario B — masa en 125 | 121.65 | 125.0 | 125.0 | 125.0 |
| C_masa_150 | Escenario C — masa en 150 | 146.66 | 150.0 | 150.0 | 150.0 |
| D_mixto | Escenario D — mezcla heterogénea | 110.87 | 100.0 | 100.0 | 125.0 |

### Impacto sobre 100 / 125 / 150
| scenario_label | bid | q_accept | ev_uplift_conservative | ev_uplift_downside |
| --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | 100 | 0.5834 | 528.0516 | 438.1146 |
| Escenario A — masa en 100 | 125 | 1.0 | 880.1665 | 725.9998 |
| Escenario A — masa en 100 | 150 | 1.0 | 855.1667 | 701.0 |
| Escenario B — masa en 125 | 100 | 0.0243 | 21.97 | 18.2281 |
| Escenario B — masa en 125 | 125 | 0.8454 | 744.0813 | 613.7508 |
| Escenario B — masa en 125 | 150 | 1.0 | 855.1667 | 701.0 |
| Escenario C — masa en 150 | 100 | 0.0 | 0.0 | 0.0 |
| Escenario C — masa en 150 | 125 | 0.0204 | 17.9742 | 14.8259 |
| Escenario C — masa en 150 | 150 | 0.8451 | 722.7343 | 592.4421 |
| Escenario D — mezcla heterogénea | 100 | 0.1103 | 99.8512 | 82.8447 |
| Escenario D — mezcla heterogénea | 125 | 0.941 | 828.2467 | 683.1741 |
| Escenario D — mezcla heterogénea | 150 | 1.0 | 855.1667 | 701.0 |

Lectura:
- Escenario A (masa en 100): `125` gana por poco sobre `150` (~25 EV de ventaja).
- Escenario B (masa en 125): `150` supera a `125` por ~111 EV.
- Escenario C (masa en 150): `150` aplasta a `125` por ~705 EV.
- Escenario D (mezcla): `150` vuelve a superar a `125`, pero por un gap chico (~27 EV).

## E. Visualizaciones

Plots generados en `/Users/pablo/Desktop/prosperity/round_2/results/kiko_maf_validation/plots/`:
- `rival_bid_distribution.png`
- `induced_cutoff_distribution.png`
- `ev_100_125_150_by_scenario.png`
- `marginal_ev_increment.png`
- `acceptance_by_bid_discrete.png`
- `final_sensitivity_heatmap.png`

Interpretación clave:
- La distribución rival muestra claramente si `125` queda en zona congestionada.
- La distribución del cutoff inducido hace visible cuándo `150` cruza de “sobrepago” a “seguro útil”.
- El mapa de sensibilidad deja algo fuerte: con estos escenarios discretos, **solo el escenario A deja a `125` como mejor bid; en B/C/D gana `150` para todo Delta razonable**.

## F. Recomendación final

### Mejor bid por criterio
| criterion | bid |
| --- | --- |
| best_bid_ev_mean_discrete | 150 |
| best_bid_downside_discrete | 150 |
| best_bid_bunching_125 | 150 |
| best_bid_bunching_150 | 150 |
| best_bid_worst_case_combo | 150 |
| robust_global_bid | 150 |

### Recomendación
- **Bid recomendado: `150`**.
- **Cuándo elegir `100`**: solo si creés que el field es suave y la masa principal está claramente en `100`, y querés minimizar fee por encima de todo.
- **Cuándo elegir `125`**: si seguís pensando que el modelo logístico original describe mejor el field que los escenarios con bunching; o sea, si le asignás baja probabilidad al amontonamiento en `125` y sobre todo en `150`.
- **Cuándo elegir `150`**: si querés robustez frente a bunching rival y cutoff duro. Con los escenarios discretos de esta validación, `150` pasa a ser la mejor cobertura global.

### Veredicto final

Después de revisar el análisis y modelar la distribución esperada de bids rivales con bunching, **el bid `125` no sigue siendo la mejor opción robusta**.

La principal razón es que, una vez que se permite concentración rival en números focales, **la forma de `q(b)` cambia mucho**:
- pasar de `125` a `150` compra aproximadamente **0.055** de probabilidad adicional y **24.8** de EV en el modelo logístico original,
- pero compra **0.155 / 111 EV** si el crowd se amontona en `125`,
- y compra **0.825 / 705 EV** si el crowd se amontona en `150`.

Entonces, si tomás en serio el riesgo de bunching rival, **`150` pasa de “sobrepago marginal” a “seguro robusto contra quedarse fuera”**.
