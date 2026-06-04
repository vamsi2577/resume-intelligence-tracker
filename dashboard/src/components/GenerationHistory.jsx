import { useEffect, useState } from 'react';
import { fetchGenerationHistory } from '../services/api';

const STATUS_STYLE = {
  success:          { bg: '#dcfce7', fg: '#15803d', label: 'success' },
  llm_error:        { bg: '#fee2e2', fg: '#b91c1c', label: 'llm error' },
  validation_error: { bg: '#fef3c7', fg: '#a16207', label: 'validation' },
};

function StatusPill({ status }) {
  const s = STATUS_STYLE[status] || { bg: '#e5e7eb', fg: '#374151', label: status };
  return (
    <span
      style={{
        background: s.bg, color: s.fg, fontSize: 11, fontWeight: 700,
        padding: '2px 8px', borderRadius: 999, letterSpacing: 0.3,
        whiteSpace: 'nowrap',
      }}
    >
      {s.label}
    </span>
  );
}

function fmtWhen(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function GenerationHistory() {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchGenerationHistory(100);
      setRows(resp.data || []);
      setStats(resp.stats || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="generation-history" style={{ padding: '16px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Generation history</h2>
        <button className="btn btn-primary btn-sm" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      {/* ── Aggregate stats ── */}
      {stats && (
        <div className="header-stats" style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div className="stat-chip"><div className="val">{stats.total}</div><div className="lbl">Total</div></div>
          <div className="stat-chip"><div className="val">{Math.round((stats.success_rate || 0) * 100)}%</div><div className="lbl">Success</div></div>
          <div className="stat-chip rejected"><div className="val">{stats.llm_error + stats.validation_error}</div><div className="lbl">Failures</div></div>
          <div className="stat-chip"><div className="val">{stats.avg_duration_ms != null ? `${stats.avg_duration_ms}ms` : '–'}</div><div className="lbl">Avg latency</div></div>
          <div className="stat-chip"><div className="val">{(stats.total_tokens || 0).toLocaleString()}</div><div className="lbl">Tokens</div></div>
        </div>
      )}

      {error && <div className="error-bar visible">{error}</div>}

      {loading ? (
        <div className="loading"><div className="spinner"></div> Loading history…</div>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <div className="icon">⟡</div>
          <p>No résumé generations yet. Generate one from a job description to see telemetry here.</p>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Status</th>
              <th>Company</th>
              <th>Role</th>
              <th>Model</th>
              <th style={{ textAlign: 'right' }}>Tokens</th>
              <th style={{ textAlign: 'right' }}>Latency</th>
              <th>Mode</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="date" title={r.created_at}>{fmtWhen(r.created_at)}</td>
                <td><StatusPill status={r.status} /></td>
                <td className="company">{r.target_company || '–'}</td>
                <td className="title">{r.job_title || '–'}</td>
                <td style={{ fontSize: 12, color: 'var(--muted)' }}>{r.model || '–'}</td>
                <td style={{ textAlign: 'right' }}>{r.total_tokens != null ? r.total_tokens.toLocaleString() : '–'}</td>
                <td style={{ textAlign: 'right' }}>{r.duration_ms != null ? `${r.duration_ms}ms` : '–'}</td>
                <td>
                  {r.preview
                    ? <span className="work-type-tag">preview</span>
                    : <span style={{ color: 'var(--muted)', fontSize: 12 }}>committed</span>}
                </td>
                <td style={{ maxWidth: 280 }}>
                  {r.error_message
                    ? <span style={{ color: 'var(--danger, #d33)', fontSize: 12 }} title={r.error_message}>
                        {r.error_message.length > 60 ? r.error_message.slice(0, 60) + '…' : r.error_message}
                      </span>
                    : r.application_id
                      ? <span style={{ fontSize: 11, color: 'var(--muted)' }} title={`Application ${r.application_id}`}>
                          logged · {r.application_id.slice(0, 8)}
                        </span>
                      : <span style={{ color: 'var(--muted)' }}>–</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {rows.some((r) => r.correlation_id) && (
        <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
          Each row carries a correlation ID that joins to the backend logs — quote it when reporting a failed generation.
        </p>
      )}
    </div>
  );
}
