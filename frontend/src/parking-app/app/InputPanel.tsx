/**
 * GenFabTools Parking Engine - Input Panel
 *
 * Left panel containing site definition, parking config, and constraints.
 */

import React from "react";
import { SiteDefinitionPanel } from "../panels/SiteDefinitionPanel";
import { ParkingConfigPanel } from "../panels/ParkingConfigPanel";
import { ConstraintsPanel } from "../panels/ConstraintsPanel";
import { EvaluateButton } from "./EvaluateButton";

export function InputPanel() {
    return (
        <div className="flex flex-col h-full max-h-full bg-white border-r border-gray-200">
            {/* Header - Fixed */}
            <div className="px-4 py-3 border-b border-gray-200 flex-shrink-0">
                <h2 className="text-base font-semibold text-gray-900">
                    Input
                </h2>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-gray-200">
                <SiteDefinitionPanel />
                <ParkingConfigPanel />
                <ConstraintsPanel />
            </div>

            {/* Evaluate Button - Fixed */}
            <div className="flex-shrink-0">
                <EvaluateButton />
            </div>
        </div>
    );
}
