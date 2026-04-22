# Prosperity Visualizer

Dashboard local-first para inspeccionar, comparar y diagnosticar runs de Prosperity sin build step y sin subir datos a ningún lado.

## Objetivo

El visualizer **no** es una estrategia ni un backtester. Es una herramienta para:

- descubrir runs del workspace
- cargar logs oficiales IMC JSON, replay logs textuales y backtests CSV locales
- normalizar fuentes heterogéneas a un modelo común
- entender **PnL, drawdown, inventario, execution quality y microestructura**
- comparar estrategias con un criterio más cuantitativo que una simple tabla de PnL

## Arquitectura

Se preserva el enfoque deliberadamente liviano:

- frontend: **HTML + CSS + vanilla JS**
- backend: **Python stdlib**
- sin build step
- sin frameworks pesados
- local-first
- sin dependencias runtime innecesarias

## Arranque

Desde la raíz del proyecto:

```bash
python3 visualizer/server.py
```

Abrí:

- [http://127.0.0.1:8000](http://127.0.0.1:8000)

Opcionalmente:

```bash
python3 visualizer/server.py --port 8787
```

## Qué soporta

- logs oficiales IMC en JSON (`activitiesLog`, `logs`, `tradeHistory`)
- replay `.log` textuales con secciones `Sandbox logs / Activities log / Trade History`
- backtests CSV locales de `round_0` y `round_1`
- carga manual por drag & drop de `.log` / `.json`
- descubrimiento automático de runs del workspace vía API local

## Qué muestra hoy

### Core market / run viewer

- PnL total y por producto
- curva de PnL acumulado
- drawdown
- posiciones / inventario
- market trades y fills propios
- timeline filtrable de eventos, warnings y logs
- comparación simple entre runs

### Mejoras nuevas de microestructura y evaluación

- **Order Book Explorer**
  - ladder más clara por niveles
  - bid / ask / spread / mid / microprice / wall-mid / imbalance
  - snapshot actual + evolución reciente del book
  - depth ribbon estilo mini-heatmap para profundidad visible reciente
  - modo explicativo con interpretación textual del estado del libro
- **What happened here?**
  - resumen automático del tick/ventana actual en lenguaje claro
  - combina estado del libro, inventario, fills recientes y PnL local
- **Order Lifecycle**
  - reconstrucción de episodios de órdenes propias
  - tipo inferido: pasiva / agresiva / marketable / improving
  - estado: filled / multi-fill / partial si la cobertura lo permite
  - lifetime, VWAP, queue ahead estimada, relación con el best price y markout
- **Execution Quality**
  - passive fill %
  - aggressive fill %
  - average queue ahead estimate
  - implementation shortfall
  - slippage
  - realized spread aproximado
  - markout 1/5/10 ticks
  - adverse selection score
  - breakdown global / por producto / por lado
- **Strategy Diagnostics**
  - Sharpe-like
  - expectancy
  - hit rate
  - trade PnL skewness
  - time under water / recovery time
  - max / average inventory
  - concentración por producto
  - best / worst episodes
  - heurísticos de consistency / fragility / stability
  - performance by regime:
    - spread wide / narrow
    - low / high volatility
    - balanced / imbalanced book
    - trend / mean reversion local heurística
- **Advanced Compare**
  - comparación side-by-side entre run de referencia y otra estrategia cargada
  - window / episode compare por rango de ticks
  - diff de métricas clave
  - lista automática de “why different?”
  - tabla por producto para explicar de dónde sale la diferencia

## Exacto vs inferido

Esto es IMPORTANTE.

El visualizer distingue entre información **observada** y **reconstruida**:

### Exacto / observado

- PnL y series del run cuando vienen del resultado normalizado
- fills propios observados
- market trades observados
- libro visible en cada tick cuando existe `activitiesLog` / data base
- realized PnL FIFO sobre fills
- drawdown, inventario, hit rate, expectancy sobre fills cerrados

### Aproximado / inferido

- lifecycle de órdenes cuando el log no trae submissions explícitas
- queue ahead estimate a partir del libro visible
- passive vs aggressive según precio de fill contra el book del tick
- implementation shortfall / spread capture / adverse selection usando referencias de mid / micro / fair visible
- PnL decomposition por inventario / spread capture / execution cost
- fragility / consistency / stability scores
- regime detection (trend / mean reversion / wide / narrow / imbalance)

### Limitaciones actuales

- Si el log no trae `lambdaLog` estructurado con órdenes, **fill ratio** y **cancel ratio** exactos no existen; se reportan como no disponibles o se usan proxies explícitas.
- `Order Lifecycle` en la mayoría de los runs actuales es **inferred-from-fills**.
- `dashboard.json` de Monte Carlo sigue sin tener una vista dedicada en esta UI.

## Archivos clave

- `/Users/pablo/Desktop/prosperity/visualizer/server.py` — servidor local + API
- `/Users/pablo/Desktop/prosperity/visualizer/backend/discovery.py` — descubrimiento de runs
- `/Users/pablo/Desktop/prosperity/visualizer/backend/backtest.py` — normalización de backtests CSV
- `/Users/pablo/Desktop/prosperity/visualizer/js/parser.js` — parser de logs IMC y replay
- `/Users/pablo/Desktop/prosperity/visualizer/js/strategyPrep.js` — normalización final + timeline + enrich pipeline
- `/Users/pablo/Desktop/prosperity/visualizer/js/analysis.js` — métricas derivadas, execution quality, diagnostics, lifecycle y comparación
- `/Users/pablo/Desktop/prosperity/visualizer/js/panels/orderBook.js` — Order Book Explorer
- `/Users/pablo/Desktop/prosperity/visualizer/js/panels/orderLifecycle.js` — panel de lifecycle
- `/Users/pablo/Desktop/prosperity/visualizer/js/panels/executionPanel.js` — execution quality
- `/Users/pablo/Desktop/prosperity/visualizer/js/panels/comparePanel.js` — comparación avanzada
- `/Users/pablo/Desktop/prosperity/visualizer/js/panels/diagnostics.js` — diagnostics + PnL decomposition
- `/Users/pablo/Desktop/prosperity/visualizer/js/panels/whatHappened.js` — explicación contextual del tick actual

## Smoke tests

Smoke mínimo:

```bash
python3 visualizer/smoke_test.py
```

El smoke actual verifica:

- discovery del workspace
- parsers base
- endpoints `/api/*`
- pipeline frontend `parser -> strategyPrep -> analytics`
- presencia de los paneles nuevos en `index.html`

## Notas

- No hace falta instalar dependencias extra.
- Si abrís `index.html` con `file://`, el dashboard no va a funcionar bien; usá el server Python.
- Todo sigue pensado para uso local de escritorio y respuesta rápida, no para una SPA enterprise barroca.

## Más contexto

- Auditoría y arquitectura histórica: `/Users/pablo/Desktop/prosperity/visualizer/AUDIT.md`
- Review de arquitectura base: `/Users/pablo/Desktop/prosperity/visualizer/ARCHITECTURE_REVIEW.md`
