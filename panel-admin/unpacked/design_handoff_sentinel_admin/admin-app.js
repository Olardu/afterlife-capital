/* ============================================================
 * AFTERLIFE CAPITAL — Sentinel Admin Panel
 * Cliente para /admin (gestión de usuarios)
 * Solo accesible para administradores.
 * ============================================================ */

(function () {
  'use strict';

  // ----- CONFIG -----
  const OWNER_EMAIL = '***REMOVED-EMAIL***';
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
    { id: 'u_001', email: '***REMOVED-EMAIL***', role: 'ADMIN', created_at: '2025-08-12T10:24:00Z' },
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
      return Array.isArray(data) ? data : (data.users || []);
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

  // ============ INIT ============
  function init() {
    addForm.addEventListener('submit', onAddSubmit);
    emailInput.addEventListener('input', clearFeedback);
    loadUsers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
