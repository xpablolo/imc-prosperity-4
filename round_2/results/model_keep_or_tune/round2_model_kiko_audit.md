# Auditoría cuantitativa de `model_kiko` para Round 2

## 1. Resumen ejecutivo

- **Recomendación final:** **Opción A — mantener `model_kiko` intacto en su lógica de trading**.
- **Confianza:** media-alta.
- Tomo como restricción fuerte tu dato reportado de live Round 1 (~192k, top 70). Eso **sube muchísimo** la carga de prueba para tocar el modelo.
- Localmente, `model_kiko` sigue siendo la mejor base que encontré: `310,785.0` en Round 1 y `309,940.0` en Round 2.
- Contra comparables cercanos (`G5`, `G1`, `G4`, `G2`, `F3`), `model_kiko` queda **primero en ambas rondas y en todos los escenarios microestructurales testeados**.
- Los microtweaks que mejoran el replay local **sí existen**, pero todos empujan más fuerte la misma hipótesis de drift de PEPPER. Eso me parece **más overfit que mejora robusta**.
- Mi lectura práctica: **Round 2 se parece más a un problema de preservar una estrategia ya muy buena y decidir bien el bid que a un problema de rediseñar `model_kiko`**.

## 2. Contexto: por qué este problema NO es “buscar un modelo nuevo”

- El archivo auditado es el modelo real que, según tu dato reportado, produjo un resultado live muy fuerte en Round 1.
- Eso implica una filosofía correcta de trabajo:
  1. **Hipótesis nula = no tocar.**
  2. Un cambio solo entra si mejora de forma clara, consistente y explicable.
  3. Si la mejora sale de exprimir el mismo replay local, se penaliza como riesgo de overfit.

## 3. `model_kiko`: archivo, estructura y lógica

- **Ruta exacta:** `/Users/pablo/Desktop/prosperity/round_2/models/model_kiko.py`.
- Arquitectura general:
  - `SharedBookOps`: utilidades comunes de making/taking/clear.
  - `OsmiumEngine`: lógica de `ASH_COATED_OSMIUM`.
  - `PepperEngine`: lógica de `INTARIAN_PEPPER_ROOT`.
  - `Trader`: orquestación y serialización de `traderData`.

### ASH_COATED_OSMIUM

- Fair value por **EWMA del mid**.
- Reservation price con skew por inventario.
- Taking simple alrededor de `take_width`.
- Making con `default_edge` grande y lógica clásica de join/step.

### INTARIAN_PEPPER_ROOT

- La tesis central es **trend-following prior-driven**.
- El modelo fija `price_slope = 0.00100001` por timestamp y reconstruye una `base_price` de-trendeada.
- Después calcula `alpha = forward_edge - residual_weight * residual - inventory_skew * position` (más un término de gap hoy neutralizado).
- En castellano: **asume que PEPPER tiene una deriva lineal muy estable y trata de cargar inventario largo sin pagar de más**.

### Cómo genera el PnL

- **Round 1:** ASH aporta 20.2% del total y PEPPER 79.8%.
- **Round 2:** ASH aporta 21.4% del total y PEPPER 78.6%.
- O sea: el edge de verdad está en **PEPPER**. ASH suma, pero no define el ranking.

## 4. Revisión del entorno de Round 2

- Productos y límites no cambian: `ASH_COATED_OSMIUM` e `INTARIAN_PEPPER_ROOT`, ambos con límite 80.
- La novedad es el **Market Access Fee (MAF)**: un `bid()` ciego para acceder a +25% de quotes si entrás en el top 50%.
- **PERO** eso no cambia qué inputs ve el modelo en `run()`.

### Qué inputs existen realmente

- En el `TradingState` del repo existen: `timestamp`, `order_depths`, `own_trades`, `market_trades`, `position`, `observations`, `traderData`.
- En el backtester local, al llamar `run()` se pasan `own_trades={product: []}`, `market_trades={product: []}` y `observations` vacías.
- **No existe** un flag `access_granted`, `accepted_bid` ni nada equivalente en `TradingState` o en el backtester local.
- Entonces: cualquier mejora seria tiene que depender de **inputs observables reales** (libro visible, timestamp, posición, traderData propio), no de una señal ficticia.

## 5. Auditoría de robustez de `model_kiko`

### 5.1 Baseline por round y producto

| round_label | product | total_pnl | max_drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position | pct_abs_ge_70 | pct_at_limit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Round 1 | ASH_COATED_OSMIUM | 62841.000 | -1840.000 | 1956.000 | 0.629 | 5.773 | 27.515 | 0.064 | 0.015 |
| Round 1 | INTARIAN_PEPPER_ROOT | 247944.000 | -1520.000 | 1411.000 | 0.378 | 5.259 | 74.136 | 0.790 | 0.366 |
| Round 1 | TOTAL | 310785.000 | -1972.000 | 3367.000 | 0.524 | 5.558 |  |  |  |
| Round 2 | ASH_COATED_OSMIUM | 66456.000 | -1620.000 | 2024.000 | 0.666 | 5.692 | 28.271 | 0.048 | 0.018 |
| Round 2 | INTARIAN_PEPPER_ROOT | 243484.000 | -1680.000 | 1525.000 | 0.386 | 5.342 | 71.121 | 0.642 | 0.262 |
| Round 2 | TOTAL | 309940.000 | -1850.000 | 3549.000 | 0.546 | 5.542 |  |  |  |

### 5.2 Robustez día a día

| model | mean_day_pnl | std_day_pnl | min_day_pnl | max_day_pnl |
| --- | --- | --- | --- | --- |
| model_kiko | 103454.2 | 1141.1 | 102346.0 | 105296.0 |
| model_G5 | 101573.0 | 669.5 | 100943.5 | 102674.0 |
| model_G1 | 101487.7 | 654.1 | 100900.0 | 102527.0 |
| model_G4 | 101383.5 | 612.5 | 100706.0 | 102254.0 |
| model_G2 | 101289.2 | 590.7 | 100575.0 | 102005.0 |
| model_F3 | 101132.3 | 724.0 | 100273.5 | 101992.5 |

- `model_kiko` le gana a `G5` en **5 de 6 días** a nivel total.
- En `PEPPER`, `model_kiko` le gana a `G5` en **6 de 6 días**.
- En `ASH`, `model_kiko` pierde en promedio; su edge no sale de ahí.

### 5.3 Capacidad / inventario

| round_label | scenario | day | product | day_pnl | avg_abs_position | pct_abs_ge_70 | pct_at_limit | time_to_70 | time_to_80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Round 1 | baseline | -2 | ASH_COATED_OSMIUM | 20113.000 | 26.349 | 0.023 | 0.004 |  |  |
| Round 1 | baseline | -1 | ASH_COATED_OSMIUM | 22308.000 | 21.381 | 0.037 | 0.002 |  |  |
| Round 1 | baseline | 0 | ASH_COATED_OSMIUM | 20420.000 | 34.812 | 0.132 | 0.038 |  |  |
| Round 1 | baseline | -2 | INTARIAN_PEPPER_ROOT | 83008.000 | 75.880 | 0.883 | 0.431 | 1100.000 | 11300.000 |
| Round 1 | baseline | -1 | INTARIAN_PEPPER_ROOT | 82988.000 | 74.559 | 0.807 | 0.373 | 0.000 | 0.000 |
| Round 1 | baseline | 0 | INTARIAN_PEPPER_ROOT | 81948.000 | 71.968 | 0.680 | 0.292 | 5200.000 | 6900.000 |
| Round 2 | baseline | -1 | ASH_COATED_OSMIUM | 22167.000 | 41.554 | 0.071 | 0.024 |  |  |
| Round 2 | baseline | 0 | ASH_COATED_OSMIUM | 22630.000 | 21.616 | 0.036 | 0.014 |  |  |
| Round 2 | baseline | 1 | ASH_COATED_OSMIUM | 21659.000 | 21.637 | 0.038 | 0.017 |  |  |
| Round 2 | baseline | -1 | INTARIAN_PEPPER_ROOT | 81203.500 | 73.054 | 0.706 | 0.306 | 5700.000 | 12600.000 |
| Round 2 | baseline | 0 | INTARIAN_PEPPER_ROOT | 81593.500 | 71.639 | 0.657 | 0.246 | 0.000 | 2700.000 |
| Round 2 | baseline | 1 | INTARIAN_PEPPER_ROOT | 80687.000 | 68.671 | 0.564 | 0.234 | 0.000 | 0.000 |
| Round 2 | maf_uniform_125 | -1 | ASH_COATED_OSMIUM | 23041.000 | 40.464 | 0.077 | 0.025 |  |  |
| Round 2 | maf_uniform_125 | 0 | ASH_COATED_OSMIUM | 23218.000 | 22.766 | 0.048 | 0.016 |  |  |
| Round 2 | maf_uniform_125 | 1 | ASH_COATED_OSMIUM | 22299.000 | 23.965 | 0.043 | 0.017 |  |  |
| Round 2 | maf_uniform_125 | -1 | INTARIAN_PEPPER_ROOT | 81305.500 | 72.848 | 0.705 | 0.328 | 5700.000 | 11300.000 |
| Round 2 | maf_uniform_125 | 0 | INTARIAN_PEPPER_ROOT | 81689.500 | 71.459 | 0.675 | 0.268 | 0.000 | 2700.000 |
| Round 2 | maf_uniform_125 | 1 | INTARIAN_PEPPER_ROOT | 81127.500 | 68.927 | 0.596 | 0.276 | 0.000 | 0.000 |
| Round 2 | maf_front_125 | -1 | ASH_COATED_OSMIUM | 23721.000 | 39.251 | 0.106 | 0.027 |  |  |
| Round 2 | maf_front_125 | 0 | ASH_COATED_OSMIUM | 23840.000 | 23.597 | 0.052 | 0.017 |  |  |
| Round 2 | maf_front_125 | 1 | ASH_COATED_OSMIUM | 22919.000 | 24.627 | 0.043 | 0.019 |  |  |
| Round 2 | maf_front_125 | -1 | INTARIAN_PEPPER_ROOT | 81247.000 | 72.540 | 0.691 | 0.333 | 2700.000 | 5700.000 |
| Round 2 | maf_front_125 | 0 | INTARIAN_PEPPER_ROOT | 81509.000 | 70.749 | 0.645 | 0.274 | 0.000 | 2700.000 |
| Round 2 | maf_front_125 | 1 | INTARIAN_PEPPER_ROOT | 81148.000 | 68.652 | 0.575 | 0.287 | 0.000 | 0.000 |

- En Round 2 baseline, PEPPER ya opera con `avg_abs_position = 71.1` y `pct_abs_ge_70 = 64.2%`.
- Eso te dice dos cosas a la vez:
  1. ya está monetizando fuerte el carry,
  2. pero **sin** pasar tanto tiempo clavado en el límite como otros modelos más warehouse-heavy.

## 6. Comparación con alternativas cercanas

### 6.1 Totales baseline

| model | Round 1 | Round 2 |
| --- | --- | --- |
| model_kiko | 310785.0 | 309940.0 |
| model_G5 | 304026.0 | 305412.0 |
| model_G1 | 303686.0 | 305240.0 |
| model_G4 | 303665.0 | 304636.0 |
| model_G2 | 303884.0 | 303851.0 |
| model_F3 | 303292.0 | 303502.0 |

### 6.2 Deltas pareados de `model_kiko` contra comparables

| alt_model | delta_round_1_total | delta_round_2_total | mean_daily_total_delta | std_daily_total_delta | min_daily_total_delta | wins_total_days | wins_pepper_days | wins_ash_days | scenario_wins |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model_F3 | 7493.0 | 6438.0 | 2321.8 | 1098.1 | 406.0 | 6 | 6 | 2 | 6 |
| model_G2 | 6901.0 | 6089.0 | 2165.0 | 1103.8 | 341.0 | 6 | 6 | 2 | 6 |
| model_G4 | 7120.0 | 5304.0 | 2070.7 | 1128.9 | 92.0 | 6 | 6 | 2 | 6 |
| model_G1 | 7099.0 | 4700.0 | 1966.5 | 1225.3 | -181.0 | 5 | 6 | 2 | 6 |
| model_G5 | 6759.0 | 4528.0 | 1881.2 | 1260.4 | -328.0 | 5 | 6 | 2 | 6 |

### 6.3 Robustez por escenarios de microestructura / MAF

| model | baseline | depth_110 | depth_90 | maf_depth_trade_125 | maf_front_125 | maf_uniform_125 |
| --- | --- | --- | --- | --- | --- | --- |
| model_kiko | 309940.0 | 310549.5 | 308409.5 | 329216.5 | 314384.0 | 312680.5 |
| model_G5 | 305412.0 | 307854.5 | 303034.5 | 325705.5 | 311931.0 | 309976.5 |
| model_G1 | 305240.0 | 307858.5 | 302814.5 | 325558.5 | 311677.0 | 309406.5 |
| model_G4 | 304636.0 | 307177.5 | 302105.5 | 324911.5 | 311565.0 | 309198.5 |
| model_G2 | 303851.0 | 306965.5 | 301778.5 | 325269.5 | 311471.0 | 308807.5 |
| model_F3 | 303502.0 | 306261.5 | 301554.5 | 323728.5 | 310277.0 | 307865.5 |

Lectura importante:

- `model_kiko` queda **primero en baseline**.
- También queda **primero con depth -10% y +10%**.
- Y sigue **primero bajo los proxies MAF**.
- O sea: no veo a ninguna alternativa cercana dominándolo de verdad. Las otras son buenas, pero **no mejores**.

## 7. Posibles microajustes detectados

### 7.1 Sensibilidad local de parámetros

| variant | label | delta_round_1 | delta_round_2 | delta_both |
| --- | --- | --- | --- | --- |
| pepper_base_update_04 | PEPPER base_update_weight = 0.4 | 1695.0 | 6868.0 | 8563.0 |
| pepper_base_update_03 | PEPPER base_update_weight = 0.3 | 1288.0 | 3606.0 | 4894.0 |
| pepper_residual_06 | PEPPER residual_weight = 0.6 | 1092.0 | 1796.0 | 2888.0 |
| pepper_slope_p05 | PEPPER price_slope +5% | -616.0 | 2808.0 | 2192.0 |
| pepper_slope_p02 | PEPPER price_slope +2% | -160.0 | 857.0 | 697.0 |
| pepper_slope_p01 | PEPPER price_slope +1% | -36.0 | 361.0 | 325.0 |
| ash_edge_m5 | ASH default_edge -5 | 0.0 | 0.0 | 0.0 |
| ash_edge_p5 | ASH default_edge +5 | 0.0 | 0.0 | 0.0 |
| baseline | Sin cambios | 0.0 | 0.0 | 0.0 |
| pepper_take_m025 | PEPPER take_width = 0.75 | -468.0 | 210.0 | -258.0 |
| pepper_take_p025 | PEPPER take_width = 1.25 | -593.0 | -1562.0 | -2155.0 |

### 7.2 Scorecard de cambios

| candidate | variant | category | delta_round_1 | delta_round_2 | delta_both | implementable_with_real_inputs | why |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ASH default_edge -5 | ash_edge_m5 | No tocar | 0.0 | 0.0 | 0.0 | sí | No cambia nada en el replay local; moverlo añade ruido sin beneficio. |
| ASH default_edge +5 | ash_edge_p5 | No tocar | 0.0 | 0.0 | 0.0 | sí | No cambia nada en el replay local; moverlo añade ruido sin beneficio. |
| Sin cambios | baseline | No tocar | 0.0 | 0.0 | 0.0 | sí | Es el punto de referencia real; ya está validado en live según tu input. |
| PEPPER base_update_weight = 0.3 | pepper_base_update_03 | Demasiado frágil / alto riesgo de overfit | 1288.0 | 3606.0 | 4894.0 | sí | Es el microcambio más defendible si te obligaran a probar uno, pero la mejora sale de perseguir más rápido el mismo drift local. |
| PEPPER base_update_weight = 0.4 | pepper_base_update_04 | Demasiado frágil / alto riesgo de overfit | 1695.0 | 6868.0 | 8563.0 | sí | Mejora mucho localmente porque carga más carry y más tiempo cerca del límite; eso es justo el tipo de tuning que más puede romperse fuera de muestra. |
| PEPPER residual_weight = 0.6 | pepper_residual_06 | Demasiado frágil / alto riesgo de overfit | 1092.0 | 1796.0 | 2888.0 | sí | Reduce el castigo por residual y empuja más fuerte la tesis tendencial; mejora local, pero empeora la prudencia del modelo. |
| PEPPER price_slope +1% | pepper_slope_p01 | Demasiado frágil / alto riesgo de overfit | -36.0 | 361.0 | 325.0 | sí | Mejora local mínima ajustando exactamente la pendiente fija del drift observado. |
| PEPPER price_slope +2% | pepper_slope_p02 | Demasiado frágil / alto riesgo de overfit | -160.0 | 857.0 | 697.0 | sí | Mejora local algo mayor, pero sigue siendo tuning directo del slope conocido del dataset. |
| PEPPER price_slope +5% | pepper_slope_p05 | Demasiado frágil / alto riesgo de overfit | -616.0 | 2808.0 | 2192.0 | sí | La mejora local es fuerte, pero viene de hacer todavía más agresiva la hipótesis fija de drift. |
| PEPPER take_width = 0.75 | pepper_take_m025 | No tocar | -468.0 | 210.0 | -258.0 | sí | Ligero beneficio en Round 2 pero pequeño e inconsistente contra Round 1; no supera la carga de prueba. |
| PEPPER take_width = 1.25 | pepper_take_p025 | No tocar | -593.0 | -1562.0 | -2155.0 | sí | Empeora de forma visible; no hay caso económico claro para ensanchar más el taking. |

## 8. Análisis específico de riesgo de overfit

Acá está la parte más importante, hermano.

### Qué sí me parece robusto

- La **estructura** del modelo: ASH simple + PEPPER tendencial.
- La separación por engines y el uso de solo inputs observables reales.
- La ventaja comparativa baseline de `model_kiko` frente a alternativas cercanas.

### Qué me parece más frágil

- El corazón de PEPPER depende de una **pendiente fija** (`price_slope`).
- Los tweaks que mejoran localmente hacen casi siempre lo mismo:
  - subir `price_slope`, o
  - subir `base_update_weight`, o
  - bajar `residual_weight`.
- Traducido: **todos** empujan al modelo a creer aún más en el mismo drift lineal que ya observó el dataset.

- Ejemplo claro: con `base_update_weight = 0.3`, Round 2 sube `+3,606.0` localmente.
- Con `base_update_weight = 0.4`, Round 2 sube `+6,868.0` localmente.
- Pero ese extra PnL viene acompañado de más inventario medio y más tiempo cerca del límite en PEPPER. Es decir: gana porque **se casa más fuerte con la tendencia observada**.
- Y ojo con la comparación: `model_kiko` baseline ya hace más PnL en PEPPER que `G5` con **menos inventario medio** (`71.1` vs `74.9`) y menos tiempo al límite (`26.2%` vs `42.3%`).
- Para mí, eso es una señal de eficiencia del baseline. Si ahora lo tuneás para warehousear todavía más, podés estar cambiando eficiencia por brute force.

## 9. Qué mejoras son robustas y cuáles no

### Robustas / accionables

- **Agregar `bid()`** para Round 2: sí, pero eso es una decisión aparte del modelo, no un cambio en la lógica de `run()`.
- **Mantener la lógica de trading igual**: sí. Hoy cruza la carga de prueba.

### No robustas o demasiado frágiles

- Tocar `price_slope` basándose en estos mismos datasets.
- Hacer `base_update_weight` mucho más agresivo para cargar más carry.
- Debilitar `residual_weight` para dejar que PEPPER persiga más el precio.
- Cualquier lógica condicionada a un supuesto `access_granted` inexistente.

## 10. Implicación para la decisión del bid

### ¿El extra access favorece especialmente a `model_kiko`?

No especialmente.

| scenario | product | baseline_pnl | total_pnl | delta_vs_baseline | fill_count | maker_share | avg_abs_position |
| --- | --- | --- | --- | --- | --- | --- | --- |
| maf_uniform_125 | ASH_COATED_OSMIUM | 66456.000 | 68558.000 | 2102.000 | 2019.000 | 0.665 | 29.066 |
| maf_uniform_125 | INTARIAN_PEPPER_ROOT | 243484.000 | 244122.500 | 638.500 | 1501.000 | 0.384 | 71.078 |
| maf_uniform_125 | TOTAL | 309940.000 | 312680.500 | 2740.500 | 3520.000 | 0.545 |  |
| maf_front_125 | ASH_COATED_OSMIUM | 66456.000 | 70480.000 | 4024.000 | 2022.000 | 0.663 | 29.160 |
| maf_front_125 | INTARIAN_PEPPER_ROOT | 243484.000 | 243904.000 | 420.000 | 1493.000 | 0.381 | 70.647 |
| maf_front_125 | TOTAL | 309940.000 | 314384.000 | 4444.000 | 3515.000 | 0.543 |  |
| maf_depth_trade_125 | ASH_COATED_OSMIUM | 66456.000 | 82156.000 | 15700.000 | 2022.000 | 0.664 | 28.823 |
| maf_depth_trade_125 | INTARIAN_PEPPER_ROOT | 243484.000 | 247060.500 | 3576.500 | 1508.000 | 0.384 | 70.238 |
| maf_depth_trade_125 | TOTAL | 309940.000 | 329216.500 | 19276.500 | 3530.000 | 0.544 |  |

Comparado con G5:

| scenario | product | baseline_pnl | total_pnl | delta_vs_baseline | fill_count | maker_share | avg_abs_position |
| --- | --- | --- | --- | --- | --- | --- | --- |
| maf_uniform_125 | ASH_COATED_OSMIUM | 68006.000 | 69937.000 | 1931.000 | 2249.000 | 0.598 | 24.219 |
| maf_uniform_125 | INTARIAN_PEPPER_ROOT | 237406.000 | 240039.500 | 2633.500 | 969.000 | 0.352 | 74.914 |
| maf_uniform_125 | TOTAL | 305412.000 | 309976.500 | 4564.500 | 3218.000 | 0.524 |  |
| maf_front_125 | ASH_COATED_OSMIUM | 68006.000 | 71676.000 | 3670.000 | 2243.000 | 0.599 | 25.393 |
| maf_front_125 | INTARIAN_PEPPER_ROOT | 237406.000 | 240255.000 | 2849.000 | 955.000 | 0.352 | 74.751 |
| maf_front_125 | TOTAL | 305412.000 | 311931.000 | 6519.000 | 3198.000 | 0.525 |  |
| maf_depth_trade_125 | ASH_COATED_OSMIUM | 68006.000 | 83204.000 | 15198.000 | 2264.000 | 0.595 | 24.015 |
| maf_depth_trade_125 | INTARIAN_PEPPER_ROOT | 237406.000 | 242501.500 | 5095.500 | 962.000 | 0.353 | 75.022 |
| maf_depth_trade_125 | TOTAL | 305412.000 | 325705.500 | 20293.500 | 3226.000 | 0.523 |  |

Lectura:

- En `model_kiko`, el proxy MAF conservador suma ~`+2.7k` y el central ~`+4.4k`.
- Es menos delta que en `G5`, no más.
- Y en `model_kiko` el beneficio viene **más por ASH y por fill quality** que por desbloquear una gran mejora nueva en PEPPER.
- Eso me lleva a una conclusión fuerte: **Round 2 no me grita “reoptimizá el modelo”**. Me grita más bien: **“preservá el modelo bueno y decidí bien el bid”**.

## 11. Recomendación final: A / B / C

### **Opción A — Mantener `model_kiko` exactamente igual en su lógica de trading**

Es mi recomendación.

#### Por qué no B

- Sí, hay tweaks que mejoran el replay local.
- Pero no veo evidencia suficientemente robusta como para sacrificar la validación real fuerte de Round 1.
- Todos los buenos “tweaks” locales van en la misma dirección: **creer más fuerte y más rápido en el mismo drift observado**.
- Eso es exactamente el patrón que más fácil se convierte en overfit.

#### Por qué no C

- Ningún modelo cercano domina a `model_kiko`.
- Localmente, `model_kiko` sigue siendo el mejor candidato base.

## 12. Confianza de la recomendación

- **Media-alta**.
- Lo que sostiene la decisión:
  - `model_kiko` gana baseline y escenarios contra comparables fuertes.
  - La ventaja viene de PEPPER y es consistente día a día.
  - Los cambios que mejoran localmente tienen firma clara de overfit direccional.
- Lo que me falta para subir la confianza aún más:
  - más muestras fuera de estos 6 días, o
  - un entorno de simulación que replique mejor la aleatorización oficial del market access estándar.

## 13. Próximos pasos

1. **Mandaría `model_kiko` intacto** en su lógica de trading.
2. Le agregaría `bid()` como decisión separada de Round 2.
3. Si querés investigar un único tweak en paralelo, el menos indefendible para laboratorio sería `base_update_weight = 0.3`, **pero hoy NO lo mandaría a producción sin más evidencia**.
4. El mayor edge marginal esperable para Round 2, en mi opinión, viene más del **MAF / bid** que de retocar la estrategia base.
