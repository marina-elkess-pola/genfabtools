import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';

function CopyButton({ text }) {
    const [copied, setCopied] = useState(false);
    return (
        <button
            onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            className="shrink-0 text-xs font-medium text-slate-500 hover:text-slate-900 border border-slate-200 rounded-md px-2.5 py-1 hover:bg-slate-50 transition"
        >
            {copied ? 'Copied!' : 'Copy'}
        </button>
    );
}

export default function Account() {
    const [loading, setLoading] = useState(true);
    const [user, setUser] = useState(null);
    const [purchases, setPurchases] = useState([]);
    const [error, setError] = useState(null);
    const [downloading, setDownloading] = useState(false);
    const [downloadError, setDownloadError] = useState(null);
    const navigate = useNavigate();

    useEffect(() => {
        let mounted = true;
        async function load() {
            setLoading(true);
            try {
                const token = localStorage.getItem('token');
                if (!token) {
                    setError('Not authenticated');
                    setLoading(false);
                    return;
                }
                const apiBase = import.meta.env.VITE_API_URL || '';
                const headers = { Authorization: `Bearer ${token}` };

                const [profileRes, purchasesRes] = await Promise.all([
                    fetch(apiBase + '/me', { headers, credentials: 'include' }),
                    fetch(apiBase + '/api/purchases', { headers, credentials: 'include' }),
                ]);

                if (!profileRes.ok) {
                    setError('Failed to load profile');
                    setLoading(false);
                    return;
                }
                const profile = await profileRes.json();
                const purchaseData = purchasesRes.ok ? await purchasesRes.json() : [];

                if (mounted) {
                    setUser(profile);
                    setPurchases(purchaseData);
                }
            } catch (e) {
                if (mounted) setError('Network error');
            } finally {
                if (mounted) setLoading(false);
            }
        }
        load();
        return () => { mounted = false; };
    }, []);

    function signOut() {
        try { localStorage.removeItem('token'); } catch (e) { /* ignore */ }
        window.dispatchEvent(new Event('auth-change'));
        navigate('/');
    }

    if (loading) return (
        <div className="min-h-[60vh] flex items-center justify-center">
            <div className="animate-pulse text-slate-400">Loading account…</div>
        </div>
    );
    if (error) return (
        <div className="min-h-[60vh] flex items-center justify-center">
            <div className="text-center">
                <p className="text-sm text-rose-600 mb-4">{error}</p>
                <Link to="/login" className="inline-flex items-center gap-2 rounded-lg bg-slate-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-slate-800 transition">Sign in</Link>
            </div>
        </div>
    );

    const initial = user?.displayName ? user.displayName.charAt(0).toUpperCase() : (user?.email || '?').charAt(0).toUpperCase();
    const completedPurchases = purchases.filter(p => p.status === 'complete');
    const hasTools = completedPurchases.length > 0;

    return (
        <div className="max-w-4xl mx-auto px-6 py-12">
            {/* ── Profile Header ── */}
            <div className="flex items-center gap-5">
                <div className="h-16 w-16 rounded-full bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center text-xl font-bold text-white shadow-lg">
                    {initial}
                </div>
                <div className="min-w-0 flex-1">
                    <h1 className="text-2xl font-bold text-slate-900 truncate">{user?.displayName || 'User'}</h1>
                    <p className="text-sm text-slate-500 truncate">{user?.email}</p>
                    {user?.createdAt && (
                        <p className="text-xs text-slate-400 mt-0.5">Member since {new Date(user.createdAt).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</p>
                    )}
                </div>
                <button
                    onClick={signOut}
                    className="shrink-0 text-sm text-slate-500 hover:text-slate-900 border border-slate-200 rounded-lg px-4 py-2 hover:bg-slate-50 transition"
                >
                    Sign out
                </button>
            </div>

            {/* ── My Tools ── */}
            <div className="mt-10">
                <h2 className="text-lg font-semibold text-slate-900">My tools</h2>

                {hasTools ? (
                    <div className="mt-4 space-y-4">
                        {completedPurchases.map(p => (
                            <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex items-center gap-4">
                                        <div className="h-12 w-12 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                                            <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5" />
                                            </svg>
                                        </div>
                                        <div>
                                            <h3 className="font-semibold text-slate-900">RSI — Residential Scheme Intelligence</h3>
                                            <p className="text-xs text-slate-400 mt-0.5">Revit plugin · Purchased {new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</p>
                                        </div>
                                    </div>
                                    <span className="inline-flex items-center gap-1.5 rounded-full bg-green-50 border border-green-200 px-3 py-1 text-xs font-medium text-green-700 shrink-0">
                                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                                        Active
                                    </span>
                                </div>

                                {/* License Key */}
                                {p.licenseKey && (
                                    <div className="mt-5 rounded-lg bg-slate-50 border border-slate-200 p-4">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">License Key</span>
                                            <CopyButton text={p.licenseKey} />
                                        </div>
                                        <code className="block text-xs text-slate-700 font-mono break-all leading-relaxed select-all bg-white rounded-md border border-slate-100 p-3 overflow-hidden overflow-wrap-anywhere" style={{ wordBreak: 'break-all', overflowWrap: 'anywhere' }}>
                                            {p.licenseKey}
                                        </code>
                                        {/* Activation status */}
                                        {p.machineId ? (
                                            <div className="mt-3 flex items-center gap-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
                                                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
                                                <span>Activated on machine <code className="font-mono text-[11px]">{p.machineId.slice(0, 12)}…</code> · {new Date(p.activatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                                            </div>
                                        ) : (
                                            <p className="mt-2 text-[11px] text-slate-400">Paste this key into the RSI Revit plugin to activate. The key will be locked to that PC.</p>
                                        )}
                                    </div>
                                )}

                                {/* Download + Links */}
                                <div className="mt-4 flex flex-wrap items-center gap-3">
                                    {downloadError && (
                                        <div className="w-full rounded-lg bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700 mb-2">
                                            {downloadError}
                                        </div>
                                    )}
                                    <button
                                        onClick={async () => {
                                            setDownloadError(null);
                                            setDownloading(true);
                                            try {
                                                const token = localStorage.getItem('token');
                                                const apiBase = import.meta.env.VITE_API_URL || '';
                                                const res = await fetch(apiBase + '/api/download/rsi', {
                                                    headers: { Authorization: `Bearer ${token}` },
                                                    credentials: 'include',
                                                });
                                                if (!res.ok) {
                                                    const body = await res.json().catch(() => ({}));
                                                    setDownloadError(body.error || 'Download failed. Please try again.');
                                                    return;
                                                }
                                                const { url } = await res.json();
                                                window.location.href = url;
                                            } catch {
                                                setDownloadError('Network error. Please check your connection and try again.');
                                            } finally {
                                                setDownloading(false);
                                            }
                                        }}
                                        disabled={downloading}
                                        className="inline-flex items-center gap-2 rounded-lg bg-blue-600 text-white px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition shadow-sm disabled:opacity-60 disabled:cursor-wait"
                                    >
                                        {downloading ? (
                                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                            </svg>
                                        ) : (
                                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" /></svg>
                                        )}
                                        {downloading ? 'Preparing download…' : 'Download RSI for Revit 2024'}
                                    </button>
                                    <Link to="/tools/rsi" className="text-sm text-slate-500 hover:text-slate-700 transition">
                                        View product page
                                    </Link>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="mt-4 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 p-8 text-center">
                        <svg className="w-10 h-10 text-slate-300 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
                        </svg>
                        <p className="mt-3 text-sm text-slate-500">No tools purchased yet.</p>
                        <Link to="/tools" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-slate-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-slate-800 transition shadow-sm">
                            Browse tools
                        </Link>
                    </div>
                )}
            </div>

            {/* ── Quick Links ── */}
            <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/tools" className="text-sm text-slate-600 hover:text-slate-900 border border-slate-200 rounded-lg px-4 py-2 hover:bg-slate-50 transition">
                    All tools
                </Link>
                <Link to="/support" className="text-sm text-slate-600 hover:text-slate-900 border border-slate-200 rounded-lg px-4 py-2 hover:bg-slate-50 transition">
                    Contact support
                </Link>
            </div>
        </div>
    );
}
