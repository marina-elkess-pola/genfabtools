import React, { useState } from 'react';
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

    const monthlyPrice = rsi.pricing.monthly;
    const yearlyPrice = rsi.pricing.yearly;
    const savings = monthlyPrice * 12 - yearlyPrice;
    const price = billing === 'monthly' ? monthlyPrice : yearlyPrice;

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
                        Analyze residential layouts, diagnose inefficiencies, and compare design
                        schemes directly inside Revit.
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

                    {/* CTAs */}
                    <div className="mt-10 flex flex-wrap justify-center gap-4">
                        <a
                            href={rsi.links.download}
                            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-lg bg-blue-600 text-white font-semibold text-sm hover:bg-blue-500 transition shadow-lg shadow-blue-600/25"
                        >
                            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                            </svg>
                            Download RSI for Revit 2024
                        </a>

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

            {/* ── SCREENSHOTS ── */}
            <section className="bg-slate-50 py-24">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="text-center mb-14">
                        <h2 className="text-3xl font-extrabold text-slate-900">See it in action</h2>
                        <p className="mt-3 text-slate-500">Real output from RSI running inside Revit.</p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-8">
                        <div className="rounded-xl overflow-hidden shadow-lg border border-slate-200">
                            <img src="/images/rsi/efficiency-dashboard.png" alt="Efficiency dashboard" className="w-full" />
                            <div className="p-4 bg-white">
                                <p className="text-sm font-semibold text-slate-800">Efficiency Dashboard</p>
                                <p className="text-xs text-slate-500 mt-1">83% net-to-gross efficiency with space composition breakdown.</p>
                            </div>
                        </div>
                        <div className="rounded-xl overflow-hidden shadow-lg border border-slate-200">
                            <img src="/images/rsi/decision-summary.png" alt="Decision summary comparison" className="w-full" />
                            <div className="p-4 bg-white">
                                <p className="text-sm font-semibold text-slate-800">Decision Summary</p>
                                <p className="text-xs text-slate-500 mt-1">Compare schemes and see revenue impact instantly.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── PRICING ── */}
            <section className="max-w-5xl mx-auto px-6 py-24">
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
                    <a
                        href={rsi.links.download}
                        className="mt-8 block w-full text-center px-6 py-3.5 rounded-lg bg-slate-900 text-white font-semibold text-sm hover:bg-slate-800 transition shadow"
                    >
                        Download RSI
                    </a>
                </div>
            </section>

        </div>
    );
}