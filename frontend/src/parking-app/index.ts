/**
 * GenFabTools Parking Engine - Frontend Application
 *
 * This is a decision lens, not a design tool.
 *
 * The frontend:
 * - Displays conceptual, rule-based results
 * - Supports scenario-based decision making
 * - Never implies construction readiness or code compliance
 *
 * All geometry and metrics come from the backend.
 * The frontend does NOT compute or modify parking layouts.
 *
 * @module parking-app
 */

// =============================================================================
// Main Application
// =============================================================================

export { ParkingApp, default } from "./app";

// =============================================================================
// State Management
// =============================================================================

export {
    ScenarioProvider,
    useScenario,
    DEFAULT_PARKING_CONFIG,
    DEFAULT_CANVAS_STATE,
} from "./state";

export type {
    ScenarioState,
    ScenarioAction,
    ScenarioContextValue,
} from "./state";

// =============================================================================
// API
// =============================================================================

export {
    evaluateParkingScenario,
    importBoundaryFromDxf,
    importConstraints,
    checkApiHealth,
    exportScenario,
    ParkingApiError,
} from "./api";

// =============================================================================
// Canvas
// =============================================================================

export { ParkingCanvas } from "./canvas";

// =============================================================================
// Panels
// =============================================================================

export {
    SiteDefinitionPanel,
    ParkingConfigPanel,
    ConstraintsPanel,
    MetricsPanel,
} from "./panels";

// =============================================================================
// Utilities
// =============================================================================

export {
    CONSTRAINT_COLORS,
    CONSTRAINT_LABELS,
    STALL_COLORS,
    ZONE_COLORS,
    CANVAS_COLORS,
    calculateBounds,
    calculateCombinedBounds,
    worldToScreen,
    screenToWorld,
    fitBoundsToViewport,
    formatNumber,
    formatArea,
    formatEfficiency,
    formatPercent,
    formatDimension,
    isDisplayablePolygon,
    isSupportedFile,
    generateId,
    BOUNDARY_FILE_EXTENSIONS,
    CONSTRAINT_FILE_EXTENSIONS,
} from "./utils";

// =============================================================================
// Types
// =============================================================================

export type {
    // Geometry
    Point,
    Polygon,
    Bounds,
    // Constraints
    ConstraintType,
    ImportedConstraint,
    ConstraintSet,
    // Configuration
    ParkingType,
    AisleDirection,
    CirculationMode,
    FlowDirection,
    AisleCenterline,
    RampType,
    CoreType,
    RampLocation,
    StructuredConfig,
    ParkingConfig,
    // Results
    Stall,
    Aisle,
    ParkingBay,
    Ramp,
    VerticalCore,
    ParkingZone,
    LevelLayout,
    SurfaceMetrics,
    SurfaceParkingResult,
    StructuredMetrics,
    StructuredParkingResult,
    ConstraintImpact,
    ParkingResult,
    EvaluationResult,
    // Scenario
    ScenarioStatus,
    Scenario,
    // UI State
    ViewportState,
    LayerVisibility,
    CanvasState,
    // API
    EvaluateRequest,
    EvaluateResponse,
    DxfImportResult,
    DxfImportErrorCode,
    ConstraintImportResult,
} from "./types";
