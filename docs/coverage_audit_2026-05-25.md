# Auditoría de cobertura — 2026-05-25 (#FASE2-NEW-4)

> **Cierre T-P — 2026-05-24.** El bloque T-P completó la cobertura. Resumen abajo;
> el baseline histórico de T-N se conserva a partir de "Auditoría inicial".

## Cierre T-P (#FASE2-NEW-4) — final 2026-05-24

Suite **431 tests** (era 99 al baseline T-N). Cobertura final del set de módulos
críticos del gate CI (mismo comando + `--cov=main`):

| Módulo | Stmts | Miss | Cover | T-N → T-P |
|---|---|---|---|---|
| `claude_client.py` | 66 | 0 | **100%** | 18% → 100% (`4949540`) |
| `config.py` | 72 | 4 | **94%** | sin target (`validate_config` sin test) |
| `correlation_guard.py` | 98 | 0 | **100%** | 44% → 100% (`e850432`) |
| `dispatcher.py` | 497 | 0 | **100%** | 44% → 100% (este bloque) |
| `historian.py` | 712 | 0 | **100%** | 25% → 100% (este bloque) |
| `main.py` | 291 | 0 | **100%** | 16% → 100% (`d680084`, Sub-obj 9) |
| `market_clock.py` | 53 | 0 | **100%** | 0% → 100% (`76db0e0`) |
| `the_ear.py` | 161 | 0 | **100%** | 16% → 100% (`84f97e5`) |
| `universe_selector.py` | 361 | 0 | **100%** | 43% → 100% (`fbb6d64`) |
| **TOTAL (set del gate)** | **2311** | **4** | **99%** | 36% → **99%** |

- **Gate CI subido `--cov-fail-under=35` → `95`** y agregado `--cov=main` al set medido.
  Con TOTAL 99% el job pasa con margen.
- Único `# pragma: no cover` agregado a fuente: rama `else "other"` del shadow fractional
  en `dispatcher.py` — inalcanzable (qty_real=floor(frac) ⟹ frac≥qty_real; si frac==qty_real
  ⟹ dollar_diff=0 ⟹ rama "matched"). El resto es 100% sin pragmas (salvo bloques
  `if __name__=="__main__"`).
- `config.py` queda en 94% (4 líneas: `validate_config`, L224-232) — no era target T-P.
- `api.py` sigue sin medir (FastAPI, requiere TestClient — bloque aparte).

---

# Auditoría inicial de cobertura — 2026-05-25 (#FASE2-NEW-4 parte 1)

Generado por T-N (sub-objetivo 4). Números **reales** de `pytest-cov` sobre la suite
de 99 tests. NO se implementaron tests nuevos en este bloque — este reporte es el
insumo para un bloque futuro (probablemente T-P) que suba la cobertura a ≥95% en los
módulos críticos.

Comando:
```
cd sentinel-v0.5
venv/Scripts/python.exe -m pytest tests/ -q --cov=dispatcher --cov=historian \
  --cov=the_ear --cov=correlation_guard --cov=universe_selector --cov=config \
  --cov=claude_client --cov-report=term-missing
```

## Cobertura por módulo

| Módulo | Stmts | Miss | Cover | Prioridad |
|---|---|---|---|---|
| `config.py` | 71 | 4 | **94%** | — (ya alto) |
| `dispatcher.py` | 498 | 278 | 44% | 🔴 P1 (core ejecución) |
| `correlation_guard.py` | 98 | 55 | 44% | 🟠 P2 (risk manager) |
| `universe_selector.py` | 361 | 206 | 43% | 🟡 P3 (rotación, aislado por try/except) |
| `historian.py` | 692 | 518 | 25% | 🔴 P1 (persistencia, base de todo) |
| `claude_client.py` | 66 | 54 | 18% | 🟡 P3 (wrapper API externa) |
| `the_ear.py` | 184 | 154 | 16% | 🔴 P1 (detección macro, menos probado) |
| `market_clock.py` | — | — | **0%** | 🟠 P2 (no importado por ningún test) |
| **TOTAL (medido)** | **1970** | **1269** | **36%** | — |

> Nota: `market_clock.py` reporta 0% porque ningún test lo importa (CoverageWarning
> "module-not-imported"). Tiene un self-test `python market_clock.py` pero no en la
> suite pytest. `api.py` no se midió (FastAPI, requiere TestClient — bloque aparte).

## Funciones críticas sin cobertura (de las líneas Missing)

**`dispatcher.py`** (278 miss) — las rutas más críticas del bot:
- `allocate_capital` / Half-Kelly (~L173-233) — sizing de capital, sin test directo.
- `_submit_order_sync` rama bracket + limit (~L761-798) — construcción de órdenes Alpaca.
- `run_cycle` (~L1064-1155) — loop principal de procesamiento.
- Varias ramas de `process_signal` (early returns: kill_switch, the_ear veto, atr_unavailable) — los tests actuales cubren el happy path + shadow (T-K), no los vetos.

**`historian.py`** (518 miss, el más grande) — mayoría de queries sin test:
- Casi todos los getters (`get_sentinel_scores`, `get_trade_history`, `get_recent_macro_*`, usuarios, api_keys, rotaciones). Los tests actuales cubren `record_signal`/`record_trade`/`record_shadow_fractional`/`calculate_performance`/`evaluate_decay` (parcial).

**`the_ear.py`** (154 miss, 16% — el menos probado):
- `evaluate` (circuit breaker / parking brake / risk_score) — el corazón del Ear, sin test.
- `_fetch_price_changes`, fetch de noticias, scoring de keywords. **Relevante para T-O** (#TD-5/#TD-6 tocan justo estas funciones).

**`correlation_guard.py`** (55 miss):
- `fetch_bars`, `calculate_correlation` (Pearson manual) — sin test directo. `evaluate_signal` sí tiene tests (T-H).

## Estimación gruesa para llegar a 95% por módulo

Para 95% hay que cubrir casi todo el `Miss`. Estimación en tests nuevos (no líneas):

| Módulo | Miss a cubrir (~) | Tests nuevos estimados |
|---|---|---|
| `the_ear.py` | ~145 | 12-16 (evaluate + breakers + fetch mocks) |
| `historian.py` | ~490 | 25-35 (un test por query con mock pool) |
| `dispatcher.py` | ~255 | 18-25 (allocate, submit branches, run_cycle, vetos) |
| `correlation_guard.py` | ~50 | 6-8 (fetch_bars + correlation + edge) |
| `universe_selector.py` | ~190 | 15-20 (flujos de rotación con mocks Claude) |
| `claude_client.py` | ~50 | 6-8 (wrapper con mock anthropic) |
| `market_clock.py` | full | 5-8 (estados NYSE + holidays) |

Total grueso: **~90-120 tests nuevos** para 95% en todos los críticos. Mucho — se hace por módulo en bloques separados.

## Recomendación de orden (para el bloque futuro)

1. **`the_ear.py` primero** — es el más bajo (16%) Y T-O lo va a tocar (#TD-5/#TD-6). Escribir sus tests junto con los fixes de T-O mata dos pájaros: el fix viene con su test y de paso sube cobertura.
2. **`market_clock.py`** — barato (módulo chico, lógica pura sin I/O), sube de 0% rápido.
3. **`correlation_guard.py`** — pocos miss (55), cierra un módulo de risk a >90%.
4. **`dispatcher.py`** — core, pero requiere mocks elaborados de Alpaca; ya tiene andamiaje de tests (test_dispatcher_*). Priorizar `allocate_capital` y las ramas de veto.
5. **`historian.py`** — el más grande; muchos getters triviales de cubrir con el patrón de mock pool ya establecido (`test_correlation_guard_persistence.py`). Volumen alto pero mecánico.
6. **`universe_selector.py` / `claude_client.py`** — último; muy aislados por try/except, menor riesgo operativo si fallan.

## Meta escalonada sugerida para CI (`--cov-fail-under`)

- Hoy: **36%** real. Arrancar el gate de CI en `--cov-fail-under=35` (no bloquear el estado actual).
- Tras cubrir the_ear + market_clock + correlation_guard: subir a ~55%.
- Tras dispatcher + historian: subir a ~85%.
- Meta final #FASE2-NEW-4: **95%** en los 7 módulos críticos.
