import React from 'react';

export default function About() {
    return (
        <div className="max-w-6xl mx-auto px-6 py-16">

            {/* HEADER */}
            <div className="max-w-3xl">
                <h1 className="text-4xl font-extrabold text-slate-900">
                    About GenFabTools
                </h1>

                <p className="mt-4 text-lg text-slate-600 leading-relaxed">
                    GenFabTools is a platform dedicated to building intelligent tools for architects,
                    engineers, and designers. Our focus is on simplifying complex workflows,
                    improving decision-making, and bridging the gap between design and performance.
                </p>
            </div>

            {/* MISSION */}
            <div className="mt-12 grid md:grid-cols-2 gap-10">

                <div>
                    <h2 className="text-xl font-bold text-slate-900">Our mission</h2>

                    <p className="mt-3 text-slate-600 leading-relaxed">
                        To develop a growing ecosystem of tools that enhance how projects are designed,
                        analyzed, and delivered — making advanced workflows accessible, efficient,
                        and reliable.
                    </p>
                </div>

                <div>
                    <h2 className="text-xl font-bold text-slate-900">What we build</h2>

                    <ul className="mt-3 space-y-2 text-slate-600">
                        <li>• Revit plugins for design intelligence and feasibility analysis</li>
                        <li>• Grasshopper tools for computational design workflows</li>
                        <li>• Digital utilities that connect design decisions with performance outcomes</li>
                    </ul>
                </div>

            </div>

            {/* PRODUCTS */}
            <div className="mt-16">
                <h2 className="text-xl font-bold text-slate-900">Current tools</h2>

                <div className="mt-6 grid md:grid-cols-2 gap-6">

                    {/* RSI */}
                    <div className="p-6 border rounded-xl">
                        <h3 className="font-semibold text-slate-900">
                            Residential Scheme Intelligence (RSI)
                        </h3>
                        <p className="mt-2 text-sm text-slate-600">
                            A professional Revit plugin that analyzes residential layouts,
                            detects inefficiencies, and evaluates financial performance to support
                            better design decisions.
                        </p>
                    </div>

                    {/* Elytra */}
                    <div className="p-6 border rounded-xl">
                        <h3 className="font-semibold text-slate-900">
                            Elytra (Grasshopper Plugin)
                        </h3>

                        <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                            Elytra is a Grasshopper plugin developed to support computational facade design,
                            with a focus on adaptive panel systems. It enables designers to generate and
                            control panel geometries based on performance-driven parameters, making it easier
                            to explore responsive facade strategies within parametric workflows.
                        </p>

                        <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                            The plugin has been published on Food4Rhino and GitHub, where it has been used by
                            designers working with generative and performance-based design approaches.
                        </p>

                        <a
                            href="https://www.food4rhino.com/en/app/adaptive-facade-panels-elytra-adpanels"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-blue-600 font-medium hover:underline mt-2 inline-block"
                        >
                            View on Food4Rhino →
                        </a>
                    </div>

                </div>
            </div>

            {/* VALUES */}
            <div className="mt-16">
                <h2 className="text-xl font-bold text-slate-900">Values</h2>

                <div className="mt-6 grid md:grid-cols-3 gap-6">

                    <div className="p-6 border rounded-xl">
                        <h3 className="font-semibold text-slate-900">Clarity</h3>
                        <p className="mt-2 text-sm text-slate-600">
                            We turn complex processes into clear, actionable insights.
                        </p>
                    </div>

                    <div className="p-6 border rounded-xl">
                        <h3 className="font-semibold text-slate-900">Practicality</h3>
                        <p className="mt-2 text-sm text-slate-600">
                            Every tool is built for real-world use, not theoretical workflows.
                        </p>
                    </div>

                    <div className="p-6 border rounded-xl">
                        <h3 className="font-semibold text-slate-900">Innovation</h3>
                        <p className="mt-2 text-sm text-slate-600">
                            We continuously explore new ways to improve design and analysis processes.
                        </p>
                    </div>

                </div>
            </div>

            {/* TEAM */}
            <div className="mt-16">
                <h2 className="text-xl font-bold text-slate-900">Team</h2>

                <p className="mt-3 text-slate-600">
                    GenFabTools is an independent initiative focused on developing tools that
                    address real challenges in architecture and design workflows.
                </p>
            </div>

        </div>
    );
}