/**
 * GenFabTools Parking Engine - Cores Layer
 *
 * Renders vertical cores (stairs, elevators) for structured parking.
 * Read-only rendering - no editing.
 */

import React from "react";
import type { VerticalCore, ViewportState } from "../../types";
import { worldToScreen, CANVAS_COLORS } from "../../utils";

interface CoresLayerProps {
    cores: readonly VerticalCore[];
    viewport: ViewportState;
    canvasHeight: number;
}

export function CoresLayer({
    cores,
    viewport,
    canvasHeight,
}: CoresLayerProps) {
    if (cores.length === 0) {
        return null;
    }

    return (
        <g className="cores-layer">
            {cores.map((core) => {
                const { geometry, id } = core;

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
                        fill={CANVAS_COLORS.coreFill}
                        stroke={CANVAS_COLORS.core}
                        strokeWidth={2}
                        strokeLinejoin="round"
                    />
                );
            })}
        </g>
    );
}
