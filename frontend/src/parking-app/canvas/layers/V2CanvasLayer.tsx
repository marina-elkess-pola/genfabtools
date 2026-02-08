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

const STALL_FILL = "#32CD32";      // Lime green for angled stalls (more visible)
const STALL_STROKE = "#006400";    // Dark green stroke
const AISLE_FILL = "#B0C4DE";      // Light steel blue for aisles
const AISLE_STROKE = "#4682B4";    // Steel blue stroke
const LOOP_POLYGON_FILL = "#C4D7E8";  // Actual loop polygon fill (slightly darker)
const LOOP_POLYGON_STROKE = "#5A7A99"; // Loop polygon stroke
const ARROW_COLOR = "#333333";
const SPINE_COLOR = "#FF6600";     // Orange for circulation loop centerline debug
const CENTERLINE_COLOR = "#9933FF"; // Purple for aisle arrows
const NORMAL_COLOR = "#FF0066";    // Magenta for stall normals
const UTURN_COLOR = "#00CCFF";     // Cyan for U-turn arcs

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
    // DEV PROOF LOG — REMOVE BEFORE PRODUCTION
    console.log("🎨 V2CanvasLayer RENDERING", {
        stallCount: v2Stalls?.length ?? 0,
        aisleCount: v2Aisles?.length ?? 0,
        hasDebugGeometry: !!v2DebugGeometry,
        firstStall: v2Stalls?.[0] ? {
            id: v2Stalls[0].id,
            angle: v2Stalls[0].angle,
            pointCount: v2Stalls[0].geometry?.points?.length ?? 0,
            points: v2Stalls[0].geometry?.points,
        } : null,
    });

    // Helper to create loop polyline path (prefer loop_polyline, fallback to spine_polyline)
    const createLoopPath = (): string => {
        const polyline = v2DebugGeometry?.loop_polyline ?? v2DebugGeometry?.spine_polyline;
        if (!polyline || polyline.length < 2) {
            return "";
        }
        const screenPoints = polyline.map(([x, y]) =>
            worldToScreen({ x, y }, viewport, canvasHeight)
        );
        return screenPoints.map((p, i) =>
            i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`
        ).join(" ");
    };

    // Get the polyline for rendering check
    const loopPolyline = v2DebugGeometry?.loop_polyline ?? v2DebugGeometry?.spine_polyline;
    const aisleArrows = v2DebugGeometry?.aisle_arrows ?? v2DebugGeometry?.aisle_centerlines;
    const hasLoopPolygon = v2DebugGeometry?.loop_polygon_outer && v2DebugGeometry.loop_polygon_outer.length >= 3;
    const aisleWidth = v2DebugGeometry?.aisle_width;
    const circMode = v2DebugGeometry?.circulation_mode;

    return (
        <g className="v2-canvas-layer">
            {/* DEV DEBUG: Visible indicator that V2 layer is rendering */}
            <rect x="10" y="10" width="280" height="40" fill="rgba(50,205,50,0.9)" stroke="#006400" strokeWidth="2" />
            <text x="20" y="35" fill="#006400" fontSize="14" fontWeight="bold">
                {`V2: ${v2Stalls?.length ?? 0} stalls | ${circMode ?? "?"}: ${aisleWidth ?? "?"}ft${hasLoopPolygon ? " (poly)" : ""}`}
            </text>

            {/* Debug: Circulation Loop Centerline (thick orange line) - for debug only */}
            {loopPolyline && loopPolyline.length >= 2 && (
                <path
                    d={createLoopPath()}
                    fill="none"
                    stroke={SPINE_COLOR}
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeDasharray="8,4"
                    opacity={0.6}
                />
            )}

            {/* Debug: U-Turn Arcs (cyan circles) */}
            {v2DebugGeometry?.u_turn_arcs?.map(([cx, cy, radius], i) => {
                const center = worldToScreen({ x: cx, y: cy }, viewport, canvasHeight);
                const screenRadius = radius * viewport.zoom;
                return (
                    <circle
                        key={`uturn-${i}`}
                        cx={center.x}
                        cy={center.y}
                        r={screenRadius}
                        fill="none"
                        stroke={UTURN_COLOR}
                        strokeWidth={2}
                        strokeDasharray="4,2"
                        opacity={0.7}
                    />
                );
            })}

            {/* Debug: Aisle Direction Arrows (purple lines with arrowheads) */}
            {aisleArrows?.map((arrow, i) => {
                const [[x1, y1], [x2, y2]] = arrow;
                const start = worldToScreen({ x: x1, y: y1 }, viewport, canvasHeight);
                const end = worldToScreen({ x: x2, y: y2 }, viewport, canvasHeight);
                // Create arrowhead for direction
                const dx = end.x - start.x;
                const dy = end.y - start.y;
                const len = Math.sqrt(dx * dx + dy * dy);
                if (len < 1) return null;
                const nx = dx / len;
                const ny = dy / len;
                const headLen = 6;
                const headWidth = 3;
                return (
                    <g key={`aisle-arrow-${i}`}>
                        <line
                            x1={start.x}
                            y1={start.y}
                            x2={end.x}
                            y2={end.y}
                            stroke={CENTERLINE_COLOR}
                            strokeWidth={2}
                            opacity={0.8}
                        />
                        <polygon
                            points={`
                                ${end.x},${end.y}
                                ${end.x - headLen * nx - headWidth * ny},${end.y - headLen * ny + headWidth * nx}
                                ${end.x - headLen * nx + headWidth * ny},${end.y - headLen * ny - headWidth * nx}
                            `}
                            fill={CENTERLINE_COLOR}
                            opacity={0.8}
                        />
                    </g>
                );
            })}

            {/* Debug: Stall Normals (magenta arrows) */}
            {v2DebugGeometry?.stall_normals?.map((arrow, i) => {
                const [[x1, y1], [x2, y2]] = arrow;
                const start = worldToScreen({ x: x1, y: y1 }, viewport, canvasHeight);
                const end = worldToScreen({ x: x2, y: y2 }, viewport, canvasHeight);
                // Create arrowhead
                const dx = end.x - start.x;
                const dy = end.y - start.y;
                const len = Math.sqrt(dx * dx + dy * dy);
                if (len < 1) return null;
                const nx = dx / len;
                const ny = dy / len;
                const headLen = 4;
                const headWidth = 2;
                return (
                    <g key={`normal-${i}`}>
                        <line
                            x1={start.x}
                            y1={start.y}
                            x2={end.x}
                            y2={end.y}
                            stroke={NORMAL_COLOR}
                            strokeWidth={1.5}
                            opacity={0.7}
                        />
                        <polygon
                            points={`
                                ${end.x},${end.y}
                                ${end.x - headLen * nx - headWidth * ny},${end.y - headLen * ny + headWidth * nx}
                                ${end.x - headLen * nx + headWidth * ny},${end.y - headLen * ny - headWidth * nx}
                            `}
                            fill={NORMAL_COLOR}
                            opacity={0.7}
                        />
                    </g>
                );
            })}

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
                        {/* Display aisle width for verification */}
                        {v2DebugGeometry.aisle_width && (
                            <text
                                x={worldToScreen({ x: v2DebugGeometry.loop_polygon_outer[0][0], y: v2DebugGeometry.loop_polygon_outer[0][1] }, viewport, canvasHeight).x + 5}
                                y={worldToScreen({ x: v2DebugGeometry.loop_polygon_outer[0][0], y: v2DebugGeometry.loop_polygon_outer[0][1] }, viewport, canvasHeight).y - 5}
                                fill="#333"
                                fontSize="10"
                            >
                                {`${v2DebugGeometry.circulation_mode || "?"}: ${v2DebugGeometry.aisle_width} ft`}
                            </text>
                        )}
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
                            opacity={0.85}
                        />
                    );
                })}
            </g>
        </g>
    );
}

export default V2CanvasLayer;
