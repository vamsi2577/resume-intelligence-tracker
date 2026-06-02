import { useState, useEffect } from 'react';
import { STATUS_LABEL, STATUS_OPTIONS, WORK_TYPE_OPTIONS } from '../utils';
import { downloadResume } from '../services/api';

export function Drawer({ app, history, loading, isOpen, onClose, onUpdate, onDelete }) {
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [downloadingResume, setDownloadingResume] = useState(false);
  const [form, setForm] = useState({});

  useEffect(() => {
    if (app) {
      setForm({
        status: app.status || 'applied',
        notes: app.notes || '',
        contact_name: app.contact_name || '',
        contact_email: app.contact_email || '',
        follow_up_date: app.follow_up_date || '',
        work_type: app.work_type || '',
        salary_range: app.salary_range || '',
        location: app.location || '',
        job_url: app.job_url || '',
        needs_review: app.needs_review || false,
      });
      setEditError(null);
    }
  }, [app]);

  const handleSave = async () => {
    setSaving(true);
    setEditError(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([_, v]) => v !== '' && v !== null)
      );
      await onUpdate(app.id, payload);
    } catch (err) {
      setEditError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const set = (key) => (e) => setForm(f => ({
    ...f,
    [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
  }));

  return (
    <div className={`drawer ${isOpen ? 'open' : ''}`} id="drawer">
      <div className="drawer-inner">
        {loading ? (
          <div className="loading"><div className="spinner"></div> Loading…</div>
        ) : app ? (
          <>
            {/* ── Header ── */}
            <div className="drawer-header">
              <div>
                <div className="drawer-company">{app.company_name}</div>
                <div className="drawer-title">{app.job_title}</div>
              </div>
              <button className="drawer-close" onClick={onClose}>✕</button>
            </div>

            {/* ── Always-editable form ── */}
            <div className="edit-form">
              {editError && <div className="form-error">{editError}</div>}

              <div className="form-group">
                <label className="form-label">Status</label>
                <select className="form-select" value={form.status || ''} onChange={set('status')}>
                  {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Work Type</label>
                  <select className="form-select" value={form.work_type || ''} onChange={set('work_type')}>
                    {WORK_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Salary Range</label>
                  <input className="form-input" value={form.salary_range || ''} onChange={set('salary_range')} placeholder="e.g. $120k–$150k" />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Location</label>
                  <input className="form-input" value={form.location || ''} onChange={set('location')} placeholder="City, State or Remote" />
                </div>
                <div className="form-group">
                  <label className="form-label">
                    Job Link{' '}
                    {form.job_url && (
                      <a
                        href={form.job_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 11, marginLeft: 4, textDecoration: 'none' }}
                        title="Open job post in new tab"
                      >
                        ↗
                      </a>
                    )}
                  </label>
                  <input
                    className="form-input"
                    type="url"
                    value={form.job_url || ''}
                    onChange={set('job_url')}
                    placeholder="https://…"
                  />
                </div>
              </div>

              <div className="drawer-section-title" style={{ marginTop: '4px' }}>Recruiter</div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Contact Name</label>
                  <input className="form-input" value={form.contact_name || ''} onChange={set('contact_name')} placeholder="Name" />
                </div>
                <div className="form-group">
                  <label className="form-label">Contact Email</label>
                  <input className="form-input" type="email" value={form.contact_email || ''} onChange={set('contact_email')} placeholder="email@company.com" />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Follow-up Date</label>
                  <input className="form-input" type="date" value={form.follow_up_date || ''} onChange={set('follow_up_date')} />
                </div>
                <div className="form-group" style={{ justifyContent: 'flex-end', paddingTop: '22px' }}>
                  <label className="toggle-label">
                    <input type="checkbox" checked={!!form.needs_review} onChange={set('needs_review')} />
                    <span style={{ marginLeft: '6px' }}>Needs Review</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Notes</label>
                <textarea className="form-textarea" rows={4} value={form.notes || ''} onChange={set('notes')} placeholder="Add notes…" />
              </div>

              {/* ── Read-only details ── */}
              <div className="drawer-section-title" style={{ marginTop: '8px' }}>Details</div>
              <div className="drawer-meta">
                <div className="meta-item">
                  <div className="meta-label">Applied</div>
                  <div className="meta-value">{app.applied_date || '–'}</div>
                </div>
                <div className="meta-item">
                  <div className="meta-label">Source</div>
                  <div className="meta-value">{app.source || '–'}</div>
                </div>
              </div>

              {/* ── Timeline ── */}
              {history && history.length > 0 && (
                <>
                  <div className="drawer-section-title">Timeline</div>
                  <div className="timeline">
                    {history.map(item => (
                      <div className="tl-item" key={item.id || Math.random()}>
                        <div className="tl-status">{STATUS_LABEL[item.status] || item.status}</div>
                        <div className="tl-date">{new Date(item.changed_at || item.created_at || Date.now()).toLocaleDateString()}</div>
                        {item.note && <div className="tl-note">{item.note}</div>}
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* ── Phase 3 Placeholder ── */}
              <div className="drawer-section-title" style={{ marginTop: '16px' }}>Analysis</div>
              <div className="phase3-placeholder">
                <div className="phase3-icon">⟡</div>
                <div className="phase3-label">Resume Analysis</div>
                <div className="phase3-desc">Available in Phase 3</div>
              </div>

              <div className="edit-actions" style={{ gap: 8, display: 'flex', flexWrap: 'wrap' }}>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving…' : 'Save Changes'}
                </button>
                {app.resume_content && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={async () => {
                      setDownloadingResume(true);
                      try { await downloadResume(app.id); }
                      catch (err) { setEditError(err.message); }
                      finally { setDownloadingResume(false); }
                    }}
                    disabled={downloadingResume}
                    title="Re-download the tailored résumé that was generated for this application"
                  >
                    {downloadingResume ? 'Downloading…' : '↓ Resume'}
                  </button>
                )}
                {onDelete && (
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={async () => {
                      if (!confirm('Soft-delete this application? You can restore it by listing with include_deleted=true.')) return;
                      setDeleting(true);
                      try { await onDelete(app.id); onClose?.(); }
                      catch (err) { setEditError(err.message); }
                      finally { setDeleting(false); }
                    }}
                    disabled={deleting || app.is_deleted}
                    style={{ marginLeft: 'auto' }}
                  >
                    {deleting ? 'Deleting…' : (app.is_deleted ? 'Already deleted' : 'Delete')}
                  </button>
                )}
              </div>
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--muted)', fontSize: '13px', padding: '20px' }}>
            Select an application to view details.
          </div>
        )}
      </div>
    </div>
  );
}
