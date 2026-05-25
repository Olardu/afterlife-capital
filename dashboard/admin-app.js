/* ============================================================
 * AFTERLIFE CAPITAL — Sentinel Admin Panel
 * Cliente para /admin (gestión de usuarios)
 * Solo accesible para administradores.
 * ============================================================ */

(function () {
  'use strict';

  // ----- CONFIG -----
  const OWNER_EMAIL = 'owner@example.com';
  const API_BASE = '/api/admin/users';

  // ----- DOM -----
  const $ = (id) => document.getElementById(id);
  const usersBody = $('usersBody');
  const userCount = $('userCount');
  const usersUpdated = $('usersUpdated');
  const addForm = $('addUserForm');
  const emailInput = $('emailInput');
  const roleSelect = $('roleSelect');
  const addBtn = $('addBtn');
  const feedback = $('feedback');
  const mainContent = $('mainContent');

  // ============ DEMO DATA (se usa solo si el endpoint falla con error de red,
  //              NO si la API devuelve 4xx/5xx). Útil para previsualizar el
  //              diseño en static hosts. En producción siempre llega data real. ============
  const DEMO_USERS = [
    { id: 'u_001', email: 'owner@example.com', role: 'ADMIN', created_at: '2025-08-12T10:24:00Z' },
    { id: 'u_002', email: 'analyst@afterlife.capital', role: 'VIEWER', created_at: '2025-09-03T14:18:00Z' },
    { id: 'u_003', email: 'ops@afterlife.capital', role: 'ADMIN', created_at: '2025-10-21T09:02:00Z' },
    { id: 'u_004', email: 'observer@partner.io', role: 'VIEWER', created_at: '2026-01-15T11:47:00Z' },
    { id: 'u_005', email: 'audit@afterlife.capital', role: 'VIEWER', created_at: '2026-03-08T16:33:00Z' }
  ];
  let useDemo = false;

  // ============ HELPERS ============
  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      const pad = (n) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (_) { return iso; }
  }

  function nowHHMMSS() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function escapeHTML(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function showFeedback(kind, message) {
    feedback.className = 'feedback show ' + (kind === 'ok' ? 'ok' : 'err');
    feedback.textContent = message;
    if (kind === 'ok') {
      setTimeout(() => { feedback.classList.remove('show'); }, 5000);
    }
  }

  function clearFeedback() {
    feedback.className = 'feedback';
    feedback.textContent = '';
  }

  // ============ AUTH HANDLING ============
  function handleAuthResponse(res) {
    if (res.status === 401) {
      // No autenticado → redirect a login
      window.location.href = '/auth/login';
      throw new Error('REDIRECT_LOGIN');
    }
    if (res.status === 403) {
      // Autenticado pero sin permisos → mostrar mensaje
      renderPermissionDenied();
      throw new Error('NO_PERMISSION');
    }
    return res;
  }

  function renderPermissionDenied() {
    const tpl = document.getElementById('permTpl');
    mainContent.innerHTML = '';
    mainContent.appendChild(tpl.content.cloneNode(true));
  }

  // ============ API ============
  async function apiListUsers() {
    try {
      const res = await fetch(API_BASE, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin'
      });
      handleAuthResponse(res);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      // Aceptar { users: [...] } o array directo
      const list = Array.isArray(data) ? data : (data.users || []);
      // La API real usa user_id; el resto del JS espera id. Mapeamos
      // acá para no tocar el endpoint (la lógica id/user_id queda aislada).
      return list.map(u => ({ ...u, id: u.id || u.user_id }));
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') throw err;
      // Fallback a demo data en caso de error de red (preview estático)
      console.warn('[admin] API no disponible, usando datos demo:', err.message);
      useDemo = true;
      return DEMO_USERS.slice();
    }
  }

  async function apiAddUser(email, role) {
    if (useDemo) {
      // Simulación local
      if (DEMO_USERS.some(u => u.email.toLowerCase() === email.toLowerCase())) {
        const e = new Error('DUP'); e.status = 409; throw e;
      }
      const u = { id: 'u_' + Date.now(), email, role, created_at: new Date().toISOString() };
      DEMO_USERS.push(u);
      return u;
    }
    const res = await fetch(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ email, role })
    });
    handleAuthResponse(res);
    if (res.status === 409) { const e = new Error('DUP'); e.status = 409; throw e; }
    if (!res.ok) {
      let msg = 'HTTP ' + res.status;
      try { const j = await res.json(); if (j && j.error) msg = j.error; } catch (_) {}
      const e = new Error(msg); e.status = res.status; throw e;
    }
    return res.json();
  }

  async function apiDeleteUser(userId) {
    if (useDemo) {
      const i = DEMO_USERS.findIndex(u => u.id === userId);
      if (i >= 0) DEMO_USERS.splice(i, 1);
      return true;
    }
    const res = await fetch(`${API_BASE}/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    });
    handleAuthResponse(res);
    if (!res.ok) {
      const e = new Error('HTTP ' + res.status); e.status = res.status; throw e;
    }
    return true;
  }

  // ============ RENDER ============
  function renderUsers(users) {
    if (!users || users.length === 0) {
      usersBody.innerHTML = '<tr><td colspan="4" class="empty">// SIN USUARIOS REGISTRADOS</td></tr>';
      userCount.textContent = '0';
      usersUpdated.textContent = 'actualizado ' + nowHHMMSS();
      return;
    }

    // Ordenar: owner primero, luego ADMIN, luego VIEWER, luego por fecha
    const sorted = users.slice().sort((a, b) => {
      const ao = a.email.toLowerCase() === OWNER_EMAIL ? 0 : 1;
      const bo = b.email.toLowerCase() === OWNER_EMAIL ? 0 : 1;
      if (ao !== bo) return ao - bo;
      const ar = a.role === 'ADMIN' ? 0 : 1;
      const br = b.role === 'ADMIN' ? 0 : 1;
      if (ar !== br) return ar - br;
      return new Date(a.created_at || 0) - new Date(b.created_at || 0);
    });

    const rows = sorted.map(u => {
      const isOwner = String(u.email || '').toLowerCase() === OWNER_EMAIL;
      const role = (u.role || 'VIEWER').toUpperCase();
      const roleClass = role === 'ADMIN' ? 'admin' : 'viewer';
      const action = isOwner
        ? '<span class="no-action">— OWNER —</span>'
        : `<button class="btn-del" data-id="${escapeHTML(u.id)}" data-email="${escapeHTML(u.email)}">ELIMINAR</button>`;
      return `
        <tr>
          <td class="email-cell">
            ${escapeHTML(u.email)}
            ${isOwner ? '<span class="owner-tag">OWNER</span>' : ''}
          </td>
          <td><span class="role-badge ${roleClass}">${role}</span></td>
          <td class="date-cell">${escapeHTML(fmtDate(u.created_at))}</td>
          <td style="text-align:right;">${action}</td>
        </tr>
      `;
    }).join('');

    usersBody.innerHTML = rows;
    userCount.textContent = sorted.length;
    usersUpdated.textContent = 'actualizado ' + nowHHMMSS() + (useDemo ? ' · DEMO' : '');

    // Bind delete buttons
    usersBody.querySelectorAll('.btn-del').forEach(btn => {
      btn.addEventListener('click', onDeleteClick);
    });
  }

  // ============ ACTIONS ============
  async function loadUsers() {
    try {
      const users = await apiListUsers();
      renderUsers(users);
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      usersBody.innerHTML = `<tr><td colspan="4" class="empty">// ERROR AL CARGAR USUARIOS</td></tr>`;
      console.error('[admin] loadUsers error:', err);
    }
  }

  async function onDeleteClick(ev) {
    const btn = ev.currentTarget;
    const id = btn.getAttribute('data-id');
    const email = btn.getAttribute('data-email');
    if (!id) return;
    const ok = window.confirm(`¿Eliminar al usuario ${email}?\n\nEsta acción no se puede deshacer.`);
    if (!ok) return;
    btn.disabled = true;
    btn.textContent = 'ELIMINANDO...';
    try {
      await apiDeleteUser(id);
      await loadUsers();
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      btn.disabled = false;
      btn.textContent = 'ELIMINAR';
      showFeedback('err', 'Error al eliminar usuario: ' + err.message);
    }
  }

  async function onAddSubmit(ev) {
    ev.preventDefault();
    clearFeedback();
    const email = (emailInput.value || '').trim().toLowerCase();
    const role = roleSelect.value;
    if (!email) {
      showFeedback('err', 'El email es obligatorio.');
      return;
    }
    addBtn.disabled = true;
    addBtn.textContent = 'AGREGANDO...';
    try {
      await apiAddUser(email, role);
      showFeedback('ok', 'Usuario agregado. Email de bienvenida enviado.');
      emailInput.value = '';
      roleSelect.value = 'VIEWER';
      await loadUsers();
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      if (err.status === 409 || err.message === 'DUP') {
        showFeedback('err', 'Ese email ya está registrado.');
      } else {
        showFeedback('err', 'Error al agregar usuario: ' + err.message);
      }
    } finally {
      addBtn.disabled = false;
      addBtn.textContent = '+ AGREGAR';
    }
  }

  // =============================================================
  // API KEYS — gestión de credenciales encriptadas (#FIX-008)
  // =============================================================
  const KEYS_API = '/api/admin/api-keys';
  const REVEAL_TIMEOUT_MS = 30000;

  const keysBody     = $('keysBody');
  const keyCount     = $('keyCount');
  const keysUpdated  = $('keysUpdated');
  const addKeyForm   = $('addKeyForm');
  const serviceInput = $('serviceInput');
  const keyValueInput = $('keyValueInput');
  const keyDescInput = $('keyDescInput');
  const addKeyBtn    = $('addKeyBtn');
  const keyFeedback  = $('keyFeedback');

  // Tracking de timeouts de auto-hide por key_id (revealed → masked tras 30s)
  const revealTimers = new Map();

  function showKeyFeedback(kind, msg) {
    keyFeedback.className = 'feedback show ' + (kind === 'ok' ? 'ok' : 'err');
    keyFeedback.textContent = msg;
    if (kind === 'ok') setTimeout(() => keyFeedback.classList.remove('show'), 5000);
  }
  function clearKeyFeedback() {
    keyFeedback.className = 'feedback';
    keyFeedback.textContent = '';
  }

  async function apiListKeys() {
    const res = await fetch(KEYS_API, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    });
    handleAuthResponse(res);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function apiRevealKey(keyId) {
    const res = await fetch(`${KEYS_API}/${encodeURIComponent(keyId)}/reveal`, {
      method: 'POST',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    });
    handleAuthResponse(res);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    return data.value;
  }

  async function apiUpsertKey(service_name, value, description) {
    const res = await fetch(KEYS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ service_name, value, description })
    });
    handleAuthResponse(res);
    if (!res.ok) {
      let msg = 'HTTP ' + res.status;
      try { const j = await res.json(); if (j && j.detail) msg = j.detail; } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  async function apiDeleteKey(keyId) {
    const res = await fetch(`${KEYS_API}/${encodeURIComponent(keyId)}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    });
    handleAuthResponse(res);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return true;
  }

  function renderKeys(keys) {
    if (!keys || keys.length === 0) {
      keysBody.innerHTML = '<tr><td colspan="5" class="empty">// SIN API KEYS REGISTRADAS</td></tr>';
      keyCount.textContent = '0';
      keysUpdated.textContent = 'actualizado ' + nowHHMMSS();
      return;
    }

    const rows = keys.map(k => {
      const id = escapeHTML(k.key_id);
      return `
        <tr data-key-id="${id}">
          <td><strong>${escapeHTML(k.service_name)}</strong></td>
          <td class="key-cell" data-role="value" data-masked="${escapeHTML(k.masked_value)}">${escapeHTML(k.masked_value)}</td>
          <td>${escapeHTML(k.description || '—')}</td>
          <td class="date-cell">${escapeHTML(fmtDate(k.last_rotated_at))}</td>
          <td style="text-align:right;">
            <button class="btn-toggle" data-action="toggle" data-id="${id}">MOSTRAR</button>
            <button class="btn-del" data-action="delete" data-id="${id}" data-service="${escapeHTML(k.service_name)}">ELIMINAR</button>
          </td>
        </tr>
      `;
    }).join('');

    keysBody.innerHTML = rows;
    keyCount.textContent = keys.length;
    keysUpdated.textContent = 'actualizado ' + nowHHMMSS();

    keysBody.querySelectorAll('button[data-action="toggle"]').forEach(btn => {
      btn.addEventListener('click', onToggleClick);
    });
    keysBody.querySelectorAll('button[data-action="delete"]').forEach(btn => {
      btn.addEventListener('click', onDeleteKeyClick);
    });
  }

  function maskRow(row, btn) {
    const cell = row.querySelector('[data-role="value"]');
    if (!cell) return;
    cell.textContent = cell.dataset.masked;
    cell.classList.remove('revealed');
    btn.textContent = 'MOSTRAR';
    btn.classList.remove('revealed');
    const id = btn.dataset.id;
    if (revealTimers.has(id)) {
      clearTimeout(revealTimers.get(id));
      revealTimers.delete(id);
    }
  }

  async function onToggleClick(ev) {
    const btn = ev.currentTarget;
    const id  = btn.dataset.id;
    const row = btn.closest('tr');
    if (!row) return;
    const cell = row.querySelector('[data-role="value"]');
    if (btn.classList.contains('revealed')) {
      maskRow(row, btn);
      return;
    }
    btn.disabled = true;
    btn.textContent = 'CARGANDO...';
    try {
      const value = await apiRevealKey(id);
      cell.textContent = value;
      cell.classList.add('revealed');
      btn.textContent = 'OCULTAR';
      btn.classList.add('revealed');
      // Auto-hide a los 30s
      const t = setTimeout(() => maskRow(row, btn), REVEAL_TIMEOUT_MS);
      revealTimers.set(id, t);
    } catch (err) {
      btn.textContent = 'MOSTRAR';
      showKeyFeedback('err', 'Error al revelar key: ' + err.message);
    } finally {
      btn.disabled = false;
    }
  }

  async function onDeleteKeyClick(ev) {
    const btn = ev.currentTarget;
    const id = btn.dataset.id;
    const service = btn.dataset.service;
    if (!id) return;
    const ok = window.confirm(`¿Eliminar la API key "${service}"?\n\nEsta acción no se puede deshacer.`);
    if (!ok) return;
    btn.disabled = true;
    btn.textContent = 'ELIMINANDO...';
    try {
      await apiDeleteKey(id);
      await loadKeys();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'ELIMINAR';
      showKeyFeedback('err', 'Error al eliminar key: ' + err.message);
    }
  }

  async function loadKeys() {
    try {
      const keys = await apiListKeys();
      renderKeys(keys);
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      keysBody.innerHTML = `<tr><td colspan="5" class="empty">// ERROR AL CARGAR API KEYS</td></tr>`;
      console.error('[admin] loadKeys error:', err);
    }
  }

  async function onAddKeySubmit(ev) {
    ev.preventDefault();
    clearKeyFeedback();
    const service_name = (serviceInput.value || '').trim();
    const value        = keyValueInput.value || '';
    const description  = (keyDescInput.value || '').trim();
    if (!service_name) { showKeyFeedback('err', 'El nombre del servicio es obligatorio.'); return; }
    if (!value)        { showKeyFeedback('err', 'El valor es obligatorio.'); return; }
    addKeyBtn.disabled = true;
    addKeyBtn.textContent = 'GUARDANDO...';
    try {
      await apiUpsertKey(service_name, value, description);
      showKeyFeedback('ok', `API key "${service_name}" guardada.`);
      serviceInput.value = '';
      keyValueInput.value = '';
      keyDescInput.value = '';
      await loadKeys();
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      showKeyFeedback('err', 'Error al guardar: ' + err.message);
    } finally {
      addKeyBtn.disabled = false;
      addKeyBtn.textContent = '+ GUARDAR';
    }
  }

  // =============================================================
  // ROTATIONS (#UNIVERSE-SELECTION) — historial + rollback + modal
  // =============================================================
  const ROTATIONS_API  = '/api/admin/rotations';
  const CANDIDATES_API = '/api/admin/candidates';
  const ROLLBACK_WINDOW_DAYS = 7;

  const rotationsBody    = $('rotationsBody');
  const rotationCount    = $('rotationCount');
  const rotationsUpdated = $('rotationsUpdated');
  const filterStatus     = $('filterStatus');
  const candidatesBody   = $('candidatesBody');
  const candCount        = $('candCount');
  const rotationModal    = $('rotationModal');
  const modalBody        = $('modalBody');
  const modalCloseBtn    = $('modalCloseBtn');

  function fmtUsd(n) {
    if (n === null || n === undefined) return '—';
    const v = Number(n);
    if (!isFinite(v)) return '—';
    return '$' + v.toFixed(4);
  }
  function fmtPct(n) {
    if (n === null || n === undefined) return '—';
    const v = Number(n);
    if (!isFinite(v)) return '—';
    return (v * 100).toFixed(1) + '%';
  }
  function fmtNum(n, digits = 2) {
    if (n === null || n === undefined) return '—';
    const v = Number(n);
    if (!isFinite(v)) return '—';
    return v.toFixed(digits);
  }

  async function apiListRotations(status) {
    const url = status
      ? `${ROTATIONS_API}?status=${encodeURIComponent(status)}&limit=50`
      : `${ROTATIONS_API}?limit=50`;
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json' }, credentials: 'same-origin',
    });
    handleAuthResponse(res);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function apiGetRotation(decisionId) {
    const res = await fetch(`${ROTATIONS_API}/${encodeURIComponent(decisionId)}`, {
      headers: { 'Accept': 'application/json' }, credentials: 'same-origin',
    });
    handleAuthResponse(res);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function apiRollbackRotation(decisionId) {
    const res = await fetch(`${ROTATIONS_API}/${encodeURIComponent(decisionId)}/rollback`, {
      method: 'POST',
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin',
    });
    handleAuthResponse(res);
    if (!res.ok) {
      let msg = 'HTTP ' + res.status;
      try { const j = await res.json(); if (j && j.detail) msg = j.detail; } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  async function apiListCandidates() {
    const res = await fetch(CANDIDATES_API, {
      headers: { 'Accept': 'application/json' }, credentials: 'same-origin',
    });
    handleAuthResponse(res);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  function canRollback(rotation) {
    if (rotation.status !== 'executed') return false;
    if (!rotation.executed_at) return false;
    const ageDays = (Date.now() - new Date(rotation.executed_at).getTime()) / (1000*60*60*24);
    return ageDays <= ROLLBACK_WINDOW_DAYS;
  }

  function renderRotations(rotations) {
    if (!rotations || rotations.length === 0) {
      rotationsBody.innerHTML = '<tr><td colspan="6" class="empty">// SIN ROTACIONES</td></tr>';
      rotationCount.textContent = '0';
      rotationsUpdated.textContent = 'actualizado ' + nowHHMMSS();
      return;
    }
    const rows = rotations.map(r => {
      const id = escapeHTML(r.decision_id);
      const fecha = escapeHTML(fmtDate(r.triggered_at));
      const sentinel = escapeHTML(r.sentinel_name || '?');
      const old = escapeHTML(r.old_ticker || '?');
      const nw  = escapeHTML(r.new_ticker || '—');
      const status = String(r.status || 'pending');
      const cost = fmtUsd(r.claude_cost_usd);
      const rollbackBtn = canRollback(r)
        ? `<button class="btn-rollback" data-action="rollback" data-id="${id}">ROLLBACK</button>`
        : '<span class="no-action">—</span>';
      return `
        <tr>
          <td class="date-cell">${fecha}</td>
          <td>${sentinel}</td>
          <td><span class="tk-old">${old}</span><span class="tk-arrow">→</span><span class="tk-new">${nw}</span></td>
          <td><span class="status-badge ${escapeHTML(status)}">${escapeHTML(status.toUpperCase())}</span></td>
          <td>${cost}</td>
          <td style="text-align:right;">
            <button class="btn-detail" data-action="detail" data-id="${id}">DETALLE</button>
            ${rollbackBtn}
          </td>
        </tr>
      `;
    }).join('');
    rotationsBody.innerHTML = rows;
    rotationCount.textContent = rotations.length;
    rotationsUpdated.textContent = 'actualizado ' + nowHHMMSS();

    rotationsBody.querySelectorAll('button[data-action="detail"]').forEach(btn => {
      btn.addEventListener('click', () => openRotationModal(btn.dataset.id));
    });
    rotationsBody.querySelectorAll('button[data-action="rollback"]').forEach(btn => {
      btn.addEventListener('click', () => onRollbackClick(btn));
    });
  }

  async function loadRotations() {
    try {
      const rotations = await apiListRotations(filterStatus ? filterStatus.value : '');
      renderRotations(rotations);
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      rotationsBody.innerHTML = '<tr><td colspan="6" class="empty">// ERROR AL CARGAR ROTACIONES</td></tr>';
      console.error('[admin] loadRotations:', err);
    }
  }

  function renderCandidates(cands) {
    if (!cands || cands.length === 0) {
      candidatesBody.innerHTML = '<tr><td colspan="4" class="empty">// SIN CANDIDATOS EN WATCHLIST</td></tr>';
      candCount.textContent = '0';
      return;
    }
    const rows = cands.map(c => `
      <tr>
        <td>${escapeHTML(c.sentinel_name || '?')}</td>
        <td><span class="tk-new">${escapeHTML(c.proposed_ticker || '?')}</span></td>
        <td class="date-cell">${escapeHTML(fmtDate(c.proposed_at))}</td>
        <td class="date-cell">${escapeHTML(fmtDate(c.expires_at))}</td>
      </tr>
    `).join('');
    candidatesBody.innerHTML = rows;
    candCount.textContent = cands.length;
  }

  async function loadCandidates() {
    try {
      const cands = await apiListCandidates();
      renderCandidates(cands);
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      candidatesBody.innerHTML = '<tr><td colspan="4" class="empty">// ERROR AL CARGAR</td></tr>';
      console.error('[admin] loadCandidates:', err);
    }
  }

  async function onRollbackClick(btn) {
    const id = btn.dataset.id;
    const ok = window.confirm(
      '¿Hacer rollback de esta rotación?\n\nEl ticker volverá al anterior. Esta acción quedará registrada con tu email.'
    );
    if (!ok) return;
    btn.disabled = true;
    btn.textContent = 'ROLLBACK...';
    try {
      await apiRollbackRotation(id);
      await loadRotations();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'ROLLBACK';
      alert('Error al hacer rollback: ' + err.message);
    }
  }

  function renderRotationDetail(rot) {
    const cands = Array.isArray(rot.candidates_proposed) ? rot.candidates_proposed : [];
    const candsHtml = cands.length === 0
      ? '<span class="cd-reason">(sin candidatos alternativos)</span>'
      : `<ul class="candidate-list">${cands.map(c => `
          <li>
            <span class="cd-tk">${escapeHTML(c.ticker || '?')}</span>
            &nbsp;<span class="cd-conf">conf ${escapeHTML(fmtNum(c.confidence))}</span>
            <span class="cd-reason">${escapeHTML(c.reason || '')}</span>
          </li>
        `).join('')}</ul>`;
    return `
      <div class="modal-row"><span class="k">SENTINEL</span><span class="v">${escapeHTML(rot.sentinel_name || '?')}</span></div>
      <div class="modal-row"><span class="k">DISPARADOR</span><span class="v">${escapeHTML(rot.trigger_reason || '?')}</span></div>
      <div class="modal-row"><span class="k">ROTACIÓN</span><span class="v"><span class="tk-old">${escapeHTML(rot.old_ticker || '?')}</span> <span class="tk-arrow">→</span> <span class="tk-new">${escapeHTML(rot.new_ticker || '—')}</span></span></div>
      <div class="modal-row"><span class="k">ESTADO</span><span class="v"><span class="status-badge ${escapeHTML(rot.status || '')}">${escapeHTML((rot.status || '').toUpperCase())}</span></span></div>
      <div class="modal-row"><span class="k">DISPARADO</span><span class="v">${escapeHTML(fmtDate(rot.triggered_at))}</span></div>
      ${rot.executed_at ? `<div class="modal-row"><span class="k">EJECUTADO</span><span class="v">${escapeHTML(fmtDate(rot.executed_at))}</span></div>` : ''}
      ${rot.rolled_back_at ? `<div class="modal-row"><span class="k">ROLLBACK</span><span class="v">${escapeHTML(fmtDate(rot.rolled_back_at))} · ${escapeHTML(rot.rolled_back_by || '?')}</span></div>` : ''}
      <div class="modal-row"><span class="k">PERFORMANCE OLD</span><span class="v">win ${escapeHTML(fmtPct(rot.old_win_rate))} · sharpe ${escapeHTML(fmtNum(rot.old_sharpe_ratio))} · trades ${escapeHTML(String(rot.old_total_trades ?? '—'))}</span></div>
      <div class="modal-row"><span class="k">CONFIDENCE</span><span class="v">${escapeHTML(fmtNum(rot.claude_confidence))}</span></div>
      <div class="modal-row"><span class="k">RAZONAMIENTO</span><span class="v reasoning">${escapeHTML(rot.claude_reasoning || '(sin razonamiento)')}</span></div>
      <div class="modal-row"><span class="k">CANDIDATOS</span><span class="v">${candsHtml}</span></div>
      <div class="modal-row"><span class="k">MODELO</span><span class="v">${escapeHTML(rot.claude_model || '—')}</span></div>
      <div class="modal-row"><span class="k">TOKENS</span><span class="v">in ${escapeHTML(String(rot.claude_input_tokens || 0))} · out ${escapeHTML(String(rot.claude_output_tokens || 0))}</span></div>
      <div class="modal-row"><span class="k">COSTO</span><span class="v">${escapeHTML(fmtUsd(rot.claude_cost_usd))}</span></div>
      ${rot.notes ? `<div class="modal-row"><span class="k">NOTAS</span><span class="v">${escapeHTML(rot.notes)}</span></div>` : ''}
    `;
  }

  async function openRotationModal(decisionId) {
    rotationModal.classList.add('show');
    rotationModal.setAttribute('aria-hidden', 'false');
    modalBody.innerHTML = '<div class="loading">CARGANDO</div>';
    try {
      const rot = await apiGetRotation(decisionId);
      modalBody.innerHTML = renderRotationDetail(rot);
    } catch (err) {
      if (err.message === 'REDIRECT_LOGIN' || err.message === 'NO_PERMISSION') return;
      modalBody.innerHTML = `<div class="empty">// ERROR: ${escapeHTML(err.message)}</div>`;
    }
  }

  function closeModal() {
    rotationModal.classList.remove('show');
    rotationModal.setAttribute('aria-hidden', 'true');
  }

  // ============ INIT ============
  function init() {
    addForm.addEventListener('submit', onAddSubmit);
    emailInput.addEventListener('input', clearFeedback);
    if (addKeyForm) {
      addKeyForm.addEventListener('submit', onAddKeySubmit);
      [serviceInput, keyValueInput, keyDescInput].forEach(el => {
        if (el) el.addEventListener('input', clearKeyFeedback);
      });
    }
    if (filterStatus) {
      filterStatus.addEventListener('change', loadRotations);
    }
    if (modalCloseBtn) {
      modalCloseBtn.addEventListener('click', closeModal);
      rotationModal.addEventListener('click', (ev) => {
        if (ev.target === rotationModal) closeModal();
      });
      document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && rotationModal.classList.contains('show')) closeModal();
      });
    }
    loadUsers();
    if (keysBody) loadKeys();
    if (rotationsBody) loadRotations();
    if (candidatesBody) loadCandidates();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
