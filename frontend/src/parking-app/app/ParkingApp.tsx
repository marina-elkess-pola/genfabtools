/**
 * GenFabTools Parking Engine - Main Application
 *
 * Three-panel layout:
 * - Input Panel (left)
 * - Drawing Canvas (center)
 * - Results Panel (right)
 *
 * This is a decision lens, not a design tool.
 * All geometry and metrics come from the backend.
 */

import React, { useEffect } from "react";
import { ScenarioProvider, useScenario } from "../state";
import { ParkingCanvas } from "../canvas";
import { ScenarioManager } from "./ScenarioManager";
import { InputPanel } from "./InputPanel";
import { ResultsPanel } from "./ResultsPanel";

// Logo imports
import genfabtoolsLogo from "../../assets/genfabtools-logo-black.png";
import parkLogo from "../../assets/park-logo-black.png";

// =============================================================================
// App Header
// =============================================================================

/** Header logo height - consistent across all pages */
const HEADER_LOGO_HEIGHT = 28; // px

/** Version badge - update this for each release */
const APP_VERSION = "2.0 (DEV)";

console.log("🔥 FRONTEND HEADER COMPONENT IS LIVE 🔥");

function AppHeader() {
    return (
        <header className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-gray-200">
            {/* Left: Platform logo (secondary) + Tool branding (primary) */}
            <div className="flex items-center gap-4">
                {/* GenFabTools platform logo - primary (leftmost) */}
                <a
                    href="/"
                    className="flex-shrink-0 hover:opacity-80 transition-opacity"
                    title="GenFabTools Home"
                >
                    <img
                        src={genfabtoolsLogo}
                        alt="GenFabTools"
                        style={{ height: HEADER_LOGO_HEIGHT, width: 'auto' }}
                    />
                </a>

                {/* Divider */}
                <div className="w-px h-6 bg-gray-300" />

                {/* Parking Engine branding - secondary (tool) */}
                <div className="flex items-center gap-2">
                    <img
                        src={parkLogo}
                        alt="Parking Engine"
                        style={{ height: HEADER_LOGO_HEIGHT, width: 'auto' }}
                    />
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <h1 className="text-base font-bold text-gray-900 leading-tight">
                                Parking Engine
                            </h1>
                            <span className="px-1.5 py-0.5 text-xs font-mono text-gray-500 bg-gray-100 rounded">
                                v{APP_VERSION}
                            </span>
                        </div>
                        <span className="text-xs font-medium text-blue-600">
                            Feasibility Tool
                        </span>
                    </div>
                </div>
            </div>

            {/* Right: Disclaimer */}
            <div className="text-xs text-gray-500">
                Conceptual estimates only • Not for construction
            </div>
        </header>
    );
}

// =============================================================================
// App Layout (requires scenario context)
// =============================================================================

function AppLayout() {
    const { state, createScenario } = useScenario();

    // Create initial scenario on mount if none exist
    useEffect(() => {
        if (state.scenarios.length === 0) {
            createScenario(); // Uses "Scenario A" by default
        }
    }, [state.scenarios.length, createScenario]);

    return (
        <div className="flex flex-col h-screen max-h-screen overflow-hidden bg-gray-100">
            {/* Header - Fixed */}
            <div className="flex-shrink-0">
                <AppHeader />
            </div>

            {/* Scenario Manager - Fixed */}
            <div className="flex-shrink-0">
                <ScenarioManager />
            </div>

            {/* Main Content - Fills remaining height, no page scroll */}
            <div className="flex flex-1 min-h-0 overflow-hidden">
                {/* Left Panel - Input (scrolls independently) */}
                <aside className="w-80 flex-shrink-0 h-full overflow-hidden">
                    <InputPanel />
                </aside>

                {/* Center - Canvas (fixed viewport, internal zoom/pan) */}
                <main className="flex-1 min-w-0 h-full overflow-hidden">
                    <ParkingCanvas />
                </main>

                {/* Right Panel - Results (scrolls independently) */}
                <aside className="w-80 flex-shrink-0 h-full overflow-hidden">
                    <ResultsPanel />
                </aside>
            </div>
        </div>
    );
}

// =============================================================================
// Main App Component (with provider)
// =============================================================================

export function ParkingApp() {
    // Add body class to lock viewport height when parking engine is active
    useEffect(() => {
        document.body.classList.add("parking-engine-app");

        return () => {
            document.body.classList.remove("parking-engine-app");
        };
    }, []);

    return (
        <ScenarioProvider>
            <AppLayout />
        </ScenarioProvider>
    );
}

// Default export for easier imports
export default ParkingApp;
