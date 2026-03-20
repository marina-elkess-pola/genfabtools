import React, { useState, useMemo } from 'react';
import toolsLogo from './assets/tools-logo-black.png';
import ToolCard from './components/ToolCard';

const SAMPLE_TOOLS = [
    {
        id: 'rsi',
        title: 'Residential Scheme Intelligence',
        description:
            'Analyze residential layouts, diagnose inefficiencies, compare design options, and evaluate financial outcomes directly inside Autodesk Revit.',
        category: 'Revit Plugin',
        tags: ['Featured', 'Revit Plugin'],
        link: 'https://genfabtools.com/download/RSI_Setup.exe',
        docs: 'https://genfabtools.com/docs/rsi/index.html',
        icon: '/images/rsi/efficiency-dashboard.png',
        price: 49,
    },
];

function Tools() {
    const [query, setQuery] = useState('');
    const [activeTags, setActiveTags] = useState([]);
    const [priceFilter, setPriceFilter] = useState('all');

    function scrollToTools(e) {
        if (e && e.preventDefault) e.preventDefault();
        const el = document.getElementById('tools');
        if (!el) return;
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
            const text = (t.title + ' ' + t.description).toLowerCase();
            if (query && !text.includes(query.toLowerCase())) return false;

            if (activeTags.length > 0) {
                const has = (t.tags || []).some(tag => activeTags.includes(tag));
                if (!has) return false;
            }

            const isFree = t.price === 0;
            const isPaid = typeof t.price === 'number' && t.price > 0;

            if (priceFilter === 'free' && !isFree) return false;
            if (priceFilter === 'paid' && !isPaid) return false;

            return true;
        });
    }, [query, activeTags, priceFilter]);

    return (
        <div>
            {/* HERO */}
            <header className="relative w-full py-16">
                <div className="max-w-6xl mx-auto px-6">
                    <div className="rounded-2xl bg-white/50 backdrop-blur-lg border p-8 flex flex-col md:flex-row items-center gap-6 shadow-md">
                        <img src={toolsLogo} alt="Tools" className="w-14 h-14" />

                        <div className="flex-1 text-center md:text-left">
                            <h1 className="text-4xl font-extrabold">Tools</h1>
                            <p className="mt-2 text-lg text-slate-700">
                                Practical utilities to speed your workflow.
                            </p>
                        </div>

                        <a
                            href="#tools"
                            onClick={scrollToTools}
                            className="px-4 py-2 rounded-md border text-sm font-semibold"
                        >
                            Explore tools
                        </a>
                    </div>
                </div>
            </header>

            {/* CONTENT */}
            <main className="max-w-6xl mx-auto px-6 mt-8 pb-12">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">

                    {/* FILTERS */}
                    <aside className="md:col-span-1">
                        <div className="sticky top-28 bg-slate-50 rounded-xl p-4 border shadow-sm">
                            <h4 className="font-bold">Filters</h4>

                            <input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                className="mt-3 w-full border px-3 py-2"
                                placeholder="Search tools"
                            />

                            <div className="mt-4 flex gap-2">
                                <button onClick={() => setPriceFilter('all')}>All</button>
                                <button onClick={() => setPriceFilter('free')}>Free</button>
                                <button onClick={() => setPriceFilter('paid')}>Paid</button>
                            </div>
                        </div>
                    </aside>

                    {/* TOOLS */}
                    <section id="tools" className="md:col-span-3">

                        {/* FEATURED */}
                        <div className="mb-8 bg-white p-6 rounded-xl shadow border">
                            <h2 className="text-2xl font-bold">Residential Scheme Intelligence</h2>

                            <p className="mt-3 text-slate-600">
                                Analyze residential layouts directly inside Revit.
                            </p>

                            <div className="mt-5 flex gap-3">

                                {/* OPEN TOOL */}
                                <a
                                    href="https://genfabtools.com/download/RSI_Setup.exe"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="bg-black text-white px-4 py-2 rounded"
                                >
                                    Open Tool
                                </a>

                                {/* DOCS */}
                                <a
                                    href="https://genfabtools.com/docs/rsi/index.html"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="border px-4 py-2 rounded"
                                >
                                    Documentation
                                </a>

                                {/* EMAIL */}
                                <a
                                    href="mailto:support@genfabtools.com"
                                    className="border px-4 py-2 rounded"
                                >
                                    Get Early Access
                                </a>

                            </div>
                        </div>

                        {/* GRID */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filtered
                                .filter(t => t.id !== 'rsi')
                                .map((t) => (
                                    <ToolCard key={t.id} tool={t} />
                                ))}
                        </div>

                    </section>
                </div>
            </main>
        </div>
    );
}

export default Tools;