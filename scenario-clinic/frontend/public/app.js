'use strict';
/* Cedar Hollow Patient Records — portal client.
 *
 * No framework, no build step, no dependencies. The demo runs on a network that
 * is assumed broken; a bundler or CDN import would be a liability.
 *
 * The failure path is the important path. When the backend returns 502 we render
 * the machine identifiers it gave us verbatim — error class, upstream host:port,
 * correlation ID. Those exact strings are also written to the backend's app log,
 * so what the FDE reads on this screen is what the agent retrieves from the
 * bundle. Do not prettify them.
 */

const el = (id) => document.getElementById(id);

const ui = {
  loading: el('loading'),
  records: el('records'),
  body: el('records-body'),
  count: el('records-count'),
  failure: el('failure'),
  diag: {
    code: el('diag-code'),
    upstream: el('diag-upstream'),
    cid: el('diag-cid'),
    time: el('diag-time'),
    detail: el('diag-detail'),
  },
  status: {
    dot: el('dot'),
    backend: el('status-backend'),
    upstream: el('status-upstream'),
    lastok: el('status-lastok'),
    build: el('status-build'),
  },
};

let BACKEND = '';

function show(which) {
  ui.loading.hidden = which !== 'loading';
  ui.records.hidden = which !== 'records';
  ui.failure.hidden = which !== 'failure';
}

function setStatus(state, text, detail) {
  ui.status.dot.className = 'dot dot--' + state;
  ui.status.backend.textContent = text;
  if (detail !== undefined) ui.status.upstream.textContent = detail;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function renderRecords(data) {
  ui.body.innerHTML = data.patients
    .map(
      (p) => `
      <tr>
        <td class="mrn">${escapeHtml(p.mrn)}</td>
        <td class="name">${escapeHtml(p.name)}</td>
        <td class="dob">${escapeHtml(p.dob)}</td>
        <td>${escapeHtml(p.provider)}</td>
        <td class="visit">${escapeHtml(p.lastVisit)}</td>
        <td>${p.flags.map((f) => `<span class="flag">${escapeHtml(f)}</span>`).join('') || '<span class="pill pill--inactive">none</span>'}</td>
        <td><span class="pill pill--${escapeHtml(p.status)}">${escapeHtml(p.status)}</span></td>
      </tr>`
    )
    .join('');
  ui.count.textContent = `${data.count} record${data.count === 1 ? '' : 's'}`;
  show('records');
}

function renderFailure(payload) {
  const up = payload.upstream || {};
  ui.diag.code.textContent = payload.code || 'UNKNOWN';
  ui.diag.upstream.textContent = up.host ? `${up.host}:${up.port}` : 'unknown';
  ui.diag.cid.textContent = payload.correlationId || '—';
  ui.diag.time.textContent = new Date().toISOString();
  ui.diag.detail.textContent = payload.detail || payload.error || '—';
  show('failure');
  setStatus('down', 'reachable', `unreachable (${payload.code || 'error'})`);
}

// The portal itself is up; the backend is what failed to answer. Distinct
// condition from a 502, and the FDE needs to be able to tell them apart.
function renderPortalIsolated(err) {
  ui.diag.code.textContent = 'EPORTAL';
  ui.diag.upstream.textContent = BACKEND || '(unconfigured)';
  ui.diag.cid.textContent = '—';
  ui.diag.time.textContent = new Date().toISOString();
  ui.diag.detail.textContent = `portal could not reach clinic-backend: ${err.message}`;
  show('failure');
  setStatus('down', 'unreachable', '—');
}

async function loadPatients(query) {
  show('loading');
  const url = new URL('/api/patients', BACKEND);
  if (query) url.searchParams.set('q', query);

  let res;
  try {
    res = await fetch(url, { cache: 'no-store' });
  } catch (err) {
    return renderPortalIsolated(err);
  }

  let payload;
  try {
    payload = await res.json();
  } catch (err) {
    return renderFailure({ code: 'EPARSE', detail: `backend returned unparseable body: ${err.message}` });
  }

  if (!res.ok) return renderFailure(payload);
  renderRecords(payload);
}

async function refreshStatus() {
  try {
    const res = await fetch(new URL('/api/meta', BACKEND), { cache: 'no-store' });
    const meta = await res.json();
    ui.status.upstream.textContent = `${meta.upstream.host}:${meta.upstream.port}`;
    ui.status.lastok.textContent = meta.lastUpstreamSuccess || 'none this boot';
    ui.status.backend.textContent = `${meta.service} v${meta.version}`;
    ui.status.dot.className = 'dot dot--ok';
  } catch (err) {
    setStatus('down', 'unreachable', '—');
    ui.status.lastok.textContent = '—';
  }
}

async function init() {
  // Served by the portal's own process, so it always resolves — this is where a
  // stale BACKEND_URL would surface (the frontend-side variant of the bug).
  const cfg = await fetch('./config.json', { cache: 'no-store' }).then((r) => r.json());
  BACKEND = cfg.backendUrl;
  ui.status.build.textContent = `${cfg.service} v${cfg.version}`;

  document.querySelector('.search').addEventListener('submit', (e) => {
    e.preventDefault();
    loadPatients(el('q').value.trim());
  });
  el('retry').addEventListener('click', () => {
    refreshStatus();
    loadPatients(el('q').value.trim());
  });

  await refreshStatus();
  await loadPatients('');
  setInterval(refreshStatus, 10000);
}

init();
