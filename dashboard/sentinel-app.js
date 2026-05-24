/* ============ HELPERS ============ */
const $ = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>[...r.querySelectorAll(s)];
const t = k => (I18N[STATE.lang]||I18N.es)[k] || k;
const fmt = n => n>=1000 ? n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : n.toFixed(2);
const fmt0 = n => n>=1000 ? n.toLocaleString('en-US') : n.toFixed(0);

/* ============ SECURITY ============ */
/**
 * Escapa caracteres HTML para prevenir XSS al interpolar datos no-confiables
 * (API responses, DB rows, logs externos) dentro de template literals que
 * usan innerHTML. Datos hardcoded (i18n keys, constantes AGENTS/NEWS/SENTINELS,
 * valores numéricos calculados) NO necesitan escape — quedan sin tocar.
 *
 * Política BUENAS_PRACTICAS_V2 §7: validar/sanitizar inputs en bordes.
 * Este es el borde DOM ← API/DB.
 */
function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ============ I18N APPLY ============ */
function applyI18n(){
  document.documentElement.lang = STATE.lang;
  $$('[data-i18n]').forEach(el => { const k = el.dataset.i18n; el.textContent = t(k); });
  renderAll();
}

/* ============ AGENTS ============ */
function renderAgents(){
  $('#agentsGrid').innerHTML = AGENTS.map(a => {
    const statusKey = a.active ? 'ag_active' : 'ag_idle';
    const statusCls = a.active ? 'active' : 'idle';
    return `<div class="agent-card ${a.active?'active':''}">
      <div class="ag-icon">${AGENT_ICONS[a.icon]}</div>
      <div class="ag-name">${t(a.nameKey)}</div>
      <div class="ag-sub">${t(a.subKey)}</div>
      <div class="ag-desc">${t(a.descKey)}</div>
      <div class="ag-status ${statusCls}"><span class="dot"></span><span>${t(statusKey)}</span></div>
    </div>`;
  }).join('');
}

/* ============ NEWS ============ */
function renderNews(){
  $('#newsList').innerHTML = NEWS.map(n => {
    const lblKey = 'impact_'+n.impact;
    return `<div class="news-item">
      <span class="ts">${n.ts}</span>
      <span class="title">${t(n.titleKey)}</span>
      <span class="badge ${n.impact}">${t(lblKey)}</span>
    </div>`;
  }).join('');
  $('#newsCount').textContent = NEWS.length + ' items';
}

/* ============ EQUITY (Robinhood-style) ============ */
let _eqHoverActive = false;

function renderEquity(){
  const data = STATE.equityHist;
  if (!data || data.length < 2) {
    $('#eqChart').innerHTML = '<text x="600" y="120" text-anchor="middle" fill="var(--dim)" font-size="12">Sin datos para este período</text>';
    return;
  }

  const W = 1200, H = 280, PAD_TOP = 40, PAD_BOT = 20;
  const usableH = H - PAD_TOP - PAD_BOT;
  const base = STATE.equityBaseValue || data[0];
  const latest = data[data.length - 1];
  const trend = latest >= base;

  // Y scale includes base line
  const allVals = [...data, base];
  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const range = (max - min) || 1;

  function toY(v) {
    return PAD_TOP + usableH - ((v - min) / range) * usableH;
  }

  // Breakeven line Y
  const baseY = toY(base);

  // Build points
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = toY(v);
    return [x, y];
  });

  const linePath = pts.map(([x, y], i) => (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ');

  // Area path from breakeven (for fill)
  const areaAbove = `M${pts[0][0].toFixed(1)} ${baseY.toFixed(1)} L${pts.map(p => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' L')} L${pts[pts.length-1][0].toFixed(1)} ${baseY.toFixed(1)} Z`;

  // Grid lines (subtle)
  const gridLines = [0.25, 0.5, 0.75].map(pct => {
    const y = PAD_TOP + usableH * (1 - pct);
    return `<line x1="0" y1="${y.toFixed(1)}" x2="${W}" y2="${y.toFixed(1)}"/>`;
  }).join('');

  // Hover vertical line + dot (hidden by default)
  const hoverEl = `<line id="eqHoverLine" x1="0" y1="0" x2="0" y2="${H}" stroke="var(--dim)" stroke-width="0.8" stroke-dasharray="4 3" opacity="0"/>` +
    `<circle id="eqHoverDot" cx="0" cy="0" r="4" fill="var(--cyan)" stroke="var(--bg)" stroke-width="2" opacity="0"/>`;

  // Bicolor: clip-paths to split line and area above/below breakeven
  $('#eqChart').innerHTML = `
    <defs>
      <linearGradient id="eqgGreen" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#00ff88" stop-opacity="0.25"/>
        <stop offset="1" stop-color="#00ff88" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="eqgRed" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0" stop-color="#ff2060" stop-opacity="0.25"/>
        <stop offset="1" stop-color="#ff2060" stop-opacity="0"/>
      </linearGradient>
      <clipPath id="clipAbove"><rect x="0" y="0" width="${W}" height="${baseY.toFixed(1)}"/></clipPath>
      <clipPath id="clipBelow"><rect x="0" y="${baseY.toFixed(1)}" width="${W}" height="${(H - baseY).toFixed(1)}"/></clipPath>
    </defs>
    <g stroke="rgba(0,245,255,0.04)" stroke-width="0.5">${gridLines}</g>
    <line x1="0" y1="${baseY.toFixed(1)}" x2="${W}" y2="${baseY.toFixed(1)}"
          stroke="var(--dim)" stroke-width="0.8" stroke-dasharray="6 4" opacity="0.5"/>
    <path d="${areaAbove}" fill="url(#eqgGreen)" clip-path="url(#clipAbove)"/>
    <path d="${areaAbove}" fill="url(#eqgRed)" clip-path="url(#clipBelow)"/>
    <path d="${linePath}" fill="none" stroke="var(--green)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" clip-path="url(#clipAbove)"/>
    <path d="${linePath}" fill="none" stroke="var(--red)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" clip-path="url(#clipBelow)"/>
    ${hoverEl}
    <rect id="eqHoverRect" width="${W}" height="${H}" fill="transparent" style="cursor:crosshair"/>
  `;

  // Update KPIs
  const pnl = latest - base;
  const pnlPct = base > 0 ? (pnl / base * 100) : 0;
  const sign = pnl >= 0 ? '+' : '-';
  const eqCapEl = document.getElementById('eqCapital');
  const eqPnlEl = document.getElementById('eqPnl');
  if (eqCapEl) eqCapEl.textContent = '$' + latest.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  if (eqPnlEl) {
    eqPnlEl.textContent = sign + '$' + Math.abs(pnl).toFixed(2) + ' (' + (pnl >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%)';
    eqPnlEl.className = pnl >= 0 ? 'green' : 'red';
  }

  // Hover interaction
  _setupEquityHover(data, pts, base);
}

function _setupEquityHover(data, pts, base) {
  const svg = document.getElementById('eqChart');
  const hoverRect = document.getElementById('eqHoverRect');
  const hoverLine = document.getElementById('eqHoverLine');
  const hoverDot = document.getElementById('eqHoverDot');
  const hoverInfo = document.getElementById('eqHoverInfo');
  const hoverValue = document.getElementById('eqHoverValue');
  const hoverChange = document.getElementById('eqHoverChange');
  if (!hoverRect || !svg) return;

  const W = 1200;

  function onMove(e) {
    const rect = svg.getBoundingClientRect();
    const xPct = (e.clientX - rect.left) / rect.width;
    const idx = Math.round(xPct * (data.length - 1));
    if (idx < 0 || idx >= data.length) return;

    const val = data[idx];
    const pt = pts[idx];
    const pnl = val - base;
    const pnlPct = base > 0 ? (pnl / base * 100) : 0;
    const sign = pnl >= 0 ? '+' : '-';
    const trend = pnl >= 0;

    // Position hover elements in SVG
    if (hoverLine) { hoverLine.setAttribute('x1', pt[0]); hoverLine.setAttribute('x2', pt[0]); hoverLine.setAttribute('opacity', '1'); }
    if (hoverDot) { hoverDot.setAttribute('cx', pt[0]); hoverDot.setAttribute('cy', pt[1]); hoverDot.setAttribute('opacity', '1'); hoverDot.setAttribute('fill', trend ? 'var(--green)' : 'var(--red)'); }

    // Hover info overlay
    if (hoverInfo) hoverInfo.classList.add('visible');
    if (hoverValue) {
      hoverValue.textContent = '$' + val.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      hoverValue.style.color = trend ? 'var(--green)' : 'var(--red)';
    }
    if (hoverChange) {
      let timeLabel = '';
      if (STATE.equityTimestamps && STATE.equityTimestamps[idx]) {
        const ts = STATE.equityTimestamps[idx];
        const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
        timeLabel = d.toLocaleDateString('en-US', {month:'short', day:'numeric'}) + ' ' + d.toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit', hour12:false}) + '  ·  ';
      }
      hoverChange.textContent = timeLabel + sign + '$' + Math.abs(pnl).toFixed(2) + ' (' + (pnl >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%)';
      hoverChange.style.color = trend ? 'var(--green)' : 'var(--red)';
    }
  }

  function onLeave() {
    if (hoverLine) hoverLine.setAttribute('opacity', '0');
    if (hoverDot) hoverDot.setAttribute('opacity', '0');
    if (hoverInfo) hoverInfo.classList.remove('visible');
  }

  hoverRect.addEventListener('mousemove', onMove);
  hoverRect.addEventListener('mouseleave', onLeave);
}

/* ============ EQUITY PERIOD SELECTOR ============ */
(function initEquityPeriodSelector() {
  document.addEventListener('DOMContentLoaded', function() {
    const btns = document.querySelectorAll('.eq-period-btn');
    btns.forEach(function(btn) {
      btn.addEventListener('click', function() {
        btns.forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        const period = btn.getAttribute('data-period');
        const label = document.getElementById('eqPeriodLabel');
        if (label) label.textContent = period;
        if (typeof fetchPortfolioHistory === 'function') {
          fetchPortfolioHistory(period);
        }
      });
    });

    // Set 1D as active by default (fetch real se hace en reloadFromAPI)
    btns.forEach(function(b) {
      b.classList.toggle('active', b.getAttribute('data-period') === '1D');
    });
  });
})();

/* ============ SENTINEL CARDS ============ */
function renderSentGrid(){
  const grid = $('#sentGrid');
  grid.innerHTML = SENTINELS.map((s, idx) => {
    // Curva real: PnL acumulado desde trades FILLED de este Sentinel
    const myTrades = (STATE.trades || []).filter(t => t.sent === s.id && t.status === 'FILLED' && t.px > 0);
    let pts = [];
    if (myTrades.length >= 2) {
      let acc = 100;
      const ordered = [...myTrades].reverse(); // ASC
      ordered.forEach(t => {
        const delta = t.side === 'SELL' ? (t.px * t.qty * 0.001) : -(t.px * t.qty * 0.001);
        acc += delta;
        pts.push(acc);
      });
    } else {
      // Sin suficientes trades: linea plana gris
      for (let i = 0; i < 12; i++) pts.push(100);
    }
    const min=Math.min(...pts), max=Math.max(...pts), rng=(max-min)||1;
    const polyPts = pts.map((vv,i)=>{
      const x = (i/(pts.length-1))*100;
      const y = 100 - ((vv-min)/rng)*90 - 5;
      return x.toFixed(1)+','+y.toFixed(1);
    }).join(' ');
    const hasTrades = myTrades.length >= 2;
    const trend = hasTrades ? pts[pts.length-1] > pts[0] : false;
    const stroke = hasTrades ? (trend ? '#00ff88' : '#ff2060') : 'rgba(255,255,255,0.15)';
    const fill = hasTrades ? (trend ? 'rgba(0,255,136,0.12)' : 'rgba(255,32,96,0.12)') : 'rgba(255,255,255,0.03)';
    const sigCls = s.sig.toLowerCase();
    const sigTxt = t('sig_'+sigCls);
    const sharpeC = s.sharpe>=1?'green':s.sharpe>=0?'':'red';
    return `<div class="sent-card" data-detail="${s.id}">
      <div class="top">
        <div><span class="name">${escapeHtml(s.name)}</span> <span class="sid">${s.id}</span></div>
        <span class="sig ${sigCls}">${sigTxt}</span>
      </div>
      <div class="strat">${t(s.stratKey)}</div>
      <svg class="mini-eq" viewBox="0 0 100 100" preserveAspectRatio="none">
        <polygon points="0,100 ${polyPts} 100,100" fill="${fill}" stroke="none"/>
        <polyline points="${polyPts}" fill="none" stroke="${stroke}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="stats">
        <div class="stat"><span class="k">${t('st_win')}</span><span class="v">${s.win > 0 ? (s.win*100).toFixed(0)+'%' : '--'}</span></div>
        <div class="stat"><span class="k">${t('st_sharpe')}</span><span class="v ${sharpeC}">${s.sharpe > 0 ? s.sharpe.toFixed(2) : '--'}</span></div>
        <div class="stat"><span class="k">${t('st_alloc')}</span><span class="v">${(s.alloc*100).toFixed(0)}%</span></div>
      </div>
    </div>`;
  }).join('');
  $$('#sentGrid .sent-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.detail;
      STATE.expandedDetails.add(id);
      renderDetail();
      const target = document.getElementById('detail-'+id);
      if (target) target.scrollIntoView({behavior:'smooth', block:'start'});
    });
  });
}

/* ============ STATUS & POSITION HELPERS ============ */
/* Maps Alpaca raw status → i18n key. Returns {text, tip, cls} */
function statusInfo(rawStatus) {
  const s = (rawStatus || '').toUpperCase().replace(/ /g, '_');
  const map = {
    'FILLED':          { key: 'st_filled',    cls: 'st-ok' },
    'PARTIALLY_FILLED':{ key: 'st_partial',   cls: 'st-warn' },
    'CANCELLED':       { key: 'st_cancelled', cls: 'st-cancel' },
    'CANCELED':        { key: 'st_cancelled', cls: 'st-cancel' },
    'EXPIRED':         { key: 'st_expired',   cls: 'st-cancel' },
    'REJECTED':        { key: 'st_rejected',  cls: 'st-cancel' },
    'PENDING_NEW':     { key: 'st_pending',   cls: 'st-wait' },
    'NEW':             { key: 'st_new',       cls: 'st-wait' },
    'ACCEPTED':        { key: 'st_accepted',  cls: 'st-wait' },
    'SUSPENDED':       { key: 'st_suspended', cls: 'st-warn' },
  };
  const entry = map[s] || { key: 'st_unknown', cls: 'st-cancel' };
  return { text: t(entry.key), tip: t(entry.key + '_tip'), cls: entry.cls };
}

/* ============ DETAIL ACCORDION ============ */
function getQuote(s){
  return ({es:s.quote, en:s.quoteEn, ja:s.quoteJa, th:s.quoteTh})[STATE.lang] || s.quote;
}
function renderDetail(){
  const c = $('#detailContainer');
  c.innerHTML = SENTINELS.map(s => {
    const open = STATE.expandedDetails.has(s.id);
    /* Frente A.5 — datos reales desde /api/sentinels (s._api.tickers[] tiene
     * objects con last_signal, pnl, win_rate, sharpe_ratio por ticker).
     * Las 4 fórmulas charCodeAt del bundle quedaron eliminadas. Política
     * "—" en lugar de mentir cuando el dato es null/undefined o exactamente 0.
     * Fallback: si s._api no existe, iteramos sobre s.tickers (strings) y
     * mostramos "—" en todas las columnas excepto TICKER. */
    const apiTickers = (s._api && Array.isArray(s._api.tickers)) ? s._api.tickers : null;
    const iter = apiTickers || s.tickers.map(tk => ({ ticker: tk }));
    const tickerRows = iter.map(td => {
      const sym = (td && td.ticker) ? td.ticker : '?';

      // Trades FILLED reales de este sentinel para este ticker
      const myTkTrades = (STATE.trades || []).filter(
        tr => tr.sent === s.id && tr.ticker === sym && tr.status === 'FILLED' && tr.px > 0
      );
      const hasTrades = myTkTrades.length > 0;

      // Señal — si no ha operado este ticker, mostrar "VIGILANDO"
      let sigCls, sigTxt;
      if (!hasTrades) {
        sigCls = 'sig-hold'; sigTxt = '\u{1f441} ' + t('sig_watching');
      } else {
        const rawSig = (td.last_signal || '').toString().toUpperCase();
        if (rawSig === 'BUY')       { sigCls = 'sig-buy';  sigTxt = t('sig_buy');  }
        else if (rawSig === 'SELL') { sigCls = 'sig-sell'; sigTxt = t('sig_sell'); }
        else if (rawSig === 'HOLD') { sigCls = 'sig-hold'; sigTxt = t('sig_hold'); }
        else                        { sigCls = 'sig-hold'; sigTxt = '—';           }
      }

      // P&L — calcular desde trades FILLED reales
      let pnlCell;
      if (hasTrades) {
        const buys = myTkTrades.filter(tr => tr.side === 'BUY');
        const sells = myTkTrades.filter(tr => tr.side === 'SELL');
        const netQty = buys.reduce((a, tr) => a + tr.qty, 0) - sells.reduce((a, tr) => a + tr.qty, 0);
        if (buys.length > 0 && sells.length > 0) {
          // Hay round-trips: calcular P&L realizado
          const soldVal = sells.reduce((a, tr) => a + tr.px * tr.qty, 0);
          const boughtVal = buys.reduce((a, tr) => a + tr.px * tr.qty, 0);
          const realPnl = soldVal - boughtVal;
          if (realPnl > 0) {
            pnlCell = `<td style="text-align:center;color:var(--green)">+$${realPnl.toFixed(2)}</td>`;
          } else if (realPnl < 0) {
            pnlCell = `<td style="text-align:center;color:var(--red)">-$${Math.abs(realPnl).toFixed(2)}</td>`;
          } else {
            pnlCell = `<td style="text-align:center;color:var(--dim)">$0.00</td>`;
          }
        } else {
          // Solo buys o solo sells — posición abierta
          pnlCell = `<td style="text-align:center;color:var(--cyan);font-size:10px;letter-spacing:0.08em"><span class="tip-trigger" data-tip="${netQty > 0 ? t('pos_long_tip') : t('pos_short_tip')}">${Math.abs(netQty)} ${netQty > 0 ? t('pos_long') : t('pos_short')}</span></td>`;
        }
      } else {
        pnlCell = `<td style="text-align:center;color:var(--dim)">—</td>`;
      }

      // Win rate — performance_scores está vacía hoy, así que win_rate llega
      // como 0 (backend lo mapea desde NULL). Tratamos 0 como "—".
      const win = Number(td.win_rate);
      const winCell = (Number.isFinite(win) && win > 0)
        ? `<td style="text-align:center">${(win * 100).toFixed(0)}%</td>`
        : `<td style="text-align:center;color:var(--dim)">—</td>`;

      // Sharpe — idem, 0 → "—". Sharpe negativo (pérdida real) sí se muestra.
      const sh = Number(td.sharpe_ratio);
      const shCell = (Number.isFinite(sh) && sh !== 0)
        ? `<td style="text-align:center">${sh.toFixed(2)}</td>`
        : `<td style="text-align:center;color:var(--dim)">—</td>`;

      return `<tr><td>${tickerSpan(sym)}</td><td><span class="${sigCls}">${sigTxt}</span></td>${pnlCell}${winCell}${shCell}</tr>`;
    }).join('');

    /* fake last 5 trades */
    const recent = STATE.trades.filter(tr => tr.sent === s.id).slice(0,5);
    const recentRows = recent.length ? recent.map(tr => {
      const sideCls = tr.side==='BUY'?'sig-buy':'sig-sell';
      const sideTxt = tr.side==='BUY'?t('sig_buy'):t('sig_sell');
      return `<tr><td>${escapeHtml(tr.ts)}</td><td>${tickerSpan(tr.ticker)}</td><td class="${sideCls}">${sideTxt}</td><td style="text-align:center">${escapeHtml(tr.qty)}</td><td style="text-align:right">${fmt(tr.px)}</td><td style="text-align:center" class="${statusInfo(tr.status).cls}"><span class="tip-trigger" data-tip="${statusInfo(tr.status).tip}">${statusInfo(tr.status).text}</span></td></tr>`;
    }).join('') : `<tr><td colspan="6" class="empty">${t('empty_ops')}</td></tr>`;

    return `<div class="detail-block ${open?'open':''}" id="detail-${s.id}">
      <div class="detail-head" data-id="${s.id}">
        <span class="name">${s.name}</span>
        <span class="strat">${t(s.stratKey)}</span>
        <span class="chev">▶</span>
      </div>
      <div class="detail-body">
        <div class="detail-quote">"${escapeHtml(getQuote(s))}"<span class="src">— ${s.quoteSrc}</span></div>
        <div class="detail-desc">${t('desc_'+s.stratKey)}</div>
        <div class="dt-subhead">${t('dt_tickers')}</div>
        <div class="tbl-wrap"><table class="tbl tbl-fixed"><colgroup><col style="width:14%"><col style="width:22%"><col style="width:28%"><col style="width:18%"><col style="width:18%"></colgroup><thead><tr>
          <th>${t('th_ticker')}</th><th>${t('th_signal')}</th><th style="text-align:center">${t('th_pnl')}</th><th style="text-align:center">${t('th_win')}</th><th style="text-align:center">${t('th_sharpe')}</th>
        </tr></thead><tbody>${tickerRows}</tbody></table></div>
        <div class="dt-subhead">${t('dt_recent')}</div>
        <div class="tbl-wrap"><table class="tbl tbl-fixed"><colgroup><col style="width:18%"><col style="width:16%"><col style="width:16%"><col style="width:12%"><col style="width:18%"><col style="width:20%"></colgroup><thead><tr>
          <th>${t('th_ts')}</th><th>${t('th_ticker')}</th><th>${t('th_side')}</th><th style="text-align:center">${t('th_qty')}</th><th style="text-align:right">${t('th_px')}</th><th style="text-align:center">${t('th_status')}</th>
        </tr></thead><tbody>${recentRows}</tbody></table></div>
      </div>
    </div>`;
  }).join('');
  $$('#detailContainer .detail-head').forEach(h => {
    h.addEventListener('click', () => {
      const id = h.dataset.id;
      if (STATE.expandedDetails.has(id)) STATE.expandedDetails.delete(id);
      else STATE.expandedDetails.add(id);
      renderDetail();
    });
  });
}

/* ============ OPS / FLOW TABLES ============ */
function renderOps(){
  $('#opsHead').innerHTML = ['th_id','th_sent','th_ticker','th_side','th_qty','th_px','th_status','th_ts'].map((k,i)=>{
    const align = (k==='th_qty'||k==='th_status') ? 'center' : (k==='th_px') ? 'right' : '';
    return `<th${align?' style="text-align:'+align+'"':''}>${t(k)}</th>`;
  }).join('');
  const body = $('#opsBody');
  body.innerHTML = STATE.trades.map(tr => {
    const sideCls = tr.side==='BUY'?'sig-buy':'sig-sell';
    const sideTxt = tr.side==='BUY'?t('sig_buy'):t('sig_sell');
    return `<tr><td>#${escapeHtml(tr.id)}</td><td style="color:var(--cyan)">${escapeHtml(tr.sentName||tr.sent)}</td><td>${tickerSpan(tr.ticker)}</td><td class="${sideCls}">${sideTxt}</td><td style="text-align:center">${escapeHtml(tr.qty)}</td><td style="text-align:right">${fmt(tr.px)}</td><td style="text-align:center" class="${statusInfo(tr.status).cls}"><span class="tip-trigger" data-tip="${statusInfo(tr.status).tip}">${statusInfo(tr.status).text}</span></td><td>${escapeHtml(tr.ts)}</td></tr>`;
  }).join('');
  $('#opsCount').textContent = STATE.trades.length + ' trades';
}

function renderFlow(){
  $('#flowHead').innerHTML = ['th_sent','th_strat','th_signal','th_win','th_sharpe','th_alloc'].map((k,i)=>`<th${i>=3?' style="text-align:center"':''}>${t(k)}</th>`).join('');
  $('#flowBody').innerHTML = SENTINELS.map(s => {
    const sigCls = s.sig==='BUY'?'sig-buy':s.sig==='SELL'?'sig-sell':'sig-hold';
    const sigTxt = s.sig==='BUY'?t('sig_buy'):s.sig==='SELL'?t('sig_sell'):t('sig_hold');
    const sharpeC = s.sharpe>=1?'var(--green)':s.sharpe>=0?'var(--text)':'var(--red)';
    return `<tr><td><span style="color:var(--cyan);font-family:var(--display);font-weight:700;letter-spacing:0.08em">${s.name}</span> <span style="color:var(--faint);font-size:9px">${s.id}</span></td><td>${t(s.stratKey)}</td><td><span class="${sigCls}">${sigTxt}</span></td><td style="text-align:center">${(s.win*100).toFixed(1)}%</td><td style="text-align:center;color:${sharpeC}">${s.sharpe > 0 ? s.sharpe.toFixed(2) : '--'}</td><td style="text-align:center">${(s.alloc*100).toFixed(1)}%</td></tr>`;
  }).join('');
  $('#flowCount').textContent = '9 sentinels';
}

/* ============ FULL VIEW PANELS ============ */
function renderGauge(){
  const v = STATE.riskScore;
  const cx=50, cy=50, r=38;
  const startA = Math.PI*0.75, endA = Math.PI*2.25;
  const totalA = endA - startA;
  const valA = startA + totalA * Math.min(v/0.6, 1);
  const arc = (a1, a2) => {
    const x1 = cx + Math.cos(a1)*r, y1 = cy + Math.sin(a1)*r;
    const x2 = cx + Math.cos(a2)*r, y2 = cy + Math.sin(a2)*r;
    const large = (a2-a1) > Math.PI ? 1 : 0;
    return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  };
  const color = v < 0.3 ? 'var(--green)' : v < 0.5 ? 'var(--yellow)' : 'var(--red)';
  $('#gaugeRisk').innerHTML = `
    <path d="${arc(startA, endA)}" fill="none" stroke="var(--border)" stroke-width="6" stroke-linecap="round"/>
    <path d="${arc(startA, valA)}" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round"/>
    <text x="50" y="56" text-anchor="middle" fill="var(--text)" font-family="Orbitron" font-weight="900" font-size="14">${v.toFixed(2)}</text>
  `;
  $('#gaugeVal').textContent = v.toFixed(2);
}

function renderHistorian(){
  $('#histHead').innerHTML = ['th_sent','th_win','th_sharpe','th_trades','th_slip','th_decay'].map((k,i)=>`<th${i>0?' style="text-align:center"':''}>${t(k)}</th>`).join('');
  // Frente A — datos reales desde /api/sentinels (s._api guarda el row crudo).
  // total_trades y decay_status vienen agregados por sentinel en sentinel-data.js.
  // slippage por sentinel NO está en /api/sentinels (sí en /api/report.strategy_performance,
  // que el dashboard no consume hoy) — mostramos "—" hasta Frente B.
  $('#histBody').innerHTML = SENTINELS.map((s,i) => {
    const apiRow      = s._api || {};
    const totalTrades = (apiRow.total_trades != null) ? apiRow.total_trades : '—';
    const slip        = '—';
    let decay;
    if (apiRow.decay_status === true)       decay = `<span style="color:var(--red)">YES</span>`;
    else if (apiRow.decay_status === false) decay = `<span style="color:var(--green)">NO</span>`;
    else                                    decay = '—';
    return `<tr><td><span style="color:var(--cyan);font-weight:700">${s.name}</span></td><td style="text-align:center">${s.win > 0 ? (s.win*100).toFixed(0)+'%' : '--'}</td><td style="text-align:center">${s.sharpe > 0 ? s.sharpe.toFixed(2) : '--'}</td><td style="text-align:center">${escapeHtml(totalTrades)}</td><td style="text-align:center">${slip}</td><td style="text-align:center">${decay}</td></tr>`;
  }).join('');
}

function renderAlloc(){
  const max = 0.25;
  $('#allocBars').innerHTML = SENTINELS.map(s => {
    const pct = (s.alloc/max)*100;
    const top25 = (0.25/max)*100;
    const bot5 = (0.05/max)*100;
    return `<div class="alloc-row">
      <span class="name">${s.name}</span>
      <div class="bar"><div class="fill" style="width:${pct}%"></div><div class="top-line" style="left:${top25}%"></div><div class="bot-line" style="left:${bot5}%"></div></div>
      <span class="pct">${(s.alloc*100).toFixed(0)}%</span>
    </div>`;
  }).join('');
}

/* ============ HEADER STATS ============ */
function renderHeader(){
  $('#hRisk').textContent = STATE.riskScore.toFixed(2);
  $('#hRisk').className = 'v ' + (STATE.riskScore<0.3?'green':STATE.riskScore<0.5?'yellow':'red');
  // Frente A — sin endpoint de equity Alpaca, STATE.balance==null y
  // renderEmptyKPIs() escribe "—" en osBalance/osPnl después de renderAll.
  if (STATE.balance != null) {
    $('#osBalance').textContent = fmt(STATE.balance);
    $('#osPnl').textContent = fmt(Math.abs(STATE.balance-100000));
  }
  $('#footUpd').textContent = new Date().toTimeString().slice(0,8);
}

/* ============ LOGS ============ */
function renderLogs(){
  const body = $('#terminalBody'); if (!body) return;
  body.innerHTML = STATE.logs.map((l,i) => {
    const cls = l.lvl==='WARN'?'warn':l.lvl==='ERROR'?'err':'';
    const msg = escapeHtml(l.msg)
      .replace(/SIGNAL BUY/g,  '<span class="sig-buy">SIGNAL BUY</span>')
      .replace(/SIGNAL SELL/g, '<span class="sig-sell">SIGNAL SELL</span>')
      .replace(/SIGNAL HOLD/g, '<span class="sig-hold">SIGNAL HOLD</span>');
    const newCls = (i===STATE.logs.length-1 && l.isNew) ? ' new' : '';
    return `<div class="log-line${newCls}"><span class="ts">${escapeHtml(l.ts)}</span><span class="lvl ${cls}">[${escapeHtml(l.lvl)}]</span><span class="msg">${msg}</span></div>`;
  }).join('');
  body.scrollTop = body.scrollHeight;
  $('#logCount').textContent = STATE.logs.length + ' lines';
  $('#logsCountMeta').textContent = STATE.logs.length + ' lines';
}

function renderAll(){
  renderHeader(); renderAgents(); renderNews(); renderEquity();
  renderSentGrid(); renderDetail();
  renderOps(); renderFlow();
  renderGauge(); renderHistorian(); renderAlloc();
  renderLogs();
}

/* ============ TICK ============ */
function tick(){
  const s = SENTINELS[Math.floor(Math.random()*SENTINELS.length)];
  const sigs = ['BUY','SELL','HOLD','HOLD','HOLD'];
  const newSig = sigs[Math.floor(Math.random()*sigs.length)];
  s.sig = newSig;
  const tk = s.tickers[Math.floor(Math.random()*s.tickers.length)];
  const px = PRICES[tk] || 100;
  const drift = px * (Math.random()*0.004 - 0.002);
  const newPx = +(px + drift).toFixed(2);
  PRICES[tk] = newPx;
  const now = new Date();
  const tsLog = now.toISOString().replace('T',' ').slice(0,19);
  const tsShort = now.toTimeString().slice(0,8);

  const msg = newSig==='HOLD'
    ? `SIGNAL HOLD  :: ${s.name.toLowerCase()} ${tk} px=${newPx}`
    : `SIGNAL ${newSig}   :: ${s.name.toLowerCase()} ${tk} px=${newPx} agent=${s.id}`;
  STATE.logs.push({ts:tsLog, lvl: Math.random()<0.06?'WARN':'INFO', msg, isNew:true});
  if (STATE.logs.length > 60) STATE.logs.shift();

  if (newSig !== 'HOLD') {
    const qty = Math.floor(Math.random()*20+3);
    STATE.trades.unshift({id: STATE.nextId++, sent:s.id, sentName:s.name, ticker:tk, side:newSig, qty, px:newPx, status:'FILLED', ts:tsShort});
    if (STATE.trades.length > 20) STATE.trades.pop();
  }

  const pnl = (Math.random()-0.45)*60;
  STATE.balance = +(STATE.balance + pnl).toFixed(2);
  STATE.balanceChange = +((STATE.balance/100000-1)*100).toFixed(2);
  STATE.equityHist.push(STATE.balance);
  if (STATE.equityHist.length > 80) STATE.equityHist.shift();
  STATE.riskScore = Math.max(0.05, Math.min(0.55, STATE.riskScore + (Math.random()-0.5)*0.04));

  renderAll();
  STATE.logs.forEach(l => l.isNew = false);
  setTimeout(tick, 3000 + Math.random()*2500);
}

/* ============ DOWNLOAD JSON ============ */
function buildReport(range){
  return {
    metadata: {
      generated_at: new Date().toISOString(),
      range,
      system_version: "SENTINEL v0.5"
    },
    system_health: {
      uptime_hours: 168,
      errors_by_module: { dispatcher:0, correlation_guard:1, the_ear:3, historian:0, sentinels:2 },
      reconnections: { alpaca:1, postgresql:0, newsapi:2 },
      circuit_breaker_activations: 0,
      parking_brake_activations: 5
    },
    strategy_performance: SENTINELS.map(s => ({
      sentinel: s.name,
      strategy: t(s.stratKey),
      tickers: s.tickers,
      win_rate: s.win,
      sharpe_ratio: s.sharpe,
      total_trades: 28 + (SENTINELS.indexOf(s)*7)%200,
      slippage_avg: +(0.02+(SENTINELS.indexOf(s)*0.011)%0.06).toFixed(3),
      decay_status: s.id==='S-9',
      allocation_pct: Math.round(s.alloc*100)
    })),
    macro_context: {
      risk_score_avg: STATE.riskScore,
      regime_distribution: { BULL:3, NEUTRAL:12, BEAR:0 },
      news_that_moved_decisions: NEWS.map(n => ({
        timestamp: n.ts, title: t(n.titleKey), impact: t('impact_'+n.impact)
      }))
    },
    correlation_guard: { signals_reduced:5, signals_discarded:2, avg_correlation:0.45 },
    dispatcher: {
      signals_received: 45, signals_approved: 38, signals_rejected: 7,
      rejection_reasons: { risk_score_veto:3, no_open_position:2, high_correlation:2 }
    },
    trades: STATE.trades.map(tr => ({
      id: '#'+tr.id, sentinel: tr.sentName||tr.sent, ticker: tr.ticker,
      side: tr.side, qty: tr.qty, price: tr.px, status: tr.status, timestamp: tr.ts
    }))
  };
}

// Frente A — usa /api/report real (FIX-006). buildReport() arriba sigue
// definido por compatibilidad pero ya no se invoca desde acá.
// /api/report acepta range ∈ {today, last_week, last_month, all}; el
// dropdown del HTML incluye "last_hour" que el backend rechazaría con 422,
// así que mapeamos cualquier value desconocido a "today".
async function downloadReport(){
  const raw   = $('#dlRange').value;
  const valid = new Set(['today','last_week','last_month','all']);
  const range = valid.has(raw) ? raw : 'today';
  try {
    const r = await fetch(`/api/report?range=${encodeURIComponent(range)}`, {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    const data = await r.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `sentinel-report-${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('downloadReport:', e);
    alert('Error al descargar el reporte: ' + e.message);
  }
}

/* ============ EVENTS ============ */
$('#langToggle').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  STATE.lang = b.dataset.lang;
  $$('#langToggle button').forEach(x => x.classList.toggle('active', x===b));
  applyI18n();
});

$('#viewToggle').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  STATE.view = b.dataset.view;
  document.body.dataset.view = STATE.view;
  $$('#viewToggle button').forEach(x => x.classList.toggle('active', x===b));
});

$('#themeBtn').addEventListener('click', () => {
  STATE.theme = STATE.theme==='cyber'?'sober':'cyber';
  document.body.dataset.theme = STATE.theme;
  $('#themeIcon').innerHTML = STATE.theme==='sober'
    ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
    : '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>';
  renderAll();
});

$('#detenerBtn').addEventListener('click', () => alert('SISTEMA DETENIDO (demo)'));

$('#expandAll').addEventListener('click', () => {
  SENTINELS.forEach(s => STATE.expandedDetails.add(s.id));
  renderDetail();
});
$('#collapseAll').addEventListener('click', () => {
  STATE.expandedDetails.clear();
  renderDetail();
});

$('#logsHead').addEventListener('click', () => {
  STATE.logsOpen = !STATE.logsOpen;
  $('#logsSection').classList.toggle('open', STATE.logsOpen);
});

$('#downloadBtn').addEventListener('click', downloadReport);

/* ============ BOOT ============ */
applyI18n();
setTimeout(tick, 2500);
