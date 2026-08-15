import React, { useEffect, useState } from 'react';

export const OwnerAuthGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then((response) => response.json())
      .then((data) => setAuthenticated(Boolean(data.authenticated)))
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  const login = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      const data = await response.json();
      if (!response.ok || !data.authenticated) throw new Error(data.error || 'Access denied');
      setPassword('');
      setAuthenticated(true);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Access denied');
    } finally {
      setBusy(false);
    }
  };

  if (checking) {
    return <div className="min-h-screen bg-black text-cyan-200 flex items-center justify-center font-mono tracking-widest">AUTHENTICATING JARVIS OWNER...</div>;
  }

  if (authenticated) return <>{children}</>;

  return (
    <div className="min-h-screen bg-black text-cyan-100 flex items-center justify-center px-6 font-mono">
      <div className="w-full max-w-md border border-cyan-500/40 bg-slate-950/85 rounded-xl p-8 shadow-[0_0_45px_rgba(0,220,255,0.12)]">
        <div className="text-xs tracking-[0.45em] text-cyan-400 mb-3">JARVIS // PRIVATE CORE</div>
        <h1 className="text-2xl tracking-[0.22em] font-semibold mb-2">OWNER ACCESS</h1>
        <p className="text-sm text-slate-400 mb-7 leading-6">Private memory and personal context are locked. Authenticate before entering the HUD.</p>
        <form onSubmit={login} className="space-y-4">
          <input
            autoFocus
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Owner passphrase"
            className="w-full rounded-lg border border-cyan-500/30 bg-black/70 px-4 py-3 outline-none focus:border-cyan-300 text-cyan-100 placeholder:text-slate-600"
            autoComplete="current-password"
          />
          {error && <div className="text-xs text-red-400">{error}</div>}
          <button
            type="submit"
            disabled={busy || !password}
            className="w-full rounded-lg border border-cyan-400/50 bg-cyan-500/10 px-4 py-3 text-sm tracking-[0.18em] text-cyan-100 hover:bg-cyan-400/15 disabled:opacity-40"
          >
            {busy ? 'VERIFYING...' : 'UNLOCK JARVIS'}
          </button>
        </form>
      </div>
    </div>
  );
};
