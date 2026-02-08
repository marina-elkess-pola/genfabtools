/**
 * GenFabTools Parking Engine - Results Panel
 *
 * Right panel containing metrics and results.
 */

import React from "react";
import { MetricsPanel } from "../panels/MetricsPanel";

export function ResultsPanel() {
    return (
        <div className="flex flex-col h-full max-h-full bg-white border-l border-gray-200">
            {/* Header - Fixed */}
            <div className="px-4 py-3 border-b border-gray-200 flex-shrink-0">
                <h2 className="text-base font-semibold text-gray-900">
                    Results
                </h2>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 min-h-0 overflow-y-auto">
                <MetricsPanel />
            </div>

            {/* Footer with Transparency Labels - Fixed */}
            <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 flex-shrink-0">
                {/* Transparency Labels */}
                <div className="flex justify-center gap-4 text-xs text-gray-500 mb-1">
                    <span>Units: Imperial (ft / SF)</span>
                    <span>•</span>
                    <span>Ruleset: Generic US parking standards</span>
                </div>
                <p className="text-xs text-gray-400 text-center">
                    For early-stage feasibility only. Not for construction.
                </p>
            </div>
        </div>
    );
}
