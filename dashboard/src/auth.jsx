/* eslint-disable react-refresh/only-export-components -- context module intentionally exports the provider/gate components alongside the useAuth hook and PERMS constants. */
/**
 * Client-side auth/permission context.
 *
 * Loads GET /auth/me and exposes the caller's identity, roles, and effective
 * permissions, plus the sign-in state used to gate the whole app:
 *
 *   - loading     — the initial /auth/me probe is in flight
 *   - needsLogin  — auth is enabled and there's no valid session (401); the
 *                   app renders the login screen instead of the dashboard
 *   - me          — the signed-in (or default-owner) identity
 *
 * A 401 from any request (here or via services/api request()) flips
 * needsLogin, so an expired cookie mid-session bounces the user to login.
 *
 * Permissions here are UX only — the server re-checks every call via
 * require_permission, so hiding a button is convenience, never the boundary.
 */
import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { fetchMe, logout as apiLogout, setUnauthorizedHandler } from './services/api';

const AuthContext = createContext({
  me: null,
  loading: true,
  error: null,
  needsLogin: false,
  can: () => false,
  hasRole: () => false,
  refresh: async () => {},
  signOut: async () => {},
});

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [needsLogin, setNeedsLogin] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMe();
      setMe(data);
      setNeedsLogin(false);
    } catch (err) {
      if (err.status === 401) {
        setMe(null);
        setNeedsLogin(true);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    try { await apiLogout(); } catch { /* clearing cookie is best-effort */ }
    setMe(null);
    setNeedsLogin(true);
  }, []);

  // Any 401 anywhere → show the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setNeedsLogin(true));
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const value = useMemo(() => {
    const perms = new Set(me?.permissions || []);
    const roles = new Set(me?.roles || []);
    return {
      me,
      loading,
      error,
      needsLogin,
      can: (perm) => perms.has(perm),
      hasRole: (role) => roles.has(role),
      refresh,
      signOut,
    };
  }, [me, loading, error, needsLogin, refresh, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

/** Render children only when the current user holds `perm`. */
export function Can({ perm, children, fallback = null }) {
  const { can } = useAuth();
  return can(perm) ? children : fallback;
}

// Permission keys — must match src/core/permissions.py on the backend.
export const PERMS = {
  USERS_MANAGE: 'users.manage',
  ROLES_MANAGE: 'roles.manage',
};
