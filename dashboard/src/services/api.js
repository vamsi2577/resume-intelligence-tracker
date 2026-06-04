export const API_BASE = '/api/v1';

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
    Object.entries(params).filter(([_, v]) => v != null && v !== '')
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
