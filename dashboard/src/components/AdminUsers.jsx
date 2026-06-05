import { useEffect, useState } from 'react';
import {
  fetchAdminUsers, fetchAdminUser, fetchRoles,
  assignRole, revokeRole, setUserActive,
} from '../services/api';
import { useAuth, PERMS } from '../auth';

/**
 * Admin "Manage Users" page (Phase 1b).
 *
 * Lists users, shows each user's roles, and lets an admin assign/revoke roles
 * and activate/deactivate accounts. Gated on `users.manage` — the server
 * enforces the same; this gate just avoids showing a page that would 403.
 */
export function AdminUsers() {
  const { can } = useAuth();
  const allowed = can(PERMS.USERS_MANAGE);

  const [users, setUsers] = useState([]);     // [{id, email, is_active, roles?}]
  const [roles, setRoles] = useState([]);     // [{name, ...}]
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    if (!allowed) { setLoading(false); return; }
    (async () => {
      try {
        const [userList, roleList] = await Promise.all([fetchAdminUsers(), fetchRoles()]);
        // Pull each user's roles (the list endpoint omits them).
        const withRoles = await Promise.all(
          userList.map(async (u) => {
            try { const d = await fetchAdminUser(u.id); return { ...u, roles: d.roles || [] }; }
            catch { return { ...u, roles: [] }; }
          })
        );
        setUsers(withRoles);
        setRoles(roleList);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [allowed]);

  const patchUser = (id, patch) =>
    setUsers((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)));

  const onAssign = async (id, role) => {
    if (!role) return;
    setBusyId(id);
    try { const { roles: r } = await assignRole(id, role); patchUser(id, { roles: r }); }
    catch (err) { setError(err.message); }
    finally { setBusyId(null); }
  };

  const onRevoke = async (id, role) => {
    setBusyId(id);
    try { const { roles: r } = await revokeRole(id, role); patchUser(id, { roles: r }); }
    catch (err) { setError(err.message); }
    finally { setBusyId(null); }
  };

  const onToggleActive = async (id, current) => {
    setBusyId(id);
    try { const u = await setUserActive(id, !current); patchUser(id, { is_active: u.is_active }); }
    catch (err) { setError(err.message); }
    finally { setBusyId(null); }
  };

  if (!allowed) {
    return (
      <div style={{ padding: 24, color: 'var(--muted)' }}>
        You don't have permission to manage users.
      </div>
    );
  }

  return (
    <div className="admin-users" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Manage Users</h2>
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>{users.length} users</span>
      </div>

      {error && <div className="error-bar visible">{error}</div>}
      {loading ? (
        <div className="loading"><div className="spinner"></div> Loading…</div>
      ) : (
        <table className="data-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Email</th>
              <th>Status</th>
              <th>Roles</th>
              <th style={{ width: 220 }}>Add role</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ opacity: busyId === u.id ? 0.5 : 1 }}>
                <td>{u.email}</td>
                <td>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
                    background: u.is_active ? 'var(--tint-green, #0f2d1a)' : 'var(--tint-red, #2d1515)',
                    color: u.is_active ? '#6ee7b7' : '#fca5a5',
                  }}>
                    {u.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {(u.roles || []).map((r) => (
                      <span key={r} className="role-chip" style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontSize: 11, padding: '2px 6px', borderRadius: 6,
                        background: 'var(--surface, #1f2430)', border: '1px solid var(--line, #2d3340)',
                      }}>
                        {r}
                        <button
                          title={`Revoke ${r}`}
                          onClick={() => onRevoke(u.id, r)}
                          disabled={busyId === u.id}
                          style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}
                        >×</button>
                      </span>
                    ))}
                    {(u.roles || []).length === 0 && <span style={{ color: 'var(--muted)', fontSize: 12 }}>—</span>}
                  </div>
                </td>
                <td>
                  <select
                    className="form-select"
                    defaultValue=""
                    disabled={busyId === u.id}
                    onChange={(e) => { onAssign(u.id, e.target.value); e.target.value = ''; }}
                  >
                    <option value="" disabled>+ assign role…</option>
                    {roles
                      .filter((r) => !(u.roles || []).includes(r.name))
                      .map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
                  </select>
                </td>
                <td>
                  <button
                    className="btn btn-sm btn-secondary"
                    disabled={busyId === u.id}
                    onClick={() => onToggleActive(u.id, u.is_active)}
                  >
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
