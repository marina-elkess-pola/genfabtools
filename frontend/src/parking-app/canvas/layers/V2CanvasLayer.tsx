/**
 * V2CanvasLayer - DEV ONLY
 *
 * Dedicated rendering layer for v2 parking geometry (60° angled parking).
 * Does NOT reuse v1 StallsLayer/AislesLayer logic.
 *
 * Renders geometry EXACTLY as received from backend:
 * - Stall polygons: parallelograms at 60° angles
 * - Aisle polygons: rectangles with optional direction arrows
 *
 * No axis-alignment assumptions. No rotation in frontend.
 */

import React from "react";
import type { ViewportState, Point } from "../../types";
import { worldToScreen } from "../../utils";

// =============================================================================
// Props
// =============================================================================

interface V2Stall {
    readonly id: string;
    readonly geometry: { readonly points: readonly Point[] };
    readonly angle?: number;
}

interface V2Aisle {
    readonly id: string;
    readonly geometry: { readonly points: readonly Point[] };
    readonly centerline?: {
        readonly start: Point;
        readonly end: Point;
    };
    readonly circulation?: "TWO_WAY" | "ONE_WAY_FORWARD" | "ONE_WAY_REVERSE";
    readonly width?: number;
}

interface V2DebugGeometry {
    // Circulation-first debug geometry
    readonly loop_polyline?: readonly [number, number][];
    readonly aisle_arrows?: readonly [[number, number], [number, number]][];
    readonly stall_normals?: readonly [[number, number], [number, number]][];
    readonly u_turn_arcs?: readonly [number, number, number][]; // [cx, cy, radius]
    // Loop polygon as outer + inner ring for actual geometry rendering
    readonly loop_polygon_outer?: readonly [number, number][];
    readonly loop_polygon_inner?: readonly [number, number][];
    // Aisle width and circulation mode for reference
    readonly aisle_width?: number;
    readonly circulation_mode?: "ONE_WAY" | "TWO_WAY";
    // Legacy spine-based (fallback)
    readonly spine_polyline?: readonly [number, number][];
    readonly aisle_centerlines?: readonly [[number, number], [number, number]][];
}

interface V2CanvasLayerProps {
    v2Stalls: readonly V2Stall[];
    v2Aisles: readonly V2Aisle[];
    v2DebugGeometry?: V2DebugGeometry | null;
    viewport: ViewportState;
    canvasHeight: number;
}

// =============================================================================
// Colors
// =============================================================================

const STALL_FILL = "#334155";
const STALL_STROKE = "#1E293B";
const AISLE_FILL = "#E5E7EB";
const AISLE_STROKE = "#D1D5DB";
const LOOP_POLYGON_FILL = "#E5E7EB";
const LOOP_POLYGON_STROKE = "#D1D5DB";
const ARROW_COLOR = "#6B7280";

// =============================================================================
// Helpers
// =============================================================================

/**
 * Create SVG path from polygon vertices.
 * No assumptions about shape - uses points as-is.
 */
function createPolygonPath(
    points: readonly Point[],
    viewport: ViewportState,
    canvasHeight: number
): string {
    if (points.length < 3) return "";

    const screenPoints = points.map((p) =>
        worldToScreen(p, viewport, canvasHeight)
    );

    const pathParts = screenPoints.map((p, i) =>
        i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`
    );
    pathParts.push("Z");

    return pathParts.join(" ");
}

/**
 * Create SVG path for a ring-shaped polygon (outer ring with inner hole).
 * This is used for the actual circulation loop polygon.
 * Uses evenodd fill-rule to create the hole.
 */
function createRingPath(
    outerPoints: readonly [number, number][],
    innerPoints: readonly [number, number][],
    viewport: ViewportState,
    canvasHeight: number
): string {
    if (outerPoints.length < 3) return "";

    // Convert outer ring to screen coordinates
    const screenOuter = outerPoints.map(([x, y]) =>
        worldToScreen({ x, y }, viewport, canvasHeight)
    );

    // Start with outer ring (clockwise)
    const parts: string[] = [];
    parts.push(
        ...screenOuter.map((p, i) =>
            i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`
        )
    );
    parts.push("Z");

    // Add inner ring (counter-clockwise for hole)
    if (innerPoints.length >= 3) {
        const screenInner = innerPoints.map(([x, y]) =>
            worldToScreen({ x, y }, viewport, canvasHeight)
        );
        // Reverse inner ring for evenodd fill to work
        const reversedInner = [...screenInner].reverse();
        parts.push(
            ...reversedInner.map((p, i) =>
                i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`
            )
        );
        parts.push("Z");
    }

    return parts.join(" ");
}

/**
 * Create arrow path for one-way aisle.
 * Arrow points from start to end of centerline.
 */
function createArrowPath(
    start: Point,
    end: Point,
    viewport: ViewportState,
    canvasHeight: number
): string {
    const screenStart = worldToScreen(start, viewport, canvasHeight);
    const screenEnd = worldToScreen(end, viewport, canvasHeight);

    // Calculate midpoint of centerline for arrow position
    const midX = (screenStart.x + screenEnd.x) / 2;
    const midY = (screenStart.y + screenEnd.y) / 2;

    // Direction vector
    const dx = screenEnd.x - screenStart.x;
    const dy = screenEnd.y - screenStart.y;
    const len = Math.sqrt(dx * dx + dy * dy);

    if (len < 1) return "";

    // Normalize
    const nx = dx / len;
    const ny = dy / len;

    // Arrow size (in screen pixels)
    const arrowLen = 12;
    const arrowWidth = 6;

    // Arrow tip at midpoint + offset in direction
    const tipX = midX + nx * arrowLen / 2;
    const tipY = midY + ny * arrowLen / 2;

    // Arrow base points (perpendicular to direction)
    const baseX = midX - nx * arrowLen / 2;
    const baseY = midY - ny * arrowLen / 2;

    const leftX = baseX - ny * arrowWidth;
    const leftY = baseY + nx * arrowWidth;

    const rightX = baseX + ny * arrowWidth;
    const rightY = baseY - nx * arrowWidth;

    return `M ${tipX} ${tipY} L ${leftX} ${leftY} L ${rightX} ${rightY} Z`;
}

// =============================================================================
// Component
// =============================================================================

export function V2CanvasLayer({
    v2Stalls,
    v2Aisles,
    v2DebugGeometry,
    viewport,
    canvasHeight,
}: V2CanvasLayerProps): React.ReactElement {
    return (
        <g className="v2-canvas-layer">
            {/* Render aisles first (behind stalls) */}
            {/* PRIORITY: Use loop_polygon_outer/inner when available (actual geometry) */}
            {/* Otherwise fall back to v2Aisles individual rectangles */}
            <g className="v2-aisles">
                {v2DebugGeometry?.loop_polygon_outer && v2DebugGeometry.loop_polygon_outer.length >= 3 ? (
                    // Render ACTUAL loop polygon (ring shape with correct aisle width)
                    <g className="v2-loop-polygon">
                        <path
                            d={createRingPath(
                                v2DebugGeometry.loop_polygon_outer,
                                v2DebugGeometry.loop_polygon_inner || [],
                                viewport,
                                canvasHeight
                            )}
                            fill={LOOP_POLYGON_FILL}
                            stroke={LOOP_POLYGON_STROKE}
                            strokeWidth={1}
                            fillRule="evenodd"
                            opacity={0.85}
                        />
                    </g>
                ) : (
                    // Fallback: render individual aisle rectangles from v2Aisles
                    v2Aisles.map((aisle) => {
                        const path = createPolygonPath(
                            aisle.geometry.points,
                            viewport,
                            canvasHeight
                        );

                        if (!path) return null;

                        // Determine if we should draw an arrow
                        const showArrow =
                            aisle.centerline &&
                            aisle.circulation &&
                            aisle.circulation !== "TWO_WAY";

                        // Arrow direction based on circulation mode
                        let arrowPath = "";
                        if (showArrow && aisle.centerline) {
                            const { start, end } = aisle.centerline;
                            if (aisle.circulation === "ONE_WAY_FORWARD") {
                                arrowPath = createArrowPath(start, end, viewport, canvasHeight);
                            } else if (aisle.circulation === "ONE_WAY_REVERSE") {
                                arrowPath = createArrowPath(end, start, viewport, canvasHeight);
                            }
                        }

                        return (
                            <g key={aisle.id}>
                                <path
                                    d={path}
                                    fill={AISLE_FILL}
                                    stroke={AISLE_STROKE}
                                    strokeWidth={0.5}
                                    opacity={0.7}
                                />
                                {arrowPath && (
                                    <path
                                        d={arrowPath}
                                        fill={ARROW_COLOR}
                                        stroke="none"
                                        opacity={0.8}
                                    />
                                )}
                            </g>
                        );
                    })
                )}
            </g>

            {/* Render stalls on top */}
            <g className="v2-stalls">
                {v2Stalls.map((stall) => {
                    const path = createPolygonPath(
                        stall.geometry.points,
                        viewport,
                        canvasHeight
                    );

                    if (!path) return null;

                    return (
                        <path
                            key={stall.id}
                            d={path}
                            fill={STALL_FILL}
                            stroke={STALL_STROKE}
                            strokeWidth={0.5}
                            strokeLinejoin="round"
                            opacity={0.8}
                        />
                    );
                })}
            </g>
        </g>
    );
}

export default V2CanvasLayer;
