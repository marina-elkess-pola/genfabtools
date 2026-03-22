import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import toolsLogo from './assets/tools-logo-black.png';
import ToolCard from './components/ToolCard';
import { toolsData } from './data/toolsData';


function Tools() {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [priceFilter, setPriceFilter] = useState('all');

    function scrollToTools(e) {
        if (e && e.preventDefault) e.preventDefault();
        const el = document.getElementById('tools');
        if (!el) return;
        const y = el.getBoundingClientRect().top + window.pageYOffset - 72;
        window.scrollTo({ top: y, behavior: 'smooth' });
    }

    const filtered = useMemo(() => {
        return toolsData.filter((t) => {
            const text = (t.title + ' ' + t.description).toLowerCase();

            if (query && !text.includes(query.toLowerCase())) return false;

            const isFree =
                !t.pricing?.monthly && !t.pricing?.yearly;

            const isPaid =
                (t.pricing?.monthly > 0) ||
                (t.pricing?.yearly > 0);

            if (priceFilter === 'free' && !isFree) return false;
            if (priceFilter === 'paid' && !isPaid) return false;

            return true;
        });
    }, [query, priceFilter]);

    return (
        <div>
            {/* HERO */}
            <header className="py-16">
                <div className="max-w-6xl mx-auto px-6">
                    <div className="rounded-2xl bg-white border p-8 flex items-center justify-between shadow-sm">
                        <div className="flex items-center gap-4">
                            <img src={toolsLogo} alt="Tools" className="w-12 h-12" />
                            <div>
                                <h1 className="text-3xl font-bold">Tools</h1>
                                <p className="text-slate-600">
                                    Practical utilities to speed your workflow.
                                </p>
                            </div>
                        </div>

                        <button
                            onClick={scrollToTools}
                            className="px-4 py-2 border rounded-md font-semibold"
                        >
                            Explore tools
                        </button>
                    </div>
                </div>
            </header>

            {/* CONTENT */}
            <main className="max-w-6xl mx-auto px-6 pb-12">
                <div className="grid md:grid-cols-4 gap-6">

                    {/* FILTERS */}
                    <aside>
                        <div className="bg-slate-50 p-4 rounded-xl border">
                            <h4 className="font-bold mb-3">Filters</h4>

                            <input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search tools"
                                className="w-full border px-3 py-2 rounded-md"
                            />

                            <div className="mt-4 flex gap-2">
                                {['all', 'free', 'paid'].map((type) => (
                                    <button
                                        key={type}
                                        onClick={() => setPriceFilter(type)}
                                        className={`px-3 py-1 rounded-md text-sm ${priceFilter === type
                                            ? 'bg-black text-white'
                                            : 'bg-white border text-black'
                                            }`}
                                    >
                                        {type}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </aside>

                    {/* TOOLS */}
                    <section id="tools" className="md:col-span-3">

                        {/* FEATURED TOOL */}
                        <div className="mb-8 bg-white p-6 rounded-xl border shadow-sm flex flex-col md:flex-row gap-6 items-center">

                            {/* TEXT */}
                            <div className="flex-1">
                                <span className="text-xs text-blue-500 font-bold uppercase">
                                    Featured Tool
                                </span>

                                <h2 className="text-2xl font-bold mt-2">
                                    Residential Scheme Intelligence
                                </h2>

                                <p className="mt-3 text-slate-600 leading-relaxed">
                                    Analyze residential layouts, detect inefficiencies, compare design
                                    options, and instantly evaluate financial feasibility — all directly
                                    inside Revit.
                                </p>

                                <ul className="mt-4 text-sm text-slate-600 space-y-1">
                                    <li>• Unit mix & efficiency analysis</li>
                                    <li>• Built-up vs sellable ratio</li>
                                    <li>• Financial feasibility insights</li>
                                    <li>• Instant performance scoring</li>
                                </ul>

                                {/* BUTTONS */}
                                <div className="mt-5 flex gap-3 flex-wrap">

                                    <button
                                        onClick={() => { navigate('/tools/rsi'); window.scrollTo(0, 0); }}
                                        className="bg-black text-white px-5 py-2 rounded-md font-semibold"
                                    >
                                        Open Tool
                                    </button>

                                    <a
                                        href="https://genfabtools.com/docs/rsi/index.html"
                                        target="_blank"
                                        className="border text-black px-5 py-2 rounded-md font-semibold"
                                    >
                                        Documentation
                                    </a>

                                </div>
                            </div>

                            {/* IMAGE (VERY IMPORTANT) */}
                            <img
                                src="/images/rsi/efficiency-dashboard-heatmap.png"
                                alt="RSI dashboard"
                                className="w-full md:w-64 rounded-lg shadow"
                            />
                        </div>

                        {/* GRID */}
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filtered.map((t) => (
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