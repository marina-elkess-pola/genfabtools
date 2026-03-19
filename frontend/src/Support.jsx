import emailjs from 'emailjs-com';
import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

const typeToSubject = { bug: 'Bug Report', feature: 'Feature Request' };

export default function Support() {
    const [searchParams] = useSearchParams();
    const initialSubject = typeToSubject[searchParams.get('type')] || 'General Question';

    const [form, setForm] = useState({ name: '', email: '', subject: initialSubject, message: '' });
    const [submitted, setSubmitted] = useState(false);

    useEffect(() => {
        document.title = 'Support — GenFabTools';
    }, []);

    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
    };

    const handleSubmit = (e) => {
        e.preventDefault();

        const templateParams = {
            from_name: form.name,
            from_email: form.email,
            subject: form.subject,
            message: form.message,
        };

        emailjs
            .send(
                "service_ne9ljj4",
                "template_zkwaoqn",
                templateParams,
                "NIka6Be3jlqdsk_iB"
            )
            .then(
                () => {
                    setForm({ name: '', email: '', subject: 'General Question', message: '' });
                    setSubmitted(true);
                    setTimeout(() => setSubmitted(false), 5000);
                },
                (error) => {
                    console.error(error);
                    alert("Failed to send message");
                }
            );
    };

    const inputClass = 'w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors';
    const labelClass = 'block text-sm font-medium text-slate-700 mb-1.5';

    return (
        <main className="max-w-5xl mx-auto px-4 py-12">
            <header className="mb-12 text-center">
                <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">Support</h1>
                <p className="mt-3 text-lg text-slate-600 mx-auto" style={{ maxWidth: '520px' }}>
                    Need help with GenFabTools or RSI? We're here to help.
                </p>
            </header>

            <section className="mb-12">
                <h2 className="text-2xl font-semibold text-slate-900 mb-6 text-center">Quick Links</h2>
                <div className="grid gap-6 sm:grid-cols-2 max-w-2xl mx-auto">
                    <Link
                        to="/docs/rsi/index.html"
                        className="group rounded-2xl border border-slate-200 p-6 text-center hover:shadow-lg transition-shadow duration-200"
                    >
                        <h3 className="text-xl font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">Documentation</h3>
                        <p className="mt-2 text-slate-500 text-sm">Guides, setup instructions, and feature reference for RSI.</p>
                    </Link>
                    <Link
                        to="/tools/rsi/index.html"
                        className="group rounded-2xl border border-slate-200 p-6 text-center hover:shadow-lg transition-shadow duration-200"
                    >
                        <h3 className="text-xl font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">Download RSI</h3>
                        <p className="mt-2 text-slate-500 text-sm">Get the latest version of Residential Scheme Intelligence.</p>
                    </Link>
                </div>
            </section>

            <section className="max-w-2xl mx-auto mb-12">
                <h2 className="text-2xl font-semibold text-slate-900 mb-6 text-center">Contact Us</h2>
                <div className="rounded-2xl border border-slate-200 p-8">
                    <form onSubmit={handleSubmit} className="space-y-5">
                        {submitted && (
                            <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-800 text-sm">
                                Your message has been sent. We'll get back to you soon.
                            </div>
                        )}
                        <div>
                            <label htmlFor="name" className={labelClass}>Name</label>
                            <input
                                id="name"
                                name="name"
                                type="text"
                                required
                                value={form.name}
                                onChange={handleChange}
                                placeholder="Your name"
                                className={inputClass}
                            />
                        </div>

                        <div>
                            <label htmlFor="email" className={labelClass}>Email</label>
                            <input
                                id="email"
                                name="email"
                                type="email"
                                required
                                value={form.email}
                                onChange={handleChange}
                                placeholder="you@example.com"
                                className={inputClass}
                            />
                        </div>

                        <div>
                            <label htmlFor="subject" className={labelClass}>Subject</label>
                            <select
                                id="subject"
                                name="subject"
                                value={form.subject}
                                onChange={handleChange}
                                className={inputClass}
                            >
                                <option>General Question</option>
                                <option>Bug Report</option>
                                <option>Feature Request</option>
                            </select>
                        </div>

                        <div>
                            <label htmlFor="message" className={labelClass}>Message</label>
                            <textarea
                                id="message"
                                name="message"
                                required
                                rows={5}
                                value={form.message}
                                onChange={handleChange}
                                placeholder="Describe your issue or question..."
                                className={inputClass + ' resize-vertical'}
                            />
                        </div>

                        <button
                            type="submit"
                            className="w-full rounded-lg bg-blue-600 text-white font-semibold px-6 py-2.5 text-sm hover:bg-blue-700 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                        >
                            Send Message
                        </button>
                    </form>

                    <p className="mt-6 text-center text-slate-500 text-sm">
                        Prefer email? Contact us at{' '}
                        <a href="mailto:support@genfabtools.com" className="text-blue-600 font-medium hover:underline">
                            support@genfabtools.com
                        </a>
                    </p>
                </div>
            </section>
        </main>
    );
}
