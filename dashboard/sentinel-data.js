/* ============================================================ *
 * sentinel-data.js                                              *
 *                                                                *
 * Reemplaza el sentinel-data.js mock del handoff oficial.        *
 * Define las MISMAS globales que sentinel-app.js consume         *
 * (SENTINELS, AGENTS, AGENT_ICONS, NEWS, STATE, PRICES) pero     *
 * las popula con datos reales de la API:                         *
 *   - GET /api/status                                            *
 *   - GET /api/sentinels                                         *
 *   - GET /api/trades?limit=50                                   *
 *   - GET /api/macro                                             *
 *   - GET /api/sse  (push de updates cada 15 min)                *
 *                                                                *
 * El tick mock del handoff (setTimeout(tick, 2500) en app.js)    *
 * se neutraliza interceptando setTimeout antes de que app.js     *
 * cargue. Los datos llegan vía SSE en lugar.                     *
 *                                                                *
 * Las CITAS de los Sentinels y los AGENTES son CONTENIDO FIJO    *
 * del diseño — viajan hardcoded acá (originales del handoff).    *
 * ============================================================ */
"use strict";

/* ============ CONSTANTES HARDCODED DEL DISEÑO ============ */

/* Mapeo strategy_type (API) → stratKey (i18n del handoff) */
const STRATEGY_KEY_MAP = {
  sma_crossover:     "sma_xover",
  rsi_short:         "rsi_short",
  bollinger_bounce:  "bb_bounce",
  macd_volume:       "macd_vol",
  orb_breakout:      "or_breakout",
  ema_triple:        "ema_triple",
  vwap_reversion:    "vwap_revert",
  rsi_divergence:    "rsi_diverg",
  bollinger_squeeze: "bb_squeeze",
};

/* Nombre cyberpunk por strategy_type — fijado en el diseño */
const CYBERPUNK_NAME = {
  sma_crossover:     "MORPHEUS",
  rsi_short:         "MANTIS",
  bollinger_bounce:  "ORACLE",
  macd_volume:       "SILVERHAND",
  orb_breakout:      "SMASHER",
  ema_triple:        "TRINITY",
  vwap_reversion:    "NETRUNNER",
  rsi_divergence:    "NEO",
  bollinger_squeeze: "ROGUE",
};

/* SID por strategy_type (S-1..S-9). Fijado: el orden está en el diseño */
const SID_BY_STRATEGY = {
  sma_crossover:     "S-1",
  rsi_short:         "S-2",
  bollinger_bounce:  "S-3",
  macd_volume:       "S-4",
  orb_breakout:      "S-5",
  ema_triple:        "S-6",
  vwap_reversion:    "S-7",
  rsi_divergence:    "S-8",
  bollinger_squeeze: "S-9",
};

/* Citas Matrix/Cyberpunk + descripciones (contenido editorial fijo del diseño) */
const QUOTES = {
  sma_crossover: {
    quote:"Él ve la señal, sigue la tendencia, guía el camino.", quoteSrc:"Matrix, 1999",
    quoteEn:"He sees the signal, follows the trend, guides the way.",
    quoteJa:"彼はシグナルを見て、トレンドに従い、道を示す。",
    quoteTh:"เขาเห็นสัญญาณ ตามเทรนด์ และนำทาง",
  },
  rsi_short: {
    quote:"Golpe rápido y preciso — entra y sale en un instante.", quoteSrc:"Cyberpunk 2077",
    quoteEn:"A swift, precise strike — in and out in an instant.",
    quoteJa:"素早く正確な一撃 — 一瞬で出入りする。",
    quoteTh:"จู่โจมเร็วและแม่นยำ เข้าออกในชั่วพริบตา",
  },
  bollinger_bounce: {
    quote:"Predice el rebote, sabe que el precio vuelve a la media.", quoteSrc:"Matrix, 1999",
    quoteEn:"Predicts the bounce, knows price returns to the mean.",
    quoteJa:"反発を予測し、価格は平均に戻ると知る。",
    quoteTh:"ทำนายการเด้งกลับ รู้ว่าราคากลับสู่ค่าเฉลี่ย",
  },
  macd_volume: {
    quote:"No actúa sin confirmación — necesita la presencia para moverse.", quoteSrc:"Cyberpunk 2077",
    quoteEn:"Does not act without confirmation — needs presence to move.",
    quoteJa:"確認なしには動かない — 動くには存在が必要。",
    quoteTh:"ไม่เคลื่อนไหวโดยไม่มีการยืนยัน ต้องมีสัญญาณก่อน",
  },
  orb_breakout: {
    quote:"Rompe cualquier barrera — breakout puro.", quoteSrc:"Cyberpunk 2077",
    quoteEn:"Breaks any barrier — pure breakout.",
    quoteJa:"いかなる障壁も打ち砕く — 純粋なブレイクアウト。",
    quoteTh:"ทุบทุกแนวต้าน เบรกเอาต์บริสุทธิ์",
  },
  ema_triple: {
    quote:"Tres fuerzas alineadas. El nombre se pone solo.", quoteSrc:"Matrix, 1999",
    quoteEn:"Three forces aligned. The name speaks for itself.",
    quoteJa:"三つの力が揃う。名前が物語る。",
    quoteTh:"สามแรงเรียงตัว ชื่อนี้บอกตัวเอง",
  },
  vwap_reversion: {
    quote:"Encuentra el valor oculto en los datos.", quoteSrc:"Cyberpunk 2077",
    quoteEn:"Finds the hidden value in the data.",
    quoteJa:"データの中に隠された価値を見つける。",
    quoteTh:"ค้นพบมูลค่าที่ซ่อนอยู่ในข้อมูล",
  },
  rsi_divergence: {
    quote:"Ve lo que otros no ven — la divergencia detrás de la superficie.", quoteSrc:"Matrix, 1999",
    quoteEn:"Sees what others miss — divergence beneath the surface.",
    quoteJa:"他人が見えないものを見る — 表面下のダイバージェンス。",
    quoteTh:"เห็นในสิ่งที่คนอื่นมองข้าม ไดเวอร์เจนซ์ใต้ผิวหน้า",
  },
  bollinger_squeeze: {
    quote:"Espera en silencio hasta el momento perfecto, y entonces actúa.", quoteSrc:"Cyberpunk 2077",
    quoteEn:"Waits silently for the perfect moment, then strikes.",
    quoteJa:"完璧な瞬間まで静かに待ち、そして動く。",
    quoteTh:"รอเงียบ ๆ จนถึงจังหวะที่สมบูรณ์ แล้วลงมือ",
  },
};

/* ============ AGENTES (5) — contenido fijo del diseño ============ */
const AGENTS = [
  { id:"dispatcher",  nameKey:"ag_dispatcher",  subKey:"ag_dispatcher_sub",  descKey:"ag_dispatcher_desc",  active:true,  icon:"dispatcher" },
  { id:"correlation", nameKey:"ag_correlation", subKey:"ag_correlation_sub", descKey:"ag_correlation_desc", active:false, icon:"corr" },
  { id:"the_ear",     nameKey:"ag_the_ear",     subKey:"ag_the_ear_sub",     descKey:"ag_the_ear_desc",     active:true,  icon:"ear" },
  { id:"historian",   nameKey:"ag_historian",   subKey:"ag_historian_sub",   descKey:"ag_historian_desc",   active:false, icon:"hist" },
  { id:"regime",      nameKey:"ag_regime",      subKey:"ag_regime_sub",      descKey:"ag_regime_desc",      active:false, icon:"regime" },
];

/* SVG ICONS — copiados tal cual del handoff */
const AGENT_ICONS = {
  dispatcher: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 4v3M12 17v3M4 12h3M17 12h3M6.3 6.3l2 2M15.7 15.7l2 2M6.3 17.7l2-2M15.7 8.3l2-2"/></svg>',
  corr:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><circle cx="8" cy="12" r="5"/><circle cx="16" cy="12" r="5"/><path d="M11 12h2"/></svg>',
  ear:        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="10" stroke-dasharray="2 2"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>',
  hist:       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"><path d="M3 20V8M9 20V4M15 20v-9M21 20v-6"/><path d="M2 20h20"/></svg>',
  regime:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M12 3l3 5 5 1-4 4 1 6-5-3-5 3 1-6-4-4 5-1z"/></svg>',
};

/* ============ GLOBALES POBLADAS POR LA API ============ */
const SENTINELS = [];   // se llena en loadSentinels()
const NEWS      = [];   // se llena en loadMacro()
const PRICES    = {};   // sin endpoint dedicado — se mantiene vacío

const STATE = {
  lang: 'es', view: 'full', theme: 'cyber',
  trades: [], logs: [],
  // balance/balanceChange neutralizados (Frente A — 2026-04-28). Sin endpoint
  // de equity Alpaca, mostramos "—" en vez de inventar 100000. Cuando exista
  // /api/account/equity (Frente B), repoblar con datos reales y reactivar
  // los renders de osBalance/osPnl/eqCapital/eqPnl.
  balance: null, balanceChange: null,
  riskScore: 0,
  nextId: 1,
  equityHist: [],
  equityTimestamps: [],
  equityBaseValue: 100000,
  equityPeriod: '1D',
  equityLoading: false,
  expandedDetails: new Set(),
  logsOpen: false,
};

/* ============ TICKER NAMES ============ */
const TICKER_NAMES = {
  // Major indices / ETFs
  SPY:  'SPDR S&P 500 ETF Trust',
  QQQ:  'Invesco QQQ Trust (Nasdaq-100)',
  IWM:  'iShares Russell 2000 ETF',
  DIA:  'SPDR Dow Jones Industrial Average ETF',
  VOO:  'Vanguard S&P 500 ETF',
  VTI:  'Vanguard Total Stock Market ETF',
  IVV:  'iShares Core S&P 500 ETF',
  // Sector ETFs
  XLF:  'Financial Select Sector SPDR Fund',
  XLK:  'Technology Select Sector SPDR Fund',
  XLE:  'Energy Select Sector SPDR Fund',
  XLV:  'Health Care Select Sector SPDR Fund',
  XLP:  'Consumer Staples Select Sector SPDR Fund',
  XLY:  'Consumer Discretionary Select Sector SPDR Fund',
  XLI:  'Industrial Select Sector SPDR Fund',
  XLB:  'Materials Select Sector SPDR Fund',
  XLC:  'Communication Services Select Sector SPDR Fund',
  XLU:  'Utilities Select Sector SPDR Fund',
  XLRE: 'Real Estate Select Sector SPDR Fund',
  // Commodities / Safe haven
  GLD:  'SPDR Gold Shares',
  SLV:  'iShares Silver Trust',
  USO:  'United States Oil Fund',
  TLT:  'iShares 20+ Year Treasury Bond ETF',
  SHY:  'iShares 1-3 Year Treasury Bond ETF',
  IEF:  'iShares 7-10 Year Treasury Bond ETF',
  BND:  'Vanguard Total Bond Market ETF',
  // Volatility
  VXX:  'iPath Series B S&P 500 VIX Short-Term Futures ETN',
  VIXY: 'ProShares VIX Short-Term Futures ETF',
  UVXY: 'ProShares Ultra VIX Short-Term Futures ETF',
  SVXY: 'ProShares Short VIX Short-Term Futures ETF',
  // Tech mega-caps
  AAPL: 'Apple Inc.',
  MSFT: 'Microsoft Corporation',
  GOOGL:'Alphabet Inc. (Class A)',
  GOOG: 'Alphabet Inc. (Class C)',
  AMZN: 'Amazon.com Inc.',
  META: 'Meta Platforms Inc.',
  NVDA: 'NVIDIA Corporation',
  TSLA: 'Tesla Inc.',
  AMD:  'Advanced Micro Devices Inc.',
  INTC: 'Intel Corporation',
  AVGO: 'Broadcom Inc.',
  CRM:  'Salesforce Inc.',
  ORCL: 'Oracle Corporation',
  ADBE: 'Adobe Inc.',
  NFLX: 'Netflix Inc.',
  // Other large caps
  JPM:  'JPMorgan Chase & Co.',
  V:    'Visa Inc.',
  MA:   'Mastercard Inc.',
  BAC:  'Bank of America Corporation',
  WMT:  'Walmart Inc.',
  JNJ:  'Johnson & Johnson',
  PG:   'Procter & Gamble Co.',
  UNH:  'UnitedHealth Group Inc.',
  HD:   'The Home Depot Inc.',
  KO:   'The Coca-Cola Company',
  PEP:  'PepsiCo Inc.',
  COST: 'Costco Wholesale Corporation',
  MRK:  'Merck & Co. Inc.',
  ABBV: 'AbbVie Inc.',
  LLY:  'Eli Lilly and Company',
  CVX:  'Chevron Corporation',
  XOM:  'Exxon Mobil Corporation',
  BA:   'The Boeing Company',
  CAT:  'Caterpillar Inc.',
  DIS:  'The Walt Disney Company',
  PYPL: 'PayPal Holdings Inc.',
  SQ:   'Block Inc.',
  COIN: 'Coinbase Global Inc.',
  PLTR: 'Palantir Technologies Inc.',
  SOFI: 'SoFi Technologies Inc.',
  // International / Emerging
  EEM:  'iShares MSCI Emerging Markets ETF',
  EFA:  'iShares MSCI EAFE ETF',
  FXI:  'iShares China Large-Cap ETF',
  // Crypto-adjacent
  MSTR: 'MicroStrategy Inc.',
  MARA: 'Marathon Digital Holdings Inc.',
  RIOT: 'Riot Platforms Inc.',
  // ARK
  ARKK: 'ARK Innovation ETF',
  ARKW: 'ARK Next Generation Internet ETF',
  // Leveraged
  TQQQ: 'ProShares UltraPro QQQ (3x)',
  SQQQ: 'ProShares UltraPro Short QQQ (-3x)',
  SPXL: 'Direxion Daily S&P 500 Bull 3X',
  SPXS: 'Direxion Daily S&P 500 Bear 3X',
};

/**
 * Devuelve HTML de un ticker con tooltip (nombre completo).
 * Tooltip vía div fijo (#tickerTooltip) posicionado por JS.
 * Funciona con hover (desktop) y touch/tap (móvil).
 */
function tickerSpan(sym) {
  const name = TICKER_NAMES[sym] || '';
  if (!name) return `<span class="ticker-sym">${sym}</span>`;
  return `<span class="ticker-sym" data-tip="${name}">${sym}</span>`;
}

/* Universal tooltip — floating div positioned via JS, no overflow issues.
 * Works for .ticker-sym (ticker names) AND .tip-trigger (status, positions, etc.) */
(function initTickerTooltip() {
  function ensureTip() {
    let tip = document.getElementById('tickerTooltip');
    if (!tip) { tip = document.createElement('div'); tip.id = 'tickerTooltip'; document.body.appendChild(tip); }
    return tip;
  }

  let touchActive = false;

  function show(el) {
    const tip = ensureTip();
    const text = el.getAttribute('data-tip');
    if (!text) return;
    tip.textContent = text;
    tip.classList.add('visible');
    const r = el.getBoundingClientRect();
    const tipW = tip.offsetWidth;
    let left = r.left + r.width / 2 - tipW / 2;
    if (left < 8) left = 8;
    if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;
    tip.style.left = left + 'px';
    tip.style.top = (r.top - tip.offsetHeight - 6) + 'px';
  }

  function hide() {
    const tip = document.getElementById('tickerTooltip');
    if (tip) tip.classList.remove('visible');
    touchActive = false;
  }

  const TIP_SEL = '[data-tip]';

  document.addEventListener('mouseover', function(e) {
    const el = e.target.closest(TIP_SEL);
    if (el) show(el); else hide();
  });

  document.addEventListener('mouseout', function(e) {
    if (e.target.closest(TIP_SEL)) hide();
  });

  // Touch: tap to show, tap again or tap elsewhere to hide
  document.addEventListener('touchstart', function(e) {
    const el = e.target.closest(TIP_SEL);
    if (el) {
      e.preventDefault();
      if (touchActive) { hide(); return; }
      show(el);
      touchActive = true;
    } else {
      hide();
    }
  }, { passive: false });
})();

/* ============ INTERCEPT TICK MOCK ============
 * sentinel-app.js termina con `setTimeout(tick, 2500)` que arranca un loop
 * de mutaciones aleatorias. En modo conectado a la API, los updates llegan
 * por SSE — así que interceptamos esa llamada antes de que app.js cargue.
 * ============================================================ */
(function killTickMock() {
  const orig = window.setTimeout;
  window.setTimeout = function(fn, delay, ...rest) {
    if (typeof fn === 'function' && fn.name === 'tick') {
      console.info('[sentinel-data] tick mock interceptado — usando /api/sse');
      return -1;
    }
    return orig.call(window, fn, delay, ...rest);
  };
})();

/* ============ FETCHERS ============ */

// Estado interno para evitar redirects en cascada cuando varios fetch
// reciben 401 simultáneamente al expirar la sesión.
let _redirectingToLogin = false;

async function _fetchJson(url) {
  try {
    const r = await fetch(url);
    if (r.status === 401) {
      if (!_redirectingToLogin) {
        _redirectingToLogin = true;
        window.location.href = '/auth/login';
      }
      return null;
    }
    if (r.status === 403) {
      console.warn(`[sentinel-data] forbidden ${url}`);
      alert('No tenés permisos para esta acción.');
      return null;
    }
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return await r.json();
  } catch (e) {
    console.error(`[sentinel-data] fetch ${url}:`, e);
    return null;
  }
}

async function loadStatus() {
  const data = await _fetchJson('/api/status');
  if (!data) return null;
  STATE.riskScore = Number(data.risk_score) || 0;

  AGENTS.forEach(a => {
    if (a.id === 'dispatcher' || a.id === 'the_ear') {
      a.active = !data.circuit_breaker;
    } else if (a.id === 'regime') {
      a.active = false;     // S-10 desactivado en backend (NEUTRAL fijo)
    }
  });

  // Inyectar valores en pills del header (no las renderiza app.js, son markup estático)
  const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  if (data.system) {
    setText('hSistema', data.system === 'ONLINE' ? 'ONLINE' : data.system);
  }
  if (typeof data.regime === 'string') setText('hRegimen', data.regime);

  // Header counts: actualizar las pills numéricas (.hs .v.cyan que muestran 9/9, 27, 15MIN)
  const hsCyans = document.querySelectorAll('.hdr-stats .hs .v.cyan');
  if (hsCyans.length >= 3) {
    hsCyans[0].textContent = `${data.sentinels_active}/${data.sentinels_total}`;
    hsCyans[1].textContent = String(data.tickers_total ?? '—');
    hsCyans[2].textContent = data.refresh_interval || '15MIN';
  }

  // Frente A — renderers que consumen el mismo /api/status:
  renderAgentsActiveCount();
  renderCircuitBreakerToggle(!!data.circuit_breaker);
  renderParkingBrakeToggle(!!data.parking_brake);

  return data;
}

async function loadSentinels() {
  const data = await _fetchJson('/api/sentinels');
  if (!data) return null;

  // Ordenar por SID (S-1..S-9) usando el strategy_type
  const ordered = [...data].sort((a, b) => {
    const aSid = SID_BY_STRATEGY[a.strategy_type] || 'S-9';
    const bSid = SID_BY_STRATEGY[b.strategy_type] || 'S-9';
    return parseInt(aSid.slice(2)) - parseInt(bSid.slice(2));
  });

  const mapped = ordered.map(s => {
    const stratKey = STRATEGY_KEY_MAP[s.strategy_type] || s.strategy_type;
    const name     = CYBERPUNK_NAME[s.strategy_type] || s.name;
    const id       = SID_BY_STRATEGY[s.strategy_type] || `S-?`;
    const tickers  = (s.tickers || []).map(t => t.ticker);

    // sig: tomar el primero ≠ HOLD si existe, sino el primero
    const tList = s.tickers || [];
    const nonHold = tList.find(t => t.last_signal && t.last_signal !== 'HOLD');
    const sig = (nonHold ? nonHold.last_signal : (tList[0]?.last_signal)) || 'HOLD';

    // win/sharpe: promedio ponderado por trades (excluye tickers sin datos)
    const wins = tList.map(t => Number(t.win_rate) || 0).filter(x => x > 0);
    const win  = wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;

    // Sharpe: ponderado por total_trades para reflejar peso real de cada ticker
    let sharpe = 0;
    {
      let wSum = 0, tSum = 0;
      for (const t of tList) {
        const sh = Number(t.sharpe_ratio) || 0;
        const tr = Number(t.total_trades) || 0;
        if (tr > 0) { wSum += sh * tr; tSum += tr; }
      }
      sharpe = tSum > 0 ? wSum / tSum : 0;
    }

    const alloc = (Number(s.allocation_pct) || 0) / 100;

    const q = QUOTES[s.strategy_type] || {};

    return {
      id, name, stratKey, tickers, sig, win, sharpe, alloc,
      quote: q.quote || '', quoteSrc: q.quoteSrc || '',
      quoteEn: q.quoteEn || '', quoteJa: q.quoteJa || '', quoteTh: q.quoteTh || '',
      _api: s,                  // referencia opcional al row crudo
    };
  });

  // Mutar in-place para preservar la referencia global que app.js usa
  SENTINELS.length = 0;
  mapped.forEach(s => SENTINELS.push(s));
  return mapped;
}

async function loadTrades() {
  const data = await _fetchJson('/api/trades?limit=50');
  if (!data) return null;

  // Construir mapeo nombre cyberpunk → SID para el campo `sent`
  const nameToSid = {};
  SENTINELS.forEach(s => { nameToSid[s.name] = s.id; });
  // También indexar por nombre original ("S-1 SMA Crossover", etc.)
  // para cuando la API trae el name técnico
  const tecnicoToSid = {};
  Object.entries(SID_BY_STRATEGY).forEach(([strat, sid]) => {
    tecnicoToSid[strat] = sid;
  });

  STATE.trades = data.map((t, i) => {
    const apiName = t.sentinel_name || '';
    // Detectar SID: el name de la API es "S-1 SMA Crossover" → extraer "S-1"
    const sidMatch = apiName.match(/^S-\d+/);
    const sid  = sidMatch ? sidMatch[0] : (nameToSid[apiName] || 'S-?');
    // Para sentName usar el cyberpunk si lo tenemos
    const sentinel = SENTINELS.find(s => s.id === sid);
    const sentName = sentinel ? sentinel.name : apiName;
    return {
      id: 1000 + (data.length - i),                  // descendente como el handoff
      sent: sid,
      sentName,
      ticker: t.ticker,
      side:   t.side,
      qty:    Number(t.qty) || 0,
      px:     Number(t.filled_price) || 0,
      status: t.status || 'PENDING',
      ts:     ((t.created_at || '').slice(5, 10) + ' ' + (t.created_at || '').slice(11, 16)),  // MM-DD HH:MM
    };
  });
  STATE.nextId = 1000 + data.length + 1;

  // equityHist sintético desde trades (placeholder hasta que haya FIFO real)
  STATE.equityHist = synthEquityHist(STATE.trades);
  return data;
}

function synthEquityHist(trades) {
  // Curva de equity real: acumula PnL desde trades FILLED con precio.
  // Usa filled_price para construir la curva. Sin trades = linea plana.
  const filled = trades.filter(t => t.status === 'FILLED' && t.px > 0);
  if (!filled.length) {
    return [100000, 100000, 100000, 100000];
  }
  let acc = 100000;
  const ordered = [...filled].reverse();   // ASC por created_at
  return [100000, ...ordered.map(t => {
    // Aproximacion: BUY resta, SELL suma (proporcional al precio)
    const delta = t.side === 'SELL' ? (t.px * t.qty * 0.01) : -(t.px * t.qty * 0.01);
    acc += delta;
    return acc;
  })];
}

/* ============ PORTFOLIO HISTORY (Alpaca read-only) ============ */
async function fetchPortfolioHistory(period) {
  if (STATE.equityLoading) return;
  STATE.equityLoading = true;
  STATE.equityPeriod = period || STATE.equityPeriod;

  // Map 1Y to 1A for Alpaca API
  const apiPeriod = STATE.equityPeriod === '1Y' ? '1A' : STATE.equityPeriod;

  try {
    const data = await _fetchJson('/api/account/portfolio-history?period=' + apiPeriod);
    if (data && data.equity && data.equity.length > 1) {
      STATE.equityHist = data.equity;
      STATE.equityTimestamps = data.timestamps || [];
      STATE.equityBaseValue = data.base_value || data.equity[0] || 100000;

      // Update KPIs from latest point
      const latest = data.equity[data.equity.length - 1];
      const base = STATE.equityBaseValue;
      const pnl = latest - base;
      const sign = pnl >= 0 ? '+' : '-';

      const eqCapEl = document.getElementById('eqCapital');
      const eqPnlEl = document.getElementById('eqPnl');
      if (eqCapEl) eqCapEl.textContent = '$' + latest.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      if (eqPnlEl) {
        eqPnlEl.textContent = sign + '$' + Math.abs(pnl).toFixed(2);
        eqPnlEl.className = pnl >= 0 ? 'green' : 'red';
      }
    } else {
      // Fallback a sintético
      STATE.equityHist = synthEquityHist(STATE.trades);
      STATE.equityBaseValue = 100000;
      STATE.equityTimestamps = [];
    }
  } catch (e) {
    console.warn('[sentinel-data] fetchPortfolioHistory error:', e);
    STATE.equityHist = synthEquityHist(STATE.trades);
    STATE.equityBaseValue = 100000;
    STATE.equityTimestamps = [];
  }
  STATE.equityLoading = false;

  // Re-render equity chart
  if (typeof renderEquity === 'function') renderEquity();
}

async function loadMacro() {
  // /api/macro_events trae los eventos con news_titles JSONB ya parseados —
  // shape diferente a /api/macro. Si falla (sesión expirada, endpoint no
  // existe en bot pre-FIX-010), caemos al endpoint legacy.
  let events = await _fetchJson('/api/macro_events?limit=10');
  if (!Array.isArray(events)) {
    const legacy = await _fetchJson('/api/macro');
    if (!legacy) return null;
    events = (legacy.recent_events || []).map(ev => ({
      created_at:      ev.created_at,
      risk_score:      ev.risk_score,
      vix_change:      ev.vix_level,
      spy_change:      ev.spy_change_15min,
      circuit_breaker: ev.circuit_breaker_triggered,
      news_titles:     [],
    }));
  }

  const view = events.slice(0, 6);

  // Inyectar títulos al I18N como keys dinámicas (sentinel-app.js usa
  // t(n.titleKey) — necesitamos que la lookup resuelva). Si el evento
  // tiene news_titles[], usamos el primer titular real (#FIX-010); si no,
  // fallback al formato sintético bilingüe original.
  view.forEach((ev, i) => {
    const k = `_news_dyn_${i}`;
    const risk = Number(ev.risk_score) || 0;
    const vix  = ev.vix_change == null ? null : Number(ev.vix_change);
    const spy  = ev.spy_change == null ? null : Number(ev.spy_change);

    const titles = Array.isArray(ev.news_titles) ? ev.news_titles : [];
    const realTitle = titles.length > 0 ? String(titles[0].title || '').trim() : '';

    const fallback = (lang) => {
      const labels = {
        es: 'Macro update — risk', en: 'Macro update — risk',
        ja: 'マクロ更新 — リスク',  th: 'อัปเดตมาโคร — ความเสี่ยง',
      };
      return `${labels[lang]} ${risk.toFixed(2)}`
        + (vix != null ? ` · VIX Δ${vix.toFixed(1)}%` : '')
        + (spy != null ? ` · SPY Δ${spy.toFixed(1)}%` : '');
    };

    // Si hay titular real, mostrar el titular tal cual (los titulares
    // de NewsAPI vienen en inglés — Design puede iterar sobre traducción
    // automática en una próxima versión). Misma string en los 4 idiomas
    // para consistencia.
    const finalTxt = (lang) => realTitle ? realTitle : fallback(lang);

    if (typeof I18N === 'object') {
      for (const lang of ['es', 'en', 'ja', 'th']) {
        if (I18N[lang]) I18N[lang][k] = finalTxt(lang);
      }
    }
  });

  NEWS.length = 0;
  view.forEach((ev, i) => {
    const ts = (ev.created_at || '').slice(11, 16);   // HH:MM
    const risk = Number(ev.risk_score) || 0;
    const impact = ev.circuit_breaker ? 'cb' : (risk > 0.5 ? 'risk' : 'neutral');
    NEWS.push({ ts, titleKey: `_news_dyn_${i}`, impact });
  });

  // Logs sintéticos a partir de los mismos macro events
  STATE.logs = events.slice(0, 30).map(ev => {
    const ts = (ev.created_at || '').replace('T', ' ').slice(0, 19);
    const risk = Number(ev.risk_score) || 0;
    const lvl = ev.circuit_breaker ? 'ERROR' : (risk > 0.5 ? 'WARN' : 'INFO');
    const vixStr = ev.vix_change == null ? '—' : Number(ev.vix_change).toFixed(2);
    const spyStr = ev.spy_change == null ? '—' : Number(ev.spy_change).toFixed(2);
    const cbStr  = ev.circuit_breaker ? 'true' : 'false';
    const titles = Array.isArray(ev.news_titles) ? ev.news_titles : [];
    const tail   = titles.length > 0 ? ` titles=${titles.length}` : '';
    const msg = `EAR :: risk_score=${risk.toFixed(4)} vix=${vixStr} spy=${spyStr} circuit_breaker=${cbStr}${tail}`;
    return { ts, lvl, msg };
  });

  return events;
}

/* ============ ORQUESTACIÓN ============ */

async function reloadFromAPI() {
  // status primero (afecta AGENTS active), después sentinels (sirven mapping de
  // sentName en trades), luego trades + macro en paralelo. Kill switch state
  // se refresca también — el toggle del botón depende del flag system_halted.
  await loadStatus();
  await loadSentinels();
  await Promise.all([loadTrades(), loadMacro(), refreshKillSwitchState()]);

  if (typeof renderAll === 'function') {
    try { renderAll(); } catch (e) { console.error('[sentinel-data] renderAll:', e); }
  }
  // Frente B -- poblar KPIs con datos reales de Alpaca (/api/account/equity)
  if (typeof fetchAndRenderKPIs === 'function') {
    try { await fetchAndRenderKPIs(); } catch (e) { console.error('[sentinel-data] fetchAndRenderKPIs:', e); }
  }
  // Capital card (Excepción 1.2): rentabilidad sobre capital invertido real.
  if (typeof loadCapitalMetrics === 'function') {
    try { await loadCapitalMetrics(); } catch (e) { console.error('[sentinel-data] loadCapitalMetrics:', e); }
  }
  // Footer "Actualizado HH:MM:SS"
  const upd = document.getElementById('footUpd');
  if (upd) upd.textContent = new Date().toTimeString().slice(0, 8);

  // Cargar curva de equity real desde Alpaca (evita el flash de synthEquityHist)
  if (typeof fetchPortfolioHistory === 'function') {
    try { await fetchPortfolioHistory(STATE.equityPeriod || '1D'); } catch (e) { console.error('[sentinel-data] fetchPortfolioHistory:', e); }
  }
}

let _sse = null;
function connectSSE() {
  if (_sse) { try { _sse.close(); } catch(_){} }
  try {
    _sse = new EventSource('/api/sse');
    _sse.addEventListener('update', () => {
      reloadFromAPI();
    });
    _sse.addEventListener('error', () => {
      // El navegador re-conecta automáticamente (por defecto cada 3s)
    });
  } catch (e) {
    console.error('[sentinel-data] SSE connect:', e);
  }
}

/* ============ PERSISTENCIA lang/view/theme ============
 * sentinel-app.js NO toca localStorage. Lo hacemos acá vía event delegation.
 * ============================================================ */
function setupPersistence() {
  // Cargar de localStorage
  const lang  = localStorage.getItem('sentinel.lang')  || 'es';
  const view  = localStorage.getItem('sentinel.view')  || 'full';
  const theme = localStorage.getItem('sentinel.theme') || 'cyber';
  STATE.lang = lang; STATE.view = view; STATE.theme = theme;
  document.body.dataset.view  = view;
  document.body.dataset.theme = theme;

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#langToggle button').forEach(b => {
      b.classList.toggle('active', b.dataset.lang === lang);
    });
    document.querySelectorAll('#viewToggle button').forEach(b => {
      b.classList.toggle('active', b.dataset.view === view);
    });
    // El theme icon ya queda OK porque app.js lo setea según STATE.theme al click;
    // al boot inicial el icon corresponde al cyber por default del HTML, lo
    // refrescamos si el usuario tenía sober persistido.
    if (theme === 'sober') {
      const icon = document.getElementById('themeIcon');
      if (icon) icon.innerHTML =
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
    }

    const brand = document.querySelector('header .brand');
    if (brand) {
      brand.style.cursor = 'pointer';
      brand.setAttribute('role', 'link');
      brand.setAttribute('tabindex', '0');
      brand.setAttribute('aria-label', 'Afterlife Capital — landing');
      const goLanding = () => window.open('https://www.afterlifecapital.co', '_blank', 'noopener,noreferrer');
      brand.addEventListener('click', goLanding);
      brand.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goLanding(); }
      });
    }
  });

  // Guardar al click (event delegation, después de los handlers de app.js)
  document.addEventListener('click', (e) => {
    const lb = e.target.closest('#langToggle button');
    if (lb && lb.dataset.lang) localStorage.setItem('sentinel.lang', lb.dataset.lang);
    const vb = e.target.closest('#viewToggle button');
    if (vb && vb.dataset.view) localStorage.setItem('sentinel.view', vb.dataset.view);
    const tb = e.target.closest('#themeBtn');
    if (tb) {
      // app.js cambia el dataset.theme antes de propagarse — leer post-tick
      setTimeout(() => {
        if (document.body.dataset.theme) {
          localStorage.setItem('sentinel.theme', document.body.dataset.theme);
        }
      }, 0);
    }
  });

}

/* ============ KILL SWITCH — botón DETENER / INICIAR ============
 * sentinel-app.js (handoff) registra `$('#detenerBtn').addEventListener('click', alert(demo))`
 * en el target. En el target, los listeners corren en orden de REGISTRO,
 * así que un addEventListener(..., useCapture=true) sobre el botón mismo
 * NO antecede al del handoff. La forma correcta de interceptar antes es
 * registrar en `document` con capture=true (event delegation): la fase
 * capture del documento corre ANTES de la fase target, y
 * stopImmediatePropagation() evita que el evento alcance el listener del
 * handoff.
 *
 * Toggle visual: cuando system_halted=true, el botón cambia a verde con
 * texto INICIAR. Para que applyI18n() del handoff no pise el texto al
 * cambiar idioma, mutamos el `data-i18n` del botón entre `btn_detener` y
 * la key dinámica `btn_iniciar` (inyectada al I18N en boot).
 * (#H-7)
 * ============================================================ */

const BTN_HALTED_LABELS = {
  es: '+ INICIAR', en: '+ START', ja: '+ 開始', th: '+ เริ่ม',
};

let _systemHalted = false;

function _injectKillSwitchAssets() {
  // Keys i18n para el modo INICIAR (verde). Se evalúa cada vez por seguridad
  // ante un re-load de I18N, pero typeof I18N nunca cambia tras boot.
  if (typeof I18N === 'object') {
    for (const lang of Object.keys(BTN_HALTED_LABELS)) {
      if (I18N[lang]) I18N[lang]['btn_iniciar'] = BTN_HALTED_LABELS[lang];
    }
  }
  // CSS para el estado verde — !important para anteceder al CSS del handoff.
  if (!document.getElementById('sentinel-killswitch-style')) {
    const style = document.createElement('style');
    style.id = 'sentinel-killswitch-style';
    style.textContent = `
      #detenerBtn.system-halted {
        background: #00ff88 !important;
        border-color: #00ff88 !important;
        color: #030610 !important;
        text-shadow: none !important;
      }
    `;
    document.head.appendChild(style);
  }
}

function _setKillSwitchUI(halted) {
  _systemHalted = !!halted;
  const btn = document.getElementById('detenerBtn');
  if (!btn) return;
  if (halted) {
    btn.classList.add('system-halted');
    btn.dataset.i18n = 'btn_iniciar';
  } else {
    btn.classList.remove('system-halted');
    btn.dataset.i18n = 'btn_detener';
  }
  // Refrescar texto vía applyI18n del handoff si está disponible.
  if (typeof applyI18n === 'function') {
    try { applyI18n(); } catch (_) { /* ignore */ }
  } else if (typeof t === 'function') {
    btn.textContent = t(btn.dataset.i18n);
  }
}

async function refreshKillSwitchState() {
  try {
    const res = await fetch('/api/system/state');
    if (res.status === 401) { window.location.href = '/auth/login'; return; }
    if (!res.ok) return;
    const data = await res.json();
    _setKillSwitchUI(!!data.system_halted);
  } catch (e) {
    console.warn('[sentinel-data] refreshKillSwitchState:', e);
  }
}

function setupKillSwitch() {
  _injectKillSwitchAssets();

  document.addEventListener('click', async (e) => {
    if (!e.target.closest('#detenerBtn')) return;
    e.stopImmediatePropagation();
    e.preventDefault();

    if (_systemHalted) {
      // Modo INICIAR — pedir resume
      const ok = confirm(
        '▶ INICIAR SISTEMA\n\n' +
        '¿Reactivar el trading? El Dispatcher volverá a procesar señales.'
      );
      if (!ok) return;
      try {
        const res  = await fetch('/api/system/resume', { method: 'POST' });
        if (res.status === 401) { window.location.href = '/auth/login'; return; }
        if (res.status === 403) { alert('No tenés permisos para esta acción.'); return; }
        const data = await res.json();
        if (data.status === 'resume_requested') {
          alert('Sistema reactivándose. En máximo 5 segundos vuelve a operar.');
          // Optimistic: el SSE/refresh confirmará pero adelantamos UI
          setTimeout(refreshKillSwitchState, 6000);
        } else if (data.status === 'already_running') {
          alert('El sistema ya está activo.');
          _setKillSwitchUI(false);
        } else {
          alert('Respuesta inesperada: ' + JSON.stringify(data));
        }
      } catch (err) {
        alert('Error al contactar la API: ' + err.message);
      }
      return;
    }

    // Modo DETENER — pedir halt
    const ok = confirm(
      '⚠ KILL SWITCH\n\n' +
      '¿Detener el sistema?\n\n' +
      'Esto cancela las órdenes pendientes y cierra las posiciones abiertas.'
    );
    if (!ok) return;
    try {
      const res  = await fetch('/api/system/halt', { method: 'POST' });
      if (res.status === 401) { window.location.href = '/auth/login'; return; }
      if (res.status === 403) { alert('No tenés permisos para esta acción.'); return; }
      const data = await res.json();
      if (data.status === 'halt_requested') {
        alert('Kill switch activado. Posiciones cerrándose en máximo 5 segundos.');
        setTimeout(refreshKillSwitchState, 6000);
      } else if (data.status === 'already_halted') {
        alert('El sistema ya está detenido.');
        _setKillSwitchUI(true);
      } else {
        alert('Respuesta inesperada: ' + JSON.stringify(data));
      }
    } catch (err) {
      alert('Error al contactar la API: ' + err.message);
    }
  }, true);
}

function hideDetenerForViewer() {
  const btn = document.getElementById('detenerBtn');
  if (btn) {
    btn.style.display = 'none';
  } else {
    setTimeout(hideDetenerForViewer, 200);
  }
}

/* ============ ADMIN LINK ============
 * Si el usuario logueado tiene role=ADMIN, inyectamos un badge "ADMIN" en
 * el header del dashboard que linkea a /admin. Para VIEWER NO se muestra
 * el link (no debe siquiera saber que /admin existe).
 * ============================================================ */
async function setupAdminLink() {
  try {
    const r = await fetch('/auth/me');
    if (r.status === 401) return;   // sin sesión — el resto del flujo redirige
    if (!r.ok) return;
    const me = await r.json();
    // Guardar role para que otros módulos (e.g. setupRotationsBanner)
    // condicionen UI sin volver a hacer fetch a /auth/me.
    if (me && me.role) window._userRole = me.role;
    if (!me || me.role !== 'ADMIN') {
      // VIEWER no puede operar el kill switch — ocultar botón DETENER.
      // setupAdminLink() puede correr antes de que el DOM tenga #detenerBtn
      // (script en head + parseo HTML en curso). Reintentamos cada 200ms
      // hasta encontrarlo.
      hideDetenerForViewer();
      return;
    }

    if (!document.getElementById('sentinel-adminlink-style')) {
      const style = document.createElement('style');
      style.id = 'sentinel-adminlink-style';
      style.textContent = `
        #adminLink {
          display: inline-block;
          margin-right: 10px;
          padding: 6px 12px;
          color: #ff00ff;
          border: 1px solid #ff00ff;
          background: transparent;
          font-family: 'Orbitron', sans-serif;
          font-size: 11px;
          letter-spacing: 2px;
          text-decoration: none;
          font-weight: 700;
          transition: background 0.15s;
        }
        #adminLink:hover { background: rgba(255,0,255,0.08); }
      `;
      document.head.appendChild(style);
    }

    const detener = document.getElementById('detenerBtn');
    if (!detener || detener.parentElement.querySelector('#adminLink')) return;
    const a = document.createElement('a');
    a.id = 'adminLink';
    a.href = '/admin';
    a.textContent = 'ADMIN';
    a.title = 'Panel de administración de usuarios';
    detener.parentElement.insertBefore(a, detener);
  } catch (e) {
    console.warn('[sentinel-data] setupAdminLink:', e);
  }
}

/* ============ ROTATIONS BANNER (#UNIVERSE-SELECTION) ============ *
 * Muestra una franja discreta debajo del header cuando hubo una rotación
 * automática de Sentinel en las últimas 24h. Visible para todos los roles;
 * el link "Ver detalle" sólo aparece si el usuario es ADMIN (consume
 * setupAdminLink que ya hace fetch a /auth/me y guarda window._userRole).
 * ============================================================ */

const ROTATIONS_RECENCY_MS = 24 * 60 * 60 * 1000;   // 24h
const ROTATIONS_REFRESH_MS = 5 * 60 * 1000;         // refrescar cada 5 min
const ROTATIONS_STYLE_ID   = 'sentinel-rotations-banner-style';
const ROTATIONS_BANNER_ID  = 'rotationsBanner';

function _injectRotationsStyles() {
  if (document.getElementById(ROTATIONS_STYLE_ID)) return;
  const css = `
    #${ROTATIONS_BANNER_ID} {
      display: flex; align-items: center; justify-content: center; gap: 14px;
      padding: 10px 18px;
      background: linear-gradient(90deg, rgba(255,0,212,0.08), rgba(0,245,255,0.04));
      border-bottom: 1px solid rgba(255,0,212,0.32);
      font-family: 'Share Tech Mono', monospace;
      font-size: 12px; letter-spacing: 0.10em; color: #d8e6f5;
      flex-wrap: wrap;
    }
    #${ROTATIONS_BANNER_ID} .rb-tag {
      color: #ff00d4; font-weight: bold; letter-spacing: 0.18em;
      text-shadow: 0 0 6px rgba(255,0,212,0.5);
    }
    #${ROTATIONS_BANNER_ID} .rb-arrow { color: #00f5ff; padding: 0 4px; }
    #${ROTATIONS_BANNER_ID} .rb-old   { color: #ff8aa0; }
    #${ROTATIONS_BANNER_ID} .rb-new   { color: #00ff88; font-weight: bold; }
    #${ROTATIONS_BANNER_ID} .rb-time  { color: #6a7a96; font-size: 11px; }
    #${ROTATIONS_BANNER_ID} a.rb-link {
      color: #ff00d4; text-decoration: none; border: 1px solid rgba(255,0,212,0.5);
      padding: 4px 10px; font-size: 10px; letter-spacing: 0.16em;
      transition: all 0.15s;
    }
    #${ROTATIONS_BANNER_ID} a.rb-link:hover {
      background: rgba(255,0,212,0.1); border-color: #ff00d4;
    }
    #${ROTATIONS_BANNER_ID} button.rb-close {
      background: transparent; border: none; color: #6a7a96; cursor: pointer;
      font-family: inherit; font-size: 14px; padding: 0 4px;
    }
    #${ROTATIONS_BANNER_ID} button.rb-close:hover { color: #ff2060; }
  `;
  const style = document.createElement('style');
  style.id = ROTATIONS_STYLE_ID;
  style.textContent = css;
  document.head.appendChild(style);
}

function _formatRelative(iso) {
  if (!iso) return '';
  const ts = new Date(iso).getTime();
  const diff = Date.now() - ts;
  if (diff < 0) return 'recién';
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'recién';
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.floor(mins / 60);
  return `hace ${hrs}h`;
}

let _rotationsHidden = false;

async function setupRotationsBanner() {
  _injectRotationsStyles();

  const fetchAndRender = async () => {
    if (_rotationsHidden) return;
    let rotations = [];
    try {
      const r = await fetch('/api/rotations/recent?limit=5', {
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      if (!r.ok) return;
      rotations = await r.json();
    } catch (e) {
      console.debug('[sentinel-data] rotations fetch:', e);
      return;
    }
    if (!Array.isArray(rotations) || rotations.length === 0) return;

    // Solo mostrar si la rotación es reciente (24h)
    const recent = rotations
      .filter(rot => rot.executed_at &&
        (Date.now() - new Date(rot.executed_at).getTime()) < ROTATIONS_RECENCY_MS)
      .slice(0, 1);
    if (recent.length === 0) return;
    const rot = recent[0];

    // Insertar banner debajo del header
    let banner = document.getElementById(ROTATIONS_BANNER_ID);
    if (!banner) {
      banner = document.createElement('div');
      banner.id = ROTATIONS_BANNER_ID;
      const header = document.querySelector('header.header-fixed') ||
                     document.querySelector('.header-fixed') ||
                     document.body.firstElementChild;
      if (header && header.parentNode) {
        header.parentNode.insertBefore(banner, header.nextSibling);
      } else {
        document.body.insertBefore(banner, document.body.firstChild);
      }
    }

    const isAdmin = window._userRole === 'ADMIN';
    const detailLink = isAdmin
      ? `<a class="rb-link" href="/admin#rotations" target="_blank" rel="noopener">VER DETALLE</a>`
      : '';

    const sentinelName = (rot.sentinel_name || 'Sentinel');
    banner.innerHTML = `
      <span class="rb-tag">⟲ ROTATION</span>
      <span>${escapeText(sentinelName)}:</span>
      <span class="rb-old">${escapeText(rot.old_ticker || '?')}</span>
      <span class="rb-arrow">→</span>
      <span class="rb-new">${escapeText(rot.new_ticker || '?')}</span>
      <span class="rb-time">${_formatRelative(rot.executed_at)}</span>
      ${detailLink}
      <button class="rb-close" title="Ocultar">×</button>
    `;
    banner.querySelector('.rb-close').addEventListener('click', () => {
      _rotationsHidden = true;
      banner.remove();
    });
  };

  function escapeText(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
    }[c]));
  }

  // Primera carga + refresh periódico
  fetchAndRender();
  setInterval(fetchAndRender, ROTATIONS_REFRESH_MS);
}

/* ============ MARKET STATUS INDICATOR (#FIX-011) ============ *
 * Inserta una columna nueva en .hdr-stats con label "MERCADO" + valor
 * "ABIERTO"/"CERRADO" + sub-línea "cierra en Xh Ym" / "abre en Xh Ym".
 *
 * Fetch a /api/market-status (público) al boot + refresh cada 60s.
 * El countdown se actualiza cliente-side cada 60s sin re-fetch hasta
 * que llega un fetch nuevo.
 * ============================================================ */

const MARKET_STATUS_REFRESH_MS = 60_000;
const MARKET_STATUS_STYLE_ID   = 'sentinel-market-status-style';
const MARKET_HS_ID             = 'hMercado';

let _marketState = {
  is_open: null,
  status: null,
  next_open_ms: null,
  next_close_ms: null,
};

function _injectMarketStatusStyles() {
  if (document.getElementById(MARKET_STATUS_STYLE_ID)) return;
  const css = `
    #${MARKET_HS_ID} .v { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.1; }
    #${MARKET_HS_ID} .v .label { letter-spacing: 0.04em; font-weight: 700; }
    #${MARKET_HS_ID} .v .countdown { font-size: 9px; color: var(--dim); letter-spacing: 0.04em; margin-top: 2px; }
    #${MARKET_HS_ID} .v.open    .label { color: var(--green); }
    #${MARKET_HS_ID} .v.closed  .label { color: var(--red); opacity: 0.85; }
    #${MARKET_HS_ID} .v.pre     .label { color: var(--yellow); }
    #${MARKET_HS_ID} .v.after   .label { color: var(--magenta); }
  `;
  const style = document.createElement('style');
  style.id = MARKET_STATUS_STYLE_ID;
  style.textContent = css;
  document.head.appendChild(style);
}

function _formatCountdown(ms) {
  if (ms == null || isFinite(ms) === false || ms < 0) return '';
  const totalMin = Math.floor(ms / 60000);
  if (totalMin < 60) return `${totalMin}m`;
  const totalHrs = Math.floor(totalMin / 60);
  const mins     = totalMin % 60;
  if (totalHrs < 24) return `${totalHrs}h ${mins}m`;
  const days = Math.floor(totalHrs / 24);
  const hrs  = totalHrs % 24;
  return `${days}d ${hrs}h`;
}

function _renderMarketIndicator() {
  const el = document.getElementById(MARKET_HS_ID);
  if (!el) return;
  const v = el.querySelector('.v');
  if (!v) return;

  // Sin datos todavía
  if (_marketState.status == null) {
    v.className = 'v';
    v.innerHTML = '<span class="label">…</span>';
    return;
  }

  const now = Date.now();
  let label, klass, countdown;
  if (_marketState.status === 'OPEN') {
    label = 'ABIERTO';
    klass = 'open';
    const ms = _marketState.next_close_ms != null ? _marketState.next_close_ms - now : null;
    countdown = ms != null ? `cierra en ${_formatCountdown(ms)}` : '';
  } else if (_marketState.status === 'PRE_MARKET') {
    label = 'PRE-MERCADO';
    klass = 'pre';
    const ms = _marketState.next_open_ms != null ? _marketState.next_open_ms - now : null;
    countdown = ms != null ? `abre en ${_formatCountdown(ms)}` : '';
  } else if (_marketState.status === 'AFTER_HOURS') {
    label = 'POST-MERCADO';
    klass = 'after';
    const ms = _marketState.next_open_ms != null ? _marketState.next_open_ms - now : null;
    countdown = ms != null ? `abre en ${_formatCountdown(ms)}` : '';
  } else {
    label = 'CERRADO';
    klass = 'closed';
    const ms = _marketState.next_open_ms != null ? _marketState.next_open_ms - now : null;
    countdown = ms != null ? `abre en ${_formatCountdown(ms)}` : '';
  }

  v.className = `v ${klass}`;
  const safeLabel = String(label).replace(/[<>&]/g, '');
  const safeCd    = String(countdown).replace(/[<>&]/g, '');
  v.innerHTML = `<span class="label">${safeLabel}</span>${safeCd ? `<span class="countdown">${safeCd}</span>` : ''}`;
}

async function setupMarketStatusIndicator() {
  _injectMarketStatusStyles();

  // Insertar el div.hs en .hdr-stats. Si la página aún no lo tiene
  // (sentinel-app.js corre después), reintentamos cada 100ms hasta 3s.
  let attempts = 0;
  const ensureNode = () => {
    if (document.getElementById(MARKET_HS_ID)) return true;
    const stats = document.querySelector('.hdr-stats');
    if (!stats) {
      if (attempts++ < 30) setTimeout(ensureNode, 100);
      return false;
    }
    const hs = document.createElement('div');
    hs.className = 'hs';
    hs.id = MARKET_HS_ID;
    hs.innerHTML = '<span class="k">MERCADO</span><span class="v"><span class="label">…</span></span>';
    stats.appendChild(hs);
    _renderMarketIndicator();
    return true;
  };
  ensureNode();

  const fetchAndUpdate = async () => {
    try {
      const r = await fetch('/api/market-status', {
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin',
      });
      if (!r.ok) return;
      const data = await r.json();
      _marketState = {
        is_open:        !!data.is_open,
        status:         data.status,
        next_open_ms:   data.next_open  ? new Date(data.next_open).getTime()  : null,
        next_close_ms: data.next_close ? new Date(data.next_close).getTime() : null,
      };
      _renderMarketIndicator();
    } catch (e) {
      console.debug('[sentinel-data] market-status:', e);
    }
  };

  // Primera carga
  await fetchAndUpdate();
  // Refresh periódico (server-side puede haber cambiado al cruzar boundary)
  setInterval(fetchAndUpdate, MARKET_STATUS_REFRESH_MS);
  // Tick local cada 60s para que el countdown decaiga sin esperar al fetch
  setInterval(_renderMarketIndicator, 60_000);
}

/* ============ FRENTE A — RENDERERS HONESTOS (2026-04-28) ============ *
 * Reemplaza markup literal del bundle handoff por:
 *   - valores reales cuando hay endpoint que los alimenta
 *     (agents activos, circuit breaker, parking brake)
 *   - "—" cuando no hay endpoint y la alternativa sería inventar
 *     (balance, P&L, posiciones, signals procesadas, max DD,
 *      correlation guard stats, uptime).
 * Cuando se cree el endpoint correspondiente (Frente B), reemplazar
 * el "—" por el valor real en la función renderEmptyKPIs().
 * ============================================================ */

const _DASH = '—';

function _setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function renderAgentsActiveCount() {
  const count = AGENTS.filter(a => a.active).length;
  // textContent porque el bundle pintaba i18n; al sobrescribir perdemos
  // la traducción dinámica. Acepted trade-off — el número es lo importante,
  // el resto del label "agentes activos/active" queda en español por ahora.
  _setText('agentsActiveCount', `${count} ${t('agents_active_label')}`);
}

function renderCircuitBreakerToggle(active) {
  const el = document.getElementById('bbCircuit');
  if (!el) return;
  el.classList.toggle('on', !active);   // markup original: "on" cuando off — convención inversa
  el.classList.toggle('off', !!active);
  const span = el.querySelector('span');
  if (span) {
    span.removeAttribute('data-i18n');   // evitar que applyI18n lo pise
    span.textContent = active ? 'CIRCUIT BREAKER · ON' : 'CIRCUIT BREAKER · OFF';
  }
}

function renderParkingBrakeToggle(active) {
  const el = document.getElementById('bbParking');
  if (!el) return;
  el.classList.toggle('on', !active);
  el.classList.toggle('off', !!active);
  const span = el.querySelector('span');
  if (span) {
    span.removeAttribute('data-i18n');
    span.textContent = active ? 'PARKING BRAKE · ON' : 'PARKING BRAKE · OFF';
  }
}

/* KPIs -- Frente B conectado.
 * Consulta /api/account/equity (read-only desde Alpaca) y popula los KPIs
 * del dashboard con datos reales. Los campos que aun no tienen endpoint
 * (signals, correlation guard, uptime) quedan con "--" hasta implementarlos. */

let _lastEquityData = null;
const _INITIAL_CAPITAL = 100000; // Capital inicial paper trading

async function fetchAndRenderKPIs() {
  try {
    const r = await fetch('/api/account/equity', { credentials: 'same-origin' });
    if (!r.ok) {
      console.warn('[sentinel-data] /api/account/equity HTTP', r.status);
      renderFallbackKPIs();
      return;
    }
    const data = await r.json();
    _lastEquityData = data;

    // Balance total
    const equity = data.equity || 0;
    _setText('osBalance', equity.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));

    // PnL (vs capital inicial)
    const pnl = equity - _INITIAL_CAPITAL;
    const pnlPct = _INITIAL_CAPITAL > 0 ? (pnl / _INITIAL_CAPITAL * 100) : 0;
    const sign = pnl >= 0 ? '+' : '-';
    _setText('osPnl', sign + Math.abs(pnl).toFixed(2));
    _setText('osPnlPct', (pnl >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%');

    // Equity card
    _setText('eqCapital', '$' + equity.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}));
    _setText('eqPnl', sign + '$' + Math.abs(pnl).toFixed(2));

    // Max Drawdown -- no calculable con un solo punto, dejamos "--" por ahora
    _setText('eqMaxDD', _DASH);

    // Posiciones abiertas
    _setText('osOpenPos', String(data.positions_count || 0));

    // Campos aun sin endpoint (Frente B pendiente)
    _setText('osSigProc',     _DASH);
    _setText('osSigApproved', _DASH);
    _setText('osSigRejected', _DASH);
    _setText('cgAvgCorr',     _DASH);
    _setText('cgReduced',     _DASH);
    _setText('cgDiscarded',   _DASH);

  } catch (e) {
    console.error('[sentinel-data] fetchAndRenderKPIs:', e);
    renderFallbackKPIs();
  }
}

function renderFallbackKPIs() {
  _setText('osBalance',     _DASH);
  _setText('osPnl',         _DASH);
  _setText('osPnlPct',      _DASH);
  _setText('eqCapital',     _DASH);
  _setText('eqPnl',         _DASH);
  _setText('eqMaxDD',       _DASH);
  _setText('osOpenPos',     _DASH);
  _setText('osSigProc',     _DASH);
  _setText('osSigApproved', _DASH);
  _setText('osSigRejected', _DASH);
  _setText('cgAvgCorr',     _DASH);
  _setText('cgReduced',     _DASH);
  _setText('cgDiscarded',   _DASH);
}

/* Capital card (Excepción 1.2, 2026-05-13).
 * Diferencia capital total vs efectivamente invertido y muestra rentabilidad
 * del día sobre el capital deployado (no sobre el equity total, que se diluye
 * con el cash dormido). Consume el endpoint /api/account/capital que cumple
 * el formato { data, meta } del manual de buenas prácticas (sección 6.2). */

function _formatUSD(n) {
  const sign = n >= 0 ? '' : '-';
  return sign + '$' + Math.abs(n).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function _formatPct(n, includeSign) {
  const sign = (includeSign && n >= 0) ? '+' : '';
  return sign + n.toFixed(2) + '%';
}

async function loadCapitalMetrics() {
  try {
    const r = await fetch('/api/account/capital', { credentials: 'same-origin' });
    if (!r.ok) {
      console.warn('[sentinel-data] /api/account/capital HTTP', r.status);
      renderFallbackCapital();
      return;
    }
    const body = await r.json();
    const d = body && body.data;
    if (!d) {
      console.warn('[sentinel-data] /api/account/capital: respuesta sin data');
      renderFallbackCapital();
      return;
    }

    _setText('capInvested', _formatUSD(d.invested) + ' (' + _formatPct(d.invested_pct_of_equity, false) + ')');
    _setText('capDayPnl',   _formatUSD(d.day_pnl) + ' (' + _formatPct(d.day_pnl_pct_of_invested, true) + ')');

    // Color del PnL según signo: verde si ≥0, rojo si <0. Reusa clases del handoff.
    const pnlEl = document.getElementById('capDayPnl');
    if (pnlEl) pnlEl.className = d.day_pnl >= 0 ? 'green' : 'red';
  } catch (e) {
    console.error('[sentinel-data] loadCapitalMetrics:', e);
    renderFallbackCapital();
  }
}

function renderFallbackCapital() {
  _setText('capInvested', _DASH);
  _setText('capDayPnl',   _DASH);
}

// Alias para compatibilidad -- reloadFromAPI() llama renderEmptyKPIs()
const renderEmptyKPIs = fetchAndRenderKPIs;

/* footBuild se popula con metadata.system_version del /api/report al boot.
 * Un único fetch — no se refresca periódicamente porque la versión no
 * cambia mientras el bot esté corriendo el mismo deploy. */
async function fetchAndRenderBuild() {
  try {
    const r = await fetch('/api/report?range=today', { credentials: 'same-origin' });
    if (!r.ok) { _setText('footBuild', _DASH); return; }
    const data = await r.json();
    const version = data && data.metadata && data.metadata.system_version;
    _setText('footBuild', version || _DASH);
    // Uptime from system_health
    const uptimeH = data && data.system_health && data.system_health.uptime_hours;
    if (uptimeH != null) {
      _setText('footUptime', uptimeH < 1 ? '<1h' : Math.round(uptimeH) + 'h');
    }
  } catch (e) {
    console.debug('[sentinel-data] fetchAndRenderBuild:', e);
    _setText('footBuild', _DASH);
  }
}

/* ============ BOOT ============ */
setupPersistence();
setupKillSwitch();
setupAdminLink();
setupRotationsBanner();
setupMarketStatusIndicator();

// Aplicar "--" al markup literal ANTES de la primera carga, asi no parpadean
// los valores ficticios del bundle durante los ~100-300ms de fetch.
// El fetch real de KPIs ocurre dentro de reloadFromAPI() via fetchAndRenderKPIs().
renderFallbackKPIs();
fetchAndRenderBuild();

// Disparar la primera carga + abrir SSE. No esperamos a DOMContentLoaded —
// sentinel-app.js corre sincrónico justo después de este archivo y popula
// los renders con SENTINELS=[] inicial (UI vacía). El primer fetch resuelve
// en ~100-300ms y dispara renderAll() de nuevo con datos reales.
(async () => {
  try {
    await reloadFromAPI();
  } catch (e) {
    console.error('[sentinel-data] initial load failed:', e);
  }
  connectSSE();
})();
