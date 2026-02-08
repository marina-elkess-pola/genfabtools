import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

// Lightweight PurchaseButton that calls backend /purchase/create and redirects to checkoutUrl.
// Behavior:
// - If no auth token found in localStorage, sends user to /register (preserves returnTo)
// - If token present, POST to backend with Authorization header and redirects to checkoutUrl
export default function PurchaseButton({ productId, priceId, children }) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const navigate = useNavigate();

    async function startPurchase(e) {
        e && e.preventDefault();
        setError(null);
        const token = localStorage.getItem('token');
        if (!token) {
            // preserve intent: after register/login return to OccuCalc
            localStorage.setItem('postAuthRedirect', window.location.pathname + window.location.search);
            navigate('/register');
            return;
        }

        setLoading(true);
        try {
            const body = { productId, priceId };
            const res = await fetch((import.meta.env.VITE_API_URL || '') + '/purchase/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(body)
            });

            if (res.status === 401) {
                setError('Please register / login to purchase.');
                localStorage.setItem('postAuthRedirect', window.location.pathname + window.location.search);
                navigate('/register');
                return;
            }

            let json = null;
            try {
                const txt = await res.text();
                json = txt ? JSON.parse(txt) : null;
            } catch (e) {
                json = null;
            }
            if (!res.ok) throw new Error((json && json.error) || 'Failed to create purchase');

            if (json.checkoutUrl) {
                // redirect user to hosted checkout
                window.location.href = json.checkoutUrl;
            } else {
                setError('No checkout URL returned by server.');
            }
        } catch (err) {
            console.error('purchase error', err);
            setError(err.message || String(err));
        } finally {
            setLoading(false);
        }
    }

    return (
        <div>
            <button
                onClick={startPurchase}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-md bg-emerald-600 text-white px-4 py-2 text-sm font-semibold hover:opacity-95"
            >
                {loading ? 'Starting…' : (children || 'Buy OccuCalc')}
            </button>
            {error && <div style={{ marginTop: 8 }} className="text-sm text-red-600">{error}</div>}
        </div>
    );
}
