export function Header({ stats, activeCount, activeTab, onTabChange }) {
  const { total = '-', interview = '-', rejected = '-', offer = '-' } = stats || {};
  return (
    <header>
      <div className="header-left">
        <div className="header-tag">Resume Intelligence · Phase 2</div>
        <h1>Application <span>Tracker</span></h1>
      </div>

      <div className="header-center">
        <button
          className={`tab-btn ${activeTab === 'tracker' ? 'active' : ''}`}
          onClick={() => onTabChange('tracker')}
        >
          ◈ Tracker
        </button>
        <button
          className={`tab-btn ${activeTab === 'resume' ? 'active' : ''}`}
          onClick={() => onTabChange('resume')}
        >
          ⟡ Resume Generator
        </button>
      </div>

      <div className="header-right">
        {activeCount > 0 && (
          <div className="nr-badge">
            <div className="nr-dot"></div>
            <span>{activeCount}</span> needs review
          </div>
        )}
        <div className="header-stats">
          <div className="stat-chip">
            <div className="val">{total}</div>
            <div className="lbl">Total</div>
          </div>
          <div className="stat-chip interviews">
            <div className="val">{interview}</div>
            <div className="lbl">Interviews</div>
          </div>
          <div className="stat-chip rejected">
            <div className="val">{rejected}</div>
            <div className="lbl">Rejected</div>
          </div>
          <div className="stat-chip offers">
            <div className="val">{offer}</div>
            <div className="lbl">Offers</div>
          </div>
        </div>
      </div>
    </header>
  );
}
