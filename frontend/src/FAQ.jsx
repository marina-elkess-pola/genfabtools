import React, { useEffect } from 'react';

export default function FAQ() {
    useEffect(() => {
        document.title = 'FAQ — GenFabTools';
    }, []);

    const faqs = [
        { q: 'What is OccuCalc?', a: 'OccuCalc helps calculate occupancy and space planning quickly.' },
        { q: 'Is this free?', a: 'There is a free tier; paid features are available via checkout.' },
        { q: 'How do I report a bug?', a: 'Use the Contact page with details and screenshots.' },
    ];

    return (
        <main className="max-w-3xl mx-auto px-4 py-12">
            <h2 className="text-2xl font-bold mb-6">Frequently Asked Questions</h2>
            <div className="space-y-4">
                {faqs.map((f, i) => (
                    <details key={i} className="bg-white/50 dark:bg-slate-800 p-4 rounded-md text-slate-900 dark:text-white" aria-labelledby={`faq-${i}`}>
                        <summary id={`faq-${i}`} className="cursor-pointer font-semibold">{f.q}</summary>
                        <div className="mt-2 text-slate-700 dark:text-slate-300">{f.a}</div>
                    </details>
                ))}
            </div>
        </main>
    );
}
