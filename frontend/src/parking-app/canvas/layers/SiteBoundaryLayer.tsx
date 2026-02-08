/**
 * GenFabTools Parking Engine - Site Boundary Layer
 *
 * Renders the site boundary polygon.
 * Read-only rendering - no editing.
 */

import React from "react";
import type { Polygon, ViewportState } from "../../types";
import { worldToScreen, CANVAS_COLORS } from "../../utils";

interface SiteBoundaryLayerProps {
    polygon: Polygon;
    viewport: ViewportState;
    canvasHeight: number;
}

export function SiteBoundaryLayer({
    polygon,
    viewport,
    canvasHeight,
}: SiteBoundaryLayerProps) {
    if (polygon.points.length < 3) {
        return null;
    }

    // Convert world coordinates to screen coordinates
    const screenPoints = polygon.points.map((p) =>
        worldToScreen(p, viewport, canvasHeight)
    );

    // Create SVG path
    const pathData = screenPoints
        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
        .join(" ") + " Z";

    return (
        <g className="site-boundary-layer">
            <path
                d={pathData}
                fill={CANVAS_COLORS.siteBoundaryFill}
                stroke={CANVAS_COLORS.siteBoundary}
                strokeWidth={2}
                strokeLinejoin="round"
            />
        </g>
    );
}
