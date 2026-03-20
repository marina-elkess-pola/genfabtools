import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

// /purchase/verify page: polls backend /purchase/verify until status === 'complete'
// Expects ?purchaseRef=...
export default function PurchaseVerify() {
    const [qs] = useSearchParams();
    const purchaseRef = qs.get('purchaseRef');
    const [status, setStatus] = useState('checking');
    const [message, setMessage] = useState('Checking purchase status...');
    const navigate = useNavigate();

    useEffect(() => {
        if (!purchaseRef) {
            setStatus('error');
            setMessage('Missing purchaseRef in URL');
            return;
        }

        let cancelled = false;
        const token = localStorage.getItem('token');

        async function checkOnce() {
            try {
                const res = await fetch((import.meta.env.VITE_API_URL || '') + `/purchase/verify?purchaseRef=${encodeURIComponent(purchaseRef)}`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {}
                });

                if (res.status === 401) {
                    // Save return location (so register/login will bring user back here)
                    try { localStorage.setItem('postAuthRedirect', window.location.pathname + window.location.search); } catch (e) { /* ignore */ }
                    // Redirect user to register/login so they can complete verification
                    navigate('/register');
                    return;
                }

                if (res.status === 409) {
                    // Inertia full-location response — follow the location if provided
                    const loc = res.headers.get('X-Inertia-Location');
                    if (loc) window.location.href = loc;
                    return;
                }

                let json = null;
                try {
                    const txt = await res.text();
                    json = txt ? JSON.parse(txt) : null;
                } catch (e) {
                    json = null;
                }
                if (!res.ok) throw new Error((json && json.error) || 'verification failed');

                if (json.status === 'complete') {
                    setStatus('complete');
                    setMessage('Purchase complete — thank you!');
                    // Mark locally so OccuCalc gating can unlock immediately
                    localStorage.setItem('occuCalc.paid', '1');
                    // short delay then navigate to occucalc
                    setTimeout(() => navigate('/occucalc'), 1200);
                } else {
                    setStatus('pending');
                    setMessage('Payment pending. Checking again soon...');
                }
            } catch (err) {
                console.error('verify error', err);
                setStatus('error');
                setMessage('Failed to verify purchase: ' + (err.message || String(err)));
            }
        }

        checkOnce();
        const iv = setInterval(() => { if (!cancelled) checkOnce(); }, 4000);
        return () => { cancelled = true; clearInterval(iv); };
    }, [purchaseRef, navigate]);

    return (
        <main className="p-8 max-w-xl mx-auto">
            <h1 className="text-2xl font-bold">Purchase status</h1>
            <p className="mt-4 text-sm text-slate-700">{message}</p>
            {status === 'pending' && <p className="mt-2 text-sm text-slate-500">This page will poll until the payment is processed. If you remain pending, try refreshing or contact support.</p>}
            {status === 'unauthenticated' && <p className="mt-2 text-sm text-amber-700">You need to register/login first. We saved your return location.</p>}
        </main>
    );
}
