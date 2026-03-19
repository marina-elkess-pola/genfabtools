import React, { useState, useMemo } from 'react';
import { Link, NavLink } from 'react-router-dom';
import feature1 from './assets/feature-1.svg';
import feature2 from './assets/feature-2.svg';
import feature3 from './assets/feature-3.svg';
import occuCalcLogo from './assets/occucalc-logo-black.png';
import parkLogo from './assets/park-logo-black.png';
import ToolCard from './components/ToolCard';
import ToolDetails from './components/ToolDetails';
import toolsLogo from './assets/tools-logo-black.png';

/*
  Complete Tools page with a simple header (logo + nav),
  hero, sidebar + grid and slide-over details.
*/

const SAMPLE_TOOLS = [
    {
        id: 'rsi',
        title: 'Residential Scheme Intelligence',
        description:
            'Analyze residential layouts, diagnose inefficiencies, compare design options, and evaluate financial outcomes directly inside Autodesk Revit.',
        category: 'Revit Plugin',
        tags: ['Featured', 'Revit Plugin'],
        link: '/tools/rsi',
        icon: '/images/rsi/efficiency-dashboard.png',
    },
];

function Tools() {
    const [selected, setSelected] = useState(null);
    const [query, setQuery] = useState('');
    const [activeTags, setActiveTags] = useState([]);
    const [priceFilter, setPriceFilter] = useState('all'); // all | free | paid

    const openTool = (tool) => setSelected(tool);
    const closeTool = () => setSelected(null);

    // Smooth-scroll to tools grid and account for fixed header height
    function scrollToTools(e) {
        if (e && e.preventDefault) e.preventDefault();
        const el = document.getElementById('tools');
        if (!el) return;
        // Header height: 4rem (64px) + small gap
        const headerOffset = 72;
        const y = el.getBoundingClientRect().top + window.pageYOffset - headerOffset;
        window.scrollTo({ top: y, behavior: 'smooth' });
    }

    const allTags = useMemo(() => {
        const s = new Set();
        SAMPLE_TOOLS.forEach(t => (t.tags || []).forEach(tag => s.add(tag)));
        return Array.from(s);
    }, []);

    const filtered = useMemo(() => {
        return SAMPLE_TOOLS.filter((t) => {
            const text = (t.title + ' ' + t.subtitle + ' ' + t.description).toLowerCase();
            if (query && !text.includes(query.toLowerCase())) return false;
            if (activeTags.length > 0) {
                const has = (t.tags || []).some(tag => activeTags.includes(tag));
                if (!has) return false;
            }
            if (priceFilter === 'free' && t.price && t.price.toLowerCase() !== 'free') return false;
            if (priceFilter === 'paid' && (!t.price || t.price.toLowerCase() === 'free')) return false;
            return true;
        });
    }, [query, activeTags, priceFilter]);

    return (
        <>
            {/* Content (header provided by Layout) */}
            <div>
                {/* Hero */}
                {/* Variant B: Glass + Blur (elegant) */}
                <header className="relative w-full py-16">
                    <div className="max-w-6xl mx-auto px-6">
                        <div className="rounded-2xl bg-white/50 dark:bg-white/20 backdrop-blur-lg border border-white/30 dark:border-white/20 text-slate-900 p-8 flex flex-col md:flex-row items-center gap-6 shadow-md ring-1 ring-white/5">
                            <div className="flex-shrink-0">
                                <img src={toolsLogo} alt="Tools" className="w-14 h-14 rounded-md" width="56" height="56" loading="lazy" decoding="async" />
                            </div>

                            <div className="flex-1 text-center md:text-left">
                                <div className="flex items-center justify-center md:justify-start gap-3">
                                    <h1 className="text-4xl md:text-5xl font-extrabold engraved-text">Tools</h1>
                                </div>
                                <p className="mt-2 text-lg text-slate-700 max-w-2xl engraved-subtext">
                                    Practical utilities for GenFab — calculators, converters, and design helpers to speed your workflow.
                                </p>
                            </div>

                            <div className="mt-4 md:mt-0">
                                <a href="#tools" onClick={scrollToTools} className="inline-block px-4 py-2 rounded-md border border-white/30 bg-white/10 text-slate-900 text-sm font-semibold hover:bg-white/20 shadow-sm">Explore tools</a>
                            </div>
                        </div>
                    </div>
                </header>

                {/* Content */}
                <main className="max-w-6xl mx-auto px-6 mt-8 pb-12">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-stretch">
                        {/* Sidebar / Filters */}
                        <aside className="md:col-span-1">
                            <div className="sticky top-28">
                                <div className="bg-slate-50 rounded-xl p-4 border border-slate-100 shadow-sm">
                                    <h4 className="font-bold text-slate-900">Filters</h4>
                                    <p className="text-sm text-slate-600 mt-2">Filter tools by category or status.</p>
                                    <div className="mt-4">
                                        <label className="block text-sm text-slate-700">Search</label>
                                        <input value={query} onChange={(e) => setQuery(e.target.value)} className="mt-2 w-full rounded-md border border-slate-200 px-3 py-2 bg-white text-slate-800" placeholder="Search tools" />
                                    </div>

                                    <div className="mt-4">
                                        <label className="block text-sm text-slate-700">Price</label>
                                        <div className="mt-2 flex gap-2">
                                            <button onClick={() => setPriceFilter('all')} className={`px-3 py-1 rounded-md text-sm ${priceFilter === 'all' ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 border border-slate-200'}`}>All</button>
                                            <button onClick={() => setPriceFilter('free')} className={`px-3 py-1 rounded-md text-sm ${priceFilter === 'free' ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 border border-slate-200'}`}>Free</button>
                                            <button onClick={() => setPriceFilter('paid')} className={`px-3 py-1 rounded-md text-sm ${priceFilter === 'paid' ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 border border-slate-200'}`}>Paid</button>
                                        </div>
                                    </div>

                                    <div className="mt-4">
                                        <label className="block text-sm text-slate-700">Tags</label>
                                        <div className="mt-2 flex flex-wrap gap-2">
                                            {allTags.map(tag => {
                                                const active = activeTags.includes(tag);
                                                return (
                                                    <button key={tag} onClick={() => setActiveTags(prev => active ? prev.filter(t => t !== tag) : [...prev, tag])} className={`text-xs px-2 py-1 rounded-full ${active ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 border border-slate-200'}`}>{tag}</button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </aside>

                        {/* Grid */}
                        <section id="tools" className="md:col-span-3">
                            {/* Featured tool – RSI */}
                            <div className="mb-8 rounded-2xl bg-white p-6 shadow-sm border border-slate-100">
                                <div className="flex flex-col md:flex-row items-center gap-8">
                                    <div className="flex-1">
                                        <span className="text-xs font-bold uppercase tracking-widest text-blue-500 mb-2 inline-block">Featured Tool</span>
                                        <h2 className="text-2xl font-extrabold text-slate-900">Residential Scheme Intelligence</h2>
                                        <p className="mt-3 text-slate-600 leading-relaxed">
                                            Analyze residential layouts, diagnose inefficiencies, compare design options,
                                            and evaluate financial outcomes directly inside Autodesk Revit.
                                        </p>
                                        <div className="mt-5 flex flex-wrap gap-3">
                                            <Link to="/tools/rsi" className="inline-flex items-center rounded-md bg-slate-900 text-white px-5 py-2.5 text-sm font-semibold hover:opacity-95">Open Tool</Link>
                                            <a href="/docs/rsi" className="inline-flex items-center rounded-md border border-slate-200 px-5 py-2.5 text-sm text-slate-800 font-semibold hover:bg-slate-50">Documentation</a>
                                        </div>
                                    </div>
                                    <div className="flex-shrink-0 w-full md:w-64">
                                        <img src="/images/rsi/efficiency-dashboard.png" alt="RSI efficiency dashboard" className="w-full rounded-lg shadow-md" loading="lazy" decoding="async" />
                                    </div>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">
                                {filtered.length === 0 ? (
                                    <div className="col-span-full text-center text-slate-600 py-12">No tools match your search or filters.</div>
                                ) : (
                                    filtered.map((t) => (
                                        <ToolCard key={t.id} tool={t} onOpen={openTool} />
                                    ))
                                )}
                            </div>
                        </section>
                    </div>
                </main>

                {/* Slide-over details */}
                {selected && <ToolDetails tool={selected} onClose={closeTool} />}
            </div>
        </>
    );
}

export default Tools;