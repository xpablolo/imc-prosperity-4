# model_kiko — análisis y backtest simple

## Qué analicé

- Modelo nuevo: `/Users/pablo/Desktop/prosperity/round_2/models/model_kiko.py`
- Backtest local determinista con la misma lógica base usada en tus análisis anteriores.
- Datasets usados:
  - Round 1: días `-2, -1, 0`
  - Round 2: días `-1, 0, 1`

## Resumen ejecutivo

- **model_kiko gana a G5 en el backtest local en ambas rondas**.
- Round 1 total: `model_kiko = 310,785.0` vs `G5 = 304,026.0` → delta `+6,759.0`
- Round 2 total: `model_kiko = 309,940.0` vs `G5 = 305,412.0` → delta `+4,528.0`
- La mejora viene **casi toda por PEPPER**. En ASH rinde parecido o un poco peor.
- Arquitectónicamente, `model_kiko` es **más simple y más prior-driven** que tus modelos G/F; justamente por eso parece capturar muy bien el drift lineal de PEPPER, pero también me deja más alerta por posible fragilidad si cambia el régimen.

## Resultados de model_kiko

### Round 1

| product | total_pnl | max_drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position |
| --- | --- | --- | --- | --- | --- | --- |
| ASH_COATED_OSMIUM | 62841.000 | -1840.000 | 1956.000 | 0.629 | 5.773 | 27.515 |
| INTARIAN_PEPPER_ROOT | 247944.000 | -1520.000 | 1411.000 | 0.378 | 5.259 | 74.136 |
| TOTAL | 310785.000 | -1972.000 |  |  |  |  |

### Round 2

| product | total_pnl | max_drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position |
| --- | --- | --- | --- | --- | --- | --- |
| ASH_COATED_OSMIUM | 66456.000 | -1620.000 | 2024.000 | 0.666 | 5.692 | 28.271 |
| INTARIAN_PEPPER_ROOT | 243484.000 | -1680.000 | 1525.000 | 0.386 | 5.342 | 71.121 |
| TOTAL | 309940.000 | -1850.000 |  |  |  |  |

## Ranking rápido contra tus benchmarks

### Totales Round 2

| model | Round 2 |
| --- | --- |
| model_kiko | 309940.0 |
| model_G5 | 305412.0 |
| model_G2 | 303851.0 |
| model_F3 | 303502.0 |

### Totales Round 1

| model | Round 1 |
| --- | --- |
| model_kiko | 310785.0 |
| model_G5 | 304026.0 |
| model_G2 | 303884.0 |
| model_F3 | 303292.0 |

## model_kiko vs G5

| round_label | product | model_G5 | model_kiko | delta_kiko_minus_g5 |
| --- | --- | --- | --- | --- |
| Round 1 | ASH_COATED_OSMIUM | 63148.0 | 62841.0 | -307.0 |
| Round 1 | INTARIAN_PEPPER_ROOT | 240878.0 | 247944.0 | 7066.0 |
| Round 1 | TOTAL | 304026.0 | 310785.0 | 6759.0 |
| Round 2 | ASH_COATED_OSMIUM | 68006.0 | 66456.0 | -1550.0 |
| Round 2 | INTARIAN_PEPPER_ROOT | 237406.0 | 243484.0 | 6078.0 |
| Round 2 | TOTAL | 305412.0 | 309940.0 | 4528.0 |

## Diferencias estratégicas más relevantes

### 1) Estructura general

- **model_kiko** está organizado en dos engines simples (`OsmiumEngine` y `PepperEngine`) con operaciones compartidas de libro.
- **Tus modelos G/F** tienen mucha más lógica de estado, más capas de señales y un control de inventario bastante más sofisticado.

### 2) ASH_COATED_OSMIUM

- **model_kiko** usa una tesis bastante clásica: fair value por **EWMA del mid**, reservation price con skew por inventario y making/taking relativamente simples.
- **G5** usa una tesis más rica: anchor lento alrededor de 10k, señales L1/L2, microprice, repair logic y directional overlays.
- Traducción práctica: en ASH, `model_kiko` me parece **más simple y menos fino**. Y eso se ve en los números: no mejora contra G5.

### 3) INTARIAN_PEPPER_ROOT

- Acá está toda la gracia de `model_kiko`.
- Usa una fair value **muy explícita y muy fuerte** basada en:
  - `price_slope ≈ 0.00100001` por timestamp
  - una `base_price` que se va actualizando
  - un `alpha` que mezcla `forward_edge - residual - inventory_skew`
- O sea: está modelando PEPPER como un activo con **drift lineal casi conocido de antemano**.
- **Tus modelos G/F**, en cambio, son más adaptativos:
  - EMAs
  - slope estimado
  - continuation / pullback
  - flow reciente
  - targets y carry floors explícitos

### 4) Filosofía de inventario

- **G5** fuerza mucho más una política de carry / warehouse, con targets temporales altos y reglas de sostén de inventario.
- **model_kiko** parece menos barroco: deja que el `alpha` y el skew de inventario gobiernen más directamente el pricing.
- Resultado observado: en PEPPER, `model_kiko` consigue **más fills**, un maker share algo mayor y aun así carga un poco menos de inventario absoluto promedio que G5.

## Valoración del modelo

### Lo bueno

- **Rinde mejor que G5 localmente** en Round 1 y Round 2.
- La mejora viene por donde importa: **PEPPER**.
- Tiene una arquitectura más compacta y fácil de razonar.
- Parece estar muy bien calibrado para el régimen lineal de PEPPER que muestran ambas rondas.

### Lo que me preocupa

- **Está más hardcodeado al patrón de PEPPER.** Ese `price_slope` casi exacto me grita que el modelo está muy alineado con el drift observado.
- Eso puede ser fantástico si el régimen se mantiene… y una trampa si el slope cambia o si el flujo real en simulación oficial no acompaña igual.
- En ASH no me parece superior; de hecho, ahí G5 me sigue pareciendo conceptualmente más sólido.

### Mi veredicto

- **model_kiko es prometedor y merece atención seria.**
- Si solo miro el backtest local, hoy **lo valoraría por encima de G5**.
- Pero no lo trataría como victoria definitiva todavía, porque la ventaja parece apoyarse bastante en una hipótesis muy fuerte sobre el drift de PEPPER.

## Recomendación práctica

- **No descartaría G5 todavía**, pero sí pondría `model_kiko` en el top de candidatos.
- Si querés ser prudente: lo usaría como **benchmark fuerte / candidato principal**, pero revisando muy bien cuánto depende del `price_slope` fijo.
- Si querés el resumen en una línea: **me gusta más que G5 en PnL local, pero me da menos sensación de robustez estructural**.