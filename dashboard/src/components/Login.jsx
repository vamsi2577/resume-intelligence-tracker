import { useEffect, useRef, useState } from 'react';
import { requestLoginLink, verifyLogin } from '../services/api';
import { useAuth } from '../auth';

/**
 * Full-screen sign-in, shown when auth is enabled and there's no session.
 *
 * Two modes, chosen by the URL:
 *   1. Magic-link landing — the emailed link points at /login/verify?token&email
 *      (served client-side via the SPA fallback). On mount we consume the token,
 *      and on success refresh the auth context so the dashboard renders.
 *   2. Request a link — the default: enter an email, we POST /auth/request-link.
 *      The response is deliberately generic (no account-existence oracle).
 */
export function Login() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [verifying, setVerifying] = useState(false);
  // StrictMode mounts effects twice in dev — guard the one-shot verify.
  const verifiedOnce = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    const emailParam = params.get('email');
    if (!token || !emailParam || verifiedOnce.current) return;
    verifiedOnce.current = true;
    setVerifying(true);

    verifyLogin(token, emailParam)
      .then(async () => {
        // Strip the secret from the URL before anything else can read it.
        window.history.replaceState({}, '', window.location.pathname);
        await refresh();
      })
      .catch((err) => {
        setError(err.message || 'This sign-in link is invalid or has expired.');
        window.history.replaceState({}, '', window.location.pathname);
        setVerifying(false);
      });
  }, [refresh]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestLoginLink(email.trim());
      setSent(true);
    } catch (err) {
      setError(err.message || 'Could not send the link. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-brand">Resume Intelligence</div>

        {verifying ? (
          <>
            <h2>Signing you in…</h2>
            <p className="login-sub">Verifying your link.</p>
          </>
        ) : sent ? (
          <>
            <h2>Check your email</h2>
            <p className="login-sub">
              If <strong>{email}</strong> has an account, a sign-in link is on its
              way. The link expires shortly.
            </p>
            <button className="btn-link" onClick={() => { setSent(false); setEmail(''); }}>
              Use a different email
            </button>
          </>
        ) : (
          <>
            <h2>Sign in</h2>
            <p className="login-sub">
              We'll email you a one-time sign-in link — no password needed.
            </p>
            <form onSubmit={onSubmit} className="login-form">
              <input
                type="email"
                required
                autoFocus
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
              />
              <button type="submit" className="btn-primary" disabled={busy || !email.trim()}>
                {busy ? 'Sending…' : 'Email me a link'}
              </button>
            </form>
          </>
        )}

        {error && <div className="login-error">{error}</div>}
      </div>
    </div>
  );
}
