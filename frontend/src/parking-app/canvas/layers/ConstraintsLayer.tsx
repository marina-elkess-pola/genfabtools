/**
 * GenFabTools Parking Engine - Constraints Layer
 *
 * Renders imported constraint polygons colored by type.
 * Read-only rendering - no editing.
 *
 * v1.1: Added hover tooltip showing constraint type and dimensions
 * v1.1.1: Refactored to lift tooltip state to parent for overlay rendering
 */

import React, { useCallback } from "react";
import type { ImportedConstraint, ViewportState, ConstraintType, Polygon, Point } from "../../types";
import { worldToScreen, CONSTRAINT_COLORS, CONSTRAINT_LABELS } from "../../utils";

/** Tooltip data for hovered constraint - exported for use in ParkingCanvas */
export interface ConstraintTooltipData {
    type: ConstraintType;
    label: string;
    width: number;
    height: number;
    area: number;
    color: string;
    screenX: number;
    screenY: number;
}

interface ConstraintsLayerProps {
    constraints: readonly ImportedConstraint[];
    viewport: ViewportState;
    canvasHeight: number;
    /** Callback when hovering a constraint - parent renders tooltip */
    onConstraintHover?: (data: ConstraintTooltipData | null) => void;
}

/**
 * Calculate dimensions from polygon geometry.
 */
function getPolygonBounds(polygon: Polygon): { width: number; height: number; area: number } {
    const pts = polygon.points;
    if (pts.length < 3) return { width: 0, height: 0, area: 0 };

    const xs = pts.map(p => p.x);
    const ys = pts.map(p => p.y);
    const width = Math.max(...xs) - Math.min(...xs);
    const height = Math.max(...ys) - Math.min(...ys);

    // Calculate polygon area using shoelace formula
    let area = 0;
    for (let i = 0; i < pts.length; i++) {
        const j = (i + 1) % pts.length;
        area += pts[i].x * pts[j].y;
        area -= pts[j].x * pts[i].y;
    }
    area = Math.abs(area) / 2;

    return { width, height, area };
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

export function ConstraintsLayer({
    constraints,
    viewport,
    canvasHeight,
    onConstraintHover,
}: ConstraintsLayerProps) {
    const handleMouseEnter = useCallback((constraint: ImportedConstraint) => {
        if (!onConstraintHover) return;
        const { geometry, constraintType } = constraint;
        const bounds = getPolygonBounds(geometry);
        const centroid = getPolygonCentroid(geometry);
        const screenPos = worldToScreen(centroid, viewport, canvasHeight);
        const color = CONSTRAINT_COLORS[constraintType];
        const label = CONSTRAINT_LABELS[constraintType];

        onConstraintHover({
            type: constraintType,
            label,
            width: bounds.width,
            height: bounds.height,
            area: bounds.area,
            color,
            screenX: screenPos.x,
            screenY: screenPos.y,
        });
    }, [viewport, canvasHeight, onConstraintHover]);

    const handleMouseLeave = useCallback(() => {
        onConstraintHover?.(null);
    }, [onConstraintHover]);

    if (constraints.length === 0) {
        return null;
    }

    return (
        <g className="constraints-layer">
            {constraints.map((constraint) => {
                const { geometry, constraintType, id } = constraint;

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

                const color = CONSTRAINT_COLORS[constraintType];
                const fillColor = `${color}40`; // 25% opacity

                return (
                    <path
                        key={id}
                        d={pathData}
                        fill={fillColor}
                        stroke={color}
                        strokeWidth={1.5}
                        strokeLinejoin="round"
                        style={{ pointerEvents: "all" }}
                        onMouseEnter={() => handleMouseEnter(constraint)}
                        onMouseLeave={handleMouseLeave}
                    />
                );
            })}
        </g>
    );
}
