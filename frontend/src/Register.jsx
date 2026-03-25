import React, { useState, useMemo } from "react";
import { useNavigate, Link } from 'react-router-dom';

function getPasswordStrength(pw) {
    if (!pw) return { score: 0, label: '' };
    let score = 0;
    if (pw.length >= 8) score++;
    if (/[a-zA-Z]/.test(pw) && /[0-9]/.test(pw)) score++;
    if (pw.length >= 12) score++;
    if (/[^a-zA-Z0-9]/.test(pw)) score++;
    const labels = ['Weak', 'Fair', 'Good', 'Strong'];
    return { score: Math.min(score, 4), label: score > 0 ? labels[Math.min(score, 4) - 1] : '' };
}

const strengthColors = ['bg-red-500', 'bg-orange-400', 'bg-yellow-400', 'bg-green-500'];
const strengthTextColors = ['text-red-600', 'text-orange-500', 'text-yellow-600', 'text-green-600'];

export default function Register() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [displayName, setDisplayName] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [touched, setTouched] = useState(false);
    const navigate = useNavigate();

    const strength = useMemo(() => getPasswordStrength(password), [password]);

    const validationErrors = useMemo(() => {
        const errs = [];
        if (password && password.length < 8) errs.push('At least 8 characters');
        if (password && !/[a-zA-Z]/.test(password)) errs.push('At least one letter');
        if (password && !/[0-9]/.test(password)) errs.push('At least one number');
        return errs;
    }, [password]);

    const canSubmit = password.length >= 8 && /[a-zA-Z]/.test(password) && /[0-9]/.test(password);

    async function submit(e) {
        e.preventDefault();
        setTouched(true);
        if (!canSubmit) return;
        setError('');
        setSuccess('');
        setLoading(true);

        try {
            const base = import.meta.env.VITE_API_URL || '';
            const res = await fetch(base + '/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ email, password, displayName })
            });

            let json = null;
            try {
                const txt = await res.text();
                json = txt ? JSON.parse(txt) : null;
            } catch (e) { json = null; }
            if (!res.ok) throw new Error((json && json.error) || 'Registration failed');

            setSuccess(json?.message || 'Registered');

            try {
                const loginRes = await fetch(base + '/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ email, password })
                });
                let loginJson = null;
                try {
                    const txt = await loginRes.text();
                    loginJson = txt ? JSON.parse(txt) : null;
                } catch (e) { loginJson = null; }
                if (loginRes.ok && loginJson?.token) {
                    localStorage.setItem('token', loginJson.token);
                    window.dispatchEvent(new Event('auth-change'));
                    const dest = localStorage.getItem('postAuthRedirect') || '/account';
                    localStorage.removeItem('postAuthRedirect');
                    navigate(dest);
                    return;
                }

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
        <div className="min-h-[60vh] flex items-center justify-center px-4 py-12">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
                <h2 className="text-2xl font-bold text-slate-900">Create an account</h2>
                <p className="mt-1 text-sm text-slate-500">Get started with GenFabTools</p>

                <form onSubmit={submit} className="mt-6 space-y-5">
                    {/* Display Name */}
                    <div>
                        <label htmlFor="reg-name" className="block text-sm font-medium text-slate-700">Full name</label>
                        <input
                            id="reg-name"
                            value={displayName}
                            onChange={e => setDisplayName(e.target.value)}
                            autoComplete="name"
                            className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:outline-none transition"
                            placeholder="Optional"
                        />
                    </div>

                    {/* Email */}
                    <div>
                        <label htmlFor="reg-email" className="block text-sm font-medium text-slate-700">Email</label>
                        <input
                            id="reg-email"
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
                        <label htmlFor="reg-password" className="block text-sm font-medium text-slate-700">Password</label>
                        <div className="relative mt-1.5">
                            <input
                                id="reg-password"
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                                onBlur={() => setTouched(true)}
                                type={showPassword ? 'text' : 'password'}
                                required
                                autoComplete="new-password"
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

                        {/* Strength bar */}
                        {password && (
                            <div className="mt-2">
                                <div className="flex gap-1">
                                    {[0, 1, 2, 3].map(i => (
                                        <div
                                            key={i}
                                            className={`h-1 flex-1 rounded-full transition-colors ${i < strength.score ? strengthColors[strength.score - 1] : 'bg-slate-200'}`}
                                        />
                                    ))}
                                </div>
                                {strength.label && (
                                    <p className={`mt-1 text-xs font-medium ${strengthTextColors[strength.score - 1]}`}>{strength.label}</p>
                                )}
                            </div>
                        )}

                        {/* Validation errors */}
                        {touched && validationErrors.length > 0 && (
                            <ul className="mt-2 space-y-0.5">
                                {validationErrors.map(err => (
                                    <li key={err} className="flex items-center gap-1.5 text-xs text-red-600">
                                        <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                                        {err}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    {/* Error / Success */}
                    {error && (
                        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700">
                            {error}
                        </div>
                    )}
                    {success && (
                        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2.5 text-sm text-green-700">
                            {success}
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
                        {loading ? 'Creating account…' : 'Create account'}
                    </button>
                </form>

                {/* Terms & Privacy */}
                <p className="mt-4 text-center text-xs text-slate-400">
                    By creating an account you agree to our{' '}
                    <Link to="/terms" className="underline hover:text-slate-600 transition">Terms</Link>{' '}and{' '}
                    <Link to="/privacy" className="underline hover:text-slate-600 transition">Privacy Policy</Link>.
                </p>

                {/* Login link */}
                <p className="mt-4 text-center text-sm text-slate-500">
                    Already have an account?{' '}
                    <Link to="/login" className="font-semibold text-slate-900 hover:text-slate-700 transition">Log in</Link>
                </p>
            </div>
        </div>
    );
}