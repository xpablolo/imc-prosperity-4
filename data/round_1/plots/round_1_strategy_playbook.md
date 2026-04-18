# Round 1 strategy playbook (mid-only)

## Metrics used
- **trend R²**: cuánto de la trayectoria del mid se explica con una recta. Cerca de 1 = deriva limpia; cerca de 0 = más estacionario/choppy.
- **smooth eff50**: eficiencia direccional del mid suavizado a 50 ticks. Cerca de 0 = ida y vuelta; cerca de 1 = movimiento limpio y tendencial.
- **drift / residual-noise**: drift por 10k timestamps dividido por el ruido alrededor de la tendencia. Alto = conviene respetar la deriva.
- **residual half-life**: velocidad con la que el precio vuelve hacia su tendencia local. Bajo = pullbacks cortos y operables.

## Asset playbooks
### Ash Coated Osmium
- Strategy: **Stationary mean reversion / market making**
- Why: trend R² **0.059**, smooth eff50 **0.001**, drift/noise **0.003**, residual half-life **2.69**.
- Playbook: Conviene anclar a un fair value casi estático, capturar spread y desvanecer excursiones en vez de perseguir momentum.

### Intarian Pepper Root
- Strategy: **Trend + pullback mean reversion**
- Why: trend R² **1.000**, smooth eff50 **0.941**, drift/noise **4.543**, residual half-life **0.70**.
- Playbook: Usá una fair value móvil, sesgo de inventario a favor de la tendencia y entradas en pullbacks en vez de perseguir cada tick.
