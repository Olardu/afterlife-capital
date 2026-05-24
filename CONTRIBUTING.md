# Contributing — Afterlife Capital / Sentinel

Guía de desarrollo. Para el contexto del proyecto ver `BACKLOG.md` y, para las reglas
de trabajo (TDD, backups, gate post-edit anti-truncado), `BUENAS_PRACTICAS_V2.md`.

## Development setup

```bash
git clone https://github.com/Olardu/afterlife-capital.git
cd afterlife-capital/sentinel-v0.5

# venv + dependencias (Python 3.14)
python -m venv venv
venv\Scripts\activate            # Windows  (source venv/bin/activate en Unix)
pip install -r requirements.txt -r requirements-dev.txt

# correr la suite
python -m pytest tests/ -q                       # 99 passed esperado

# cobertura (instala pytest-cov si falta)
pip install pytest-cov
python -m pytest tests/ --cov=dispatcher --cov=historian --cov=the_ear \
  --cov=correlation_guard --cov=universe_selector --cov-report=term-missing
```

Requiere PostgreSQL 18 local + `.env` con credenciales (ver `sentinel-v0.5/CLAUDE.md`).
El `.env` NUNCA se commitea (está en `.gitignore`).

### Pre-commit hooks (gate local)

```bash
pip install pre-commit
pre-commit install                # instala el hook en .git/hooks/
pre-commit run --all-files        # corre todos los hooks sobre el repo
```

Hooks (ver `.pre-commit-config.yaml`): `gitleaks` (secretos), `check-added-large-files`
(500KB), `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`,
`ruff` (lint de correctness), `pytest --collect-only`. `pre-commit autoupdate`
actualiza las versiones de los hooks.

### CI (GitHub Actions)

`.github/workflows/ci.yml` corre en cada push/PR a `main`: **test** (pytest),
**lint** (ruff), **secrets** (gitleaks), **coverage** (umbral escalonado). El run
queda visible en la pestaña *Actions* del repo. No requiere secrets manuales
(`gitleaks-action` usa el `GITHUB_TOKEN` automático).

## Code style

- **Lint: `ruff`** con reglas de *correctness* (`F` pyflakes + `E9` syntax). Ver `ruff.toml`.
  `ruff check .` antes de commitear; `ruff check . --fix` auto-arregla lo seguro.
- **NO se usa formateador automático** (black / ruff-format). El código usa alineación
  manual intencional de `=` (ej. `config.py`); un formateador la destruiría con un
  cambio masivo, contra la disciplina de edición quirúrgica de `BUENAS_PRACTICAS_V2 §14.0`.
- Montos monetarios en `Decimal` (no float) — ver `§8.6` del manual.
- Archivos >500 LOC llevan marcadores de sección `§ N` + índice interno (grep `§ N`).

## Política de dependencias (#FASE2-NEW-2)

- `requirements.txt` usa **pin exacto** (`==X.Y.Z`), no rangos. Build reproducible.
- `requirements-dev.txt` para herramientas de desarrollo/test (no entran al runtime del bot).
- **Para actualizar una dependencia:**
  1. Cambiar el pin en `requirements.txt`.
  2. `pip install -r requirements.txt` en un venv limpio.
  3. Correr la suite completa (`pytest tests/ -q` → debe seguir verde).
  4. Si la dep toca ejecución de órdenes (alpaca-py), correr un smoke test contra
     Alpaca paper antes de mergear.
  5. Commit dedicado `chore(deps): bump X de A a B` con el resultado de la suite.

## Workflow de commits

- TDD test-first donde aplique; gate post-edit obligatorio (`py_compile`/`node --check`
  + suite verde + `validate-workspace.ps1` 0/0) ANTES de declarar un commit hecho.
- Backups pre-edit en `backups/YYYY-MM-DD/`.
- Mensajes en formato convencional (`feat`/`fix`/`docs`/`chore(scope): ...`).
