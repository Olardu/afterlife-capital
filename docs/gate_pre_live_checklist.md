# Gate Pre-Live Checklist — Sentinel Fase 5

> **Lista binaria de validaciones OBLIGATORIAS** antes de transición a Fase 5 live (dinero real). Sin TODOS los checkboxes marcados ✓, NO se procede a live.

**Cierra:** #FASE2-NEW-5 del BACKLOG.

**Mantenedores:** Roman (decisión final Go/No-Go) · Cowork (Roma — coordina evaluación) · Code (provee evidencia técnica).

**Última actualización:** 2026-05-25.

---

## Cómo se usa este gate

1. **Sesión dedicada Roman + Cowork + Code** cuando se evalúe transición a live (no de pasada).
2. **Cada item es binario:** ✓ cumplido / ✗ no cumplido / N/A (con justificación escrita).
3. **Si fallan items críticos** (secciones 1-4 + 7), retroceso obligatorio a período de observación adicional.
4. **Documento de "Go/No-Go" firmado por Roman** antes del primer dólar real.

---

## §1 — Tests y cobertura

- [ ] Suite completa pasa 100% (X/X tests, número documentado).
- [ ] Cobertura módulos críticos ≥95% verificada por CI (`--cov-fail-under=95`).
- [ ] CI workflow funcionando: `test` + `lint` + `secrets` + `coverage` todos verdes en último push a main.
- [ ] Pre-commit hooks activos (`gitleaks`, `ruff`, `check-added-large-files`, etc.).
- [ ] No hay regresiones en suite respecto al último cierre de período de observación.
- [ ] Tests TDD demostrados rojo→verde para cada bug financiero histórico (#H-1, #H-2, #H-4, #H-5b, #H-6).

## §2 — Bugs financieros críticos cerrados

- [ ] #H-1 a #H-6 todos en `Archivo DONE` del BACKLOG con commit hash.
- [ ] #H-4 Decimal completo en pipeline monetario (correlation_guard + historian + dispatcher + reconciler).
- [ ] #H-5b cache pop tras SELL filled validado en producción ≥30 días sin "Posiciones fantasma".
- [ ] #H-6b auto-reconcile CANCELLED/PENDING_NEW funcionando.
- [ ] EXP-001 Sharpe per-trade B.2 (no anualizado) en producción ≥30 días sin valores absurdos (|Sharpe|>5).
- [ ] EXP-002 Decay PF+RTD funcionando — al menos 1 rotación validada como "rescued_by_pf_rtd" o "decayed_correctamente".
- [ ] EXP-003 CorrelationGuard persistiendo en `signals` (queries §6 del balance ejecutables).

## §3 — Gestión de riesgo activa

- [ ] #GR-1 Bracket orders ATR-based con SL/TP automáticos activo (`ATR_SIZING_ENABLED=true`).
- [ ] #GR-2 Position sizing por ATR (risk parity) activo.
- [ ] #GR-3 Drawdown limits portfolio activo (`PORTFOLIO_DD_LIMITS_ENABLED=true`).
- [ ] #GR-4 Cap 85% `MAX_ALLOCATION_TOTAL` respetado (verificable en dispatcher.allocate_capital).
- [ ] CorrelationGuard threshold `0.75` calibrado con evidencia del período 2 (ajustado si necesario).
- [ ] Cap absoluto `MAX_CAPITAL_PER_SENTINEL = 25%` respetado.
- [ ] Half-Kelly (`KELLY_FRACTION = 0.5`) confirmado en producción.

## §4 — Observabilidad y monitoreo

- [ ] #OP-1 Backup DB automático diario funcionando + restore validation ejecutado al menos 1 vez.
- [ ] #OP-2 Heartbeat externo (healthchecks.io) activo + alerta email/SMS configurada + probada (simular caída del bot).
- [ ] #OP-3 Modo degraded ante caídas APIs externas (Alpaca, NewsAPI, Claude API) implementado.
- [ ] Logs con rotación adecuada (`TimedRotatingFileHandler` diario, no llenan disco).
- [ ] Dashboard accesible y funcional (Cloudflare tunnel o equivalente).
- [ ] `/api/healthz` dedicado para load balancers o monitoring externo (#TD-10).
- [ ] Métricas críticas en dashboard: equity curve, drawdown actual, posiciones abiertas, slippage promedio.

## §5 — Slippage y costos realistas

- [ ] #ME-1 Slippage tracking activo (`trades.slippage` poblado por trade).
- [ ] #CR-3 Fees realistas simulados en métricas paper (SEC, FINRA TAF, exchange fees) para que `Sharpe_paper × (1 - slippage_factor)` ≈ `Sharpe_live esperado`.
- [ ] #ME-4 Costo Claude API tracked per Sentinel (visible en dashboard).
- [ ] Análisis post-período: comparación slippage paper vs live esperado documentado.

## §6 — Compliance legal/fiscal (si entra capital de terceros)

> **Aplica si hay socios MEMBER aportando capital.** Si Fase 5 arranca solo con capital de Roman, varias secciones quedan N/A.

- [ ] **LLC Wyoming constituida** + EIN + Articles of Organization registrados (#OPS-005).
- [ ] Cuenta Alpaca de **entity** (no personal) configurada y financiada.
- [ ] **Operating Agreement firmado** por todos los socios.
- [ ] **Securities exemption identificada** (Section 4(a)(2) para friends and family, o Reg D 506(b) si formaliza más).
- [ ] **Operating Agreement revisado por abogado de securities** (~$500-1500, una vez).
- [ ] **Blue Sky compliance** en estados de cada socio verificado (si socios en múltiples estados).
- [ ] **Form D filing** en SEC si va por Reg D 506(b).
- [ ] #CR-1 Pipeline de reportes fiscales implementado (1099 o K-1 según estructura).
- [ ] #CR-2 Manejo correcto de splits y dividendos verificado en historian.
- [ ] Bookkeeping software / hoja de cálculo de fund accounting (`members` + `capital_movements` tablas).

## §7 — Performance del período de observación

- [ ] Mínimo **30 días paper consistentes con código frozen** (sin cambios mid-período, lección AQR).
- [ ] **Sharpe portfolio anualizado > 0.5** (mínimo razonable retail).
- [ ] **Max drawdown < 10%** durante el período.
- [ ] **Win rate consistente con hipótesis** de cada Sentinel (no muy desviado de lo esperado).
- [ ] **Universe Selector funcionando** sin productos exóticos no autorizados (lista negra `_BLACKLIST` efectiva).
- [ ] **The Ear con al menos 1 acción** durante el período (al menos 1 evento macro vetó correctamente — sino, el componente no se validó realmente).
- [ ] **CorrelationGuard reduciendo ≥10% de señales** (sino, threshold demasiado laxo o no hay correlaciones reales).
- [ ] **Shadow fractional capturó datos** (EXP-005, decisión sobre #FEAT-001 informada por evidencia).
- [ ] **Comparación QuantStats vs SPY** del período documentada y archivada.

## §8 — Validación matemática y técnica

- [ ] **#TD-26 Validación Half-Kelly** completada (por quant externo o auditoría IAs independientes #OPS-006).
- [ ] **Code review externo** completado (auditoría IAs si se contrata) — 3 perfiles: código, matemáticas, investigación.
- [ ] **Smoke tests contra Alpaca paper** documentados para cada flow crítico (entrada/salida orden, bracket, reconciliación, kill switch).

## §9 — Operacionales pre-arranque

- [ ] **Restart procedure documentado** en `INCIDENT_PLAYBOOK.md` (cómo parar y arrancar el bot sin perder estado).
- [ ] **Kill switch testeado** y funcionando en producción al menos 1 vez (simulado).
- [ ] **Reconciliación post-restart verificada** (Alpaca ↔ DB local sin desincronización).
- [ ] **Procedimiento de rollback** documentado para caso de bug post-arranque.
- [ ] **Email/notificación a viewers/socios** sobre arranque coordinado.
- [ ] **Capital mínimo definido** ($X exacto) y disponible en cuenta target el día del arranque.
- [ ] **Plan de monitoreo intensivo primer semana** (cuánto tiempo dedica Roman a watching, cuándo se relaja).

## §10 — Cierre formal y firma

- [ ] **Documento "Go/No-Go" firmado por Roman** con todos los items anteriores en ✓.
- [ ] **Fecha exacta de arranque** definida (no "cuando esté listo" — fecha calendario).
- [ ] **Plan B documentado** si algo sale mal en las primeras 48 horas (apagar bot, volver a paper).
- [ ] **Roman compromete tiempo dedicado** la primera semana (no fin de semana intensivo, monitoreo continuo).

---

## Estados especiales del gate

### N/A (No aplica) — justificación obligatoria

Algunos items pueden no aplicar al caso particular (ej. compliance LLC si el primer arranque es solo con capital de Roman). En esos casos:
- Marcar `N/A`.
- Agregar justificación escrita debajo del item.
- Documentar cuándo dejaría de ser N/A (ej. "N/A hasta que entre el primer socio MEMBER").

### Diferimiento condicional

Si un item importante (ej. auditoría IAs) está en progreso pero no terminado:
- Marcar `⏳ EN CURSO`.
- Documentar fecha esperada de cierre.
- Roman decide si arranca con item en curso o espera.

---

## Reglas del gate

1. **Auto-reflection del operador:** si Roman piensa "esto está OK aunque falte X", X probablemente importa más de lo que parece. Atender al impulso de saltarse items.
2. **Sin TODOS los checkboxes marcados ✓ o N/A justificado, NO live.**
3. **Si fallan items críticos** (secciones 1-4 y 7), retroceso a período de observación adicional sin debate.
4. **Si pasaron >30 días desde último cierre del gate** sin arrancar live, re-evaluar el gate completo (las condiciones cambian).
5. **El gate se re-evalúa después de cada cierre de período de observación** (no solo al primer intento).

---

## Referencias cruzadas

- `BACKLOG.md` — sección "Archivo DONE" para verificar commits de items cerrados.
- `OBSERVATION_PERIOD.md` — restricciones del período de observación previo.
- `INCIDENT_PLAYBOOK.md` — procedimientos de emergencia.
- `RATIONALE.md` — justificación de parámetros congelados.
- `EXPERIMENTS.md` — criterios de éxito de experimentos pre-registrados.
- `BUENAS_PRACTICAS_V2.md §14` — checklist técnico post-edit (gate menor por commit).
- `BUENAS_PRACTICAS_V2.md §8.6` — política de tests para paths financieros críticos.

---

*Gate Pre-Live Checklist armado por Cowork el 2026-05-25 como #FASE2-NEW-5. Inspirado en investigación de posicionamiento (lección Knight Capital 2012, AQR risk parity docs). Se actualiza cuando se identifique gap nuevo durante operación real.*
