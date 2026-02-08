import React from 'react';

export default function GFT({ className = 'w-6 h-6 sm:w-8 sm:h-8 text-slate-900 dark:text-white', title = 'GFT' }) {
    return (
        <svg
            width="32"
            height="32"
            viewBox="0 0 32 32"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className={className}
            role="img"
            aria-label={title}
        >
            <rect width="32" height="32" rx="6" fill="currentColor" opacity="0.06" />
            <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 20v-8h5l3.5 6 3.5-6H26v8" />
            </g>
            <title>{title}</title>
        </svg>
    );
}
