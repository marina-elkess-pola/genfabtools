"""
api/schemas.py - Pydantic Models for Request/Response

Defines the data models for API input validation and output serialization.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


# =============================================================================
# GEOMETRY SCHEMAS
# =============================================================================

class PointSchema(BaseModel):
    """A 2D point."""
    x: float
    y: float


class PolygonSchema(BaseModel):
    """A polygon defined by a list of points."""
    points: List[PointSchema]

    class Config:
        json_schema_extra = {
            "example": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 80},
                    {"x": 0, "y": 80}
                ]
            }
        }


class RectangleSchema(BaseModel):
    """A rectangle defined by origin, width, and height."""
    origin_x: float = Field(
        0.0, description="X coordinate of bottom-left corner")
    origin_y: float = Field(
        0.0, description="Y coordinate of bottom-left corner")
    width: float = Field(..., description="Width in feet")
    height: float = Field(..., description="Height in feet")


# =============================================================================
# PARKING SCHEMAS
# =============================================================================

class StallTypeEnum(str, Enum):
    """Parking stall types."""
    STANDARD = "standard"
    COMPACT = "compact"
    ACCESSIBLE = "accessible"
    EV = "ev"


class ParkingLayoutRequest(BaseModel):
    """Request for parking layout generation."""
    site_boundary: PolygonSchema
    stall_angle: float = Field(
        90.0, ge=0, le=90, description="Parking angle in degrees")
    stall_type: StallTypeEnum = StallTypeEnum.STANDARD
    include_circulation: bool = True
    exclusion_zones: Optional[List[PolygonSchema]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "site_boundary": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 200, "y": 0},
                        {"x": 200, "y": 150},
                        {"x": 0, "y": 150}
                    ]
                },
                "stall_angle": 90,
                "stall_type": "standard",
                "include_circulation": True
            }
        }


class ParkingOptimizeRequest(BaseModel):
    """Request for parking optimization."""
    site_boundary: PolygonSchema
    angles_to_try: List[float] = Field(
        [0, 45, 60, 90], description="Angles to test")
    min_stalls: Optional[int] = None
    max_iterations: int = Field(10, ge=1, le=100)
    exclusion_zones: Optional[List[PolygonSchema]] = None


class StallResponse(BaseModel):
    """Response for a single parking stall."""
    id: str
    geometry: List[PointSchema]
    stall_type: str
    is_accessible: bool = False


class ParkingLayoutResponse(BaseModel):
    """Response for parking layout."""
    total_stalls: int
    stall_angle: float
    standard_stalls: int
    accessible_stalls: int
    stalls: Optional[List[StallResponse]] = None
    drive_lanes: Optional[List[List[PointSchema]]] = None
    efficiency: float = Field(..., description="Stalls per 1000 SF")
    site_area: float


class ParkingOptimizeResponse(BaseModel):
    """Response for parking optimization."""
    best_angle: float
    best_stall_count: int
    results_by_angle: Dict[str, Any]
    optimization_time_ms: float


# =============================================================================
# BUILDING SCHEMAS
# =============================================================================

class FloorTypeEnum(str, Enum):
    """Floor types."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    RETAIL = "retail"
    PARKING = "parking"
    AMENITY = "amenity"


class UnitMixRequest(BaseModel):
    """Request for unit mix."""
    studios: int = 0
    one_br: int = 0
    two_br: int = 0
    three_br: int = 0
    penthouses: int = 0


class BuildingMassingRequest(BaseModel):
    """Request for building massing."""
    footprint: PolygonSchema
    floor_count: int = Field(..., ge=1, le=100)
    floor_height: float = Field(10.0, ge=8, le=20)
    floor_type: FloorTypeEnum = FloorTypeEnum.RESIDENTIAL
    step_backs: Optional[List[Dict[str, Any]]] = None


class BuildingMassingResponse(BaseModel):
    """Response for building massing."""
    total_gross_area: float
    total_net_area: float
    floor_count: int
    total_height: float
    footprint_area: float
    efficiency: float
    estimated_units: int
    floor_plates: List[Dict[str, Any]]


class UnitMixResponse(BaseModel):
    """Response for unit mix calculation."""
    total_units: int
    studios: int
    one_br: int
    two_br: int
    three_br: int
    average_unit_size: float
    unit_density_per_acre: float


# =============================================================================
# ZONING SCHEMAS
# =============================================================================

class ZoningRequest(BaseModel):
    """Zoning parameters."""
    name: str = "R-4"
    max_height_ft: Optional[float] = None
    max_far: Optional[float] = None
    max_lot_coverage: Optional[float] = None
    parking_ratio: float = 1.5
    front_setback: float = 10.0
    side_setback: float = 5.0
    rear_setback: float = 10.0


class SetbackRequest(BaseModel):
    """Setback requirements."""
    front: float = Field(10.0, ge=0)
    rear: float = Field(10.0, ge=0)
    left: float = Field(5.0, ge=0)
    right: float = Field(5.0, ge=0)


# =============================================================================
# FEASIBILITY SCHEMAS
# =============================================================================

class FeasibilityRequest(BaseModel):
    """Request for feasibility analysis."""
    site_boundary: PolygonSchema
    zoning: Optional[ZoningRequest] = None
    setbacks: Optional[SetbackRequest] = None
    target_units: Optional[int] = None
    parking_ratio: float = Field(1.5, ge=0.5, le=3.0)
    parking_location: str = Field(
        "surface", pattern="^(surface|structure|underground)$")
    building_coverage: float = Field(0.4, ge=0.1, le=0.8)
    floor_count: int = Field(5, ge=1, le=50)

    class Config:
        json_schema_extra = {
            "example": {
                "site_boundary": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 300, "y": 0},
                        {"x": 300, "y": 200},
                        {"x": 0, "y": 200}
                    ]
                },
                "parking_ratio": 1.5,
                "building_coverage": 0.4,
                "floor_count": 5
            }
        }


class FeasibilityResponse(BaseModel):
    """Response for feasibility analysis."""
    site_area: float
    buildable_area: float

    # Building metrics
    building_footprint: float
    total_gross_area: float
    total_net_area: float
    floor_count: int
    total_height: float

    # Unit metrics
    estimated_units: int
    units_per_acre: float

    # Parking metrics
    required_parking: int
    provided_parking: int
    parking_surplus: int

    # Efficiency metrics
    far: float
    site_coverage: float

    # Compliance
    is_compliant: bool
    compliance_issues: List[str]

    # Geometry (optional)
    building_geometry: Optional[List[PointSchema]] = None
    parking_geometry: Optional[List[PointSchema]] = None


# =============================================================================
# OPTIMIZATION SCHEMAS
# =============================================================================

class OptimizationRequest(BaseModel):
    """Request for optimization."""
    site_boundary: PolygonSchema
    zoning: Optional[ZoningRequest] = None
    setbacks: Optional[SetbackRequest] = None
    objective: str = Field(
        "maximize_score", pattern="^(maximize_score|maximize_units|maximize_profit)$")
    parking_angles: List[float] = [45, 90]
    coverage_range: List[float] = Field([0.3, 0.5], min_length=2, max_length=2)
    floor_range: List[int] = Field([4, 8], min_length=2, max_length=2)
    max_configurations: int = Field(50, ge=1, le=500)


class ConfigurationSummary(BaseModel):
    """Summary of a configuration."""
    id: str
    name: str
    total_score: float
    rank: int
    units: int
    parking: int
    far: float
    is_compliant: bool


class OptimizationResponse(BaseModel):
    """Response for optimization."""
    best_configuration: ConfigurationSummary
    top_configurations: List[ConfigurationSummary]
    configurations_evaluated: int
    optimization_time_seconds: float


# =============================================================================
# EXPORT SCHEMAS
# =============================================================================

class ExportFormatEnum(str, Enum):
    """Export formats."""
    JSON = "json"
    GEOJSON = "geojson"
    DXF = "dxf"
    SVG = "svg"


class ExportRequest(BaseModel):
    """Request for export."""
    format: ExportFormatEnum
    include_parking: bool = True
    include_building: bool = True
    include_site: bool = True


class ExportResponse(BaseModel):
    """Response for export."""
    format: str
    content: str
    filename: str
