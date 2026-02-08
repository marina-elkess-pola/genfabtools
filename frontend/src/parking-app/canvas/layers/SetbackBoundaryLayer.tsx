/**
 * GenFabTools Parking Engine - Setback Boundary Layer
 *
 * Renders the parkable envelope (site boundary minus setbacks).
 * Shows where parking stalls can be placed.
 * Read-only visualization - no editing.
 */

import React from "react";
import type { Polygon, ViewportState, Setbacks } from "../../types";
import { worldToScreen } from "../../utils";

interface SetbackBoundaryLayerProps {
    siteBoundary: Polygon;
    setbacks: Setbacks;
    uniformSetback: boolean;
    viewport: ViewportState;
    canvasHeight: number;
}

/**
 * Compute the parkable boundary by insetting the site boundary by the setback amounts.
 * For rectangular sites (v1), this is a simple inset operation.
 * North = top (max Y), South = bottom (min Y), East = right (max X), West = left (min X)
 */
function computeParkableBoundary(
    siteBoundary: Polygon,
    setbacks: Setbacks
): Polygon {
    if (siteBoundary.points.length < 4) {
        return siteBoundary;
    }

    // Get bounding box of site
    const points = siteBoundary.points;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of points) {
        minX = Math.min(minX, p.x);
        minY = Math.min(minY, p.y);
        maxX = Math.max(maxX, p.x);
        maxY = Math.max(maxY, p.y);
    }

    // Apply directional setbacks
    // West = left edge (minX), East = right edge (maxX)
    // South = bottom edge (minY), North = top edge (maxY)
    const newMinX = minX + setbacks.west;
    const newMaxX = maxX - setbacks.east;
    const newMinY = minY + setbacks.south;
    const newMaxY = maxY - setbacks.north;

    // Check if setbacks are too large (would create invalid polygon)
    if (newMinX >= newMaxX || newMinY >= newMaxY) {
        // Return empty polygon if setbacks consume entire site
        return { points: [] };
    }

    // Create inset rectangular boundary (CCW for SVG)
    return {
        points: [
            { x: newMinX, y: newMinY },
            { x: newMaxX, y: newMinY },
            { x: newMaxX, y: newMaxY },
            { x: newMinX, y: newMaxY },
        ],
    };
}

export function SetbackBoundaryLayer({
    siteBoundary,
    setbacks,
    uniformSetback,
    viewport,
    canvasHeight,
}: SetbackBoundaryLayerProps) {
    // Check if any setback is non-zero
    const hasSetback = setbacks.north > 0 || setbacks.south > 0 ||
        setbacks.east > 0 || setbacks.west > 0;

    if (!hasSetback || siteBoundary.points.length < 3) {
        return null;
    }

    // Compute the parkable boundary
    const parkableBoundary = computeParkableBoundary(siteBoundary, setbacks);

    if (parkableBoundary.points.length < 3) {
        return null;
    }

    // Convert site boundary to screen coordinates for the setback fill
    const siteScreenPoints = siteBoundary.points.map((p) =>
        worldToScreen(p, viewport, canvasHeight)
    );
    const sitePathData = siteScreenPoints
        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
        .join(" ") + " Z";

    // Convert parkable boundary to screen coordinates
    const parkableScreenPoints = parkableBoundary.points.map((p) =>
        worldToScreen(p, viewport, canvasHeight)
    );
    const parkablePathData = parkableScreenPoints
        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
        .join(" ") + " Z";

    // Create combined path for setback zone fill (site boundary minus parkable boundary)
    // Using even-odd fill rule to create the "donut" effect
    const setbackZonePath = sitePathData + " " + parkablePathData;

    return (
        <g className="setback-boundary-layer">
            {/* Setback zone fill (very subtle) */}
            <path
                d={setbackZonePath}
                fill="rgba(100, 100, 100, 0.06)"
                fillRule="evenodd"
                stroke="none"
            />
            {/* Parkable boundary outline (dashed) */}
            <path
                d={parkablePathData}
                fill="none"
                stroke="#888888"
                strokeWidth={1}
                strokeDasharray="4 3"
                strokeLinejoin="round"
                opacity={0.6}
            />
        </g>
    );
}
