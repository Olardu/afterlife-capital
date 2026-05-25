# Sentinel v0.5

Sistema de trading algorítmico multi-agente. 9 estrategias autónomas (Sentinels) coordinadas por un Dispatcher, con protecciones macro, gestión de capital Half-Kelly y persistencia en PostgreSQL. Operación en paper trading hasta validar.

## Estado al 2026-05-25 — T-V COMPLETO (3/3) + #TECH-004 + #BUG-002. `origin/main`=`31f0304`, HEAD `a5db770` (ahead 20), suite 658/658

**Turno post-T-U: 4 ítems cerrados** (A confirmación FinBERT, B #TECH-004, C T-V 3/3, D #BUG-002). 4 commits LOCALES, sin migración nueva. Suite 636→**658**. Pendiente: validación Cowork.

**#TECH-004** (`c6ea32d`): fixture autouse `_atr_sizing_off` (patch `config.ATR_SIZING_ENABLED=False`) en `test_dispatcher_coverage`/`_decimal`/`shadow_fractional` — los tests heredaban el `.env` (ATR=true de Roman) y entraban al path ATR real → ValueError. Suite 636/636 heredando .env. CI sin .env ya pasaba.

**T-V — 3 cambios de comportamiento, todos flag-gated default OFF:**
- `571f30c` **#TECH-003 FIFO** (cierra #TD-1): `calculate_performance` usa `tax_lots.match_fifo` (no `zip(buys,sells)`). Sin flag (fix bug). **Parity-check DB real: 0/25 pares con diferencia** (período 1 fue qty=1 alternado; el motor queda correcto para fills parciales/sizing real). SQL agrega qty. Tests existentes: rows con qty + `created_at` datetime (match_fifo calcula holding_days).
- `b1bf88b` **#FEAT-014 Cooldown post-loss**: bloquea BUY si hubo cierre con pérdida (FIFO) en el ticker dentro de `COOLDOWN_POST_LOSS_DAYS`=7. Flag `COOLDOWN_POST_LOSS_ENABLED` (default OFF). `historian.get_last_loss_on_ticker` (read-only). Chequeo en `process_signal` tras duplicate_ticker_buy, **fail-open**. NO persiste el descarte (no hay columna rejection_reason).
- `a5db770` **Wilder RSI**: `_rsi()` usa Wilder (RMA = `ewm(alpha=1/period)`, = pandas_ta/_atr) con flag `WILDER_RSI_ENABLED` (default OFF). Cambia señales S-2/S-8. Validado vs RMA manual ε=0.001. Doc en RATIONALE.md.

**#BUG-002 (17 signals huérfanas 27-abr) — RESUELTO, no es bug.** El 27-abr es el ÚNICO día con huérfanas (todas las 17); el primer trade de la DB es del 28-abr → el primer día de mercado el Dispatcher (pre-fixes) no ejecutó. 28-abr en adelante: 0 huérfanas. Recomendado a Cowork: cerrar como artefacto histórico.

**Flags nuevos (Roman activa en .env + restart si quiere):** `COOLDOWN_POST_LOSS_ENABLED`, `WILDER_RSI_ENABLED` (ambos default OFF). #TECH-003 FIFO sin flag (ya activo, no cambia scores actuales por el parity-check).

## Estado al 2026-05-25 — T-U distilFinBERT COMPLETO (6/6). The Ear con sentiment. `origin/main`=`31f0304`, HEAD `e934338` (ahead 16), suite 636/636

**T-U #FEAT-007 — Sentiment analysis FinBERT en The Ear — COMPLETO (6/6).** 6 commits LOCALES, migración **018 APLICADA**. Pendiente: validación Cowork.
- `1005c83` chore(deps): `torch==2.9.1+cpu` + `transformers==5.9.0` (CPU, índice PyTorch) en requirements.txt + README.
- `769a6d6` feat(sentiment): `sentiment_analyzer.py` PURO — `SentimentAnalyzer` (lazy load `ProsusAI/finbert`, `score()→[-1,1]`, `batch_score` con fallback per-item, defensivo→None). 15 tests TDD (pipeline mockeado), módulo **100%**.
- `0670ecc` feat(db): migración **018** `macro_events += sentiment_score_finbert NUMERIC(6,4) + sentiment_method VARCHAR(20)`. DDL idempotente inline en `historian.connect()` + `db/018`. `record_macro_event` persiste ambos (defaults backward-compat).
- `a669a80` feat(the_ear): integración **DIP** (analyzer inyectado, no importa el módulo) + flags `THE_EAR_SENTIMENT_ENABLED` (default false) / `THE_EAR_FINBERT_VETO_THRESHOLD` (-0.6) + **hybrid mode** + `_compute_finbert_score`. 10 tests, the_ear **100%**.
- `c3f4423` feat(main): wire-up flag-gated (construye analyzer e inyecta si flag on; lazy load; fallback a keyword). +1 test, main **100%**.
- `e934338` docs(finbert): `docs/finbert_recalibration_plan.md` (nuevo) + secciones en `RATIONALE.md` + `INCIDENT_PLAYBOOK.md`.
- Suite 610→**636** (+26 TDD). Gate CI **99.84%** exit 0. ruff verde. validate-workspace **0/0**. Smoke real: beats+guidance +0.905, crash -0.934.

**Diseño (hybrid mode):** con el flag on, el `risk_score` [0,1] lo SIGUE dando el keyword matching (semántica intacta para decay/dashboard/veto). FinBERT calcula el sentiment promedio [-1,1] de TODOS los titulares, lo persiste, y agrega un **veto extra** si `< umbral`. `sentiment_method` = `keyword` (off/no disponible) | `hybrid`. Si el modelo no carga → fallback automático a keyword (no rompe el bot).

**Drifts (forzados por Python 3.14, doc en LOG):** (1) torch 2.9.1/transformers 5.9.0 (la spec pedía 2.5.0/4.45.0, sin wheels cp314). (2) modelo `ProsusAI/finbert` (no `yiyanghkust/finbert-tone`, que no carga en transformers 5.x). (3) `finbert` puro (FinBERT como fuente primaria del risk_score) = post-calibración; v1 es hybrid.

**⚠️ Gotcha tests/.env:** el `.env` local tiene `ATR_SIZING_ENABLED=true` (Roman, para el martes) → 24 tests de dispatcher/shadow fallan LOCALMENTE (asumen ATR=false, entran al path real de Alpaca sin mock). **Con `ATR_SIZING_ENABLED=false` → 636/636.** El CI (ubuntu sin .env) pasa verde. Es techdebt de tests (deberían parchear el flag), NO de T-U.

**Pendiente Roman (martes, activar FinBERT):** `pip install -r requirements.txt` + pre-descargar modelo (`python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='ProsusAI/finbert')"`) + `THE_EAR_SENTIMENT_ENABLED=true` en .env + restart.

## Estado al 2026-05-25 — T-T CERRADO COMPLETO (3/3). Sub-3 Equity Research integrado. `origin/main`=`31f0304`, HEAD `78823da` (ahead 10), suite 610/610

**T-T Bloque E COMPLETO (Sub-1 #HE-2 ✅ + Sub-2 #HE-4 ✅ + Sub-3 ✅).** Sub-3 cierra T-T entero. Pendiente: validación Cowork.

**T-T Sub-3 — Integración Equity Research al system prompt del Universe Selector — COMPLETO.** 1 commit LOCAL `78823da`, **SIN migración** (reasoning expandido se persiste concatenado en `rotation_decisions.claude_reasoning` TEXT — mismo patrón que `factor_exposure_analysis`):
- **SYSTEM_PROMPT:** nueva sección **"## Análisis fundamental (Equity Research)"** (entre marco factorial All Weather y restricciones operativas). Instruye a Claude a evaluar calidad/riesgo fundamental como **filtro de corto plazo** (NO tesis de valor de largo plazo): salud financiera (señales 10-K/10-Q), valuación relativa (P/E, EV/EBITDA, P/S vs comparables), riesgo de evento (earnings/guidance = gap risk). **Distingue acciones individuales (fundamentales) de ETFs/commodities (composición/expense ratio/liquidez, NO DCF)** para evitar overreach. Salvaguarda de honestidad: si no hay datos confiables o es ETF, decirlo en vez de inventar.
- **Campo `fundamental_analysis`** (opcional) en `_RESPONSE_SCHEMA` + ejemplo JSON + instrucción en `build_user_prompt`. Se concatena al `claude_reasoning` (`[Fundamental analysis]\n...`) antes de `save_rotation_decision`.
- **8 tests TDD** (`tests/test_universe_selector_equity_research.py`). Suite 602→**610**. `universe_selector.py` **100%**, gate CI **99.84%** (exit 0), ruff verde, validate-workspace **0/0**.
- **DRIFT/DECISIÓN documentada:** el bot llama a Claude vía API **SIN tool use/MCP** en el call de rotación. "Integrar Equity Research" = instruir el FRAMEWORK fundamental con el conocimiento de Claude, NO ejecutar las skills `equity-research:*`/MCP en vivo (esas viven en el Code de Claude, no en el runtime). Análisis fundamental con datos EN VIVO (10-Ks reales, DCF computado) = follow-up **Sub-3b** (requiere dar tool use/MCP al `claude_client`) — propuesto a backlog, no hecho.
- **Sin flag nuevo:** la guía fundamental está siempre activa en el prompt; no cambia las órdenes del bot (solo enriquece el reasoning que pide/persiste). Flags del restart del martes sin cambios.

## Estado al 2026-05-25 — T-T Sub-1 #HE-2 Investment Thesis Tracking COMPLETO. `origin/main`=`31f0304`, HEAD `9c8893a` (ahead 8), suite 602/602

**#HE-2 Investment Thesis Tracking — COMPLETO** (core). 3 commits LOCALES + migración **017 APLICADA**. Tracking estructurado de las tesis de inversión del bot: cada rotación del Universe Selector nace como tesis con state machine, y el historial cerrado realimenta el system prompt (#ME-2). FLAG-GATED (`THESIS_TRACKING_ENABLED`, default False) — Roman lo activa como **5º flag del restart del martes**. NO toca el hot-path del dispatcher; vive en el flujo de rotación (ya error-isolado + bajo timeout). El enganche es observabilidad enriquecida: registra metadata + alimenta el prompt; no altera las órdenes salvo el feedback loop (el objetivo).
- `7573747` `investment_thesis.py` PURO (sin DB/red, 100% cobertura §8.6, 26 tests TDD): state machine `IDEA→ENTRY_READY→ACTIVE→CLOSED` (`VALID_TRANSITIONS` + `can/validate_transition`; descarte temprano IDEA/ENTRY_READY→CLOSED) · `compute_excursions` MAE/MFE LONG/SHORT desde barras OHLC ({high,low} o {close}/{price}), Decimal, clamp ≥0, % vs entry, entrada inválida→0.0 (seguro) · `compute_outcome` (win/loss/breakeven) · `summarize_theses` + `build_feedback_block`. Calcado de tax_lots/corporate_actions (DIP).
- `a884c8a` migración **017** `investment_theses` (CREATE TABLE + 5 índices, verificado en information_schema: 26 cols, CHECK direction/state; FK a sentinels/users/rotation_decisions). DDL idempotente inline en `historian.connect()` (patrón 011/013/014/015/016) + `db/017`. historian §7.5: `save_investment_thesis` (nace IDEA) · `update_thesis_state` (transición validada con el módulo puro dentro de la tx SELECT FOR UPDATE; SET dinámico sobre allowlist; transición inválida→False sin lanzar) · `find_open_thesis` · `get_closed_theses_feedback` · `_serialize_thesis`. 14 tests.
- `9c8893a` flag `THESIS_TRACKING_ENABLED` + `THESIS_FEEDBACK_LIMIT` (config) + enganche universe_selector: rotación propuesta→tesis IDEA; rotación ejecutada→nueva IDEA→ENTRY_READY + cierra tesis del ticker saliente; feedback loop al prompt (`build_user_prompt(thesis_feedback=...)`). `_thesis_direction` (SHORT para rsi_short/rsi_divergence). Flag-gated + try/except (nunca aborta la rotación). 14 tests.
- Suite 548→**602** (+54 TDD). Gate CI cobertura **99.84%** (exit 0): historian/universe_selector/investment_thesis/dispatcher/main/the_ear/etc. **100%**. ruff verde. validate-workspace **0/0**.
- **Decisión de alcance (consultada a Roman):** las funcionalidades nuevas ENTRAN A OPERAR desde el martes (a diferencia del fraccionamiento, en sombras). Por eso enganche al runtime real, flag-gated para reversibilidad.
- **Pendiente #HE-2b (follow-up documentado, NO en este sprint):** transición ENTRY_READY→ACTIVE al primer fill (captura `entry_price`/`entry_at` — requiere hook en dispatcher, hot-path financiero) + backfill de MAE/MFE y outcome fino sobre tesis cerradas (requiere fetch de barras Alpaca sobre el holding, reusando `backtest/data.py`). Hoy el cierre setea outcome coarse desde el win_rate; el calculador MAE/MFE ya existe y está testeado, falta solo alimentarlo con barras reales.

**Pendiente T-T:** Sub-3 Equity Research integración al system prompt del Universe Selector (plugin instalado ✅, NO bloqueado).

## Estado al 2026-05-25 — T-T Sub-2 #HE-4 backtesting COMPLETO. `origin/main`=`31f0304`, ahead 5 (`d21966f`..`b24ccfb`), suite 548/548

**#HE-4 Framework de backtesting — COMPLETO** (paquete `backtest/`, 4 commits feat + 1 docs LOCALES, SIN migración). Herramienta de validación on-demand — **NO la importa el runtime del bot** (main.py/api.py):
- `d21966f` `metrics.py` PURO: sharpe, sortino, max_drawdown, win_rate, profit_factor, return_to_drawdown, total_return + compute_metrics. Sin dep externa. 24 tests TDD vs cálculo manual. Sharpe/Sortino per-trade (no anualizado), consistente con historian post-fix #TECHDEBT-NEW-1.
- `c6b2647` `data.py`: `normalize_ohlcv` (cualquier origen → contrato Backtesting.py: DatetimeIndex + OHLCV capitalizado float) + loaders Alpaca/CSV/Yahoo + `load_bars` dispatcher. 11 tests.
- `1811260` `adapters.py`: `make_strategy` envuelve cada Sentinel como `Strategy`. `run_sync` (bridge async→sync para analyze await-free vía coro.send) + `_to_live_bars` (timestamp tz-aware + columnas minúsculas, requerido por S-5/S-7 intradía). Long-only default, `allow_short` opcional. 12 tests.
- `8fa0e9a` `runner.py` + `__main__.py` CLI: `run_backtest` (Backtest con `finalize_trades=True` → métricas propias + stats nativas), `BacktestResult.to_dict` JSON-safe (inf/nan→null), `compare_to_paper`. CLI `python -m backtest --sentinel s2 --ticker SPY --start --end [--source alpaca|csv|yahoo] [--paper-json] [--json]`. `format_report` ASCII (robusto en consolas no-UTF8). 12 tests + smoke end-to-end real.
- **Librería:** `backtesting==0.6.5` → `requirements-dev.txt` (dev/test, NO prod; §7.5). Compatible con pandas 3.0.2 / numpy 2.4.4 (CERO downgrade). Aditivas: bokeh, jinja2, tornado, narwhals, xyzservices. **Paquete `backtest/` (singular) — NO `backtesting/` — para no shadowear la lib pip homónima.**
- Suite 489→**548** (+59 TDD). Gate cobertura CI **99.83%** (intacto, mi módulo fuera del set crítico). ruff verde. validate-workspace **0/0**. Ver `backtest/README.md`.

**Pendiente T-T (orden ratificado por Cowork):** Sub-1 **#HE-2** Investment Thesis Tracking (state machine + MAE/MFE + feedback loop, **migración 017 `investment_theses` APROBADA**) → Sub-3 Equity Research integración al system prompt del Universe Selector (Equity Research instalado ✅, NO bloqueado).

## Estado al 2026-05-25 — T-S 5/5 COMPLETO (#CR-2 splits/dividendos). `origin/main`=`7727511`, HEAD `6f87820` (ahead 14), suite 489/489

**#CR-2 Corporate actions simulado — COMPLETO. T-S cerrado entero (5/5).** 3 commits LOCALES, SIN migración (on-the-fly, patrón #CR-1/#CR-3):
- `fb0cae2` módulo puro `corporate_actions.py`: `normalize_alpaca_ca` (objetos SDK alpaca-py o dicts → {splits, dividends}; ratio = new_rate/old_rate para forward y reverse), `adjust_trades_for_splits` (trades pre-ex_date → qty×ratio, price/ratio; mantiene cost_basis), `compute_dividend_income` (net long en ex_date × rate; **short = payment in lieu = income negativo**), `build_corporate_actions_report` (ajusta trades por splits → reusa `tax_lots.compute_tax_report`). **26 tests TDD, 100% cobertura.**
- `6259389` wire-up `historian.get_corporate_actions_report(owner, ca inyectadas)`: **DIP** — las CA se inyectan (el endpoint las trae de Alpaca), historian NO se acopla a la red → 100% testeable. Refactor DRY: extraídos `_fetch_filled_trades` + `_serialize_tax_disposals` (compartidos con `get_tax_report`). +1 test.
- `6f87820` endpoint `/api/tax/corporate-actions` (formato `{data, meta}` §6.2, **dedicado on-demand, NO en /api/status** para evitar la llamada de red Alpaca en el poll del dashboard): query inline tickers+rango (patrón /api/status), `CorporateActionsClient` en `asyncio.to_thread`, normaliza, delega en historian. + `scripts/queries_corporate_actions.sql`.
- **Investigación Alpaca:** alpaca-py 0.43.3 expone `CorporateActionsClient.get_corporate_actions(CorporateActionsRequest(symbols, start, end, types))`; la cuenta paper devuelve datos. Tipos: forward/reverse/unit splits, cash/stock dividends, spin-offs, mergers, etc. (#CR-2 v1 consume forward/reverse splits + cash dividends).
- **Validado end-to-end SQL==Python sobre DB+Alpaca reales:** dividendos = **$0.27** (AAPL, 1 share long en ex 2026-05-11, confirmado por SQL net=1); **0 splits que afecten** lotes (el único, XLU 2:1 ex 2025-12-05, es **pre-período** — el bot operó XLU desde 11-may a precio ya ajustado); **tax report ajustado == #CR-1 idéntico** (no-regresión: −12.57 realized, 27 wash sales, neto 33.24). corporate_actions + historian + tax_lots 100% cobertura, suite 462→489 (+27).
- **Decisiones (drift/criterio, doc en código):** (1) forward y reverse splits con la misma fórmula ratio=new/old (reverse → ratio<1). (2) Dividendo short = income negativo (payment in lieu). (3) qualified vs ordinary NO se separa en v1 (income total ordinary; el bot mean-reversion holding corto → casi todo ordinary igual). (4) endpoint dedicado on-demand (decisión Roman).

**T-S Bloque C Compliance + Slippage — COMPLETO 5/5:** ✅ #ME-1 slippage · ✅ #ME-4 Claude/Sentinel · ✅ #CR-3 fees · ✅ #CR-1 fiscal · ✅ #CR-2 corporate actions. **Próxima migración libre = 017** (T-S no consumió ninguna: todo on-the-fly por drift/decisiones). **PRÓXIMO:** esperar validación Cowork de #CR-1+#CR-2 en el LOG + decisión de Roman sobre el próximo macro bloque (D Patrón Broker / E Plugins) y el bundle push.

## Estado al 2026-05-25 — T-S 4/5 (#CR-1 fiscal COMPLETO). `origin/main`=`7727511`, HEAD `f4bf2d8` (ahead 10), suite 462/462

**#CR-1 Reporte fiscal simulado — COMPLETO**, 2 commits LOCALES, SIN migración (on-the-fly, patrón #CR-3):
- `53fd044` módulo puro `tax_lots.py` (204 líneas): `match_fifo` (FIFO firmado LONG+SHORT — S-2/S-8 shortean — con holding_days y term short/long >365d), `apply_wash_sales` (disposal LONG con pérdida + recompra ±30d excluyendo el lote propio → difiere pérdida completa, simplificación documentada), `summarize`, `compute_tax_report` (agrupa por ticker). **14 tests TDD.** Cierra #TD-1 (reemplaza el `zip(buys,sells)` ingenuo de `calculate_performance` por FIFO por qty exacta).
- `f4bf2d8` wire-up: `historian.get_tax_report(owner)` (acumulado, a nivel CUENTA por owner/ticker cruzando Sentinels = trato IRS; devuelve `{summary, disposals}` JSON-safe) + `/api/status.tax_report_summary` (solo summary, liviano) + `scripts/queries_tax_report.sql` (referencia read-only; FIFO no replicable en SQL plano → da input crudo + agregados, invariante: net_qty=0 ⟹ realized_gain Python == net_cash_flow SQL) + test cobertura historian.
- **Validado SQL==Python read-only sobre 214 FILLED reales:** 101 disposals, 4 tickers planos OK / 0 mismatch. Resultado real: realized −$12.57 (todo short-term, qty=1), **27 wash sales** difiriendo $45.81, neto $33.24. **Hallazgo:** ~27% de disposals son wash sales (re-entrada rápida del bot) — dato fiscal para live. historian + tax_lots 100% cobertura, gate CI 99.83%.
- **Decisión Roman 2026-05-25:** tax lots = **FIFO** (default IRS, simple, auditable; extensible a specific-id luego).

**Pendiente T-S — 1/5: #CR-2 splits/dividendos** — corporate_actions + ajuste cost_basis. Investigar si Alpaca expone corporate actions API (¿`GET /v1/corporate-actions`?). Posible migración **017** si se persiste. Depende del cost_basis de #CR-1 (los disposals de `tax_lots` ya exponen cost_basis por lote para ajustar).

## Estado al 2026-05-25 — T-S 3/5 (#CR-3 fees COMPLETO). `origin/main`=`7727511`, HEAD `dc427ea` (ahead 8), suite 447/447

**#CR-3 Fees simulados — COMPLETO** (sub-4 de T-S), 4 commits LOCALES, SIN migración:
- `dee1a3f` módulo puro `simulated_costs.calculate_fees` (SEC §31 + FINRA TAF tope $8.30 + exchange, los 3 por VENTA, Decimal **exacto** — redondeo único al agregar, no por-trade, 11 tests TDD).
- `bada54d` wire-up: `historian.get_simulated_costs_today` (on-the-fly desde `trades`, patrón #ME-1 sin columna nueva) + `/api/status.simulated_costs_today` + `scripts/queries_simulated_costs.sql`.
- `27d230e` CLAUDE.md · `dc427ea` tasa SEC a valor real.
- **Validado SQL==Python read-only sobre 107 ventas FILLED reales** (total fees ~$0.14 — el período operó qty=1; pesan con sizing real). historian + simulated_costs 100% cobertura.
- **Decisiones Roman 2026-05-25:** tasa SEC = **$0.0278/$1000** (real FY2024, no el $0.00278 de la spec) · fees **on-the-fly** (revertible a persistir) · tax lots #CR-1 = **FIFO**.

**Pendiente T-S — 2/5 (bloque fiscal, DIFERIDO a sesión fresca por decisión Roman — no apurar código live-bound):**
- **#CR-1 fiscal** — diseño LISTO para retomar: módulo nuevo `tax_lots.py`, PURE/no-migración sobre los fills de `trades` (no toca DB). Pasos: (1) motor **FIFO** + holding period → disposals {qty, proceeds, cost_basis, gain, holding_days, term short/long >1año}; (2) wash-sale (pérdida + recompra ±30d → difiere); (3) reporte historian + /api/status + SQL. OJO: pairing actual `calculate_performance` es `zip(buys,sells)` ingenuo (bug #TD-1); el motor nuevo hace FIFO por qty.
- **#CR-2 splits/dividendos** — corporate_actions + ajuste cost_basis. Depende de #CR-1. Investigar si Alpaca expone corporate actions API.
- Próxima migración libre = **017** (si se decide persistir algo; el patrón hasta ahora evitó migraciones).

## Estado al 2026-05-25 — BUNDLE PUSHEADO + T-S PARCIAL 2/5. `origin/main`=`7727511`, HEAD `4788022` (ahead 2), suite 435/435

**Bundle del sprint pusheado** (Roman): `origin/main`=`7727511`, **CI GitHub Actions = success** (los 3 jobs, primer run real). Local en sync. NO-push sigue para lo nuevo.

**T-S Compliance+Slippage — parcial 2/5** (métricas, ambos sin migración por drift):
- ✅ `2aa3f14` #ME-1 slippage (bps on-the-fly) · ✅ `4788022` #ME-4 costo Claude per-Sentinel (dato ya per-Sentinel). historian methods + /api/status + queries SQL validadas en psql + tests. historian 100%, suite 435.
- ⏳ Pendiente 3/5 greenfield (migraciones 018-021 autorizadas): #CR-1 fiscal (wash sales/cost basis/tax lots), #CR-2 splits/dividendos (corporate_actions), #CR-3 fees simulados (`simulated_costs.py`). Cortado para budget fresco (código live-bound).

## Estado al 2026-05-25 — T-Q + T-R COMPLETOS (TECHDEBT Bloque F 9/9). 35 commits LOCALES, `origin/main`=`0242eb2`, HEAD `157f363`, suite 431/431

**T-R cerrado** (9 commits por archivo, plan ejecutivo Cowork): api (`f271742`) · dispatcher (`86c197e`) · main (`2f4fc0b`) · historian + migración 016 is_warmup (`82b6f45`) · config (`15bd719`) · correlation_guard (`57a5b8f`) · sentinels (`1782da2`) · infra TimedRotatingFileHandler (`513a8f9`) · regime+misc (`157f363`). Los 3 jobs CI verdes (test 431/431, lint limpio, coverage 99.83%). Migraciones DB aplicadas: 013/014/015/**016**.
- Comportamiento cambiado (aprobado): dispatcher #TD-2/#TD-7, correlation_guard #TD-3 (no_data→rechaza)/#TD-4 (duplicado→veto). historian get_trade_history eliminado (dead-code).
- **Diferidos:** Wilder RSI, #TD-12 TIMESTAMPTZ, dashboard #TD-18-21, #TD-13 /api/v1 (post-período-2 / Design). #TECH-001→WONTFIX (recomendado a Cowork).
- **T-Q hecho:** rename S-2 (ya estaba, UPDATE idempotente).

## Estado al 2026-05-24 — T-P CERRADO + lint verde (9/9 a 100%, gate CI 95). 25 commits LOCALES, `origin/main`=`0242eb2`, HEAD `f56f174`, suite 431/431

**Update:** `f56f174` `style(ruff)` resolvió los 15 errores ruff preexistentes (F401/F541) → **los 3 jobs del CI pasan local** (test 431/431, lint "All checks passed!", coverage exit 0 / 99.83%). Backups en `backups/2026-05-24/*_pre_ruff`. Sin bloqueadores de CI; falta solo el bundle (Cowork commitea su parte + orden de Roman).


**T-P (cobertura ≥95% módulos críticos) — COMPLETO.** Modelo NO-push vigente. Los 9 módulos críticos a 100% (config 94%, sin target):
- ✅ market_clock (`76db0e0`) · claude_client (`4949540`) · the_ear (`84f97e5`) · main (`d680084`) · correlation_guard (`e850432`) · universe_selector (`fbb6d64`).
- ✅ **historian 27%→100%** (`e5aa079`, 82 tests, `test_historian_coverage.py`) — 46 métodos SQL + connect() DDL + ramas except, pool asyncpg mockeado.
- ✅ **dispatcher 44%→100%** (`316ee4d`, 69 tests, `test_dispatcher_coverage.py`) — process_signal/execute_order/run_cycle/drawdown/kill-switch + wrappers `_sync` con Alpaca mockeado. 1 línea `# pragma: no cover` (rama `else "other"` del shadow, inalcanzable).
- ✅ **Gate CI** (`371a044`): `--cov-fail-under` 35→95 + `--cov=main` en `.github/workflows/ci.yml`; `docs/coverage_audit_2026-05-25.md` sección "Cierre T-P". Réplica del comando CI con gate 95 → **exit 0, TOTAL 99.83%**.
- Patrón: bloques `if __name__=="__main__"` → `# pragma: no cover`. Loops infinitos: `asyncio.sleep` mockeado con centinela. Suite 115→431.

**✅ Lint verde (`f56f174`):** los 15 errores ruff preexistentes (F401/F541) en api.py/the_ear.py/sentinels/universe_selector/claude_client/main/scripts/adopt_orphan_positions/run_adopt/test_decay_pf_rtd quedaron resueltos (14 auto + 1 manual). `ruff check .` → "All checks passed!".

## Estado al 2026-05-24 — T-O COMPLETA. 11 commits LOCALES (modelo NO-push), `origin/main`=`0242eb2`, suite 115/115

Sesión T-K→T-O con Cowork. **Modelo desde LOG 04:45: commits LOCALES, sin push** hasta un bundle ordenado por Roman. 10 commits locales sobre `origin/main`=`0242eb2` (HEAD `ce3480d`).

- **T-K EXP-005 Modo Observador Fractional** (`09dd71b`+`ad33843`): tabla `signals_shadow_fractional` (**migración 015 aplicada a DB**), flag `SHADOW_FRACTIONAL_ENABLED` (default ON), bloque shadow al final de `process_signal` (calcula qué operaría fractional vs `floor()` real, INSERT aislado, NO afecta la ejecución), `historian.record_shadow_fractional`. T-J (fractional real) ARCHIVADO: Alpaca no acepta notional+bracket.
- **T-L**: marcadores § + índice interno en `main.py`, `sentinels/__init__.py`, `universe_selector.py` (los otros 4 archivos >500 LOC ya los tenían).
- **T-M**: hardening XSS en `dashboard/sentinel-app.js` (escapeHtml en `s.id`/`s.name`/`s.quoteSrc`).
- **T-N**: `.pre-commit-config.yaml` + `.github/workflows/ci.yml` + `ruff.toml` (lint de correctness F+E9, **NO black** por la alineación manual de `=`) + `docs/coverage_audit_2026-05-25.md` (cobertura total **36%**) + `CONTRIBUTING.md`.
- **T-O COMPLETA** (4 sub-objetivos):
  - #TD-5 (`37ec6dd`): `the_ear` `pct_change`→`None`; el circuit breaker distingue sin-datos de 0% real.
  - #TD-6 (`37ec6dd`): flag `news_disabled` expuesto en `evaluate()`; follow-up: `the_ear_news_disabled` en `/api/status` (commit #ME-3).
  - #OP-2 (`93067d6`): heartbeat externo healthchecks.io. `config.HEARTBEAT_URL` (flag-gated, default off) + `main._send_heartbeat()` async no-bloqueante al final de cada ciclo (`import aiohttp`). Fallo de red → warning, no rompe el bot. `tests/test_heartbeat.py` (3). Nota README.
  - #ME-3 (`ce3480d`): `historian.get_signals_breakdown_today()` → `{filled, cancelled, pending, no_trade}` de las señales de HOY (conteo en `_bucket_signal_rows`, función pura). `/api/status` expone `signals_breakdown_today`. `scripts/queries_signals_breakdown.sql`. `tests/test_signals_breakdown.py` (6).
  - Suite **115/115** (era 106). the_ear 16%→29%.

**Pendiente:** **T-P — cobertura ≥95% módulos críticos** (EN COLA, BLOQUEADA hasta `[COWORK VALIDACIÓN T-O + OK avanzar a T-P]` en `teamwork/LOG.md`). **Migraciones DB aplicadas: 013, 014, 015.**

**Precondición Roman #OP-2:** crear check en healthchecks.io + `HEARTBEAT_URL=https://hc-ping.com/<UUID>` en `.env` + restart `main.py` (sin la URL el ping no hace nada). **Martes 26-may** restart `api.py` con env: `SHADOW_FRACTIONAL_ENABLED=true` + `ATR_SIZING_ENABLED=true` + `PORTFOLIO_DD_LIMITS_ENABLED=true` + `DAILY_REPORT_ENABLED=true`.

## Stack

- Python 3.14, asyncio
- PostgreSQL 18 nativo en Windows (servicio `postgresql-x64-18`)
- alpaca-py con feed IEX (paper)
- aiohttp + NewsAPI (macro)
- scikit-learn (RandomForest, S-10 desactivado)
- pandas (cálculos manuales de indicadores, sin ta-lib)
- LangGraph: planeado, todavía no implementado (loop manual en `main.py`)

## Componentes

| Archivo | Rol |
|---|---|
| `main.py` | Entry point, initialize() + main_loop() alineado a 15 min ET |
| `config.py` | Constantes y validación de credenciales |
| `historian.py` | Pool asyncpg, signals/trades, performance decay |
| `dispatcher.py` | Orquestador: kill-switch, sizing Half-Kelly, ejecución Alpaca |
| `the_ear.py` | NewsAPI cada 15min, VIXY/SPY change, Circuit Breaker, Parking Brake |
| `correlation_guard.py` | Pearson manual sobre rolling 60 velas, umbral 0.75 |
| `regime_classifier.py` | S-10 RandomForest BULL/NEUTRAL/BEAR — **DESACTIVADO** |
| `sentinels/__init__.py` | BaseSentinel + 9 estrategias |
| `api.py` | FastAPI backend (REST + SSE) en puerto 8080. Sirve dashboard estático. |
| `db/schema.sql` | 7 tablas con multi-tenant `owner_id` |
| `db/003_add_order_id_to_trades.sql` | Migración aplicada 2026-04-25: columna order_id en trades. |
| `db/004_create_system_state.sql` | Migración 2026-04-26: tabla system_state (canal IPC api↔main para kill switch). |
| `db/005_fix_trades_status_length.sql` | Migración 2026-04-27: trades.status VARCHAR(10)→(32), drop CHECK constraint para soportar status de Alpaca como PENDING_NEW. |
| `db/006_add_news_titles_to_macro_events.sql` | Migración 2026-04-27: columna news_titles JSONB en macro_events para titulares matched de The Ear. |
| `db/007_create_api_keys_table.sql` | Migración 2026-04-27: tabla api_keys con encrypted_value para gestión visual desde panel admin. |
| `db/008_create_rotation_decisions.sql` | Migración 2026-04-27: log inmutable de decisiones de Universe Selection. |
| `db/009_create_pending_candidates.sql` | Migración 2026-04-27: Watchlist Anticipada con UNIQUE parcial por sentinel. |
| `db/010_add_warning_threshold_to_performance_scores.sql` | Migración 2026-04-27: warning_status + warning_detected_at. |
| `email_service.py` | Cliente async de Resend para welcome/removal emails (templates Design) + template de rotación. |
| `crypto_utils.py` | Fernet helpers (encrypt/decrypt/mask) para api_keys encriptadas. |
| `claude_client.py` | Wrapper async sobre anthropic.AsyncAnthropic con timeout, cost tracking, JSON schema. |
| `universe_selector.py` | Lógica de rotación automática con Claude Sonnet 4.6 (warning/decay → propuesta → rotación). |
| `market_clock.py` | Estado mercado NYSE (OPEN/CLOSED/PRE_MARKET/AFTER_HOURS) + holidays 2026-2027. |
| `backtest/` | Framework de backtesting (#HE-4, dev-only). metrics/data/adapters/runner + CLI `python -m backtest`. Valida Sentinels sobre data histórica. NO runtime del bot. Ver `backtest/README.md`. |
| `investment_thesis.py` | Módulo PURO de Investment Thesis Tracking (#HE-2): state machine IDEA→ENTRY_READY→ACTIVE→CLOSED + MAE/MFE + outcome + feedback dataset. Sin DB/red. Lo consumen historian (persistencia) y universe_selector (enganche flag-gated `THESIS_TRACKING_ENABLED`). |
| `db/017_create_investment_theses.sql` | Migración 2026-05-25: tabla `investment_theses` (#HE-2). State machine + MAE/MFE + FK a rotation_decisions/sentinels. APLICADA. |

## 9 Sentinels operativos

| # | Tipo | Lógica |
|---|---|---|
| S-1 | sma_crossover | Cruce SMA(10)/SMA(50) |
| S-2 | rsi_short | RSI(2): <15 BUY / >85 SELL |
| S-3 | bollinger_bounce | Cierre fuera de BB(20, 2σ) |
| S-4 | macd_volume | MACD(12,26,9) + volumen >1.5×SMA(20) |
| S-5 | orb_breakout | Opening Range Breakout 9:30 ET |
| S-6 | ema_triple | EMA 8>21>55 alineadas |
| S-7 | vwap_reversion | Cierre fuera de VWAP±2σ intraday |
| S-8 | rsi_divergence | Divergencia RSI(14) en swings (k=3) |
| S-9 | bollinger_squeeze | BBW percentil 10 + breakout |

S-10 (RegimeClassifier) está implementado pero desactivado con early returns documentados — accuracy 0.3849 sobre 3 clases es casi random. Reactivar cuando haya 50-100 trades reales y features adicionales (RSI, MACD, breadth, yield curve).

## Arrancar

```powershell
cd sentinel-v0.5
venv\Scripts\activate
python main.py
```

Requiere PostgreSQL servicio activo y `.env` con credenciales.

## Estado al 2026-05-24 noche — Fase 2/3 robustez (`origin/main` `de4f029`, suite 95/95)

Sesión de robustez post-incidente del Write truncado. Cambios de código relevantes (todos pusheados):

- **Sharpe bug corregido (#TECHDEBT-NEW-1, `67164a5`):** `historian.calculate_performance` ya NO anualiza con `sqrt(252×26)≈80.94`. El Sharpe es **per-trade puro** (`mean/std`). Los valores de `performance_scores.sharpe_ratio` previos al fix (93.9, -120.4) eran artefacto del bug y distorsionaban `dispatcher.allocate_capital`. `SHARPE_MINIMUM` recalibrado 0.5→0.05 en `config.py`. `_SHARPE_ANNUALIZATION_FACTOR` queda definido pero DEPRECADO en el cálculo.
- **CorrelationGuard persistido (#TECHDEBT-NEW-2 / EXP-003, `2bf79ec`):** migración **013** agrega `avg_correlation_at_decision`, `original_qty`, `adjusted_qty`, `reduction_factor` a `signals`. `record_signal` acepta los 4 (default None, backward compat). `dispatcher.process_signal` persiste el output del guard, **incluidas las señales descartadas** por correlación (antes el `return` pre-`record_signal` las perdía).
- **Decay multifactor (#FASE2-NEW-5 / EXP-002, `de4f029`):** `calculate_performance` retorna `profit_factor` + `return_to_drawdown_ratio` (`inf` en edge cases gross_loss=0 / max_dd=0). `evaluate_decay` usa lógica combinada Opción C. Migración **014** agrega ambas columnas a `performance_scores`. Nuevos thresholds `PROFIT_FACTOR_MINIMUM=1.3`, `RTD_MINIMUM=1.0`. (OBS: el `rescued_by_pf_rtd` de la Opción C es matemáticamente redundante — pendiente de revisión por Cowork.)
- **Dashboard XSS hardening (`ac55d40`):** `escapeHtml()` en `dashboard/sentinel-app.js` (5 sitios con datos API/DB) + fix raíz en `tickerSpan` (`dashboard/sentinel-data.js`).

**Migraciones DB local:** 013 + 014 APLICADAS. **Suite: 95/95** (era 77 al inicio del día).

**Scripts ops nuevos en `scripts/`:** `validate-workspace.ps1` (gate anti-truncado — correr antes de cada commit), `clean-git-locks.ps1` (recovery de `.git/index.lock` huérfano), `run_balance_queries.py` + `generate_quantstats_report.py` (balance del período de observación). Migraciones `db/013` + `db/014`.

**Bug `.git/index.lock` recurrente:** resuelto con Windows Defender exclusion del repo (era el escaneo real-time sobre `.git/`).

**Pendiente:** **T-J Fractional trading** (`qty`→`notional`, refactor del dispatcher). Operacional Roman: `UPDATE sentinels SET name='S-2 RSI Fast Reversion' WHERE strategy_type='rsi_short'` en pgAdmin; restart `api.py` martes 26-may con flags `ATR_SIZING_ENABLED` + `PORTFOLIO_DD_LIMITS_ENABLED` ON.

## Estado al 2026-05-23 — Cierre anticipado del período de observación

### Fase 2 en curso (sesión nocturna 23-may, camino a v0.6 martes 26-may)

Coordinación vía `teamwork/LOG.md` (protocolo Cowork↔Code). Avanzado y **pusheado** a `origin/main`: `6a427c5` #H-5b (cache pop tras SELL) + quantstats · `a022de0` #H-4 Decimal correlation_guard · `917cad8` #H-4 Decimal historian · `5fa7125` §-markers dispatcher · `0ed87e4` #H-4 Decimal dispatcher · `3672a82` #H-6b auto-reconcile (poller 5 min en main.py) + #H-4 reconciler. **#H-4 y #H-6b cerrados.** Suite TDD **27/27** en `tests/`.

**Local sin pushear (espera PUSH-OK Cowork):** `5417066` (rename S-2 display→"RSI Fast Reversion", `requirements.txt` `==`, `requirements-dev.txt`).

Pendientes: DB `UPDATE sentinels SET name='S-2 RSI Fast Reversion' WHERE strategy_type='rsi_short'` (Roman) · 56 PENDING_NEW backlog (auto-limpia al arrancar main.py) · siguen lista negra Universe Selector + #GR-4 + #GR-1/#GR-2.

Convención: TDD test-first, backup pre-edit, Decimal en montos (§8.6), commit local + PUSH-OK.

### Sesión del 2026-05-23 (Roma + Code, HANDOFF #2)

El período de observación protegida (28-abr → 27-may) se **cerró anticipadamente el 2026-05-23**, 4 días antes de lo previsto. Decisión de Roman, documentada en `OBSERVATION_PERIOD.md` (sección "Cierre del período"). Motivo: durante las 4 semanas el sistema nunca operó en su forma de diseño (Dispatcher roto hasta 07-may, sizing trivial `qty=1` todo el período, bug #H-5b reaparecido 2 veces). Acumular más días sub-óptimos no aporta señal. El balance del período se lee como **versión sub-óptima del diseño**, no como evaluación del diseño final.

**El bot sigue en paper trading.** El cierre NO implica transición a live (live conservador previsto para julio 2026, post-Fase 4).

#### Restricciones del período — LEVANTADAS a partir del 23-may

Todas las reglas de la sección "❌ NO PERMITIDO" de `OBSERVATION_PERIOD.md` dejan de aplicar. Ahora SÍ se puede tocar SYSTEM_PROMPT del Universe Selector, thresholds, prompts, parámetros de estrategias, agregar/remover Sentinels, lógica de agentes, timeouts, reactivar S-10, e implementar features bloqueadas — **pero no de forma indiscriminada**: todo cambio sigue el plan de 6 fases (abajo). Fase 1 debe completarse antes de Fases 2-3.

#### Reporte diario — DESACTIVADO

El scheduler del reporte diario (16:30 ET L-V, `_daily_report_loop` en `api.py`) quedó **desactivado** vía flag `DAILY_REPORT_ENABLED` (definido en `config.py`, default `True`; puesto en `false` en `.env`). El arranque del scheduler en el lifespan de `api.py` ahora chequea el flag antes de crear la task. Email de cierre enviado a los 5 viewers el 23-may avisando la pausa.

- **Reactivar para el 2do período de observación (junio):** poner `DAILY_REPORT_ENABLED=true` en `.env` (o quitar la línea — el default es `True`) y reiniciar `api.py`.
- **Requiere restart de `api.py`** para tomar efecto (el proceso vivo mantiene el loop anterior hasta reiniciar).
- El endpoint manual `/api/report/daily/send-now` sigue activo para tests.
- La lógica del reporte NO se borró — solo se desactivó el disparo automático.

#### Plan post-observación activo — 6 fases (detalle en `NEXT_ITERATION.md`)

1. **Fase 1 — Análisis del período (días 1-3).** Métricas por Sentinel (win rate, Sharpe, profit factor, drawdown, slippage), equity curve, evaluación de Universe Selector / The Ear / CorrelationGuard. Recomendado QuantStats (#HE-1).
2. **Fase 2 — Auditoría de código (días 4-7).** Aplicar `BUENAS_PRACTICAS_V2` al codebase, cerrar #H-4 (float→Decimal restante) y #H-5b (cache `open_positions`), hardening dashboard, tests core, code review externo opcional.
3. **Fase 3 — Features bloqueadas (días 8-14).** Por prioridad: rename S-2, fix #H-5b, lista negra de leveraged/decay en prompt del Universe Selector, fractional trading (`qty`→`notional`), módulo `simulated_costs`, trigger `idle_timeout`, reactivar S-10, plugin Equity Research.
4. **Fase 4 — Segundo período de observación (30 días, junio).** Código limpio, sigue en paper, sin leverage. Validar mejora consistente vs abril-mayo.
5. **Fase 5 — Live conservador (julio 2026, condicionado).** Capital pequeño ($500-2K), solo bots long-cash, fractional, sin leverage, paper experimental en paralelo.
6. **Fase 6 — Hipótesis exploratorias (post-julio, condicionado).** Leverage escalonado 1.25x, shorts intencionales, multimercado, La Forja.

#### Eventos del período (resumen, detalle en `OBSERVATION_PERIOD.md`)

- Excepción 1 (07-may): scores parciales + agregación Dispatcher.
- Excepción 1.1 (08-may): Decimal/float + JOIN zombies + cleanup Mantis.
- Excepción 1.2 (13-may): Capital card dashboard (endpoint read-only).
- Intervención manual SPY (11-may) y QQQ (16-may): cierres de short accidental por #H-5b. Costo acumulado #H-5b: ~−$12 en QQQ, +$4.53 en SPY.
- Hallazgo 11-may: sizing trivial `qty=1` → diferido a #GR-2.

Contador del período nunca reiniciado (todas fueron correcciones de bug, no cambios de hipótesis).

---

## Estado al 2026-05-08 — Excepción 1 ampliada: dos bugs heredados

### Sesión del 2026-05-08 (Roma + Roman)

Primer día de mercado post-Excepción 1. Aparecieron dos bugs que la Excepción 1 expuso:

1. **Dispatcher: TypeError float += Decimal** en `allocate_capital()`. Mezcla de tipos al sumar `weighted_sharpe_sum` (float) con `score["sharpe_ratio"]` (Decimal de asyncpg). 21 errores en logs el 08-may. Resultado: `cycle_allocation = {}` cada ciclo → todos los Sentinels al fallback `MIN_CAPITAL_PER_SENTINEL = 5%` plano → órdenes con `qty=1`.

2. **Universe Selector: bucle de rotación zombie**. `historian.get_sentinel_scores()` no hacía JOIN con `sentinel_tickers`, devolvía scores de tickers ya rotados (`is_active=FALSE`). Mantis (S-2) ejecutó 23 rotaciones en 6h sobre TSLA y SPY zombies, costo ~$0.65 USD, acumulando 18 tickers nuevos.

**Fixes aplicados** (registrados como ampliación de Excepción 1, contador NO reinicia):

- `dispatcher.py` L153-163: conversión explícita `float()` e `int()` al leer scores. Cierra **#H-4** (último 🟠 ALTO pendiente).
- `historian.py` L585-619: `get_sentinel_scores()` con `JOIN sentinel_tickers ON is_active=TRUE`.
- DB: limpieza de Mantis a `NVDA + XLU + TLT` activos (resto inactive, sin borrar). Cubre Ambientes 2 (NVDA tech), 3 (XLU defensivo) y 4 (TLT bonos largos) del marco All Weather, todos compatibles con rsi_short (mean reversion).

**Validación:** simulación en `backups/2026-05-08/test_fixes_simulation.py` reproduce el TypeError y demuestra que ambos fixes producen allocation Sharpe-weighted Half-Kelly correcta (Mantis al 25% techo, qty NVDA pasa de 1 a ~200 shares).

**Pendiente para Roman al volver:** ejecutar `cleanup_mantis.sql` en pgAdmin y reiniciar `main.py`. Pasos en `backups/2026-05-08/DEPLOY_STEPS.md`. Mercado cerrado, ventana de deploy óptima.

**Deferido:** Trigger `idle_timeout` propuesto para Universe Selector — cae en "cambiar lógica de agente", se difiere a post-2026-05-27. Anotado en `NEXT_ITERATION.md`.

---

## Estado al 2026-04-28 — segunda jornada paper + Frente A/A.5 dashboard honesto

### Sesión del 2026-04-28 (Roman + Code) — todo READ-ONLY o cosmética dashboard

**Período de observación protegida vigente** (28-abr → 27-may). Default no-tocar; lo de hoy entra en "observabilidad read-only" + "cosmética dashboard". Cero cambios a thresholds, prompts, agentes, schema o datos de DB.

#### 1. Inventario read-only de DB (`backups/sentinel_2026-04-28_pre_inventory.dump` 49 KB + `inventory_2026-04-28.txt` 53 KB)

12 tablas auditadas (no 11 — apareció `sentinel_tickers` con 27 filas que la lista del prompt original no incluía). Hallazgos:

- **Timestamps en DB están en EDT** (hora local del server), no UTC. Para distinguir "handoff vs día real" el cutoff conceptual es `2026-04-28 09:30:00` (apertura mercado), no `13:30 UTC` como se asumía.
- **`signals`**: 36 filas. 17 del 27-abr (TSLA/NVDA/MSFT/GLD/SPY/QQQ/XLP), 19 del 28-abr.
- **`trades`**: 19 filas, **TODAS del 28-abr** (las 17 signals del 27 nunca llegaron al dispatcher). Status: 8 FILLED / 6 PENDING_NEW / 5 CANCELLED. Tickers: TSLA, NVDA, SPY, QQQ, AAPL, GLD, MSFT.
- **`performance_scores` VACÍA** → los win_rate/sharpe ficticios del dashboard NO venían de DB.
- **`macro_events`**: ~275 (drift, The Ear sigue ingresando cada 7-15 min).
- **`migration_log` y `api_keys` vacías** (esperado).
- **`rotation_decisions` y `pending_candidates` vacías** (Universe Selection no disparó porque performance_scores está vacía → nadie cruzó warning/decay threshold).
- **AMD aparece sólo en `sentinel_tickers`** (asignado a S-4 y S-9), nunca emitió signal ni trade. Refuta hipótesis inicial: los datos AMD/+$115 del dashboard NO eran seed de DB.

#### 2. Auditoría dashboard (`audit_dashboard_2026-04-28.md` 28 KB, 364 líneas)

Mapeo completo: 28 endpoints backend, 12 fetch frontend, 38 elementos del dashboard (16 reales / 7 parciales / 15 sintéticos). Veredicto: **Escenario B (parcial)**. La causa raíz NO era una sola función — eran 3 mecanismos mezclados:
- Markup literal en `index.html` sin `id` (11 piezas).
- Funciones sintéticas en `sentinel-app.js` (handoff Design): `renderSentGrid` mini-charts, `renderDetail` tickers operados, `renderHistorian` columnas trades/slip/decay, `buildReport` cliente, `tick` (interceptado).
- Constantes hardcoded en `sentinel-data.js`: `STATE.balance = 100000`, `synthEquityHist()`, `AGENTS[]` con `active` fijo.

Los 11 casos especiales del prompt resueltos uno por uno con archivo:línea exacto.

#### 3. Frente A — markup honesto + renderers reales

Backup: `backups/dashboard_2026-04-28_pre_fix_a.tar.gz` (28 KB).

Cambios:
- **`index.html`** +10/-10: 11 IDs nuevos sobre markup literal (`#agentsActiveCount`, `#osPnlPct`, `#osOpenPos`, `#osSigApproved`, `#osSigRejected`, `#eqMaxDD`, `#cgAvgCorr`, `#cgReduced`, `#cgDiscarded`, `#footUptime`, `#footBuild`).
- **`sentinel-data.js`** +118/-1: `STATE.balance = null` (era 100000), nueva sección "Frente A" con `renderAgentsActiveCount`, `renderCircuitBreakerToggle`, `renderParkingBrakeToggle`, `renderEmptyKPIs`, `fetchAndRenderBuild`. Llamadas en `loadStatus()` (toggles + count) y al final de `reloadFromAPI()` (`renderEmptyKPIs` sobrescribe).
- **`sentinel-app.js`** +53/-20: `renderHeader` y `renderEquity` envueltos en `if (STATE.balance != null)` para no romper con null. `renderHistorian` ahora lee `s._api.total_trades` y `s._api.decay_status` reales (slip queda "—"). `downloadReport` async pegando contra `/api/report` real (mapeo `last_hour` → `today` para evitar 422). `buildReport()` original conservada por si algo la usa.

Política central: **mostrar "—" en lugar de inventar**. KPIs sin endpoint (BALANCE, P&L, POSICIONES, signals procesadas, max DD, correlation guard, uptime) muestran em-dash hasta que Frente B agregue endpoints. Cuando exista `/api/account/equity`, se reemplazan los `_setText(id, _DASH)` en `renderEmptyKPIs()` por la lectura del campo correspondiente.

#### 4. Frente A.5 — neutralizar columnas sintéticas en `renderDetail` + corregir etiqueta engañosa

Backup: `backups/dashboard_2026-04-28_pre_fix_a5.tar.gz` (16 KB).

Cambios:
- **`sentinel-app.js`** +46/-9: solo el bloque `tickerRows` dentro de `renderDetail`. Iteración cambia de `s.tickers` (strings) a `s._api.tickers` (objects). Las 4 fórmulas `charCodeAt` del bundle eliminadas — ahora usa `last_signal`, `pnl`, `win_rate`, `sharpe_ratio` reales con regla "0 → '—'" porque el backend mapea NULL → 0.0 (api.py L493-495). Sharpe negativo SÍ se muestra.
- **`sentinel-i18n.js`** +4/-4: `dt_tickers` cambiado de "TICKERS OPERADOS" → "TICKERS ASIGNADOS" en es/en/ja/th. Los tickers que se muestran son del universo asignado (`sentinel_tickers`), no los efectivamente operados — el nombre nuevo no miente. `dt_recent` ("ÚLTIMOS 5 TRADES") intacto porque esa tabla SÍ son trades reales.

#### 5. Anomalías documentadas pendientes de acción

- **`viewer-2@example.com` sigue en `users`** (creado 2026-04-28 11:15:31). Roman dijo que fue eliminado hoy por incidente de seguridad — la eliminación NO se ejecutó en DB. Próxima sesión: ejecutar el DELETE vía panel admin o script controlado.
- **17 signals huérfanas del 27-abr** que nunca llegaron al dispatcher. Verificable revisando logs de ese día (fuera de scope hoy).

## Próximos pasos

### Frente B — endpoints faltantes (PARA POST-OBSERVATION o como excepción documentable)

✅ **Operativo y corriendo**:
- API + Cloudflare Tunnel + main.py corriendo. Primer ciclo real con mercado abierto fue lunes 2026-04-27.
- DB con 9 Sentinels (5% allocation cada uno, 45% total). 27 tickers en `sentinel_tickers`.
- Auth Google OAuth con roles ADMIN/VIEWER. Único ADMIN: `owner@example.com`. Único VIEWER: `viewer-1@example.com`.
- Kill switch operacional: botón DETENER/INICIAR del dashboard dispara halt/resume vía DB flag, poller cada 5s en `main.py` ejecuta `activate_kill_switch`/`deactivate_kill_switch`.
- Panel admin en `/admin` (ADMIN-only): CRUD de usuarios con welcome/removal email automático vía Resend desde `noreply@afterlifecapital.co` (dominio verificado).
- Universe Selection automática habilitada con Claude Sonnet 4.6.

### Bloque 1 (2026-04-27 — fixes del primer día) — mergeado a main

- `#FIX-005` trades.status VARCHAR(10)→VARCHAR(32) + drop CHECK constraint. PENDING_NEW de Alpaca ya no rompe el INSERT.
- `#FIX-006` `/api/report` con datos reales del Historian (uptime, signals_received, news_that_moved_decisions, etc.). El `buildReport()` cliente-side de sentinel-app.js sigue siendo demo y queda en TECHDEBT — el endpoint real es la fuente de verdad.
- `#FIX-007` The Ear persiste top 5 titulares en `macro_events.news_titles` (JSONB).
- `#FIX-008` Panel admin con gestión de API keys encriptadas (Fernet). El bot SIGUE leyendo desde .env — la sincronización automática es trabajo futuro. Requiere `MASTER_ENCRYPTION_KEY` en .env.

### Bloque 2 (2026-04-27 — Universe Selection) — mergeado a main

Sistema completo de rotación automática (Modo A — sin aprobación manual):
- `claude_client.py` — wrapper async con timeout (30s), cost tracking ($/M tokens), JSON schema. Cap por call $0.20.
- `universe_selector.py` — `evaluate_all_sentinels()` corre cada ciclo de 15min:
  - Pre-decay (warning): pide candidato y queda en watchlist 7 días.
  - Decay confirmado: ejecuta candidato pendiente o pide urgente.
  - Recuperación: descarta candidato pendiente.
- 3 tablas nuevas: `rotation_decisions` (log auditable con costo USD), `pending_candidates` (Watchlist con UNIQUE parcial), `performance_scores.warning_status`.
- 5 endpoints admin: `GET /api/admin/rotations[?status=]`, `GET /admin/rotations/{id}`, `POST /admin/rotations/{id}/rollback`, `GET /admin/candidates`, `GET /api/rotations/recent` (público VIEWER).
- Email automático al admin en cada rotación (template cyberpunk).
- Banner discreto de rotaciones recientes (24h) en dashboard.
- Sección de rotaciones + candidatos en panel admin con modal de detalle (razonamiento Claude, costo, candidatos alternativos) y rollback con confirm + email logueado.
- Test real al deploy: $0.0142 por call, 1169 in / 710 out tokens. Costo mensual estimado: ~$3.80 normal, ~$68 pico (cap mensual de $10 ya configurado en console.anthropic.com).

### Bloque 3 (2026-04-27 — The Ear + visibilidad) — mergeado a main

- `#FIX-009` Substring bug en keyword matching: `keyword in text` → `re.compile(\b{kw}\b)` con IGNORECASE. Elimina falsos positivos como "war" en "warnings". Trade-off documentado: word-boundary no matchea plurales (tariffs ≠ tariff, surges ≠ surge) — aceptamos precisión sobre recall.
- `#FIX-010` Endpoint `GET /api/macro_events?limit=N` (VIEWER+ADMIN) + frontend que reemplaza el placeholder genérico "Macro update — risk X · VIX Y · SPY Z" por el primer titular real de news_titles[]. Fallback al formato genérico si el evento no tiene titulares.
- `#FIX-011` Endpoint `GET /api/market-status` (público) + indicador en header con MERCADO ABIERTO/CERRADO/PRE-MERCADO/POST-MERCADO + countdown adaptativo (1h 42m / 17h 14m / 2d 5h). Estados con colores semánticos (verde/rojo/amarillo/magenta). `market_clock.py` con holidays NYSE 2026-2027 hardcoded.

### Hardening post-auditoría (sesiones 1–4 — 2026-04-25 / 2026-04-26)

**Sesiones 1–2.5** (2026-04-25):
- `#H-2` Race TheEar → `asyncio.Lock`.
- `#H-3` Timeouts asyncpg + `asyncio.wait_for` en los 11 call sites Alpaca.
- `#H-5` open_positions desync → refactor `list[dict]` → `dict[str, dict]`.
- `#H-6` Limit orders en background con `_check_later` + migración 003 (`order_id`).
- `_is_limit_strategy` set explícito; `approved = status == "FILLED"`; `done_callback` en ear_task.

**Sesión 3** (2026-04-26 — kill switch + Sharpe):
- `#H-7` kill switch operacional: tabla `system_state` (migración 004) como canal IPC entre `api.py` y `main.py`. Endpoints `POST /api/system/halt`, `POST /api/system/resume`, `GET /api/system/state`. Poller en `main.py` cada 5s. Frontend toggle DETENER/INICIAR.
- Sharpe annualization (#TECHDEBT promovido): factor `sqrt(252×26) ≈ 80.94` aplicado en `historian.calculate_performance`.

**Sesión 4** (2026-04-26 — auth + admin panel + integración Design):
- `#H-1` Google OAuth: rutas `/auth/login,callback,logout,me` con Authlib + SessionMiddleware (cookie firmada itsdangerous, HttpOnly, Secure, SameSite=Lax, 24h). Middleware `auth_middleware` con matriz de gating (público / sesión / role=ADMIN).
- Roles ADMIN/VIEWER aplicados en endpoints. VIEWER no ve botón DETENER ni link ADMIN; `/admin` redirige silently a `/`.
- Panel admin (`/admin`): handoff Design integrado (`admin.html` + `admin-app.js`) con adapter `user_id → id` para mantener API.
- Email service Resend con templates HTML del handoff Design (welcome bilingüe ES/EN con bloque permisos ADMIN, revoked bilingüe ES/EN). Envío async con httpx.

**Sesión 4.1** (2026-04-26 tarde — fixes UX dashboard + landing):
- `dashboard/sentinel-data.js`: logo `.brand` del header ahora es clickeable, abre `https://www.afterlifecapital.co` en nueva pestaña con `noopener,noreferrer`. Accesible por teclado (Enter/Space) con `role=link` y `tabindex=0`. Sin tocar `index.html`. Commit `0723a93`.
- `index.html` (raíz, landing Vercel): link CTA actualizado de `bot-cambio-ruta-production.up.railway.app/` a `sentinel.afterlifecapital.co/`. Commit final `77f6740` tras incidente: el primer intento (`33156b7`) consumió el `\` que escapaba la quote `\"` del atributo `href` dentro del `<script type="__bundler/template">` JSON-string, rompiendo el render. Revertido (`64f246b`) y reaplicado con regex que respeta el escape. JSON validado con `ConvertFrom-Json` antes del push.

### Issues 🟠 ALTOS — estado al 2026-04-27
- ✅ #H-1 (auth API)
- ✅ #H-2 (race TheEar)
- ✅ #H-3 (timeouts)
- ✅ #H-5 (open_positions)
- ✅ #H-6 (limit orders)
- ✅ #H-7 (kill switch)
- ⏳ **#H-4 — float→Decimal en cálculos financieros**. Único 🟠 pendiente.

### Issues #FIX-* (Bloques 1-3) — todos cerrados al 2026-04-27
- ✅ #FIX-005 trades.status VARCHAR + CHECK
- ✅ #FIX-006 /api/report con datos reales
- ✅ #FIX-007 news_titles persistidos por The Ear
- ✅ #FIX-008 panel admin con API keys encriptadas
- ✅ #FIX-009 substring bug en The Ear
- ✅ #FIX-010 /api/macro_events + render real
- ✅ #FIX-011 /api/market-status + indicador header

### Universe Selection (#UNIVERSE-SELECTION) — operativo al 2026-04-27
- Modo A (automático) habilitado. Email al admin por cada rotación.
- Cap mensual $10 en console.anthropic.com.
- Cap por call $0.20 (test real: $0.0142).

### Branches
- `main` — todos los bloques mergeados, último commit `9403e69` (DESIGN_CHANGES.md fixes 10-11).
- `feature/the-ear-improvements` — Bloque 3 (mergeado).
- `feature/universe-selection` — Bloque 2 (mergeado).
- `feature/day1-fixes` — Bloque 1 (mergeado).
- `backup/pre-redesign-2026-04-25` — snapshot inmutable previo.

## Decisiones clave

- **Sin Docker**: PostgreSQL 18 nativo en Windows (Docker Desktop fallaba en setup inicial).
- **Refactor BaseSentinel**: `fetch_bars`, `_fetch_bars_sync`, `run` centralizados. Cada Sentinel solo define `__init__` + `analyze`.
- **`feed=DataFeed.IEX` obligatorio**: la cuenta paper sin SIP da 403 al pedir datos recientes. Aplicado en los 4 sitios que hacen StockBarsRequest.
- **S-10 desactivado**: ahorra 30-60s de arranque (no descarga 25 años de SPY ni entrena RF). `get_regime()` retorna `"NEUTRAL"` fijo. Reactivar editando los early returns en `regime_classifier.py`.
- **RSI con SMA, no Wilder**: cálculo simplificado en `_rsi()`. Diferencia marginal vs Wilder smoothing — mejorar después si hace falta.
- **Logs**: `logs/sentinel.log` con RotatingFileHandler (5MB, 3 backups).

### Backlog operativo (post-observation)

1. **#H-4** float→Decimal en cálculos financieros (último 🟠 ALTO pendiente).
2. Dashboard hardening: XSS innerHTML, race SSE, defensa Chart.js.
3. Implementar nodo LangGraph real en `main.py` (actualmente loop manual con `asyncio.gather`).
4. Mejorar `_rsi()` a Wilder smoothing (S-2, S-8).
5. Reactivar S-10 cuando criterios estén (50–100 trades + features adicionales).
6. Universe Selection — agregar plurales/conjugaciones a `_NEGATIVE_KEYWORDS`/`_POSITIVE_KEYWORDS` o cambiar pattern a `\b{kw}s?\b` si word-boundary estricto pierde mucha señal.
7. ✅ Botón "DESCARGAR REPORTE JSON" — migrado a `/api/report` real (Frente A 2026-04-28). TECHDEBT.md L132 cerrado.
8. Sincronización automática `.env` ↔ tabla api_keys (hoy es solo gestión visual).
9. Deploy a Raspberry Pi 5.

### Frente B propuesto (cuando OWNER lo autorice como excepción o post-2026-05-27)

Endpoints **read-only nuevos** que rellenan los "—" del dashboard sin cambiar lógica del bot. Cada uno reemplaza un `_setText(id, _DASH)` en `renderEmptyKPIs()` por la lectura del campo correspondiente:

- `/api/account/equity` → llamar Alpaca `get_account()` y devolver `{balance, equity, cash, day_pnl, day_pnl_pct, positions_count}`. Reemplaza: `#osBalance`, `#osPnl`, `#osPnlPct`, `#osOpenPos`, `#eqCapital`, `#eqPnl`.
- `/api/equity/series?range=today` → curva real desde Alpaca portfolio history. Reemplaza: `#eqChart` (renderEquity hoy usa `synthEquityHist`) + permite calcular `#eqMaxDD` real.
- Persistir `signals.approved` + `signals.rejection_reason` (TODO en api.py L911-913) → exponer en `/api/signals/summary` para `#osSigProc`, `#osSigApproved`, `#osSigRejected`.
- Persistir `signals.correlation_action` + `signals.correlation_used` (TODO api.py L897-901) → `/api/correlation/summary` para `#cgAvgCorr`, `#cgReduced`, `#cgDiscarded`.
- Endpoint liviano `/api/version` con `{system_version, uptime_hours}` (hoy hay que pegarle a `/api/report` completo solo para sacar el build) → `#footUptime`, `#footBuild`.

Nota importante: estos endpoints técnicamente "exponen datos que ya existen" (no modifican lógica), pero agregar columnas nuevas a `signals` toca schema. Si Roman autoriza durante observación, **registrar como Excepción en `OBSERVATION_PERIOD.md` y resetear el contador de 30 días**. Más conservador: anotar en `NEXT_ITERATION.md` y aplicar después del 2026-05-27.

### Acciones operativas pendientes (no son features)

- **Eliminar `viewer-2@example.com` de `users`** — eliminación falló hoy 2026-04-28, sigue en DB con `created_at = 2026-04-28 11:15:31`. Ejecutar via panel admin (`DELETE /api/admin/users/{user_id}`) o script controlado.
- Investigar por qué las **17 signals del 27-abr nunca llegaron al dispatcher** (logs de ese día — `logs/sentinel.log`).
- Roman pendiente: rotar credenciales OAuth de Claude Code en meridian (incidente 25-abr, tokens viejos siguen vivos).

## Bugs conocidos

- Ninguno bloqueante al cierre 2026-04-28.
- ORB y VWAP retornan `price=0.0` cuando no hay barras del día actual ET (sábado/domingo o pre-market). El `run()` filtra por `qty=0.0` así que no afecta el pipeline, pero es estéticamente raro en logs.
- `update_trade_status` no warns si 0 rows afectados (ej. order_id no existe en DB).
- `record_trade` se hace en el mismo try que `record_signal`; si `record_signal` falla, la orden ya está en Alpaca pero sin fila DB.
- Reconciliación post-restart de limit orders: si el sistema cae con tasks `_check_later` en vuelo, mueren con el proceso. La orden Alpaca queda activa pero sin tracking. TODO en `dispatcher.execute_order`.
- `system_halted` flag persiste entre reinicios pero el Dispatcher arranca con `kill_switch_active=False` in-memory. Discrepancia hasta que el poller reaccione a un nuevo `halt_requested` o `resume_requested`.
- `OWNER_EMAIL` hardcodeado en dos lugares (`historian._OWNER_EMAIL` y `admin-app.js`). Si cambia el admin Google, hay que editar ambos.
- Word-boundary regex de The Ear (#FIX-009) no matchea plurales/conjugaciones — trade-off intencional vs falsos positivos del bug original. Si una nota relevante usa "tariffs" en lugar de "tariff", la perdemos.
- Holidays NYSE en `market_clock.py` hardcodeados 2026-2027. Hay que actualizar manualmente en noviembre 2027 cuando NYSE publique 2028.
- Indicador de mercado puede no aparecer si el handoff borra `.hdr-stats` después de los 3s del retry de `ensureNode()`. No observado en producción aún.
- Titulares de NewsAPI llegan en inglés y se muestran tal cual en los 4 idiomas (es/en/ja/th) — no hay traducción automática.
- Cache miss del system prompt de Universe Selection: el SYSTEM_PROMPT (~400 tokens) está debajo del mínimo cacheable de Sonnet 4.6 (2048). Cada call paga full price input. Si querés activar caching, engrosar el prompt o aceptar la limitación.

## Seguridad

- Multi-tenant: todo dato lleva `owner_id`. Owner actual: `<owner-username>` / `owner@example.com` (UUID `<owner-uuid>`).
- `.env`, `client_secret_*.json`, `.claude/` excluidos de git y de Drive sync.
- NEWS_API_KEY enviado en header `X-Api-Key` (nunca en URL params).
- Kill switch: `dispatcher.activate_kill_switch("CONFIRMAR")` requiere passphrase exacta. Disparable desde `/api/system/halt` (ADMIN-only) o desde el botón DETENER del dashboard.
- Auth: Google OAuth con cookie firmada itsdangerous (HttpOnly, Secure, SameSite=Lax, max-age 24h). Solo emails registrados en `users` reciben sesión válida.
- Resend: dominio verificado `afterlifecapital.co`. Emails desde `noreply@afterlifecapital.co` con `X-Entity-Ref-ID` para tracking.
