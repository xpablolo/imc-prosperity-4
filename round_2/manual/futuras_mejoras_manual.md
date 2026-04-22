# Limitaciones del approach actual y mejoras para futuras rondas

## Limitaciones

### 1. Pesos demasiado “story-driven”
La mezcla por tipos funciona, pero los pesos siguen dependiendo bastante de juicio subjetivo.  
Eso puede ir bien en una ronda concreta y fallar si cambia el field.

### 2. Simulación demasiado i.i.d.
Tratamos a los jugadores como draws independientes de la misma mezcla.  
En realidad muchas veces hay **crowding**: varios equipos convergen al mismo número, razonamiento o prompt.

### 3. Un único escenario central da falsa precisión
Aunque haya sensibilidad, el enfoque sigue girando alrededor de una mezcla central.  
Eso puede hacer que la decisión dependa demasiado de una narrativa concreta.

### 4. El componente estratégico aún es simple
La quantal response de un paso está bien, pero no captura bien distintos **niveles de razonamiento** dentro del field.

### 5. El framework aún está algo pegado al problema actual
La idea es buena, pero todavía no está totalmente abstraída para reutilizarla rápido en otros manual rounds.

---

## Mejoras prioritarias

### 1. Usar varios escenarios de pesos, no una sola mezcla
En vez de fijar un único vector \(w\), trabajar con varios escenarios plausibles:
- más IA,
- más focales,
- más racionales,
- más just-above,
- más crowding.

Y elegir la acción que mejor aguante entre todos.

**Dónde habría ayudado antes:**  
- **Manual Round 5 (portfolio optimization):** encaja perfecto, porque ahí la clave era optimizar bajo incertidumbre de priors.  
- **Manual Round 2 (shipping container):** útil si había varias narrativas plausibles sobre cómo se repartiría el field.

---

### 2. Modelar crowding / correlación entre jugadores
No solo mezcla i.i.d., sino modos del field:
- modo ChatGPT / números limpios,
- modo Nash,
- modo focal,
- modo conservative / corner.

**Dónde habría ayudado antes:**  
- **Manual Round 4:** era justo una ronda donde distintos grupos podían concentrarse en pocos números salientes.  
- **Manual Round 2:** si muchos equipos convergían a una misma “solución razonable”, esta mejora capturaría mejor el riesgo de saturación.

---

### 3. Pasar de mezcla de distribuciones a mezcla de agentes
Más que definir solo PMFs, conviene definir arquetipos reutilizables:
- strategic,
- focal,
- just-above,
- naive,
- LLM-like,
- corner,
- noise.

Así el framework se adapta mejor cuando cambia el tipo de ejercicio.

**Dónde habría ayudado antes:**  
- **Automatic Round 5 (Trader IDs):** el ejercicio literalmente pedía clasificar agentes: noise, market makers, informed.  
- **Manual Round 4:** también encaja muy bien con el enfoque de griefers, Nash-followers y round-number players.

---

### 4. Introducir level-k / cognitive hierarchy
En vez de “racionales” como un solo bloque:
- Level 0: random / focal / naive
- Level 1: responde a Level 0
- Level 2: responde a 0 + 1
- Level 3: casi racional

Esto suele ser más realista que Nash puro.

**Dónde habría ayudado antes:**  
- **Manual Round 2:** mejor que asumir un equilibrio limpio en un field muy heterogéneo.  
- **Manual Round 4:** también natural si algunos equipos hacían just-above sobre números focales y otros respondían a eso.

---

### 5. Formalizar mejor la optimización robusta
No elegir solo por EV.  
Mirar también:
- regret medio,
- regret máximo,
- percentiles malos,
- estabilidad del top-3 entre escenarios.

**Dónde habría ayudado antes:**  
- **Manual Round 5:** clarísimo, porque era un problema de optimización bajo incertidumbre.  
- **Manual Round 3:** si la distribución de valores o bids tenía ambigüedad, una regla robusta habría sido mejor que una solución demasiado puntual.

---

### 6. Separar “modelo del field” y “modelo del mundo”
No todas las rondas son crowding games.  
A veces el problema no es qué harán los otros jugadores, sino qué distribución tiene el entorno.

**Dónde habría ayudado antes:**  
- **Manual Round 3:** ahí lo central era modelar bien la distribución de valores, más que la población rival.  
- **Manual Round 1:** el núcleo era el grafo y el path óptimo; la mezcla poblacional no era el core, solo podría haber sido auxiliar si hubiese incertidumbre adicional.

---

## Qué mantener sí o sí

Hay partes del approach actual que son muy buenas y conviene conservar:

- mezcla poblacional por tipos,
- Nash como componente parcial,
- Monte Carlo poblacional,
- uso de regret y robustez,
- inclusión de IA, focalidad, colas y jugadores incompletamente optimizados.

---

## Idea central para el futuro

El siguiente salto no es añadir más distribuciones, sino pasar a:

**mezcla de agentes + escenarios plausibles + optimización robusta**

Eso mantiene lo que ya funcionó bien en esta ronda y lo hace mucho más reusable para futuras rondas.