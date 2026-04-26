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
  balance: 100000, balanceChange: 0,   // TODO: extender API con /api/account/equity
  riskScore: 0,
  nextId: 1,
  equityHist: [],
  expandedDetails: new Set(),
  logsOpen: false,
};

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

    // win/sharpe: promedio sobre los tickers (la API los expone por ticker)
    const wins    = tList.map(t => Number(t.win_rate) || 0).filter(x => x > 0);
    const sharpes = tList.map(t => Number(t.sharpe_ratio) || 0);
    const win    = wins.length    ? wins.reduce((a, b) => a + b, 0)    / wins.length    : 0;
    const sharpe = sharpes.length ? sharpes.reduce((a, b) => a + b, 0) / sharpes.length : 0;

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
      ts:     (t.created_at || '').slice(11, 19),    // HH:MM:SS
    };
  });
  STATE.nextId = 1000 + data.length + 1;

  // equityHist sintético desde trades (placeholder hasta que haya FIFO real)
  STATE.equityHist = synthEquityHist(STATE.trades);
  return data;
}

function synthEquityHist(trades) {
  // PnL acumulado naive a partir de slippage * qty * sign(side).
  // No es PnL real (FIFO BUY→SELL) — solo da forma a una curva
  // hasta que el backend exponga equity series real.
  if (!trades.length) {
    // Sin trades: devolver una línea horizontal en 100000 con jitter mínimo
    const out = [];
    for (let i = 0; i < 24; i++) out.push(100000 + Math.sin(i * 0.4) * 10);
    return out;
  }
  let acc = 100000;
  const ordered = [...trades].reverse();   // ASC por created_at
  return ordered.map(t => {
    const sign = t.side === 'SELL' ? 1 : -1;
    const slip = 0;   // sin slippage en el formato handoff — placeholder cero
    acc += sign * slip * (t.qty || 1);
    return acc;
  });
}

async function loadMacro() {
  const data = await _fetchJson('/api/macro');
  if (!data) return null;

  const events = (data.recent_events || []).slice(0, 6);
  // Inyectar títulos sintéticos al I18N como keys dinámicas
  // (sentinel-app.js usa t(n.titleKey) — necesitamos que la lookup resuelva).
  events.forEach((ev, i) => {
    const k = `_news_dyn_${i}`;
    const risk = Number(ev.risk_score) || 0;
    const vix  = ev.vix_level == null ? null : Number(ev.vix_level);
    const spy  = ev.spy_change_15min == null ? null : Number(ev.spy_change_15min);
    const txt = {
      es: `Macro update — risk ${risk.toFixed(2)}` +
          (vix != null ? ` · VIX Δ${vix.toFixed(1)}%` : '') +
          (spy != null ? ` · SPY Δ${spy.toFixed(1)}%` : ''),
      en: `Macro update — risk ${risk.toFixed(2)}` +
          (vix != null ? ` · VIX Δ${vix.toFixed(1)}%` : '') +
          (spy != null ? ` · SPY Δ${spy.toFixed(1)}%` : ''),
      ja: `マクロ更新 — リスク ${risk.toFixed(2)}` +
          (vix != null ? ` · VIX Δ${vix.toFixed(1)}%` : '') +
          (spy != null ? ` · SPY Δ${spy.toFixed(1)}%` : ''),
      th: `อัปเดตมาโคร — ความเสี่ยง ${risk.toFixed(2)}` +
          (vix != null ? ` · VIX Δ${vix.toFixed(1)}%` : '') +
          (spy != null ? ` · SPY Δ${spy.toFixed(1)}%` : ''),
    };
    if (typeof I18N === 'object') {
      for (const lang of ['es', 'en', 'ja', 'th']) {
        if (I18N[lang]) I18N[lang][k] = txt[lang];
      }
    }
  });

  NEWS.length = 0;
  events.forEach((ev, i) => {
    const ts = (ev.created_at || '').slice(11, 16);   // HH:MM
    const risk = Number(ev.risk_score) || 0;
    const impact = ev.circuit_breaker_triggered ? 'cb' : (risk > 0.5 ? 'risk' : 'neutral');
    NEWS.push({ ts, titleKey: `_news_dyn_${i}`, impact });
  });

  // Logs sintéticos a partir de macro events
  STATE.logs = (data.recent_events || []).slice(0, 30).map(ev => {
    const ts = (ev.created_at || '').replace('T', ' ').slice(0, 19);
    const risk = Number(ev.risk_score) || 0;
    const lvl = ev.circuit_breaker_triggered ? 'ERROR' : (risk > 0.5 ? 'WARN' : 'INFO');
    const vixStr = ev.vix_level == null ? '—' : Number(ev.vix_level).toFixed(2);
    const spyStr = ev.spy_change_15min == null ? '—' : Number(ev.spy_change_15min).toFixed(2);
    const cbStr  = ev.circuit_breaker_triggered ? 'true' : 'false';
    const msg = `EAR :: risk_score=${risk.toFixed(4)} vix=${vixStr} spy=${spyStr} circuit_breaker=${cbStr}`;
    return { ts, lvl, msg };
  });

  return data;
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
  // Footer "Actualizado HH:MM:SS"
  const upd = document.getElementById('footUpd');
  if (upd) upd.textContent = new Date().toTimeString().slice(0, 8);
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

/* ============ BOOT ============ */
setupPersistence();
setupKillSwitch();

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
