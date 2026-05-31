# deploy/ — artefactos de despliegue ALC-P (Hetzner)

Acompaña a `docs/RUNBOOK_DEPLOY_HETZNER.md` (Cowork). Acá viven los archivos
concretos que el runbook deja "a crear" (C6: los 3 systemd units).

## systemd/ — units (paso C6)

Asumen el layout del runbook:
- Usuario: `sentinel`
- App: `/home/sentinel/afterlife-capital/sentinel-v0.5`
- venv: `.../sentinel-v0.5/venv`
- `.env` (perms 600) en el WorkingDirectory (lo lee `load_dotenv()`); llega por **scp, nunca por git**.

Instalación en el server (Fase C, modo PREP):
```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinel-api        # API SÍ (solo sirve datos de lectura)
# sentinel-tunnel: editar <TUNNEL_NAME> + credenciales; NO apuntar al hostname LIVE en prep
# sentinel-bot:    NO enable, NO start en PREP  ← crítico (anti doble-trading)
```

### ⚠️ Reglas duras
- **`sentinel-bot` NO se arranca en PREP.** Recién en el CUTOVER (Fase D, post-lunes),
  tras apagar el bot del Ally. NUNCA dos bots sobre la misma cuenta Alpaca.
- **`sentinel-tunnel` NO sirve `sentinel.afterlifecapital.co` hasta el cutover** (robaría
  el túnel del Ally). Editar `<TUNNEL_NAME>` y configurar credenciales antes de habilitar.
- **uvicorn bindea 127.0.0.1** (loopback): cloudflared lo expone; el puerto NO se abre en ufw.

### Cutover (Fase D, post-lunes)
```bash
sudo systemctl enable --now sentinel-bot        # trading real (solo tras apagar el Ally)
```

Ver el runbook completo + checklist de seguridad en `docs/RUNBOOK_DEPLOY_HETZNER.md`.
