export const API_BASE = '/api/v1';

// ── Shared request core + 401 interceptor ──────────────────
// A single place that turns a 401 into a global "you need to sign in" signal.
// AuthProvider registers a handler here; any request that comes back 401 (e.g.
// the session cookie expired mid-session) flips the app to the login screen.
//
// Every API call routes through requestRaw() so the interceptor fires
// consistently. request() is the JSON variant; requestDownload() is the
// binary/DOCX sibling (request() would choke trying to JSON-parse a blob).
let _onUnauthorized = null;
export function setUnauthorizedHandler(fn) { _onUnauthorized = fn; }

function buildUrl(path, query) {
  if (!query) return `${API_BASE}${path}`;
  const clean = Object.fromEntries(
    Object.entries(query).filter(([, v]) => v != null && v !== '')
  );
  const qs = new URLSearchParams(clean).toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`;
}

async function requestRaw(path, { method = 'GET', body, query } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(buildUrl(path, query), opts);
  if (resp.status === 401) {
    if (_onUnauthorized) _onUnauthorized();
    const err = new Error('Authentication required');
    err.status = 401;
    throw err;
  }
  return resp;
}

export async function request(path, opts) {
  const resp = await requestRaw(path, opts);
  // 204 / empty bodies are valid (e.g. token revoke).
  const text = await resp.text();
  const json = text ? JSON.parse(text) : null;
  if (!resp.ok) {
    const err = new Error((json && json.detail) || `HTTP ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  return json;
}

// ── Binary download helper ─────────────────────────────────
function filenameFrom(resp, fallback = 'Resume.docx') {
  const disposition = resp.headers.get('Content-Disposition') || '';
  return disposition.split('filename=')[1]?.replace(/"/g, '').trim() || fallback;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Fetch a binary (DOCX) response, save it, and return the header-derived
// metadata. Shares the 401 interceptor; on failure the error body is JSON.
async function requestDownload(path, opts) {
  const resp = await requestRaw(path, opts);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const e = new Error(err.detail || `HTTP ${resp.status}`);
    e.status = resp.status;
    throw e;
  }
  const blob = await resp.blob();
  const filename = filenameFrom(resp);
  triggerDownload(blob, filename);
  return {
    filename,
    applicationId: resp.headers.get('X-Application-Id'),
    duplicateWarning: resp.headers.get('X-Duplicate-Warning') === 'true',
  };
}

// Fetch the backend's /health to read its self-reported environment.
// Cached on first call so the env badge doesn't ping the API repeatedly.
// Stays a bare fetch: it's outside /api/v1, never throws, and isn't auth-gated.
let _healthCache = null;
export async function fetchHealth() {
  if (_healthCache) return _healthCache;
  try {
    const resp = await fetch('/health');
    if (!resp.ok) return null;
    const body = await resp.json();
    _healthCache = {
      env: body.env || resp.headers.get('X-Environment') || 'unknown',
      db: body.db,
    };
    return _healthCache;
  } catch {
    return null;
  }
}

// ── Applications ───────────────────────────────────────────
export function fetchApplications(params) {
  return request('/applications', { query: params });
}

export function fetchHistory(id) {
  return request(`/applications/${id}/history`);
}

export function fetchStats() {
  return request('/applications/stats');
}

export function createApplication(data) {
  return request('/log-application', { method: 'POST', body: data });
}

export function updateApplication(id, data) {
  return request(`/log-application/${id}`, { method: 'PATCH', body: data });
}

// Soft-delete.
export function deleteApplication(id) {
  return request(`/applications/${id}`, { method: 'DELETE' });
}

// ── Résumé generation / download (DOCX) ────────────────────
export function generateResume(data) {
  return requestDownload('/generate-resume', { method: 'POST', body: data });
}

// Re-download an already-generated résumé.
export function downloadResume(id) {
  return requestDownload(`/applications/${id}/resume`);
}

// JD → tailored résumé via backend LLM.
// preview=true returns the structured ResumeRequest JSON for review;
// preview=false (default) triggers a DOCX download and auto-logs the
// application — same UX as generateResume().
export function generateResumeFromJD(data, { preview = false } = {}) {
  if (preview) {
    return request('/generate-resume-from-jd', { method: 'POST', body: data, query: { preview: true } });
  }
  return requestDownload('/generate-resume-from-jd', { method: 'POST', body: data });
}

// ── Base résumé (master copy fed into the LLM) ─────────────
export async function getBaseResume() {
  try {
    return await request('/base-resume');
  } catch (err) {
    if (err.status === 404) return null;   // nothing uploaded yet
    throw err;
  }
}

export function saveBaseResume(data) {
  return request('/base-resume', { method: 'PUT', body: data });
}

// ── Résumé-generation audit log (observability) ────────────
export function fetchGenerationHistory(limit = 50) {
  return request('/generation-history', { query: { limit } });
}

// ── IAM / auth ─────────────────────────────────────────────

// The caller's identity, roles, and effective permissions. The <Can> gate and
// admin nav read this; the server still enforces every call. Routed through
// request() so a 401 (auth on, not signed in) trips the global handler.
export function fetchMe() {
  return request('/auth/me');   // { user_id, email, roles, permissions }
}

// ── Magic-link sign-in (Phase 2) ─────────────────────────

// Always resolves the same generic response — never reveals whether the
// address has an account.
export function requestLoginLink(email) {
  return request('/auth/request-link', { method: 'POST', body: { email } });
}

// Consume a magic-link token; on success the server sets the session cookie.
export function verifyLogin(token, email) {
  return request('/auth/verify', { query: { token, email } });   // { user_id, email }
}

export function logout() {
  return request('/auth/logout', { method: 'POST' });
}

// Revoke every session for the current user (bumps token_version server-side),
// including this one. Used by "Sign out of all devices".
export function logoutAll() {
  return request('/auth/logout-all', { method: 'POST' });
}

// ── Personal API tokens (Phase 2) ────────────────────────
// Long-lived bearer credentials for non-browser clients (the H1B Scout
// extension). The raw secret is returned exactly once, on create.

export function fetchTokens() {
  return request('/auth/tokens');   // [ TokenInfo, ... ]
}

export function createToken({ name, expires_in_days = null }) {
  return request('/auth/tokens', { method: 'POST', body: { name, expires_in_days } });
}

export function revokeToken(id) {
  return request(`/auth/tokens/${id}`, { method: 'DELETE' });   // 204
}

// ── Admin (IAM management) ─────────────────────────────────
export function fetchAdminUsers({ limit = 100, offset = 0 } = {}) {
  return request('/admin/users', { query: { limit, offset } });
}

export function fetchAdminUser(id) {
  return request(`/admin/users/${id}`);
}

export function fetchRoles() {
  return request('/admin/roles');
}

export function assignRole(userId, role) {
  return request(`/admin/users/${userId}/roles`, { method: 'POST', body: { role } });
}

export function revokeRole(userId, role) {
  return request(`/admin/users/${userId}/roles/${encodeURIComponent(role)}`, { method: 'DELETE' });
}

export function setUserActive(userId, active) {
  return request(`/admin/users/${userId}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' });
}
