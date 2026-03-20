import React from 'react';
import { Link } from 'react-router-dom';

export default function ToolDetails({ tool, onClose }) {
  if (!tool) return null;

  return (
    // simple slide-over panel fixed to the right
    <div className="fixed inset-0 z-50 pointer-events-none">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm pointer-events-auto" onClick={onClose} />
      <aside className="absolute right-0 top-0 h-full w-full sm:w-96 bg-white shadow-lg p-6 pointer-events-auto overflow-auto">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">{tool.title}</h2>
            <p className="text-sm text-slate-600 mt-1">{tool.subtitle}</p>
          </div>
          <button onClick={onClose} className="ml-4 text-slate-600 hover:text-slate-800">Close</button>
        </div>

        <div className="mt-6">
          <p className="text-sm text-slate-700 leading-relaxed">{tool.longDescription || tool.description}</p>

          <div className="mt-6">
            <strong className="text-sm text-slate-600">Price:</strong>
            <div className="mt-1 text-sm font-semibold text-slate-800">{tool.price}</div>
          </div>

          <div className="mt-6">
            <Link to={tool.link || '#'} className="inline-block px-4 py-2 bg-slate-900 text-white rounded-md hover:bg-slate-700">Open Tool</Link>
          </div>
        </div>
      </aside>
    </div>
  );
}
