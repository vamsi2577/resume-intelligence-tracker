import { STATUS_LABEL } from '../utils';

export function Table({ data, loading, selectedId, onRowClick, sort, onSort }) {
  if (loading) {
    return (
      <div className="loading" id="loadingState">
        <div className="spinner"></div> Loading applications…
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="empty-state" id="emptyState">
        <div className="icon">◈</div>
        <p>No applications match your filters.</p>
      </div>
    );
  }

  const renderSortArrow = (field) => {
    if (sort.field !== field) return <span className="sort-arrow">↕</span>;
    return <span className="sort-arrow">{sort.dir === 'asc' ? '↑' : '↓'}</span>;
  };

  const handleSort = (field) => {
    onSort(field);
  };

  return (
    <table id="appTable">
      <thead>
        <tr>
          <th onClick={() => handleSort('company_name')} className={sort.field === 'company_name' ? 'sorted' : ''}>
            Company {renderSortArrow('company_name')}
          </th>
          <th onClick={() => handleSort('job_title')} className={sort.field === 'job_title' ? 'sorted' : ''}>
            Role {renderSortArrow('job_title')}
          </th>
          <th onClick={() => handleSort('status')} className={sort.field === 'status' ? 'sorted' : ''}>
            Status {renderSortArrow('status')}
          </th>
          <th onClick={() => handleSort('applied_date')} className={sort.field === 'applied_date' ? 'sorted' : ''}>
            Applied {renderSortArrow('applied_date')}
          </th>
          <th>Source</th>
          <th>Type</th>
          <th>Location</th>
          <th aria-label="Job link"></th>
        </tr>
      </thead>
      <tbody id="tableBody">
        {data.map(app => (
          <tr 
            key={app.id} 
            className={selectedId === app.id ? 'selected' : ''}
            onClick={() => onRowClick(app.id)}
          >
            <td className="company">{app.company_name}</td>
            <td className="title">{app.job_title}</td>
            <td><span className={`badge ${app.status}`}>{STATUS_LABEL[app.status] || app.status}</span></td>
            <td className="date">{app.applied_date}</td>
            <td>{app.source || '–'}</td>
            <td>{app.work_type ? <span className="work-type-tag">{app.work_type}</span> : '–'}</td>
            <td>{app.location || '–'}</td>
            <td onClick={(e) => e.stopPropagation()} style={{ textAlign: 'center' }}>
              {app.job_url ? (
                <a
                  href={app.job_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={app.job_url}
                  style={{ textDecoration: 'none' }}
                >
                  ↗
                </a>
              ) : (
                <span style={{ color: 'var(--muted)' }}>–</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
