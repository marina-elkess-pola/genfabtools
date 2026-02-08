import React from 'react';

function PurchaseRow({ p }) {
    return (
        <li className="flex items-center justify-between gap-4 py-3 border-b last:border-b-0">
            <div className="min-w-0">
                <div className="font-medium truncate">{p.product}</div>
                <div className="text-xs text-slate-500 truncate">{new Date(p.date).toLocaleDateString()}</div>
            </div>
            <div className="flex items-center gap-3">
                <div className="text-sm text-slate-700">{p.amount}</div>
                {p.receiptUrl && (
                    <a href={p.receiptUrl} target="_blank" rel="noreferrer" className="text-sm text-indigo-600 hover:underline">Receipt</a>
                )}
            </div>
        </li>
    );
}

export default function PurchasesList({ purchases }) {
    if (!purchases || purchases.length === 0) {
        return <p className="text-sm text-slate-500">No purchases yet.</p>;
    }

    return (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {purchases.map(p => <PurchaseRow key={p.id} p={p} />)}
        </ul>
    );
}
