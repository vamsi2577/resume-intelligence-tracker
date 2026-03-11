export function Toolbar({ search, onSearchChange, dateFrom, onDateFromChange, dateTo, onDateToChange, status, onStatusChange }) {
  const statuses = [
    { value: '', label: 'All', className: 'all' },
    { value: 'applied', label: 'Applied', className: 'applied' },
    { value: 'screening', label: 'Screening', style: { '--active-color': '#a78bfa' } },
    { value: 'interview', label: 'Interview', className: 'interview' },
    { value: 'assessment', label: 'Assessment' },
    { value: 'offer', label: 'Offer', className: 'offer' },
    { value: 'rejected', label: 'Rejected', className: 'rejected' },
    { value: 'withdrawn', label: 'Withdrawn', className: 'withdrawn' },
    { value: 'ghosted', label: 'Ghosted' },
  ];

  return (
    <div className="toolbar">
      <div className="search-wrap">
        <span className="search-icon">⌕</span>
        <input 
          type="text" 
          placeholder="Search company or role…" 
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <div className="date-wrap">
        <input 
          type="date" 
          title="Applied from" 
          value={dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
        />
        <span className="date-sep">→</span>
        <input 
          type="date" 
          title="Applied to" 
          value={dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
        />
      </div>
      <div className="status-filters">
        {statuses.map(s => {
          const isActive = status === s.value ? 'active' : '';
          const className = `chip ${s.className || ''} ${isActive}`.trim();
          return (
            <div 
              key={s.value}
              className={className}
              style={s.style}
              onClick={() => onStatusChange(s.value)}
            >
              {s.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}
