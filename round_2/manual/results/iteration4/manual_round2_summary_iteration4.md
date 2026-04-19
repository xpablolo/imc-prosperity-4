# IMC Prosperity Round 2 Manual — Iteration 4 summary

## 1. Resumen ejecutivo

- NO empecé desde cero: reutilicé el solver exacto `Research/Scale`, el motor exacto de ranking con ties y los artefactos de `iteration3` como benchmark de comparación.
- La gran novedad de `iteration4` es la **mezcla nueva** con estos pesos: IA 30%, Nash 23%, just-above 15%, clásicos 10%, naive 10%, high-speed 7%, random 5%.
- El componente IA se modeló explícitamente como **dos normales truncadas en 20–40** con medias 25 y 35, usando el mismo sigma en el escenario central por interpretabilidad.
- El componente Nash se modeló como una **quantal response de un paso contra el field no racional**. También calculé el fixed-point completamente autorreferencial como stress test, pero lo traté como cota agresiva, no como escenario central.

- **Recomendación central:** `Speed* = 42`, `Research* = 15`, `Scale* = 43`.
- **Recomendación robusta:** `v = 42`.
- **Recomendación más conservadora:** `v = 46`.
- **Banda defendible:** `41–46`.

## 2. Qué se reutiliza de iteration3 y qué cambia ahora

| topic | status | detail |
| --- | --- | --- |
| Iteration3 exact economics | reused | Reused the exact integer Research/Scale solver from `manual_round2_utils.compute_rs_table()` without modification. |
| Iteration3 exact ranking | reused | Reused the tie-aware ranking engine where rank depends on the number of strictly higher speeds only. |
| Iteration3 artifacts | reused | Loaded the iteration3 mixture PMF and final recommendation to compare the new scenario against the previous central scenario. |
| New work in iteration4 | new | Implemented a brand new central mixture with an explicit two-normal AI component, a one-step quantal strategic component, a 0/5 just-above cluster, classic-number choices, a deterministic-naive component and updated sensitivity. |

## 3. Subproblema exacto Research/Scale

Para cada `v`, primero se resuelve exactamente `r*(v), s*(v)` con enteros. Como `Research` y `Scale` son crecientes, siempre se usa todo el presupuesto factible: `r + s + v = 100`.

| v | r_star | s_star | gross_value | budget_used |
| --- | --- | --- | --- | --- |
| 20.0 | 19.0 | 61.0 | 554342.0 | 50000.0 |
| 25.0 | 18.0 | 57.0 | 509122.6 | 50000.0 |
| 30.0 | 17.0 | 53.0 | 464702.0 | 50000.0 |
| 35.0 | 16.0 | 49.0 | 421134.0 | 50000.0 |
| 36.0 | 16.0 | 48.0 | 412539.5 | 50000.0 |
| 40.0 | 15.0 | 45.0 | 378480.0 | 50000.0 |
| 41.0 | 15.0 | 44.0 | 370069.4 | 50000.0 |
| 45.0 | 14.0 | 41.0 | 336810.4 | 50000.0 |

## 4. Ranking exacto con empates

La parte crítica del manual sigue siendo esta:

- `rank(v) = # {players con speed estrictamente mayor} + 1`
- los empates comparten el mínimo rank del bloque
- el multiplier baja linealmente de `0.9` a `0.1`

Eso hace que los ties importen MUCHO: si hay cluster en `35`, elegir `35` no te despega; elegir `36` sí te salta toda esa masa.

| example | my_speed | others | rank | multiplier |
| --- | --- | --- | --- | --- |
| ties | 70 | [70, 70, 50, 40, 40, 30] | 1 | 0.900 |
| ties | 70 | [70, 70, 50, 40, 40, 30] | 1 | 0.900 |
| ties | 70 | [70, 70, 50, 40, 40, 30] | 1 | 0.900 |
| ties | 50 | [70, 70, 70, 40, 40, 30] | 4 | 0.500 |
| ties | 40 | [70, 70, 70, 50, 40, 30] | 5 | 0.367 |
| ties | 40 | [70, 70, 70, 50, 40, 30] | 5 | 0.367 |
| ties | 30 | [70, 70, 70, 50, 40, 40] | 7 | 0.100 |
| three_players | 95 | [20, 10] | 1 | 0.900 |
| three_players | 20 | [95, 10] | 2 | 0.500 |
| three_players | 10 | [95, 20] | 3 | 0.100 |

## 5. Construcción explícita de la mezcla nueva

### 5.1 Pesos usados

| tipo | peso |
| --- | --- |
| Recomendaciones de IA | 0.30 |
| Nash / racionales | 0.23 |
| Just-above 0 o 5 | 0.15 |
| Allocations simples / focal | 0.10 |
| Naive / optimización incompleta | 0.10 |
| High speed / speed-race parcial | 0.07 |
| Aleatorio | 0.05 |

### 5.2 Cómo se modela cada tipo

- **IA (30%)**: mezcla de dos normales discretizadas y truncadas a `20–40`, con medias `25` y `35`, peso interno `25%/75%`. En el escenario central usé `sigma = 3.5` para ambos clusters: lo bastante concentrado para producir recomendación repetible, pero no tan estrecho como para suponer un número único mágico.
- **Nash / racionales (23%)**: respuesta cuasi-racional de un paso al field no racional. Primero armo la mezcla de todos los tipos excepto Nash, calculo la curva exacta de EV contra ese field y después convierto esa curva en una PMF con softmax. Esto es más prudente que asumir common knowledge total entre racionales.
- **Just-above 0/5 (15%)**: PMF discreta sobre `1,6,11,16,21,26,31,36,41,46,...`, con más masa en `31,36,41,46` porque ahí es donde el patrón 0/5 realmente cruza con la zona económicamente plausible del juego.
- **Clásicos / bonitos (10%)**: PMF discreta sobre `7,13,17,23,27,33,37`, priorizando `33` y `37` como números mentalmente atractivos y además relevantes en este problema.
- **Naive (10%)**: distribución derivada de una optimización incompleta que reemplaza el juego estratégico por un multiplier lineal heurístico creciente con `v`; eso concentra masa en speeds medios-altos, sobre todo alrededor de `35–37`.
- **High-speed parcial (7%)**: normal truncada en `50–80`, centrada en `64`.
- **Aleatorio (5%)**: uniforme discreta en `0..100`.

### 5.3 Resumen cuantitativo de componentes

| component | weight_total | mean_speed | top_speeds | top_probs_pct |
| --- | --- | --- | --- | --- |
| Recomendaciones de IA | 0.30 | 32.49 | 35, 34, 36, 33, 37 | 14.9%, 13.1%, 13.1%, 9.1%, 9.1% |
| Nash / racionales | 0.23 | 41.56 | 41, 42, 40, 43, 39 | 9.1%, 8.9%, 8.8%, 8.2%, 8.0% |
| Just-above 0 o 5 | 0.15 | 35.94 | 41, 35, 36, 31, 46 | 18.0%, 16.0%, 16.0%, 14.0%, 12.0% |
| Allocations simples / focal | 0.10 | 34.41 | 40, 50, 33, 25, 20 | 18.0%, 17.0%, 16.0%, 15.0%, 14.0% |
| Naive / optimización incompleta | 0.10 | 32.36 | 32, 33, 31, 30, 34 | 6.6%, 6.5%, 6.5%, 6.2%, 6.2% |
| High speed / speed-race parcial | 0.07 | 64.34 | 64, 63, 65, 66, 62 | 4.9%, 4.8%, 4.8%, 4.7%, 4.7% |
| Aleatorio | 0.05 | 50.00 | 0, 64, 74, 73, 72 | 1.0%, 1.0%, 1.0%, 1.0%, 1.0% |

### 5.4 Perfil cuantitativo del componente Nash

| v | mean_pnl | mean_multiplier | p_higher | quantal_prob |
| --- | --- | --- | --- | --- |
| 41.0000 | 224892.2052 | 0.7428 | 0.1965 | 0.0911 |
| 42.0000 | 219489.3994 | 0.7451 | 0.1936 | 0.0888 |
| 40.0000 | 219477.0441 | 0.7120 | 0.2350 | 0.0881 |
| 43.0000 | 213921.9073 | 0.7471 | 0.1911 | 0.0817 |
| 39.0000 | 216128.1495 | 0.6879 | 0.2652 | 0.0804 |
| 44.0000 | 208361.6916 | 0.7488 | 0.1890 | 0.0711 |
| 38.0000 | 217848.5791 | 0.6775 | 0.2781 | 0.0692 |
| 45.0000 | 202700.3889 | 0.7503 | 0.1872 | 0.0586 |
| 37.0000 | 215650.8346 | 0.6576 | 0.3029 | 0.0563 |
| 46.0000 | 203098.4102 | 0.7702 | 0.1622 | 0.0460 |

### 5.5 Stress test: fixed-point autorreferencial

Si fuerzo un fixed-point completamente autorreferencial entre los Nash-like, la masa estratégica se dispara hacia arriba. Eso sirve como cota agresiva, pero es DEMASIADO fuerte como escenario central porque supone coordinación estratégica mutua mucho más dura.

| iteration | mean_speed | l1_change | top_speeds | top_probs_pct | best_ev_v | best_ev |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | 45.52 | 1.00 | 46, 44, 47, 45, 43 | 66.8%, 18.9%, 5.3%, 5.2%, 3.0% | 46 | 212085.70 |
| 9 | 45.98 | 0.36 | 46, 47, 44, 45, 43 | 75.0%, 14.4%, 6.6%, 1.8%, 1.0% | 46 | 209514.93 |
| 10 | 46.53 | 0.80 | 47, 46, 48, 44, 45 | 51.2%, 41.5%, 3.7%, 2.3%, 0.6% | 47 | 206038.26 |
| 11 | 46.94 | 0.58 | 47, 46, 48, 44, 49 | 73.6%, 14.5%, 9.8%, 0.8%, 0.6% | 47 | 204260.93 |
| 12 | 47.32 | 0.47 | 47, 48, 46, 49, 50 | 60.5%, 30.8%, 5.1%, 2.1%, 0.9% | 47 | 200310.44 |

## 6. Qué distribución total de Speed inducen estos pesos

| speed | pmf_pct |
| --- | --- |
| 35.00 | 9.00 |
| 36.00 | 7.90 |
| 34.00 | 6.31 |
| 33.00 | 5.36 |
| 41.00 | 5.06 |
| 37.00 | 4.52 |
| 40.00 | 4.35 |
| 31.00 | 3.58 |
| 38.00 | 3.50 |
| 25.00 | 3.35 |

Lectura técnica:

- El **cluster IA en torno a 35** empuja con fuerza la masa total hacia `34–36`.
- El componente **just-above** mete escalones claros en `26`, `31`, `36`, `41`.
- El componente Nash no destruye esos clusters; los **reordena** alrededor de donde el salto de ties compensa mejor el coste económico de subir `v`.
- El fixed-point autorreferencial, en cambio, empuja demasiado arriba y por eso lo traté como stress test, no como centro de gravedad metodológico.

## 7. Monte Carlo poblacional

El Monte Carlo central usa muchas poblaciones simuladas con `N = 50` y seeds fijas. Para cada población y para cada `v`, recalcula rank exacto, multiplier exacto y PnL usando el `r*(v), s*(v)` exacto.

| v | mean_pnl | p10 | p90 | mean_regret | max_regret | mean_multiplier | mean_rank |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 26.0 | 58176.7 | 32684.6 | 81682.8 | 155063.4 | 241427.1 | 0.2 | 42.9 |
| 31.0 | 77920.0 | 47700.2 | 107250.7 | 135320.2 | 218254.9 | 0.3 | 38.9 |
| 36.0 | 167815.7 | 139431.4 | 200049.4 | 45424.5 | 129368.9 | 0.5 | 23.8 |
| 40.0 | 196139.4 | 173226.0 | 222660.1 | 17100.8 | 80320.8 | 0.7 | 16.3 |
| 41.0 | 205617.7 | 180349.3 | 228684.9 | 7622.5 | 62730.4 | 0.7 | 13.8 |
| 42.0 | 206401.8 | 181018.7 | 228255.8 | 6838.4 | 58158.5 | 0.7 | 12.7 |
| 43.0 | 206196.8 | 187180.8 | 227552.0 | 7043.4 | 47540.9 | 0.7 | 11.7 |
| 46.0 | 204832.2 | 186722.9 | 224276.7 | 8408.0 | 46799.2 | 0.8 | 8.6 |

En esta mezcla, el mejor `v` central es **42**, mientras que en `iteration3` era **43**.

## 8. Sensibilidad

| label | best_v | robust_v | best_ev |
| --- | --- | --- | --- |
| AI sigma = 2.5 | 42 | 42 | 206385.8 |
| AI sigma = 3.5 | 42 | 42 | 206437.0 |
| AI sigma = 5.0 | 42 | 42 | 206409.4 |
| AI internal 35-cluster = 70% | 42 | 42 | 206339.3 |
| AI internal 35-cluster = 75% | 42 | 42 | 206215.7 |
| AI internal 35-cluster = 80% | 42 | 42 | 206434.6 |
| AI total weight = 25% | 46 | 46 | 201534.8 |
| AI total weight = 30% | 42 | 42 | 206195.3 |
| AI total weight = 35% | 42 | 42 | 211407.9 |
| Nash weight = 18% | 41 | 41 | 209776.8 |
| Nash weight = 23% | 42 | 42 | 206217.3 |
| Nash weight = 28% | 46 | 46 | 205116.4 |
| Just-above weight = 10% | 43 | 43 | 205890.0 |
| Just-above weight = 15% | 43 | 43 | 206302.9 |
| Just-above weight = 20% | 42 | 42 | 207432.9 |
| N = 20 | 42 | 42 | 206702.0 |
| N = 35 | 42 | 42 | 206663.6 |
| N = 50 | 42 | 42 | 206484.2 |
| N = 75 | 42 | 42 | 206214.9 |
| N = 100 | 42 | 42 | 206248.8 |

### Conteo de ganadores por escenario

| v | count |
| --- | --- |
| 41 | 1 |
| 42 | 15 |
| 43 | 2 |
| 46 | 2 |

### Superficie agregada

| v | mean_ev_across_scenarios | median_ev_across_scenarios | min_ev_across_scenarios | p25_ev_across_scenarios | p75_ev_across_scenarios | mean_regret_across_scenarios | max_regret_across_scenarios |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 26.0 | 57734.7 | 58055.4 | 53561.1 | 56454.5 | 58327.7 | 155836.9 | 162101.7 |
| 31.0 | 79425.5 | 78139.9 | 72841.4 | 77825.4 | 80104.4 | 134146.2 | 142078.9 |
| 36.0 | 167365.9 | 167893.3 | 159109.4 | 166076.8 | 168427.4 | 46205.7 | 52896.2 |
| 40.0 | 196123.3 | 196132.9 | 188656.8 | 195917.1 | 196348.0 | 17448.3 | 24357.1 |
| 41.0 | 205634.4 | 205694.5 | 199447.5 | 205379.1 | 205898.9 | 7937.2 | 14776.9 |
| 42.0 | 206379.0 | 206362.6 | 200822.8 | 206215.5 | 206529.1 | 7192.6 | 13984.2 |
| 43.0 | 206260.9 | 206249.5 | 201213.1 | 206142.0 | 206361.1 | 7310.7 | 14024.4 |
| 46.0 | 204806.5 | 204770.6 | 201534.8 | 204708.3 | 205002.7 | 8765.1 | 15695.1 |

Centro de gravedad de sensibilidad: **42**.

## 9. Comparación explícita contra iteration3

| metric | iteration3 | iteration4 |
| --- | --- | --- |
| recommended_v | 43 | 42 |
| top_clusters | 35 (6.9%), 34 (6.3%), 36 (5.7%), 41 (5.5%), 31 (5.0%), 33 (4.3%) | 35 (9.0%), 36 (7.9%), 34 (6.3%), 33 (5.4%), 41 (5.1%), 37 (4.5%) |
| mean_speed_field | 38.69 | 38.38 |
| mass_24_27_pct | 5.56 | 9.64 |
| mass_34_36_pct | 18.89 | 23.20 |
| mass_41_43_pct | 10.07 | 9.40 |

Interpretación:

- La mezcla nueva mete **más estructura en 25 y 35** por el componente IA, y más estructura en `26/31/36/41` por el just-above sobre números acabados en 0 o 5.
- Eso hace que el juego deje de estar dominado solamente por el cuello de botella `41–42` de `iteration3` y pase a tener más candidatas intermedias como `26`, `31` y especialmente `36`.
- La pregunta correcta ya no es solo ‘¿me pongo arriba del 41?’, sino también ‘¿cuánto valor tiene ponerme arriba del gran cluster en 35 sin pagar demasiado impuesto económico?’

## 10. Recomendación final

| criterion | v | r | s | gross_value | expected_pnl | p10_pnl | p90_pnl | mean_regret | max_regret | prob_best_response | broad_range_low | broad_range_high | core_range_low | core_range_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Max EV (central mixture) | 42 | 15 | 43 | 361658.7 | 206401.8 | 181018.7 | 228255.8 | 6838.4 | 58158.5 | 0.2 | 41 | 46 | 41 | 46 |
| Robust (min mean regret) | 42 | 15 | 43 | 361658.7 | 206401.8 | 181018.7 | 228255.8 | 6838.4 | 58158.5 | 0.2 | 41 | 46 | 41 | 46 |
| Conservative (best min EV across sensitivity) | 46 | 14 | 40 | 328595.6 | 204832.2 | 186722.9 | 224276.7 | 8408.0 | 46799.2 | 0.2 | 41 | 46 | 41 | 46 |

### Mi recomendación central: `42 / 15 / 43`

- **Por EV puro**: `42`.
- **Por robustez**: `42`.
- **Si querés cubrirte contra un field algo más alto**: `46`.
- **Banda defendible**: `41–46`.

### Qué parte de la decisión viene de cada componente

- **Componente IA (25/35)**: crea un gran colchón de masa en `34–36`, que vuelve muy atractiva la lógica de ponerse apenas por encima del cluster de 35 cuando el coste económico lo permite.
- **Componente just-above**: mete contra-clusters en `26`, `31`, `36`, `41`; eso hace que `36` y `41` no sean caprichos, sino escalones estratégicos reales.
- **Subproblema Research/Scale**: frena la tentación de correr demasiado arriba. Si te vas muy alto en `v`, el salto de multiplier ya no compensa el deterioro de `Research × Scale`.

## 11. Respuestas directas a las preguntas pedidas

1. **¿Qué distribución total de Speed inducen estos pesos?**
   - Una mezcla con clusters muy visibles en torno a `25–26`, `34–36` y un escalón adicional en `41`, más una cola alta moderada por el grupo speed-race.
2. **¿Dónde están los principales clusters?**
   - El corazón del field está en `34–36`; los escalones tácticos adicionales más relevantes están en `26`, `31` y `41`.
3. **¿Cómo influye el componente IA con medias 25 y 35?**
   - Le mete mucha masa al 35 y una masa secundaria al 25; eso hace que los valores justo por encima de esos clusters valgan más de lo que valían en iteration3.
4. **¿Qué papel juega el componente just-above?**
   - Es el componente que más explícitamente monetiza los ties. Sin él, la mezcla sería más ‘bonita’; con él, aparecen escalones estratégicos claros en `26/31/36/41`.
5. **¿Qué v explota mejor esos clusters?**
   - En el escenario central, `42`.
6. **¿Qué allocation r,s,v recomendaría?**
   - `15, 43, 42` en formato `Research, Scale, Speed`.
7. **¿Qué tan sensible es la recomendación a pequeños cambios en IA?**
   - El rango total de ganadores en la batería fue `41–46`, pero la banda central defendible quedó más estrecha: `41–46`.

## 12. Artefactos

- Notebook: `/Users/pablo/Desktop/prosperity/round_2/manual/manual_round2_analysis_iteration4.ipynb`
- Markdown: `/Users/pablo/Desktop/prosperity/round_2/manual/results/iteration4/manual_round2_summary_iteration4.md`
- Plots: `/Users/pablo/Desktop/prosperity/round_2/manual/results/iteration4/plots`
- CSVs: `/Users/pablo/Desktop/prosperity/round_2/manual/results/iteration4/csv`
