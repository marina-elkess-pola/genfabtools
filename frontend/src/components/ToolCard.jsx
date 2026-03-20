import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

export default function ToolCard({ tool }) {
  const [mounted, setMounted] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 30);
    return () => clearTimeout(t);
  }, []);

  const shortDesc = tool.description.length > 140 ? tool.description.slice(0, 140) + '…' : tool.description;

  // Prevent the parent Link from navigating when an inner action is clicked
  function handleAction(e, path) {
    e.stopPropagation();
    e.preventDefault();
    navigate(path);
  }

  return (
    <Link
      to={`/tools/${tool.id}`}
      className={`bg-white rounded-2xl shadow-sm w-full cursor-pointer transition-all flex flex-col h-full min-h-[460px] transform ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'} hover:-translate-y-1 hover:shadow-lg duration-300 overflow-hidden no-underline text-inherit`}
    >
      {/* Card body */}
      <div className="flex flex-col flex-1 p-6">
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

        {/* Tags */}
        {tool.tags && tool.tags.length > 0 && (
          <div className="mt-3 flex items-center gap-2">
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
      </div>

      {/* Footer: uses buttons instead of nested Links to avoid invalid <a> inside <a> */}
      <div className="mt-auto pt-4 px-6 pb-6 border-t border-slate-100/60 dark:border-slate-800/60 flex-shrink-0">
        {tool.price ? (
          <>
            {tool.type !== 'plugin' && (
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-slate-800">{typeof tool.price === 'number' ? `$${tool.price}` : tool.price}</span>
                <select
                  onClick={(e) => { e.stopPropagation(); e.preventDefault(); }}
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
              <button
                type="button"
                onClick={(e) => handleAction(e, tool.link || '#')}
                className="flex-1 rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold text-center hover:opacity-95 cursor-pointer border-none"
              >
                View Tool
              </button>

              <button
                type="button"
                onClick={(e) => handleAction(e, `/tools/${tool.id}`)}
                className="flex-1 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm text-slate-800 text-center hover:bg-slate-50 cursor-pointer"
              >
                Product details
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="mb-3">
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-100 text-amber-800">Early Access</span>
            </div>

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                window.location.href = 'mailto:contact@genfabtools.com';
              }}
              className="block w-full rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold text-center hover:opacity-95 cursor-pointer border-none"
            >
              Get Early Access
            </button>
          </>
        )}
      </div>
    </Link>
  );
}
