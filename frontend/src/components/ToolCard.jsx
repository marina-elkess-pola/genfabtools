import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

export default function ToolCard({ tool, onOpen }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 30);
    return () => clearTimeout(t);
  }, []);

  const shortDesc = tool.description.length > 140 ? tool.description.slice(0, 140) + '…' : tool.description;

  return (
    <div
      className={`bg-white rounded-2xl shadow-sm p-6 w-full cursor-pointer transition-all flex flex-col h-full min-h-[460px] transform ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'} hover:-translate-y-1 hover:shadow-lg duration-300 overflow-hidden`}
      onClick={() => onOpen(tool)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen(tool); }}
    >
      {/* Icon */}
      <img
        src={tool.icon}
        alt={tool.title}
        className="w-16 h-16 rounded-lg shadow-md flex-shrink-0"
        width="64"
        height="64"
        loading="lazy"
        decoding="async"
      />

      {/* Title */}
      <h3 className="mt-4 text-lg font-extrabold text-slate-900">{tool.title}</h3>

      {/* Subtitle */}
      <p className="mt-1 mb-3 text-sm text-slate-500">{tool.subtitle}</p>

      {/* Description */}
      <p className="mt-2 text-sm text-slate-700 leading-relaxed break-words">
        {shortDesc}
      </p>

      {/* Tags (moved below description to avoid header overflow) */}
      {tool.tags && tool.tags.length > 0 && (
        <div className="mt-3 flex items-center gap-2">
          {/* show first tag on xs, reveal second and +N on sm+ to avoid overflow */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{tool.tags[0]}</span>
            {tool.tags.length > 1 && (
              <span className="hidden sm:inline-flex text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{tool.tags[1]}</span>
            )}
            {tool.tags.length > 2 && (
              <span className="hidden sm:inline-flex text-[11px] px-2 py-0.5 rounded-full bg-slate-50 text-slate-600">+{tool.tags.length - 2}</span>
            )}
          </div>
        </div>
      )}

      {/* Short tip */}
      {tool.tip && (
        <p className="mt-3 text-xs text-slate-500 italic">Tip: {tool.tip}</p>
      )}

      {/* Footer: fixed to bottom using mt-auto so all cards align */}
      <div className="mt-auto pt-4 border-t border-slate-100/60 dark:border-slate-800/60 flex-shrink-0">
        {tool.price ? (
          <>
            {tool.type !== 'plugin' && (
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-slate-800">{tool.price}</span>
                <select
                  onClick={(e) => e.stopPropagation()}
                  className="rounded-md border border-slate-200 px-2 py-1 text-sm bg-white text-slate-800"
                  defaultValue="1 year"
                  aria-label="Select term"
                >
                  <option>1 year</option>
                  <option>1 month</option>
                </select>
              </div>
            )}

            <div className="flex flex-row gap-3">
              <Link
                to={tool.link || '#'}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold text-center hover:opacity-95"
              >
                View Tool
              </Link>

              <Link
                to={tool.link || '#'}
                onClick={(e) => e.stopPropagation()}
                className="flex-1 rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-800 text-center hover:bg-slate-50"
              >
                Product details
              </Link>
            </div>
          </>
        ) : (
          <>
            <div className="mb-3">
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-100 text-amber-800">Early Access</span>
            </div>

            <a
              href="mailto:contact@genfabtools.com"
              onClick={(e) => e.stopPropagation()}
              className="block w-full rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold text-center hover:opacity-95"
            >
              Get Early Access
            </a>
          </>
        )}
      </div>
    </div>
  );
}
