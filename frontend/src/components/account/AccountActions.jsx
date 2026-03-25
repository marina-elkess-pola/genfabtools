import React from 'react';
import { Link } from 'react-router-dom';

export default function AccountActions({ user, onSignOut }) {
    return (
        <div className="bg-white/80 dark:bg-slate-900/95 rounded-lg border border-slate-200 dark:border-slate-800 p-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex gap-3">
                    {!user?.paid ? (
                        <Link
                            to="/tools/rsi"
                            className="inline-flex items-center rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 transition transform duration-150 hover:-translate-y-1 hover:shadow-md hover:!text-white"
                        >
                            Get access
                        </Link>
                    ) : (
                        <span className="inline-flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-4 py-2 text-sm font-medium text-green-700">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                            Active subscription
                        </span>
                    )}
                    <Link
                        to="/support"
                        className="inline-flex items-center rounded-md bg-white text-slate-900 border border-slate-200 px-4 py-2 text-sm hover:bg-slate-100 dark:bg-slate-800 dark:text-white dark:border-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 transition transform duration-150 hover:-translate-y-1 hover:shadow-md hover:!text-slate-900 dark:hover:!text-white"
                    >
                        Contact support
                    </Link>
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={onSignOut}
                        className="inline-flex items-center rounded-md bg-white text-slate-900 border border-slate-200 px-3 py-2 text-sm hover:bg-slate-100 dark:bg-slate-800 dark:text-white dark:border-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 transition transform duration-150 hover:-translate-y-1 hover:shadow-md"
                    >
                        Sign out
                    </button>
                </div>
            </div>
        </div>
    );
}
