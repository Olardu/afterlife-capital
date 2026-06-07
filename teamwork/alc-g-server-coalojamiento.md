# ALC-G en ALC-P — ¿impedimento técnico para co-alojar ambas ALC?
## Code · 2026-06-07 · diagnóstico read-only (SSH a ALC-P, no se tocó nada)

> **Pregunta de Roman:** ¿la cuenta del servidor tendría algún impedimento técnico
> para que funcionen ambas ALC (el bot ALC-P + el runtime ALC-G) alojadas ahí mismo?

## Veredicto: NO hay impedimento. Recursos holgados. 1 recomendación (swap).

### Foto del servidor (Hetzner CPX21, 2026-06-07 19:02 UTC)
| Recurso | Valor | Margen para ALC-G |
|---|---|---|
| CPU | 3 vCPU, **load 0.00** (idle) | sobra (ALC-G es liviano) |
| RAM | 3.7 GB total · **2.8 GB libres** · usado ~1.0 GB | alcanza; **sin swap (0B)** ⚠ |
| Disco | 75 GB · 6% usado · **69 GB libres** | sobra |
| Python | 3.14.4 (mismo que el bot) | reusa el venv/patrón |
| Servicios vivos | mcp(9090), postgres-18, sentinel-api(8080), bot, túnel | conviven |
| Puertos libres | **8081+** (8080/9090/5432/22 ocupados) | API ALC-G → 8081 |

### Por qué ALC-G suma poco
- **Sin ML/torch** (el swap a DeepSeek ya lo sacó). Es núcleo pasivo: lee Alpaca + cálculo Decimal + uvicorn. Footprint estimado ~80-120 MB.
- **Fase 0 NO usa DB** (lee la cuenta #2 on-demand y loguea). Cero carga sobre PostgreSQL.
- **On-demand**: cada GET /status corre un ciclo; no hay loop pesado.

### Aislamiento (cero riesgo de regresión sobre el bot vivo)
- `alc_g/` **NO importa** `dispatcher`/`main`/`api` del bot → no puede romperlo.
- **Cuenta Alpaca #2 separada** (PA3G19D7F02K, keys propias) ≠ cuenta del bot (PA36P9MDPXCD). Llamadas API independientes; paper, volumen bajo → sin choque de rate-limit relevante.
- **Servicio systemd propio** `alc-g.service` (puerto 8081 loopback). Si crashea, no toca a ALC-P.

### Recomendaciones al desplegar
1. **Agregar swap (2 GB).** Hoy el server tiene **0B de swap**. Con el bot+pg+mcp en ~1 GB y ALC-G sumando ~0.1 GB hay margen (2.8 GB libres), pero sin swap un pico puntual dispara el OOM-killer y mata procesos. 2 GB de swapfile = colchón barato y prudente **antes** de sumar otro servicio. (Comando para Roman, no lo ejecuté: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` + línea en `/etc/fstab`.)
2. **Puerto 8081 loopback** (ya configurado en el unit). Exposición externa opcional: ruta en el túnel cloudflared existente (p.ej. `alcg.afterlifecapital.co`) o dejarlo local-only vía SSH tunnel. Decisión de Roman.
3. **Servicio aislado** `deploy/systemd/alc-g.service` (creado). Deploy: copiar `alc_g/` + `.env.alc-g` (perms 600, scp) → `systemctl enable --now alc-g`.
4. **DB futura (Fase 1+)**: si se persiste diario de decisiones / historial, crear base `alcg` SEPARADA en el mismo PostgreSQL 18 (no tocar la DB del bot).

### Conclusión
Co-alojar ambas ALC en ALC-P es viable hoy, sin tensión de recursos y con aislamiento limpio. El único paso previo recomendado es **agregar swap**. Todo lo demás (puerto, servicio, cuenta, código) ya está separado por diseño.
