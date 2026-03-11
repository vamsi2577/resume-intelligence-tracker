import { STATUS_LABEL } from '../utils';

export function Drawer({ app, history, loading, isOpen, onClose }) {
  return (
    <div className={`drawer ${isOpen ? 'open' : ''}`} id="drawer">
      <div className="drawer-inner">
        {loading ? (
          <div className="loading"><div className="spinner"></div> Loading…</div>
        ) : app ? (
          <>
            <div className="drawer-header">
              <div>
                <div className="drawer-company">{app.company_name}</div>
                <div className="drawer-title">{app.job_title}</div>
              </div>
              <button className="drawer-close" onClick={onClose}>✕ Close</button>
            </div>

            <div className="drawer-meta">
              <div className="meta-item">
                <div className="meta-label">Status</div>
                <div className="meta-value">
                  <span className={`badge ${app.status}`}>{STATUS_LABEL[app.status] || app.status}</span>
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Applied</div>
                <div className="meta-value">{app.applied_date}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Source</div>
                <div className="meta-value">{app.source || '–'}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Work Type</div>
                <div className="meta-value">{app.work_type || '–'}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Location</div>
                <div className="meta-value">{app.location || '–'}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Job Link</div>
                <div className="meta-value">
                  {app.job_url ? (
                    <a href={app.job_url} target="_blank" rel="noopener noreferrer">↗ Job Link</a>
                  ) : '–'}
                </div>
              </div>
            </div>
            
            {(history && history.length > 0) && (
              <>
                <div className="drawer-section-title">Timeline</div>
                <div className="timeline">
                  {history.map(item => (
                    <div className="tl-item" key={item.id || Math.random()}>
                      <div className="tl-status">{STATUS_LABEL[item.status] || item.status}</div>
                      <div className="tl-date">{new Date(item.created_at || new Date()).toLocaleDateString()}</div>
                      {item.notes && <div className="tl-note">{item.notes}</div>}
                    </div>
                  ))}
                </div>
              </>
            )}
            
            {app.notes && (
              <>
                <div className="drawer-section-title" style={{ marginTop: '20px' }}>Notes</div>
                <div className="notes-box">{app.notes}</div>
              </>
            )}
          </>
        ) : (
          <div style={{ color: 'var(--danger)', fontSize: '12px', padding: '20px' }}>
            No details to display.
          </div>
        )}
      </div>
    </div>
  );
}
