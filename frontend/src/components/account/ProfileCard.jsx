import React from 'react';

export default function ProfileCard({ user }) {
    const initial = user?.displayName ? user.displayName.charAt(0).toUpperCase() : (user?.email || '?').charAt(0).toUpperCase();
    return (
        <div className="bg-white/95 dark:bg-slate-900/95 border border-slate-200 dark:border-slate-800 rounded-lg p-5">
            <div className="flex items-center gap-4">
                <div className="h-14 w-14 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-lg font-medium text-slate-800 dark:text-white">
                    {initial}
                </div>
                <div className="min-w-0">
                    <div className="text-lg font-semibold truncate">{user?.displayName || user?.email}</div>
                    <div className="text-sm text-slate-500 truncate">{user?.email}</div>
                    {user?.createdAt && <div className="mt-2 text-xs text-slate-400">Member since {new Date(user.createdAt).toLocaleDateString()}</div>}
                </div>
            </div>
        </div>
    );
}
