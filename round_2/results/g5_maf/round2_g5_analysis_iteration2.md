# Round 2 G5 analysis — iteration 2

Base explícita usada: `/Users/pablo/Desktop/prosperity/round_2/results/g5_maf/round2_g5_analysis.md` + CSVs previos ya generados en `/Users/pablo/Desktop/prosperity/round_2/results/g5_maf`.

## 1. Qué partes del análisis previo se confirman

- **G5 sigue siendo baseline razonable.** No apareció evidencia nueva que justifique cambiar de familia por una diferencia marginal.
- **El Delta del extra access sigue siendo positivo** en todos los proxies razonables: conservador `4,564.5`, central `6,519.0`, upper bound `20,293.5`.
- **PEPPER sigue siendo el canal principal de monetización** del market access extra.
- **La lectura microestructural anterior se mantiene:** el beneficio parece venir más por mejor fill quality / tamaño y timing de inventario que por hiperactividad.

## 2. Qué partes del análisis previo eran frágiles

- La recomendación previa `bid() = 75` **no era un óptimo limpio**.
- El propio CSV previo muestra que el EV máximo estaba en el borde de la grid anterior (bid=100), lo que significa que la elección de `75` salió de una **grid truncada**, no de una meseta plenamente explorada.
- Regla previa exacta: *elegir el menor bid dentro del 95% del EV máximo del grid*. Eso devolvió `75` porque el máximo estaba en el extremo superior disponible.
- `75` hay que interpretarlo entonces como **el borde inferior de una zona alta** bajo el prior original, no como un número sagrado.

### Supuestos previos auditados

- Delta de decisión = `0.75 * Delta_conservative`.
- Cutoff rival modelado con tres escenarios logísticos muy suaves (medianas 15 / 30 / 50).
- Grid original limitada a bids hasta 100.
- Eso vuelve sólida la señal “los bids muy bajos son malos”, pero frágil la precisión del número exacto.

## 3. Reestimación del bid con grid ampliada

Usé una grid bastante más amplia:

`0, 10, 25, 40, 50, 60, 75, 90, 100, 125, 150, 175, 200, 250, 300, 400, 500`

La idea es simple: si Delta vale miles, el coste marginal de subir de 75 a 100 o 150 puede ser casi irrelevante comparado con una mejora modesta en probabilidad de aceptación.

### Plateau summary (delta risk-adjusted)

| scenario_family | best_bid | best_ev | plateau_99 | plateau_97 | plateau_95 |
| --- | --- | --- | --- | --- | --- |
| moderate_alt | 175 | 3233.5 | 150,175,200 | 150,175,200,250 | 125,150,175,200,250,300 |
| prior_reused | 100 | 3316.6 | 90,100,125 | 75,90,100,125,150,175,200 | 75,90,100,125,150,175,200,250 |
| tough_alt | 250 | 3156.2 | 250 | 200,250,300 | 200,250,300,400 |
| very_tough_alt | 300 | 3072.3 | 300 | 250,300,400 | 250,300,400,500 |

### EV y aceptación ponderada en bids clave

| scenario_family_label | bid | weighted_acceptance | weighted_ev |
| --- | --- | --- | --- |
| Moderate alternative | 75 | 0.669 | 2238.773 |
| Moderate alternative | 100 | 0.841 | 2794.979 |
| Moderate alternative | 150 | 0.982 | 3215.689 |
| Moderate alternative | 200 | 0.999 | 3219.650 |
| Moderate alternative | 250 | 1.000 | 3173.146 |
| Prior reused | 75 | 0.976 | 3269.471 |
| Prior reused | 100 | 0.998 | 3316.627 |
| Prior reused | 150 | 1.000 | 3273.330 |
| Prior reused | 200 | 1.000 | 3223.375 |
| Prior reused | 250 | 1.000 | 3173.375 |
| Tough alternative | 75 | 0.346 | 1159.248 |
| Tough alternative | 100 | 0.566 | 1881.125 |
| Tough alternative | 150 | 0.841 | 2752.930 |
| Tough alternative | 200 | 0.964 | 3107.052 |
| Tough alternative | 250 | 0.995 | 3156.215 |
| Very tough alternative | 75 | 0.219 | 734.612 |
| Very tough alternative | 100 | 0.347 | 1153.768 |
| Very tough alternative | 150 | 0.667 | 2182.552 |
| Very tough alternative | 200 | 0.841 | 2710.880 |
| Very tough alternative | 250 | 0.941 | 2986.949 |

### Conclusión cuantitativa de esta sección

- **`75` NO es un óptimo identificable.**
- Bajo el prior viejo, la meseta 99% ya incluye `90–125`.
- Bajo escenarios moderados y duros, el máximo se desplaza a `175–300`.
- En otras palabras: lo que está identificado no es “75 exacto”, sino una **banda alta de bids razonables**, y la banda se mueve según cómo creas que pujan los rivales.

## 4. Análisis marginal del coste vs aceptación

La condición exacta para preferir `b2` frente a `b1` es:

`q(b2) * (Delta - b2) > q(b1) * (Delta - b1)`

Equivalentemente:

`q(b2) / q(b1) > (Delta - b1) / (Delta - b2)`

o en términos de aumento absoluto mínimo de aceptación:

`Delta_q > q(b1) * (b2 - b1) / (Delta - b2)`

### Umbral marginal requerido (risk-adjusted Delta)

| scenario_family | from_bid | to_bid | q1_weighted | q2_weighted | actual_abs_q_increase | required_abs_q_increase_at_q1 |
| --- | --- | --- | --- | --- | --- | --- |
| prior_reused | 75 | 100 | 0.9764 | 0.9980 | 0.0215 | 0.0073 |
| moderate_alt | 75 | 100 | 0.6686 | 0.8410 | 0.1724 | 0.0050 |
| tough_alt | 75 | 100 | 0.3462 | 0.5660 | 0.2198 | 0.0026 |
| very_tough_alt | 75 | 100 | 0.2194 | 0.3472 | 0.1278 | 0.0017 |
| prior_reused | 100 | 150 | 0.9980 | 1.0000 | 0.0020 | 0.0152 |
| moderate_alt | 100 | 150 | 0.8410 | 0.9824 | 0.1414 | 0.0128 |
| tough_alt | 100 | 150 | 0.5660 | 0.8410 | 0.2750 | 0.0086 |
| very_tough_alt | 100 | 150 | 0.3472 | 0.6668 | 0.3196 | 0.0053 |
| prior_reused | 150 | 200 | 1.0000 | 1.0000 | 0.0000 | 0.0155 |
| moderate_alt | 150 | 200 | 0.9824 | 0.9988 | 0.0165 | 0.0152 |
| tough_alt | 150 | 200 | 0.8410 | 0.9639 | 0.1229 | 0.0130 |
| very_tough_alt | 150 | 200 | 0.6668 | 0.8410 | 0.1742 | 0.0103 |
| prior_reused | 200 | 300 | 1.0000 | 1.0000 | 0.0000 | 0.0320 |
| moderate_alt | 200 | 300 | 0.9988 | 1.0000 | 0.0012 | 0.0320 |
| tough_alt | 200 | 300 | 0.9639 | 0.9993 | 0.0353 | 0.0309 |
| very_tough_alt | 200 | 300 | 0.8410 | 0.9836 | 0.1426 | 0.0269 |

### Lectura importante

- Pasar de **75 → 100** requiere apenas un aumento relativo de aceptación de ~**0.75%** bajo `Delta_risk_adjusted=3,423.4`.
- Pasar de **100 → 150** requiere ~**1.53%** relativo.
- Pasar de **150 → 200** requiere ~**1.55%** relativo.
- Eso es poquísimo. Entonces, si pensás que subir el bid mejora aunque sea un poco la chance de entrar, bids más altos se justifican enseguida.

## 5. Revisión crítica del cutoff rival

### Qué se había supuesto antes

- Tres escenarios logísticos muy suaves con medianas bajas (15, 30, 50).
- Pesos 20% / 50% / 30%.
- Cero evidencia dura de bids rivales en este repo.

### Qué evidencia histórica real sí existe

- Busqué referencias de bidding en el repo.
- Lo único que aparece son stubs viejos de Round 0 devolviendo `15` en varios modelos.
- Eso **NO** sirve como histórico útil para el cutoff rival de esta ronda.

### Qué cambia al endurecer el cutoff

- Si los rivales pujan suave, la zona buena empieza cerca de 90–125.
- Si los rivales pujan moderado, la zona buena sube a 150–200.
- Si los rivales pujan duro, la zona buena sube todavía más (200–300).

### Conclusión crítica

- **La decisión final está dominada por la incertidumbre sobre los rivales.**
- Lo que sabemos bien es que un bid alto tiene mucho más sentido que uno bajo.
- Lo que NO sabemos bien es dónde cae el cutoff del top 50%. Ese punto domina si conviene 100, 150 o 200+.

## 6. Verificación de access_granted / implementabilidad

- Firma actual de `TradingState`: `traderData, timestamp, listings, order_depths, own_trades, market_trades, position, observations`.
- `access_granted` explícito disponible: **False**.
- Hits reales de runtime flags en datamodel/backtester: `[]`.

### Conclusión

- **NO encontré una señal formal tipo `access_granted` en `TradingState`, `observations` ni en el backtester local.**
- Entonces no corresponde diseñar la estrategia alrededor de un booleano ficticio.
- Si el acceso extra existe en runtime, la señal observable real sería **ver más profundidad / más volumen visible / más oportunidades de fill**, no un flag explícito.

### Implicación práctica

Cualquier mejora razonable tiene que depender solo de variables observables:

- profundidad visible acumulada
- imbalance
- flow reciente
- spread visible
- gap respecto al target inventory

## 7. Análisis detallado de PEPPER capacity timing

| proxy | day | baseline_day_pnl | proxy_day_pnl | delta_day_pnl | baseline_time_to_70 | proxy_time_to_70 | delta_time_to_70 | baseline_time_to_80 | proxy_time_to_80 | delta_time_to_80 | baseline_pct_pos_below_70 | proxy_pct_pos_below_70 | baseline_pct_pos_at_80 | proxy_pct_pos_at_80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| front_bias_depth_25 | -1 | 78538.0 | 79194.5 | 656.5 | 23100.0 | 12600.0 | -10500.0 | 25500.0 | 17400.0 | -8100.0 | 0.1 | 0.2 | 0.5 | 0.5 |
| front_bias_depth_25 | 0 | 78670.0 | 80127.5 | 1457.5 | 0.0 | 0.0 | 0.0 | 0.0 | 2700.0 | 2700.0 | 0.2 | 0.2 | 0.4 | 0.5 |
| front_bias_depth_25 | 1 | 80198.0 | 80933.0 | 735.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 | 0.2 | 0.4 | 0.4 |
| uniform_depth_125 | -1 | 78538.0 | 79416.0 | 878.0 | 23100.0 | 17400.0 | -5700.0 | 25500.0 | 23100.0 | -2400.0 | 0.1 | 0.1 | 0.5 | 0.5 |
| uniform_depth_125 | 0 | 78670.0 | 79630.0 | 960.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2700.0 | 2700.0 | 0.2 | 0.2 | 0.4 | 0.5 |
| uniform_depth_125 | 1 | 80198.0 | 80993.5 | 795.5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 | 0.2 | 0.4 | 0.4 |
| uniform_depth_trade_125 | -1 | 78538.0 | 80065.5 | 1527.5 | 23100.0 | 17400.0 | -5700.0 | 25500.0 | 23100.0 | -2400.0 | 0.1 | 0.1 | 0.5 | 0.5 |
| uniform_depth_trade_125 | 0 | 78670.0 | 80573.5 | 1903.5 | 0.0 | 0.0 | 0.0 | 0.0 | 2700.0 | 2700.0 | 0.2 | 0.2 | 0.4 | 0.5 |
| uniform_depth_trade_125 | 1 | 80198.0 | 81862.5 | 1664.5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 | 0.1 | 0.4 | 0.4 |

### Qué me dice esto de verdad

| proxy | total_delta_pnl | day_minus1_delta | day0_delta | day1_delta | avg_delta_time_to_80 |
| --- | --- | --- | --- | --- | --- |
| uniform_depth_trade_125 | 5095.5 | 1527.5 | 1903.5 | 1664.5 | 100.0 |
| front_bias_depth_25 | 2849.0 | 656.5 | 1457.5 | 735.0 | -1800.0 |
| uniform_depth_125 | 2633.5 | 878.0 | 960.0 | 795.5 | 100.0 |

Lectura crítica:

- En baseline, PEPPER ya pasa gran parte del tiempo muy cerca de +80.
- El proxy sí acelera la llegada a 70/80, sobre todo en day -1.
- **PERO** el Delta diario de PEPPER no queda concentrado solo en day -1. En el proxy conservador, los tres días aportan de forma bastante repartida.
- Eso sugiere que el valor del extra access no es solo “entrar antes al carry”, sino también **reciclar mejor una vez que ya estás cargado**.
- Dicho más simple: el acceso extra ayuda al inicio del episodio, pero también mejora el fill quality mientras defendés y renovás la posición grande.

## 8. Robustez del modelo G5 frente a alternativas

| model | baseline_total_pnl | uniform_depth_125_total_pnl |
| --- | --- | --- |
| model_G5 | 305412.0 | 309976.5 |
| model_G2 | 303851.0 | 308807.5 |
| model_F3 | 303502.0 | 307865.5 |

### Lectura

- La ventaja de G5 sobre G2/F3 existe, pero no es enorme en porcentaje del total.
- En Round 2 baseline, G5 le saca ~1.6k a G2 y ~1.9k a F3.
- Eso es material, pero bastante menor que la incertidumbre del problema del bid y del cutoff rival.
- Además, el ranking no cambia con el proxy conservador.

### Conclusión

- **No veo motivo suficiente para cambiar de familia.**
- Si fueras a tocar algo, tiene más sentido microajustar G5 que saltar a G2/F3 por una diferencia chica.

## 9. Cambios mínimos recomendados en G5

### ASH

- Mantener el core igual.
- Como mucho, permitir un poco más de tamaño pasivo cuando la profundidad visible top-3 supere claramente su nivel normal.
- No recomiendo estrechar spreads globalmente.

### PEPPER

Cambio mínimo y defendible:

- **Solo cuando** `position_gap = target_inventory - position` sea grande (ej. >= 8 o 10),
- **y** la señal siga alineada (`l2_imbalance` no en contra, `flow_recent` no claramente adverso, spread aceptable),
- **y** la profundidad visible acumulada sea rica,
- permitir un pequeño aumento de `passive_buy_size` y/o un step-in comprador algo más agresivo.

Importante:

- eso **NO** depende de saber si el bid fue aceptado;
- depende solo de que el mercado observable te muestre realmente más oportunidad.

### Qué NO haría

- No metería lógica `if access_granted:`.
- No estrecharía los spreads de forma ciega.
- No aumentaría agresividad una vez que ya estás pegado a +80.

## 10. Limitaciones restantes

- Seguimos sin conocer la distribución real de bids rivales.
- El valor exacto de Delta sigue dependiendo de proxies, aunque la dirección y el orden de magnitud ya están bastante mejor establecidos.
- El backtest local es determinista; no estima la variabilidad del feed aleatorizado entre submissions.

## Recomendación final actualizada

- **¿Debés interpretar 75 como número concreto?** No. Hay que interpretarlo como **borde inferior de una zona alta**, no como óptimo preciso.
- **Bid puntual recomendado hoy:** `150`.
- **Banda realmente defendible:** `100–200`.
- **Si querés ser más conservador con el gasto:** `100`.
- **Si querés priorizar probabilidad de aceptación:** `200`.
- **Mantengo G5:** sí.
- **¿Haría cambios al modelo antes de enviar?** Solo microcambios observables en PEPPER; si no podés validarlos rápido, mandaría G5 casi intacto.
- **Confianza en la decisión:** media. Lo sólido es la zona alta; lo incierto es el cutoff rival exacto.