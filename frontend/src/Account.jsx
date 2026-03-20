import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import ProfileCard from './components/account/ProfileCard';
import PurchasesList from './components/account/PurchasesList';
import AccountActions from './components/account/AccountActions';

export default function Account() {
    const [loading, setLoading] = useState(true);
    const [user, setUser] = useState(null);
    const [error, setError] = useState(null);
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
                const res = await fetch(apiBase + '/me', { headers: { Authorization: `Bearer ${token}` } });
                if (!res.ok) {
                    setError('Failed to load profile');
                    setLoading(false);
                    return;
                }
                const json = await res.json();
                if (mounted) setUser(json || null);
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
        // navigate and let app state update without forcing a reload
        navigate('/');
    }

    if (loading) return <div className="p-8">Loading profile…</div>;
    if (error) return (
        <div className="p-8 max-w-xl mx-auto">
            <h2 className="text-xl font-semibold">Account</h2>
            <p className="mt-4 text-sm text-rose-600">{error}</p>
            <div className="mt-6">
                <Link to="/login" className="inline-flex items-center rounded-md border px-3 py-2">Sign in</Link>
            </div>
        </div>
    );

    return (
        <div className="p-8 max-w-5xl mx-auto">
            <h2 className="text-2xl font-semibold">Account</h2>

            <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1">
                    <ProfileCard user={user} />
                    <div className="mt-4">
                        <AccountActions user={user} onSignOut={signOut} />
                    </div>
                </div>

                <div className="lg:col-span-2">
                    <section className="bg-white/80 dark:bg-slate-900/95 backdrop-blur-sm rounded-lg p-5 border border-slate-200 dark:border-slate-800">
                        <h3 className="text-lg font-medium">Recent purchases</h3>
                        <div className="mt-3">
                            <PurchasesList purchases={user.purchases} />
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
