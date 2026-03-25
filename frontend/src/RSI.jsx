import React, { useState, useEffect, useCallback } from 'react';
import { toolsData } from './data/toolsData';




const rsi = toolsData.find(t => t.id === 'rsi');

const features = [
    {
        title: 'Layout Analysis',
        desc: 'Detect inefficiencies in unit distribution, circulation paths, and planning logic at a glance.',
        icon: (
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 8.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
            </svg>
        ),
    },
    {
        title: 'Performance Metrics',
        desc: 'Evaluate KPIs like net-to-gross efficiency, unit mix balance, and space utilization in real time.',
        icon: (
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
            </svg>
        ),
    },
    {
        title: 'Financial Insight',
        desc: 'Instantly estimate revenue potential, compare pricing scenarios, and assess scheme feasibility.',
        icon: (
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        ),
    },
    {
        title: 'Heatmap Visualization',
        desc: 'Overlay colour-coded efficiency heatmaps directly on your Revit floor plans for instant diagnostics.',
        icon: (
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
            </svg>
        ),
    },
    {
        title: 'Benchmark Comparison',
        desc: 'Compare your scheme against industry benchmarks and competing designs side by side.',
        icon: (
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
            </svg>
        ),
    },
    {
        title: 'Scheme Comparison',
        desc: 'Run multiple design options and compare results to find the highest-performing scheme.',
        icon: (
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15a2.25 2.25 0 012.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
            </svg>
        ),
    },
];

export default function RSI() {
    const [billing, setBilling] = useState('monthly');
    const [hasAccess, setHasAccess] = useState(null);
    const [downloading, setDownloading] = useState(false);
    const [downloadError, setDownloadError] = useState(null);

    const verify = useCallback(async () => {
        const token = localStorage.getItem("token");
        if (!token) {
            setHasAccess(false);
            return;
        }
        try {
            const apiBase = import.meta.env.VITE_API_URL || '';
            const res = await fetch(apiBase + "/api/access", {
                headers: { Authorization: `Bearer ${token}` },
                credentials: 'include',
            });
            if (!res.ok) {
                setHasAccess(false);
                return;
            }
            const data = await res.json();
            setHasAccess(data.access === true);
        } catch {
            setHasAccess(false);
        }
    }, []);

    useEffect(() => {
        verify();

        // Re-verify when page is restored from bfcache (back/forward)
        const onPageShow = (e) => { if (e.persisted) verify(); };
        window.addEventListener('pageshow', onPageShow);

        // Re-verify when tab regains focus (covers alt-tab, undo scenarios)
        const onFocus = () => verify();
        window.addEventListener('focus', onFocus);

        return () => {
            window.removeEventListener('pageshow', onPageShow);
            window.removeEventListener('focus', onFocus);
        };
    }, [verify]);

    const monthlyPrice = rsi.pricing.monthly;
    const yearlyPrice = rsi.pricing.yearly;
    const savings = monthlyPrice * 12 - yearlyPrice;
    const price = billing === 'monthly' ? monthlyPrice : yearlyPrice;

    async function handleDownload(e) {
        e.preventDefault();
        setDownloadError(null);

        const token = localStorage.getItem('token');
        if (!token) {
            localStorage.setItem('postAuthRedirect', '/tools/rsi');
            window.location.href = '/register';
            return;
        }

        if (hasAccess === true) {
            // Fetch a short-lived signed download URL from the backend
            setDownloading(true);
            try {
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
            return;
        }

        // No access — create a purchase and redirect to checkout
        try {
            const apiBase = import.meta.env.VITE_API_URL || '';
            const res = await fetch(apiBase + '/purchase/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                credentials: 'include',
                body: JSON.stringify({ productId: 'rsi', priceId: billing }),
            });
            if (!res.ok) {
                setDownloadError('Could not start purchase. Please try again.');
                return;
            }
            const data = await res.json();
            if (data.checkoutUrl) {
                window.location.href = data.checkoutUrl;
            } else {
                setDownloadError('No checkout URL returned. Please contact support.');
            }
        } catch {
            setDownloadError('Network error. Please check your connection and try again.');
        }
    }

    return (
        <div className="bg-white">

            {/* ── HERO ── */}
            <section className="relative overflow-hidden bg-gradient-to-b from-slate-950 via-slate-900 to-slate-800">

                {/* Subtle radial glow */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[500px] rounded-full bg-blue-500/10 blur-3xl" />
                </div>

                <div className="relative max-w-5xl mx-auto px-6 pt-28 pb-20 text-center">

                    {/* Badge */}
                    <span className="inline-block mb-6 px-4 py-1.5 text-xs font-medium tracking-wide uppercase rounded-full bg-white/10 text-blue-300 border border-white/10">
                        Revit 2024 Plugin
                    </span>

                    {/* Title */}
                    <h1 className="text-5xl md:text-6xl font-extrabold text-white leading-tight tracking-tight">
                        Residential Scheme<br />Intelligence
                    </h1>

                    {/* Subtitle */}
                    <p className="mt-6 max-w-2xl mx-auto text-lg md:text-xl text-slate-300 leading-relaxed">
                        Stop spending hours in spreadsheets. Get live efficiency scoring,
                        financial feasibility, and scheme comparison — directly inside Revit.
                    </p>

                    {/* Feature pills */}
                    <div className="mt-8 flex flex-wrap justify-center gap-3 text-sm text-slate-400">
                        {['Residential Efficiency', 'Heatmap Diagnostics', 'Scheme Comparison', 'Exportable Reports'].map(
                            (t) => (
                                <span key={t} className="px-3 py-1 rounded-full border border-white/10 bg-white/5">
                                    {t}
                                </span>
                            )
                        )}
                    </div>

                    {/* Trust signal */}
                    <p className="mt-6 text-sm text-slate-500 tracking-wide">
                        Designed &amp; tested inside real Revit projects
                    </p>

                    {/* CTAs */}
                    {downloadError && (
                        <div className="mt-6 max-w-md mx-auto rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                            {downloadError}
                        </div>
                    )}
                    <div className="mt-10 flex flex-wrap justify-center gap-4">
                        <button
                            onClick={handleDownload}
                            disabled={downloading}
                            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-lg bg-blue-600 text-white font-semibold text-sm hover:bg-blue-500 transition shadow-lg shadow-blue-600/25 disabled:opacity-60 disabled:cursor-wait"
                        >
                            {downloading ? (
                                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                            ) : (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                                </svg>
                            )}
                            {downloading ? 'Preparing download…' : 'Download RSI for Revit 2024'}
                        </button>

                        <a
                            href={rsi.links.docs}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-lg bg-white/10 text-white font-semibold text-sm hover:bg-white/20 transition border border-white/10"
                        >
                            View Documentation
                        </a>
                    </div>
                </div>

                {/* Fade-out bottom edge */}
                <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-white to-transparent" />
            </section>

            {/* ── PRODUCT SCREENSHOT ── */}
            <section className="relative -mt-12 z-10 max-w-6xl mx-auto px-6">
                <div className="rounded-2xl overflow-hidden shadow-2xl border border-slate-200 bg-slate-900">
                    <img
                        src="/images/rsi/project00.png"
                        alt="RSI running inside Revit — floor plan with live efficiency analysis"
                        className="w-full"
                    />
                </div>
            </section>

            {/* ── FEATURES ── */}
            <section className="max-w-5xl mx-auto px-6 py-24">
                <div className="text-center mb-14">
                    <h2 className="text-3xl font-extrabold text-slate-900">
                        Everything you need to optimize residential schemes
                    </h2>
                    <p className="mt-3 text-slate-500 max-w-xl mx-auto">
                        Built for architects and developers who need fast, data-driven design feedback inside Revit.
                    </p>
                </div>

                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8">
                    {features.map((f, i) => (
                        <div
                            key={i}
                            className="group p-6 rounded-xl border border-slate-200 hover:border-slate-300 hover:shadow-md transition"
                        >
                            <div className="w-10 h-10 flex items-center justify-center rounded-lg bg-slate-100 text-slate-700 group-hover:bg-blue-50 group-hover:text-blue-600 transition">
                                {f.icon}
                            </div>
                            <h3 className="mt-4 font-bold text-slate-900">{f.title}</h3>
                            <p className="mt-2 text-sm text-slate-500 leading-relaxed">{f.desc}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* ── BEFORE vs AFTER ── */}
            <section className="bg-slate-950 py-24">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="text-center mb-14">
                        <h2 className="text-3xl font-extrabold text-white">
                            The old way vs. RSI
                        </h2>
                        <p className="mt-3 text-slate-400 max-w-xl mx-auto">
                            What it actually looks like to evaluate a residential scheme without RSI.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-8">
                        {/* WITHOUT */}
                        <div className="rounded-2xl border border-red-500/20 bg-red-950/20 p-8">
                            <div className="flex items-center gap-2 mb-6">
                                <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                                <h3 className="text-lg font-bold text-red-300">Without RSI</h3>
                            </div>
                            <ul className="space-y-4 text-sm text-slate-300">
                                {[
                                    'Export area schedules from Revit to Excel',
                                    'Manually tag net, core, and circulation areas',
                                    'Calculate efficiency ratios by hand',
                                    'Google industry benchmarks to compare against',
                                    'Build a separate financial spreadsheet',
                                    'Repeat everything for each design option',
                                    'Manually create comparison reports',
                                ].map((item, i) => (
                                    <li key={i} className="flex items-start gap-3">
                                        <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center text-red-400 text-xs">✕</span>
                                        {item}
                                    </li>
                                ))}
                            </ul>
                            <div className="mt-8 pt-6 border-t border-red-500/20">
                                <p className="text-2xl font-bold text-red-300">2–4 hours</p>
                                <p className="text-sm text-slate-400 mt-1">per scheme iteration, every time the design changes</p>
                            </div>
                        </div>

                        {/* WITH RSI */}
                        <div className="rounded-2xl border border-green-500/20 bg-green-950/20 p-8">
                            <div className="flex items-center gap-2 mb-6">
                                <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                </svg>
                                <h3 className="text-lg font-bold text-green-300">With RSI</h3>
                            </div>
                            <ul className="space-y-4 text-sm text-slate-300">
                                {[
                                    'Click "Analyze" — results appear in seconds',
                                    'Areas auto-classified from your Revit model',
                                    'Efficiency, benchmarks, and heatmaps — live',
                                    'Financial impact calculated instantly',
                                    'Compare schemes with one click',
                                    'Results update every time you modify the design',
                                    'Export-ready reports built in',
                                ].map((item, i) => (
                                    <li key={i} className="flex items-start gap-3">
                                        <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full bg-green-500/20 flex items-center justify-center text-green-400 text-xs">✓</span>
                                        {item}
                                    </li>
                                ))}
                            </ul>
                            <div className="mt-8 pt-6 border-t border-green-500/20">
                                <p className="text-2xl font-bold text-green-300">Under 10 seconds</p>
                                <p className="text-sm text-slate-400 mt-1">and it recalculates automatically as you design</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── ROI STATS ── */}
            <section className="py-24">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="text-center mb-14">
                        <h2 className="text-3xl font-extrabold text-slate-900">
                            $49/month pays for itself on day one
                        </h2>
                        <p className="mt-3 text-slate-500 max-w-2xl mx-auto">
                            A single hour of an architect's time costs more than a month of RSI.
                            Here's the math.
                        </p>
                    </div>

                    <div className="grid sm:grid-cols-3 gap-8 text-center">
                        {[
                            {
                                stat: '10×',
                                label: 'Faster analysis',
                                desc: 'What takes 2–4 hours manually runs in seconds inside Revit.',
                            },
                            {
                                stat: '2%+',
                                label: 'Efficiency gains found',
                                desc: 'Even a small improvement on a 10,000 ft² scheme can shift revenue by millions.',
                            },
                            {
                                stat: '$49',
                                label: 'vs. $150+/hr architect time',
                                desc: 'Less than 20 minutes of billable time to save hours every week.',
                            },
                        ].map((s, i) => (
                            <div key={i} className="p-8 rounded-2xl border border-slate-200 bg-white">
                                <p className="text-4xl font-extrabold text-blue-600">{s.stat}</p>
                                <p className="mt-2 font-bold text-slate-900">{s.label}</p>
                                <p className="mt-2 text-sm text-slate-500 leading-relaxed">{s.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── SCREENSHOTS ── */}
            <section className="bg-slate-50 py-24">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="text-center mb-14">
                        <h2 className="text-3xl font-extrabold text-slate-900">See it in action</h2>
                        <p className="mt-3 text-slate-500">Real output from RSI running inside Revit.</p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-6">
                        {[
                            {
                                src: '/images/rsi/efficiency-dashboard.png',
                                alt: 'Efficiency dashboard',
                                label: 'Efficiency Dashboard',
                                desc: '83% net-to-gross efficiency with live space composition breakdown.',
                            },
                            {
                                src: '/images/rsi/financial-impact-RSI.png',
                                alt: 'Financial impact analysis',
                                label: 'Financial Impact',
                                desc: 'Revenue estimation and sell-price sensitivity per scheme.',
                            },
                            {
                                src: '/images/rsi/decision-summary.png',
                                alt: 'Decision summary',
                                label: 'Decision Summary',
                                desc: 'Side-by-side scheme comparison with revenue delta.',
                            },
                        ].map((card, i) => (
                            <div
                                key={i}
                                className="group rounded-2xl border border-slate-200 bg-white overflow-hidden hover:shadow-lg transition"
                            >
                                <div className="aspect-[4/3] overflow-hidden bg-slate-100 flex items-center justify-center p-4">
                                    <img
                                        src={card.src}
                                        alt={card.alt}
                                        className="max-h-full max-w-full object-contain group-hover:scale-[1.03] transition duration-300"
                                    />
                                </div>
                                <div className="p-5">
                                    <p className="font-semibold text-slate-900">{card.label}</p>
                                    <p className="mt-1 text-sm text-slate-500 leading-relaxed">{card.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── PRICING ── */}
            <section className="py-24">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl font-extrabold text-slate-900">Simple, transparent pricing</h2>
                        <p className="mt-3 text-slate-500">One tool. One plan. No hidden fees.</p>
                    </div>

                    <div className="max-w-md mx-auto rounded-2xl border border-slate-200 p-8 shadow-sm">

                        {/* Toggle */}
                        <div className="flex items-center justify-center gap-3 mb-8">
                            <button
                                onClick={() => setBilling('monthly')}
                                className={`px-5 py-2 rounded-lg text-sm font-semibold transition ${billing === 'monthly'
                                    ? 'bg-slate-900 text-white shadow'
                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                    }`}
                            >
                                Monthly
                            </button>
                            <button
                                onClick={() => setBilling('yearly')}
                                className={`px-5 py-2 rounded-lg text-sm font-semibold transition relative ${billing === 'yearly'
                                    ? 'bg-slate-900 text-white shadow'
                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                    }`}
                            >
                                Yearly
                                <span className="absolute -top-2.5 -right-4 bg-green-500 text-white text-[10px] px-2 py-0.5 rounded-full font-bold">
                                    Save ${savings}
                                </span>
                            </button>
                        </div>

                        {/* Price */}
                        <div className="text-center">
                            <span className="text-5xl font-extrabold text-slate-900">${price}</span>
                            <span className="text-slate-500 ml-2">/ {billing === 'monthly' ? 'month' : 'year'}</span>
                        </div>

                        {billing === 'yearly' && (
                            <p className="text-center text-sm text-green-600 mt-2 font-medium">
                                That's ${(yearlyPrice / 12).toFixed(0)}/month — billed annually
                            </p>
                        )}

                        {/* Features checklist */}
                        <ul className="mt-8 space-y-3">
                            {rsi.features.map((f, i) => (
                                <li key={i} className="flex items-start gap-3 text-sm text-slate-700">
                                    <svg className="w-5 h-5 text-green-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                    </svg>
                                    {f}
                                </li>
                            ))}
                        </ul>

                        {/* CTA */}
                        <button
                            onClick={handleDownload}
                            disabled={downloading}
                            className="mt-8 block w-full text-center px-6 py-3.5 rounded-lg bg-slate-900 text-white font-semibold text-sm hover:bg-slate-800 transition shadow disabled:opacity-60 disabled:cursor-wait"
                        >
                            {downloading ? 'Preparing download…' : 'Download RSI'}
                        </button>
                    </div>
                </div>
            </section>

            {/* ── FAQ ── */}
            <section className="bg-slate-50 py-24">
                <div className="max-w-3xl mx-auto px-6">
                    <div className="text-center mb-14">
                        <h2 className="text-3xl font-extrabold text-slate-900">Frequently asked questions</h2>
                    </div>

                    <div className="space-y-6">
                        {[
                            {
                                q: 'Can\'t I just do this in Excel for free?',
                                a: 'You can — and most architects do. But it means exporting area schedules, manually tagging spaces, building formulas, finding benchmarks online, and rebuilding everything when the design changes. RSI does all of that in seconds, live inside Revit, with zero context-switching.',
                            },
                            {
                                q: 'Is $49/month worth it for a single tool?',
                                a: 'An architect billing at $100–200/hr spends 2–4 hours per scheme doing this manually. RSI pays for itself in a single use. On a typical project with 3–5 iterations, it saves 10–20 hours per month.',
                            },
                            {
                                q: 'What if my project only has one scheme?',
                                a: 'Even with one scheme, RSI gives you instant benchmarking, heatmap diagnostics, and financial feasibility that would take hours to assemble manually. And the moment you test a second option, the comparison tools make the value obvious.',
                            },
                            {
                                q: 'Do I need an internet connection?',
                                a: 'RSI runs entirely inside Revit on your local machine. No cloud dependency, no data leaves your computer.',
                            },
                            {
                                q: 'Can I cancel anytime?',
                                a: 'Yes. Monthly plans cancel anytime with no penalties. Annual plans are billed upfront and valid for 12 months.',
                            },
                        ].map((faq, i) => (
                            <details key={i} className="group rounded-xl border border-slate-200 bg-white overflow-hidden">
                                <summary className="flex items-center justify-between cursor-pointer p-6 font-semibold text-slate-900 hover:bg-slate-50 transition">
                                    {faq.q}
                                    <svg className="w-5 h-5 text-slate-400 shrink-0 ml-4 group-open:rotate-180 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                                    </svg>
                                </summary>
                                <div className="px-6 pb-6 text-sm text-slate-600 leading-relaxed">
                                    {faq.a}
                                </div>
                            </details>
                        ))}
                    </div>
                </div>
            </section>

        </div>
    );
}