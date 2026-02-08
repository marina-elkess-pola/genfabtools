import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();
    // Dev-only: allow quick mocking of login when not using a real backend.
    // Set VITE_MOCK_LOGIN=true in frontend/.env.local to enable, or the mock
    // will be enabled automatically in Vite dev mode (import.meta.env.DEV).
    const MOCK_LOGIN = (import.meta.env.VITE_MOCK_LOGIN === 'true') || !!import.meta.env.DEV;

    async function submit(e) {
        e.preventDefault();
        setError('');
        setLoading(true);
        // Fast dev mock path — immediately set a fake token and navigate.
        if (MOCK_LOGIN) {
            try {
                // small delay to simulate network
                await new Promise(r => setTimeout(r, 200));
                const fakeToken = 'dev-fake-token';
                localStorage.setItem('token', fakeToken);
                const dest = localStorage.getItem('postAuthRedirect') || '/occucalc';
                localStorage.removeItem('postAuthRedirect');
                navigate(dest);
                return;
            } catch (err) {
                setError(String(err));
                setLoading(false);
                return;
            }
        }
        try {
            const base = import.meta.env.VITE_API_URL || '';
            const res = await fetch(base + '/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            let json = null;
            let txt = null;
            try {
                txt = await res.text();
                json = txt ? JSON.parse(txt) : null;
            } catch (e) { json = null; }
            if (!res.ok) {
                const serverMsg = (json && json.error) || (txt && txt.slice(0, 200)) || `status ${res.status}`;
                throw new Error(`Login failed: ${serverMsg}`);
            }

            if (json?.token) {
                localStorage.setItem('token', json.token);
                const dest = localStorage.getItem('postAuthRedirect') || '/occucalc';
                localStorage.removeItem('postAuthRedirect');
                navigate(dest);
                return;
            }

            setError('Login did not return a token');
        } catch (err) {
            setError(err.message || String(err));
        } finally {
            setLoading(false);
        }
    }

    return (
        <main style={{ fontFamily: 'system-ui, sans-serif', padding: 40, maxWidth: 520, margin: '40px auto', background: '#fff', borderRadius: 12, boxShadow: '0 6px 28px rgba(0,0,0,0.08)' }}>
            <h2 style={{ fontSize: '1.6rem', marginBottom: 16 }}>Log in</h2>
            <form onSubmit={submit}>
                <label style={{ display: 'block', marginBottom: 8 }}>Email
                    <input value={email} onChange={e => setEmail(e.target.value)} type="email" required style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #e5e7eb', marginTop: 8 }} />
                </label>

                <label style={{ display: 'block', marginBottom: 16 }}>Password
                    <input value={password} onChange={e => setPassword(e.target.value)} type="password" required style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #e5e7eb', marginTop: 8 }} />
                </label>

                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    <button type="submit" disabled={loading} style={{ background: '#2563eb', color: '#fff', borderRadius: 8, padding: '10px 20px', fontWeight: 600, border: 'none', cursor: 'pointer' }}>{loading ? 'Logging in…' : 'Log in'}</button>
                </div>

                {error && <div style={{ marginTop: 12, color: 'crimson' }}>{error}</div>}
            </form>
        </main>
    );
}
