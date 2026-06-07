// ALC-G Cockpit — lógica de la cabina (vanilla JS, sin build).
// Lee /api/alcg/status, renderiza signos vitales, palanca de leverage y plan de
// rebalanceo. El leverage real se mueve al rebalancear; el cockpit informa.
'use strict';

const $ = (id) => document.getElementById(id);
const fmtUSD = (s) => '$' + Number(s).toLocaleString('en-US', { maximumFractionDigits: 0 });
const fmtLev = (s) => Number(s).toFixed(2) + '×';

// Hardening XSS (§7.2 + precedente sentinel-app.js): escapar todo string de la
// API antes de inyectarlo como HTML. Los números pasan por Number()/fmt* (seguros).
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const SIDES = ['BUY', 'SELL', 'HOLD'];

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || ('HTTP ' + r.status));
  return body;
}

// --- Presets -----------------------------------------------------------------

async function loadPresets() {
  const { data } = await api('/api/alcg/presets');
  const box = $('presets');
  box.innerHTML = '';
  const labels = {
    turbo: 'TURBO', rendimiento: 'RENDIMIENTO', normal: 'NORMAL', pasivo: 'PASIVO',
  };
  for (const [name, p] of Object.entries(data)) {
    const ballast = Math.round(Number(p.ballast_pct) * 100);
    const el = document.createElement('div');
    el.className = 'preset';
    el.dataset.preset = name;
    el.innerHTML = `<div class="pn">${esc(labels[name] || name.toUpperCase())}</div>` +
      `<div class="pd">${fmtLev(p.leverage)} · lastre ${ballast}%</div>`;
    el.onclick = () => applyPreset(name);
    box.appendChild(el);
  }
}

async function applyPreset(name) {
  try {
    const { data } = await api('/api/alcg/preset', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: name }),
    });
    $('levSlider').value = Number(data.leverage_target);
    onSliderInput();
    await refresh();
  } catch (e) { flashWarn(e.message); }
}

// --- Slider de leverage ------------------------------------------------------

function onSliderInput() {
  const v = Number($('levSlider').value);
  $('levChosen').textContent = fmtLev(v);
  const warn = $('levWarn');
  if (v > 1.5) {
    warn.textContent = `⚠ ${fmtLev(v)} supera el límite recomendado de 1.5× — zona de riesgo elevado.`;
    warn.classList.add('hot');
  } else {
    warn.textContent = ''; warn.classList.remove('hot');
  }
}

async function applyLeverage() {
  try {
    await api('/api/alcg/leverage', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: Number($('levSlider').value) }),
    });
    await refresh();
  } catch (e) { flashWarn(e.message); }
}

function flashWarn(msg) {
  const w = $('levWarn'); w.textContent = '✕ ' + msg; w.classList.add('hot');
}

// --- Fase de capital (deriva del techo) --------------------------------------

function phaseLabel(equity) {
  const e = Number(equity);
  if (e < 250000) return 'SEMILLA (<$250K)';
  if (e < 350000) return 'TRANSICIÓN ($250–350K)';
  if (e < 500000) return 'CONSOLIDACIÓN ($350–500K)';
  return 'CONSERVADORA (≥$500K)';
}

// --- Render principal --------------------------------------------------------

function render(snap) {
  const rep = snap.report;
  $('modeBadge').textContent = 'MODO ' + (snap.mode || '—').toUpperCase();
  $('modeBadge').className = 'badge ' + (snap.mode === 'ejecutar' ? 'amber' : 'cyan');

  $('levReal').textContent = fmtLev(rep.real_leverage);
  $('levChosen').textContent = fmtLev(rep.target_leverage);
  const gap = Number(rep.gap);
  $('levGap').textContent = (gap >= 0 ? '+' : '') + gap.toFixed(2) + '×';

  $('vEquity').textContent = fmtUSD(rep.equity);
  $('vCeiling').textContent = fmtLev(rep.glide_ceiling);
  $('vPhase').textContent = phaseLabel(rep.equity);
  $('vLong').textContent = fmtUSD(rep.long_value);
  const vix = $('vVix');
  vix.textContent = rep.vix_capped ? 'CAP 1.0× ACTIVO' : 'inactivo';
  vix.className = 'v ' + (rep.vix_capped ? 'red' : 'green');
  const dep = Number(snap.floor_deposit);
  const fl = $('vFloor');
  fl.textContent = dep > 0 ? ('APORTAR ' + fmtUSD(dep)) : 'pausado';
  fl.className = 'v ' + (dep > 0 ? 'amber' : 'green');

  // reconciliación: si efectivo == real dentro del umbral -> verde
  const recon = !rep.needs_rebalance;
  $('reconTxt').textContent = recon ? 'OK' : 'GAP';
  $('reconDot').querySelector('.dot').className = 'dot ' + (recon ? 'green' : 'red');

  renderOrders(snap.planned_orders, rep.drifted);
  $('footStamp').textContent = 'actualizado ' + new Date().toLocaleString('es-AR');
}

function renderOrders(orders, drifted) {
  const body = $('ordersBody');
  body.innerHTML = '';
  for (const o of orders) {
    const tr = document.createElement('tr');
    const delta = Number(o.delta_value);
    const side = SIDES.includes(o.side) ? o.side : 'HOLD';
    tr.innerHTML = `<td>${esc(o.ticker)}</td><td>${fmtUSD(o.target_value)}</td>` +
      `<td>${fmtUSD(o.current_value)}</td>` +
      `<td>${(delta >= 0 ? '+' : '') + fmtUSD(delta)}</td>` +
      `<td class="side-${side}">${side}</td>`;
    body.appendChild(tr);
  }
  const note = $('driftNote');
  note.textContent = (drifted && drifted.length)
    ? '⚠ Componentes fuera de banda (±5%): ' + drifted.map(esc).join(', ')
    : '';
}

async function refresh() {
  try {
    const { data } = await api('/api/alcg/status');
    render(data);
  } catch (e) {
    $('ordersBody').innerHTML = `<tr><td colspan="5" class="muted">error: ${e.message}</td></tr>`;
  }
}

// --- Init --------------------------------------------------------------------

window.addEventListener('DOMContentLoaded', async () => {
  $('levSlider').addEventListener('input', onSliderInput);
  $('applyLev').addEventListener('click', applyLeverage);
  onSliderInput();
  await loadPresets();
  await refresh();
  setInterval(refresh, 30000); // refresco cada 30s
});
