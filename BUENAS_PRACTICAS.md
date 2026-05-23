# BUENAS_PRACTICAS.md — Manual de Buenas Prácticas de Desarrollo

**Aplica a:** Todos los proyectos de Roman (Afterlife Capital, Meridian, y futuros)
**Creado:** 5 de mayo de 2026
**Última actualización:** 5 de mayo de 2026

---

## 1. Protocolo de inicio de sesión

Cada vez que se abre un chat nuevo en cualquier proyecto, seguir este orden ANTES de responder o hacer trabajo:

1. **Leer MEMORY.md** — revisar el índice de memorias permanentes para entender qué contexto existe.
2. **Buscar PROJECT_MAP.md** en la raíz del proyecto montado. Si existe, leerlo completo para tener el mapa de estructura, módulos, flujo de datos y convenciones.
3. **Si no existe PROJECT_MAP.md** — informar al usuario y ofrecerse a crearlo antes de cualquier otra cosa.
4. **Leer memorias relevantes** según la tarea que el usuario pida. No leer todas, solo las que apliquen.
5. **Leer restricciones temporales** — si el proyecto tiene un OBSERVATION_PERIOD.md o equivalente, leerlo para saber qué está permitido y qué no.

**Regla de oro:** Nunca preguntar "¿de qué se trata este proyecto?" — la respuesta está en PROJECT_MAP.md y la memoria. Llegar preparado.

---

## 2. PROJECT_MAP.md — Mapa del proyecto

Cada proyecto debe tener un `PROJECT_MAP.md` en la raíz. Este es el documento de orientación rápida que permite entender el proyecto sin leer todo el código.

**Contenido obligatorio:**

- **Estructura de archivos** — árbol con descripción breve de cada archivo/carpeta importante.
- **Módulos y componentes** — qué hace cada módulo, funciones clave, dependencias entre ellos.
- **Flujo de datos principal** — cómo se mueve la información de entrada a salida.
- **Base de datos** — tablas principales, relaciones, si aplica.
- **Infraestructura** — dónde corre, cómo se despliega, servicios externos.
- **Convenciones** — nombrado, estilo de código, idioma de comentarios, etc.
- **Documentos clave** — dónde encontrar blueprint, changelog, backlog, etc.

**Mantenimiento:** Actualizar cada vez que se agreguen módulos, archivos, o cambios estructurales significativos.

---

## 3. Protocolo de proyecto nuevo

Cuando se arranca un proyecto desde cero:

### 3.1 Estructura del código

Seguir las convenciones del ecosistema del stack elegido (Python, Node, React, etc.). No forzar estructuras genéricas — cada ecosistema tiene sus propias convenciones y se respetan.

### 3.2 Archivos de gestión estándar

Estos aplican a CUALQUIER proyecto, sin importar el stack:

| Archivo | Propósito |
|---|---|
| `PROJECT_MAP.md` | Estructura, módulos, flujo de datos, convenciones |
| `CHANGELOG.md` | Historial de cambios del proyecto |
| `.gitignore` | Apropiado para el stack |
| `backups/` | Carpeta para backups catalogados |

### 3.3 Documentar desde el día uno

No esperar a que el proyecto crezca para organizarlo. La documentación arranca con el primer archivo de código.

---

## 4. Backups

### 4.1 Regla general

Antes de modificar cualquier archivo, hacer backup primero.

**Formato:** `archivo.ext.bak.YYYYMMDD_HHMMSS`

**Ejemplo:** `api.py.bak.20260505_143200`

### 4.2 Frecuencia

- Hacer backup ANTES de cada sesión de edición.
- Si un archivo se edita múltiples veces en una sesión, hacer backup antes de cada ronda de cambios significativos.
- No solo una vez al día.

### 4.3 Organización

- Cuando se acumulen backups, organizarlos en `backups/` con un `README.md` que catalogue las versiones.
- Ejemplo: `backups/20260505/api.py.bak` con nota de qué cambió.

### 4.4 Precaución con archivos grandes

El Edit tool de Cowork tiene un bug conocido que trunca archivos grandes (>500 líneas). Para estos archivos, preferir ediciones vía Python/bash en lugar del Edit tool directo.

---

## 5. Control de cambios

### 5.1 CHANGELOG.md

Cada proyecto lleva un `CHANGELOG.md` general con historial de cambios significativos.

### 5.2 CHANGELOG-UI.md (para proyectos con interfaz)

Si el proyecto tiene dashboard o interfaz visual, llevar un `CHANGELOG-UI.md` separado con:

- **Qué se cambió** — componente, sección, o elemento afectado.
- **En qué archivo** — ruta exacta.
- **Por qué** — razón del cambio.
- **Impacto visual** — qué ve diferente el usuario.

### 5.3 Sincronización con Claude Design

Cuando el diseño del proyecto se trabaja en Claude Design (o cualquier herramienta de diseño separada):

- **CHANGELOG-UI.md es el puente** entre el código y el diseño. Claude Design debe recibir este archivo para conocer el estado actual antes de proponer o hacer modificaciones visuales.
- **Cambios hechos por código** que afecten la interfaz deben registrarse en CHANGELOG-UI.md para que Claude Design no trabaje sobre un estado desactualizado.
- **Cambios hechos desde Claude Design** también deben registrarse en CHANGELOG-UI.md, indicando que el origen fue diseño, no código. Esto permite que al volver a trabajar en código se sepa qué cambió visualmente.
- **Flujo bidireccional:** Código → CHANGELOG-UI.md → Claude Design → CHANGELOG-UI.md → Código. El changelog es la fuente de verdad de qué cambió en la interfaz, sin importar desde dónde se hizo.

### 5.4 Cache-bust

Al modificar archivos JS o CSS del dashboard:

- Actualizar el query param `?v=` en los `<script>` y `<link>` tags de `index.html`.
- Formato: `YYYYMMDD` + letra incremental (ej: `?v=20260505a`, luego `?v=20260505b`).
- Esto fuerza que el navegador recargue el archivo en vez de usar caché.

---

## 6. Line endings (CRLF / LF)

### 6.1 Regla

Los archivos del dashboard (HTML, JS, CSS) usan line endings Windows (CRLF). Los archivos Python y de configuración usan LF.

### 6.2 Cómo aplicar

- Usar scripts Python para editar archivos del dashboard y preservar los line endings originales.
- Nunca usar el Edit tool directo en archivos del dashboard — puede cambiar CRLF a LF y romper diffs o causar problemas en Git.

---

## 7. Idioma

### 7.1 Contenido generado

Todo el contenido generado debe estar en español: respuestas, comentarios en código, logs visibles al usuario, texto de interfaz, emails, documentación.

### 7.2 Excepciones

- **Nombres de variables y funciones** — en inglés (convención de programación).
- **Términos técnicos sin traducción** — "slippage", "drawdown", "callback", "middleware", etc.
- **Nombres propios** — APIs, librerías, servicios.
- **Código** — la sintaxis y estructura del código es en inglés por naturaleza.

---

## 8. Períodos de observación / congelamiento

Cuando un proyecto tiene un período de observación activo:

### 8.1 Documentación

Crear un `OBSERVATION_PERIOD.md` en la raíz del proyecto que defina:

- Fecha de inicio y fin.
- Estado del sistema al inicio (configuración congelada).
- Qué está PERMITIDO (bug fixes críticos, documentación, observabilidad read-only, cosmética).
- Qué NO está permitido (cambios de lógica, thresholds, parámetros, features nuevos).
- Proceso de excepciones documentables.
- Plan de revisión al cierre.

### 8.2 Verificación obligatoria

ANTES de hacer cualquier cambio o dar opinión sobre qué está permitido, LEER el documento de observación. Nunca responder de memoria — verificar primero, hablar después.

### 8.3 Disciplina

- Las ideas nuevas se anotan en `NEXT_ITERATION.md` y se implementan DESPUÉS del período.
- Números mediocres son INFORMACIÓN, no problemas a corregir.
- Solo se actúa ante fallas estructurales verificables, no ante resultados temporales.

---

## 9. Lecciones anti-error (de la industria)

Principios derivados de la investigación comparativa con casos reales:

1. **No hacer overfitting** — si una estrategia falla en prueba, evaluarla honestamente, NO ajustarla para que funcione sobre datos pasados.
2. **No dejar código muerto en producción** — revisar deuda técnica periódicamente por riesgo catastrófico, no solo por severidad.
3. **No confiar en alertas que nadie lee** — las alertas críticas deben ir por un canal separado (SMS, push, Telegram), no perderse en el inbox.
4. **No confundir correlación histórica con protección real** — las correlaciones se disparan en crisis precisamente cuando más necesitas decorrelación.
5. **No mover dinero real antes de que el sistema lo merezca** — respetar las gates del plan ejecutivo.
6. **Tener runbook de incidentes ANTES de necesitarlo** — bajo presión, la decisión intuitiva puede ser la más peligrosa.
7. **Distinguir "estrategia rota" de "estrategia en régimen equivocado"** — antes de matar algo, verificar si el contexto explica el resultado.

---

## 10. Archivos de gestión por tipo de proyecto

### 10.1 Cualquier proyecto

| Archivo | Obligatorio | Propósito |
|---|---|---|
| `PROJECT_MAP.md` | Sí | Mapa de estructura y orientación rápida |
| `CHANGELOG.md` | Sí | Historial de cambios |
| `.gitignore` | Sí | Exclusiones de Git para el stack |
| `backups/` | Sí | Backups catalogados |

### 10.2 Proyectos con interfaz visual

| Archivo | Obligatorio | Propósito |
|---|---|---|
| `CHANGELOG-UI.md` | Sí | Registro de cambios visuales, puente con Claude Design |

### 10.3 Proyectos con período de validación

| Archivo | Obligatorio | Propósito |
|---|---|---|
| `OBSERVATION_PERIOD.md` | Sí | Reglas de congelamiento y plan de revisión |
| `NEXT_ITERATION.md` | Recomendado | Ideas y mejoras para después del período |

### 10.4 Proyectos de trading / sistemas críticos

| Archivo | Obligatorio | Propósito |
|---|---|---|
| `INCIDENT_PLAYBOOK.md` | Sí | Secuencia de respuesta a incidentes |
| `BLUEPRINT_AS_BUILT.md` | Recomendado | Arquitectura documentada tal como está construida |
| `RATIONALE.md` | Recomendado | Razones detrás de cada decisión/parámetro |

---

## 11. Memoria permanente

### 11.1 Tipos de memoria

- **user** — perfil del usuario, preferencias, conocimientos.
- **feedback** — correcciones y validaciones de enfoque de trabajo.
- **project** — estado de proyectos, bugs, decisiones, plazos.
- **reference** — dónde encontrar información en sistemas externos.

### 11.2 Qué NO guardar en memoria

- Patrones de código o arquitectura (se derivan del código actual).
- Historial de Git (se consulta con `git log`).
- Soluciones a bugs (el fix está en el código, el contexto en el commit).
- Detalles efímeros de la tarea actual (usar tareas, no memoria).

### 11.3 Mantenimiento

- No duplicar memorias — buscar si ya existe una antes de crear otra.
- Actualizar o eliminar memorias obsoletas.
- Convertir fechas relativas a absolutas al guardar.

---

## 12. Comunicación con Claude

### 12.1 No re-explicar

Claude debe llegar preparado a cada sesión. Si hay PROJECT_MAP.md y memorias, no hacer preguntas básicas sobre el proyecto.

### 12.2 No tocar CLAUDE.md

El archivo `CLAUDE.md` en la raíz del código del bot lo mantiene Claude Code. Cowork no lo modifica — se lee para contexto pero se usa la memoria permanente propia.

### 12.3 Verificar antes de opinar

Antes de decir si algo está permitido o no (especialmente durante períodos de observación), leer el documento fuente. No responder de memoria.

---

*Este manual se actualiza conforme se identifiquen nuevas prácticas o se refinen las existentes.*
