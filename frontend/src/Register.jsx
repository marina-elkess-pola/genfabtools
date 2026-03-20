import React, { useState } from "react";
import { useNavigate, Link } from 'react-router-dom';

export default function Register() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const navigate = useNavigate();

    async function submit(e) {
        e.preventDefault();
        setError('');
        setSuccess('');
        setLoading(true);

        try {
            const base = import.meta.env.VITE_API_URL || '';
            const res = await fetch(base + '/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, displayName })
            });

            let json = null;
            try {
                const txt = await res.text();
                json = txt ? JSON.parse(txt) : null;
            } catch (e) { json = null; }
            if (!res.ok) throw new Error((json && json.error) || 'Registration failed');

            setSuccess(json?.message || 'Registered');

            // Attempt to login automatically so the user continues the flow
            try {
                const loginRes = await fetch(base + '/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });
                let loginJson = null;
                try {
                    const txt = await loginRes.text();
                    loginJson = txt ? JSON.parse(txt) : null;
                } catch (e) { loginJson = null; }
                if (loginRes.ok && loginJson?.token) {
                    localStorage.setItem('token', loginJson.token);
                    // Redirect to saved post-auth destination if present
                    const dest = localStorage.getItem('postAuthRedirect') || '/occucalc';
                    localStorage.removeItem('postAuthRedirect');
                    navigate(dest);
                    return;
                }

                // If login failed because confirmation required, show message and stay
                if (loginJson?.error) {
                    setError(loginJson.error);
                    setLoading(false);
                    return;
                }
            } catch (loginErr) {
                console.error('auto-login error', loginErr);
            }

            setLoading(false);
        } catch (err) {
            setError(err.message || String(err));
            setLoading(false);
        }
    }

    return (
        <main style={{ fontFamily: "system-ui, sans-serif", padding: 40, maxWidth: 520, margin: "40px auto", background: "#fff", borderRadius: 12, boxShadow: "0 6px 28px rgba(0,0,0,0.08)" }}>
            <h2 style={{ fontSize: "1.6rem", marginBottom: 16 }}>Create an account</h2>
            <form onSubmit={submit}>
                <label style={{ display: 'block', marginBottom: 8 }}>Full name
                    <input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="Optional" style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid #e5e7eb", marginTop: 8 }} />
                </label>

                <label style={{ display: 'block', marginBottom: 8 }}>Email
                    <input value={email} onChange={e => setEmail(e.target.value)} type="email" required style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid #e5e7eb", marginTop: 8 }} />
                </label>

                <label style={{ display: 'block', marginBottom: 16 }}>Password
                    <input value={password} onChange={e => setPassword(e.target.value)} type="password" required style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid #e5e7eb", marginTop: 8 }} />
                </label>

                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    <button type="submit" disabled={loading} style={{ background: "#2563eb", color: "#fff", borderRadius: 8, padding: "10px 20px", fontWeight: 600, border: "none", cursor: "pointer" }}>{loading ? 'Creating…' : 'Create account'}</button>
                    <Link to="/login" style={{ background: '#eee', borderRadius: 8, padding: '10px 16px', border: '1px solid #ddd', textDecoration: 'none', color: 'inherit' }}>Have an account? Log in</Link>
                </div>

                {error && <div style={{ marginTop: 12, color: 'crimson' }}>{error}</div>}
                {success && <div style={{ marginTop: 12, color: 'green' }}>{success}</div>}
            </form>
        </main>
    );
}