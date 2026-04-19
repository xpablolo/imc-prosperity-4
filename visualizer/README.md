# Prosperity Dashboard

Dashboard local para visualizar runs reales de este repo de Prosperity sin build step y sin subir datos a ningún lado.

## Arranque

Desde la raíz del proyecto:

```bash
python3 visualizer/server.py
```

Abrí:

- [http://127.0.0.1:8787](http://127.0.0.1:8787)

## Qué soporta

- logs oficiales IMC en JSON (`activitiesLog`, `logs`, `tradeHistory`)
- `.log` textuales de replay con secciones `Sandbox logs / Activities log / Trade History`
- backtests CSV locales de `round_0` y `round_1`
- carga manual por drag & drop de `.log` / `.json`
- descubrimiento automático de runs del workspace vía API local

## Qué muestra

- PnL total y por producto
- curva de PnL acumulado
- drawdown
- posiciones / inventario
- fills propios
- market trades
- libro / liquidez / presión
- timeline filtrable de eventos, logs y warnings
- comparación simple entre runs

## Archivos clave

- `/Users/pablo/Desktop/prosperity/visualizer/server.py` — servidor local + API
- `/Users/pablo/Desktop/prosperity/visualizer/backend/discovery.py` — descubrimiento de runs
- `/Users/pablo/Desktop/prosperity/visualizer/backend/backtest.py` — normalización de backtests CSV
- `/Users/pablo/Desktop/prosperity/visualizer/js/parser.js` — parser de logs IMC y replay
- `/Users/pablo/Desktop/prosperity/visualizer/js/strategyPrep.js` — métricas derivadas, drawdown, timeline

## Notas

- No hace falta instalar dependencias extra.
- Si abrís `index.html` con `file://`, el dashboard no va a funcionar bien; usá el server Python.
- Los dashboards Monte Carlo (`dashboard.json`) todavía no tienen vista dedicada en esta UI.

## Más contexto

- Auditoría y arquitectura: `/Users/pablo/Desktop/prosperity/visualizer/AUDIT.md`
- El visualizer original upstream era un SPA estático local-first inspirado en OpenProsperity / jmerle. Esta versión lo adapta a los formatos reales de este repo.
