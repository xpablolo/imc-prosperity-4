# Round 2 — MAF model heterogeneity y rival model switching

## A. Resumen ejecutivo

- **Sí**: el MAF vale bastante más para varios modelos del repo que para `model_kiko`.
- En la unidad correcta (**1 día = 1 ronda live comparable**), `model_kiko` tiene el mejor baseline medio, pero el **menor Delta conservador** del set auditado.
- Los modelos más sensibles al MAF son `model_G2`, `model_G5` y `model_G4`; el uplift adicional viene **sobre todo de PEPPER**, no de ASH.
- **No** veo evidencia de que sea racional pasar de `model_kiko` a esos modelos *solo* por el MAF: el gap de baseline de `model_kiko` sigue siendo demasiado grande.
- **Sí** veo evidencia de que un field heterogéneo, con equipos ya parados sobre modelos tipo `G5/G2`, puede empujar el cutoff rival hacia arriba.
- Implicación práctica: el análisis anterior de cutoff homogéneo probablemente **subestima la cola alta**. Eso vuelve mucho menos defendible `125`, complica `150`, hace que `175` sea el nuevo piso serio y mete a `200` en consideración real.

### Comparativa corta

| model | P0_mean | Delta_conservative_mean | Delta_conservative_min | Delta_central_mean | cons_uplift_pct | sensitivity_class |
| --- | --- | --- | --- | --- | --- | --- |
| model_kiko | 102898.83 | 1005.17 | 851.00 | 1609.83 | 0.98 | MAF-light |
| model_G5 | 101269.00 | 1641.50 | 1457.00 | 2335.50 | 1.62 | MAF-heavy |
| model_G1 | 101222.67 | 1467.17 | 1230.00 | 2285.17 | 1.45 | MAF-medium |
| model_G4 | 101021.00 | 1610.83 | 1332.00 | 2455.67 | 1.59 | MAF-heavy |
| model_G2 | 100767.67 | 1723.67 | 1432.00 | 2666.50 | 1.71 | MAF-heavy |
| model_F3 | 100646.83 | 1533.83 | 1380.00 | 2400.50 | 1.52 | MAF-medium |

## B. Comparativa entre modelos

### Baseline por modelo (TOTAL, por día)

| model | P0_mean | P0_median | P0_min | P0_max | P0_std |
| --- | --- | --- | --- | --- | --- |
| model_kiko | 102898.83 | 103370.50 | 101456.00 | 103870.00 | 1274.25 |
| model_G5 | 101269.00 | 101150.00 | 101103.00 | 101554.00 | 247.93 |
| model_G1 | 101222.67 | 101157.00 | 101045.00 | 101466.00 | 218.05 |
| model_G4 | 101021.00 | 100950.00 | 100910.00 | 101203.00 | 158.88 |
| model_G2 | 100767.67 | 100748.00 | 100575.00 | 100980.00 | 203.21 |
| model_F3 | 100646.83 | 100778.00 | 100273.50 | 100889.00 | 328.05 |

### Delta del MAF por modelo (TOTAL)

**Proxy conservador**

| model | Delta_mean | Delta_median | Delta_min | Delta_max | Delta_std | Delta_p25 |
| --- | --- | --- | --- | --- | --- | --- |
| model_G2 | 1723.67 | 1819.50 | 1432.00 | 1919.50 | 257.49 | 1625.75 |
| model_G5 | 1641.50 | 1619.00 | 1457.00 | 1848.50 | 196.72 | 1538.00 |
| model_G4 | 1610.83 | 1738.00 | 1332.00 | 1762.50 | 241.79 | 1535.00 |
| model_F3 | 1533.83 | 1514.00 | 1380.00 | 1707.50 | 164.65 | 1447.00 |
| model_G1 | 1467.17 | 1540.00 | 1230.00 | 1631.50 | 210.43 | 1385.00 |
| model_kiko | 1005.17 | 976.00 | 851.00 | 1188.50 | 170.63 | 913.50 |

**Proxy central**

| model | Delta_mean | Delta_median | Delta_min | Delta_max | Delta_std |
| --- | --- | --- | --- | --- | --- |
| model_G2 | 2666.50 | 2780.50 | 2333.00 | 2886.00 | 293.60 |
| model_G4 | 2455.67 | 2523.00 | 2251.00 | 2593.00 | 180.67 |
| model_F3 | 2400.50 | 2277.00 | 2199.50 | 2725.00 | 283.68 |
| model_G5 | 2335.50 | 2338.00 | 2099.50 | 2569.00 | 234.76 |
| model_G1 | 2285.17 | 2195.50 | 2068.00 | 2592.00 | 273.27 |
| model_kiko | 1609.83 | 1597.50 | 1320.00 | 1912.00 | 296.19 |

### Lectura económica

- `model_kiko` sigue siendo el **baseline leader** del set: gana más sin access extra.
- Pero es **MAF-light**: su `Delta_conservative_mean` queda claramente por debajo del resto.
- Los modelos `G/F` auditados son más **PEPPER-sensitive** al extra access: su mejora marginal con MAF viene mucho más por PEPPER que en `model_kiko`.
- Eso significa que, aunque `model_kiko` sea mejor estrategia base, **otros equipos pueden tener un valor privado del access bastante mayor** si están usando otra familia de modelos.

## C. Incentivo a cambio de modelo

### Switch contra `model_kiko`

| model | P0_gap_vs_kiko | Delta_cons_gap_vs_kiko | q_star_cons_to_match_kiko | q_star_cent_to_match_kiko | switch_from_kiko_justified_cons | switch_from_kiko_justified_cent |
| --- | --- | --- | --- | --- | --- | --- |
| model_G2 | 2131.17 | 718.50 | 2.97 | 2.02 | False | False |
| model_G5 | 1629.83 | 636.33 | 2.56 | 2.25 | False | False |
| model_G4 | 1877.83 | 605.67 | 3.10 | 2.22 | False | False |
| model_F3 | 2252.00 | 528.67 | 4.26 | 2.85 | False | False |
| model_G1 | 1676.17 | 462.00 | 3.63 | 2.48 | False | False |

### Frontera baseline vs Delta conservador

| model | on_frontier | dominated_by |
| --- | --- | --- |
| model_kiko | True |  |
| model_G5 | True |  |
| model_G1 | False | model_G5 |
| model_G4 | False | model_G5 |
| model_G2 | True |  |
| model_F3 | False | model_G5, model_G4, model_G2 |

### Conclusión de model switching

- El test relevante es:  
  `EV_model - EV_kiko = (P0_model - P0_kiko) + q * (Delta_model - Delta_kiko)`
- Para todos los modelos auditados, el `q*` necesario para que un equipo que **ya tiene `model_kiko`** prefiera cambiar solo por el MAF queda **por encima de 1** en conservador y también en central.
- O sea: **no** veo racionalidad en abandonar `model_kiko` *solo* para perseguir el MAF.
- Pero eso **no** invalida el riesgo rival: si un equipo **ya** está en una familia tipo `G5/G2`, o tiene un baseline más flojo que el nuestro, sí puede justificar bids más altos.
- Por eso el efecto rival más plausible no es “todos saltan desde `model_kiko`”, sino “una fracción del field usa o retiene modelos con mayor valor privado del access”.

## D. Modelo rival endógeno

### Escenarios de composición del field

| scenario | scenario_label | model_kiko | model_G5 | model_G1 | model_G4 | model_G2 | model_F3 | noise |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | R1 — Field conservador | 0.600 | 0.033 | 0.125 | 0.033 | 0.033 | 0.125 | 0.050 |
| R2 | R2 — Field mixto | 0.450 | 0.067 | 0.125 | 0.067 | 0.067 | 0.125 | 0.100 |
| R3 | R3 — Field adaptativo | 0.250 | 0.133 | 0.125 | 0.133 | 0.133 | 0.125 | 0.100 |
| R4 | R4 — Field muy agresivo | 0.100 | 0.167 | 0.100 | 0.167 | 0.167 | 0.100 | 0.200 |

### Lógica económica

- `R1`: mayoría en modelos light/medium; adaptación limitada.
- `R2`: field mixto; aparece una masa visible de modelos MAF-heavy.
- `R3`: field adaptativo; una parte importante sí internaliza el MAF y migra hacia modelos más sensibles.
- `R4`: stress serio; cola alta por mezcla de modelos heavy + bids de overinsurance/noise.

### Cutoff inducido

| scenario | scenario_label | cutoff_mean | cutoff_median | cutoff_p25 | cutoff_p75 | cutoff_p90 |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | R1 — Field conservador | 150.30 | 150.00 | 150.00 | 150.00 | 150.00 |
| R2 | R2 — Field mixto | 153.17 | 150.00 | 150.00 | 150.00 | 175.00 |
| R3 | R3 — Field adaptativo | 164.73 | 175.00 | 150.00 | 175.00 | 175.00 |
| R4 | R4 — Field muy agresivo | 173.09 | 175.00 | 175.00 | 175.00 | 175.00 |

### EV de nuestros bids (`model_kiko`) bajo field heterogéneo

**Delta conservador**

| scenario | bid | q_accept | net_gain_if_accepted | fee_roi | ev_uplift |
| --- | --- | --- | --- | --- | --- |
| R1 | 125 | 0.000 | 880.167 | 7.041 | 0.204 |
| R1 | 150 | 0.458 | 855.167 | 5.701 | 391.939 |
| R1 | 175 | 0.999 | 830.167 | 4.744 | 829.263 |
| R1 | 200 | 1.000 | 805.167 | 4.026 | 805.167 |
| R2 | 125 | 0.000 | 880.167 | 7.041 | 0.009 |
| R2 | 150 | 0.272 | 855.167 | 5.701 | 232.788 |
| R2 | 175 | 0.986 | 830.167 | 4.744 | 818.878 |
| R2 | 200 | 1.000 | 805.167 | 4.026 | 805.167 |
| R3 | 125 | 0.000 | 880.167 | 7.041 | 0.000 |
| R3 | 150 | 0.074 | 855.167 | 5.701 | 63.096 |
| R3 | 175 | 0.887 | 830.167 | 4.744 | 736.676 |
| R3 | 200 | 1.000 | 805.167 | 4.026 | 805.165 |
| R4 | 125 | 0.000 | 880.167 | 7.041 | 0.000 |
| R4 | 150 | 0.010 | 855.167 | 5.701 | 8.859 |
| R4 | 175 | 0.679 | 830.167 | 4.744 | 563.769 |
| R4 | 200 | 1.000 | 805.167 | 4.026 | 805.047 |

### Qué cambia respecto del análisis anterior

- `125` deja de ser serio en casi todos los escenarios endógenos: queda muy por debajo del cutoff inducido.
- `150` solo sobrevive si el field sigue muy conservador.
- `175` funciona bien mientras el cutoff no suba demasiado por model switching.
- `200` entra en juego porque el costo adicional frente a `175` es chico comparado con el valor económico del MAF.

Para `model_kiko`, con `Delta_conservative_mean ≈ 1005.2`, pasar de `175` a `200` reduce el `net_gain_if_accepted` apenas en **25**.  
Eso significa que `200` supera a `175` en EV apenas compra unos pocos puntos extra de aceptación; en campos rivales más agresivos, eso pasa muy rápido.

### Mejor bid por escenario dentro del modelo endógeno

| scenario | scenario_label | best_bid_cons | ev_uplift |
| --- | --- | --- | --- |
| R1 | R1 — Field conservador | 175 | 829.26 |
| R2 | R2 — Field mixto | 175 | 818.88 |
| R3 | R3 — Field adaptativo | 200 | 805.16 |
| R4 | R4 — Field muy agresivo | 200 | 805.05 |

### Resumen igual ponderado por escenario

| delta_key | best_bid_equal_weight | best_bid_worst_case |
| --- | --- | --- |
| Delta_conservative_mean | 200 | 200 |
| Delta_conservative_min | 200 | 200 |
| Delta_central_mean | 200 | 200 |

## E. Visualizaciones

Los plots generados están en:

- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/delta_by_model.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/baseline_vs_uplift_by_model.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/maf_sensitivity_classification.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/max_reasonable_bid_by_model.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/rival_bid_distributions_by_scenario.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/cutoff_distribution_and_cdf.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/our_bid_ev_under_heterogeneous_field.png`
- `/Users/pablo/Desktop/prosperity/round_2/results/maf_model_heterogeneity/plots/final_sensitivity_heatmap.png`

### Cómo leerlos

1. **Delta por modelo** — separa el hecho observado importante: `model_kiko` lidera baseline, pero no lidera valor del access.
2. **Baseline vs uplift** — deja claro el trade-off baseline fuerte vs MAF sensitivity.
3. **Clasificación MAF-light/medium/heavy** — resume qué familias son candidatas a pujar más alto.
4. **Bid máximo razonable por modelo** — muestra que condicionalmente muchos modelos pueden pagar 175–225 sin volverse absurdos.
5. **Distribución modelada de bids rivales** — visualiza el efecto del model switching: más masa en 175/200 y cola a 225/250/300.
6. **Cutoff inducido (PMF/CDF)** — traduce la mezcla de modelos en una distribución concreta del cutoff.
7. **EV de nuestros bids** — permite ver cuándo `175` aguanta y cuándo `200` le gana.
8. **Heatmap final** — resume el punto de decisión: sensibilidad del EV a la composición del field rival.

## F. Recomendación final

### Hechos observados

- **Sí**: el MAF puede valer mucho más para otros modelos que para `model_kiko`.
- El gap observado es grande: los mejores modelos MAF-heavy del set están aproximadamente entre **+45% y +72%** arriba de `model_kiko` en `Delta_conservative_mean`.
- El diferencial viene **principalmente de PEPPER**.
- **No**: eso no alcanza para justificar que alguien con `model_kiko` cambie racionalmente *solo* por el MAF.

### Implicación para nuestro bid

- **Sí**: esto empuja el cutoff rival esperado hacia arriba respecto de un field homogéneo.
- `150` queda más frágil.
- `175` pasa a ser el **nuevo piso robusto** si querés protegerte contra una parte del field usando modelos más MAF-heavy.
- `200` entra en **consideración seria** bajo escenarios `R3/R4`, donde la adaptación rival es real.

### Mi recomendación operativa

- **Bid recomendado por robustez práctica: 175**
- **Rango alternativo razonable: 175–200**
- **Subiría a 200** si tu lectura es que el field efectivamente va a internalizar el MAF y que habrá una fracción no marginal de equipos en modelos tipo `G5/G2` o equivalentes.
- **Me quedaría en 175** si querés una recomendación que suba respecto de `150`, pero sin dejar que el componente más modelado del análisis rival sobre-domine la decisión.

### Frase final

> **Sí:** el MAF podría valer bastante más para otros modelos.  
> **Sí:** es plausible que algunos equipos cambien o, más realista todavía, que ya estén en modelos que valoran mucho más el access.  
> **Sí:** eso empuja nuestro bid recomendado hacia arriba.  
> **La razón principal** es que `model_kiko` tiene el mejor baseline, pero no el mayor valor privado del MAF; entonces el riesgo no es que nos ganen por estrategia base, sino que parte del field pueda pujar más alto sin estar haciendo una locura económica.
