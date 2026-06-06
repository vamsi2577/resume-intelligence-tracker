import { useEffect, useState } from 'react';
import { useAuth } from '../auth';
import { fetchTokens, createToken, revokeToken, logoutAll } from '../services/api';

function fmtDate(s) {
  if (!s) return '—';
  try { return new Date(s).toLocaleDateString(); } catch { return s; }
}

/**
 * "My Account" — identity + personal API token management.
 *
 * API tokens are the bearer credential the H1B Scout extension uses to reach
 * the RIT bridge (its chrome-extension:// origin can't carry the session
 * cookie). The raw secret is shown exactly once, right after creation.
 */
export function Account() {
  const { me, signOut } = useAuth();
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Create form
  const [name, setName] = useState('');
  const [expiry, setExpiry] = useState('');   // '' = never
  const [creating, setCreating] = useState(false);
  const [newSecret, setNewSecret] = useState(null);   // shown once
  const [copied, setCopied] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setTokens(await fetchTokens());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const onCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    setNewSecret(null);
    try {
      const body = { name: name.trim() };
      if (expiry) body.expires_in_days = Number(expiry);
      const created = await createToken(body);
      setNewSecret(created.token);
      setName('');
      setExpiry('');
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const onRevoke = async (id) => {
    if (!window.confirm('Revoke this token? Any client using it will stop working immediately.')) return;
    try {
      await revokeToken(id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const copySecret = async () => {
    try {
      await navigator.clipboard.writeText(newSecret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard may be unavailable; the value is selectable */ }
  };

  return (
    <div className="account">
      <section className="account-card">
        <h2>Account</h2>
        <div className="account-row"><span className="lbl">Email</span><span>{me?.email || '—'}</span></div>
        <div className="account-row">
          <span className="lbl">Roles</span>
          <span>{(me?.roles || []).join(', ') || '—'}</span>
        </div>
        <div className="account-actions">
          <button className="btn-secondary" onClick={signOut}>Sign out</button>
          <button
            className="btn-link danger"
            onClick={async () => {
              if (!window.confirm('Sign out of all devices? Every active session (including this one) will be ended.')) return;
              try { await logoutAll(); } catch { /* revoked anyway */ }
              await signOut();
            }}
          >
            Sign out of all devices
          </button>
        </div>
      </section>

      <section className="account-card">
        <h2>API tokens</h2>
        <p className="account-sub">
          Bearer tokens for clients that can't sign in with a browser — chiefly
          the H1B Scout extension. Paste a token into the extension's settings to
          connect it to your tracker. The secret is shown only once.
        </p>

        {newSecret && (
          <div className="token-secret">
            <div className="token-secret-label">
              Copy your new token now — you won't see it again:
            </div>
            <div className="token-secret-row">
              <code>{newSecret}</code>
              <button className="btn-secondary" onClick={copySecret}>
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        <form className="token-create" onSubmit={onCreate}>
          <input
            type="text"
            placeholder="Token name (e.g. Work laptop)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            required
          />
          <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            <option value="">Never expires</option>
            <option value="30">30 days</option>
            <option value="90">90 days</option>
            <option value="365">1 year</option>
          </select>
          <button type="submit" className="btn-primary" disabled={creating || !name.trim()}>
            {creating ? 'Creating…' : 'Create token'}
          </button>
        </form>

        {error && <div className="account-error">{error}</div>}

        {loading ? (
          <div className="account-empty">Loading…</div>
        ) : tokens.length === 0 ? (
          <div className="account-empty">No tokens yet.</div>
        ) : (
          <table className="token-table">
            <thead>
              <tr>
                <th>Name</th><th>Prefix</th><th>Created</th>
                <th>Last used</th><th>Expires</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => {
                const revoked = !!t.revoked_at;
                const expired = t.expires_at && new Date(t.expires_at) <= new Date();
                return (
                  <tr key={t.id} className={revoked || expired ? 'token-dead' : ''}>
                    <td>{t.name}</td>
                    <td><code>{t.token_prefix}…</code></td>
                    <td>{fmtDate(t.created_at)}</td>
                    <td>{fmtDate(t.last_used_at)}</td>
                    <td>{t.expires_at ? fmtDate(t.expires_at) : 'Never'}</td>
                    <td>
                      {revoked ? <span className="pill dead">Revoked</span>
                        : expired ? <span className="pill dead">Expired</span>
                        : <span className="pill live">Active</span>}
                    </td>
                    <td>
                      {!revoked && (
                        <button className="btn-link danger" onClick={() => onRevoke(t.id)}>
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
