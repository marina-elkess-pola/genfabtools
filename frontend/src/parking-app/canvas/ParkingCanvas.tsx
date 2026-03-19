/**
 * GenFabTools Parking Engine - Parking Canvas
 *
 * 2D read-only rendering of parking layouts.
 * World coordinates must match backend coordinates.
 *
 * This canvas does NOT:
 * - Allow dragging or editing
 * - Compute geometry
 * - Snap to grid
 *
 * It only renders backend results.
 */

import React, { useRef, useEffect, useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useScenario } from "../state";
import {
    SiteBoundaryLayer,
    SetbackBoundaryLayer,
    ConstraintsLayer,
    StallsLayer,
    AislesLayer,
    RampsLayer,
    CoresLayer,
    ZonesLayer,
} from "./layers";
import { V2CanvasLayer } from "./layers/V2CanvasLayer";
import type { AisleTooltipData, ConstraintTooltipData } from "./layers";
import {
    calculateBounds,
    fitBoundsToViewport,
    CANVAS_COLORS,
    isDisplayablePolygon,
} from "../utils";
import type { Stall, Aisle, Ramp, VerticalCore, ParkingZone, ViewportState, Polygon, Point, Setbacks } from "../types";

// Default setbacks for rendering when not specified
const DEFAULT_SETBACKS: Setbacks = {
    north: 5.0,
    south: 5.0,
    east: 5.0,
    west: 5.0,
};

// =============================================================================
// Tooltip Style Constants (v1.1: Standardized across canvas)
// =============================================================================

const TOOLTIP_STYLE = {
    maxWidth: 180,
    padding: "px-2.5 py-1.5",
    fontSize: "text-[11px]",
    bg: "bg-gray-800",
    text: "text-white",
    secondary: "text-gray-300",
    tertiary: "text-gray-400",
} as const;

// Tooltip offset from element center (in pixels)
const TOOLTIP_OFFSET = 16;
// Margin from canvas edge for auto-flip
const CANVAS_EDGE_MARGIN = 10;

/**
 * Calculate tooltip position with auto-flip to prevent edge overflow.
 * Returns CSS positioning properties.
 */
function calculateTooltipPosition(
    screenX: number,
    screenY: number,
    canvasWidth: number,
    canvasHeight: number,
    tooltipWidth: number = TOOLTIP_STYLE.maxWidth,
    tooltipHeight: number = 60
): { left?: number; right?: number; top?: number; bottom?: number } {
    const result: { left?: number; right?: number; top?: number; bottom?: number } = {};

    // Horizontal positioning with flip
    const spaceOnRight = canvasWidth - screenX - TOOLTIP_OFFSET;
    const spaceOnLeft = screenX - TOOLTIP_OFFSET;

    if (spaceOnRight >= tooltipWidth + CANVAS_EDGE_MARGIN) {
        // Position to the right of element
        result.left = screenX + TOOLTIP_OFFSET;
    } else if (spaceOnLeft >= tooltipWidth + CANVAS_EDGE_MARGIN) {
        // Flip to the left
        result.left = screenX - TOOLTIP_OFFSET - tooltipWidth;
    } else {
        // Center horizontally if no space on either side
        result.left = Math.max(CANVAS_EDGE_MARGIN, Math.min(screenX - tooltipWidth / 2, canvasWidth - tooltipWidth - CANVAS_EDGE_MARGIN));
    }

    // Vertical positioning with flip
    const spaceAbove = screenY - TOOLTIP_OFFSET;
    const spaceBelow = canvasHeight - screenY - TOOLTIP_OFFSET;

    if (spaceAbove >= tooltipHeight + CANVAS_EDGE_MARGIN) {
        // Position above element
        result.top = screenY - TOOLTIP_OFFSET - tooltipHeight;
    } else if (spaceBelow >= tooltipHeight + CANVAS_EDGE_MARGIN) {
        // Flip to below
        result.top = screenY + TOOLTIP_OFFSET;
    } else {
        // Center vertically if no space
        result.top = Math.max(CANVAS_EDGE_MARGIN, Math.min(screenY - tooltipHeight / 2, canvasHeight - tooltipHeight - CANVAS_EDGE_MARGIN));
    }

    return result;
}

// =============================================================================
// Stall Tooltip Component (v1.1: Standardized styling)
// =============================================================================

interface StallTooltipProps {
    stall: Stall;
    mouseX: number;
    mouseY: number;
}

function StallTooltip({ stall, mouseX, mouseY }: StallTooltipProps) {
    // Calculate stall dimensions from geometry bounds
    const bounds = getPolygonBounds(stall.geometry);
    const width = Math.abs(bounds.maxX - bounds.minX);
    const depth = Math.abs(bounds.maxY - bounds.minY);

    // Calculate access aisle width if present
    let accessAisleWidth: number | null = null;
    if (stall.accessAisle) {
        const aisleBounds = getPolygonBounds(stall.accessAisle);
        accessAisleWidth = Math.abs(aisleBounds.maxX - aisleBounds.minX);
    }

    // Format stall type for display
    const stallTypeLabels: Record<string, string> = {
        standard: "Standard",
        compact: "Compact",
        ada: "ADA Accessible",
        ada_van: "ADA Van-Accessible",
    };
    const typeLabel = stallTypeLabels[stall.stallType] || stall.stallType;

    // Position tooltip offset from cursor
    const offsetX = 12;
    const offsetY = 12;

    return (
        <div
            className={`absolute pointer-events-none z-50 ${TOOLTIP_STYLE.bg} ${TOOLTIP_STYLE.text} ${TOOLTIP_STYLE.fontSize} leading-tight rounded shadow-lg ${TOOLTIP_STYLE.padding}`}
            style={{
                left: mouseX + offsetX,
                top: mouseY + offsetY,
                maxWidth: TOOLTIP_STYLE.maxWidth,
            }}
        >
            <div className="font-semibold">{typeLabel}</div>
            <div className={TOOLTIP_STYLE.secondary}>
                {width.toFixed(0)}' × {depth.toFixed(0)}'
            </div>
            {accessAisleWidth !== null && (
                <div className={`${TOOLTIP_STYLE.tertiary} text-[10px] mt-0.5`}>
                    + {accessAisleWidth.toFixed(0)}' access aisle
                </div>
            )}
        </div>
    );
}

// =============================================================================
// Aisle Tooltip Component (v1.1.1: Rendered in overlay with auto-flip)
// =============================================================================

interface AisleTooltipProps {
    aisle: AisleTooltipData;
    canvasWidth: number;
    canvasHeight: number;
}

function AisleTooltip({ aisle, canvasWidth, canvasHeight }: AisleTooltipProps) {
    const position = calculateTooltipPosition(
        aisle.screenX,
        aisle.screenY,
        canvasWidth,
        canvasHeight,
        TOOLTIP_STYLE.maxWidth,
        50
    );

    const directionLabel = aisle.direction === "two-way" ? "Two-Way" :
        aisle.direction === "one-way" ? "One-Way" : "Drive";

    return (
        <div
            className={`absolute pointer-events-none z-50 ${TOOLTIP_STYLE.bg} ${TOOLTIP_STYLE.text} ${TOOLTIP_STYLE.fontSize} leading-tight rounded shadow-lg ${TOOLTIP_STYLE.padding}`}
            style={{
                ...position,
                maxWidth: TOOLTIP_STYLE.maxWidth,
            }}
        >
            <div className="font-semibold text-gray-100">{directionLabel} Aisle</div>
            <div className={TOOLTIP_STYLE.secondary}>
                {aisle.width.toFixed(0)}' × {aisle.length.toFixed(0)}'
            </div>
        </div>
    );
}

// =============================================================================
// Constraint Tooltip Component (v1.1.1: Rendered in overlay with auto-flip)
// =============================================================================

interface ConstraintTooltipProps {
    constraint: ConstraintTooltipData;
    canvasWidth: number;
    canvasHeight: number;
}

function ConstraintTooltip({ constraint, canvasWidth, canvasHeight }: ConstraintTooltipProps) {
    const position = calculateTooltipPosition(
        constraint.screenX,
        constraint.screenY,
        canvasWidth,
        canvasHeight,
        TOOLTIP_STYLE.maxWidth,
        60
    );

    return (
        <div
            className={`absolute pointer-events-none z-50 ${TOOLTIP_STYLE.bg} ${TOOLTIP_STYLE.text} ${TOOLTIP_STYLE.fontSize} leading-tight rounded shadow-lg ${TOOLTIP_STYLE.padding}`}
            style={{
                ...position,
                maxWidth: TOOLTIP_STYLE.maxWidth,
            }}
        >
            <div className="flex items-center gap-1.5">
                <span
                    className="w-2 h-2 rounded-sm flex-shrink-0"
                    style={{ backgroundColor: constraint.color }}
                />
                <span className="font-semibold text-gray-100">{constraint.label}</span>
            </div>
            <div className={TOOLTIP_STYLE.secondary}>
                {constraint.width.toFixed(0)}' × {constraint.height.toFixed(0)}'
            </div>
            <div className={`${TOOLTIP_STYLE.tertiary} text-[10px]`}>
                {constraint.area.toFixed(0)} SF
            </div>
        </div>
    );
}

// =============================================================================
// Hit Testing Utilities
// =============================================================================

function getPolygonBounds(polygon: Polygon): { minX: number; minY: number; maxX: number; maxY: number } {
    if (!polygon.points || polygon.points.length === 0) {
        return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of polygon.points) {
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
    }
    return { minX, minY, maxX, maxY };
}

function screenToWorld(
    screenX: number,
    screenY: number,
    viewport: ViewportState,
    canvasHeight: number
): Point {
    // Convert screen coordinates to world coordinates
    // Account for pan and zoom
    const worldX = (screenX - viewport.panX) / viewport.zoom;
    // Y is flipped in SVG (0 at top), and we also apply viewport transform
    const worldY = (canvasHeight - screenY - viewport.panY) / viewport.zoom;
    return { x: worldX, y: worldY };
}

function isPointInBounds(
    point: Point,
    bounds: { minX: number; minY: number; maxX: number; maxY: number }
): boolean {
    return (
        point.x >= bounds.minX &&
        point.x <= bounds.maxX &&
        point.y >= bounds.minY &&
        point.y <= bounds.maxY
    );
}

function findStallAtPoint(stalls: Stall[], worldPoint: Point): Stall | null {
    // Simple bounds-based hit testing
    // Check in reverse order so top-rendered stalls are checked first
    for (let i = stalls.length - 1; i >= 0; i--) {
        const stall = stalls[i];
        const bounds = getPolygonBounds(stall.geometry);
        if (isPointInBounds(worldPoint, bounds)) {
            return stall;
        }
    }
    return null;
}

// =============================================================================
// Grid Component
// =============================================================================

interface GridProps {
    width: number;
    height: number;
    gridSize: number;
}

function Grid({ width, height, gridSize }: GridProps) {
    const lines: React.ReactNode[] = [];

    // Vertical lines
    for (let x = 0; x <= width; x += gridSize) {
        lines.push(
            <line
                key={`v-${x}`}
                x1={x}
                y1={0}
                x2={x}
                y2={height}
                stroke={CANVAS_COLORS.grid}
                strokeWidth={0.5}
            />
        );
    }

    // Horizontal lines
    for (let y = 0; y <= height; y += gridSize) {
        lines.push(
            <line
                key={`h-${y}`}
                x1={0}
                y1={y}
                x2={width}
                y2={y}
                stroke={CANVAS_COLORS.grid}
                strokeWidth={0.5}
            />
        );
    }

    return <g className="grid-layer">{lines}</g>;
}

// =============================================================================
// Empty State
// =============================================================================

interface EmptyStateProps {
    width: number;
    height: number;
}

function EmptyState({ width, height }: EmptyStateProps) {
    return (
        <g className="empty-state">
            <text
                x={width / 2}
                y={height / 2 - 20}
                textAnchor="middle"
                fill="#6B7280"
                fontSize="16"
                fontWeight="500"
            >
                Ready for input
            </text>
            <text
                x={width / 2}
                y={height / 2 + 8}
                textAnchor="middle"
                fill="#9CA3AF"
                fontSize="12"
            >
                Define a site boundary in the Input panel
            </text>
            <text
                x={width / 2}
                y={height / 2 + 28}
                textAnchor="middle"
                fill="#D1D5DB"
                fontSize="11"
            >
                then click Evaluate to generate parking layout
            </text>
        </g>
    );
}

// =============================================================================
// Level Selector (for structured parking)
// =============================================================================

interface LevelSelectorProps {
    levels: number;
    selected: number;
    onSelect: (level: number) => void;
}

function LevelSelector({ levels, selected, onSelect }: LevelSelectorProps) {
    if (levels <= 1) {
        return null;
    }

    return (
        <div className="absolute top-3 left-3 bg-white rounded shadow-md p-1 flex gap-1">
            {Array.from({ length: levels }, (_, i) => (
                <button
                    key={i}
                    onClick={() => onSelect(i)}
                    className={`px-2 py-1 text-xs font-medium rounded transition-colors ${selected === i
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                        }`}
                >
                    L{i + 1}
                </button>
            ))}
        </div>
    );
}

// =============================================================================
// Layer Visibility Controls (v1.1: Added color swatches and legend)
// =============================================================================

interface LayerControlsProps {
    visibility: Record<string, boolean>;
    onToggle: (layer: string) => void;
}

// Layer definitions with associated colors for visual identification
const LAYER_DEFINITIONS = [
    { key: "siteBoundary", label: "Site", color: "#111827", style: "solid" },
    { key: "constraints", label: "Constraints", color: "#DC2626", style: "solid" },
    { key: "stalls", label: "Stalls", color: "#334155", style: "solid" },
    { key: "aisles", label: "Aisles", color: "#E5E7EB", style: "solid" },
    { key: "ramps", label: "Ramps", color: "#9CA3AF", style: "solid" },
    { key: "cores", label: "Cores", color: "#6B7280", style: "solid" },
] as const;

// Stall type legend for expanded view
const STALL_LEGEND = [
    { label: "Standard", color: "#334155" },
    { label: "ADA", color: "#2563EB" },
    { label: "Van ADA", color: "#2563EB" },
] as const;

function LayerControls({ visibility, onToggle }: LayerControlsProps) {
    const [isCollapsed, setIsCollapsed] = React.useState(false);
    const [showLegend, setShowLegend] = React.useState(false);

    return (
        <div
            className="absolute left-3 bg-white/95 backdrop-blur-sm rounded-lg shadow-md flex flex-col border border-gray-200/50"
            style={{
                // Position above zoom indicator
                bottom: "48px",
                maxHeight: isCollapsed ? "auto" : "260px",
                minWidth: "130px",
            }}
        >
            {/* Fixed header with collapse toggle */}
            <button
                onClick={() => setIsCollapsed(!isCollapsed)}
                className="flex items-center justify-between gap-2 px-2.5 py-2 text-xs font-medium text-gray-600 hover:bg-gray-50 rounded-t-lg transition-colors cursor-pointer w-full border-b border-gray-100"
            >
                <span>Layers</span>
                <svg
                    className={`w-3 h-3 text-gray-400 transition-transform ${isCollapsed ? "rotate-180" : ""}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {/* Collapsible content */}
            {!isCollapsed && (
                <>
                    {/* Scrollable layer list */}
                    <div className="overflow-y-auto flex-1 px-2 pb-1" style={{ maxHeight: "120px" }}>
                        <div className="space-y-1">
                            {LAYER_DEFINITIONS.map(({ key, label, color }) => (
                                <label
                                    key={key}
                                    className="flex items-center gap-2 text-xs cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5 -mx-1"
                                >
                                    <input
                                        type="checkbox"
                                        checked={visibility[key] ?? true}
                                        onChange={() => onToggle(key)}
                                        className="w-3 h-3 rounded text-blue-600"
                                    />
                                    <span
                                        className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                                        style={{ backgroundColor: color }}
                                    />
                                    <span className="text-gray-700">{label}</span>
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* Stall Legend Toggle */}
                    <button
                        onClick={() => setShowLegend(!showLegend)}
                        className="mx-2 mb-1 px-1.5 py-0.5 text-[10px] text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded flex items-center gap-1"
                    >
                        <svg
                            className={`w-2.5 h-2.5 transition-transform ${showLegend ? "rotate-90" : ""}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        Stall Legend
                    </button>

                    {/* Stall Type Legend (collapsible) */}
                    {showLegend && (
                        <div className="mx-2 mb-1 px-2 py-1 bg-gray-50 rounded text-[10px]">
                            {STALL_LEGEND.map(({ label, color }) => (
                                <div key={label} className="flex items-center gap-1.5 py-0.5">
                                    <span
                                        className="w-2 h-2 rounded-sm flex-shrink-0"
                                        style={{ backgroundColor: color }}
                                    />
                                    <span className="text-gray-600">{label}</span>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Fixed footer */}
                    <div className="px-2 py-1 border-t border-gray-100 text-[10px] text-gray-400">
                        Read-only view
                    </div>
                </>
            )}
        </div>
    );
}

// =============================================================================
// Fit to View Button (v1.1: Added keyboard shortcut hint)
// =============================================================================

interface FitToViewButtonProps {
    onClick: () => void;
}

function FitToViewButton({ onClick }: FitToViewButtonProps) {
    return (
        <button
            onClick={onClick}
            className="absolute top-3 right-3 bg-white/95 backdrop-blur-sm rounded-lg shadow-md border border-gray-200/50 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-white hover:text-gray-800 active:bg-gray-50 transition-colors flex items-center gap-1.5"
            title="Fit drawing to view (reset zoom and pan)"
        >
            <svg
                className="w-3.5 h-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
                />
            </svg>
            Fit
        </button>
    );
}

// =============================================================================
// Zoom Controls (v1.1: Interactive zoom with presets)
// =============================================================================

interface ZoomControlsProps {
    zoom: number;
    onZoomChange: (newZoom: number) => void;
    onFitToView: () => void;
}

const ZOOM_PRESETS = [50, 100, 150, 200] as const;

function ZoomControls({ zoom, onZoomChange, onFitToView }: ZoomControlsProps) {
    const [showPresets, setShowPresets] = React.useState(false);

    const zoomPercent = Math.round(zoom * 100);

    const handleZoomIn = () => {
        const newZoom = Math.min(zoom * 1.25, 10);
        onZoomChange(newZoom);
    };

    const handleZoomOut = () => {
        const newZoom = Math.max(zoom / 1.25, 0.1);
        onZoomChange(newZoom);
    };

    const handlePreset = (preset: number) => {
        onZoomChange(preset / 100);
        setShowPresets(false);
    };

    return (
        <div className="absolute bottom-3 right-3 flex items-center gap-0.5">
            {/* Zoom preset menu */}
            {showPresets && (
                <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-md border border-gray-200/50 mr-1.5 flex flex-col overflow-hidden">
                    {ZOOM_PRESETS.map((preset) => (
                        <button
                            key={preset}
                            onClick={() => handlePreset(preset)}
                            className={`px-3 py-1.5 text-xs hover:bg-gray-100 transition-colors ${zoomPercent === preset ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600"
                                }`}
                        >
                            {preset}%
                        </button>
                    ))}
                    <button
                        onClick={() => { onFitToView(); setShowPresets(false); }}
                        className="px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 transition-colors border-t border-gray-100"
                    >
                        Fit
                    </button>
                </div>
            )}

            {/* Zoom controls group */}
            <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-md border border-gray-200/50 flex items-center overflow-hidden">
                {/* Zoom out button */}
                <button
                    onClick={handleZoomOut}
                    className="w-7 h-7 flex items-center justify-center text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
                    title="Zoom out"
                >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                    </svg>
                </button>

                {/* Zoom percentage (clickable for presets) */}
                <button
                    onClick={() => setShowPresets(!showPresets)}
                    className="px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 transition-colors min-w-[48px] text-center font-medium tabular-nums border-x border-gray-100"
                    title="Zoom presets"
                >
                    {zoomPercent}%
                </button>

                {/* Zoom in button */}
                <button
                    onClick={handleZoomIn}
                    className="w-7 h-7 flex items-center justify-center text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
                    title="Zoom in"
                >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                </button>
            </div>
        </div>
    );
}

// =============================================================================
// Navigation Help (v1.1: Keyboard/mouse shortcuts hint)
// =============================================================================

function NavigationHelp() {
    const [isVisible, setIsVisible] = React.useState(false);

    return (
        <div className="absolute bottom-12 right-3">
            <button
                onMouseEnter={() => setIsVisible(true)}
                onMouseLeave={() => setIsVisible(false)}
                onClick={() => setIsVisible(!isVisible)}
                className="bg-white/90 backdrop-blur-sm rounded-full w-5 h-5 flex items-center justify-center text-gray-400 hover:bg-white hover:text-gray-600 transition-colors shadow-sm text-[10px] font-medium border border-gray-200/50"
                title="Navigation help"
            >
                ?
            </button>

            {isVisible && (
                <div className="absolute bottom-7 right-0 bg-gray-800/95 backdrop-blur-sm text-white text-[10px] rounded-lg shadow-lg px-3 py-2.5 whitespace-nowrap">
                    <div className="font-medium text-gray-100 mb-2 text-[11px]">Navigation</div>
                    <div className="space-y-1.5 text-gray-300">
                        <div className="flex justify-between gap-6">
                            <span>Pan</span>
                            <span className="text-gray-400 font-mono">Drag</span>
                        </div>
                        <div className="flex justify-between gap-6">
                            <span>Zoom</span>
                            <span className="text-gray-400 font-mono">Scroll</span>
                        </div>
                        <div className="flex justify-between gap-6">
                            <span>Inspect</span>
                            <span className="text-gray-400 font-mono">Hover</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// =============================================================================
// Main Canvas Component
// =============================================================================

export function ParkingCanvas() {
    const { state, activeScenario, dispatch } = useScenario();
    const [searchParams] = useSearchParams();
    const isV2 = searchParams.get('v2') === '1';
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

    // Pan state for drag interaction
    const [isPanning, setIsPanning] = useState(false);
    const [panStart, setPanStart] = useState({ x: 0, y: 0 });
    const [viewportStart, setViewportStart] = useState({ panX: 0, panY: 0 });

    // Hover state for stall inspection
    const [hoveredStall, setHoveredStall] = useState<Stall | null>(null);
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

    // Hover state for aisle/constraint tooltips (lifted from layers for overlay rendering)
    const [hoveredAisle, setHoveredAisle] = useState<AisleTooltipData | null>(null);
    const [hoveredConstraint, setHoveredConstraint] = useState<ConstraintTooltipData | null>(null);

    // Handle container resize
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const observer = new ResizeObserver((entries) => {
            for (const entry of entries) {
                setDimensions({
                    width: entry.contentRect.width,
                    height: entry.contentRect.height,
                });
            }
        });

        observer.observe(container);
        return () => observer.disconnect();
    }, []);

    // ==========================================================================
    // V1 Auto-fit: ONLY runs when isV2 === false
    // Fits to raw site boundary (no setback adjustment)
    // ==========================================================================
    useEffect(() => {
        // HARD-DISABLE: Skip entirely when V2 mode is active
        if (isV2) return;
        if (!activeScenario?.siteBoundary) return;

        const siteBounds = calculateBounds(activeScenario.siteBoundary);

        const viewport = fitBoundsToViewport(
            siteBounds,
            dimensions.width,
            dimensions.height,
            60
        );

        dispatch({ type: "SET_VIEWPORT", payload: viewport });
    }, [activeScenario?.siteBoundary, dimensions, dispatch, isV2]);

    // ==========================================================================
    // V2 Auto-fit: ONLY runs when isV2 === true
    // Fits to v2Aisles polygon bounds (NOT site bounds, NOT buildable bounds)
    // ==========================================================================
    useEffect(() => {
        // HARD-DISABLE: Skip entirely when V1 mode is active
        if (!isV2) return;
        if (!activeScenario?.siteBoundary) return;

        // Get v2 aisle data from results
        const parkingResult = activeScenario?.result?.parkingResult;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const v2Aisles = (parkingResult as any)?.v2Aisles || [];

        // Compute bounds from v2Aisles polygons
        let v2Bounds: ReturnType<typeof calculateBounds> | null = null;
        if (v2Aisles.length > 0) {
            // Collect all aisle polygon points to compute combined bounds
            const allPoints: Point[] = [];
            for (const aisle of v2Aisles) {
                if (aisle.geometry?.points) {
                    allPoints.push(...aisle.geometry.points);
                }
            }
            if (allPoints.length > 0) {
                v2Bounds = calculateBounds({ points: allPoints });
            }
        }

        // Fallback to site bounds if no v2 aisle data yet
        const targetBounds = v2Bounds || calculateBounds(activeScenario.siteBoundary);

        const viewport = fitBoundsToViewport(
            targetBounds,
            dimensions.width,
            dimensions.height,
            60
        );

        dispatch({ type: "SET_VIEWPORT", payload: viewport });
    }, [activeScenario?.siteBoundary, activeScenario?.result, dimensions, dispatch, isV2]);

    // Extract data from scenario
    const { viewport, layerVisibility, selectedLevel } = state.canvasState;

    // ==========================================================================
    // Fit to View handler
    // v1: fits to raw site boundary
    // v2: fits to v2Aisles bounds (NOT site bounds)
    // ==========================================================================
    const handleFitToView = useCallback(() => {
        if (!activeScenario?.siteBoundary) return;

        const siteBounds = calculateBounds(activeScenario.siteBoundary);
        let targetBounds = siteBounds;

        if (isV2) {
            // V2: Fit to v2Aisles polygon bounds
            const parkingResult = activeScenario?.result?.parkingResult;
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const v2Aisles = (parkingResult as any)?.v2Aisles || [];
            if (v2Aisles.length > 0) {
                const allPoints: Point[] = [];
                for (const aisle of v2Aisles) {
                    if (aisle.geometry?.points) {
                        allPoints.push(...aisle.geometry.points);
                    }
                }
                if (allPoints.length > 0) {
                    targetBounds = calculateBounds({ points: allPoints });
                }
            }
        }

        const newViewport = fitBoundsToViewport(
            targetBounds,
            dimensions.width,
            dimensions.height,
            60
        );

        dispatch({ type: "SET_VIEWPORT", payload: newViewport });
    }, [activeScenario?.siteBoundary, activeScenario?.result, dimensions, dispatch, isV2]);

    // ==========================================================================
    // Zoom handler (mouse wheel / trackpad)
    // Uses native event listener with { passive: false } to allow preventDefault
    // ==========================================================================
    const handleWheel = useCallback(
        (e: WheelEvent) => {
            e.preventDefault();

            const container = containerRef.current;
            if (!container) return;

            const rect = container.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            // Determine zoom direction and factor
            // Normalize deltaY for different devices (trackpad vs mouse wheel)
            const delta = -e.deltaY;
            const zoomFactor = delta > 0 ? 1.1 : 0.9;

            // Calculate new zoom, clamped between 0.1 and 10
            const newZoom = Math.min(Math.max(viewport.zoom * zoomFactor, 0.1), 10);

            // Zoom towards mouse position
            // Calculate the world point under the mouse before zoom
            const worldX = (mouseX - viewport.panX) / viewport.zoom;
            const worldY = (mouseY - viewport.panY) / viewport.zoom;

            // Calculate new pan to keep the same world point under mouse
            const newPanX = mouseX - worldX * newZoom;
            const newPanY = mouseY - worldY * newZoom;

            dispatch({
                type: "SET_VIEWPORT",
                payload: { panX: newPanX, panY: newPanY, zoom: newZoom },
            });
        },
        [viewport, dispatch]
    );

    // Attach wheel listener with { passive: false } to allow preventDefault
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        container.addEventListener("wheel", handleWheel, { passive: false });
        return () => {
            container.removeEventListener("wheel", handleWheel);
        };
    }, [handleWheel]);

    // ==========================================================================
    // Pan handlers (click and drag)
    // ==========================================================================
    const handleMouseDown = useCallback(
        (e: React.MouseEvent<HTMLDivElement>) => {
            // Only pan with left mouse button
            if (e.button !== 0) return;

            setIsPanning(true);
            setPanStart({ x: e.clientX, y: e.clientY });
            setViewportStart({ panX: viewport.panX, panY: viewport.panY });
            // Clear hover when starting to pan
            setHoveredStall(null);

            // Prevent text selection during drag
            e.preventDefault();
        },
        [viewport.panX, viewport.panY]
    );

    // Need stalls for hover detection - get from extractedData
    // We'll move extractedData computation before this, or use a ref
    // For now, we'll create a ref to hold stalls for hover detection
    const stallsRef = useRef<Stall[]>([]);

    const handleMouseMove = useCallback(
        (e: React.MouseEvent<HTMLDivElement>) => {
            const container = containerRef.current;
            if (!container) return;

            const rect = container.getBoundingClientRect();
            const screenX = e.clientX - rect.left;
            const screenY = e.clientY - rect.top;

            // Update mouse position for tooltip
            setMousePosition({ x: screenX, y: screenY });

            if (isPanning) {
                // Panning mode - update viewport
                const deltaX = e.clientX - panStart.x;
                const deltaY = e.clientY - panStart.y;

                // Note: Y delta is inverted because screen Y is down but world Y is up
                // When user drags down (positive deltaY), they want drawing to move down
                // which means panY should DECREASE (since worldToScreen subtracts panY)
                dispatch({
                    type: "SET_VIEWPORT",
                    payload: {
                        panX: viewportStart.panX + deltaX,
                        panY: viewportStart.panY - deltaY,  // Invert Y for CAD-style pan
                        zoom: viewport.zoom,
                    },
                });
                return;
            }

            // Hover detection mode - find stall under cursor
            const worldPoint = screenToWorld(screenX, screenY, viewport, dimensions.height);
            const stall = findStallAtPoint(stallsRef.current, worldPoint);
            setHoveredStall(stall);
        },
        [isPanning, panStart, viewportStart, viewport, dimensions.height, dispatch]
    );

    const handleMouseUp = useCallback(() => {
        setIsPanning(false);
    }, []);

    const handleMouseLeave = useCallback(() => {
        setIsPanning(false);
        setHoveredStall(null);
        setHoveredAisle(null);
        setHoveredConstraint(null);
    }, []);

    // Extract stalls, aisles, etc. from results
    // CRITICAL: V1 and V2 paths are COMPLETELY SEPARATE based on isV2 flag
    const extractedData = useMemo(() => {
        const empty = {
            stalls: [] as Stall[],
            aisles: [] as Aisle[],
            ramps: [] as Ramp[],
            cores: [] as VerticalCore[],
            zones: [] as ParkingZone[],
            levelCount: 0,
            isV2Active: false,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            v2StallsRaw: [] as any[],
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            v2AislesRaw: [] as any[],
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            v2DebugGeometry: null as any,
        };

        const parkingResult = activeScenario?.result?.parkingResult;
        if (!parkingResult) {
            return empty;
        }

        const result = parkingResult;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const resultAny = result as any;

        // ======================================================================
        // V2 MODE: Extract ONLY v2 geometry, ignore v1 paths entirely
        // ======================================================================
        if (isV2) {
            const v2StallsRaw = resultAny.v2Stalls || [];
            const v2AislesRaw = resultAny.v2Aisles || [];
            const v2DebugGeometry = resultAny.v2DebugGeometry || null;

            return {
                stalls: [], // V1 stalls NOT extracted when isV2
                aisles: [], // V1 aisles NOT extracted when isV2
                ramps: [],
                cores: [],
                zones: result.type === "surface" ? (result.zones || []) : [],
                levelCount: 1,
                isV2Active: v2StallsRaw.length > 0,
                v2StallsRaw,
                v2AislesRaw,
                v2DebugGeometry,
            };
        }

        // ======================================================================
        // V1 MODE: Extract ONLY v1 geometry, ignore v2 paths entirely
        // ======================================================================

        if (result.type === "surface") {
            const stalls: Stall[] = [];
            const aisles: Aisle[] = [];

            // V1 path: extract from bays
            for (const bay of result.bays) {
                stalls.push(...bay.stalls);
                aisles.push(bay.aisle);
            }

            return {
                stalls,
                aisles,
                ramps: [],
                cores: [],
                zones: result.zones || [],
                levelCount: 1,
                isV2Active: false,
                v2StallsRaw: [], // V2 data NOT extracted when !isV2
                v2AislesRaw: [], // V2 data NOT extracted when !isV2
                v2DebugGeometry: null,
            };
        } else {
            // Structured parking (V1 only)
            const stalls: Stall[] = [];
            const aisles: Aisle[] = [];

            const level = result.levels[selectedLevel];
            if (level) {
                for (const bay of level.bays) {
                    stalls.push(...bay.stalls);
                    aisles.push(bay.aisle);
                }
            }

            return {
                stalls,
                aisles,
                ramps: result.ramps,
                cores: result.cores,
                zones: [],
                levelCount: result.levels.length,
                isV2Active: false,
                v2StallsRaw: [],
                v2AislesRaw: [],
                v2DebugGeometry: null,
            };
        }
    }, [activeScenario?.result, selectedLevel, isV2]);

    // Keep stallsRef in sync with extractedData for hover detection
    useEffect(() => {
        stallsRef.current = extractedData.stalls;
    }, [extractedData.stalls]);

    // Handle level selection
    const handleLevelSelect = useCallback(
        (level: number) => {
            dispatch({ type: "SET_SELECTED_LEVEL", payload: level });
        },
        [dispatch]
    );

    // Handle layer visibility toggle
    const handleLayerToggle = useCallback(
        (layer: string) => {
            dispatch({
                type: "SET_LAYER_VISIBILITY",
                payload: { [layer]: !layerVisibility[layer as keyof typeof layerVisibility] },
            });
        },
        [dispatch, layerVisibility]
    );

    const hasSite = activeScenario && isDisplayablePolygon(activeScenario.siteBoundary);

    // Determine cursor style based on state
    const getCursorStyle = (): string => {
        if (isPanning) return "cursor-grabbing";
        if (hoveredStall) return "cursor-pointer";
        return "cursor-crosshair";
    };

    return (
        <div
            ref={containerRef}
            className={`relative w-full h-full bg-gray-50 overflow-hidden ${getCursorStyle()}`}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
        >
            <svg
                width={dimensions.width}
                height={dimensions.height}
                className="block pointer-events-none"
            >
                {/* Background */}
                <rect
                    width={dimensions.width}
                    height={dimensions.height}
                    fill={CANVAS_COLORS.background}
                />

                {/* Grid */}
                <Grid
                    width={dimensions.width}
                    height={dimensions.height}
                    gridSize={50}
                />

                {/* Empty State */}
                {!hasSite && (
                    <EmptyState
                        width={dimensions.width}
                        height={dimensions.height}
                    />
                )}

                {/* Render Layers (in order) */}
                {hasSite && activeScenario && (
                    <>
                        {/* 1. Site Boundary */}
                        {layerVisibility.siteBoundary && (
                            <SiteBoundaryLayer
                                polygon={activeScenario.siteBoundary!}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}

                        {/* 1b. Setback/Parkable Boundary (dashed inner line) */}
                        {layerVisibility.siteBoundary && (
                            <SetbackBoundaryLayer
                                siteBoundary={activeScenario.siteBoundary!}
                                setbacks={activeScenario.parkingConfig.setbacks || DEFAULT_SETBACKS}
                                uniformSetback={activeScenario.parkingConfig.uniformSetback !== false}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}

                        {/* 2. Zones (background) */}
                        {layerVisibility.zones && extractedData.zones.length > 0 && (
                            <ZonesLayer
                                zones={extractedData.zones}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}

                        {/* 3. Constraints */}
                        {layerVisibility.constraints &&
                            activeScenario.constraintsEnabled && (
                                <ConstraintsLayer
                                    constraints={activeScenario.constraints}
                                    viewport={viewport}
                                    canvasHeight={dimensions.height}
                                    onConstraintHover={setHoveredConstraint}
                                />
                            )}

                        {/* 4. Aisles (V1 ONLY - HARD-DISABLED when isV2) */}
                        {layerVisibility.aisles && !isV2 && (
                            <AislesLayer
                                aisles={extractedData.aisles}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                                onAisleHover={setHoveredAisle}
                            />
                        )}

                        {/* 5. Stalls (V1 ONLY - HARD-DISABLED when isV2) */}
                        {layerVisibility.stalls && !isV2 && (
                            <StallsLayer
                                stalls={extractedData.stalls}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}

                        {/* 6. Ramps */}
                        {layerVisibility.ramps && (
                            <RampsLayer
                                ramps={extractedData.ramps}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}

                        {/* 7. Cores */}
                        {layerVisibility.cores && (
                            <CoresLayer
                                cores={extractedData.cores}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}

                        {/* V2 ONLY: V2 Canvas Layer (angled parking) */}
                        {/* Renders when isV2 is true AND v2 data is available */}
                        {isV2 && extractedData.v2StallsRaw.length > 0 && (
                            <V2CanvasLayer
                                v2Stalls={extractedData.v2StallsRaw}
                                v2Aisles={extractedData.v2AislesRaw}
                                v2DebugGeometry={extractedData.v2DebugGeometry}
                                viewport={viewport}
                                canvasHeight={dimensions.height}
                            />
                        )}
                    </>
                )}
            </svg>

            {/* Level Selector (for structured parking) */}
            {extractedData.levelCount > 1 && (
                <LevelSelector
                    levels={extractedData.levelCount}
                    selected={selectedLevel}
                    onSelect={handleLevelSelect}
                />
            )}

            {/* Layer Controls */}
            {hasSite && (
                <LayerControls
                    visibility={layerVisibility as unknown as Record<string, boolean>}
                    onToggle={handleLayerToggle}
                />
            )}

            {/* Fit to View Button */}
            {hasSite && <FitToViewButton onClick={handleFitToView} />}

            {/* ================================================================
                Canvas Tooltips (v1.1.1: All rendered in overlay layer with auto-flip)
                These render ABOVE the SVG geometry to prevent overlap.
            ================================================================ */}

            {/* Stall Hover Tooltip */}
            {hoveredStall && !isPanning && (
                <StallTooltip
                    stall={hoveredStall}
                    mouseX={mousePosition.x}
                    mouseY={mousePosition.y}
                />
            )}

            {/* Aisle Hover Tooltip */}
            {hoveredAisle && !isPanning && (
                <AisleTooltip
                    aisle={hoveredAisle}
                    canvasWidth={dimensions.width}
                    canvasHeight={dimensions.height}
                />
            )}

            {/* Constraint Hover Tooltip */}
            {hoveredConstraint && !isPanning && (
                <ConstraintTooltip
                    constraint={hoveredConstraint}
                    canvasWidth={dimensions.width}
                    canvasHeight={dimensions.height}
                />
            )}

            {/* Drawing orientation indicator (top-left, non-interactive) */}
            <div
                className="absolute top-3 left-3 bg-white/95 rounded-md shadow-sm p-2 pointer-events-none select-none"
                title="Drawing orientation (not true geographic north)"
            >
                <div
                    className="grid text-[11px] leading-none"
                    style={{
                        gridTemplateColumns: 'auto auto auto',
                        gridTemplateRows: 'auto auto auto',
                        gap: '1px',
                    }}
                >
                    {/* Row 1: _ N _ */}
                    <span className="w-3 h-3"></span>
                    <span className="w-3 h-3 flex items-center justify-center font-semibold text-gray-700">N</span>
                    <span className="w-3 h-3"></span>
                    {/* Row 2: W • E */}
                    <span className="w-3 h-3 flex items-center justify-center font-medium text-gray-500">W</span>
                    <span className="w-3 h-3 flex items-center justify-center text-gray-300 text-[8px]">•</span>
                    <span className="w-3 h-3 flex items-center justify-center font-medium text-gray-500">E</span>
                    {/* Row 3: _ S _ */}
                    <span className="w-3 h-3"></span>
                    <span className="w-3 h-3 flex items-center justify-center font-medium text-gray-500">S</span>
                    <span className="w-3 h-3"></span>
                </div>
            </div>

            {/* v1.1: Interactive Zoom Controls */}
            <ZoomControls
                zoom={viewport.zoom}
                onZoomChange={(newZoom) => {
                    dispatch({
                        type: "SET_VIEWPORT",
                        payload: { ...viewport, zoom: newZoom },
                    });
                }}
                onFitToView={handleFitToView}
            />

            {/* v1.1: Navigation Help */}
            <NavigationHelp />
        </div>
    );
}
