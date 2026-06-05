/* eslint-disable react-refresh/only-export-components -- context module intentionally exports the provider/gate components alongside the useAuth hook and PERMS constants. */
/**
 * Client-side auth/permission context (Phase 1b).
 *
 * Loads GET /auth/me once and exposes the caller's roles + effective
 * permissions. The <Can> gate and admin nav use this to decide what UI to show.
 *
 * This is UX only — the server re-checks every call via require_permission, so
 * hiding a button here is convenience, never the security boundary.
 */
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { fetchMe } from './services/api';

const AuthContext = createContext({
  me: null,
  loading: true,
  error: null,
  can: () => false,
  hasRole: () => false,
});

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchMe()
      .then((data) => { if (alive) setMe(data); })
      .catch((err) => { if (alive) setError(err.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const value = useMemo(() => {
    const perms = new Set(me?.permissions || []);
    const roles = new Set(me?.roles || []);
    return {
      me,
      loading,
      error,
      can: (perm) => perms.has(perm),
      hasRole: (role) => roles.has(role),
    };
  }, [me, loading, error]);

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
