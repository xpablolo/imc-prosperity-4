# Round 2 G5 analysis — Market Access Fee / bid()

## Resumen ejecutivo

- **Baseline local G5 sin extra access (Round 2):** 305,412.0 de PnL total.
- **PnL por producto en Round 2:** ASH 68,006.0 / PEPPER 237,406.0.
- **Delta estimado por extra market access (+25% quotes):** conservador 4,564.5, central 6,519.0, upper bound 20,293.5.
- **Delta usado para decidir bid de forma prudente:** 3,423.4 (haircut del 25% sobre el proxy conservador).
- **Recomendación explícita:** `bid() = 75`.
- **Rango alternativo razonable:** 60–100; 75 es el menor bid que queda dentro del 95% del máximo EV ponderado del grid testeado.
- **Confianza:** media. Delta sale positivo en todos los proxies razonables y G5 sigue dominando el ranking, pero el cutoff real de bids rivales sigue siendo el mayor foco de incertidumbre.

## Reglas de la ronda

- `bid()` es una puja ciega por acceso extra al mercado.
- Solo el top 50% de bids recibe acceso adicional.
- Si el bid es aceptado: acceso a 25% más quotes y pago único igual al bid.
- Si el bid no entra: no hay acceso extra y no se paga nada.
- En testing normal de Round 2 el `bid()` se ignora, así que el efecto del MAF **no** se observa directamente. Hay que estimarlo contrafactualmente.

## Descripción actual del modelo G5

- **Archivo principal:** `/Users/pablo/Desktop/prosperity/round_1/models/model_G5.py`.
- **ASH_COATED_OSMIUM:** market making estacionario con anchor lento alrededor de 10_000, reservation price sesgado por inventario y overlay microestructural (L1/L2 imbalance + microprice).
- **INTARIAN_PEPPER_ROOT:** estrategia trend-carry. Usa EMAs, slope local, residual z-score, flow signed, continuation/pullback adjustments y una política explícita de inventario objetivo alta.
- **Inventory management PEPPER (G5):** hold target agresivo (80 casi toda la sesión), carry floor alto y quote shaping para llegar rápido al inventario largo.
- **Execution:** mezcla taking controlado (thresholds agresivos) y making con tamaños pasivos asimétricos según gap al target.

### Herramientas existentes localizadas

- Backtester base: `/Users/pablo/Desktop/prosperity/round_1/tools/backtest.py`.
- Evaluaciones históricas de la familia F/G: `/Users/pablo/Desktop/prosperity/round_1/tools/evaluate_policy_architecture_research.py`.
- Este análisis añade: `/Users/pablo/Desktop/prosperity/round_2/tools/analyze_g5_maf.py`.

## Metodología de backtest

- Se usó el backtester local del repo, sin build y sin tocar el matching engine.
- **Datasets comparables usados:** Round 1 (`-2,-1,0`) y Round 2 (`-1,0,1`) para los mismos dos productos.
- **Round 0 quedó fuera** del análisis cuantitativo porque tradea EMERALDS/TOMATOES, o sea: no es comparable con ASH/PEPPER.
- El backtest es determinista y usa los supuestos del repo: órdenes agresivas cruzan libro visible; resting orders viven hasta el siguiente snapshot; market trades pueden ejecutar resting orders; sin latencia/slippage extra.

## Resultados baseline

### G5 baseline por round y producto

| round_label | product | total_pnl | max_drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position | daily_std_pnl |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Round 1 | ASH_COATED_OSMIUM | 63148.000 | -1254.000 | 2223.000 | 0.547 | 5.519 | 25.004 | 1066.720 |
| Round 1 | INTARIAN_PEPPER_ROOT | 240878.000 | -1520.000 | 782.000 | 0.352 | 4.831 | 77.023 | 518.422 |
| Round 1 | TOTAL | 304026.000 | -1744.000 | 3005.000 | 0.496 | 5.340 |  | 587.337 |
| Round 2 | ASH_COATED_OSMIUM | 68006.000 | -1233.000 | 2263.000 | 0.596 | 5.495 | 22.688 | 226.383 |
| Round 2 | INTARIAN_PEPPER_ROOT | 237406.000 | -1680.000 | 1021.000 | 0.342 | 4.940 | 74.866 | 922.660 |
| Round 2 | TOTAL | 305412.000 | -1981.000 | 3284.000 | 0.517 | 5.322 |  | 784.625 |

- **Round 1 total:** 304,026.0 con max DD combinado -1,744.0.
- **Round 2 total:** 305,412.0 con max DD combinado -1,981.0.
- Cambio total Round 1 → Round 2: +1,386.0. O sea: G5 siguió MUY estable entre datasets.

### Sensibilidad temporal / bloques (baseline Round 2)

- PEPPER sigue explicando casi toda la ventaja competitiva.
- G5 pasa gran parte de la sesión cerca del límite en PEPPER, así que el valor del extra access viene más por **llegar antes al carry target** y por **hacer fills más grandes**, no por multiplicar el número de fills.

### Capacity diagnostics PEPPER (Round 2)

| proxy | day | time_to_70 | time_to_80 | pct_pos_below_70 | pct_pos_at_80 |
| --- | --- | --- | --- | --- | --- |
| baseline | -1 | 23100 | 25500 | 0.1 | 0.5 |
| baseline | 0 | 0 | 0 | 0.2 | 0.4 |
| baseline | 1 | 0 | 0 | 0.2 | 0.4 |
| uniform_depth_125 | -1 | 17400 | 23100 | 0.1 | 0.5 |
| uniform_depth_125 | 0 | 0 | 2700 | 0.2 | 0.5 |
| uniform_depth_125 | 1 | 0 | 0 | 0.2 | 0.4 |
| front_bias_depth_25 | -1 | 12600 | 17400 | 0.2 | 0.5 |
| front_bias_depth_25 | 0 | 0 | 2700 | 0.2 | 0.5 |
| front_bias_depth_25 | 1 | 0 | 0 | 0.2 | 0.4 |
| uniform_depth_trade_125 | -1 | 17400 | 23100 | 0.1 | 0.5 |
| uniform_depth_trade_125 | 0 | 0 | 2700 | 0.2 | 0.5 |
| uniform_depth_trade_125 | 1 | 0 | 0 | 0.1 | 0.4 |

Lectura: en baseline, el day -1 tarda bastante en llegar a 70/80. Ahí sí hay cuello de botella de liquidez/acceso. En days 0/1 el modelo ya arranca muy cargado y el beneficio marginal del extra access es menor.

## Proxy de extra market access

No se puede backtestear `bid()` directo sobre el mercado normal porque el mercado de test ignora el bid. Entonces estimé `P1` con proxies explícitos y documentados.

### Proxies implementados

1. **Uniform depth +25%** — escala el volumen visible en todos los niveles existentes, trades iguales. Proxy conservador.
2. **Front-biased depth +25%** — concentra la parte extra cerca del touch (L1/L2/L3 con 1.45/1.20/1.15), manteniendo los mismos precios visibles.
3. **Depth +25% + trade flow +25%** — además escala market trades. Lo trato como upper bound razonable, NO como estimación central.

### P0 / P1 / Delta por proxy

| proxy | product | P0 | total_pnl | Delta | fill_count | maker_share | avg_fill_size | avg_abs_position |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| uniform_depth_125 | ASH_COATED_OSMIUM | 68006.000 | 69937.000 | 1931.000 | 2249.000 | 0.598 | 6.081 | 24.219 |
| uniform_depth_125 | INTARIAN_PEPPER_ROOT | 237406.000 | 240039.500 | 2633.500 | 969.000 | 0.352 | 5.539 | 74.914 |
| uniform_depth_125 | TOTAL | 305412.000 | 309976.500 | 4564.500 | 3218.000 | 0.524 | 5.918 |  |
| front_bias_depth_25 | ASH_COATED_OSMIUM | 68006.000 | 71676.000 | 3670.000 | 2243.000 | 0.599 | 6.564 | 25.393 |
| front_bias_depth_25 | INTARIAN_PEPPER_ROOT | 237406.000 | 240255.000 | 2849.000 | 955.000 | 0.352 | 5.853 | 74.751 |
| front_bias_depth_25 | TOTAL | 305412.000 | 311931.000 | 6519.000 | 3198.000 | 0.525 | 6.352 |  |
| uniform_depth_trade_125 | ASH_COATED_OSMIUM | 68006.000 | 83204.000 | 15198.000 | 2264.000 | 0.595 | 6.765 | 24.015 |
| uniform_depth_trade_125 | INTARIAN_PEPPER_ROOT | 237406.000 | 242501.500 | 5095.500 | 962.000 | 0.353 | 5.949 | 75.022 |
| uniform_depth_trade_125 | TOTAL | 305412.000 | 325705.500 | 20293.500 | 3226.000 | 0.523 | 6.521 |  |

### Lectura de Delta

- **Conservador (`uniform_depth_125`)**: Δ total = 4,564.5.
- **Central (`front_bias_depth_25`)**: Δ total = 6,519.0.
- **Upper bound (`uniform_depth_trade_125`)**: Δ total = 20,293.5.
- El hallazgo clave es que el extra access **no** se traduce en +25% PnL. El efecto parece más bien estar en el rango de low single-digit percent sobre el PnL total si asumimos libro extra sin escalar también los market trades.
- Además, en los proxies conservadores el fill count incluso baja levemente mientras sube el avg fill size. O sea: el edge viene por **mejor tamaño/quality of access**, no por hyperactivity.

## Formalización matemática del bid

Defino:

- `P0`: PnL sin extra access.
- `P1`: PnL con extra access estimado por proxy.
- `Delta = P1 - P0`.
- `b`: bid.
- `A(b)`: indicador de aceptación del bid.

Entonces:

`Pi(b) = P0 + A(b) * (Delta - b)`

### Por qué bid y estrategia NO son lo mismo

- La lógica de trading decide **qué hacer** una vez que ves el mercado.
- El bid decide **cuánto mercado ves**.
- Cambiar `b` sin cambiar el mercado observable no dice nada útil, porque en el test normal el bid se ignora.
- Por eso la secuencia correcta es: **(1) estimar Delta contrafactual, (2) modelar aceptación q(b), (3) optimizar b**.

## Modelo de teoría de juegos para el cutoff

No hay histórico de bids rivales en el repo. Entonces modelé el cutoff aleatorio `C` con escenarios logísticos sobre la mediana rival:

| escenario | median_bid | slope | weight | lectura |
| --- | --- | --- | --- | --- |
| Competencia baja | 15.00 | 5.00 | 0.20 | Campo poco agresivo: bids rivales en los teens. Lo tomo como ancla floja porque el repo viejo devolvía 15 en stubs históricos, pero NO como evidencia dura. |
| Central | 30.00 | 7.00 | 0.50 | Escenario central sin histórico usable: cutoff alrededor de 30 con transición relativamente suave. |
| Competencia alta | 50.00 | 10.00 | 0.30 | Escenario pesimista: muchos equipos pujan en serio y el cutoff relevante se mueve a la zona 40-60. |

Defino `q(b) = Pr(C < b)` con CDF logística. Luego:

`E[Pi(b)] ≈ E[P0] + q(b) * (E[Delta] - b)`

Para ser prudente, NO optimicé con el Delta más alto, sino con:

- `Delta_risk_adjusted = 0.75 * Delta_conservative = 3,423.4`

### Grid de bids evaluado

| bid | q_low_competition | q_central | q_high_competition | ev_low_competition | ev_central | ev_high_competition | weighted_ev_risk_adjusted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.000 | 0.047 | 0.014 | 0.007 | 162.357 | 46.479 | 22.912 | 62.584 |
| 5.000 | 0.119 | 0.027 | 0.011 | 407.480 | 93.482 | 37.557 | 139.504 |
| 10.000 | 0.269 | 0.054 | 0.018 | 917.998 | 185.392 | 61.394 | 294.713 |
| 15.000 | 0.500 | 0.105 | 0.029 | 1704.188 | 357.881 | 99.907 | 549.750 |
| 20.000 | 0.731 | 0.193 | 0.047 | 2488.066 | 657.945 | 161.408 | 875.008 |
| 25.000 | 0.881 | 0.329 | 0.076 | 2993.279 | 1116.885 | 257.795 | 1234.436 |
| 30.000 | 0.953 | 0.500 | 0.119 | 3232.441 | 1696.688 | 404.500 | 1616.182 |
| 40.000 | 0.993 | 0.807 | 0.269 | 3360.731 | 2729.296 | 909.930 | 2309.773 |
| 50.000 | 0.999 | 0.946 | 0.500 | 3370.302 | 3190.156 | 1686.688 | 2775.145 |
| 60.000 | 1.000 | 0.986 | 0.731 | 3362.960 | 3317.711 | 2458.824 | 3069.095 |
| 75.000 | 1.000 | 0.998 | 0.924 | 3348.354 | 3342.977 | 3094.373 | 3269.471 |
| 100.000 | 1.000 | 1.000 | 0.993 | 3323.375 | 3323.224 | 3301.132 | 3316.627 |

- El **máximo EV ponderado** del grid aparece en la cola alta, pero la curva se aplana fuerte.
- Usando una regla downside-aware simple (*elegir el menor bid dentro del 95% del EV máximo ponderado*), sale **75**.

## Filosofía de riesgo

- No usé el proxy más optimista para decidir.
- No asumí que `+25% quotes => +25% PnL`.
- No extrapolé Round 0 porque ni siquiera comparte productos.
- Apliqué haircut explícito al Delta conservador para absorber error de modelado.
- La recomendación final privilegia **robustez > aparente precisión**.

## Recomendación de bid

### Recomendación principal: `bid() = 75`

Por qué:

- El baseline G5 ya es muy fuerte y el Delta estimado del extra access es claramente positivo incluso en el proxy conservador (4,564.5).
- En el grid probado, 75 es el menor bid que queda prácticamente en la meseta del EV ponderado.
- Si el cutoff real termina siendo más bajo, 75 no te cambia materialmente el net benefit frente a 60 o 50.
- Si el cutoff real es bastante más alto de lo esperado, 75 te deja mejor parado que un bid tímido.

### Rango alternativo razonable

- **60–100** si querés moverte en la meseta del EV del grid.
- **50** todavía es defendible si tu sesgo es MUY conservador y querés minimizar el pago en caso de aceptación.
- **<30** me parece demasiado tímido para un modelo con este Delta esperado.

## Posibles mejoras de estrategia G5 para esta ronda

### 1) ASH — tocar poco

- ASH no está limitado por posición máxima; su avg |pos| ronda 22–25.
- Con extra access, el beneficio parece venir de fills un poco más grandes, no de cambiar la tesis.
- Cambio robusto sugerido si se implementa una versión Round 2: **si `bid()` fue aceptado, subir tamaño pasivo 10–15% en ASH sin estrechar agresivamente el ancho de quotes**.

### 2) PEPPER — usar el extra access para llegar antes al carry, no para sobreoperar

- PEPPER pasa muchísimo tiempo cerca de +80. Entonces el cuello de botella es **early accumulation**, sobre todo en day -1.
- Con acceso extra, conviene usar la ventaja para llegar antes al target cuando `position < 70` y la señal sigue alineada.
- Cambio robusto sugerido:
  - solo cuando el bid haya sido aceptado y `position_gap > 8`, permitir un poco más de size agresivo/pasivo del lado comprador;
  - NO hacerlo una vez que ya estés >70, porque ahí el beneficio marginal cae y el riesgo de churn sube;
  - mantener o incluso endurecer el trim cuando el flow y el imbalance se ponen en contra.

### 3) No estrechar spreads por reflejo

- El proxy no dice “tradeá más”; dice “llenate mejor”.
- O sea: prefiero **más tamaño condicional** antes que quote widths mucho más agresivos.

### 4) G5 sigue siendo baseline correcta

Probé también dos alternativas fuertes del mismo family tree sobre Round 2:

| model | baseline_total_pnl | uniform_depth_125_total_pnl | delta_proxy_conservative |
| --- | --- | --- | --- |
| model_G5 | 305412.000 | 309976.500 | 4564.500 |
| model_G2 | 303851.000 | 308807.500 | 4956.500 |
| model_F3 | 303502.000 | 307865.500 | 4363.500 |

G5 sigue arriba tanto en baseline como bajo el proxy conservador. Así que, salvo que quieras rehacer arquitectura, no veo razón fuerte para abandonar G5.

## Limitaciones y supuestos

- El mayor agujero de información es la distribución real de bids rivales.
- El segundo agujero es cuánto del 20% “faltante” del flujo estándar representa quotes extra versus market trades extra.
- Por eso reporto tres proxies y separo **conservative / central / upper bound**.

## Próximos pasos

1. Si querés ejecutar esto de nuevo: `./.venv_backtest/bin/python /Users/pablo/Desktop/prosperity/round_2/tools/analyze_g5_maf.py`
2. Si querés pasar de análisis a implementación: crear una variante Round 2 de G5 con `bid()` y gating explícito `access_granted` para ajustar tamaños en ASH/PEPPER solo cuando haya valor.
3. Si querés afinar todavía más: correr sensibilidad adicional con bid grid extendido y un stress cutoff más alto (ej. mediana 60–70).

## Recomendación final explícita

- **Bid recomendado:** `75`
- **Por qué:** Delta robusto positivo, G5 sigue siendo el mejor baseline, y 75 entra en la meseta del EV sin necesitar ir al extremo por reflejo.
- **Rango alternativo:** `60–100`
- **Confianza:** media