import { useEffect, useState } from 'react';
import { fetchHealth } from '../services/api';
import { Can, PERMS } from '../auth';

const ENV_COLORS = {
  development: { bg: '#dbeafe', fg: '#1d4ed8', label: 'DEV' },
  e2e:         { bg: '#fef3c7', fg: '#a16207', label: 'E2E' },
  staging:     { bg: '#fde68a', fg: '#92400e', label: 'STAGING' },
  production:  { bg: '#fee2e2', fg: '#b91c1c', label: 'PROD' },
  test:        { bg: '#e5e7eb', fg: '#374151', label: 'TEST' },
  unknown:     { bg: '#e5e7eb', fg: '#374151', label: '?' },
};

function EnvBadge({ env }) {
  const style = ENV_COLORS[env] || ENV_COLORS.unknown;
  return (
    <div
      className="env-badge"
      title={`Backend reports APP_ENV=${env}. Don't act on prod data unless you mean to.`}
      style={{
        background: style.bg,
        color: style.fg,
        fontSize: 10,
        fontWeight: 700,
        padding: '2px 8px',
        borderRadius: 999,
        letterSpacing: 0.5,
      }}
    >
      {style.label}
    </div>
  );
}

export function Header({ stats, activeCount, activeTab, onTabChange }) {
  const { total = '-', interview = '-', rejected = '-', offer = '-' } = stats || {};
  const [env, setEnv] = useState('unknown');

  useEffect(() => {
    fetchHealth().then((h) => h && setEnv(h.env));
  }, []);

  return (
    <header>
      <div className="header-left">
        <div className="header-tag" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>Resume Intelligence · Phase 2</span>
          <EnvBadge env={env} />
        </div>
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
        <button
          className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => onTabChange('history')}
        >
          ◷ Generation History
        </button>
        <Can perm={PERMS.USERS_MANAGE}>
          <button
            className={`tab-btn ${activeTab === 'admin' ? 'active' : ''}`}
            onClick={() => onTabChange('admin')}
          >
            ⚙ Manage Users
          </button>
        </Can>
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
