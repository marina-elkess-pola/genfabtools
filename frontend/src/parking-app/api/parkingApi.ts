/**
 * GenFabTools Parking Engine - API Integration
 *
 * Single evaluation endpoint for parking layout generation.
 * The frontend sends scenario input and receives complete results.
 * No geometry computation happens in the frontend.
 */

import type {
    EvaluateRequest,
    EvaluateResponse,
    EvaluationResult,
    Polygon,
    ParkingConfig,
    ImportedConstraint,
    DxfImportResult,
    ConstraintImportResult,
} from "../types";

// =============================================================================
// Configuration
// =============================================================================

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL || "/api";
const PARKING_API = `${API_BASE_URL}/parking`;

// Dev mode flag
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const IS_DEV = (import.meta as any).env?.DEV ?? false;

// =============================================================================
// DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
// v2 engine feature flag: if URL contains ?v2=1, enable v2 mode
// =============================================================================
function isV2Enabled(): boolean {
    if (typeof window === 'undefined') return false;
    const params = new URLSearchParams(window.location.search);
    return params.get('v2') === '1';
}

function getV2Flags(): Record<string, unknown> {
    if (!isV2Enabled()) return {};
    // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
    // Note: angle is now passed from parkingConfig.stallAngle
    const flags = {
        useV2: true,
        allowAngledParking: true,
        recoverResidual: true,
    };
    if (IS_DEV) {
        console.log('[V2 FLAGS] getV2Flags() returning:', flags);
    }
    return flags;
}
// =============================================================================

// =============================================================================
// Error Types
// =============================================================================

export class ParkingApiError extends Error {
    constructor(
        message: string,
        public readonly statusCode?: number,
        public readonly details?: unknown
    ) {
        super(message);
        this.name = "ParkingApiError";
    }
}

// =============================================================================
// API Client
// =============================================================================

async function apiRequest<T>(
    endpoint: string,
    options: RequestInit = {}
): Promise<T> {
    const url = `${PARKING_API}${endpoint}`;

    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        let errorDetails: unknown;
        try {
            errorDetails = await response.json();
        } catch {
            errorDetails = await response.text();
        }
        throw new ParkingApiError(
            `API request failed: ${response.statusText}`,
            response.status,
            errorDetails
        );
    }

    return response.json();
}

// =============================================================================
// Parking Evaluation API
// =============================================================================

/**
 * Evaluate a parking scenario.
 *
 * Sends site boundary, configuration, and constraints to the backend.
 * Receives complete layout geometry and metrics.
 *
 * The frontend does NOT:
 * - Compute stall positions
 * - Validate geometry
 * - Optimize layouts
 *
 * All intelligence lives in the backend.
 */
export async function evaluateParkingScenario(
    siteBoundary: Polygon,
    parkingConfig: ParkingConfig,
    constraints?: readonly ImportedConstraint[]
): Promise<EvaluationResult> {
    // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
    const v2Flags = getV2Flags();

    // Get stallAngle from config (default to 90 if not set)
    const stallAngle = parkingConfig.stallAngle ?? 90;

    // Circulation mode is now controlled by UI based on angle:
    // - 90° → TWO_WAY (required)
    // - 45°/60° → ONE_WAY (required)
    // The UI auto-sets this, but we enforce it here as a safety check
    const effectiveAisleDirection = stallAngle === 90 ? "TWO_WAY" : "ONE_WAY";

    const request: EvaluateRequest = {
        siteBoundary,
        parkingConfig: { ...parkingConfig, aisleDirection: effectiveAisleDirection },
        constraints: constraints?.length ? constraints : undefined,
        // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
        ...v2Flags,
        // Pass angle from config
        angle: stallAngle,
    };

    // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
    if (IS_DEV) {
        if (parkingConfig.aisleDirection !== effectiveAisleDirection) {
            console.log(`[PARKING API] Enforcing ${effectiveAisleDirection} circulation for ${stallAngle}° parking`);
        }
        console.log('[PARKING API] evaluateParkingScenario request:', JSON.stringify(request, null, 2));
    }

    // DEV ONLY — explicit V2 payload confirmation
    console.log('[V2 REQUEST]', request);

    const response = await apiRequest<EvaluateResponse>("/evaluate", {
        method: "POST",
        body: JSON.stringify(request),
    });

    if (!response.success || !response.result) {
        throw new ParkingApiError(
            response.error || "Evaluation failed with no result"
        );
    }

    // If v2 is enabled and response contains v2 data, also assign to parkingResultV2
    const result = response.result;
    if (isV2Enabled()) {
        const resultAny = result.parkingResult as any;
        if (resultAny?.v2Stalls?.length > 0 || resultAny?.v2Aisles?.length > 0) {
            // Assign parkingResult to parkingResultV2 when v2 data is present
            (result as any).parkingResultV2 = result.parkingResult;
        }
    }

    return result;
}

// =============================================================================
// DXF Import API (Boundary)
// =============================================================================

/**
 * Import site boundary from DXF file.
 *
 * Returns extracted polygons - frontend does NOT interpret DXF directly.
 * Handles structured error responses with user-friendly messages.
 */
export async function importBoundaryFromDxf(
    file: File
): Promise<DxfImportResult> {
    const formData = new FormData();
    formData.append("file", file);

    // Dev mode logging
    if (IS_DEV) {
        console.log("[DXF Import] Uploading:", {
            name: file.name,
            size: file.size,
            type: file.type,
        });
    }

    const response = await fetch(`${PARKING_API}/import/boundary`, {
        method: "POST",
        body: formData,
    });

    // Dev mode: log response status
    if (IS_DEV) {
        console.log("[DXF Import] Response status:", response.status);
    }

    // Parse response - backend always returns JSON with success flag
    const result: DxfImportResult = await response.json();

    // Dev mode: log result
    if (IS_DEV) {
        console.log("[DXF Import] Result:", result);
    }

    // If backend returned an error, throw with the user message
    if (!result.success) {
        throw new ParkingApiError(
            result.errorMessage || "DXF import failed",
            response.status,
            {
                code: result.errorCode,
                detail: result.errorDetail,
                entitiesFound: result.entitiesFound,
            }
        );
    }

    return result;
}

// =============================================================================
// Constraint Import API
// =============================================================================

/**
 * Import constraints from DXF file.
 *
 * Returns classified constraints - frontend does NOT interpret files directly.
 * Handles structured error responses with user-friendly messages.
 */
export async function importConstraints(
    file: File
): Promise<ConstraintImportResult> {
    const formData = new FormData();
    formData.append("file", file);

    // Dev mode logging
    if (IS_DEV) {
        console.log("[Constraint Import] Uploading:", {
            name: file.name,
            size: file.size,
            type: file.type,
        });
    }

    const response = await fetch(`${PARKING_API}/import/constraints`, {
        method: "POST",
        body: formData,
    });

    // Dev mode: log response status
    if (IS_DEV) {
        console.log("[Constraint Import] Response status:", response.status);
    }

    // Parse response - backend always returns JSON with success flag
    const result: ConstraintImportResult = await response.json();

    // Dev mode: log result
    if (IS_DEV) {
        console.log("[Constraint Import] Result:", result);
    }

    // If backend returned an error, throw with the user message
    if (!result.success) {
        throw new ParkingApiError(
            result.errorMessage || "Constraint import failed",
            response.status,
            {
                code: result.errorCode,
                detail: result.errorDetail,
                entitiesFound: result.entitiesFound,
            }
        );
    }

    return result;
}

// =============================================================================
// Health Check
// =============================================================================

export async function checkApiHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${PARKING_API}/health`);
        return response.ok;
    } catch {
        return false;
    }
}

// =============================================================================
// Export Stub (Future)
// =============================================================================

/**
 * Export scenario results.
 *
 * The backend generates export files - frontend only downloads.
 */
export async function exportScenario(
    scenarioId: string,
    format: "json" | "pdf" | "csv"
): Promise<Blob> {
    const response = await fetch(
        `${PARKING_API}/export/${scenarioId}?format=${format}`
    );

    if (!response.ok) {
        throw new ParkingApiError(
            "Export failed",
            response.status
        );
    }

    return response.blob();
}

// =============================================================================
// DXF Export API
// =============================================================================

/**
 * Export parking layout to DXF file.
 *
 * Sends current site boundary and config to backend.
 * Receives downloadable DXF file with layered geometry.
 *
 * Layers:
 * - PARKING_SITE_BOUNDARY
 * - PARKING_STALL_STANDARD
 * - PARKING_STALL_ADA
 * - PARKING_ACCESS_AISLE
 * - PARKING_AISLES
 */
export async function exportParkingDxf(
    siteBoundary: Polygon,
    parkingConfig: ParkingConfig
): Promise<Blob> {
    const request = {
        siteBoundary,
        parkingConfig,
    };

    if (IS_DEV) {
        console.log("[DXF Export] Sending request to:", `${PARKING_API}/export/dxf`);
        console.log("[DXF Export] Request payload:", request);
    }

    let response: Response;
    try {
        response = await fetch(`${PARKING_API}/export/dxf`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(request),
        });
    } catch (networkError) {
        // Network error - server not reachable
        console.error("[DXF Export] Network error:", networkError);
        throw new ParkingApiError(
            "Cannot connect to server. Ensure backend is running on port 8001.",
            0,
            networkError
        );
    }

    if (IS_DEV) {
        console.log("[DXF Export] Response status:", response.status);
        console.log("[DXF Export] Content-Type:", response.headers.get("Content-Type"));
    }

    if (!response.ok) {
        let errorMessage = "DXF export failed";
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
        } catch {
            // Ignore JSON parse errors
        }
        throw new ParkingApiError(
            errorMessage,
            response.status
        );
    }

    return response.blob();
}

// =============================================================================
// Exports
// =============================================================================

export type { EvaluateRequest, EvaluateResponse };
