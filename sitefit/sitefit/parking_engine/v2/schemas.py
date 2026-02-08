"""
GenFabTools Parking Engine v2 — API Schemas

Pydantic models for zone-related request/response handling.
These schemas extend v1 API without modifying existing contracts.

v1 remains frozen. These schemas are additive only.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ZoneTypeSchema(str, Enum):
    """
    Zone types for parking areas.

    GENERAL: Standard parking area (default)
    RESERVED: Reserved parking (non-ADA, e.g., employee, visitor, VIP)
    """
    GENERAL = "GENERAL"
    RESERVED = "RESERVED"


class AngleConfigSchema(str, Enum):
    """
    Stall angle configuration.

    90_DEGREES: Perpendicular parking (v1 default)
    60_DEGREES: Angled parking (v2, requires one-way aisles)
    """
    DEGREES_90 = "90_DEGREES"
    DEGREES_60 = "60_DEGREES"


# =============================================================================
# POINT AND POLYGON (Re-export for v2 API)
# =============================================================================

class PointSchema(BaseModel):
    """A 2D point."""
    x: float
    y: float


class PolygonSchema(BaseModel):
    """A polygon defined by a list of points."""
    points: List[PointSchema]

    @field_validator("points")
    @classmethod
    def validate_points(cls, v):
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 points")
        return v


# =============================================================================
# ZONE SCHEMAS
# =============================================================================

class ZoneSchema(BaseModel):
    """
    A parking zone definition.

    Zones partition the parkable area into named regions,
    each with its own stall configuration.
    """
    id: str = Field(
        ...,
        description="Unique zone identifier",
        json_schema_extra={"example": "zone-1"}
    )
    name: str = Field(
        ...,
        description="Human-readable zone name",
        json_schema_extra={"example": "Main Lot"}
    )
    type: ZoneTypeSchema = Field(
        ZoneTypeSchema.GENERAL,
        description="Zone type (GENERAL or RESERVED)"
    )
    polygon: PolygonSchema = Field(
        ...,
        description="Zone boundary polygon"
    )
    angleConfig: AngleConfigSchema = Field(
        AngleConfigSchema.DEGREES_90,
        description="Stall angle (90_DEGREES or 60_DEGREES)"
    )
    stallTargetMin: Optional[int] = Field(
        None,
        ge=0,
        description="Optional minimum stall count"
    )
    stallTargetMax: Optional[int] = Field(
        None,
        ge=0,
        description="Optional maximum stall count"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Zone name cannot be empty")
        return v.strip()

    @field_validator("stallTargetMax")
    @classmethod
    def validate_stall_targets(cls, v, info):
        min_val = info.data.get("stallTargetMin")
        if min_val is not None and v is not None and min_val > v:
            raise ValueError("stallTargetMin cannot exceed stallTargetMax")
        return v


class ZoneResultSchema(BaseModel):
    """
    Zone layout result.

    Returned for each zone after layout generation.
    """
    id: str = Field(..., description="Zone identifier")
    name: str = Field(..., description="Zone name")
    type: ZoneTypeSchema = Field(..., description="Zone type")
    stallCount: int = Field(..., ge=0, description="Number of stalls placed")
    angledStalls: int = Field(
        0,
        ge=0,
        description="Number of 60° angled stalls"
    )
    area: float = Field(..., ge=0, description="Zone area in sq ft")


# =============================================================================
# V2 REQUEST/RESPONSE EXTENSIONS
# =============================================================================

class V2RequestExtension(BaseModel):
    """
    v2 request fields (optional, additive to v1 request).

    All fields have sensible defaults for backwards compatibility.
    If omitted, v1 behavior is used.
    """
    zones: Optional[List[ZoneSchema]] = Field(
        None,
        description="Optional list of zones. If omitted, entire site is one GENERAL zone."
    )
    allowAngledParking: bool = Field(
        False,
        description="Enable 60° angled parking"
    )
    recoverResidual: bool = Field(
        False,
        description="Attempt stall recovery in residual spaces (opt-in)"
    )


class V2ResponseExtension(BaseModel):
    """
    v2 response fields (additive to v1 response).

    These fields are included in the response when v2 features are used.
    """
    zones: Optional[List[ZoneResultSchema]] = Field(
        None,
        description="Per-zone layout results"
    )
    angledStalls: int = Field(
        0,
        ge=0,
        description="Total 60° angled stalls across all zones"
    )
    residualRecovered: int = Field(
        0,
        ge=0,
        description="Stalls recovered from residual spaces"
    )
    circulationConnected: bool = Field(
        True,
        description="Whether all aisles form a connected network"
    )
