import React, { useState } from 'react';

export default function RSI() {
    const [billing, setBilling] = useState('monthly');

    const monthlyPrice = 49;
    const yearlyPrice = 390;
    const savings = monthlyPrice * 12 - yearlyPrice;

    const price = billing === 'monthly' ? monthlyPrice : yearlyPrice;

    return (
        <div className="max-w-6xl mx-auto px-6 py-16">

            {/* HERO */}
            <div className="grid md:grid-cols-2 gap-12 items-center">

                <div>
                    <h1 className="text-4xl font-extrabold text-slate-900">
                        Residential Scheme Intelligence
                    </h1>

                    <p className="mt-4 text-lg text-slate-600">
                        Analyze residential layouts, detect inefficiencies, optimize design decisions,
                        and evaluate financial performance directly inside Revit.
                    </p>

                    {/* PRICING TOGGLE */}
                    <div className="mt-6 flex items-center gap-3">

                        <button
                            onClick={() => setBilling('monthly')}
                            className={`px-4 py-2 rounded-md text-sm font-semibold ${billing === 'monthly'
                                    ? 'bg-black text-white'
                                    : 'bg-white border'
                                }`}
                        >
                            Monthly
                        </button>

                        <button
                            onClick={() => setBilling('yearly')}
                            className={`px-4 py-2 rounded-md text-sm font-semibold relative ${billing === 'yearly'
                                    ? 'bg-black text-white'
                                    : 'bg-white border'
                                }`}
                        >
                            Yearly

                            {/* SAVE BADGE */}
                            <span className="absolute -top-2 -right-3 bg-green-500 text-white text-[10px] px-2 py-0.5 rounded-full">
                                Save ${savings}
                            </span>
                        </button>

                    </div>

                    {/* PRICE */}
                    <div className="mt-4 text-3xl font-bold text-slate-900">
                        ${price}
                        <span className="text-sm text-slate-500 ml-2">
                            / {billing === 'monthly' ? 'month' : 'year'}
                        </span>
                    </div>

                    {/* YEARLY INFO */}
                    {billing === 'yearly' && (
                        <p className="text-sm text-green-600 mt-1">
                            Equivalent to ${(yearlyPrice / 12).toFixed(0)}/month
                        </p>
                    )}

                    {/* BUTTONS */}
                    <div className="mt-6 flex gap-4 flex-wrap">

                        <a
                            href="https://genfabtools.com/download/RSI_Setup.exe"
                            className="bg-black text-white px-6 py-3 rounded-md font-semibold hover:bg-gray-800"
                        >
                            Download Tool
                        </a>

                        <a
                            href="https://genfabtools.com/docs/rsi/index.html"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="border text-black px-6 py-3 rounded-md font-semibold hover:bg-gray-100"
                        >
                            Documentation
                        </a>

                    </div>
                </div>

                {/* IMAGE */}
                <div>
                    <img
                        src="/images/rsi/financial-impact-RSI.png"
                        alt="RSI Dashboard"
                        className="rounded-xl shadow-lg"
                    />
                </div>
            </div>

            {/* FEATURES */}
            <div className="mt-20 grid md:grid-cols-3 gap-8">

                <div className="p-6 border rounded-xl">
                    <h3 className="font-bold text-lg">Layout Analysis</h3>
                    <p className="text-sm text-slate-600 mt-2">
                        Detect inefficiencies in unit distribution, circulation, and planning logic.
                    </p>
                </div>

                <div className="p-6 border rounded-xl">
                    <h3 className="font-bold text-lg">Performance Metrics</h3>
                    <p className="text-sm text-slate-600 mt-2">
                        Evaluate KPIs like efficiency ratios, unit mix, and space utilization.
                    </p>
                </div>

                <div className="p-6 border rounded-xl">
                    <h3 className="font-bold text-lg">Financial Insight</h3>
                    <p className="text-sm text-slate-600 mt-2">
                        Instantly estimate revenue potential and feasibility of schemes.
                    </p>
                </div>

            </div>

        </div>
    );
}