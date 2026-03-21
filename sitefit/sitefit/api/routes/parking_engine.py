"""
api/routes/parking_engine.py - Parking Engine API Routes

Endpoints for the GenFabTools Parking Engine.
Uses the parking_engine module for feasibility-grade parking layouts.
"""

import time
import uuid
from enum import Enum
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from parking_engine import (
    Polygon as PEPolygon,
    Point as PEPoint,
    AisleDirection,
    generate_surface_layout,
    generate_surface_layout_irregular,
    compute_metrics,
    generate_structured_parking_skeleton,
    generate_structured_parking_layout,
    compute_structured_layout_metrics,
)

# Try to import DXF export (Phase 6)
try:
    from parking_engine import export_surface_layout_to_dxf
    HAS_DXF_EXPORT = True
except ImportError:
    HAS_DXF_EXPORT = False

# Try to import DXF import (Phase 7)
try:
    from parking_engine.dxf_import import (
        import_dxf_from_bytes,
        DxfImportError,
        DxfImportErrorCode,
        get_user_message,
    )
    HAS_DXF_IMPORT = True
except ImportError:
    HAS_DXF_IMPORT = False

# Try to import CAD constraints (Phase 5)
try:
    from parking_engine import (
        ConstraintType,
        ImportedConstraint,
        ConstraintSet,
        apply_constraints_to_surface_layout,
        apply_constraints_to_structured_layout,
    )
    HAS_CAD_CONSTRAINTS = True
except ImportError:
    HAS_CAD_CONSTRAINTS = False

# Try to import v2 engine (v2 MVP)
try:
    from sitefit.parking_engine.v2 import (
        # Schemas
        ZoneTypeSchema as V2ZoneType,
        AngleConfigSchema as V2AngleConfig,
        ZoneSchema as V2ZoneSchema,
        ZoneResultSchema as V2ZoneResultSchema,
        # Zone model
        Zone,
        ZoneType,
        AngleConfig,
        Setbacks as V2Setbacks,
        CirculationMode,
        create_default_zone,
        # Orchestrator
        ZoneOrchestrator,
        orchestrate_layout,
        OrchestratedLayoutResult,
        # Residual recovery
        perform_residual_recovery,
        # Connectivity
        check_circulation_connected,
        # Geometry
        Aisle60,
        # V2 Layout Error
        V2LayoutError,
    )
    # Import the single authoritative V2 entrypoint
    from sitefit.parking_engine.v2.circulation_loop_v2 import (
        generateParkingLayoutV2,
        V2LayoutResult,
        Setbacks as V2EngineSetbacks,
    )
    from sitefit.core.geometry import Point as SFPoint, Polygon as SFPolygon
    HAS_V2_ENGINE = True
except ImportError as e:
    print(f"v2 engine import failed: {e}")
    HAS_V2_ENGINE = False


router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class PointSchema(BaseModel):
    """A 2D point."""
    x: float
    y: float


class PolygonSchema(BaseModel):
    """A polygon defined by a list of points."""
    points: List[PointSchema]


class ConstraintTypeEnum(str, Enum):
    """Constraint types."""
    COLUMN = "COLUMN"
    CORE = "CORE"
    WALL = "WALL"
    MEP_ROOM = "MEP_ROOM"
    SHAFT = "SHAFT"
    VOID = "VOID"
    UNKNOWN = "UNKNOWN"


class ImportedConstraintSchema(BaseModel):
    """An imported constraint."""
    id: Optional[str] = None
    geometry: PolygonSchema
    constraintType: ConstraintTypeEnum
    layerName: Optional[str] = None
    categoryName: Optional[str] = None
    sourceFile: Optional[str] = None
    level: Optional[int] = None


class StructuredConfigSchema(BaseModel):
    """Structured parking configuration."""
    levels: int = Field(4, ge=2, le=12)
    floorToFloorHeight: float = Field(10.5, ge=9, le=14)
    rampType: str = "single_helix"
    rampLocation: str = "northeast"
    coreType: str = "stair_elevator"
    coreLocation: str = "center"


class SetbacksSchema(BaseModel):
    """Per-edge setback distances in feet."""
    north: float = Field(5.0, ge=0, le=50)
    south: float = Field(5.0, ge=0, le=50)
    east: float = Field(5.0, ge=0, le=50)
    west: float = Field(5.0, ge=0, le=50)


class ParkingConfigSchema(BaseModel):
    """Parking configuration."""
    parkingType: str = Field("surface", pattern="^(surface|structured)$")
    aisleDirection: str = Field("TWO_WAY", pattern="^(ONE_WAY|TWO_WAY)$")
    setback: float = Field(5.0, ge=0, le=50)  # Legacy uniform setback
    setbacks: Optional[SetbacksSchema] = None  # Per-edge setbacks
    uniformSetback: bool = True  # When true, use setback; when false, use setbacks
    structuredConfig: Optional[StructuredConfigSchema] = None


# =============================================================================
# V2 ZONE SCHEMA (inline for API compatibility)
# =============================================================================

class V2ZoneTypeEnum(str, Enum):
    """Zone types for v2."""
    GENERAL = "GENERAL"
    RESERVED = "RESERVED"


class V2AngleConfigEnum(str, Enum):
    """Angle config for v2."""
    DEGREES_90 = "90_DEGREES"
    DEGREES_60 = "60_DEGREES"
    DEGREES_45 = "45_DEGREES"
    DEGREES_30 = "30_DEGREES"


class V2ZoneRequestSchema(BaseModel):
    """Zone definition for v2 request."""
    id: str = Field(..., description="Unique zone identifier")
    name: str = Field(..., description="Human-readable zone name")
    type: V2ZoneTypeEnum = Field(
        V2ZoneTypeEnum.GENERAL, description="Zone type")
    polygon: PolygonSchema = Field(..., description="Zone boundary")
    angleConfig: V2AngleConfigEnum = Field(
        V2AngleConfigEnum.DEGREES_90, description="Stall angle")
    stallTargetMin: Optional[int] = Field(None, ge=0)
    stallTargetMax: Optional[int] = Field(None, ge=0)


class V2ZoneResponseSchema(BaseModel):
    """Zone result for v2 response."""
    id: str
    name: str
    type: str
    stallCount: int = 0
    angledStalls: int = 0
    area: float = 0


class EvaluateRequest(BaseModel):
    """Request for parking evaluation."""
    siteBoundary: PolygonSchema
    parkingConfig: ParkingConfigSchema
    constraints: Optional[List[ImportedConstraintSchema]] = None
    # v2 feature flag (default: false - use v1)
    useV2: bool = Field(
        False, description="Enable v2 engine (zones, 60° parking)")
    # v2 request extensions (ignored unless useV2=true)
    zones: Optional[List[V2ZoneRequestSchema]] = Field(
        None, description="v2: Zone definitions (useV2=true only)")
    allowAngledParking: bool = Field(
        False, description="v2: Enable angled parking (30°/45°/60°)")
    angle: Optional[int] = Field(
        None, description="v2: Parking angle in degrees (30, 45, or 60). If not set, defaults to 45°")
    recoverResidual: bool = Field(
        False, description="v2: Attempt stall recovery in residual spaces")

    class Config:
        json_schema_extra = {
            "example": {
                "siteBoundary": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 300, "y": 0},
                        {"x": 300, "y": 200},
                        {"x": 0, "y": 200}
                    ]
                },
                "parkingConfig": {
                    "parkingType": "surface",
                    "aisleDirection": "TWO_WAY",
                    "setback": 5.0
                },
                "useV2": False
            }
        }


class StallResponseSchema(BaseModel):
    """A parking stall."""
    id: str
    geometry: PolygonSchema
    stallType: str
    bayId: str
    accessAisle: Optional[PolygonSchema] = None  # For ADA/ADA_VAN stalls


class AisleResponseSchema(BaseModel):
    """A drive aisle."""
    id: str
    geometry: PolygonSchema
    direction: str


class BayResponseSchema(BaseModel):
    """A parking bay with stalls and aisle."""
    id: str
    geometry: PolygonSchema
    stalls: List[StallResponseSchema]
    aisle: AisleResponseSchema


class ZoneResponseSchema(BaseModel):
    """A parking zone."""
    id: str
    geometry: PolygonSchema
    zoneType: str
    stallCount: int


class SurfaceMetricsSchema(BaseModel):
    """Surface parking metrics."""
    totalStalls: int
    standardStalls: int
    adaStalls: int
    totalArea: float
    parkableArea: float
    efficiencySfPerStall: float
    usabilityRatio: float
    areaLostToGeometry: float
    areaLostToGeometryPct: float


class SurfaceResultSchema(BaseModel):
    """Surface parking result."""
    type: str = "surface"
    bays: List[BayResponseSchema]
    zones: List[ZoneResponseSchema]
    metrics: SurfaceMetricsSchema


class StructuredMetricsSchema(BaseModel):
    """Structured parking metrics."""
    totalStalls: int
    stallsPerLevel: List[int]
    levelCount: int
    totalHeight: float
    grossArea: float
    netParkableArea: float
    efficiencySfPerStall: float
    stallsLostToRamps: int
    stallsLostToCores: int
    stallsLostToConstraints: int


class RampResponseSchema(BaseModel):
    """A ramp."""
    id: str
    geometry: PolygonSchema
    rampType: str
    fromLevel: int
    toLevel: int


class CoreResponseSchema(BaseModel):
    """A vertical core."""
    id: str
    geometry: PolygonSchema
    coreType: str


class LevelLayoutSchema(BaseModel):
    """A single level layout."""
    level: int
    floorElevation: float
    bays: List[BayResponseSchema]
    stallCount: int
    stallsLostToExclusions: int


class StructuredResultSchema(BaseModel):
    """Structured parking result."""
    type: str = "structured"
    levels: List[LevelLayoutSchema]
    ramps: List[RampResponseSchema]
    cores: List[CoreResponseSchema]
    metrics: StructuredMetricsSchema


class ConstraintImpactSchema(BaseModel):
    """Constraint impact on layout."""
    totalStallsRemoved: int
    totalAreaLost: float
    efficiencyLossPct: float
    impactByType: Dict[str, int]


class EvaluationResultSchema(BaseModel):
    """Evaluation result."""
    scenarioId: str
    timestamp: str
    parkingResult: Dict[str, Any]  # Can be surface or structured
    constraintImpact: Optional[ConstraintImpactSchema] = None
    warnings: List[str] = []
    # v2 response extensions (populated when useV2=true)
    v2Zones: Optional[List[V2ZoneResponseSchema]] = Field(
        None, description="v2: Per-zone layout results")
    angledStalls: int = Field(
        0, ge=0, description="v2: Total 60° angled stalls")
    residualRecovered: int = Field(
        0, ge=0, description="v2: Stalls recovered from residual spaces")
    circulationConnected: bool = Field(
        True, description="v2: Whether all aisles form a connected network")
    v2Error: Optional[str] = Field(
        None, description="v2: Error message if layout generation failed")
    interiorDebugInfo: Optional[Dict[str, Any]] = Field(
        None, description="v2: Debug info from interior aisle generation")


class EvaluateResponse(BaseModel):
    """Response for parking evaluation."""
    success: bool
    result: Optional[EvaluationResultSchema] = None
    error: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def schema_to_polygon(schema: PolygonSchema) -> PEPolygon:
    """Convert PolygonSchema to parking_engine Polygon."""
    points = [PEPoint(p.x, p.y) for p in schema.points]
    return PEPolygon(points)


def polygon_to_schema(polygon: PEPolygon) -> PolygonSchema:
    """Convert parking_engine Polygon to PolygonSchema."""
    return PolygonSchema(
        points=[PointSchema(x=p.x, y=p.y) for p in polygon.vertices]
    )


def stall_to_schema(stall, bay_id: str, index: int) -> StallResponseSchema:
    """Convert a stall to schema."""
    access_aisle_schema = None
    if hasattr(stall, 'access_aisle') and stall.access_aisle is not None:
        access_aisle_schema = polygon_to_schema(stall.access_aisle)

    return StallResponseSchema(
        id=f"stall_{bay_id}_{index}",
        geometry=polygon_to_schema(stall.geometry),
        stallType=stall.stall_type.value if hasattr(
            stall.stall_type, 'value') else str(stall.stall_type),
        bayId=bay_id,
        accessAisle=access_aisle_schema
    )


def aisle_to_schema(aisle, bay_id: str) -> AisleResponseSchema:
    """Convert an aisle to schema."""
    return AisleResponseSchema(
        id=f"aisle_{bay_id}",
        geometry=polygon_to_schema(aisle.geometry),
        direction=aisle.direction.value if hasattr(aisle, 'direction') and hasattr(
            aisle.direction, 'value') else "TWO_WAY"
    )


def bay_to_schema(bay, index: int) -> BayResponseSchema:
    """Convert a parking bay to schema."""
    bay_id = f"bay_{index}"

    # Compute bay geometry from aisle and stalls
    all_geoms = [bay.aisle.geometry] + [s.geometry for s in bay.all_stalls()]
    if all_geoms:
        min_x = min(g.bounds[0] for g in all_geoms)
        min_y = min(g.bounds[1] for g in all_geoms)
        max_x = max(g.bounds[2] for g in all_geoms)
        max_y = max(g.bounds[3] for g in all_geoms)
        bay_geometry = PEPolygon([
            PEPoint(min_x, min_y),
            PEPoint(max_x, min_y),
            PEPoint(max_x, max_y),
            PEPoint(min_x, max_y),
        ])
    else:
        bay_geometry = bay.aisle.geometry

    return BayResponseSchema(
        id=bay_id,
        geometry=polygon_to_schema(bay_geometry),
        stalls=[stall_to_schema(s, bay_id, i)
                for i, s in enumerate(bay.all_stalls())],
        aisle=aisle_to_schema(bay.aisle, bay_id)
    )


def schema_to_constraint_set(
    constraints: List[ImportedConstraintSchema],
) -> 'ConstraintSet':
    """Convert list of ImportedConstraintSchema to ConstraintSet.

    Converts frontend constraint data to the internal constraint format
    used by the parking engine for constraint integration.
    """
    if not HAS_CAD_CONSTRAINTS:
        raise RuntimeError("CAD constraints module not available")

    imported_constraints = []
    for schema in constraints:
        # Convert geometry
        points = [PEPoint(p.x, p.y) for p in schema.geometry.points]
        polygon = PEPolygon(points)

        # Map constraint type enum
        type_mapping = {
            ConstraintTypeEnum.COLUMN: ConstraintType.COLUMN,
            ConstraintTypeEnum.CORE: ConstraintType.CORE,
            ConstraintTypeEnum.WALL: ConstraintType.WALL,
            ConstraintTypeEnum.MEP_ROOM: ConstraintType.MEP_ROOM,
            ConstraintTypeEnum.SHAFT: ConstraintType.SHAFT,
            ConstraintTypeEnum.VOID: ConstraintType.VOID,
            ConstraintTypeEnum.UNKNOWN: ConstraintType.UNKNOWN,
        }
        constraint_type = type_mapping.get(
            schema.constraintType, ConstraintType.UNKNOWN)

        # Create ImportedConstraint
        constraint = ImportedConstraint(
            geometry=polygon,
            constraint_type=constraint_type,
            source_format="dxf",  # Assume DXF for now
            source_layer_or_category=schema.layerName or "imported",
            source_id=schema.id,
            confidence=1.0,
        )
        imported_constraints.append(constraint)

    return ConstraintSet(
        constraints=imported_constraints,
        source_file=constraints[0].sourceFile if constraints else None,
        source_format="dxf",
    )


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_parking(request: EvaluateRequest) -> EvaluateResponse:
    """
    Evaluate a parking scenario.

    Generates a complete parking layout with metrics.
    This is a conceptual, rule-based estimate for early feasibility only.
    """
    try:
        start_time = time.time()
        warnings = []

        # Convert site boundary
        site_boundary = schema_to_polygon(request.siteBoundary)

        # Validate site
        if site_boundary.area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid site boundary - area must be positive")

        if site_boundary.area < 2500:  # Less than 50x50
            warnings.append("Site is very small - results may be limited")

        # Get aisle direction
        aisle_direction = AisleDirection.TWO_WAY
        if request.parkingConfig.aisleDirection == "ONE_WAY":
            aisle_direction = AisleDirection.ONE_WAY

        # Generate layout based on type
        config = request.parkingConfig
        constraint_impact = None

        # v2 response extension fields (populated if useV2=true)
        v2_zones_response = None
        angled_stalls = 0
        residual_recovered = 0
        circulation_connected = True

        # Extract setbacks - use per-edge if provided and not uniform
        setbacks_dict = None
        if config.setbacks and not config.uniformSetback:
            setbacks_dict = {
                "north": config.setbacks.north,
                "south": config.setbacks.south,
                "east": config.setbacks.east,
                "west": config.setbacks.west,
            }

        # =====================================================================
        # V2 ENGINE PATH (when useV2=true)
        # SINGLE AUTHORITATIVE ENTRYPOINT: generateParkingLayoutV2
        # NO V1-derived metrics, layouts, or explanations are used.
        # =====================================================================

        if request.useV2:
            if not HAS_V2_ENGINE:
                raise RuntimeError(
                    "V2 requested but V2 engine is not available")

            # v2 engine is enabled and available
            warnings.append("Using v2 engine (experimental)")

            # Convert site boundary to Shapely polygon for V2 engine
            site_points = [(p.x, p.y) for p in request.siteBoundary.points]
            from shapely.geometry import Polygon as ShapelyPolygon
            shapely_boundary = ShapelyPolygon(site_points)

            # Build v2 setbacks from request config
            v2_setbacks = V2EngineSetbacks.uniform(0.0)
            if setbacks_dict:
                v2_setbacks = V2EngineSetbacks(
                    north=setbacks_dict["north"],
                    south=setbacks_dict["south"],
                    east=setbacks_dict["east"],
                    west=setbacks_dict["west"],
                )
            elif config.setback > 0:
                v2_setbacks = V2EngineSetbacks.uniform(config.setback)

            # DEBUG: Print V2 inputs for discrepancy investigation
            site_bounds = shapely_boundary.bounds  # (minx, miny, maxx, maxy)

            # Map aisleDirection to v2 CirculationMode
            # V2 ENGINE: Locked to 90° which REQUIRES TWO_WAY
            v2_circulation = CirculationMode.TWO_WAY

            # V2 ENGINE: Locked to 90° parking angle
            parking_angle = 90

            # =====================================================================
            # CALL generateParkingLayoutV2 — SINGLE AUTHORITATIVE ENTRYPOINT
            # This is the ONLY function that generates V2 layouts.
            # V2LayoutError is caught and converted to a safe empty response.
            # =====================================================================
            print("[DEBUG] V2 ROUTE HIT")
            print("[DEBUG] use_v2 =", request.useV2)
            try:
                v2_layout = generateParkingLayoutV2(
                    site_boundary=shapely_boundary,
                    setbacks=v2_setbacks,
                    circulation_mode=v2_circulation,
                    parking_angle=parking_angle,
                )

                # ================================================================
                # V2 ENGINE: VALIDATION GUARDS
                # Convert validation failures to V2LayoutError for uniform handling
                # ================================================================

                # GUARD 1: Zero stalls
                if v2_layout.total_stalls == 0:
                    raise V2LayoutError("ZERO_STALLS: No stalls generated")

                # GUARD 2: Zero aisles
                if len(v2_layout.aisles) == 0:
                    raise V2LayoutError("ZERO_AISLES: No aisles generated")

                # GUARD 3: No circulation loop
                if v2_layout.circulation is None:
                    raise V2LayoutError(
                        "NO_CIRCULATION_LOOP: Circulation loop not generated")

            except V2LayoutError as e:
                # ================================================================
                # V2LayoutError → Safe empty response (HTTP 200)
                # Frontend receives valid JSON with error message, not HTTP 500
                # ================================================================

                empty_result = EvaluationResultSchema(
                    scenarioId=str(uuid.uuid4()),
                    timestamp=time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    parkingResult={
                        "type": "surface",
                        "bays": [],
                        "zones": [],
                        "v2Stalls": [],
                        "v2Aisles": [],
                        "v2DebugGeometry": None,
                        "metrics": {
                            "totalStalls": 0,
                            "standardStalls": 0,
                            "adaStalls": 0,
                            "totalArea": shapely_boundary.area,
                            "parkableArea": 0,
                            "efficiencySfPerStall": 0,
                            "usabilityRatio": 0,
                            "areaLostToGeometry": 0,
                            "areaLostToGeometryPct": 0,
                        }
                    },
                    constraintImpact=None,
                    warnings=[f"V2 layout failed: {str(e)}"],
                    v2Zones=[],
                    angledStalls=0,
                    residualRecovered=0,
                    circulationConnected=False,
                    v2Error=str(e),  # Include error message for frontend
                )

                return EvaluateResponse(
                    success=False,
                    result=empty_result,
                    error=str(e),
                )

            # DEBUG INSTRUMENTATION

            # Build v2 stalls response from V2LayoutResult
            # AUDIT: all_v2_stalls is built from v2_layout.stalls (final_valid_stalls)
            all_v2_stalls = []
            for stall in v2_layout.stalls:
                stall_dict = stall.to_dict()
                all_v2_stalls.append({
                    "id": stall_dict["id"],
                    "geometry": stall_dict["geometry"],
                    "stallType": "STANDARD",
                    "bayId": "default-zone",
                    "angle": stall_dict["angle"],
                })

            # AUDIT ASSERTION: len(all_v2_stalls) MUST equal v2_layout.total_stalls
            assert len(all_v2_stalls) == v2_layout.total_stalls, (
                f"AUDIT FAIL: all_v2_stalls ({len(all_v2_stalls)}) != total_stalls ({v2_layout.total_stalls})"
            )

            # Build v2 aisles response from V2LayoutResult
            all_v2_aisles = v2_layout.aisles

            # Build v2 zone responses (single default zone)
            v2_zones_response = [V2ZoneResponseSchema(
                id="default-zone",
                name="Default",
                type="GENERAL",
                stallCount=v2_layout.total_stalls,
                angledStalls=v2_layout.total_stalls,
                area=shapely_boundary.area,
            )]

            angled_stalls = v2_layout.total_stalls

            # Circulation is always connected for V2 (validated in generateParkingLayoutV2)
            circulation_connected = True

            # V2 ENGINE: No residual recovery in V2 path (handled internally)
            residual_recovered = 0

            # Build v2 parking result (surface only)
            total_stalls = v2_layout.total_stalls
            parking_result = {
                "type": "surface",
                "bays": [],  # v2 doesn't use bays, uses zones
                "zones": [z.model_dump() for z in v2_zones_response],
                # v2 geometry for canvas rendering
                "v2Stalls": all_v2_stalls,
                "v2Aisles": all_v2_aisles,
                # Debug geometry from V2 layout
                "v2DebugGeometry": v2_layout.debug_geometry,
                "metrics": {
                    "totalStalls": total_stalls,
                    "standardStalls": total_stalls,  # v2 doesn't track ADA separately yet
                    "adaStalls": 0,
                    "totalArea": shapely_boundary.area,
                    "parkableArea": shapely_boundary.area,
                    "efficiencySfPerStall": shapely_boundary.area / total_stalls if total_stalls > 0 else 0,
                    "usabilityRatio": 1.0,
                    "areaLostToGeometry": 0,
                    "areaLostToGeometryPct": 0,
                }
            }

            # Calculate elapsed time for v2
            elapsed_ms = (time.time() - start_time) * 1000
            if elapsed_ms > 1000:
                warnings.append(f"Evaluation took {elapsed_ms:.0f}ms")

            # DEBUG: Print total_stalls before returning

            # Build v2 result and return immediately - no fallthrough to v1
            result = EvaluationResultSchema(
                scenarioId=str(uuid.uuid4()),
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                parkingResult=parking_result,
                constraintImpact=None,  # v2 doesn't use constraint impact
                warnings=warnings,
                v2Zones=v2_zones_response,
                angledStalls=angled_stalls,
                residualRecovered=residual_recovered,
                circulationConnected=circulation_connected,
                interiorDebugInfo=v2_layout.interior_debug_info,
            )

            return EvaluateResponse(
                success=True,
                result=result,
            )

        # =====================================================================
        # V1 ENGINE PATH (legacy - must not execute when v2 is enabled)
        # =====================================================================
        # EXPLICIT GUARD: V1 code is UNREACHABLE when useV2 === true
        # The V2 path above returns early. This assertion catches any bugs.
        if request.useV2:
            raise RuntimeError(
                "CRITICAL: V1 path reached with useV2=true. "
                "This is a bug - V2 code path should have returned or raised."
            )
        assert not request.useV2, "V1 path must not execute when v2 is enabled"

        if config.parkingType == "surface":

            # Check if constraints are provided
            has_constraints = (
                HAS_CAD_CONSTRAINTS and
                request.constraints and
                len(request.constraints) > 0
            )

            if has_constraints:
                # === CONSTRAINT-AWARE LAYOUT GENERATION ===
                # Convert constraints to internal format
                constraint_set = schema_to_constraint_set(request.constraints)

                # Debug logging
                original_area = site_boundary.area
                constraint_area = constraint_set.total_area

                # Apply constraints to layout - this subtracts constraint polygons
                # from the parkable area BEFORE generating stalls
                constrained_result = apply_constraints_to_surface_layout(
                    site_boundary=site_boundary,
                    constraints=constraint_set,
                    aisle_direction=aisle_direction,
                    setback=config.setback if setbacks_dict is None else 5.0,
                    setbacks=setbacks_dict,
                    compute_unconstrained_baseline=True,
                )

                # Debug: net parkable area after constraint subtraction

                # Extract layout from constrained result
                layout = constrained_result.layout

                if layout is None:
                    # All area was consumed by constraints
                    warnings.append(
                        "Constraints consume entire site - no parking possible")
                    parking_result = {
                        "type": "surface",
                        "bays": [],
                        "zones": [],
                        "metrics": {
                            "totalStalls": 0,
                            "standardStalls": 0,
                            "adaStalls": 0,
                            "totalArea": original_area,
                            "parkableArea": 0,
                            "efficiencySfPerStall": 0,
                            "usabilityRatio": 0,
                            "areaLostToGeometry": original_area,
                            "areaLostToGeometryPct": 100.0,
                        }
                    }
                else:
                    # Compute metrics from constrained layout
                    metrics = compute_metrics(layout)

                    # Debug: stall count comparison
                    impact = constrained_result.constraint_impact

                    # Convert to response
                    bays = [bay_to_schema(bay, i)
                            for i, bay in enumerate(layout.bays)]

                    parking_result = {
                        "type": "surface",
                        "bays": [b.model_dump() for b in bays],
                        "zones": [],
                        "metrics": {
                            "totalStalls": metrics.total_stalls,
                            "standardStalls": metrics.standard_stalls,
                            "adaStalls": metrics.ada_stalls,
                            "totalArea": original_area,
                            "parkableArea": constrained_result.constrained_site_area,
                            "efficiencySfPerStall": metrics.efficiency_sf_per_stall,
                            "usabilityRatio": constrained_result.constrained_site_area / original_area if original_area > 0 else 0,
                            "areaLostToGeometry": original_area - constrained_result.constrained_site_area,
                            "areaLostToGeometryPct": (1 - constrained_result.constrained_site_area / original_area) * 100 if original_area > 0 else 0,
                        }
                    }

                    # Record constraint impact for response
                    constraint_impact = ConstraintImpactSchema(
                        totalStallsRemoved=impact.total_stalls_lost,
                        totalAreaLost=original_area - constrained_result.constrained_site_area,
                        efficiencyLossPct=impact.efficiency_delta * 100,
                        impactByType={
                            ct.name: len(
                                constraint_set.get_polygons_by_type(ct))
                            for ct in set(c.constraint_type for c in constraint_set.constraints)
                        },
                    )

                    # Add constraint notes to warnings
                    warnings.extend(constrained_result.notes[:3])

            else:
                # === STANDARD LAYOUT GENERATION (NO CONSTRAINTS) ===
                layout = generate_surface_layout(
                    site_boundary=site_boundary,
                    aisle_direction=aisle_direction,
                    setback=config.setback if setbacks_dict is None else None,
                    setbacks=setbacks_dict,
                )

                # Compute metrics
                metrics = compute_metrics(layout)

                # Convert to response
                bays = [bay_to_schema(bay, i)
                        for i, bay in enumerate(layout.bays)]

                parking_result = {
                    "type": "surface",
                    "bays": [b.model_dump() for b in bays],
                    "zones": [],
                    "metrics": {
                        "totalStalls": metrics.total_stalls,
                        "standardStalls": metrics.standard_stalls,
                        "adaStalls": metrics.ada_stalls,
                        "totalArea": metrics.gross_site_area,
                        "parkableArea": metrics.net_parking_area,
                        "efficiencySfPerStall": metrics.efficiency_sf_per_stall,
                        "usabilityRatio": metrics.net_parking_area / metrics.gross_site_area if metrics.gross_site_area > 0 else 0,
                        "areaLostToGeometry": metrics.gross_site_area - metrics.net_parking_area,
                        "areaLostToGeometryPct": (1 - metrics.net_parking_area / metrics.gross_site_area) * 100 if metrics.gross_site_area > 0 else 0,
                    }
                }

        else:
            # Structured parking
            struct_config = config.structuredConfig or StructuredConfigSchema()

            # Generate skeleton
            skeleton = generate_structured_parking_skeleton(
                footprint=site_boundary,
                level_count=struct_config.levels,
                floor_to_floor_height=struct_config.floorToFloorHeight,
                ramp_config={"type": struct_config.rampType,
                             "location": struct_config.rampLocation},
                core_config={"type": struct_config.coreType,
                             "location": struct_config.coreLocation},
            )

            # Generate layout with stalls
            layout = generate_structured_parking_layout(
                structured_layout=skeleton,
                aisle_direction=aisle_direction,
            )

            # Compute metrics
            metrics = compute_structured_layout_metrics(layout)

            # Convert levels
            levels_response = []
            for level in layout.levels:
                level_bays = [bay_to_schema(bay, i)
                              for i, bay in enumerate(level.bays)]
                levels_response.append({
                    "level": level.level_number,
                    "floorElevation": level.floor_elevation,
                    "bays": [b.model_dump() for b in level_bays],
                    "stallCount": level.stall_count,
                    "stallsLostToExclusions": getattr(level, 'stalls_lost', 0),
                })

            # Convert ramps
            ramps_response = []
            for i, ramp in enumerate(skeleton.ramps):
                ramps_response.append({
                    "id": f"ramp_{i}",
                    "geometry": polygon_to_schema(ramp.geometry).model_dump(),
                    "rampType": ramp.ramp_type.value if hasattr(ramp.ramp_type, 'value') else str(ramp.ramp_type),
                    "fromLevel": ramp.from_level,
                    "toLevel": ramp.to_level,
                })

            # Convert cores
            cores_response = []
            for i, core in enumerate(skeleton.cores):
                cores_response.append({
                    "id": f"core_{i}",
                    "geometry": polygon_to_schema(core.geometry).model_dump(),
                    "coreType": core.core_type.value if hasattr(core.core_type, 'value') else str(core.core_type),
                })

            parking_result = {
                "type": "structured",
                "levels": levels_response,
                "ramps": ramps_response,
                "cores": cores_response,
                "metrics": {
                    "totalStalls": metrics.total_stalls,
                    "stallsPerLevel": metrics.stalls_per_level,
                    "levelCount": metrics.level_count,
                    "totalHeight": metrics.total_height,
                    "grossArea": metrics.gross_area,
                    "netParkableArea": metrics.net_parkable_area,
                    "efficiencySfPerStall": metrics.overall_efficiency_sf_per_stall,
                    "stallsLostToRamps": metrics.stalls_lost_to_ramps,
                    "stallsLostToCores": metrics.stalls_lost_to_cores,
                    "stallsLostToConstraints": 0,
                }
            }

        # Calculate elapsed time
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > 1000:
            warnings.append(f"Evaluation took {elapsed_ms:.0f}ms")

        # Build result
        result = EvaluationResultSchema(
            scenarioId=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            parkingResult=parking_result,
            # Now populated when constraints are provided
            constraintImpact=constraint_impact,
            warnings=warnings,
            # v2 response extensions
            v2Zones=v2_zones_response,
            angledStalls=angled_stalls,
            residualRecovered=residual_recovered,
            circulationConnected=circulation_connected,
        )

        return EvaluateResponse(
            success=True,
            result=result,
        )

    except HTTPException:
        raise
    except Exception as e:
        return EvaluateResponse(
            success=False,
            error=str(e),
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "engine": "parking_engine",
        "version": "0.5.0",
        "has_cad_constraints": HAS_CAD_CONSTRAINTS,
        "has_dxf_export": HAS_DXF_EXPORT,
        "has_v2_engine": HAS_V2_ENGINE,
    }


# =============================================================================
# DXF EXPORT ENDPOINT
# =============================================================================

class ExportDxfRequest(BaseModel):
    """Request for DXF export."""
    siteBoundary: PolygonSchema
    parkingConfig: ParkingConfigSchema

    class Config:
        json_schema_extra = {
            "example": {
                "siteBoundary": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 300, "y": 0},
                        {"x": 300, "y": 200},
                        {"x": 0, "y": 200}
                    ]
                },
                "parkingConfig": {
                    "parkingType": "surface",
                    "aisleDirection": "TWO_WAY",
                    "setback": 5.0
                }
            }
        }


@router.post("/export/dxf")
async def export_dxf(request: ExportDxfRequest) -> Response:
    """
    Export parking layout as DXF file.

    Generates a complete parking layout and exports it to DXF format
    suitable for Rhino, AutoCAD, and other CAD software.

    Returns a downloadable DXF file.

    Layers:
        - PARKING_SITE_BOUNDARY: Site boundary polygon
        - PARKING_STALL_STANDARD: Standard parking stalls
        - PARKING_STALL_ADA: ADA accessible stalls
        - PARKING_ACCESS_AISLE: ADA access aisles (hatched area)
        - PARKING_AISLES: Drive aisles and lanes

    Units: Feet (world units)
    """
    # Debug: Log that endpoint was hit

    if not HAS_DXF_EXPORT:
        raise HTTPException(
            status_code=501,
            detail="DXF export not available. Install ezdxf: pip install ezdxf"
        )

    try:
        # Convert site boundary
        site_boundary = schema_to_polygon(request.siteBoundary)

        # Validate site
        if site_boundary.area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid site boundary - area must be positive")

        # Get aisle direction
        aisle_direction = AisleDirection.TWO_WAY
        if request.parkingConfig.aisleDirection == "ONE_WAY":
            aisle_direction = AisleDirection.ONE_WAY

        # Only surface parking supported for v1
        if request.parkingConfig.parkingType != "surface":
            raise HTTPException(
                status_code=400,
                detail="DXF export only supports surface parking in v1"
            )

        # Generate layout
        layout = generate_surface_layout(
            site_boundary=site_boundary,
            aisle_direction=aisle_direction,
            setback=request.parkingConfig.setback,
        )

        # Export to DXF
        dxf_bytes = export_surface_layout_to_dxf(layout)

        # Return as downloadable file
        return Response(
            content=dxf_bytes,
            media_type="application/dxf",
            headers={
                "Content-Disposition": "attachment; filename=parking_layout.dxf"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"DXF export failed: {str(e)}"
        )


# =============================================================================
# DXF IMPORT ENDPOINTS
# =============================================================================

class DxfImportResponseSchema(BaseModel):
    """Response schema for DXF import."""
    success: bool
    polygons: List[PolygonSchema] = []
    warnings: List[str] = []
    entitiesFound: Dict[str, int] = {}
    entitiesImported: int = 0
    entitiesSkipped: int = 0
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None
    errorDetail: Optional[str] = None


@router.post("/import/boundary", response_model=DxfImportResponseSchema)
async def import_boundary_from_dxf(
    file: UploadFile = File(...,
                            description="DXF file containing site boundary")
) -> DxfImportResponseSchema:
    """
    Import site boundary from DXF file.

    The DXF file must contain at least one closed polyline.
    Only 2D closed polylines are supported in v1.

    Supported entities:
        - LWPOLYLINE (closed)
        - POLYLINE (2D, closed)

    Unsupported entities that will cause rejection:
        - SPLINE
        - ELLIPSE
        - 3DSOLID, MESH, SURFACE

    Ignored entities (non-geometric):
        - TEXT, MTEXT, DIMENSION
        - INSERT, BLOCK
        - HATCH

    Returns:
        - success: True if at least one closed polyline was found
        - polygons: List of extracted polygons with points
        - warnings: List of skipped entities or other notes
        - errorCode: Machine-readable error code on failure
        - errorMessage: User-friendly error message on failure
    """
    if not HAS_DXF_IMPORT:
        return DxfImportResponseSchema(
            success=False,
            errorCode="FEATURE_NOT_AVAILABLE",
            errorMessage="DXF import not available. Install ezdxf: pip install ezdxf",
        )

    try:
        # Read file content
        content = await file.read()

        if len(content) == 0:
            return DxfImportResponseSchema(
                success=False,
                errorCode="EMPTY_FILE",
                errorMessage="The uploaded file is empty.",
            )

        # Import the DXF
        result = import_dxf_from_bytes(
            data=content,
            require_closed=True,  # Site boundary must be closed
            layer_filter=None,
        )

        # Convert polygons to response format
        polygons = [
            PolygonSchema(points=[PointSchema(x=p[0], y=p[1])
                          for p in poly.points])
            for poly in result.polygons
        ]

        return DxfImportResponseSchema(
            success=True,
            polygons=polygons,
            warnings=result.warnings,
            entitiesFound=result.entities_found,
            entitiesImported=result.entities_imported,
            entitiesSkipped=result.entities_skipped,
        )

    except DxfImportError as e:
        user_message = get_user_message(e)
        return DxfImportResponseSchema(
            success=False,
            errorCode=e.code.value,
            errorMessage=user_message,
            errorDetail=e.detail,
            entitiesFound=e.entities_found,
        )
    except Exception as e:
        return DxfImportResponseSchema(
            success=False,
            errorCode="UNKNOWN_ERROR",
            errorMessage="An unexpected error occurred during import.",
            errorDetail=str(e),
        )


@router.post("/import/constraints", response_model=DxfImportResponseSchema)
async def import_constraints_from_dxf(
    file: UploadFile = File(..., description="DXF file containing constraints")
) -> DxfImportResponseSchema:
    """
    Import constraints (columns, cores, walls) from DXF file.

    The DXF file may contain polylines (open or closed) representing
    constraints that should be avoided by parking stalls.

    Supported entities:
        - LWPOLYLINE (open or closed)
        - POLYLINE (2D, open or closed)
        - LINE (for wall segments)

    Unsupported entities that will cause rejection:
        - SPLINE
        - ELLIPSE
        - 3DSOLID, MESH, SURFACE

    Ignored entities (non-geometric):
        - TEXT, MTEXT, DIMENSION
        - INSERT, BLOCK
        - HATCH

    Returns:
        - success: True if any geometry was found
        - polygons: List of extracted polygons with points and layer info
        - warnings: List of skipped entities or other notes
        - errorCode: Machine-readable error code on failure
        - errorMessage: User-friendly error message on failure
    """
    if not HAS_DXF_IMPORT:
        return DxfImportResponseSchema(
            success=False,
            errorCode="FEATURE_NOT_AVAILABLE",
            errorMessage="DXF import not available. Install ezdxf: pip install ezdxf",
        )

    try:
        # Read file content
        content = await file.read()

        if len(content) == 0:
            return DxfImportResponseSchema(
                success=False,
                errorCode="EMPTY_FILE",
                errorMessage="The uploaded file is empty.",
            )

        # Import the DXF - constraints don't need to be closed
        result = import_dxf_from_bytes(
            data=content,
            require_closed=False,  # Constraints can be open polylines
            layer_filter=None,
        )

        # Convert polygons to response format
        polygons = [
            PolygonSchema(points=[PointSchema(x=p[0], y=p[1])
                          for p in poly.points])
            for poly in result.polygons
        ]

        return DxfImportResponseSchema(
            success=True,
            polygons=polygons,
            warnings=result.warnings,
            entitiesFound=result.entities_found,
            entitiesImported=result.entities_imported,
            entitiesSkipped=result.entities_skipped,
        )

    except DxfImportError as e:
        user_message = get_user_message(e)
        return DxfImportResponseSchema(
            success=False,
            errorCode=e.code.value,
            errorMessage=user_message,
            errorDetail=e.detail,
            entitiesFound=e.entities_found,
        )
    except Exception as e:
        return DxfImportResponseSchema(
            success=False,
            errorCode="UNKNOWN_ERROR",
            errorMessage="An unexpected error occurred during import.",
            errorDetail=str(e),
        )
