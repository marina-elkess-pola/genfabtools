import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function ToolCard({ tool }) {
  const navigate = useNavigate();

  // Billing state
  const [billing, setBilling] = useState('month');

  // Pricing logic
  const price =
    billing === 'month'
      ? tool.priceMonthly
      : tool.priceYearly;

  return (
    <div className="bg-white rounded-2xl shadow-sm w-full flex flex-col h-full min-h-[460px] hover:-translate-y-1 hover:shadow-lg transition-all duration-300 overflow-hidden">

      {/* CLICKABLE BODY */}
      <div
        onClick={() => {
          navigate(`/tools/${tool.id}`);
          window.scrollTo(0, 0);
        }}
        className="flex flex-col flex-1 p-6 cursor-pointer"
      >
        {/* IMAGE */}
        <img
          src={tool.image || tool.icon}
          alt={tool.title}
          className="w-full h-40 object-cover rounded-lg shadow-sm"
        />

        {/* TITLE */}
        <h3 className="mt-4 text-lg font-extrabold text-slate-900">
          {tool.title}
        </h3>

        {/* DESCRIPTION */}
        <p className="mt-2 text-sm text-slate-600 leading-relaxed">
          {tool.description}
        </p>

        {/* TAGS */}
        <div className="mt-3 flex gap-2 flex-wrap">
          {tool.tags?.map((tag, i) => (
            <span
              key={i}
              className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>

      {/* FOOTER */}
      <div className="mt-auto p-6 border-t border-slate-100">

        {tool.priceMonthly ? (
          <>
            {/* PRICE + TOGGLE */}
            <div className="flex items-center justify-between mb-3">

              <span className="text-lg font-bold text-slate-900">
                ${price}
                <span className="text-sm text-slate-500 ml-1">
                  / {billing}
                </span>
              </span>

              <select
                value={billing}
                onChange={(e) => setBilling(e.target.value)}
                className="border rounded-md px-2 py-1 text-sm"
              >
                <option value="month">month</option>
                <option value="year">year</option>
              </select>
            </div>

            {/* ACTION BUTTONS */}
            <div className="flex gap-3">

              {/* OPEN TOOL */}
              <button
                onClick={() => navigate(`/tools/${tool.id}`)}
                className="flex-1 rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold hover:bg-slate-800"
              >
                Open Tool
              </button>

              {/* DETAILS */}
              <button
                onClick={() => navigate(`/tools/${tool.id}`)}
                className="flex-1 rounded-md border border-slate-200 px-4 py-2 text-sm hover:bg-slate-50"
              >
                Details
              </button>

            </div>
          </>
        ) : (
          <>
            {/* EARLY ACCESS */}
            <button
              onClick={() =>
                window.open(
                  'https://mail.google.com/mail/?view=cm&fs=1&to=support@genfabtools.com&su=RSI Early Access',
                  '_blank'
                )
              }
              className="w-full rounded-md bg-slate-900 text-white px-4 py-2 text-sm font-semibold hover:bg-slate-800"
            >
              Get Early Access
            </button>
          </>
        )}

      </div>
    </div>
  );
}