# Protocolo de Inicio de Sesión

**Versión:** 1.0  
**Fecha:** 7 de mayo de 2026  
**Alcance:** Universal — aplica a todos los proyectos que usen asistencia IA.

---

## Por qué existe este documento

Los proyectos crecen en complejidad con el tiempo. Cada chat nuevo empieza con cero contexto, y sin un protocolo estructurado se pierden varios mensajes de ida y vuelta antes de que la IA tenga una imagen completa del proyecto. Esos mensajes desperdiciados cuestan tokens, tiempo, y paciencia.

Este protocolo estandariza cómo se abre una sesión de trabajo para que desde el primer mensaje productivo la IA ya tenga el contexto necesario para operar con criterio.

---

## Paso 1 — Lectura de contexto (silenciosa, sin output al usuario)

La IA ejecuta estas lecturas al inicio de toda sesión, sin narrar lo que está haciendo:

1. **CLAUDE.md** — Estado del proyecto, decisiones activas, stack, archivos clave.
2. **PROJECT_MAP.md** — Estructura completa del proyecto, flujos de datos, dependencias.
3. **Memorias relevantes** — MEMORY.md + archivos de memoria que apliquen al proyecto.
4. **Restricciones temporales** — Períodos de observación, freezes, deadlines documentados (ej: OBSERVATION_PERIOD.md).
5. **BUENAS_PRACTICAS.md** — Si el proyecto referencia un manual de prácticas, leerlo antes de escribir código.

Si alguno de estos archivos no existe, la IA lo nota internamente pero no interrumpe al usuario con preguntas sobre eso — a menos que sea crítico para la tarea.

---

## Paso 2 — Evaluación del estado

Antes de responder o actuar, la IA evalúa silenciosamente:

- **¿Hay trabajo en progreso de sesiones anteriores?** Revisar si hay tareas pendientes, bugs conocidos, o continuaciones documentadas en CLAUDE.md o memorias.
- **¿Hay restricciones activas?** Períodos de observación, freezes de código, dependencias bloqueantes.
- **¿El proyecto tiene deuda técnica relevante?** Issues conocidos que podrían afectar lo que el usuario pida.

Esto no se comunica al usuario como un reporte — se usa como contexto para dar respuestas informadas.

---

## Paso 3 — Respuesta al usuario

Con el contexto cargado, la IA responde al primer mensaje del usuario aplicando estas reglas:

1. **No repetir lo que ya sabe.** Si el usuario pide algo que está documentado en CLAUDE.md, no pedirle que explique el proyecto.
2. **Preguntar lo que no está documentado.** Si la tarea es ambigua o tiene múltiples interpretaciones, clarificar antes de actuar.
3. **Alertar sobre conflictos.** Si lo que pide el usuario choca con una restricción activa (ej: cambiar un threshold durante un período de observación), mencionarlo proactivamente.
4. **Proponer, no asumir.** Para cambios significativos, proponer el enfoque y esperar confirmación. Para tareas menores, ejecutar directamente.

---

## Qué debe contener CLAUDE.md para que esto funcione

El protocolo depende de que CLAUDE.md esté actualizado. Mínimo debe incluir:

| Sección | Contenido | Ejemplo |
|---|---|---|
| Qué es el proyecto | 2-3 líneas de descripción | "Bot de trading multi-agente con 9 estrategias, paper trading en Alpaca" |
| Stack | Lenguajes, frameworks, DB | "Python 3.14, FastAPI, PostgreSQL, asyncpg, LangGraph" |
| Estado actual | Qué funciona, qué no, qué está en progreso | "9 Sentinels operativos, período de observación hasta 27/05" |
| Archivos clave | Tabla archivo → propósito | "historian.py → persistencia y feedback loop" |
| Decisiones vigentes | Con el "por qué" | "Régimen fijo NEUTRAL porque no hay suficientes trades para calibrar S-10" |
| Restricciones | Bloqueos, freezes, períodos | "No modificar thresholds hasta 27/05 (ver OBSERVATION_PERIOD.md)" |
| Problemas conocidos | Bugs abiertos, deuda técnica | "Dashboard: KPI de slippage muestra '—' porque no se calcula aún" |

**CLAUDE.md se actualiza al final de cada sesión de trabajo.** Si no se actualiza, la próxima sesión arranca con contexto obsoleto y el protocolo pierde eficacia.

---

## Qué debe contener PROJECT_MAP.md

Orientación estructural del proyecto:

- Estructura de archivos con descripción de cada uno.
- Flujos de datos principales.
- Base de datos (tablas y relaciones).
- Endpoints de API (si aplica).
- Dependencias externas.
- Cómo arrancar el proyecto.

A diferencia de CLAUDE.md (que cambia frecuentemente), PROJECT_MAP.md es más estable y solo se actualiza cuando se agregan o eliminan archivos o cambia la arquitectura.

---

## Cuándo actualizar este protocolo

- Cuando se identifique que la IA sigue perdiendo contexto a pesar del protocolo.
- Cuando se agregue un nuevo tipo de archivo de contexto al ecosistema de proyectos.
- Cuando la complejidad de un proyecto requiera pasos adicionales.

---

## Referencia cruzada

- **BUENAS_PRACTICAS.md** sección 11 — Flujo de Trabajo con IA (reglas complementarias).
- **CLAUDE.md** — Archivo de contexto por proyecto.
- **PROJECT_MAP.md** — Mapa estructural por proyecto.
- **MEMORY.md** — Índice de memorias persistentes entre sesiones.

---

*Documento creado el 7 de mayo de 2026. Versión 1.0.*
