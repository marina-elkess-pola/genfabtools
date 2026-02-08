/**
 * DEV-ONLY: 60° Aisle Overlay Layer
 *
 * Renders v2 aisles with distinctive styling for visual verification:
 * - Cyan fill with higher opacity
 * - Direction arrows showing one-way flow (from backend)
 * - Debug border around aisle bounds
 *
 * Arrow rendering uses BACKEND-PROVIDED circulation data:
 * - TWO_WAY: No arrows (bidirectional traffic)
 * - ONE_WAY_FORWARD: Arrow in centerline direction
 * - ONE_WAY_REVERSE: Arrow opposite to centerline
 *
 * This layer is ONLY shown when in DEV mode AND v2 geometry is present.
 * REMOVE BEFORE PUBLIC RELEASE.
 */

import React from "react";
import type { Aisle, ViewportState, Point, CirculationMode, FlowDirection } from "../../types";
import { worldToScreen } from "../../utils";

// DEV overlay colors - highly visible for debugging
const DEV_AISLE_COLORS = {
    fill: "rgba(0, 255, 255, 0.35)",      // Cyan, 35% opacity
    stroke: "#00FFFF",                     // Cyan stroke
    strokeWidth: 2,
    arrowFill: "#00FFFF",                  // Cyan arrow
    arrowStroke: "#004444",                // Dark teal outline
    twoWayFill: "rgba(128, 255, 128, 0.25)", // Light green for two-way
    twoWayStroke: "#00FF00",               // Green for two-way
};

interface DevAisleOverlayProps {
    aisles: readonly Aisle[];
    viewport: ViewportState;
    canvasHeight: number;
    /** Whether v2 mode is active */
    isV2Active: boolean;
}

/**
 * Calculate arrow position and direction from BACKEND-PROVIDED flow direction.
 * Does NOT infer direction from geometry - uses authoritative backend data.
 */
function getAisleArrowFromBackend(
    aisle: Aisle,
    viewport: ViewportState,
    canvasHeight: number
): { cx: number; cy: number; angle: number; length: number } | null {
    const { geometry, flowDirection, circulation } = aisle;
    const pts = geometry.points;
    if (pts.length < 3) return null;

    // TWO_WAY aisles get no arrow
    if (circulation === "TWO_WAY" || !flowDirection) {
        return null;
    }

    // Get bounding box for centroid
    const xs = pts.map(p => p.x);
    const ys = pts.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    // Centroid in world coords
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    // Convert to screen coords
    const screenCenter = worldToScreen({ x: cx, y: cy }, viewport, canvasHeight);

    // Arrow angle from BACKEND flow direction (authoritative)
    // flowDirection is in world coords (Y-up), screen is Y-down
    // atan2 gives angle from positive X axis
    const worldAngle = Math.atan2(flowDirection.dy, flowDirection.dx);
    // Convert to screen angle (flip Y)
    const screenAngle = Math.atan2(-flowDirection.dy, flowDirection.dx);
    const angleDegrees = (screenAngle * 180) / Math.PI;

    // Arrow length based on aisle width
    const dx = maxX - minX;
    const dy = maxY - minY;
    const arrowWorldLength = Math.min(dx, dy) * 0.4;
    const arrowScreenLength = arrowWorldLength * viewport.zoom;

    return {
        cx: screenCenter.x,
        cy: screenCenter.y,
        angle: angleDegrees,
        length: Math.min(arrowScreenLength, 30), // Cap at 30px
    };
}

/**
 * Arrow SVG path.
 */
function ArrowMarker({ cx, cy, angle, length }: {
    cx: number;
    cy: number;
    angle: number;
    length: number;
}) {
    // Arrow head size
    const headSize = Math.min(length * 0.4, 8);

    // Arrow shaft (line from center going in 'angle' direction)
    const rad = (angle * Math.PI) / 180;
    const halfLen = length / 2;

    const x1 = cx - halfLen * Math.cos(rad);
    const y1 = cy - halfLen * Math.sin(rad);
    const x2 = cx + halfLen * Math.cos(rad);
    const y2 = cy + halfLen * Math.sin(rad);

    // Arrow head points
    const headAngle1 = rad + (150 * Math.PI) / 180;
    const headAngle2 = rad - (150 * Math.PI) / 180;
    const hx1 = x2 + headSize * Math.cos(headAngle1);
    const hy1 = y2 + headSize * Math.sin(headAngle1);
    const hx2 = x2 + headSize * Math.cos(headAngle2);
    const hy2 = y2 + headSize * Math.sin(headAngle2);

    return (
        <g className="dev-aisle-arrow">
            {/* Shaft */}
            <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={DEV_AISLE_COLORS.arrowStroke}
                strokeWidth={3}
            />
            <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={DEV_AISLE_COLORS.arrowFill}
                strokeWidth={1.5}
            />
            {/* Head */}
            <polygon
                points={`${x2},${y2} ${hx1},${hy1} ${hx2},${hy2}`}
                fill={DEV_AISLE_COLORS.arrowFill}
                stroke={DEV_AISLE_COLORS.arrowStroke}
                strokeWidth={1}
            />
        </g>
    );
}

export function DevAisleOverlay({
    aisles,
    viewport,
    canvasHeight,
    isV2Active,
}: DevAisleOverlayProps) {
    // DEBUG INSTRUMENTATION — REMOVE BEFORE PRODUCTION
    console.warn("[V2 DEBUG] DevAisleOverlay (V2) RENDERED");

    // Only render in DEV mode with v2 active
    if (!isV2Active || aisles.length === 0) {
        return null;
    }

    // Count one-way vs two-way for badge
    const oneWayCount = aisles.filter(a => a.circulation !== "TWO_WAY").length;
    const twoWayCount = aisles.length - oneWayCount;

    return (
        <g className="dev-aisle-overlay">
            {/* DEV badge */}
            <text
                x={10}
                y={20}
                fill="#00FFFF"
                fontSize={12}
                fontFamily="monospace"
                fontWeight="bold"
            >
                DEV: v2 Aisles ({aisles.length}) | 1-way: {oneWayCount} | 2-way: {twoWayCount}
            </text>

            {aisles.map((aisle) => {
                const { geometry, id, circulation } = aisle;

                if (geometry.points.length < 3) {
                    return null;
                }

                // Determine styling based on circulation mode
                const isTwoWay = circulation === "TWO_WAY";
                const fillColor = isTwoWay ? DEV_AISLE_COLORS.twoWayFill : DEV_AISLE_COLORS.fill;
                const strokeColor = isTwoWay ? DEV_AISLE_COLORS.twoWayStroke : DEV_AISLE_COLORS.stroke;

                // Convert to screen coords
                const screenPoints = geometry.points.map((p) =>
                    worldToScreen(p, viewport, canvasHeight)
                );

                const pathData =
                    screenPoints
                        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
                        .join(" ") + " Z";

                // Get arrow from BACKEND data (returns null for TWO_WAY)
                const arrow = getAisleArrowFromBackend(aisle, viewport, canvasHeight);

                return (
                    <g key={`dev-aisle-${id}`}>
                        {/* Aisle fill - different color for TWO_WAY */}
                        <path
                            d={pathData}
                            fill={fillColor}
                            stroke={strokeColor}
                            strokeWidth={DEV_AISLE_COLORS.strokeWidth}
                            strokeDasharray={isTwoWay ? "8,4" : "4,2"}
                            strokeLinejoin="round"
                        />
                        {/* Direction arrow (only for ONE_WAY, uses backend flowDirection) */}
                        {arrow && (
                            <ArrowMarker
                                cx={arrow.cx}
                                cy={arrow.cy}
                                angle={arrow.angle}
                                length={arrow.length}
                            />
                        )}
                    </g>
                );
            })}
        </g>
    );
}
