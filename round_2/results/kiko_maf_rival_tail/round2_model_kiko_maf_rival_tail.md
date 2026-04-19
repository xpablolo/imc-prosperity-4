# Revisión incremental del modelado rival / cutoff del MAF para `model_kiko`

## A. Resumen ejecutivo

- Manteniendo fija la valoración económica base (`Delta_conservative = 1005.2`, `Delta_downside = 851.0`, `Delta_central = 1609.8`), el cambio viene **solo** del nuevo modelado rival.
- Permitiendo **bunching + grid ampliada + cola superior explícita**, el bid robusto recomendado **pasa a ser `175` dentro del set comparado {100,125,150,175}**.
- `150` **ya no** sale como la opción robusta principal.
- `125` **no** recupera atractivo: solo compite si el campo estuviera mucho más concentrado abajo de 150 de lo que sugiere esta familia de escenarios.
- `175` entra en consideración totalmente seria; de hecho, es el mejor bid por EV medio, downside y robustez global dentro del conjunto evaluado.

## B. Nueva distribución rival

### Escenarios y lógica económica

| scenario_label | rival_type | logic |
| --- | --- | --- |
| Escenario A — masa en 100 | low / lower-mid bidders con small tail de seguro | Muchos equipos intentan pagar poco pero sin quedarse demasiado abajo; 100 funciona como focal point defensivo de bajo coste. |
| Escenario B — masa en 125 | middle bidders con bunching explícito en 125 | Muchos equipos convergen a la lógica clásica de bid robusto y pagan un poco más para no quedarse en 100. |
| Escenario C — masa en 150 | aggressive middle/high bidders | Campo más agresivo: 150 pasa a ser el número focal para comprar aceptación sin irse todavía a bids extremos. |
| Escenario D — mezcla heterogénea | mix de perfiles con cola superior moderada | Campo heterogéneo con low bidders, middle bidders, high bidders y ruido; representa un field sin consenso total pero con masa intermedia y tail visible. |
| Escenario E — cola superior agresiva | high bidders con tail explícita y crowd central todavía presente | La masa principal vive entre 125 y 175, pero además existe una cola superior no trivial en 200/250/300 y algo residual en 400. |
| Escenario F — overinsurance | insured high bidders / stress serio | Un subgrupo relevante paga bids muy altos para asegurar aceptación; sigue habiendo bunching en 150, pero también masa visible en 200/250/300 y residual en 400. |

Notas metodológicas:
- Soporte rival ampliado: `0, 25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400`.
- La distribución no es lisa: combina **masa de fondo**, **bunching explícito en focal points** y **cola superior**.
- Torneo simulado con `100` participantes totales, `99` rivales, `top 50` aceptados, y **tie-break uniforme** dentro del nivel exacto del cutoff.

## C. Cutoff inducido y aceptación

### Resumen del cutoff por escenario

| scenario_label | cutoff_mean | cutoff_median | cutoff_p10 | cutoff_p25 | cutoff_p75 | cutoff_p90 |
| --- | --- | --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | 101.64 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Escenario B — masa en 125 | 125.03 | 125.0 | 125.0 | 125.0 | 125.0 | 125.0 |
| Escenario C — masa en 150 | 149.33 | 150.0 | 150.0 | 150.0 | 150.0 | 150.0 |
| Escenario D — mezcla heterogénea | 125.62 | 125.0 | 125.0 | 125.0 | 125.0 | 125.0 |
| Escenario E — cola superior agresiva | 150.54 | 150.0 | 150.0 | 150.0 | 150.0 | 150.0 |
| Escenario F — overinsurance | 174.13 | 175.0 | 150.0 | 175.0 | 175.0 | 175.0 |

### Probabilidad de aceptación `q(b)` para 100 / 125 / 150 / 175

| scenario_label | 100 | 125 | 150 | 175 |
| --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | 0.2705 | 0.9925 | 1.0 | 1.0 |
| Escenario B — masa en 125 | 0.0002 | 0.4996 | 0.9998 | 1.0 |
| Escenario C — masa en 150 | 0.0 | 0.0037 | 0.6509 | 1.0 |
| Escenario D — mezcla heterogénea | 0.0075 | 0.4963 | 0.9917 | 1.0 |
| Escenario E — cola superior agresiva | 0.0 | 0.0006 | 0.4559 | 0.9979 |
| Escenario F — overinsurance | 0.0 | 0.0 | 0.0154 | 0.5619 |

Lectura rápida:
- En `Escenario A`, `125` y `175` casi aseguran entrada; `150` y `175` quedan muy parecidos.
- En `Escenario B`, `125` cae a un coin-flip; `150` y `175` prácticamente aseguran aceptación.
- En `Escenario C`, `150` ya no es seguro; `175` sí.
- En `Escenario E`, `150` cae a `q≈0.456`; `175` sigue en `q≈0.998`.
- En `Escenario F`, `150` casi no entra (`q≈0.015`), mientras que `175` todavía conserva `q≈0.560`.

## D. Comparación de bids

### Métricas con `Delta_conservative`

| scenario_label | bid | q_accept | net_gain_if_accepted | uplift_pct_vs_base | fee_roi | ev_uplift |
| --- | --- | --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | 100 | 0.2705 | 905.2 | 0.0088 | 9.052 | 244.9 |
| Escenario A — masa en 100 | 125 | 0.9925 | 880.2 | 0.0086 | 7.041 | 873.6 |
| Escenario A — masa en 100 | 150 | 1.0 | 855.2 | 0.0083 | 5.701 | 855.2 |
| Escenario A — masa en 100 | 175 | 1.0 | 830.2 | 0.0081 | 4.744 | 830.2 |
| Escenario B — masa en 125 | 100 | 0.0002 | 905.2 | 0.0088 | 9.052 | 0.2 |
| Escenario B — masa en 125 | 125 | 0.4996 | 880.2 | 0.0086 | 7.041 | 439.7 |
| Escenario B — masa en 125 | 150 | 0.9998 | 855.2 | 0.0083 | 5.701 | 855.0 |
| Escenario B — masa en 125 | 175 | 1.0 | 830.2 | 0.0081 | 4.744 | 830.2 |
| Escenario C — masa en 150 | 100 | 0.0 | 905.2 | 0.0088 | 9.052 | 0.0 |
| Escenario C — masa en 150 | 125 | 0.0037 | 880.2 | 0.0086 | 7.041 | 3.2 |
| Escenario C — masa en 150 | 150 | 0.6509 | 855.2 | 0.0083 | 5.701 | 556.6 |
| Escenario C — masa en 150 | 175 | 1.0 | 830.2 | 0.0081 | 4.744 | 830.2 |
| Escenario D — mezcla heterogénea | 100 | 0.0075 | 905.2 | 0.0088 | 9.052 | 6.8 |
| Escenario D — mezcla heterogénea | 125 | 0.4963 | 880.2 | 0.0086 | 7.041 | 436.8 |
| Escenario D — mezcla heterogénea | 150 | 0.9917 | 855.2 | 0.0083 | 5.701 | 848.0 |
| Escenario D — mezcla heterogénea | 175 | 1.0 | 830.2 | 0.0081 | 4.744 | 830.2 |
| Escenario E — cola superior agresiva | 100 | 0.0 | 905.2 | 0.0088 | 9.052 | 0.0 |
| Escenario E — cola superior agresiva | 125 | 0.0006 | 880.2 | 0.0086 | 7.041 | 0.5 |
| Escenario E — cola superior agresiva | 150 | 0.4559 | 855.2 | 0.0083 | 5.701 | 389.9 |
| Escenario E — cola superior agresiva | 175 | 0.9979 | 830.2 | 0.0081 | 4.744 | 828.4 |
| Escenario F — overinsurance | 100 | 0.0 | 905.2 | 0.0088 | 9.052 | 0.0 |
| Escenario F — overinsurance | 125 | 0.0 | 880.2 | 0.0086 | 7.041 | 0.0 |
| Escenario F — overinsurance | 150 | 0.0154 | 855.2 | 0.0083 | 5.701 | 13.1 |
| Escenario F — overinsurance | 175 | 0.5619 | 830.2 | 0.0081 | 4.744 | 466.5 |

### Métricas con `Delta_downside`

| scenario_label | bid | q_accept | net_gain_if_accepted | uplift_pct_vs_base | fee_roi | ev_uplift |
| --- | --- | --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | 100 | 0.2705 | 751.0 | 0.0073 | 7.51 | 203.2 |
| Escenario A — masa en 100 | 125 | 0.9925 | 726.0 | 0.0071 | 5.808 | 720.6 |
| Escenario A — masa en 100 | 150 | 1.0 | 701.0 | 0.0068 | 4.673 | 701.0 |
| Escenario A — masa en 100 | 175 | 1.0 | 676.0 | 0.0066 | 3.863 | 676.0 |
| Escenario B — masa en 125 | 100 | 0.0002 | 751.0 | 0.0073 | 7.51 | 0.2 |
| Escenario B — masa en 125 | 125 | 0.4996 | 726.0 | 0.0071 | 5.808 | 362.7 |
| Escenario B — masa en 125 | 150 | 0.9998 | 701.0 | 0.0068 | 4.673 | 700.8 |
| Escenario B — masa en 125 | 175 | 1.0 | 676.0 | 0.0066 | 3.863 | 676.0 |
| Escenario C — masa en 150 | 100 | 0.0 | 751.0 | 0.0073 | 7.51 | 0.0 |
| Escenario C — masa en 150 | 125 | 0.0037 | 726.0 | 0.0071 | 5.808 | 2.7 |
| Escenario C — masa en 150 | 150 | 0.6509 | 701.0 | 0.0068 | 4.673 | 456.3 |
| Escenario C — masa en 150 | 175 | 1.0 | 676.0 | 0.0066 | 3.863 | 676.0 |
| Escenario D — mezcla heterogénea | 100 | 0.0075 | 751.0 | 0.0073 | 7.51 | 5.7 |
| Escenario D — mezcla heterogénea | 125 | 0.4963 | 726.0 | 0.0071 | 5.808 | 360.3 |
| Escenario D — mezcla heterogénea | 150 | 0.9917 | 701.0 | 0.0068 | 4.673 | 695.2 |
| Escenario D — mezcla heterogénea | 175 | 1.0 | 676.0 | 0.0066 | 3.863 | 676.0 |
| Escenario E — cola superior agresiva | 100 | 0.0 | 751.0 | 0.0073 | 7.51 | 0.0 |
| Escenario E — cola superior agresiva | 125 | 0.0006 | 726.0 | 0.0071 | 5.808 | 0.4 |
| Escenario E — cola superior agresiva | 150 | 0.4559 | 701.0 | 0.0068 | 4.673 | 319.6 |
| Escenario E — cola superior agresiva | 175 | 0.9979 | 676.0 | 0.0066 | 3.863 | 674.6 |
| Escenario F — overinsurance | 100 | 0.0 | 751.0 | 0.0073 | 7.51 | 0.0 |
| Escenario F — overinsurance | 125 | 0.0 | 726.0 | 0.0071 | 5.808 | 0.0 |
| Escenario F — overinsurance | 150 | 0.0154 | 701.0 | 0.0068 | 4.673 | 10.8 |
| Escenario F — overinsurance | 175 | 0.5619 | 676.0 | 0.0066 | 3.863 | 379.8 |

### Métricas con `Delta_central`

| scenario_label | bid | q_accept | net_gain_if_accepted | uplift_pct_vs_base | fee_roi | ev_uplift |
| --- | --- | --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | 100 | 0.2705 | 1509.8 | 0.0147 | 15.098 | 408.5 |
| Escenario A — masa en 100 | 125 | 0.9925 | 1484.8 | 0.0144 | 11.879 | 1473.7 |
| Escenario A — masa en 100 | 150 | 1.0 | 1459.8 | 0.0142 | 9.732 | 1459.8 |
| Escenario A — masa en 100 | 175 | 1.0 | 1434.8 | 0.0139 | 8.199 | 1434.8 |
| Escenario B — masa en 125 | 100 | 0.0002 | 1509.8 | 0.0147 | 15.098 | 0.3 |
| Escenario B — masa en 125 | 125 | 0.4996 | 1484.8 | 0.0144 | 11.879 | 741.9 |
| Escenario B — masa en 125 | 150 | 0.9998 | 1459.8 | 0.0142 | 9.732 | 1459.5 |
| Escenario B — masa en 125 | 175 | 1.0 | 1434.8 | 0.0139 | 8.199 | 1434.8 |
| Escenario C — masa en 150 | 100 | 0.0 | 1509.8 | 0.0147 | 15.098 | 0.0 |
| Escenario C — masa en 150 | 125 | 0.0037 | 1484.8 | 0.0144 | 11.879 | 5.5 |
| Escenario C — masa en 150 | 150 | 0.6509 | 1459.8 | 0.0142 | 9.732 | 950.2 |
| Escenario C — masa en 150 | 175 | 1.0 | 1434.8 | 0.0139 | 8.199 | 1434.8 |
| Escenario D — mezcla heterogénea | 100 | 0.0075 | 1509.8 | 0.0147 | 15.098 | 11.4 |
| Escenario D — mezcla heterogénea | 125 | 0.4963 | 1484.8 | 0.0144 | 11.879 | 736.9 |
| Escenario D — mezcla heterogénea | 150 | 0.9917 | 1459.8 | 0.0142 | 9.732 | 1447.7 |
| Escenario D — mezcla heterogénea | 175 | 1.0 | 1434.8 | 0.0139 | 8.199 | 1434.8 |
| Escenario E — cola superior agresiva | 100 | 0.0 | 1509.8 | 0.0147 | 15.098 | 0.0 |
| Escenario E — cola superior agresiva | 125 | 0.0006 | 1484.8 | 0.0144 | 11.879 | 0.9 |
| Escenario E — cola superior agresiva | 150 | 0.4559 | 1459.8 | 0.0142 | 9.732 | 665.6 |
| Escenario E — cola superior agresiva | 175 | 0.9979 | 1434.8 | 0.0139 | 8.199 | 1431.8 |
| Escenario F — overinsurance | 100 | 0.0 | 1509.8 | 0.0147 | 15.098 | 0.0 |
| Escenario F — overinsurance | 125 | 0.0 | 1484.8 | 0.0144 | 11.879 | 0.0 |
| Escenario F — overinsurance | 150 | 0.0154 | 1459.8 | 0.0142 | 9.732 | 22.4 |
| Escenario F — overinsurance | 175 | 0.5619 | 1434.8 | 0.0139 | 8.199 | 806.2 |

### Comparación marginal de EV

| scenario_label | delta_key | EV_125_minus_100 | EV_150_minus_125 | EV_175_minus_150 |
| --- | --- | --- | --- | --- |
| Escenario A — masa en 100 | central | 1065.3 | -13.9 | -25.0 |
| Escenario A — masa en 100 | conservative | 628.7 | -18.4 | -25.0 |
| Escenario A — masa en 100 | downside | 517.4 | -19.6 | -25.0 |
| Escenario B — masa en 125 | central | 741.5 | 717.7 | -24.7 |
| Escenario B — masa en 125 | conservative | 439.5 | 415.2 | -24.8 |
| Escenario B — masa en 125 | downside | 362.6 | 338.1 | -24.8 |
| Escenario C — masa en 150 | central | 5.5 | 944.7 | 484.6 |
| Escenario C — masa en 150 | conservative | 3.2 | 553.4 | 273.5 |
| Escenario C — masa en 150 | downside | 2.7 | 453.6 | 219.7 |
| Escenario D — mezcla heterogénea | central | 725.5 | 710.8 | -12.8 |
| Escenario D — mezcla heterogénea | conservative | 430.0 | 411.2 | -17.9 |
| Escenario D — mezcla heterogénea | downside | 354.6 | 334.9 | -19.2 |
| Escenario E — cola superior agresiva | central | 0.9 | 664.7 | 766.2 |
| Escenario E — cola superior agresiva | conservative | 0.5 | 389.4 | 438.5 |
| Escenario E — cola superior agresiva | downside | 0.4 | 319.2 | 355.0 |
| Escenario F — overinsurance | central | 0.0 | 22.4 | 783.8 |
| Escenario F — overinsurance | conservative | 0.0 | 13.1 | 453.3 |
| Escenario F — overinsurance | downside | 0.0 | 10.8 | 369.1 |

Lectura marginal importante (`Delta_conservative`):
- El salto `125 -> 150` sigue valiendo mucho cuando el crowd se amontona en `125`.
- El salto `150 -> 175` pasa a ser **muy valioso** cuando aparece cola superior real:
  - `Escenario C`: `EV(175)-EV(150) ≈ 273.5`
  - `Escenario E`: `EV(175)-EV(150) ≈ 438.5`
  - `Escenario F`: `EV(175)-EV(150) ≈ 453.3`
- En escenarios suaves, subir de `150` a `175` cuesta solo ~25 EV, porque `q` ya está casi en 1. En escenarios con cola superior, ese mismo salto funciona como seguro fuerte contra quedarte corto.

### Robustez resumida

#### `Delta_conservative`
| delta_key | bid | mean_ev | min_ev | max_regret | mean_regret |
| --- | --- | --- | --- | --- | --- |
| conservative | 100 | 42.0 | 0.0 | 854.8 | 741.6 |
| conservative | 125 | 292.3 | 0.0 | 827.9 | 491.3 |
| conservative | 150 | 586.3 | 13.1 | 453.3 | 197.3 |
| conservative | 175 | 769.3 | 466.5 | 43.4 | 14.4 |

#### `Delta_downside`
| delta_key | bid | mean_ev | min_ev | max_regret | mean_regret |
| --- | --- | --- | --- | --- | --- |
| downside | 100 | 34.8 | 0.0 | 700.7 | 606.3 |
| downside | 125 | 241.1 | 0.0 | 674.1 | 400.0 |
| downside | 150 | 480.6 | 10.8 | 369.1 | 160.6 |
| downside | 175 | 626.4 | 379.8 | 44.6 | 14.8 |

## E. Visualizaciones

Plots generados en `/Users/pablo/Desktop/prosperity/round_2/results/kiko_maf_rival_tail/plots`:

1. `rival_bid_distribution_extended.png`
   - Muestra, por escenario, la **masa central**, el **bunching** y la **cola superior**.
   - Es el gráfico clave para ver si 125/150/175 quedan por debajo, dentro o por encima de la congestión rival.

2. `induced_cutoff_pmf_extended.png`
   - Muestra la PMF del cutoff inducido.
   - Permite ver si el corte cae en 100, 125, 150 o 175 según el escenario.

3. `induced_cutoff_cdf_extended.png`
   - Permite visualizar rápidamente cuánto probabilidad ganás al subir el bid.
   - OJO: con ties discretos, la CDF del cutoff no es exactamente `q(b)` en los focal points, por eso reporto `q(b)` exacta en tablas.

4. `ev_by_bid_extended.png`
   - Compara `100/125/150/175` por escenario con `Delta_conservative` y `Delta_downside`.
   - Ahí se ve si `175` compensa o si ya es demasiado caro.

5. `marginal_ev_extended.png`
   - Muestra `EV(125)-EV(100)`, `EV(150)-EV(125)` y `EV(175)-EV(150)`.
   - Es el gráfico más útil para juzgar si 175 agrega valor real o es puro sobrepago.

6. `final_sensitivity_heatmap_extended.png`
   - Eje 1: escenario rival.
   - Eje 2: Delta usado.
   - Output: mejor bid entre `{100,125,150,175}`.

## F. Recomendación final

### Identificación pedida
- Mejor bid por EV medio (`Delta_conservative`, escenarios equiponderados): **`175`**.
- Mejor bid por downside (`Delta_downside`, criterio maximin): **`175`**.
- Mejor bid bajo cola superior agresiva (`Escenario E`): **`175`**.
- Mejor bid bajo overinsurance (`Escenario F`): **`175`**.
- Bid más robusto global: **`175`**.

### Respuesta a las preguntas clave
- **¿150 sigue siendo robusto cuando permitimos cola superior en bids rivales?** No. Se vuelve intermedio: supera claramente a 125, pero queda vulnerable cuando el cutoff rival se mueve hacia 175 o cuando la cola superior es gruesa.
- **¿125 recupera atractivo?** No. El riesgo de quedarte corto con 125 pasa a ser demasiado alto en escenarios B/C/D/E/F.
- **¿175 pasa a ser necesario o sigue siendo demasiado caro?** Dentro del set comparado, **175 pasa a ser necesario y deja de parecer caro**: su coste extra respecto a 150 es pequeño en escenarios suaves y su beneficio es enorme cuando la cola superior realmente existe.
- **¿El cambio respecto al análisis anterior es pequeño o grande?** Es **material**: el cambio de 150 a 175 no viene por Delta, viene por cómo cambia `q(b)` cuando el campo rival ya no está comprimido en 100–150.

### Recomendación operativa
- **Bid recomendado**: **`175`**.
- **Rango alternativo**: **`150–175`**.
- **Cuándo usar `125`**: solo si estás convencido de que el field real está bastante más abajo y que la cola superior es irrelevante. Con esta familia de escenarios, esa postura ya no es la base case.
- **Cuándo usar `150`**: si querés una postura intermedia y te parece demasiado agresivo pagar 175, pero aceptando que quedás más expuesto a escenarios E/F.
- **Cuándo usar `175`**: si tomás en serio la posibilidad de bunching en 150 y, sobre todo, la existencia de una cola superior explícita en 200/250/300.

### Caveat honesto
Esta fase compara candidatos `{100,125,150,175}`. No re-optimizó bids propios por encima de 175. Por eso, decir que `175` es el robusto recomendado significa **“mejor dentro del set comparado”**, no una prueba formal de óptimo global sobre toda la recta.
