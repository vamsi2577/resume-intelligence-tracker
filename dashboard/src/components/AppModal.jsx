import { useState } from 'react';
import { STATUS_OPTIONS, SOURCE_OPTIONS, WORK_TYPE_OPTIONS } from '../utils';

const EMPTY = {
  company_name: '', job_title: '', source: 'manual',
  applied_date: new Date().toISOString().split('T')[0],
  status: 'applied', job_url: '', location: '', work_type: '',
  salary_range: '', contact_name: '', contact_email: '',
  job_description: '', notes: '', needs_review: false,
};

export function AppModal({ isOpen, onClose, onCreate }) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const set = (key) => (e) => setForm(f => ({
    ...f,
    [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
  }));

  const handleSubmit = async () => {
    if (!form.company_name.trim() || !form.job_title.trim()) {
      setError('Company name and job title are required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v !== '' && v !== null)
      );
      await onCreate(payload);
      setForm(EMPTY);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => { setForm(EMPTY); setError(null); onClose(); };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <span>Log Application</span>
          <button className="drawer-close" onClick={handleClose}>✕</button>
        </div>

        <div className="modal-body">
          {error && <div className="form-error">{error}</div>}

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Company Name *</label>
              <input className="form-input" value={form.company_name} onChange={set('company_name')} placeholder="e.g. Google" />
            </div>
            <div className="form-group">
              <label className="form-label">Job Title *</label>
              <input className="form-input" value={form.job_title} onChange={set('job_title')} placeholder="e.g. Senior Software Engineer" />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Applied Date *</label>
              <input className="form-input" type="date" value={form.applied_date} onChange={set('applied_date')} />
            </div>
            <div className="form-group">
              <label className="form-label">Status</label>
              <select className="form-select" value={form.status} onChange={set('status')}>
                {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Source</label>
              <select className="form-select" value={form.source} onChange={set('source')}>
                {SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Work Type</label>
              <select className="form-select" value={form.work_type} onChange={set('work_type')}>
                {WORK_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Location</label>
              <input className="form-input" value={form.location} onChange={set('location')} placeholder="e.g. Austin, TX" />
            </div>
            <div className="form-group">
              <label className="form-label">Salary Range</label>
              <input className="form-input" value={form.salary_range} onChange={set('salary_range')} placeholder="e.g. $120k–$150k" />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Job URL</label>
            <input className="form-input" type="url" value={form.job_url} onChange={set('job_url')} placeholder="https://…" />
          </div>

          <div className="form-group">
            <label className="form-label">Job Description</label>
            <textarea className="form-textarea" rows={4} value={form.job_description} onChange={set('job_description')} placeholder="Paste the full job description…" />
          </div>

          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea className="form-textarea" rows={3} value={form.notes} onChange={set('notes')} placeholder="Any notes about this application…" />
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={handleClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
            {saving ? 'Saving…' : 'Log Application'}
          </button>
        </div>
      </div>
    </div>
  );
}
