# Manual de Buenas Prácticas v2.0

**Autor:** Roman Alejandro  
**Versión:** 2.3  
**Fecha:** 23 de mayo de 2026  
**Alcance:** Universal — aplica a todos los proyectos, lenguajes y frameworks.

**Cambios v2.2 → v2.3 (23-may-2026):**
- Nueva sección 8.6: Piso de testing para paths financieros críticos (gate pre-live).
- Ampliación 10.2: Cadencia de commits (lección del lock huérfano + 50 archivos uncommitted del 13-23 may en Sentinel).
- Ampliación 13: Layout del repo es extensión por proyecto (estructura de §2 es referencia, no obligatorio).
- Sección 14 completada (estaba truncada).
- Nueva sección 15: Automatización y Enforcement (pre-commit hooks + CI). Distinción "regla" vs "hook que la fuerza".

**Cambios v2.1 → v2.2 (13-may-2026):**
- Nueva sección 5.3: Tiempo y fechas en sistemas time-sensitive.
- Nueva subsección 6.2.x: Endpoints legacy — extender vs crear nuevo.
- Nueva subsección 6.2.y: Endpoints específicos vs generales — balance SRP + ISP.
- Nueva sección 8.5: Benchmarks como prerrequisito de validación (con alcance acotado).
- Nueva sección 10.4: Períodos de validación y excepciones documentables.

---

## 1. Filosofía

Este manual existe porque construimos software como si fuera a ser auditado por un ingeniero senior mañana. No porque vaya a pasar, sino porque cuando pase — y en algún momento pasará — el código ya estará listo.

**Principio rector:** si alguien externo abre el repositorio, debe poder decir "esto se hizo bien, es fácil de entender, es fácil de modificar, es fácil de escalar."

**Tres reglas irrompibles:**

1. **Construir bien desde el inicio** — refactorear después cuesta 10x más que hacerlo bien ahora.
2. **Documentar como si tuvieras amnesia** — mañana no vas a recordar por qué tomaste esa decisión.
3. **Pensar en escala** — aunque hoy seas un solo usuario, diseña para que 100 puedan usar tu sistema sin reescribirlo.

---

## 2. Estructura de Proyecto

Todo proyecto debe tener estos archivos desde el día uno:

```
proyecto/
├── CLAUDE.md              # Estado del proyecto, decisiones, contexto para IA
├── PROJECT_MAP.md         # Mapa completo: qué hace cada archivo, flujos, dependencias
├── CHANGELOG.md           # Registro de cambios técnicos y funcionales
├── CHANGELOG-UI.md        # Solo si hay UI — puente con diseño
├── .gitignore             # Archivos excluidos del versionado
├── .env.example           # Template de variables de entorno (sin valores reales)
├── README.md              # Overview, setup, cómo arrancar
├── backups/               # Backups catalogados pre-cambio
├── docs/                  # Especificaciones, arquitectura, decisiones
├── src/                   # Código fuente
└── tests/                 # Tests automatizados
```

### 2.1 Naming de archivos

- **Python:** `snake_case.py` — `orchestrator.py`, `agents.py`
- **JavaScript/React:** `PascalCase.jsx` para componentes, `camelCase.js` para utilidades
- **CSS:** `kebab-case.css` o `tokens.css`
- **Documentación:** `MAYUSCULAS.md` para docs de proyecto, `minusculas.md` para docs técnicos
- **Backups por carpeta:** `backups/YYYYMMDD_descripcion/`

### 2.2 Organización del código

- Cada archivo tiene una responsabilidad clara.
- Si un archivo supera **300 líneas**, evaluar si se puede separar.
- Si un archivo supera **500 líneas**, debe tener:
  1. **Justificación documentada** de por qué no se ha separado (ej: "separar crearía imports circulares" o "todas las rutas comparten middleware y contexto").
  2. **Secciones marcadas explícitamente** con separadores visuales buscables:
     ```
     # ═══════════════════════════════════════════════════════════════
     # § 3 — Endpoints de Portfolio
     # ═══════════════════════════════════════════════════════════════
     ```
  3. **Índice interno** al inicio del archivo que liste las secciones por marcador:
     ```
     # Índice:
     #   § 1 — Imports y configuración
     #   § 2 — Autenticación y middleware
     #   § 3 — Endpoints de Portfolio
     #   § 4 — Endpoints de Trades
     ```
     El índice usa los marcadores `§` como referencia (no números de línea, que se desactualizan con el primer edit). Buscar `§ 3` lleva directo a la sección sin importar en qué línea esté.
- Archivos de más de 500 líneas se editan vía scripts (Python/bash), no con herramientas de edición directa que pueden truncar contenido.

---

## 3. Principios SOLID

Estos cinco principios son obligatorios para todo código nuevo. El código existente se mejora progresivamente cuando se toca por otra razón.

### 3.1 S — Single Responsibility (Responsabilidad Única)

Cada clase, módulo o función hace **una sola cosa**. Si necesitas la palabra "y" para describir qué hace, hay que separar.

```python
# MAL — hace demasiado
class GestorDeUsuarios:
    def crear_usuario(self): ...
    def enviar_email(self): ...
    def generar_reporte(self): ...

# BIEN — cada clase tiene una responsabilidad
class GestorDeUsuarios:
    def crear_usuario(self): ...

class ServicioDeEmail:
    def enviar(self): ...

class GeneradorDeReportes:
    def generar(self): ...
```

**Señales de que se viola este principio:**
- Archivos de más de 300 líneas.
- Clases con más de 5-7 métodos públicos.
- Funciones con más de 30 líneas.
- Necesitas leer el archivo entero para entender una parte.

### 3.2 O — Open/Closed (Abierto/Cerrado)

El código debe estar **abierto para extensión** pero **cerrado para modificación**. Agregar funcionalidad nueva no debería requerir cambiar código existente que ya funciona.

```python
# MAL — hay que modificar la clase cada vez que se agrega un proveedor
class Agente:
    def generar(self, proveedor, prompt):
        if proveedor == "anthropic":
            # lógica Anthropic
        elif proveedor == "google":
            # lógica Google
        elif proveedor == "xai":
            # lógica xAI
        # ... y así por cada proveedor nuevo

# BIEN — se extiende sin tocar lo existente
class BaseAgent(ABC):
    @abstractmethod
    def generar(self, prompt): ...

class AnthropicAgent(BaseAgent):
    def generar(self, prompt): ...

class GoogleAgent(BaseAgent):
    def generar(self, prompt): ...

# Agregar un nuevo proveedor = crear una nueva clase, cero cambios en las existentes
```

### 3.3 L — Liskov Substitution (Sustitución de Liskov)

Cualquier subclase debe poder reemplazar a su clase padre sin romper el sistema. Si `GoogleAgent` hereda de `BaseAgent`, debe comportarse como un `BaseAgent` en cualquier contexto.

**Señales de violación:**
- Subclases que lanzan excepciones no esperadas.
- Subclases que ignoran o no implementan métodos del padre.
- Código que hace `if isinstance(agente, GoogleAgent)` para tratar un caso especial.

### 3.4 I — Interface Segregation (Segregación de Interfaces)

Interfaces pequeñas y específicas. Ningún módulo debería depender de funciones que no usa.

```python
# MAL — interfaz gigante que obliga a implementar todo
class BaseAgent:
    def generar(self): ...
    def generar_stream(self): ...
    def generar_imagen(self): ...
    def transcribir_audio(self): ...
    def traducir(self): ...

# BIEN — interfaces separadas por capacidad
class TextAgent(ABC):
    def generar(self): ...
    def generar_stream(self): ...

class ImageAgent(ABC):
    def generar_imagen(self): ...

class AudioAgent(ABC):
    def transcribir(self): ...

# Cada agente implementa solo lo que soporta
class AnthropicAgent(TextAgent, ImageAgent): ...
class GoogleAgent(TextAgent, ImageAgent, AudioAgent): ...
```

### 3.5 D — Dependency Inversion (Inversión de Dependencias)

Los módulos de alto nivel no dependen de módulos de bajo nivel. Ambos dependen de abstracciones.

```python
# MAL — el orquestador depende directamente de implementaciones concretas
from agents import AnthropicAgent, GoogleAgent

class Orchestrator:
    def __init__(self):
        self.roma = AnthropicAgent()
        self.ale = GoogleAgent()

# BIEN — depende de la abstracción
class Orchestrator:
    def __init__(self, agentes: list[BaseAgent]):
        self.agentes = agentes

# La configuración decide qué implementaciones usar
orquestador = Orchestrator(agentes=[AnthropicAgent(), GoogleAgent()])
```

---

## 4. Clean Code

> **Nota:** Los ejemplos de esta sección usan Python, pero los principios aplican a cualquier lenguaje. Cada lenguaje y framework tiene sus propias convenciones idiomáticas (naming, estructura, patrones de concurrencia, tipado). **La regla universal es: seguir las directrices oficiales y buenas prácticas reconocidas del lenguaje y framework que se esté usando.** Cuando este manual diga "usa snake_case", en React sería camelCase; cuando diga "async/await", en Go serían goroutines. El principio se mantiene, la implementación se adapta.

### 4.1 Nombres descriptivos

```python
# MAL
d = get_data()
for i in d:
    process(i)

# BIEN
hilos_activos = obtener_hilos_activos()
for hilo in hilos_activos:
    procesar_hilo(hilo)
```

**Reglas de naming:**
- Variables y funciones: describen qué contienen o qué hacen.
- Booleanos: empiezan con `es_`, `tiene_`, `puede_` — `es_activo`, `tiene_imagenes`.
- Funciones: empiezan con verbo — `crear_hilo()`, `enviar_mensaje()`, `calcular_costo()`.
- Constantes: `MAYUSCULAS_CON_GUIONES` — `MAX_RONDAS`, `COSTO_POR_TOKEN`.
- Sin abreviaciones ambiguas: `mensaje` no `msg`, `configuracion` no `cfg`.

### 4.2 Funciones cortas y enfocadas

- Máximo **30 líneas** por función. Si pasa de ahí, dividir.
- Máximo **3-4 parámetros**. Si necesitas más, usa un objeto/diccionario de configuración.
- Una función hace una cosa. Si tiene secciones separadas por comentarios, cada sección debería ser su propia función.
- Sin efectos secundarios ocultos: si `calcular_costo()` también guarda en la base de datos, el nombre miente.

### 4.3 Comentarios

```python
# MAL — comenta el "qué" (redundante, el código ya lo dice)
# Incrementar contador
contador += 1

# BIEN — comenta el "por qué" (contexto que el código no puede expresar)
# Máximo 1 rebote por mensaje para evitar loops infinitos entre agentes
if rebotes >= 1:
    return

# BIEN — documenta decisiones no obvias
# Usamos gemini-2.5-flash porque las versiones 1.5-x y 2.0-x 
# no están disponibles en la API actual (verificado 2026-04)
modelo = "gemini-2.5-flash"
```

### 4.4 Sin código muerto

- No dejar funciones comentadas "por si acaso".
- No dejar imports sin usar.
- No dejar variables que no se leen.
- Si se necesita recuperar algo, está en los backups o en el historial de git.

### 4.5 Sin magic numbers

```python
# MAL
if len(mensajes) > 50:
    comprimir_hilo()
time.sleep(2)

# BIEN
MAX_MENSAJES_ANTES_DE_COMPRIMIR = 50
DELAY_APERTURA_NAVEGADOR_SEGUNDOS = 2

if len(mensajes) > MAX_MENSAJES_ANTES_DE_COMPRIMIR:
    comprimir_hilo()
time.sleep(DELAY_APERTURA_NAVEGADOR_SEGUNDOS)
```

### 4.6 Manejo de errores

```python
# MAL — silenciar errores
try:
    resultado = llamar_api()
except:
    pass

# MAL — capturar todo sin discriminar
try:
    resultado = llamar_api()
except Exception as e:
    print(e)

# BIEN — errores específicos, logging, y acción clara
try:
    resultado = agente.generar(prompt)
except anthropic.RateLimitError as e:
    logger.warning("Rate limit alcanzado para %s: %s", agente.nombre, e)
    raise  # Propagar para que el caller decida qué hacer
except anthropic.APIConnectionError as e:
    logger.error("Sin conexión a Anthropic: %s", e)
    raise ConexionFallidaError(f"No se pudo conectar a {agente.proveedor}") from e
```

---

## 5. Logging

El logging es la caja negra del sistema. Cuando algo falla a las 3am, los logs son lo único que tienes para reconstruir qué pasó.

### 5.1 Principios

- **Un logger por módulo**, no un `print()` global. Cada módulo identifica de dónde viene el mensaje.
- **Niveles correctos:**
  - `DEBUG`: detalle interno útil solo para desarrollo (valores de variables, flujo paso a paso).
  - `INFO`: eventos normales que confirman que el sistema funciona (arranque, tareas completadas, ciclos ejecutados).
  - `WARNING`: algo inesperado que no rompe el sistema pero requiere atención futura.
  - `ERROR`: algo falló y una operación no se completó.
  - `CRITICAL`: el sistema no puede continuar.
- **Nunca loggear datos sensibles:** API keys, contraseñas, tokens, datos personales. Si necesitas loggear un identificador, usa los últimos 4 caracteres o un hash.
- **Formato consistente:** incluir timestamp, nivel, módulo, y mensaje. Ejemplo: `2026-05-07 14:30:01 [INFO] sentinel.dispatcher — Capital asignado: {S-2: 25.0%}`.
- **Logs como evidencia, no como narrativa.** Cada línea debe ser accionable o informativa. "Procesando..." sin resultado no sirve; "Procesado: 15 trades en 230ms" sí.

### 5.2 Anti-patrones

- `print()` en producción — no tiene nivel, no tiene timestamp, no se puede filtrar.
- `except: pass` — el error desaparece y nadie se entera.
- Loggear objetos enteros sin formato — un dump de 500 líneas en el log es ruido.
- Loggear en loops sin límite — un loop de 10,000 iteraciones genera 10,000 líneas. Loggear el resumen al final.

### 5.3 Tiempo y fechas en sistemas time-sensitive

Para sistemas donde el timing importa — trading, scheduling, alertas, sistemas médicos, logs forenses, deadlines regulatorios — nunca afirmar nada sobre tiempo sin verificar contra la fuente.

**Anti-patrón:**

```
# MAL — confiar en una variable de contexto inicial
"El mercado cerró hace una hora, podemos hacer el deploy."
"Ayer vimos X, hoy vamos a hacer Y."
"El sistema lleva 3 días sin reiniciar."
```

Cualquiera puede estar equivocada si la fecha real es distinta a la que se asumió.

**Buena práctica:**

```python
# Genérico — verificar el reloj del sistema
from datetime import datetime, timezone
now_utc = datetime.now(timezone.utc)

# Para sistemas con dependencias externas, verificar contra la
# fuente autoritativa cuando aplique:
#   - Trading: clock del broker (Alpaca, IBKR, Binance)
#   - Networking: NTP server o servidor de tiempo del provider
#   - DB: hora del DB server (puede diferir del cliente)
#   - Scheduling: cron daemon del sistema
#   - Procesos distribuidos: clock skew entre nodos
```

**Reglas concretas:**

- Antes de programar tareas con tiempo absoluto, verificar la hora actual.
- Antes de afirmar "el mercado está cerrado / abierto", consultar el clock real (no asumir por hora local).
- En sesiones largas, la fecha avanza. Recalibrar antes de cualquier acción que dependa de timing.
- En sistemas con consecuencias financieras, médicas o de seguridad, el check es obligatorio antes de cada operación.

**Por qué importa:** decir "es 12 de mayo" cuando son 13 puede llevar a programar un deploy durante mercado abierto pensando que está cerrado, ejecutar reconciliación con el día equivocado, o reportar performance de la jornada anterior como si fuera la actual. En sistemas con dinero real, ese error es caro.

---

## 6. Diseño de APIs

### 6.1 Consumo de APIs externas (Anthropic, Google, xAI)

**Centralizar en un solo punto de acceso:**

```python
# MAL — llamadas a la API dispersas por todo el código
# archivo1.py
respuesta = anthropic.messages.create(...)
# archivo2.py
respuesta = anthropic.messages.create(...)

# BIEN — un wrapper centralizado
# agents.py
class AnthropicAgent(BaseAgent):
    def generar(self, prompt, mensajes): ...
    def generar_stream(self, prompt, mensajes): ...
```

**Manejo de claves:**
- Las API keys viven en `.env`, nunca hardcodeadas en el código.
- El `.env.example` documenta qué keys se necesitan sin exponer valores.
- Validar al arrancar que las keys existen y tienen formato correcto.

**Resiliencia:**
- Implementar reintentos con backoff exponencial para errores transitorios (429, 500, 503).
- Timeouts explícitos en cada llamada — nunca esperar indefinidamente.
- Logging de cada llamada: modelo usado, tokens consumidos, costo, tiempo de respuesta.
- Circuit breaker: si un proveedor falla N veces seguidas, dejar de intentar por un período.

**Costos:**
- Registrar cada llamada con su costo calculado.
- Alertar cuando el costo acumulado supere un umbral configurable.
- Nunca hacer llamadas innecesarias: cachear respuestas cuando aplique.

### 6.2 Construcción de endpoints propios (REST API)

**Principios de diseño:**

1. **Un endpoint, una responsabilidad.** Si un endpoint devuelve "medio proyecto", hay que dividirlo.
2. **Recursos, no acciones.** URLs basadas en sustantivos, no verbos.
3. **Respuestas consistentes.** Mismo formato siempre.
4. **Errores informativos.** El cliente debe saber qué falló y cómo corregirlo.

**Naming de rutas:**

```python
# MAL
GET  /obtenerTodosLosHilos
POST /crearNuevoHilo
GET  /datosDelHiloConMensajesYCostosYAgentes/123

# BIEN — recursos en plural, verbos HTTP indican la acción
GET    /api/hilos/              # Listar hilos
POST   /api/hilos/              # Crear hilo
GET    /api/hilos/123           # Detalle de un hilo
PATCH  /api/hilos/123           # Actualizar parcialmente
DELETE /api/hilos/123           # Eliminar
GET    /api/hilos/123/mensajes  # Sub-recurso: mensajes del hilo
```

**Formato de respuesta estándar:**

```json
// Éxito
{
  "data": { ... },
  "meta": { "total": 42, "pagina": 1, "por_pagina": 20 }
}

// Error
{
  "error": "Hilo no encontrado",
  "codigo": "HILO_NO_ENCONTRADO",
  "detalle": "No existe un hilo con ID 999",
  "status": 404
}
```

**Reglas de endpoints:**

- **Paginación obligatoria** en listas — nunca devolver todos los registros.
- **Filtros por query params** — `GET /api/hilos?modo=chat&desde=2026-05-01`.
- **Selección de campos** — permitir `?campos=id,titulo,modo` para respuestas ligeras.
- **Versionado** — `/api/v1/hilos` cuando haya breaking changes.
- **Rate limiting** — proteger endpoints costosos.
- **Validación de entrada** — validar todo antes de procesarlo. Nunca confiar en el input del cliente.
- **Códigos HTTP correctos:**
  - `200` OK
  - `201` Creado
  - `204` Sin contenido (DELETE exitoso)
  - `400` Request inválido (input malformado)
  - `401` No autenticado
  - `403` No autorizado
  - `404` No encontrado
  - `422` Entidad no procesable (validación de negocio)
  - `429` Rate limit excedido
  - `500` Error interno

**Endpoints SSE (Server-Sent Events):**

```python
# Siempre incluir:
# 1. Event type para que el cliente sepa qué procesar
# 2. Data serializada como JSON
# 3. Evento de cierre explícito
# 4. Manejo de desconexión del cliente

def stream_respuesta():
    yield f"event: inicio\ndata: {json.dumps({'agente': 'Roma'})}\n\n"
    for chunk in agente.generar_stream(prompt):
        yield f"event: chunk\ndata: {json.dumps({'texto': chunk})}\n\n"
    yield f"event: fin\ndata: {json.dumps({'tokens': total})}\n\n"
```

### 6.2.x Endpoints legacy: extender vs crear nuevo

Cuando heredás un endpoint que ya viola algún principio (responsabilidad única, formato estándar, naming), la tentación es agregar campos al endpoint existente. Esa decisión casi siempre es incorrecta.

**Regla:** si un endpoint ya está mal y necesitás funcionalidad nueva, crear un endpoint nuevo con diseño correcto. El viejo queda como deuda técnica para refactorizar.

**Por qué:**

- Agregar a un endpoint con mal diseño multiplica el problema, no lo resuelve.
- Refactorizar al formato correcto requiere modificar a los consumidores existentes. Hacerlo durante un cambio funcional contamina dos objetivos en uno.
- Un endpoint nuevo con responsabilidad clara es testeable, documentable y reemplazable. Uno viejo con muchas responsabilidades nuevas se vuelve más rígido.

**Ejemplo:**

```python
# Endpoint heredado, ya viola responsabilidad única:
@app.get("/api/account/equity")
def get_account():
    return {
        "equity": ..., "cash": ...,
        "positions": [...],     # ya devuelve lista detallada
        "unrealized_pl": ...
    }

# MAL — agregar más responsabilidades al mismo endpoint:
return {
    "equity": ..., "cash": ..., "positions": [...],
    "invested": ...,                  # ← nuevo
    "day_pnl_pct_of_invested": ...,   # ← nuevo
    # y más con el tiempo...
}

# BIEN — endpoint nuevo con responsabilidad única y formato estándar:
@app.get("/api/account/capital")
def get_capital_metrics():
    return {
        "data": { "invested": ..., "day_pnl_pct_of_invested": ... },
        "meta": { "source": ..., "as_of": ... }
    }
    # El endpoint viejo queda intacto, anotado como deuda técnica.
```

**Cuándo SÍ extender un endpoint existente:**

- El endpoint ya cumple los principios del manual.
- El cambio mantiene el formato estándar.
- No agrega responsabilidades nuevas, solo enriquece la existente.

**Anti-patrón a evitar:** "Después lo refactorizo bien." En la práctica, ese "después" rara vez llega. Mejor crear el nuevo correctamente desde el primer día y dejar el viejo marcado para limpieza.

### 6.2.y Endpoints específicos vs generales: balance SRP + ISP

La pregunta no es "específicos siempre" ni "generales siempre" — es balance entre dos principios SOLID:

- **SRP (Single Responsibility):** una responsabilidad conceptual por endpoint.
- **ISP (Interface Segregation):** consumers diferentes no deberían depender de datos que no usan.

**Cuándo dividir:**

1. **Por responsabilidad conceptual** (SRP): el endpoint trata recursos distintos. Orders ≠ Products ≠ Inventory ≠ Account ≠ Capital metrics.
2. **Por consumer** (ISP): el endpoint sirve a tipos de usuarios con necesidades diferentes. Admin necesita datos sensibles; viewer no. Frontend público necesita subset; backoffice necesita todo.
3. **Por formato/audiencia:** dashboards vs reportes batch vs sync service-to-service pueden requerir endpoints distintos aunque la data underlying sea similar.

**Cuándo NO dividir:**

1. Fragmentar tan fino que el cliente termina haciendo N+1 fetches para componer una vista normal. Si tu frontend necesita siempre llamar a 7 endpoints para renderizar una página, los unificaste mal.
2. Dividir cuando lo que cambia es solo formato, no responsabilidad. Usar parámetros (`?fields=`, `?format=csv`) en vez de endpoints nuevos.
3. Dividir cuando los datos están naturalmente acoplados y siempre se usan juntos. Una orden con sus líneas suele consultarse junta.

**Pregunta guía:** "¿quiénes son los consumers y qué necesita cada uno?". Si la respuesta diferencia, divide. Si no, mantené unido.

---

## 7. Seguridad

### 7.1 Variables de entorno y secretos

- **Nunca** hardcodear API keys, contraseñas, o secretos en el código.
- **Nunca** subir `.env` a git. El `.gitignore` debe incluirlo desde el día uno.
- Usar `.env.example` con valores placeholder como documentación.
- En producción, usar variables de entorno del sistema o un gestor de secretos.
- Rotar keys periódicamente. Si una key se expone, revocarla inmediatamente.

### 7.2 Validación de entrada

- **Nunca** confiar en datos del cliente — validar todo en el servidor.
- Sanitizar strings para prevenir inyección SQL (usar ORM como SQLAlchemy).
- Limitar tamaños de payload (imágenes, textos largos).
- Validar tipos de datos: si esperas un número, rechaza strings.

```python
# MAL — confía ciegamente en el input
@app.route("/api/hilos/<id>/mensaje", methods=["POST"])
def enviar_mensaje(id):
    datos = request.json
    contenido = datos["contenido"]  # ¿Y si no viene?
    
# BIEN — validación explícita
@app.route("/api/hilos/<int:id>/mensaje", methods=["POST"])
def enviar_mensaje(id):
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "Body JSON requerido"}), 400
    
    contenido = datos.get("contenido", "").strip()
    if not contenido and not datos.get("imagenes"):
        return jsonify({"error": "Mensaje vacío"}), 422
    
    if len(contenido) > MAX_LONGITUD_MENSAJE:
        return jsonify({"error": f"Mensaje excede {MAX_LONGITUD_MENSAJE} caracteres"}), 422
```

### 7.3 CORS y headers

- En desarrollo: CORS abierto (`*`) está bien.
- En producción: restringir CORS a los dominios permitidos.
- Usar headers de seguridad: `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`.

### 7.4 Base de datos

- Siempre usar ORM o queries parametrizados — nunca concatenar strings en SQL.
- Encriptar datos sensibles en reposo cuando aplique.
- Backups automáticos de la base de datos.

### 7.5 Dependencias

- Mantener las dependencias actualizadas — las versiones viejas tienen vulnerabilidades conocidas.
- Usar versiones fijas en producción (`==`) y rangos en desarrollo (`>=`).
- Revisar periódicamente vulnerabilidades con herramientas como `pip audit` o `npm audit`.

---

## 8. Testing

### 8.1 Filosofía

No se necesita 100% de cobertura. Se necesita confianza de que los cambios no rompen cosas. La prioridad es testear lo que duele cuando se rompe.

### 8.2 Qué testear (en orden de prioridad)

1. **Lógica de negocio crítica** — cálculo de costos, detección de menciones, parseo de señales.
2. **Endpoints de API** — que devuelvan los códigos y formatos correctos.
3. **Integraciones** — que las llamadas a APIs externas manejen errores correctamente.
4. **Edge cases** — inputs vacíos, caracteres especiales, límites numéricos.

### 8.3 Estructura de tests

```
tests/
├── unit/                # Tests de funciones aisladas
│   ├── test_costos.py
│   ├── test_menciones.py
│   └── test_señales.py
├── integration/         # Tests de flujos completos
│   ├── test_chat_grupal.py
│   └── test_debate.py
├── api/                 # Tests de endpoints
│   ├── test_hilos.py
│   └── test_agentes.py
└── conftest.py          # Fixtures compartidos
```

### 8.4 Convenciones

```python
def test_detectar_mencion_directa_con_arroba():
    """@Roma al inicio debe detectar mención directa."""
    resultado = detectar_mencion("@Roma qué opinas?", ["Roma", "Ale"])
    assert resultado.tipo == "directa"
    assert resultado.agente == "Roma"

def test_detectar_mencion_conversacional_en_medio():
    """Nombre en medio del texto es conversacional, no directa."""
    resultado = detectar_mencion("Me gustó lo de Roma", ["Roma", "Ale"])
    assert resultado.tipo == "conversacional"
```

**Naming:** `test_<qué>_<condición>_<resultado_esperado>`

**Cada test es independiente** — no depende del orden ni del estado de otros tests.

### 8.5 Benchmarks como prerrequisito de validación

**Cuándo aplica esta sección:**

Sistemas con outputs cuantitativos (rendimiento financiero, accuracy, latencia, throughput, tasa de error, costo) donde existe al menos una alternativa conocida contra la cual comparar.

**Cuándo NO aplica:**

- Proyectos creativos (escritura, música, arte).
- Sistemas únicos sin equivalente comparable.
- Fases tempranas sin outputs medibles todavía.
- Proyectos con valor intrínseco no cuantificable.

Si tu sistema cae en el segundo grupo, ignorar esta sección. Si cae en el primero, leer.

**Por qué importa:**

- "El sistema rinde +5%" es ambiguo. ¿Comparado con qué? ¿Mercado plano? ¿Buy-and-hold del benchmark? ¿Otro sistema?
- Sistemas que parecen rendir bien pueden estar perdiendo contra alternativas pasivas más simples.
- Sin benchmark explícito, decidir si seguir invirtiendo en el sistema o abandonarlo se vuelve subjetivo.

**Cómo definir un benchmark apropiado:**

- **Mismo riesgo:** comparar contra una estrategia con riesgo similar. Trading sistemático activo se compara con buy-and-hold del benchmark del mismo activo (SPY si opera US equities, BTC si opera crypto).
- **Mismo período:** mismas fechas exactas. No comparar "rendimiento de mayo" contra "promedio histórico anual".
- **Mismo costo:** si el sistema tiene fees explícitas, comparar net of fees contra el benchmark net of fees.
- **Mismo capital:** sobre el capital efectivamente deployado, no sobre el capital total disponible.

**Ejemplos de benchmarks por tipo de sistema (plantillas, no obligaciones):**

| Sistema | Benchmark apropiado |
|---|---|
| Trading US equities | SPY buy-and-hold mismo período |
| Cripto trading | BTC buy-and-hold |
| ML clasificador | Heurística simple + accuracy humano |
| Sistema de recomendación | Recomendación aleatoria + popularidad simple |
| Latencia de API | SLA establecido + competidor directo |
| Sistema de alertas | Random selection + threshold simple |

**Reportar performance sin benchmark es engañoso.** Si el sistema rinde +5% pero el benchmark rindió +8%, el sistema perdió 3 puntos. Si el sistema rindió +1% pero el benchmark rindió -3%, el sistema ganó 4 puntos. El número absoluto no dice nada sin contexto.

**Trampa común:**

Comparar el rendimiento "por dólar deployado" contra el rendimiento "absoluto" del benchmark da resultados engañosos. Si el sistema deploya el 5% del capital y rinde +8% sobre ese 5%, mientras el benchmark deploya 100% y rinde +6% sobre el todo:

- "Por dólar deployado" el sistema gana (8% > 6%).
- "Absoluto" el sistema pierde feo (0.4% del total vs 6% del total).

Reportar las dos métricas siempre. La primera mide la calidad del sistema. La segunda mide el costo de oportunidad de no haber deployado todo.

### 8.6 Piso de testing para paths financieros críticos (gate pre-live)

**Cuándo aplica:** sistemas que manejan dinero real (trading, pagos, custodia, settlement). La regla del 8.1 sigue vigente — no se busca 100% de cobertura genérica — pero los **paths financieros críticos** son la excepción y deben tener test antes de pasar a fase live.

**Definición de "path financiero crítico":** TODA función que:

- Calcule sizing/allocation de posiciones (`allocate_capital`, `calculate_position_size`).
- Procese fills u órdenes (`process_signal`, `submit_order`, callbacks de fills).
- Modifique el cache de posiciones abiertas o la representación de equity en memoria.
- Calcule P&L, Sharpe, drawdown, equity ajustado.
- Dispare kill switch, circuit breaker, parking brake o cualquier control de riesgo.
- Manipule cash, buying power, allocation de capital entre estrategias.

**Cobertura objetivo en estos paths: 100%.** Resto del código sigue regla genérica §8.1-8.4 (criterio del autor).

**Por qué:**

Los bugs en paths financieros no se manifiestan como "feature roto" — se manifiestan como dinero perdido, posiciones huérfanas, shorts accidentales, o métricas falseadas. El costo de detectar tarde es asimétrico vs el costo de mantener tests.

**Caso de aplicación real (Sentinel, 23-may-2026):** el bug `#H-5b` (cache `open_positions` que se sobreescribía con `side='SELL'` en lugar de removerse tras SELL FILLED) generó **45 warnings "Posiciones fantasma" en 5 días** y dos intervenciones manuales (SPY 11-may, QQQ 15-may, costo neto $-12). Un test unitario sobre `_apply_fill_to_cache(ticker, status, position)` lo habría atrapado el primer día. El fix posterior (HANDOFF #6 de la sesión 23-may) refactorizó el helper específicamente para hacerlo testeable de forma aislada — patrón a replicar en cualquier path crítico.

**Gate operativo:**

Antes de transición a fase live (capital real), checklist:

- [ ] Test unitario para cada función listada en "path financiero crítico" arriba.
- [ ] Tests rojos antes del fix de cualquier bug financiero (TDD), verdes después.
- [ ] Test de regresión por cada bug financiero resuelto previamente (no se debe poder reintroducir).
- [ ] Cobertura ≥95% sobre módulos `dispatcher.py`, `historian.py`, módulo de cálculo de riesgo, callbacks de fills.

Sin este checklist, NO se promueve a live. Es una regla durable, no una sugerencia.

---

## 9. Documentación

### 9.1 CLAUDE.md — contexto para IA

Este archivo es lo primero que lee la IA al abrir una sesión. Debe contener:

- Qué es el proyecto (2-3 líneas).
- Stack tecnológico.
- Estado actual (qué funciona, qué está en progreso).
- Archivos clave (tabla con archivo → propósito).
- Decisiones de arquitectura (con el "por qué" de cada una).
- Tareas completadas y pendientes.
- Problemas conocidos.
- Cómo arrancar el proyecto.

**Se actualiza al final de cada sesión de trabajo.**

### 9.2 PROJECT_MAP.md — mapa para humanos

Orientación rápida para cualquier persona (o IA) que entre al proyecto por primera vez:

- Qué es y para qué sirve.
- Estructura de archivos con descripción de cada uno.
- Flujos de datos principales (con diagramas ASCII si ayuda).
- Base de datos (tablas, relaciones).
- API (endpoints con método, ruta, propósito).
- Dependencias externas.
- Cómo arrancar.

### 9.3 CHANGELOG.md — historial técnico

Formato basado en [Keep a Changelog](https://keepachangelog.com/):

```markdown
## [2.0.0] — 2026-05-06 — Descripción corta

### Agregado
- Descripción de lo nuevo

### Cambiado
- Descripción de lo que se modificó

### Corregido
- Bugs arreglados

### Eliminado
- Lo que se removió
```

**Versionado semántico:**
- **MAJOR** (X.0.0): cambios que rompen compatibilidad.
- **MINOR** (0.X.0): funcionalidad nueva sin romper lo existente.
- **PATCH** (0.0.X): correcciones de bugs.

### 9.4 Docstrings

Toda función pública tiene docstring. Formato:

```python
def enviar_mensaje_chat(self, hilo_id: int, contenido: str, 
                         modelos: dict, imagenes: list = None):
    """Envía un mensaje en modo chat grupal y genera respuestas via SSE.
    
    Detecta menciones en el contenido, invoca a los agentes correspondientes,
    y hace yield de chunks SSE para streaming en tiempo real.
    
    Args:
        hilo_id: ID del hilo de conversación.
        contenido: Texto del mensaje del usuario.
        modelos: Diccionario {nombre_agente: modelo} con los modelos activos.
        imagenes: Lista de imágenes en base64 (opcional).
    
    Yields:
        str: Líneas SSE con formato "event: tipo\\ndata: json\\n\\n"
    
    Raises:
        HiloNoEncontradoError: Si el hilo_id no existe.
        AgenteSinConfigError: Si un agente no tiene API key configurada.
    """
```

---

## 10. Control de Cambios

### 10.1 Backups

- **Cuándo:** antes de cambios que toquen múltiples archivos o lógica crítica.
- **Formato:** `backups/YYYYMMDD_descripcion/` con los archivos afectados + CLAUDE.md.
- **No se requiere backup para:** cambios cosméticos aislados (un texto, un color).
- **Los cambios menores se documentan** en CHANGELOG.md para trazabilidad.

### 10.2 Git

- **Commits atómicos:** cada commit hace una sola cosa y tiene un mensaje descriptivo.
- **Formato de mensaje:** `tipo: descripción corta` — ejemplo: `feat: agregar auto-título de hilos`
- **Tipos:** `feat` (nueva funcionalidad), `fix` (corrección), `refactor`, `docs`, `test`, `chore`
- **Nunca commitear:** `.env`, `node_modules/`, `__pycache__/`, `dist/`, `*.db`, archivos temporales.
- **Cadencia:** commitear al cerrar cada cambio lógico completo. No acumular más de 24-48 hs sin commitear. **Lección del 13-23 may en Sentinel:** un `.git/index.lock` huérfano del 13-may bloqueó toda escritura git por 10 días sin que nadie lo detectara. Para el 23-may había ~50 archivos modificados sin commitear, contaminación cruzada de mayo, y casi se expone un `.env.bak` con secretos al hacer el commit grande. La falta de cadencia fue corresponsable del problema. Verificar `.git/` por locks huérfanos si `git commit` falla silenciosamente o si pasan días sin que el repo registre actividad esperada.

### 10.3 Line endings

- **Regla por defecto:** LF (`\n`) para todos los archivos de código fuente, independientemente del OS.
- Configurar `.gitattributes` con `* text=auto eol=lf` para que git normalice automáticamente.
- Si un editor o framework fuerza CRLF, documentarlo en el README del proyecto.

### 10.4 Períodos de validación y excepciones documentables

Cuando un sistema entra en fase de validación (paper trading, beta cerrada, ML model en evaluación, piloto regulatorio), establecer un período de cambios mínimos antes de tocar nada.

**Por qué:**

- Cada cambio durante validación contamina los datos. Las métricas pre y post cambio no son comparables.
- Ajustar parámetros porque "los números no salen bien" es la trampa clásica de overfitting psicológico.
- Necesitás datos limpios sobre N días consecutivos para evaluar honestamente.

**Cómo se estructura:**

1. **Definir explícitamente las fechas:** "Período de validación desde DD-MM-YYYY hasta DD-MM-YYYY."
2. **Listar qué NO se puede cambiar:** thresholds, prompts, agentes, schema, lógica core.
3. **Listar qué SÍ se puede cambiar:** bug fixes críticos (con definición clara de "crítico"), observabilidad read-only, documentación, cosmética.
4. **Documentar excepciones numeradas:** si un cambio crítico fue necesario, registrarlo como Excepción N con fecha, justificación, archivos modificados, marca pre/post.

**Estructura de una excepción documentada:**

```markdown
### Excepción N — YYYY-MM-DD: [Título corto]

**Situación:** [qué bug crítico forzó el cambio]
**Justificación:** [por qué es crítico, no opcional]
**Cambios realizados:** [archivos + líneas]
**Marca de datos:** pre-excepción-N vs post-excepción-N
**Contador del período:** [se reinicia / NO se reinicia, con justificación]
```

**Regla del contador:**

- Si la excepción cambia la **hipótesis bajo prueba** (lógica, thresholds, comportamiento del sistema), reiniciar el contador del período.
- Si la excepción solo arregla un bug de **implementación** que impedía probar la hipótesis original, NO reiniciar el contador. Los datos siguen siendo válidos.

**Disciplina psicológica:**

Durante el período vas a sentir presión para "tocar el sistema cuando muestre números mediocres". Resistir. Los números mediocres son **información**, no problema. Sirven para evaluar al final del período.

**Excepciones aplicables:**

- Bugs que rompen persistencia, ejecución, o pierden dinero por error técnico.
- Vulnerabilidades de seguridad expuestas.
- Datos corruptos en DB que requieren intervención.

**Excepciones NO aplicables (esperar al fin del período):**

- "Quiero ajustar el threshold X porque los números son mediocres."
- "Se me ocurrió un feature nuevo."
- "Quiero ver si funciona mejor con otro parámetro."

---

## 11. Flujo de Trabajo con IA

### 11.1 Inicio de sesión

1. Leer `CLAUDE.md` para contexto del proyecto.
2. Leer memorias relevantes.
3. Verificar restricciones temporales o bloqueos.
4. Preguntar antes de asumir.

### 11.2 Optimización de contexto

- **No repetir información** que ya está en CLAUDE.md o PROJECT_MAP.md.
- **Archivos grandes** (>500 líneas): leer solo las secciones relevantes, no el archivo completo.
- **No crear archivos de documentación redundantes** — un CHANGELOG.md, un PROJECT_MAP.md, no tres versiones de cada uno.
- **Mantener la memoria actualizada** — guardar aprendizajes que apliquen a sesiones futuras.

### 11.3 Antes de escribir código

1. Leer el manual de buenas prácticas (este archivo).
2. Entender la estructura existente del proyecto.
3. Planificar los cambios antes de ejecutar.
4. Crear backup si los cambios son significativos.

### 11.4 Después de escribir código

1. Verificar que funciona (tests, prueba manual, consola sin errores).
2. Actualizar CLAUDE.md con el estado nuevo.
3. Actualizar CHANGELOG.md con los cambios.
4. Actualizar PROJECT_MAP.md si se agregaron archivos nuevos.

---

## 12. Idioma

- **Código fuente:** variables y funciones en español cuando el dominio es en español. Términos técnicos universales en inglés (`stream`, `endpoint`, `token`, `cache`).
- **Comentarios:** español.
- **Documentación:** español.
- **UI:** español.
- **Mensajes de error:** español.
- **Commits:** español.
- **Nombres de archivos:** convención del lenguaje (snake_case para Python, PascalCase para React).

---

## 13. Extensiones por Proyecto

Este manual es la base universal. Cada proyecto puede tener un documento hijo con reglas específicas:

- **Meridian:** `CLAUDE.md` contiene decisiones de UI (oklch tokens, tipografía), reglas de chat grupal, divergencias con Claude Design.
- **AfterLife (Sentinel):** `sentinel-v0.5/CLAUDE.md` mantiene reglas específicas del bot (régimen NEUTRAL fijo, scheduler reporte diario flag, restricciones del período de observación, plan de 6 fases post-observación, etc.). El proyecto también tiene `teamwork/LOG.md` con coordinación bidireccional Cowork↔Code (ver §11.5 si existe, o memoria `project_cowork_code_protocol.md` de cada instancia).
- **Proyectos futuros:** copian este manual y agregan su extensión.

El hijo **nunca contradice** al padre. Si hay conflicto, el manual universal gana.

### 13.1 Layout del repo es extensión por proyecto

§2 da una **estructura de referencia** con `src/`, `tests/`, `docs/`, etc. **No es obligatorio.** Proyectos pueden ser:

- **Flat:** ej. `afterlife-capital/sentinel-v0.5/dispatcher.py` directo, sin `src/`. Usual en proyectos chicos o cuando hay una sola "app" en el repo.
- **Con `src/`:** ej. `meridian/src/agents/`, `meridian/src/api/`. Usual en proyectos medianos/grandes o con múltiples paquetes.
- **Monorepo:** múltiples sub-proyectos con su propio layout, cada uno con su `PROJECT_MAP.md`.

Cada proyecto **documenta su layout en `PROJECT_MAP.md`**. Si el layout difiere de §2, el `PROJECT_MAP.md` explica por qué y cómo. Lo importante es la coherencia interna y la legibilidad, no la fidelidad al template.

---

## 14. Checklist de Revisión

Antes de dar por terminado un cambio significativo, recorrer este checklist:

**Diseño:**
- [ ] ¿Cumple SOLID (§3)? Especialmente SRP — una sola responsabilidad por unidad.
- [ ] Si toca dinero/equity/posiciones, ¿usa `Decimal` everywhere (no `float`)?
- [ ] Si agrega un endpoint nuevo, ¿sigue el formato estándar de §6.2 (`{ data, meta }` o `{ error, codigo, detalle, status }`)?

**Código:**
- [ ] Nombres descriptivos (§4.1). Booleanos con prefijo `es_/tiene_/puede_`. Funciones con verbo.
- [ ] Funciones ≤30 líneas, ≤4 parámetros (§4.2).
- [ ] Sin magic numbers (§4.5).
- [ ] Errores específicos con logging y propagación adecuada (§4.6).
- [ ] Sin código muerto, sin imports sin usar (§4.4).

**Persistencia y seguridad:**
- [ ] Queries parametrizadas, sin concatenación de strings (§7.4).
- [ ] Inputs validados en servidor (§7.2).
- [ ] `.env`, `client_secret_*`, `*.dump`, backups in-place excluidos del repo (§7.1 + `.gitignore`).
- [ ] Si es repo público, **audit de archivos sensibles** antes de push (PII, dumps DB, inventarios, code-outputs, ZIPs binarios sin auditar).

**Tests:**
- [ ] Lógica de negocio crítica testeada (§8.1-8.2).
- [ ] **Si toca path financiero crítico, cobertura objetivo 100% (§8.6).**
- [ ] Edge cases cubiertos (inputs vacíos, ATR=0, qty=0, error de API externa).
- [ ] Tests TDD: rojo → fix → verde demostrado.

**Documentación:**
- [ ] `CLAUDE.md` del proyecto actualizado (§9.1).
- [ ] `CHANGELOG.md` con entrada nueva (§9.3).
- [ ] `PROJECT_MAP.md` actualizado si se agregaron/eliminaron archivos (§9.2).
- [ ] Docstrings en funciones públicas (§9.4).

**Control de cambios:**
- [ ] Backup pre-edit catalogado en `backups/YYYY-MM-DD/` si los cambios son significativos (§10.1).
- [ ] Commit atómico con mensaje formato `tipo: descripción` en español (§10.2).
- [ ] **Cadencia respetada:** no acumular ≥48 hs sin commitear (§10.2).
- [ ] Line endings consistentes con `.gitattributes` del proyecto (§10.3).

**Si el proyecto está en período de validación (§10.4):**
- [ ] El cambio cae en "PERMITIDO" del documento del proyecto.
- [ ] Si es excepción, está documentada con justificación + marca de datos + decisión sobre contador.

---

## 15. Automatización y Enforcement

**Principio rector:** una regla escrita en el manual que depende de criterio humano sesión a sesión se viola eventualmente. La diferencia entre "regla" y "regla efectiva" es el **hook que la fuerza automáticamente**.

### 15.1 Por qué existe esta sección

Casos reales de Sentinel (sesión 23-may-2026) que motivaron esta sección:

- `.env.bak.131426` con credenciales reales casi commiteado y pusheado a repo público. Lo cazó Code manualmente al revisar el staging. Un hook `gitleaks` o `detect-secrets` lo habría rechazado automáticamente sin necesidad de memoria del operador.
- `.git/index.lock` huérfano del 13-may bloqueó commits 10 días. Un check pre-commit que verifique el estado del repo lo habría detectado al primer intento bloqueado.
- 72 warnings de line-endings (`LF→CRLF`) sin `.gitattributes`. Un check de configuración del repo lo habría señalado.
- Backups in-place (`*.bak.*`, `*.backup_*`) entraron al staging porque el `.gitignore` no los cubría. Un hook que liste archivos staged contra patterns sospechosos lo atrapa.
- Path financiero crítico (`#H-5b`) sin test unitario por 4 semanas. Un check de CI que falle si módulos `dispatcher.py`/`historian.py` bajan de X% cobertura lo previene.

En todos los casos, el manual ya tenía reglas que cubrían el escenario. El problema fue que las reglas dependían del operador recordándolas en cada sesión.

### 15.2 Stack mínimo recomendado

**Pre-commit hooks** (`.pre-commit-config.yaml` en raíz del repo, instalado via `pre-commit install` después del clone):

| Hook | Propósito | Razón |
|---|---|---|
| `gitleaks` o `detect-secrets` | Detectar API keys, tokens, passwords en staged files | Cierra el caso `.env.bak` |
| `check-added-large-files` | Bloquear archivos > 500KB | Cierra el caso DB dumps, ZIPs binarios |
| `check-merge-conflict` | Detectar `<<<<<<< HEAD` huérfanos | Cierra merges mal cerrados |
| `end-of-file-fixer` + `trailing-whitespace` | Normalizar finales de línea/whitespace | Cierra el caso line-endings |
| `ruff` (Python) | Linting + auto-fix | Cierra estilo, imports sin usar, magic numbers detectables |
| `black` (Python) | Formato consistente | Cierra debates de estilo |
| `pytest --collect-only` | Verificar que los tests al menos colectan sin error | Cierra tests rotos por refactor |

**CI básico** (GitHub Actions u otro, archivo `.github/workflows/ci.yml`):

| Check | Propósito |
|---|---|
| Ejecutar suite de tests completa | Bloquear push/merge si rompe |
| Cobertura ≥ piso definido en módulos críticos (§8.6) | Bloquear bajadas de cobertura en paths financieros |
| Audit de archivos sensibles en commits del PR | Doble red ante secretos |
| Lint completo (ruff + black --check) | Asegurar que pre-commit corrió |

### 15.3 Anti-patrón a evitar

"Lo arreglo a mano esta vez, después configuro el hook." En la práctica el hook nunca se configura, y el próximo operador comete el mismo error con peor resultado. Si una regla se viola dos veces, la tercera vez es configurar el enforcement, no escribir más documentación.

### 15.4 Cuándo aplicar enforcement

- **Sí, desde el día uno** si el proyecto va a tener varios contribuidores (incluyendo instancias de IA distintas).
- **Sí, antes de transición a producción** si hay capital real, datos sensibles, o consecuencias regulatorias.
- **Opcional al principio** si es un proyecto experimental personal sin secretos ni paths críticos. Pero documentar la decisión de NO hacerlo.

### 15.5 Implementación es trabajo separado

Esta sección define la spec. **Implementar pre-commit + CI en un proyecto existente es trabajo propio**, no un cambio cosmético. Estimación: 2-3 sesiones de ingeniería:

1. Setup base (`.pre-commit-config.yaml`, instalar tools, primera corrida cleanup).
2. Setup CI (workflow YAML, configurar secrets en GitHub, primera corrida verde).
3. Iteración (ajustar exclusiones, calibrar pisos de cobertura, fixear flakies).

Agendar como ítem de Fase 2 (auditoría) cuando el proyecto entre a esa fase. No bloquear features urgentes por esto.

---

*Manual de Buenas Prácticas — fin del documento. v2.3, 23 de mayo de 2026.*
