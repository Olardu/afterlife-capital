/* ============ HELPERS ============ */
const $ = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>[...r.querySelectorAll(s)];
const t = k => (I18N[STATE.lang]||I18N.es)[k] || k;
const fmt = n => n>=1000 ? n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : n.toFixed(2);
const fmt0 = n => n>=1000 ? n.toLocaleString('en-US') : n.toFixed(0);

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

/* ============ EQUITY ============ */
function renderEquity(){
  const data = STATE.equityHist;
  const W=1200, H=240;
  const min = Math.min(...data), max = Math.max(...data);
  const range = (max-min)||1;
  const pts = data.map((v,i) => {
    const x = (i/(data.length-1))*W;
    const y = H - ((v-min)/range)*(H-30) - 15;
    return [x,y];
  });
  const line = pts.map(([x,y],i)=> (i===0?'M':'L') + x.toFixed(1)+' '+y.toFixed(1)).join(' ');
  const area = `M0 ${H} L${pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L')} L${W} ${H} Z`;
  const trend = data[data.length-1] > data[0];
  const stroke = trend ? 'var(--green)' : 'var(--red)';
  const grad = trend ? '#00ff88' : '#ff2060';
  $('#eqChart').innerHTML = `
    <defs><linearGradient id="eqg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${grad}" stop-opacity="0.3"/><stop offset="1" stop-color="${grad}" stop-opacity="0"/></linearGradient></defs>
    <g stroke="rgba(0,245,255,0.06)" stroke-width="0.5">
      <line x1="0" y1="60" x2="${W}" y2="60"/><line x1="0" y1="120" x2="${W}" y2="120"/><line x1="0" y1="180" x2="${W}" y2="180"/>
    </g>
    <path d="${area}" fill="url(#eqg)"/>
    <path d="${line}" fill="none" stroke="${stroke}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>
  `;
  $('#eqCapital').textContent = '$' + fmt(STATE.balance);
  const pnl = STATE.balance - 100000;
  $('#eqPnl').textContent = (pnl>=0?'+':'') + '$' + fmt(Math.abs(pnl));
  $('#eqPnl').className = pnl>=0?'green':'red';
}

/* ============ SENTINEL CARDS ============ */
function renderSentGrid(){
  const grid = $('#sentGrid');
  grid.innerHTML = SENTINELS.map((s, idx) => {
    const pts = [];
    let v = 100;
    for (let i=0;i<24;i++){
      v += (Math.sin(idx*7 + i*1.3) + Math.cos(idx*3 + i*0.7)) * 0.5 + s.sharpe*0.18 + (Math.random()-0.5)*0.4;
      pts.push(v);
    }
    const min=Math.min(...pts), max=Math.max(...pts), rng=(max-min)||1;
    const polyPts = pts.map((vv,i)=>{
      const x = (i/(pts.length-1))*100;
      const y = 100 - ((vv-min)/rng)*90 - 5;
      return x.toFixed(1)+','+y.toFixed(1);
    }).join(' ');
    const trend = pts[pts.length-1] > pts[0];
    const stroke = trend ? '#00ff88' : '#ff2060';
    const fill = trend ? 'rgba(0,255,136,0.12)' : 'rgba(255,32,96,0.12)';
    const sigCls = s.sig.toLowerCase();
    const sigTxt = t('sig_'+sigCls);
    const sharpeC = s.sharpe>=1?'green':s.sharpe>=0?'':'red';
    return `<div class="sent-card" data-detail="${s.id}">
      <div class="top">
        <div><span class="name">${s.name}</span> <span class="sid">${s.id}</span></div>
        <span class="sig ${sigCls}">${sigTxt}</span>
      </div>
      <div class="strat">${t(s.stratKey)}</div>
      <svg class="mini-eq" viewBox="0 0 100 100" preserveAspectRatio="none">
        <polygon points="0,100 ${polyPts} 100,100" fill="${fill}" stroke="none"/>
        <polyline points="${polyPts}" fill="none" stroke="${stroke}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="stats">
        <div class="stat"><span class="k">${t('st_win')}</span><span class="v">${(s.win*100).toFixed(0)}%</span></div>
        <div class="stat"><span class="k">${t('st_sharpe')}</span><span class="v ${sharpeC}">${s.sharpe.toFixed(2)}</span></div>
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

/* ============ DETAIL ACCORDION ============ */
function getQuote(s){
  return ({es:s.quote, en:s.quoteEn, ja:s.quoteJa, th:s.quoteTh})[STATE.lang] || s.quote;
}
function renderDetail(){
  const c = $('#detailContainer');
  c.innerHTML = SENTINELS.map(s => {
    const open = STATE.expandedDetails.has(s.id);
    const tickerRows = s.tickers.map(tk => {
      const sigs = ['BUY','HOLD','SELL'];
      const sig = sigs[Math.abs((tk.charCodeAt(0)+s.id.charCodeAt(2))%3)];
      const sigCls = sig==='BUY'?'sig-buy':sig==='SELL'?'sig-sell':'sig-hold';
      const sigTxt = sig==='BUY'?t('sig_buy'):sig==='SELL'?t('sig_sell'):t('sig_hold');
      const pnl = ((tk.charCodeAt(0)*7) % 280) - 60;
      const win = 0.42 + ((tk.charCodeAt(0)*11)%30)/100;
      const sh = 0.3 + ((tk.charCodeAt(0)*5)%140)/100;
      return `<tr><td style="color:var(--cyan)">${tk}</td><td><span class="${sigCls}">${sigTxt}</span></td><td class="r" style="color:${pnl>=0?'var(--green)':'var(--red)'}">${pnl>=0?'+':'-'}$${Math.abs(pnl)}</td><td class="r">${(win*100).toFixed(0)}%</td><td class="r">${sh.toFixed(2)}</td></tr>`;
    }).join('');

    /* fake last 5 trades */
    const recent = STATE.trades.filter(tr => tr.sent === s.id).slice(0,5);
    const recentRows = recent.length ? recent.map(tr => {
      const sideCls = tr.side==='BUY'?'sig-buy':'sig-sell';
      const sideTxt = tr.side==='BUY'?t('sig_buy'):t('sig_sell');
      return `<tr><td>${tr.ts}</td><td style="color:var(--cyan)">${tr.ticker}</td><td class="${sideCls}">${sideTxt}</td><td class="r">${tr.qty}</td><td class="r">${fmt(tr.px)}</td><td style="color:var(--cyan)">${tr.status}</td></tr>`;
    }).join('') : `<tr><td colspan="6" class="empty">${t('empty_ops')}</td></tr>`;

    return `<div class="detail-block ${open?'open':''}" id="detail-${s.id}">
      <div class="detail-head" data-id="${s.id}">
        <span class="name">${s.name}</span>
        <span class="strat">${t(s.stratKey)}</span>
        <span class="chev">▶</span>
      </div>
      <div class="detail-body">
        <div class="detail-quote">"${getQuote(s)}"<span class="src">— ${s.quoteSrc}</span></div>
        <div class="detail-desc">${t('desc_'+s.stratKey)}</div>
        <div class="dt-subhead">${t('dt_tickers')}</div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr>
          <th>${t('th_ticker')}</th><th>${t('th_signal')}</th><th class="r">${t('th_pnl')}</th><th class="r">${t('th_win')}</th><th class="r">${t('th_sharpe')}</th>
        </tr></thead><tbody>${tickerRows}</tbody></table></div>
        <div class="dt-subhead">${t('dt_recent')}</div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr>
          <th>${t('th_ts')}</th><th>${t('th_ticker')}</th><th>${t('th_side')}</th><th class="r">${t('th_qty')}</th><th class="r">${t('th_px')}</th><th>${t('th_status')}</th>
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
  $('#opsHead').innerHTML = ['th_id','th_sent','th_ticker','th_side','th_qty','th_px','th_status','th_ts'].map(k=>`<th>${t(k)}</th>`).join('');
  const body = $('#opsBody');
  body.innerHTML = STATE.trades.map(tr => {
    const sideCls = tr.side==='BUY'?'sig-buy':'sig-sell';
    const sideTxt = tr.side==='BUY'?t('sig_buy'):t('sig_sell');
    return `<tr><td>#${tr.id}</td><td style="color:var(--cyan)">${tr.sentName||tr.sent}</td><td>${tr.ticker}</td><td class="${sideCls}">${sideTxt}</td><td class="r">${tr.qty}</td><td class="r">${fmt(tr.px)}</td><td style="color:var(--cyan)">${tr.status}</td><td>${tr.ts}</td></tr>`;
  }).join('');
  $('#opsCount').textContent = STATE.trades.length + ' trades';
}

function renderFlow(){
  $('#flowHead').innerHTML = ['th_sent','th_strat','th_signal','th_win','th_sharpe','th_alloc'].map(k=>`<th>${t(k)}</th>`).join('');
  $('#flowBody').innerHTML = SENTINELS.map(s => {
    const sigCls = s.sig==='BUY'?'sig-buy':s.sig==='SELL'?'sig-sell':'sig-hold';
    const sigTxt = s.sig==='BUY'?t('sig_buy'):s.sig==='SELL'?t('sig_sell'):t('sig_hold');
    const sharpeC = s.sharpe>=1?'var(--green)':s.sharpe>=0?'var(--text)':'var(--red)';
    return `<tr><td><span style="color:var(--cyan);font-family:var(--display);font-weight:700;letter-spacing:0.08em">${s.name}</span> <span style="color:var(--faint);font-size:9px">${s.id}</span></td><td>${t(s.stratKey)}</td><td><span class="${sigCls}">${sigTxt}</span></td><td class="r">${(s.win*100).toFixed(1)}%</td><td class="r" style="color:${sharpeC}">${s.sharpe.toFixed(2)}</td><td class="r">${(s.alloc*100).toFixed(1)}%</td></tr>`;
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
  $('#histHead').innerHTML = ['th_sent','th_win','th_sharpe','th_trades','th_slip','th_decay'].map(k=>`<th>${t(k)}</th>`).join('');
  $('#histBody').innerHTML = SENTINELS.map((s,i) => {
    const trades = 28 + (i*7) % 200;
    const slip = (0.02 + (i*0.011)%0.06).toFixed(3);
    const decay = i===8 ? `<span style="color:var(--red)">YES</span>` : `<span style="color:var(--green)">NO</span>`;
    return `<tr><td><span style="color:var(--cyan);font-weight:700">${s.name}</span></td><td class="r">${(s.win*100).toFixed(0)}%</td><td class="r">${s.sharpe.toFixed(2)}</td><td class="r">${trades}</td><td class="r">${slip}</td><td>${decay}</td></tr>`;
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
  $('#osBalance').textContent = fmt(STATE.balance);
  $('#osPnl').textContent = fmt(Math.abs(STATE.balance-100000));
  $('#footUpd').textContent = new Date().toTimeString().slice(0,8);
}

/* ============ LOGS ============ */
function renderLogs(){
  const body = $('#terminalBody'); if (!body) return;
  body.innerHTML = STATE.logs.map((l,i) => {
    const cls = l.lvl==='WARN'?'warn':l.lvl==='ERROR'?'err':'';
    const msg = l.msg
      .replace(/SIGNAL BUY/g,  '<span class="sig-buy">SIGNAL BUY</span>')
      .replace(/SIGNAL SELL/g, '<span class="sig-sell">SIGNAL SELL</span>')
      .replace(/SIGNAL HOLD/g, '<span class="sig-hold">SIGNAL HOLD</span>');
    const newCls = (i===STATE.logs.length-1 && l.isNew) ? ' new' : '';
    return `<div class="log-line${newCls}"><span class="ts">${l.ts}</span><span class="lvl ${cls}">[${l.lvl}]</span><span class="msg">${msg}</span></div>`;
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

function downloadReport(){
  const range = $('#dlRange').value;
  const data = buildReport(range);
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `sentinel_report_${range}_${new Date().toISOString().slice(0,10)}.json`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
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
