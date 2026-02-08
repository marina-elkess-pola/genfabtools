/**
 * GenFabTools Parking Engine - Frontend Types
 *
 * All types represent read-only data from the backend.
 * The frontend does not compute or modify these values.
 */

// =============================================================================
// Geometry Types (Read-Only from Backend)
// =============================================================================

export interface Point {
    readonly x: number;
    readonly y: number;
}

export interface Polygon {
    readonly points: readonly Point[];
}

export interface Bounds {
    readonly minX: number;
    readonly minY: number;
    readonly maxX: number;
    readonly maxY: number;
}

// =============================================================================
// Constraint Types
// =============================================================================

export type ConstraintType =
    | "COLUMN"
    | "CORE"
    | "WALL"
    | "MEP_ROOM"
    | "SHAFT"
    | "VOID"
    | "UNKNOWN";

export interface ImportedConstraint {
    readonly id: string;
    readonly geometry: Polygon;
    readonly constraintType: ConstraintType;
    readonly layerName?: string;
    readonly categoryName?: string;
    readonly sourceFile?: string;
    readonly level?: number;
}

export interface ConstraintSet {
    readonly constraints: readonly ImportedConstraint[];
    readonly sourceFile: string;
}

// =============================================================================
// Parking Configuration Types
// =============================================================================

export type ParkingType = "surface" | "structured";

export type AisleDirection = "ONE_WAY" | "TWO_WAY";

/**
 * v2 Circulation Mode - matches backend CirculationMode enum.
 * TWO_WAY: Bidirectional traffic, no arrows
 * ONE_WAY_FORWARD: One-way traffic in centerline direction
 * ONE_WAY_REVERSE: One-way traffic opposite to centerline direction
 */
export type CirculationMode = "TWO_WAY" | "ONE_WAY_FORWARD" | "ONE_WAY_REVERSE";

/**
 * Direction vector for aisle flow.
 * Only present for one-way aisles.
 */
export interface FlowDirection {
    readonly dx: number;
    readonly dy: number;
}

/**
 * Aisle centerline for orientation.
 */
export interface AisleCenterline {
    readonly start: Point;
    readonly end: Point;
}

export type RampType =
    | "single_helix"
    | "double_helix"
    | "split_level"
    | "straight";

export type CoreType = "stair_only" | "stair_elevator" | "dual_stair_elevator";

export type RampLocation =
    | "northeast"
    | "northwest"
    | "southeast"
    | "southwest"
    | "center";

export interface StructuredConfig {
    readonly levels: number;
    readonly floorToFloorHeight: number;
    readonly rampType: RampType;
    readonly rampLocation: RampLocation;
    readonly coreType: CoreType;
    readonly coreLocation: RampLocation;
}

/**
 * Per-edge setback distances in feet.
 * North = top, South = bottom, East = right, West = left.
 */
export interface Setbacks {
    readonly north: number;
    readonly south: number;
    readonly east: number;
    readonly west: number;
}

/** Stall parking angle options */
export type StallAngle = 45 | 60 | 90;

export interface ParkingConfig {
    readonly parkingType: ParkingType;
    readonly aisleDirection: AisleDirection;
    /** Stall parking angle (45°, 60°, or 90°). Defaults to 90. */
    readonly stallAngle: StallAngle;
    /** @deprecated Use setbacks object instead */
    readonly setback: number;
    /** Per-edge setbacks (overrides uniform setback when provided) */
    readonly setbacks?: Setbacks;
    /** When true, all edges use the same setback value */
    readonly uniformSetback?: boolean;
    readonly structuredConfig?: StructuredConfig;
}

// =============================================================================
// Result Types (Read-Only from Backend)
// =============================================================================

export interface Stall {
    readonly id: string;
    readonly geometry: Polygon;
    readonly stallType: "standard" | "compact" | "ada" | "ada_van";
    readonly bayId: string;
    /** 
     * Access aisle geometry for ADA stalls.
     * ADA stalls have a separate access aisle (5' for standard, 8' for van).
     * The stall geometry is 11' × 18', access aisle is adjacent.
     */
    readonly accessAisle?: Polygon;
}

export interface Aisle {
    readonly id: string;
    readonly geometry: Polygon;
    readonly direction: AisleDirection;
    /** v2: Aisle width in feet (e.g. 24 for 60° parking) */
    readonly width?: number;
    /** v2: Circulation mode from backend (authoritative) */
    readonly circulation?: CirculationMode;
    /** v2: Flow direction vector for one-way aisles (null for TWO_WAY) */
    readonly flowDirection?: FlowDirection | null;
    /** v2: Aisle centerline for orientation */
    readonly centerline?: AisleCenterline;
}

export interface ParkingBay {
    readonly id: string;
    readonly geometry: Polygon;
    readonly stalls: readonly Stall[];
    readonly aisle: Aisle;
}

export interface Ramp {
    readonly id: string;
    readonly geometry: Polygon;
    readonly rampType: RampType;
    readonly fromLevel: number;
    readonly toLevel: number;
}

export interface VerticalCore {
    readonly id: string;
    readonly geometry: Polygon;
    readonly coreType: CoreType;
}

export interface ParkingZone {
    readonly id: string;
    readonly geometry: Polygon;
    readonly zoneType: "RECTANGULAR" | "REMNANT" | "UNUSABLE" | "VOID";
    readonly stallCount: number;
}

export interface LevelLayout {
    readonly level: number;
    readonly floorElevation: number;
    readonly bays: readonly ParkingBay[];
    readonly stallCount: number;
    readonly stallsLostToExclusions: number;
}

// =============================================================================
// Surface Parking Result
// =============================================================================

export interface SurfaceMetrics {
    readonly totalStalls: number;
    readonly standardStalls: number;
    readonly adaStalls: number;
    readonly totalArea: number;
    readonly parkableArea: number;
    readonly efficiencySfPerStall: number;
    readonly usabilityRatio: number;
    readonly areaLostToGeometry: number;
    readonly areaLostToGeometryPct: number;
}

export interface SurfaceParkingResult {
    readonly type: "surface";
    readonly bays: readonly ParkingBay[];
    readonly zones: readonly ParkingZone[];
    readonly metrics: SurfaceMetrics;
}

// =============================================================================
// Structured Parking Result
// =============================================================================

export interface StructuredMetrics {
    readonly totalStalls: number;
    readonly stallsPerLevel: readonly number[];
    readonly levelCount: number;
    readonly totalHeight: number;
    readonly grossArea: number;
    readonly netParkableArea: number;
    readonly efficiencySfPerStall: number;
    readonly stallsLostToRamps: number;
    readonly stallsLostToCores: number;
    readonly stallsLostToConstraints: number;
}

export interface StructuredParkingResult {
    readonly type: "structured";
    readonly levels: readonly LevelLayout[];
    readonly ramps: readonly Ramp[];
    readonly cores: readonly VerticalCore[];
    readonly metrics: StructuredMetrics;
}

// =============================================================================
// Constraint Impact
// =============================================================================

export interface ConstraintImpact {
    readonly totalStallsRemoved: number;
    readonly totalAreaLost: number;
    readonly efficiencyLossPct: number;
    readonly impactByType: Readonly<Record<ConstraintType, number>>;
    readonly impactByLevel?: readonly {
        readonly level: number;
        readonly stallsRemoved: number;
        readonly areaLost: number;
    }[];
}

// =============================================================================
// Combined Result
// =============================================================================

export type ParkingResult = SurfaceParkingResult | StructuredParkingResult;

export interface EvaluationResult {
    readonly scenarioId: string;
    readonly timestamp: string;
    readonly parkingResult: ParkingResult;
    /** v2 parking result (set when ?v2=1 enabled) */
    readonly parkingResultV2?: ParkingResult;
    readonly constraintImpact?: ConstraintImpact;
    readonly warnings: readonly string[];
}

// =============================================================================
// Scenario (Immutable State Unit)
// =============================================================================

export type ScenarioStatus = "draft" | "evaluating" | "complete" | "error";

export interface Scenario {
    readonly id: string;
    readonly name: string;
    readonly createdAt: string;
    readonly status: ScenarioStatus;
    readonly siteBoundary: Polygon | null;
    readonly parkingConfig: ParkingConfig;
    readonly constraintsEnabled: boolean;
    readonly constraints: readonly ImportedConstraint[];
    readonly result?: EvaluationResult;
    readonly error?: string;
}

// =============================================================================
// UI State Types
// =============================================================================

export interface ViewportState {
    readonly panX: number;
    readonly panY: number;
    readonly zoom: number;
}

export interface LayerVisibility {
    readonly siteBoundary: boolean;
    readonly constraints: boolean;
    readonly stalls: boolean;
    readonly aisles: boolean;
    readonly ramps: boolean;
    readonly cores: boolean;
    readonly zones: boolean;
}

export interface CanvasState {
    readonly viewport: ViewportState;
    readonly layerVisibility: LayerVisibility;
    readonly selectedLevel: number;
}

// =============================================================================
// API Request/Response Types
// =============================================================================

export interface EvaluateRequest {
    readonly siteBoundary: Polygon;
    readonly parkingConfig: ParkingConfig;
    readonly constraints?: readonly ImportedConstraint[];
    // V2 engine flags (DEV ONLY — REMOVE BEFORE PUBLIC RELEASE)
    readonly useV2?: boolean;
    readonly allowAngledParking?: boolean;
    readonly angle?: number;
    readonly recoverResidual?: boolean;
}

export interface EvaluateResponse {
    readonly success: boolean;
    readonly result?: EvaluationResult;
    readonly error?: string;
}

// =============================================================================
// DXF Import Types
// =============================================================================

/** Error codes returned by DXF import */
export type DxfImportErrorCode =
    | "FILE_READ_ERROR"
    | "INVALID_DXF"
    | "NO_GEOMETRY"
    | "NO_CLOSED_POLYLINES"
    | "UNSUPPORTED_ENTITY"
    | "INVALID_GEOMETRY"
    | "UNIT_ERROR"
    | "EMPTY_FILE"
    | "FEATURE_NOT_AVAILABLE"
    | "UNKNOWN_ERROR";

export interface DxfImportResult {
    readonly success: boolean;
    readonly polygons: readonly Polygon[];
    readonly warnings: readonly string[];
    readonly entitiesFound: Record<string, number>;
    readonly entitiesImported: number;
    readonly entitiesSkipped: number;
    readonly errorCode?: DxfImportErrorCode;
    readonly errorMessage?: string;
    readonly errorDetail?: string;
}

export interface ConstraintImportResult {
    readonly success: boolean;
    readonly polygons: readonly Polygon[];
    readonly warnings: readonly string[];
    readonly entitiesFound: Record<string, number>;
    readonly entitiesImported: number;
    readonly entitiesSkipped: number;
    readonly errorCode?: DxfImportErrorCode;
    readonly errorMessage?: string;
    readonly errorDetail?: string;
}

