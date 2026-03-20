import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import OccuCalcTools from './OccuCalcTools.jsx';
import PurchaseButton from './components/PurchaseButton';

// Gate OccuCalc behind a simple client-side check.
// The canonical source of truth is the backend /me endpoint, but the frontend currently
// may not have a full auth flow; use /me when token present, otherwise fall back to
// localStorage flag `occuCalc.paid`.
export default function OccuCalc() {
    const [loading, setLoading] = useState(true);
    const [paid, setPaid] = useState(false);
    const [user, setUser] = useState(null);
    useEffect(() => {
        async function check() {
            setLoading(true);
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    const res = await fetch((import.meta.env.VITE_API_URL || '') + '/me', { headers: { Authorization: `Bearer ${token}` } });
                    if (res.ok) {
                        let json = null;
                        try {
                            const txt = await res.text();
                            json = txt ? JSON.parse(txt) : null;
                        } catch (e) { json = null; }
                        // If backend reports paid, honor it. Otherwise, fall back to a
                        // local flag that PurchaseVerify sets after returning from
                        // hosted checkout so the UI unlocks immediately.
                        const serverPaid = !!(json && json.paid);
                        const localPaid = localStorage.getItem('occuCalc.paid') === '1';
                        setPaid(serverPaid || localPaid);
                        if (json) setUser({ email: json.email, displayName: json.displayName });
                        setLoading(false);
                        return;
                    }
                } catch (e) {
                    // ignore and fallback to local flag
                }
            }

            // fallback to local flag (set after PurchaseVerify completes)
            const localPaid = localStorage.getItem('occuCalc.paid') === '1';
            setPaid(localPaid);
            setLoading(false);
        }
        check();
    }, []);

    // Re-check the server for purchase status. This will fetch /me and, if a
    // purchaseRef is present in the URL (returned from checkout), call
    // /purchase/verify to get the latest status and update local state.
    async function refreshStatus() {
        setLoading(true);
        const token = localStorage.getItem('token');
        if (!token) { setLoading(false); return; }
        try {
            const apiBase = import.meta.env.VITE_API_URL || '';
            // refresh profile
            const res = await fetch(apiBase + '/me', { headers: { Authorization: `Bearer ${token}` } });
            if (res.ok) {
                const json = await res.json();
                if (json) {
                    setUser({ email: json.email, displayName: json.displayName });
                    if (json.paid) {
                        localStorage.setItem('occuCalc.paid', '1');
                        setPaid(true);
                        setLoading(false);
                        return;
                    }
                }
            }

            // if we have a purchaseRef in the URL (return from hosted checkout), verify it
            const params = new URLSearchParams(window.location.search);
            const purchaseRef = params.get('purchaseRef');
            if (purchaseRef) {
                const pv = await fetch(apiBase + '/purchase/verify?purchaseRef=' + encodeURIComponent(purchaseRef), { headers: { Authorization: `Bearer ${token}` } });
                if (pv.ok) {
                    const pj = await pv.json();
                    if (pj && pj.status === 'complete') {
                        localStorage.setItem('occuCalc.paid', '1');
                        setPaid(true);
                        setLoading(false);
                        return;
                    }
                }
            }

            const localPaid = localStorage.getItem('occuCalc.paid') === '1';
            setPaid(localPaid);
        } catch (e) {
            // ignore errors and fall back to local flag
            const localPaid = localStorage.getItem('occuCalc.paid') === '1';
            setPaid(localPaid);
        }
        setLoading(false);
    }

    // If still loading, render tool (avoid a blank screen) but show minimal overlay
    if (loading) return <div className="p-6">Loading…</div>;

    if (!paid) {
        const token = localStorage.getItem('token');
        // If user is not logged in, first direct them to register so they have
        // an account to receive purchased tools. Preserve the return location.
        if (!token) {
            return (
                <div className="p-8 max-w-xl mx-auto">
                    <h2 className="text-2xl font-bold">Create a free account to try OccuCalc</h2>
                    <p className="mt-4">OccuCalc requires a free GenFabTools account. Create an account to store your tools and purchases.</p>
                    <div className="mt-6">
                        <Link
                            to="/register"
                            onClick={() => localStorage.setItem('postAuthRedirect', '/occucalc')}
                            className="inline-flex items-center gap-2 rounded-md bg-blue-600 text-white px-4 py-2 text-sm font-semibold"
                        >Create free account</Link>
                    </div>
                </div>
            );
        }

        return (
            <div className="relative">
                <OccuCalcTools />

                {/* Fixed overlay so it appears above headers/toolbars and remains centered */}
                <div style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, pointerEvents: 'auto' }}>
                    {/* Backdrop */}
                    <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.35)' }} />

                    {/* Card */}
                    <div style={{ position: 'relative', background: 'rgba(255,255,255,0.98)', padding: 24, borderRadius: 8, boxShadow: '0 12px 48px rgba(2,6,23,0.3)', maxWidth: 760, width: 'min(92%,760px)', zIndex: 10000 }}>
                        <h2 style={{ margin: 0, fontSize: 20 }}>Unlock OccuCalc</h2>
                        {user && <p style={{ marginTop: 6, marginBottom: 6, color: '#374151' }}>Logged in as <strong>{user.displayName || user.email}</strong></p>}
                        <p style={{ marginTop: 8, marginBottom: 12 }}>OccuCalc is available for registered users. Purchase access to unlock the tool.</p>
                        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                            <PurchaseButton />
                            {import.meta.env.DEV && (
                                <button
                                    onClick={async () => {
                                        const token = localStorage.getItem('token');
                                        if (!token) return alert('Not logged in');
                                        try {
                                            const apiBase = import.meta.env.VITE_API_URL || '';
                                            // Try to read purchaseRef from URL (return from hosted checkout)
                                            const params = new URLSearchParams(window.location.search);
                                            let purchaseRef = params.get('purchaseRef');

                                            // If no purchaseRef present, create a pending purchase so we can mark it paid
                                            if (!purchaseRef) {
                                                const createRes = await fetch(apiBase + '/purchase/create', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                                                    body: JSON.stringify({})
                                                });
                                                if (!createRes.ok) throw new Error('failed to create purchase');
                                                const created = await createRes.json();
                                                purchaseRef = created.purchaseRef;
                                            }

                                            // Call the dev-only endpoint to mark the purchase complete
                                            const devRes = await fetch(apiBase + '/dev/purchase/mark-paid', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ purchaseRef })
                                            });
                                            if (!devRes.ok) throw new Error('dev mark-paid failed');

                                            // Refresh local status after marking paid
                                            await refreshStatus();
                                            alert('Marked purchase paid (dev)');
                                        } catch (e) {
                                            console.error('dev mark paid failed', e);
                                            alert('Dev mark-paid failed: ' + (e && e.message));
                                        }
                                    }}
                                    className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium bg-yellow-100"
                                >
                                    Dev: Mark purchase paid
                                </button>
                            )}
                            <button
                                onClick={refreshStatus}
                                className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium"
                            >
                                Refresh purchase status
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return <OccuCalcTools />;
}
