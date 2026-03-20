import React from 'react';
import { Link } from 'react-router-dom';

export default function AccountActions({ user, onSignOut }) {
    return (
        <div className="bg-white/80 dark:bg-slate-900/95 rounded-lg border border-slate-200 dark:border-slate-800 p-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex gap-3">
                    {!user?.paid ? (
                        <Link
                            to="/purchase"
                            className="inline-flex items-center rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 transition transform duration-150 hover:-translate-y-1 hover:shadow-md hover:!text-white"
                        >
                            Get access
                        </Link>
                    ) : (
                        <Link to="/purchase/manage" className="inline-flex items-center rounded-md border px-4 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300">Manage subscription</Link>
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
