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
        id: 'sitegen',
        title: 'SiteGen',
        subtitle: 'Real estate feasibility engine',
        description:
            'Automated site planning that generates optimized building massing and parking layouts given your site constraints.',
        longDescription:
            'SiteGen analyzes your site boundary, zoning constraints, and parking requirements to automatically generate optimal configurations. Test multiple angles, building positions, and parking layouts to maximize unit count and efficiency.',
        icon: feature3,
        tags: ['Featured', 'Generator', 'New'],
        tip: 'Draw your site boundary and set zoning rules to see instant feasibility results.',
        price: '$49/month',
        link: '/sitegen',
    },
    {
        id: 'occucalc',
        title: 'OccuCalc',
        subtitle: 'Occupancy & load calculator',
        description:
            'Efficient occupant load calculator for architects and engineers. Calculate safe occupancy quickly using common code rules.',
        longDescription:
            'OccuCalc helps you determine occupant loads by area type, apply multipliers, and export simple reports. Designed for quick estimation and verification during early-stage design.',
        icon: occuCalcLogo,
        tags: ['Featured', 'Estimator'],
        tip: 'Start by entering approximate room areas to get a quick occupant estimate.',
        price: '$19/month',
        link: '/occucalc',
    },
    {
        id: 'parking',
        title: 'Parking Generator',
        subtitle: 'CAD-integrated smart parking layouts',
        description: 'Generate optimized parking layouts from CAD files. Import Revit constraints and get AI-powered circulation routes.',
        longDescription:
            'Parking Generator analyzes your building constraints (walls, columns, MEP) imported from Revit and automatically generates optimal parking layouts with smart street circulation. Supports surface and structured parking.',
        icon: parkLogo,
        tags: ['Featured', 'Generator'],
        tip: 'Import your Revit floor plan to automatically detect obstacles and generate layouts.',
        price: '$39/month',
        link: '/parking',
    },
    {
        id: 'parkcore',
        title: 'ParkCore',
        subtitle: 'Parking design assistant',
        description: 'Advanced parking design and analysis tool. Estimate stalls, circulation, and layout quickly.',
        icon: parkLogo,
        tags: ['Beta', 'Analysis'],
        tip: 'Try the auto-estimate mode for a quick first-pass layout.',
        price: '$29/month',
        link: '/parkcore',
    },
    {
        id: 'parking-engine',
        title: 'Parking Engine',
        subtitle: 'Early-stage feasibility tool',
        description: 'Scenario-based parking feasibility analysis. Surface and structured layouts with CAD constraint integration.',
        longDescription:
            'Parking Engine is a decision lens for early-stage feasibility. Define sites, import CAD constraints, and instantly evaluate surface or structured parking layouts. Compare scenarios, track constraint impact, and get rule-based capacity estimates.',
        icon: parkLogo,
        tags: ['New', 'Feasibility'],
        tip: 'Create multiple scenarios to compare different configurations.',
        price: '$39/month',
        link: '/parking-engine',
    },
    {
        id: 'estimator',
        title: 'Quick Estimator',
        subtitle: 'Cost & material estimator',
        description: 'Fast cost and material estimates for preliminary budgets.',
        icon: feature1,
        tags: ['Free'],
        tip: 'Use the presets to get fast estimates for common project types.',
        price: 'Free',
        link: '#',
    },
    {
        id: 'selector',
        title: 'Material Selector',
        subtitle: 'Pick materials quickly',
        description: 'Suggests common materials and finishes based on use-case and cost.',
        icon: feature2,
        tags: ['Utility'],
        tip: 'Filter by performance or cost to narrow suggestions.',
        price: 'Free',
        link: '#',
    },
    {
        id: 'exporter',
        title: 'Export Helper',
        subtitle: 'Export formats & presets',
        description: 'Quickly export data into CSV/PDF and presets for sharing with clients.',
        icon: feature1,
        tags: ['Export'],
        tip: 'Use the preset templates to match client deliverable expectations.',
        price: 'Free',
        link: '#',
    },
    {
        id: 'tolerance',
        title: 'Tolerance Checker',
        subtitle: 'Dimensional checks',
        description: 'Check common tolerance stacks and quick pass/fail guidance.',
        icon: feature2,
        tags: ['Utility'],
        tip: 'Enter stack dimensions to see quick pass/fail guidance.',
        price: '$9/month',
        link: '#',
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
                            {/* Featured tool banner (light, uses existing theme) */}
                            <div className="mb-6 rounded-2xl bg-white dark:bg-slate-900 p-4 shadow-sm border border-slate-100 dark:border-slate-800">
                                <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center gap-4">
                                    <div className="flex-shrink-0">
                                        <img src={occuCalcLogo} alt="OccuCalc" className="w-16 h-16 rounded-md shadow" width="64" height="64" loading="lazy" decoding="async" />
                                    </div>
                                    <div className="flex-1">
                                        <h2 className="text-2xl font-extrabold text-slate-900 dark:text-slate-50">Featured: OccuCalc</h2>
                                        <p className="mt-1 text-slate-600 dark:text-slate-300">Quick occupant load calculations for early-stage design — fast, code-aware, and exportable.</p>
                                    </div>
                                    <div className="mt-3 sm:mt-0">
                                        <a href="/occucalc" className="inline-flex items-center gap-3 rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold hover:opacity-95">Open OccuCalc</a>
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