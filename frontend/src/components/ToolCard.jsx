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
      className={`bg-white rounded-2xl shadow-sm p-6 w-full cursor-pointer transition-all flex flex-col h-full min-h-[28rem] md:min-h-[30rem] transform ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'} hover:-translate-y-1 hover:shadow-lg duration-300 overflow-hidden`}
      onClick={() => onOpen(tool)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen(tool); }}
    >
      {/* Header: fixed area for icon, title, subtitle and tags */}
      <div className="flex items-start gap-4 h-20 md:h-24">
        <img
          src={tool.icon}
          alt={tool.title}
          className="w-16 h-16 rounded-lg shadow-md flex-shrink-0"
          width="64"
          height="64"
          loading="lazy"
          decoding="async"
        />
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-extrabold text-slate-900">{tool.title}</h3>
          <p className="text-sm text-slate-600">{tool.subtitle}</p>
        </div>
      </div>

      {/* Description area: consistent min height so cards align visually; prevent overflow */}
      <p className="mt-4 text-sm text-slate-700 leading-snug min-h-[4rem] md:min-h-[5rem] overflow-hidden break-words">
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

      {/* Read more opens slide-over */}
      {tool.description && tool.description.length > 140 && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onOpen(tool); }}
          className="mt-2 text-sm text-slate-600 hover:text-slate-800"
          aria-label={`Open details for ${tool.title}`}
        >
          Read more
        </button>
      )}

      {/* Footer: fixed to bottom using mt-auto so all cards align */}
      <div className="mt-auto pt-4 border-t border-slate-100/60 dark:border-slate-800/60 flex-shrink-0">
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

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); /* add to cart logic placeholder */ }}
            className="w-full sm:w-auto flex-1 rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold hover:opacity-95"
          >
            Add to cart
          </button>

          <Link
            to={tool.link || '#'}
            onClick={(e) => { e.stopPropagation(); /* allow navigation but prevent card click */ }}
            className="w-full sm:w-auto flex-1 rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-800 text-center hover:bg-slate-50"
          >
            Product details
          </Link>
        </div>
      </div>
    </div>
  );
}
