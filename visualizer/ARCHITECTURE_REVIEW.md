# Visualizer — Architecture Review

> Generado el 2026-04-19. Describe el estado **antes** de las mejoras de esta sesión.
> Ver `CHANGELOG_LOCAL.md` para lo que cambió.

---

## 1. Mapa de módulos y responsabilidades

```
visualizer/
├── server.py                  ← Servidor HTTP (stdlib), router /api/*, MIME
├── backend/
│   ├── discovery.py           ← RunRegistry: scanner DFS, clasificación de runs, caché
│   ├── backtest.py            ← Parsers CSV + normalización completa → strategy dict
│   └── limits.py              ← Mapa de límites de posición por producto
├── js/
│   ├── app.js                 ← Entry point: wiring de paneles, hidratación
│   ├── store.js               ← Pub/sub state store global (32 acciones)
│   ├── parser.js              ← Parser: IMC JSON, replay log, CSV actividades
│   ├── strategyPrep.js        ← Enriquecimiento: drawdown, eventos, normalization
│   ├── worker.js              ← Web Worker handler (parsing no bloqueante)
│   ├── parserClient.js        ← Wrapper Promise del Web Worker
│   ├── api.js                 ← Cliente HTTP /api/*
│   ├── persistence.js         ← IndexedDB wrapper (guardar/cargar strategies)
│   ├── chart.js               ← Canvas chart custom (zoom, hover, seek)
│   ├── downsample.js          ← Algoritmo LTTB para downsampling de series
│   ├── exporters.js           ← Export CSV / PNG
│   ├── format.js              ← Helpers numéricos y de formato
│   ├── colors.js              ← Paleta de colores por strategy
│   ├── positionLimits.js      ← Mapa límites por producto (DUPLICADO con limits.py)
│   ├── uid.js                 ← Generador de IDs
│   ├── demoLog.js             ← Log de demostración embebido
│   └── panels/
│       ├── rail.js            ← Sidebar: discovery, upload, manage strategies
│       ├── topBar.js          ← Playback, scrubber, product selector, tema
│       ├── pnlChart.js        ← Chart PnL performance acumulado
│       ├── priceChart.js      ← Chart precios, bid/ask, micro/wallMid, fills overlay
│       ├── positionChart.js   ← Chart posición vs tiempo
│       ├── drawdownChart.js   ← Chart drawdown total y por producto
│       ├── kpi.js             ← Grid de KPIs (Sharpe, max DD, win rate…)
│       ├── summary.js         ← Tabla comparativa de runs
│       ├── orderBook.js       ← Snapshot del order book en tick actual
│       ├── ownFills.js        ← Tabla de fills propios con filtros
│       ├── logs.js            ← Timeline de eventos + tabs
│       ├── pressure.js        ← Imbalance bid/ask
│       └── about.js           ← Modal informativo
├── index.html                 ← Layout principal, containers de paneles
├── styles.css                 ← Variables CSS, dark/light mode, componentes
└── README.md
```

---

## 2. Flujo de datos

```
[Archivo drag&drop]        [Workspace discovery]
       │                          │
       ▼                          ▼
  Web Worker                 GET /api/run/{id}
  parser.js                  server.py → discovery.py → backtest.py
  buildStrategy()                         (normalizado en servidor)
       │                          │
       └──────────┬───────────────┘
                  ▼
          strategyPrep.js
          prepareStrategy()
          (drawdown, events, summary)
                  │
                  ▼
              store.js
              addStrategy()
                  │
          [pub/sub notifica]
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
   Paneles JS           IndexedDB
   re-render            (opcional)
```

---

## 3. Problemas encontrados

### P1 — Bugs reales

| # | Archivo | Línea | Descripción |
|---|---------|-------|-------------|
| B1 | `backtest.py:185` | `parse_fill_file` | Sin `try/except` externo — si el archivo no abre, la excepción sube sin warning. Los demás parsers (`parse_price_file`, `parse_trade_file`) sí tienen bloque try/except propio. |
| B2 | `backtest.py:256-263` | `parse_result_file` | Abre el archivo **dos veces**: una para leer el header (readline) y otra para el DictReader. Ineficiente y redundante. |
| B3 | `backtest.py:136,172` | `parse_price_file`, `parse_trade_file` | Usa `path.relative_to(path.parents[2])` en mensajes de warning. Si el path tiene menos de 3 componentes, lanza `IndexError`. Debería usar `path.name` o manejar el error. |

### P2 — Duplicación de datos

| # | Descripción |
|---|-------------|
| D1 | **Límites de posición duplicados**: `backend/limits.py` (Python) y `js/positionLimits.js` (JS) tienen el mismo mapa de productos. Si se añade un producto nuevo en una temporada futura, hay que actualizar **ambos archivos**. El backend ya incluye los límites en el strategy JSON (`positionLimits`), así que la versión JS sólo es fallback para drag&drop sin servidor. |

### P3 — Monolito en backend

| # | Descripción |
|---|-------------|
| M1 | `load_backtest_strategy` (líneas 458–660, **202 líneas**) hace demasiado: parseo de fills, inferencia de productos, construcción del índice de timestamps, relleno de series de precios, aplicación de resultados, reconstrucción de posiciones desde fills, ensamblado de trades, construcción del dict final. Debería ser una función coordinadora que llame a helpers con responsabilidades claras. |

### P4 — Acoplamiento

| # | Descripción |
|---|-------------|
| C1 | `discovery.py` importa **6 constantes de headers** desde `backtest.py`. Si se renombra alguna constante en backtest, discovery falla silenciosamente (o en runtime). |
| C2 | `strategyPrep.js::prepareStrategy` combina: normalización de arrays, forward-fill, drawdown, construcción de eventos, cálculo de summary. Cuatro responsabilidades en una función. Funciona, pero dificulta testear partes individuales. |

### P5 — Robustez

| # | Descripción |
|---|-------------|
| R1 | El Web Worker reporta progreso **fake** (5%, 25%, 60%, 95%) con valores hardcodeados, no relacionados con el trabajo real. |
| R2 | `parse_result_file` no tiene try/except externo (igual que `parse_fill_file`). Si el archivo falla a mitad de la lectura, lanza excepción no controlada. |
| R3 | `discovery.py::_classify_logish` lee sólo los primeros 4096 bytes para detectar el formato. Si un JSON IMC válido tiene un preámbulo muy largo antes de `"activitiesLog"`, no se detectará. |

### P6 — Extensibilidad

| # | Descripción |
|---|-------------|
| E1 | **Añadir un panel nuevo**: requiere crear `js/panels/nuevo.js`, agregar container en `index.html`, montar en `app.js`, suscribir a store. No hay friction innecesaria pero tampoco hay patrón documentado. |
| E2 | **Soportar un nuevo formato CSV**: requiere modificar `backtest.py` (constante de header + lógica de parsing) y `discovery.py` (detección del header). El acoplamiento C1 lo hace frágil. |
| E3 | **Añadir nuevas métricas analíticas** (drawdown por producto, attribution, inventory PnL…): `strategyPrep.js::buildEvents` y `computeSummary` son los puntos naturales pero están mezclados con la normalización básica. |

---

## 4. Módulos núcleo (no tocar sin motivo)

| Módulo | Por qué es crítico |
|--------|--------------------|
| `backtest.py` | Normaliza todos los formatos CSV — es el parser más complejo |
| `parser.js` | Parser de logs — soporta 2 formatos con muchos edge cases |
| `strategyPrep.js` | Garante de shape consistente — todos los paneles asumen su output |
| `store.js` | Estado global — cualquier cambio aquí afecta todos los paneles |
| `chart.js` | Canvas chart custom — no depende de ninguna librería |

---

## 5. Módulos más acoplados

| Módulo | Acoplado con | Tipo |
|--------|-------------|------|
| `discovery.py` | `backtest.py` | 6 constantes importadas |
| `strategyPrep.js` | `parser.js` | Asume shape del output de buildStrategy |
| `panels/*` | `store.js` | Todos subscriben al mismo estado global |
| `positionLimits.js` | `backend/limits.py` | Datos duplicados, mantenimiento manual |

---

## 6. Propuestas de mejora priorizadas

### Alta prioridad (bugs / robustez)
1. **[B1-B3]** Corregir los 3 bugs de manejo de errores en `backtest.py`
2. **[M1]** Extraer helpers de `load_backtest_strategy` para mejorar legibilidad y mantenibilidad

### Media prioridad (arquitectura)
3. **[D1]** Añadir endpoint `/api/limits` en server.py para que el frontend pueda obtener los límites sin duplicación
4. **[C1]** Mover las constantes de header a un módulo separado `backend/formats.py` para evitar el acoplamiento discovery↔backtest
5. Añadir `smoke_test.py` para verificación rápida post-cambios

### Baja prioridad (mejoras)
6. **[C2]** Dividir `strategyPrep.js::prepareStrategy` en funciones más pequeñas
7. **[R1]** Progreso real en el Web Worker (aunque es difícil sin instrumentación interna)
8. Documentar el patrón de paneles para facilitar nuevas adiciones
