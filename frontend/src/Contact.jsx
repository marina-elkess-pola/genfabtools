import React, { useEffect, useState } from 'react';

export default function Contact() {
    useEffect(() => {
        document.title = 'Contact — GenFabTools';
    }, []);

    const [form, setForm] = useState({ name: '', email: '', message: '' });
    const [status, setStatus] = useState(null);

    const isValid = form.name.trim() && form.email.trim() && form.message.trim();

    const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!isValid) return setStatus('incomplete');
        setStatus('sending');
        try {
            // POST to backend API (optional). If backend not configured, this will fail gracefully.
            await fetch('/api/contact', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(form),
            });
            setStatus('sent');
            setForm({ name: '', email: '', message: '' });
        } catch (err) {
            console.error(err);
            setStatus('error');
        }
    };

    return (
        <main className="max-w-3xl mx-auto px-4 py-12">
            <h2 className="text-2xl font-bold mb-4">Contact</h2>
            <p className="mb-6 text-slate-700">Have a question, bug report, or sales inquiry? Send us a message below.</p>

            <div className="grid gap-8 md:grid-cols-2">
                <form onSubmit={handleSubmit} className="space-y-4 md:pr-6">
                    <div>
                        <label htmlFor="name" className="block text-sm font-medium text-slate-700">Name</label>
                        <input id="name" name="name" value={form.name} onChange={handleChange} required aria-required="true" className="mt-1 block w-full rounded-md border p-2" />
                    </div>

                    <div>
                        <label htmlFor="email" className="block text-sm font-medium text-slate-700">Email</label>
                        <input id="email" name="email" value={form.email} onChange={handleChange} type="email" required aria-required="true" className="mt-1 block w-full rounded-md border p-2" />
                    </div>

                    <div className="md:col-span-2">
                        <label htmlFor="message" className="block text-sm font-medium text-slate-700">Message</label>
                        <textarea id="message" name="message" value={form.message} onChange={handleChange} rows={6} required aria-required="true" className="mt-1 block w-full rounded-md border p-2" />
                    </div>

                    <div>
                        <button type="submit" className="rounded bg-slate-900 text-white px-4 py-2 disabled:opacity-60" disabled={status === 'sending'}>
                            {status === 'sending' ? 'Sending…' : 'Send Message'}
                        </button>
                    </div>

                    {status === 'sent' && <div className="text-green-600">Thanks — your message was sent (or queued).</div>}
                    {status === 'error' && <div className="text-red-600">Sorry, we couldn't send your message right now.</div>}
                    {status === 'incomplete' && <div className="text-yellow-600">Please complete all fields before sending.</div>}
                </form>

                <aside className="bg-white/50 dark:bg-slate-800 p-4 rounded-md text-slate-900 dark:text-white">
                    <h3 className="font-semibold">Other ways to reach us</h3>
                    <p className="text-slate-700 mt-2">Email: <a className="text-slate-900 underline" href="mailto:support@genfabtools.example">support@genfabtools.example</a></p>
                    <p className="text-slate-700 mt-4">Office hours: Mon–Fri, 9am–5pm (your local timezone)</p>

                    <div className="mt-6 text-sm text-slate-600">
                        <strong>Note:</strong> Messages are queued for review. We do not share your email with third parties.
                    </div>
                </aside>
            </div>
        </main>
    );
}
