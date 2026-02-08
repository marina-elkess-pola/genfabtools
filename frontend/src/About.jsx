import React, { useEffect } from 'react';

export default function About() {
    useEffect(() => {
        document.title = 'About — GenFabTools';
    }, []);

    return (
        <main className="max-w-5xl mx-auto px-4 py-12">
            <header className="mb-8">
                <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">About GenFabTools</h1>
                <p className="mt-2 text-slate-600">Practical tools for architects and engineers — simple, auditable occupancy calculations that fit your workflow.</p>
            </header>

            <section className="grid gap-8 md:grid-cols-2 items-start">
                <div>
                    <h2 className="text-xl font-semibold mb-2">Our mission</h2>
                    <p className="text-slate-700 leading-relaxed">Help design teams make confident, code-compliant decisions faster by providing clear, auditable calculations, sensible defaults, and exportable results.</p>
                </div>

                <div>
                    <h2 className="text-xl font-semibold mb-2">What we build</h2>
                    <ul className="list-disc pl-5 text-slate-700 space-y-2">
                        <li>Fast occupancy and space planning calculations</li>
                        <li>Export to PDF and CSV for reporting and handoff</li>
                        <li>Lightweight integrations for common design workflows</li>
                    </ul>
                </div>
            </section>

            <section className="mt-12">
                <h3 className="text-2xl font-semibold mb-4">Values</h3>
                <div className="grid gap-4 sm:grid-cols-3">
                    <div className="p-4 bg-white/50 dark:bg-slate-800 rounded-lg shadow-sm text-slate-900 dark:text-white">
                        <h4 className="font-semibold">Accuracy</h4>
                        <p className="text-slate-600">Clear, auditable calculations with transparent assumptions.</p>
                    </div>
                    <div className="p-4 bg-white/50 dark:bg-slate-800 rounded-lg shadow-sm text-slate-900 dark:text-white">
                        <h4 className="font-semibold">Simplicity</h4>
                        <p className="text-slate-600">Tools that are fast to learn and simple to apply.</p>
                    </div>
                    <div className="p-4 bg-white/50 dark:bg-slate-800 rounded-lg shadow-sm text-slate-900 dark:text-white">
                        <h4 className="font-semibold">Transparency</h4>
                        <p className="text-slate-600">Exportable outputs and documented assumptions for audits.</p>
                    </div>
                </div>
            </section>

            <section className="mt-12">
                <h3 className="text-2xl font-semibold mb-4">Team</h3>
                <p className="text-slate-700">A small cross-functional team focused on building dependable tools. For partnerships or support, please visit our Contact page.</p>
            </section>
        </main>
    );
}
