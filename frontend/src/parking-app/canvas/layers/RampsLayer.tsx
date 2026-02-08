/**
 * GenFabTools Parking Engine - Ramps Layer
 *
 * Renders parking ramps for structured parking.
 * Read-only rendering - no editing.
 */

import React from "react";
import type { Ramp, ViewportState } from "../../types";
import { worldToScreen, CANVAS_COLORS } from "../../utils";

interface RampsLayerProps {
    ramps: readonly Ramp[];
    viewport: ViewportState;
    canvasHeight: number;
}

export function RampsLayer({
    ramps,
    viewport,
    canvasHeight,
}: RampsLayerProps) {
    if (ramps.length === 0) {
        return null;
    }

    return (
        <g className="ramps-layer">
            {ramps.map((ramp) => {
                const { geometry, id } = ramp;

                if (geometry.points.length < 3) {
                    return null;
                }

                // Convert world coordinates to screen coordinates
                const screenPoints = geometry.points.map((p) =>
                    worldToScreen(p, viewport, canvasHeight)
                );

                // Create SVG path
                const pathData =
                    screenPoints
                        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
                        .join(" ") + " Z";

                return (
                    <path
                        key={id}
                        d={pathData}
                        fill={CANVAS_COLORS.rampFill}
                        stroke={CANVAS_COLORS.ramp}
                        strokeWidth={2}
                        strokeLinejoin="round"
                        strokeDasharray="4 2"
                    />
                );
            })}
        </g>
    );
}
