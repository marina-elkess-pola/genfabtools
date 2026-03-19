/**
 * GenFabTools Parking Engine - Stalls Layer
 *
 * Renders parking stalls colored by type.
 * ADA stalls render with their access aisle shown separately.
 * Includes hover tooltip for geometry verification.
 * Read-only rendering - no editing.
 */

import React, { useState, useCallback } from "react";
import type { Stall, ViewportState, Polygon, Point } from "../../types";
import { worldToScreen, STALL_COLORS } from "../../utils";

/** Access aisle styling - diagonal stripes pattern */
const ACCESS_AISLE_COLOR = "#2563EB";
const ACCESS_AISLE_STRIPE_COLOR = "#FFFFFF";

interface StallsLayerProps {
    stalls: readonly Stall[];
    viewport: ViewportState;
    canvasHeight: number;
}

/** Tooltip data for hovered stall */
interface StallTooltipData {
    stallType: string;
    stallWidth: number;
    stallDepth: number;
    accessAisleWidth?: number;
    totalWidth?: number;
    screenX: number;
    screenY: number;
}

/**
 * Calculate dimensions from polygon geometry.
 * Uses actual geometry, not constants.
 */
function getPolygonDimensions(polygon: Polygon): { width: number; depth: number } {
    const pts = polygon.points;
    if (pts.length < 3) return { width: 0, depth: 0 };

    const xs = pts.map(p => p.x);
    const ys = pts.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    // Width is the smaller dimension (stall width), depth is the larger (stall length)
    const dx = maxX - minX;
    const dy = maxY - minY;
    return {
        width: Math.min(dx, dy),
        depth: Math.max(dx, dy),
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
 * Creates SVG path from polygon points.
 */
function createPathData(
    polygon: Polygon,
    viewport: ViewportState,
    canvasHeight: number
): string {
    const screenPoints = polygon.points.map((p) =>
        worldToScreen(p, viewport, canvasHeight)
    );
    return (
        screenPoints
            .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
            .join(" ") + " Z"
    );
}

export function StallsLayer({
    stalls,
    viewport,
    canvasHeight,
}: StallsLayerProps) {
    const [hoveredStall, setHoveredStall] = useState<StallTooltipData | null>(null);

    const handleMouseEnter = useCallback((stall: Stall) => {
        const { geometry, stallType, accessAisle } = stall;
        const dims = getPolygonDimensions(geometry);
        const centroid = getPolygonCentroid(geometry);
        const screenPos = worldToScreen(centroid, viewport, canvasHeight);

        const tooltipData: StallTooltipData = {
            stallType: stallType === "ada_van" ? "ADA Van" :
                stallType === "ada" ? "ADA" :
                    stallType === "compact" ? "Compact" : "Standard",
            stallWidth: dims.width,
            stallDepth: dims.depth,
            screenX: screenPos.x,
            screenY: screenPos.y,
        };

        // Add access aisle info for ADA stalls
        if (accessAisle && accessAisle.points.length >= 3) {
            const aisleDims = getPolygonDimensions(accessAisle);
            tooltipData.accessAisleWidth = aisleDims.width;
            tooltipData.totalWidth = dims.width + aisleDims.width;
        }

        setHoveredStall(tooltipData);
    }, [viewport, canvasHeight]);

    const handleMouseLeave = useCallback(() => {
        setHoveredStall(null);
    }, []);

    if (stalls.length === 0) {
        return null;
    }

    // Generate unique pattern ID for this render
    const patternId = "access-aisle-stripes";

    return (
        <g className="stalls-layer">
            {/* Define stripe pattern for access aisles */}
            <defs>
                <pattern
                    id={patternId}
                    patternUnits="userSpaceOnUse"
                    width="6"
                    height="6"
                    patternTransform="rotate(45)"
                >
                    <rect
                        width="6"
                        height="6"
                        fill={ACCESS_AISLE_COLOR}
                    />
                    <line
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="6"
                        stroke={ACCESS_AISLE_STRIPE_COLOR}
                        strokeWidth="2"
                    />
                </pattern>
            </defs>

            {stalls.map((stall) => {
                const { geometry, stallType, id, accessAisle } = stall;

                if (geometry.points.length < 3) {
                    return null;
                }

                const stallPath = createPathData(geometry, viewport, canvasHeight);
                const color = STALL_COLORS[stallType];

                return (
                    <g key={id}>
                        {/* Render access aisle first (behind stall) */}
                        {accessAisle && accessAisle.points.length >= 3 && (
                            <path
                                d={createPathData(accessAisle, viewport, canvasHeight)}
                                fill={`url(#${patternId})`}
                                stroke={ACCESS_AISLE_COLOR}
                                strokeWidth={0.5}
                                strokeLinejoin="round"
                                opacity={0.9}
                            />
                        )}

                        {/* Render stall with hover interaction */}
                        <path
                            d={stallPath}
                            fill={color}
                            stroke="#ffffff"
                            strokeWidth={0.5}
                            strokeLinejoin="round"
                            opacity={0.8}
                            style={{ cursor: "pointer" }}
                            onMouseEnter={() => handleMouseEnter(stall)}
                            onMouseLeave={handleMouseLeave}
                        />
                    </g>
                );
            })}

            {/* Tooltip - rendered as foreignObject for HTML styling */}
            {hoveredStall && (
                <foreignObject
                    x={hoveredStall.screenX + 10}
                    y={hoveredStall.screenY - 60}
                    width="180"
                    height="100"
                    style={{ pointerEvents: "none", overflow: "visible" }}
                >
                    <div
                        style={{
                            background: "rgba(15, 23, 42, 0.95)",
                            color: "#fff",
                            padding: "8px 12px",
                            borderRadius: "6px",
                            fontSize: "12px",
                            fontFamily: "system-ui, sans-serif",
                            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                            whiteSpace: "nowrap",
                            lineHeight: 1.4,
                        }}
                    >
                        <div style={{ fontWeight: 600, marginBottom: "4px", color: "#60a5fa" }}>
                            {hoveredStall.stallType} Stall
                        </div>
                        <div>
                            <span style={{ color: "#94a3b8" }}>Size: </span>
                            {hoveredStall.stallWidth.toFixed(0)}' × {hoveredStall.stallDepth.toFixed(0)}'
                        </div>
                        {hoveredStall.accessAisleWidth && (
                            <>
                                <div>
                                    <span style={{ color: "#94a3b8" }}>Access Aisle: </span>
                                    {hoveredStall.accessAisleWidth.toFixed(0)}' wide
                                </div>
                                <div style={{ fontWeight: 500, color: "#4ade80" }}>
                                    Total Width: {hoveredStall.totalWidth?.toFixed(0)}'
                                </div>
                            </>
                        )}
                    </div>
                </foreignObject>
            )}
        </g>
    );
}
