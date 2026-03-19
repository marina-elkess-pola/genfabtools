/**
 * GenFabTools Parking Engine - Utility Functions
 *
 * Helper functions for coordinate transforms, colors, and formatting.
 * These do NOT perform parking calculations - only display helpers.
 */

import type {
    Point,
    Polygon,
    Bounds,
    ConstraintType,
    ViewportState,
} from "../types";

// =============================================================================
// Constraint Type Colors
// =============================================================================

export const CONSTRAINT_COLORS: Record<ConstraintType, string> = {
    COLUMN: "#DC2626",
    CORE: "#DC2626",
    WALL: "#DC2626",
    MEP_ROOM: "#DC2626",
    SHAFT: "#DC2626",
    VOID: "#DC2626",
    UNKNOWN: "#DC2626",
};

export const CONSTRAINT_LABELS: Record<ConstraintType, string> = {
    COLUMN: "Column",
    CORE: "Core",
    WALL: "Wall",
    MEP_ROOM: "MEP Room",
    SHAFT: "Shaft",
    VOID: "Void",
    UNKNOWN: "Unknown",
};

// =============================================================================
// Stall Type Colors
// =============================================================================

export const STALL_COLORS = {
    standard: "#334155",
    compact: "#334155",
    ada: "#2563EB",
    ada_van: "#2563EB",
} as const;

// =============================================================================
// Zone Type Colors
// =============================================================================

export const ZONE_COLORS = {
    RECTANGULAR: "rgba(76, 175, 80, 0.1)",
    REMNANT: "rgba(255, 193, 7, 0.1)",
    UNUSABLE: "rgba(244, 67, 54, 0.1)",
    VOID: "rgba(158, 158, 158, 0.1)",
} as const;

// =============================================================================
// Canvas Rendering Colors
// =============================================================================

export const CANVAS_COLORS = {
    siteBoundary: "#111827",
    siteBoundaryFill: "rgba(17, 24, 39, 0.03)",
    aisle: "#E5E7EB",
    aisleFill: "rgba(229, 231, 235, 0.6)",
    ramp: "#9CA3AF",
    rampFill: "rgba(156, 163, 175, 0.3)",
    core: "#6B7280",
    coreFill: "rgba(107, 114, 128, 0.3)",
    grid: "#E5E7EB",
    background: "#F9FAFB",
} as const;

// =============================================================================
// Geometry Utilities (Display Only)
// =============================================================================

/**
 * Calculate bounding box of a polygon.
 * Used for viewport fitting - NOT for parking calculations.
 */
export function calculateBounds(polygon: Polygon): Bounds {
    if (polygon.points.length === 0) {
        return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
    }

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    for (const point of polygon.points) {
        minX = Math.min(minX, point.x);
        minY = Math.min(minY, point.y);
        maxX = Math.max(maxX, point.x);
        maxY = Math.max(maxY, point.y);
    }

    return { minX, minY, maxX, maxY };
}

/**
 * Calculate bounds that contain multiple polygons.
 */
export function calculateCombinedBounds(polygons: Polygon[]): Bounds {
    if (polygons.length === 0) {
        return { minX: 0, minY: 0, maxX: 100, maxY: 100 };
    }

    const allBounds = polygons.map(calculateBounds);

    return {
        minX: Math.min(...allBounds.map((b) => b.minX)),
        minY: Math.min(...allBounds.map((b) => b.minY)),
        maxX: Math.max(...allBounds.map((b) => b.maxX)),
        maxY: Math.max(...allBounds.map((b) => b.maxY)),
    };
}

/**
 * Calculate buildable bounds after applying setbacks.
 * This is the usable area for parking after setback margins.
 */
export function calculateBuildableBounds(
    siteBounds: Bounds,
    setbacks?: { north: number; south: number; east: number; west: number }
): Bounds {
    if (!setbacks) {
        return siteBounds;
    }

    return {
        minX: siteBounds.minX + setbacks.west,
        minY: siteBounds.minY + setbacks.south,
        maxX: siteBounds.maxX - setbacks.east,
        maxY: siteBounds.maxY - setbacks.north,
    };
}

// =============================================================================
// Coordinate Transforms (Display Only)
// =============================================================================

/**
 * Transform world coordinates to screen coordinates.
 * Uses viewport state for pan and zoom.
 */
export function worldToScreen(
    point: Point,
    viewport: ViewportState,
    canvasHeight: number
): Point {
    // Flip Y axis (world Y up, screen Y down)
    const flippedY = canvasHeight - point.y * viewport.zoom - viewport.panY;
    return {
        x: point.x * viewport.zoom + viewport.panX,
        y: flippedY,
    };
}

/**
 * Transform screen coordinates to world coordinates.
 */
export function screenToWorld(
    point: Point,
    viewport: ViewportState,
    canvasHeight: number
): Point {
    // Reverse the Y flip
    const worldY = (canvasHeight - point.y - viewport.panY) / viewport.zoom;
    return {
        x: (point.x - viewport.panX) / viewport.zoom,
        y: worldY,
    };
}

/**
 * Calculate viewport to fit bounds with padding.
 */
export function fitBoundsToViewport(
    bounds: Bounds,
    canvasWidth: number,
    canvasHeight: number,
    padding: number = 40
): ViewportState {
    const boundsWidth = bounds.maxX - bounds.minX;
    const boundsHeight = bounds.maxY - bounds.minY;

    if (boundsWidth <= 0 || boundsHeight <= 0) {
        return { panX: 0, panY: 0, zoom: 1 };
    }

    const availableWidth = canvasWidth - padding * 2;
    const availableHeight = canvasHeight - padding * 2;

    const zoomX = availableWidth / boundsWidth;
    const zoomY = availableHeight / boundsHeight;
    const zoom = Math.min(zoomX, zoomY, 2); // Cap at 2x zoom

    // Center the bounds
    const panX = padding + (availableWidth - boundsWidth * zoom) / 2 - bounds.minX * zoom;
    const panY = padding + (availableHeight - boundsHeight * zoom) / 2 - bounds.minY * zoom;

    return { panX, panY, zoom };
}

// =============================================================================
// Formatting Utilities
// =============================================================================

/**
 * Format number with commas.
 */
export function formatNumber(value: number, decimals: number = 0): string {
    return value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

/**
 * Format area in square feet.
 */
export function formatArea(sqft: number): string {
    return `${formatNumber(sqft, 0)} SF`;
}

/**
 * Format efficiency as SF/stall.
 */
export function formatEfficiency(sfPerStall: number): string {
    return `${formatNumber(sfPerStall, 0)} SF/stall`;
}

/**
 * Format percentage.
 */
export function formatPercent(value: number, decimals: number = 1): string {
    return `${formatNumber(value, decimals)}%`;
}

/**
 * Format dimension in feet.
 */
export function formatDimension(feet: number): string {
    return `${formatNumber(feet, 1)}'`;
}

// =============================================================================
// Validation Utilities (Display Only)
// =============================================================================

/**
 * Check if a polygon has valid points for display.
 * Does NOT validate parking rules - only display requirements.
 */
export function isDisplayablePolygon(polygon: Polygon | null): boolean {
    if (!polygon) return false;
    if (polygon.points.length < 3) return false;
    return true;
}

/**
 * Check if a file has a supported extension.
 */
export function isSupportedFile(
    filename: string,
    extensions: string[]
): boolean {
    const ext = filename.toLowerCase().split(".").pop() || "";
    return extensions.includes(ext);
}

export const BOUNDARY_FILE_EXTENSIONS = ["dxf"];
export const CONSTRAINT_FILE_EXTENSIONS = ["dxf", "dwg", "rvt"];

// =============================================================================
// ID Utilities
// =============================================================================

/**
 * Generate a unique ID.
 */
export function generateId(prefix: string = "id"): string {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}
