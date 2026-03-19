/**
 * GenFabTools Parking Engine - Aisles Layer
 *
 * Renders drive aisles with hover tooltips.
 * Read-only rendering - no editing.
 *
 * v1.1: Added hover tooltip showing aisle dimensions
 * v1.1.1: Refactored to lift tooltip state to parent for overlay rendering
 */

import React, { useCallback } from "react";
import type { Aisle, ViewportState, Polygon, Point } from "../../types";
import { worldToScreen, CANVAS_COLORS } from "../../utils";

/** Tooltip data for hovered aisle - exported for use in ParkingCanvas */
export interface AisleTooltipData {
    width: number;
    length: number;
    direction: "two-way" | "one-way" | "unknown";
    screenX: number;
    screenY: number;
}

interface AislesLayerProps {
    aisles: readonly Aisle[];
    viewport: ViewportState;
    canvasHeight: number;
    /** Callback when hovering an aisle - parent renders tooltip */
    onAisleHover?: (data: AisleTooltipData | null) => void;
}

/**
 * Calculate dimensions from polygon geometry.
 */
function getPolygonDimensions(polygon: Polygon): { width: number; length: number } {
    const pts = polygon.points;
    if (pts.length < 3) return { width: 0, length: 0 };

    const xs = pts.map(p => p.x);
    const ys = pts.map(p => p.y);
    const dx = Math.max(...xs) - Math.min(...xs);
    const dy = Math.max(...ys) - Math.min(...ys);

    // Width is the narrower dimension (aisle width), length is the longer (drive length)
    return {
        width: Math.min(dx, dy),
        length: Math.max(dx, dy),
    };
}

/**
 * Get centroid of polygon for tooltip positioning.
 */
function getPolygonCentroid(polygon: Polygon): Point {
    const pts = polygon.points;
    if (pts.length === 0) return { x: 0, y: 0 };
    const sumX = pts.reduce((acc, p) => acc + p.x, 0);
    const sumY = pts.reduce((acc, p) => acc + p.y, 0);
    return { x: sumX / pts.length, y: sumY / pts.length };
}

/**
 * Determine aisle direction based on width.
 * Two-way = 24 ft, One-way = 15 ft
 */
function getAisleDirection(width: number): "two-way" | "one-way" | "unknown" {
    if (Math.abs(width - 24) < 1) return "two-way";
    if (Math.abs(width - 15) < 1) return "one-way";
    return "unknown";
}

export function AislesLayer({
    aisles,
    viewport,
    canvasHeight,
    onAisleHover,
}: AislesLayerProps) {
    const handleMouseEnter = useCallback((aisle: Aisle) => {
        if (!onAisleHover) return;
        const { geometry } = aisle;
        const dims = getPolygonDimensions(geometry);
        const centroid = getPolygonCentroid(geometry);
        const screenPos = worldToScreen(centroid, viewport, canvasHeight);
        const direction = getAisleDirection(dims.width);

        onAisleHover({
            width: dims.width,
            length: dims.length,
            direction,
            screenX: screenPos.x,
            screenY: screenPos.y,
        });
    }, [viewport, canvasHeight, onAisleHover]);

    const handleMouseLeave = useCallback(() => {
        onAisleHover?.(null);
    }, [onAisleHover]);

    if (aisles.length === 0) {
        return null;
    }

    return (
        <g className="aisles-layer">
            {aisles.map((aisle) => {
                const { geometry, id } = aisle;

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
                        fill={CANVAS_COLORS.aisleFill}
                        stroke={CANVAS_COLORS.aisle}
                        strokeWidth={1}
                        strokeLinejoin="round"
                        style={{ pointerEvents: "all" }}
                        onMouseEnter={() => handleMouseEnter(aisle)}
                        onMouseLeave={handleMouseLeave}
                    />
                );
            })}
        </g>
    );
}
