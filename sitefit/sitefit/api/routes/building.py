"""
api/routes/building.py - Building API Routes

Endpoints for building massing, unit mix, and floor plate analysis.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List

from sitefit.api.schemas import (
    BuildingMassingRequest,
    BuildingMassingResponse,
    UnitMixRequest,
    UnitMixResponse,
    PolygonSchema,
    PointSchema,
    FloorTypeEnum
)
from sitefit.core.geometry import Point, Polygon, Rectangle
from sitefit.building.floor_plate import FloorPlate, FloorType, FloorConfig
from sitefit.building.massing import generate_massing, MassingType, StepBack, MassingConfig
from sitefit.building.unit_mix import calculate_building_unit_mix

router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def polygon_from_schema(schema: PolygonSchema) -> Polygon:
    """Convert PolygonSchema to Polygon."""
    points = [Point(p.x, p.y) for p in schema.points]
    return Polygon(points)


def floor_type_from_schema(type_enum: FloorTypeEnum) -> FloorType:
    """Convert FloorTypeEnum to FloorType.

    Note: The actual FloorType enum has different values than schema enum.
    This maps conceptually similar types.
    """
    mapping = {
        FloorTypeEnum.RESIDENTIAL: FloorType.TYPICAL,  # Typical residential
        FloorTypeEnum.COMMERCIAL: FloorType.TYPICAL,   # Typical office
        FloorTypeEnum.RETAIL: FloorType.GROUND,        # Ground floor retail
        FloorTypeEnum.PARKING: FloorType.PODIUM,       # Parking levels
        FloorTypeEnum.AMENITY: FloorType.AMENITY       # Amenity spaces
    }
    return mapping.get(type_enum, FloorType.TYPICAL)


def is_residential_type(type_enum: FloorTypeEnum) -> bool:
    """Check if this is a residential floor type."""
    return type_enum == FloorTypeEnum.RESIDENTIAL


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/massing", response_model=BuildingMassingResponse)
async def create_building_massing(request: BuildingMassingRequest) -> BuildingMassingResponse:
    """
    Generate building massing from a footprint.

    Creates a 3D building envelope with specified floor count and heights.
    """
    try:
        # Convert footprint
        footprint = polygon_from_schema(request.footprint)
        footprint_area = footprint.area

        if footprint_area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid footprint - area must be positive")

        # Create floor config with requested height
        floor_config = FloorConfig(
            floor_to_floor_height=request.floor_height,
            efficiency=0.85
        )

        # Convert stepbacks if provided
        step_backs = []
        if request.step_backs:
            for sb in request.step_backs:
                step_backs.append(StepBack(
                    above_floor=sb.get("above_floor", 1),
                    setback_distance=sb.get("setback_distance", 10.0)
                ))

        # Create massing config
        config = MassingConfig(
            floor_config=floor_config,
            step_backs=step_backs
        )

        # Generate massing
        massing = generate_massing(
            buildable_polygon=footprint,
            num_floors=request.floor_count,
            config=config
        )

        # Calculate metrics - these are properties, not methods
        total_gross_area = massing.gross_floor_area
        total_net_area = massing.net_floor_area
        total_height = massing.total_height
        efficiency = massing.efficiency

        # Estimate units based on floor type and area
        avg_unit_size = 900  # SF
        is_residential = is_residential_type(request.floor_type)
        estimated_units = int(
            total_net_area / avg_unit_size) if is_residential else 0

        # Build floor plate info
        floor_plates = []
        for plate in massing.floors:
            floor_plates.append({
                "floor_number": plate.floor_number,
                "level": plate.elevation,
                "gross_area": round(plate.gross_area, 2),
                "net_area": round(plate.net_area, 2),
                "height": plate.floor_height,
                "floor_type": plate.floor_type.value
            })

        return BuildingMassingResponse(
            total_gross_area=round(total_gross_area, 2),
            total_net_area=round(total_net_area, 2),
            floor_count=request.floor_count,
            total_height=round(total_height, 2),
            footprint_area=round(footprint_area, 2),
            efficiency=round(efficiency, 3),
            estimated_units=estimated_units,
            floor_plates=floor_plates
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unit-mix", response_model=UnitMixResponse)
async def calculate_unit_mix(
    building_area_sf: float,
    unit_mix: UnitMixRequest
) -> UnitMixResponse:
    """
    Calculate unit mix for a building.

    Given net area and target unit counts, calculates how many of each type fit.
    """
    try:
        if building_area_sf <= 0:
            raise HTTPException(
                status_code=400, detail="Building area must be positive")

        # Define unit sizes (sf) - we don't need UnitSpec objects for simple calculation
        unit_sizes = {
            'studio': 550,
            'one_br': 750,
            'two_br': 1000,
            'three_br': 1350,
            'penthouse': 2000
        }

        # Calculate based on proportions
        total_requested = (
            unit_mix.studios + unit_mix.one_br +
            unit_mix.two_br + unit_mix.three_br + unit_mix.penthouses
        )

        if total_requested == 0:
            # Default mix: 20% studios, 40% 1BR, 30% 2BR, 10% 3BR
            avg_unit_size = 850
            total_units = int(building_area_sf / avg_unit_size)
            studios = int(total_units * 0.20)
            one_br = int(total_units * 0.40)
            two_br = int(total_units * 0.30)
            three_br = total_units - studios - one_br - two_br
            penthouses = 0
        else:
            # Calculate weighted average size
            weighted_area = (
                unit_mix.studios * 550 +
                unit_mix.one_br * 750 +
                unit_mix.two_br * 1000 +
                unit_mix.three_br * 1350 +
                unit_mix.penthouses * 2000
            )
            avg_unit_size = weighted_area / total_requested if total_requested > 0 else 850

            # Scale to fit building area
            max_units = int(building_area_sf / avg_unit_size)
            scale = max_units / total_requested if total_requested > 0 else 1

            studios = int(unit_mix.studios * scale)
            one_br = int(unit_mix.one_br * scale)
            two_br = int(unit_mix.two_br * scale)
            three_br = int(unit_mix.three_br * scale)
            penthouses = int(unit_mix.penthouses * scale)
            total_units = studios + one_br + two_br + three_br + penthouses

        # Calculate density (assume 1 acre = 43560 SF, typical FAR building)
        units_per_acre = (total_units / building_area_sf) * \
            43560 if building_area_sf > 0 else 0

        return UnitMixResponse(
            total_units=total_units,
            studios=studios,
            one_br=one_br,
            two_br=two_br,
            three_br=three_br,
            average_unit_size=round(avg_unit_size, 0),
            unit_density_per_acre=round(units_per_acre, 1)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/floor-types")
async def get_floor_types() -> Dict[str, Any]:
    """Get available floor types and their typical characteristics."""
    return {
        "residential": {
            "efficiency": 0.85,
            "typical_ceiling_height": 9,
            "floor_to_floor_height": 10,
            "description": "Residential apartments or condominiums"
        },
        "commercial": {
            "efficiency": 0.88,
            "typical_ceiling_height": 10,
            "floor_to_floor_height": 13,
            "description": "Office or commercial space"
        },
        "retail": {
            "efficiency": 0.90,
            "typical_ceiling_height": 14,
            "floor_to_floor_height": 16,
            "description": "Ground floor retail space"
        },
        "parking": {
            "efficiency": 0.95,
            "typical_ceiling_height": 8,
            "floor_to_floor_height": 10,
            "description": "Structured parking levels"
        },
        "amenity": {
            "efficiency": 0.80,
            "typical_ceiling_height": 12,
            "floor_to_floor_height": 14,
            "description": "Amenity spaces (gym, pool, clubhouse)"
        }
    }


@router.get("/efficiency-standards")
async def get_efficiency_standards() -> Dict[str, Any]:
    """Get building efficiency standards by building type."""
    return {
        "multifamily_garden": {
            "gross_to_net": 0.85,
            "core_factor": 0.10,
            "description": "Low-rise garden apartments"
        },
        "multifamily_midrise": {
            "gross_to_net": 0.82,
            "core_factor": 0.12,
            "description": "4-7 story residential"
        },
        "multifamily_highrise": {
            "gross_to_net": 0.78,
            "core_factor": 0.15,
            "description": "8+ story residential"
        },
        "office_classA": {
            "gross_to_net": 0.83,
            "core_factor": 0.10,
            "description": "Class A office building"
        },
        "office_classB": {
            "gross_to_net": 0.85,
            "core_factor": 0.08,
            "description": "Class B office building"
        }
    }
