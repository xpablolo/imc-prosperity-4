# Resumen del repo `TimoDiehm/imc-prosperity-3` — IMC Prosperity 3

# Filosofía general del equipo

## Idea central
Su enfoque fue siempre:

> **No usar una técnica porque “queda cuant”, sino porque encaja con cómo parece generarse el mercado.**

## Herramientas que usaron
### 1. Dashboard propio
Tenían un dashboard muy orientado a microestructura:
- order book por niveles
- filtros por traders
- PnL y posición por producto
- logs sincronizados
- normalización por indicadores como el **Wall Mid**

### 2. Backtesting híbrido
Usaban dos mundos:
- **backtester local** para estrategias de lógica general
- **website oficial** cuando el edge dependía de interacciones con bots o fills más realistas

Su regla práctica:
- si el edge era de **take/make simple**, usar backtester
- si el edge dependía de **bots ocultos o fills raros**, validar en la web

### 3. Wall Mid
Uno de sus conceptos más importantes.  
El **Wall Mid** es su estimación del “true price”, construida a partir de las paredes de liquidez del order book. Lo preferían frente al mid simple porque era mucho más estable y menos contaminado por quotes pequeños o undercuts.

---

# Ronda 1 — Market Making

## 1. Rainforest Resin
### Qué detectaron
- el true price era básicamente **fijo en 10,000**
- no había que predecir nada
- el problema era puramente de **capturar edge**
- la simulación era secuencial, así que la velocidad real no importaba

### Approach
- tomar cualquier orden favorable vs 10,000
- luego quotear mejorando ligeramente el libro
- si el inventario se desviaba, neutralizar a 10,000

### Lección
Esto era casi una clase de market making básico:
- fair value claro
- edge = distancia al valor justo
- inventario solo como restricción operativa, no como fuente de alpha

### Relevancia para vuestro equipo
Muy útil como recordatorio de que en Prosperity muchas veces:
- el problema **no es predecir**
- el problema es **extraer edge microestructural de forma limpia**

---

## 2. Kelp
### Qué detectaron
- muy parecido a Resin
- el precio se movía algo, pero de forma poco predecible
- el mejor estimador del fair value era el actual **Wall Mid**

### Approach
- misma lógica que Resin
- tomar precios claramente favorables
- quotear alrededor del Wall Mid
- cerrar inventario cuando fuera necesario

### Lección
No complicar lo que es esencialmente un producto de market making con drift pequeño.  
Si no hay evidencia sólida de predictibilidad, lo correcto es tratarlo casi como un producto estacionario alrededor de un fair value local.

---

## 3. Squid Ink
### Qué detectaron
Aquí vino la primera gran lectura de bots:
- un trader anónimo (luego supieron que era **Olivia**) compraba en el **mínimo diario** y vendía en el **máximo diario**
- operaba en bloques identificables
- eso generaba una señal mucho más fuerte que la simple mean reversion del producto

### Approach
- detectar trades en extremos diarios
- inferir la posición de Olivia
- posicionarse en consecuencia
- invalidar señales si aparecían nuevos extremos

### Lección
A veces el mejor alpha no está en la serie de precios, sino en el **comportamiento sistemático de otro bot**.

### Relevancia para vuestro equipo
Muy importante:
- si un producto parece “mean reverting”, no asumir que esa es la fuente real del edge
- primero mirar si hay **agentes con comportamiento repetitivo**
- filtrar por tamaño, contexto y nivel del día puede revelar mucho

---

# Ronda 2 — ETF Statistical Arbitrage

## Picnic Baskets
Había constituyentes:
- Croissants
- Jams
- Djembes

Y dos baskets:
- `PICNIC_BASKET1 = 6C + 3J + 1D`
- `PICNIC_BASKET2 = 4C + 2J`

### Qué detectaron
Vieron dos caminos:
1. spread entre baskets
2. basket vs suma sintética de constituyentes

Concluyeron que lo mejor era **basket vs sintético**, porque la generación más natural parecía ser:
- constituyentes moviéndose primero
- basket = sintético + ruido mean reverting

### Approach
- umbrales fijos sobre el spread `basket - synthetic`
- entrar largo si el spread cae mucho
- entrar corto si sube mucho
- salir al cruzar cero
- evitar complejidad innecesaria como z-scores o señales muy paramétricas
- además, ajustaban el sesgo usando la señal de Olivia en Croissants

### Detalle importante
Detectaron que las baskets tenían una pequeña **premium persistente**, así que restaban un componente de premium estimado en vivo.

### Hedge
No estaban seguros del hedge óptimo, así que en la ronda final hicieron un **half-hedge** como compromiso entre EV y reducción de varianza.

### Lección
Esta parte es muy buena:
- primero entender **cómo crees que se genera el spread**
- luego modelarlo con la mínima complejidad posible
- no usar z-score si no hay evidencia de heterocedasticidad útil
- no hedgear por reflejo; hedgear solo si mejora el trade-off real

### Relevancia para vuestro equipo
Muy alineado con lo que conviene en Prosperity:
- preferir **thresholds robustos** a modelos más “bonitos”
- combinar spread principal con señales cross-product solo si tienen sentido estructural
- mirar estabilidad del landscape, no solo el mejor punto de grid search

---

# Ronda 3 — Options Scalping

## Volcanic Rock + Vouchers
Introdujeron calls sobre `VOLCANIC_ROCK` con varios strikes.

### Qué detectaron
Separaron dos fuentes de alpha:

## A. IV Scalping
- construyeron una **volatility smile**
- ajustaron una parábola IV vs moneyness
- calcularon una IV “fair”
- llevaron eso a precio con Black-Scholes
- compararon precio de mercado vs precio teórico

Eso les permitió detectar desviaciones de precio de corto plazo.

### Approach
- hacer scalping sobre mispricings relativos entre opciones
- empezar por el strike 10,000 y luego expandir a otros strikes según convenía
- priorizar esta pata porque era la más sólida

---

## B. Mean Reversion en el subyacente
También observaron:
- autocorrelación negativa en returns de `VOLCANIC_ROCK`
- parecido con Squid Ink

Pero fueron prudentes:
- solo pocos días de datos
- presencia de saltos
- señal menos confiable

### Approach
- EMA rápida
- thresholds fijos
- sin escalar por vol rolling
- posición moderada

---

## Strategy final
Hicieron una **estrategia híbrida**:
- principal: **IV scalping**
- secundaria: **mean reversion moderada** en el underlying y en la call más ITM

No era delta hedging clásico.  
Más bien era una forma de no quedarse demasiado expuestos a un escenario donde otros equipos sí explotaran mean reversion fuerte.

### Lección
Muy importante:
- separar el alpha **teórico y robusto** del alpha **empírico pero dudoso**
- el componente de mayor convicción debe mandar
- un segundo componente puede usarse como hedge de “regret” relativo

### Relevancia para vuestro equipo
Esto es probablemente de lo más útil del repo:
- no mezclar todo bajo una sola narrativa
- distinguir entre:
  - mispricing relativo entre opciones
  - direccionalidad del subyacente
  - hedge operativo
- si la evidencia de mean reversion es mediocre, no apalancarla como si fuera una verdad

---

# Ronda 4 — Location Arbitrage

## Magnificent Macarons
Producto con:
- mercado local
- mercado externo
- costes de import/export
- límite de conversión por timestep

### Qué detectaron
Había el arbitraje obvio:
- local bid > external ask ajustado por costes
- local ask < external bid ajustado por costes

Pero lo realmente valioso fue otra cosa:
- descubrieron un **taker bot oculto**
- ese bot llenaba órdenes a precios que parecían buenos respecto a un fair value escondido
- podían vender localmente a un precio mejor que el mejor bid visible con probabilidad ~60%

### Approach final
- quotear en el precio exacto que maximizaba la probabilidad de fill manteniendo edge
- aprovechar el límite de conversión
- centrarse en esa interacción con el bot

### Intento de ML
Exploraron una regresión logística usando sunlight y otras variables.
Obtenía backtests decentes, pero no la usaron finalmente porque:
- dudaban de la generalización
- complicaba mucho la implementación
- chocaba con la lógica de conversión/arbitraje

### Lección
Esta ronda deja una enseñanza brutal:
- muchas veces el gran edge no está en el modelo “bonito”, sino en una **ineficiencia concreta de microestructura**
- una señal ML puede ser real, pero si:
  - cuesta mucho operarla
  - interactúa mal con inventario/conversión
  - no confías en generalización
  entonces puede ser peor que una lógica simple y segura

### Relevancia para vuestro equipo
Muy útil para vuestro enfoque:
- antes de modelar features exóticas, mirar si hay **fill mechanics explotables**
- el EV real depende de implementación + inventario + límites, no solo del score del modelo

---

# Ronda 5 — Trader IDs

### Qué cambió
Se hicieron visibles los trader IDs históricos.

### Qué hicieron
- dejaron de inferir indirectamente a Olivia
- la identificaron directamente
- redujeron falsos positivos
- reoptimizaron parámetros
- jugaron más conservador por su ventaja en leaderboard

### Lección
Cuando la información mejora, no hace falta reinventar la estrategia:  
basta con **hacer más limpia y menos ruidosa** la misma señal.

---

# Manual Challenge — resumen rápido

El equipo fue bastante conservador en manual:
- priorizaron no cometer errores enormes
- aceptaron sacrificar upside por robustez

## Qué sacaron
- **Round 1**: arbitraje puro, solución por fuerza bruta
- **Rounds 2 y 4**: problemas tipo game theory / crowd allocation; su modelado fue correcto a medias, pero lejos del óptimo
- **Round 3**: combinaron optimización + anticipación de la media de bids; sobreestimaron la parte estratégica
- **Round 5**: news trading con varios aciertos y varios errores por sesgo en magnitud esperada

### Lección general
En manual fueron bastante honestos:
- no intentaron “ser héroes”
- sabían que esas rondas tenían mucho ruido y componente de coordinación/juego
- prefirieron controlar pérdidas

---

# Lo más útil que vuestro equipo debería sacar de este repo

## 1. Entender el origen del edge antes de programar
Siempre preguntarse:
- ¿esto viene de fair value fijo?
- ¿de un bot repetitivo?
- ¿de una relación sintética entre activos?
- ¿de un mispricing teórico?
- ¿de un mecanismo de fills/conversión?

## 2. El dashboard importa muchísimo
Su writeup deja claro que buena parte de sus ideas no salieron de fórmulas sofisticadas, sino de:
- ver bien el libro
- filtrar trades
- mirar posiciones y fills
- normalizar series correctamente

## 3. Evitar sobreingeniería
Ellos rechazaron varias ideas “cuantitativamente bonitas” porque:
- no estaban justificadas estructuralmente
- añadían parámetros
- empeoraban robustez

## 4. Website score no es verdad absoluta
Si optimizas para el website sin entender el mecanismo, puedes sobreajustar el ruido del simulador.

## 5. Trader behavior > time series pura
En varias rondas, el alpha clave vino de:
- Olivia
- taker bots
- patrones de fills
no de modelos clásicos de forecasting

## 6. Elegir paisajes estables, no solo máximos
En grid search, preferían zonas planas y robustas frente al mejor punto absoluto.

## 7. Hacer estrategias compatibles con la operativa real
No basta con que una señal exista:
- tiene que poder ejecutarse
- convivir con inventario
- respetar conversion limits
- no romper la latencia o serialización
