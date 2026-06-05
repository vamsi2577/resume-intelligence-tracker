export const API_BASE = '/api/v1';

// ── Shared request helper + 401 interceptor ────────────────
// A single place that turns a 401 into a global "you need to sign in" signal.
// AuthProvider registers a handler here; any request that comes back 401 (e.g.
// the session cookie expired mid-session) flips the app to the login screen.
let _onUnauthorized = null;
export function setUnauthorizedHandler(fn) { _onUnauthorized = fn; }

export async function request(path, { method = 'GET', body } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(`${API_BASE}${path}`, opts);

  if (resp.status === 401) {
    if (_onUnauthorized) _onUnauthorized();
    const err = new Error('Authentication required');
    err.status = 401;
    throw err;
  }

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

// Fetch the backend's /health to read its self-reported environment.
// Cached on first call so the env badge doesn't ping the API repeatedly.
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

export async function fetchApplications(params) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v != null && v !== '')
  );
  const query = new URLSearchParams(cleanParams);
  const resp = await fetch(`${API_BASE}/applications?${query}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchHistory(id) {
  const resp = await fetch(`${API_BASE}/applications/${id}/history`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchStats() {
  const resp = await fetch(`${API_BASE}/applications/stats`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function createApplication(data) {
  const resp = await fetch(`${API_BASE}/log-application`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await resp.json();
  if (!resp.ok) throw new Error(json.detail || `HTTP ${resp.status}`);
  return json;
}

export async function updateApplication(id, data) {
  const resp = await fetch(`${API_BASE}/log-application/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await resp.json();
  if (!resp.ok) throw new Error(json.detail || `HTTP ${resp.status}`);
  return json;
}

export async function generateResume(data) {
  const resp = await fetch(`${API_BASE}/generate-resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  const blob = await resp.blob();
  const disposition = resp.headers.get('Content-Disposition') || '';
  const filename = disposition.split('filename=')[1]?.replace(/"/g, '') || 'Resume.docx';
  const applicationId = resp.headers.get('X-Application-Id');
  const duplicateWarning = resp.headers.get('X-Duplicate-Warning') === 'true';

  // Trigger browser download
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  return { applicationId, duplicateWarning, filename };
}

// ── Soft-delete ────────────────────────────────────────────
export async function deleteApplication(id) {
  const resp = await fetch(`${API_BASE}/applications/${id}`, { method: 'DELETE' });
  const json = await resp.json();
  if (!resp.ok) throw new Error(json.detail || `HTTP ${resp.status}`);
  return json;
}

// ── Re-download an already-generated résumé as DOCX ────────
export async function downloadResume(id) {
  const resp = await fetch(`${API_BASE}/applications/${id}/resume`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  const blob = await resp.blob();
  const disposition = resp.headers.get('Content-Disposition') || '';
  const filename = disposition.split('filename=')[1]?.replace(/"/g, '') || 'Resume.docx';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return { filename };
}

// ── JD → tailored résumé via backend LLM ───────────────────
// preview=true returns the structured ResumeRequest JSON for review;
// preview=false (default) triggers a DOCX download and auto-logs the
// application — same UX as generateResume().
export async function generateResumeFromJD(data, { preview = false } = {}) {
  const url = `${API_BASE}/generate-resume-from-jd${preview ? '?preview=true' : ''}`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  if (preview) {
    return resp.json();        // { tailored: ResumeRequest }
  }

  const blob = await resp.blob();
  const disposition = resp.headers.get('Content-Disposition') || '';
  const filename = disposition.split('filename=')[1]?.replace(/"/g, '') || 'Resume.docx';
  const applicationId = resp.headers.get('X-Application-Id');
  const duplicateWarning = resp.headers.get('X-Duplicate-Warning') === 'true';

  const dl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = dl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(dl);

  return { applicationId, duplicateWarning, filename };
}

// ── Base résumé (master copy fed into the LLM) ─────────────
export async function getBaseResume() {
  const resp = await fetch(`${API_BASE}/base-resume`);
  if (resp.status === 404) return null;                  // nothing uploaded yet
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function saveBaseResume(data) {
  const resp = await fetch(`${API_BASE}/base-resume`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await resp.json();
  if (!resp.ok) throw new Error(json.detail || `HTTP ${resp.status}`);
  return json;
}

// ── Résumé-generation audit log (observability) ────────────
export async function fetchGenerationHistory(limit = 50) {
  const resp = await fetch(`${API_BASE}/generation-history?limit=${limit}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // { data: [...], stats: {...} }
}

// ── IAM / auth (Phase 1b) ────────────────────────────────

// The caller's identity, roles, and effective permissions. The <Can> gate and
// admin nav read this; the server still enforces every call.
export async function fetchMe() {
  // Routed through request() so a 401 (auth on, not signed in) trips the
  // global handler and the app shows the login screen.
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
  const q = new URLSearchParams({ token, email });
  return request(`/auth/verify?${q}`);   // { user_id, email }
}

export function logout() {
  return request('/auth/logout', { method: 'POST' });
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

export async function fetchAdminUsers({ limit = 100, offset = 0 } = {}) {
  const resp = await fetch(`${API_BASE}/admin/users?limit=${limit}&offset=${offset}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // [ {id, email, is_active, created_at}, ... ]
}

export async function fetchAdminUser(id) {
  const resp = await fetch(`${API_BASE}/admin/users/${id}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // { ...user, roles: [...] }
}

export async function fetchRoles() {
  const resp = await fetch(`${API_BASE}/admin/roles`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // [ {id, name, description, is_system}, ... ]
}

export async function assignRole(userId, role) {
  const resp = await fetch(`${API_BASE}/admin/users/${userId}/roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // { user_id, roles: [...] }
}

export async function revokeRole(userId, role) {
  const resp = await fetch(`${API_BASE}/admin/users/${userId}/roles/${encodeURIComponent(role)}`, {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // { user_id, roles: [...] }
}

export async function setUserActive(userId, active) {
  const action = active ? 'activate' : 'deactivate';
  const resp = await fetch(`${API_BASE}/admin/users/${userId}/${action}`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();   // updated user
}
