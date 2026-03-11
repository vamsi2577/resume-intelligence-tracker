export const API_BASE = '/api/v1';

export async function fetchApplications(params) {
  // Filter out any empty string parameters before sending
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

export async function fetchAllApps() {
  const resp = await fetch(`${API_BASE}/applications?limit=1000&page=1`);
  if (!resp.ok) return null;
  return resp.json();
}
