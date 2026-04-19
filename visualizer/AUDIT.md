# Visualizer audit

## 1. Qué hacía el `visualizer/` original

El `visualizer/` que agregaste desde GitHub era un **SPA estático, local-first, sin build** hecho en HTML + CSS + vanilla JS.

### Arquitectura original

- `index.html` + `styles.css`: layout y estilos
- `app.js`: wiring principal
- `js/worker.js`: Web Worker para parsear archivos grandes sin bloquear la UI
- `js/parser.js`: parser del formato Prosperity esperado por upstream
- `js/store.js`: store chico pub/sub
- `js/panels/*`: paneles de KPIs, PnL, price chart, positions, order book, fills y logs
- `js/chart.js`: chart canvas propio, sin librerías externas

### Modelo mental original

El visualizer original estaba pensado para **dropear logs de Prosperity** y analizar eso directamente en el browser.

Esperaba principalmente archivos con esta forma:

```json
{
  "submissionId": "...",
  "activitiesLog": "day;timestamp;product;...",
  "logs": [...],
  "tradeHistory": [...]
}
```

### Fortalezas originales

- cero dependencias runtime
- muy buena base visual y cuantitativa
- comparación entre estrategias ya resuelta
- playback + scrubber + charts sincronizados
- order book, fills y tabs de logs ya implementados

### Limitaciones originales respecto de este repo

1. **No descubría runs del proyecto**
   - solo drag & drop manual
2. **No entendía tus backtests CSV locales**
   - especialmente los outputs de `round_0/results/*` y `round_1/results/*`
3. **No parseaba los replay `.log` textuales**
   - los que empiezan con `Sandbox logs:`
4. **No toleraba bien algunos JSON reales del repo**
   - por ejemplo logs con `activitiesLog` pero sin `logs` / `tradeHistory`
5. **No tenía servidor local integrado**
6. **No mostraba drawdown como serie dedicada**
7. **No tenía timeline filtrable de eventos/logs**

---

## 2. Formatos reales detectados en este repo

### A. Logs IMC / oficiales

Archivos detectados como:

- `round_1/official_result.log`
- `round_1/model_C_data/131140.log`

Estructura principal:

- `submissionId`
- `activitiesLog`
- `logs`
- `tradeHistory`

### B. JSON IMC resumidos

Ejemplo:

- `round_1/model_C_data/131140.json`

Tienen:

- `activitiesLog`
- a veces `graphLog`
- a veces `positions`
- no siempre `logs` ni `tradeHistory`

### C. Replay logs textuales

Ejemplos:

- `round_0/results/logs/*.log`
- `round_1/results/logs/*.log`

Formato:

- `Sandbox logs:`
- `Activities log:`
- `Trade History:`

No era JSON válido completo; hubo que soportarlo aparte.

### D. Backtests CSV locales `round_0`

Headers detectados:

- resultados:
  - `day,timestamp,global_ts,equity_total,pnl_total,pnl_TOMATOES,pnl_EMERALDS`
- fills:
  - `day,timestamp,product,side,price,quantity,source`

### E. Backtests CSV locales `round_1`

Headers detectados:

- resultados estándar por producto:
  - `day,timestamp,global_ts,mid_price,cash,position,equity,pnl`
- fills:
  - `day,timestamp,global_ts,product,side,price,quantity,source`
- variante simplificada:
  - `day,timestamp,pnl,position`

### F. Dataset de mercado base

Usado para reconstruir libro / precios / trades:

- `data/round_*/prices_round_*_day_*.csv`
- `data/round_*/trades_round_*_day_*.csv`

### G. Monte Carlo

Detectados:

- `round_*/results/montecarlo/*/*/dashboard.json`
- `session_summary.csv`

Hoy están relevados pero **no tienen vista dedicada** en esta UI.

---

## 3. Qué cambié

## Backend liviano local

Agregué un servidor Python sin dependencias extra:

- `/Users/pablo/Desktop/prosperity/visualizer/server.py`

Expone:

- `GET /api/runs` → descubre runs del workspace
- `GET /api/run/:id/source` → devuelve texto crudo de logs IMC/replay
- `GET /api/run/:id` → devuelve backtests CSV ya normalizados al modelo del dashboard

## Descubrimiento automático de runs

Agregué un scanner de workspace:

- `/Users/pablo/Desktop/prosperity/visualizer/backend/discovery.py`

Detecta:

- logs IMC
- replay logs textuales
- grupos de backtests CSV por estrategia/run

## Normalización de backtests CSV

Agregué:

- `/Users/pablo/Desktop/prosperity/visualizer/backend/backtest.py`

Qué hace:

- agrupa resultados + fills
- infiere producto cuando hace falta
- toma precios y trades desde `data/round_*`
- reconstruye series compatibles con la UI existente
- entrega un objeto homogéneo con:
  - timestamps
  - series por producto
  - total PnL
  - positions
  - fills
  - trades
  - order book / liquidity cuando los datos base existen

## Parser más robusto en frontend

Extendí `js/parser.js` y `js/worker.js` para que ahora soporten:

- logs IMC JSON clásicos
- replay logs textuales
- JSON con `activitiesLog` pero sin `logs` / `tradeHistory`

## Enriquecimiento cuantitativo

Agregué:

- `/Users/pablo/Desktop/prosperity/visualizer/js/strategyPrep.js`

Deriva:

- summary consistente
- drawdown total y por producto
- timeline unificada de:
  - fills
  - market trades
  - sandbox logs
  - algorithm logs
  - warnings
  - órdenes estructuradas si existen en `lambdaLog`

## UI / UX

Cambios visibles:

- rail con **workspace runs detectados automáticamente**
- búsqueda y recarga de runs locales
- carga fácil de backtests + logs reales
- nuevo panel de **drawdown**
- panel de logs convertido en **timeline filtrable** + tabs crudos
- fills con `source`
- mejor foco en uso cuantitativo real del repo

---

## 4. Decisiones de diseño

### Por qué Python stdlib y no Node/React

Porque el problema real NO era “hacer una app más moderna” sino **integrar formatos reales del repo sin meter complejidad al pedo**.

Tradeoff elegido:

- **sí**: servidor local chico, mantenible, sin deps pesadas
- **no**: refactor masivo, bundler, framework nuevo, build step

### Por qué mantuve la SPA vanilla original

Porque ya resolvía bien:

- store
- charts canvas
- playback
- comparación
- paneles sincronizados

Rehacer eso en React por capricho hubiera sido una pérdida de tiempo. Acá había que ser arquitecto, no influencer de frameworks.

### Por qué normalizar los CSV al mismo modelo interno

Porque así la UI no necesita caminos especiales por cada formato.

Una vez que todos los runs llegan al mismo shape lógico, los paneles existentes se reutilizan casi todos.

---

## 5. Limitaciones que quedan

1. **Monte Carlo**
   - se detecta en disco pero todavía no tiene una vista dedicada dentro del dashboard principal
2. **Órdenes detalladas**
   - solo aparecen si el `lambdaLog` tiene payload estructurado decodificable
3. **Runs con nombres repetidos**
   - puede haber varios `model_v2` en distintas carpetas de evaluación; la UI muestra el path para diferenciarlos, pero no hay grouping avanzado aún
4. **Resultados no estándar de research/manual**
   - CSV analíticos de `round_2/manual` o research tables no se muestran como estrategia porque no representan una simulación tick-by-tick
5. **Persistencia**
   - IndexedDB guarda runs cargados; si cambiás archivos en disco y querés reindexar, conviene refrescar el workspace y recargar el run

---

## 6. Resultado final

El `visualizer/` dejó de ser un viewer genérico para logs upstream y pasó a ser un **dashboard local funcional para tus estrategias reales**:

- útil con tus archivos reales
- fácil de arrancar
- comparativo
- robusto ante formatos incompletos
- sin dependencias pesadas
- sin build

Y eso era lo importante. No “hacer más cosas”. Hacer LAS COSAS CORRECTAS.
