import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    async function submit(e) {
        e.preventDefault();
        setError('');
        setLoading(true);

        if (import.meta.env.DEV && import.meta.env.VITE_MOCK_LOGIN === 'true') {
            try {
                await new Promise(r => setTimeout(r, 200));
                localStorage.setItem('token', 'dev-fake-token');
                window.dispatchEvent(new Event('auth-change'));
                const dest = localStorage.getItem('postAuthRedirect') || '/account';
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
                credentials: 'include',
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
                window.dispatchEvent(new Event('auth-change'));
                const dest = localStorage.getItem('postAuthRedirect') || '/account';
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
        <div className="min-h-[60vh] flex items-center justify-center px-4 py-12">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
                <h2 className="text-2xl font-bold text-slate-900">Log in</h2>
                <p className="mt-1 text-sm text-slate-500">Sign in to your GenFabTools account</p>

                <form onSubmit={submit} className="mt-6 space-y-5">
                    {/* Email */}
                    <div>
                        <label htmlFor="login-email" className="block text-sm font-medium text-slate-700">Email</label>
                        <input
                            id="login-email"
                            value={email}
                            onChange={e => setEmail(e.target.value)}
                            type="email"
                            required
                            autoComplete="email"
                            className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition"
                            placeholder="you@example.com"
                        />
                    </div>

                    {/* Password */}
                    <div>
                        <div className="flex items-center justify-between">
                            <label htmlFor="login-password" className="block text-sm font-medium text-slate-700">Password</label>
                            <Link to="/forgot-password" className="text-xs font-medium text-blue-600 hover:text-blue-700 transition">Forgot password?</Link>
                        </div>
                        <div className="relative mt-1.5">
                            <input
                                id="login-password"
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                                type={showPassword ? 'text' : 'password'}
                                required
                                autoComplete="current-password"
                                className="block w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 pr-10 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition"
                                placeholder="••••••••"
                            />
                            <span
                                role="button"
                                onMouseDown={e => e.preventDefault()}
                                onClick={() => setShowPassword(v => !v)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 cursor-pointer select-none text-slate-400 hover:text-slate-600"
                                aria-label={showPassword ? 'Hide password' : 'Show password'}
                            >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                                    <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                    {showPassword && <path d="M3 3l18 18" />}
                                </svg>
                            </span>
                        </div>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700">
                            {error}
                        </div>
                    )}

                    {/* Submit */}
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-slate-800 transition shadow-sm disabled:opacity-60 disabled:cursor-wait"
                    >
                        {loading && (
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                        )}
                        {loading ? 'Logging in…' : 'Log in'}
                    </button>
                </form>

                {/* Register link */}
                <p className="mt-6 text-center text-sm text-slate-500">
                    Don't have an account?{' '}
                    <Link to="/register" className="font-semibold text-slate-900 hover:text-slate-700 transition">Create one</Link>
                </p>
            </div>
        </div>
    );
}
