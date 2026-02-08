"""
SiteGen API routes - Real Estate Feasibility Engine

Provides endpoints for full site feasibility analysis including:
- Building massing optimization
- Parking layout generation  
- Zoning constraint validation
- Multi-configuration comparison
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from sitefit.core.geometry import Polygon, Point
from sitefit.core.operations import buffer
from sitefit.parking.layout_generator import generate_parking_layout
from sitefit.parking.stall import Stall, StallType
# Simplified imports - not using full building/constraints modules yet

router = APIRouter()


# --- Pydantic models ---

class PointModel(BaseModel):
    x: float
    y: float


class ExclusionModel(BaseModel):
    polygon: List[PointModel]


class SiteModel(BaseModel):
    boundary: List[PointModel]
    exclusions: Optional[List[ExclusionModel]] = []


class SetbacksModel(BaseModel):
    front: float = 20
    side: float = 10
    rear: float = 15


class ConstraintsModel(BaseModel):
    far: float = 1.0
    height_limit: float = 45
    lot_coverage: float = 0.5
    parking_ratio: float = 1.5
    setbacks: Optional[SetbacksModel] = None


class OptionsModel(BaseModel):
    parking_angles: Optional[List[int]] = [90]
    building_positions: Optional[List[str]] = ["centered"]
    optimize_for: Optional[str] = "units"  # 'units' | 'parking' | 'efficiency'


class BuildingTypeConfig(BaseModel):
    type: str = "multifamily"
    subtype: str = "midrise"
    config: Optional[Dict[str, Any]] = None


class FeasibilityRequest(BaseModel):
    site: SiteModel
    constraints: ConstraintsModel
    building_type: Optional[BuildingTypeConfig] = None
    options: Optional[OptionsModel] = None


class ConfigurationResult(BaseModel):
    buildable_area: List[PointModel]
    building_footprint: List[PointModel]
    parking: Dict[str, Any]
    score: float


class FeasibilitySummary(BaseModel):
    max_units: int
    parking_stalls: int
    building_sf: float
    floors: int
    efficiency: float
    parking_surplus: int
    # Additional metrics
    rooms: Optional[int] = None
    lots: Optional[int] = None
    mw: Optional[float] = None


class FeasibilityResponse(BaseModel):
    ok: bool
    summary: FeasibilitySummary
    configurations: List[Dict[str, Any]]
    building_type: Optional[str] = None


# --- Helper functions ---

def points_to_polygon(points: List[PointModel]) -> Polygon:
    """Convert list of PointModel to Polygon"""
    return Polygon([Point(p.x, p.y) for p in points])


def polygon_to_points(poly: Polygon) -> List[PointModel]:
    """Convert Polygon to list of PointModel"""
    return [PointModel(x=p.x, y=p.y) for p in poly.vertices]


# --- Routes ---

@router.post("/feasibility", response_model=FeasibilityResponse)
async def generate_feasibility(request: FeasibilityRequest):
    """
    Generate a full feasibility analysis for a site.

    Returns optimized configurations with building massing and parking layouts.
    """
    try:
        # Convert site boundary to Polygon
        site_boundary = points_to_polygon(request.site.boundary)
        site_area = site_boundary.area

        if site_area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid site boundary (zero or negative area)")

        # Convert exclusions
        exclusion_polys = []
        for ex in request.site.exclusions or []:
            exclusion_polys.append(points_to_polygon(ex.polygon))

        # Get constraints
        constraints = request.constraints
        setbacks = constraints.setbacks or SetbacksModel()

        # Calculate buildable area (apply setbacks)
        # For simplicity, use uniform buffer as setback (returns list of polygons)
        avg_setback = (setbacks.front + setbacks.side + setbacks.rear) / 3
        buildable_list = buffer(site_boundary, -avg_setback)

        if not buildable_list or buildable_list[0].area <= 0:
            raise HTTPException(
                status_code=400, detail="No buildable area after setbacks")

        buildable = buildable_list[0]
        buildable_area = buildable.area

        # Get building type config
        bt_config = request.building_type.config if request.building_type and request.building_type.config else {}
        bt_type = request.building_type.type if request.building_type else "multifamily"

        # Calculate max building footprint based on lot coverage
        max_footprint_area = site_area * constraints.lot_coverage

        # Calculate max floors from height
        # Use floor height from building type config, default 12ft
        floor_height = bt_config.get('floorHeight', 12)
        max_floors = int(constraints.height_limit /
                         floor_height) if floor_height > 0 else 1

        # Limit floors based on building type typical floors
        typical_floors = bt_config.get('floors', max_floors)
        max_floors = min(
            max_floors, typical_floors) if typical_floors else max_floors

        # Calculate max building SF from FAR
        max_far_sf = site_area * constraints.far

        # Calculate actual building - use smaller of coverage-limited and FAR-limited
        building_footprint_area = min(max_footprint_area, buildable_area)

        # Stack floors up to FAR or height limit
        total_building_sf = 0
        actual_floors = 0
        for f in range(1, max_floors + 1):
            proposed_sf = building_footprint_area * f
            if proposed_sf <= max_far_sf:
                total_building_sf = proposed_sf
                actual_floors = f
            else:
                break

        if actual_floors == 0:
            actual_floors = 1
            total_building_sf = building_footprint_area

        # Calculate units/rooms based on building type
        efficiency = bt_config.get('efficiency', 0.85)
        net_sf = total_building_sf * efficiency

        # Different unit calculations based on building type
        if bt_type == 'multifamily':
            avg_unit_size = bt_config.get('unitSize', 900)
            max_units = int(net_sf / avg_unit_size)
        elif bt_type == 'hotel':
            room_size = bt_config.get('roomSize', 350)
            max_units = int(net_sf / room_size)
        elif bt_type == 'singlefamily':
            lot_size = bt_config.get('lotSize', 5000)
            max_units = int(site_area / lot_size)
        elif bt_type == 'industrial':
            max_units = int(total_building_sf / 10000)  # Per 10k SF
        elif bt_type == 'retail':
            avg_tenant = bt_config.get('avgTenant', 3000)
            max_units = int(total_building_sf / avg_tenant)
        elif bt_type == 'datacenter':
            power_density = bt_config.get('powerDensity', 100)  # W/SF
            max_units = int(
                (total_building_sf * power_density) / 1000000)  # MW
        elif bt_type == 'parking':
            stalls_per_acre = bt_config.get('stallsPerAcre', 0)
            stalls_per_sf = bt_config.get('stallsPerSF', 0.003)
            if stalls_per_acre:
                max_units = int(site_area / 43560 * stalls_per_acre)
            else:
                max_units = int(total_building_sf * stalls_per_sf)
        else:
            avg_unit_size = bt_config.get('unitSize', 900)
            max_units = int(net_sf / avg_unit_size)

        # Calculate required parking
        required_parking = int(max_units * constraints.parking_ratio)

        # Generate parking layout
        # Use remaining site area outside building footprint
        # For simplicity, generate parking on the full buildable area
        options = request.options or OptionsModel()

        try:
            parking_result = generate_parking_layout(
                site=site_boundary,
                exclusions=exclusion_polys,
                stall_type=StallType.STANDARD,
                angles=options.parking_angles or [90]
            )

            # Convert parking result to response format
            parking_stalls = []
            if parking_result and parking_result.bays:
                stall_id = 1
                for bay in parking_result.bays:
                    for stall in bay.stalls:
                        parking_stalls.append({
                            "id": stall_id,
                            "polygon": [{"x": p.x, "y": p.y} for p in stall.corners],
                            "center": {"x": stall.center.x, "y": stall.center.y},
                            "width": stall.width,
                            "depth": stall.depth,
                            "angle": stall.angle
                        })
                        stall_id += 1

            actual_parking = len(parking_stalls)
        except Exception as e:
            # Fallback if parking generation fails
            parking_stalls = []
            actual_parking = 0

        # Calculate efficiency
        efficiency = (total_building_sf + actual_parking * 162) / \
            site_area  # 162 SF per stall approx

        # Calculate parking surplus/deficit
        parking_surplus = actual_parking - required_parking

        # Build summary
        summary = FeasibilitySummary(
            max_units=max_units,
            parking_stalls=actual_parking,
            building_sf=total_building_sf,
            floors=actual_floors,
            efficiency=min(efficiency, 1.0),
            parking_surplus=parking_surplus
        )

        # Build configuration
        # Scale building footprint based on lot coverage ratio
        # If coverage is less than 100%, inset the buildable area proportionally
        coverage_ratio = min(constraints.lot_coverage, 1.0)

        # Calculate how much to inset based on coverage
        # If buildable is a rectangle with area A and we want area A*coverage,
        # we need to inset by approximately: inset = (1 - sqrt(coverage)) * min_dimension / 2
        import math
        if coverage_ratio < 0.99:
            # Approximate inset to achieve target coverage
            scale_factor = math.sqrt(coverage_ratio)
            # Get bounding box dimensions
            xs = [p.x for p in buildable.vertices]
            ys = [p.y for p in buildable.vertices]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            min_dim = min(width, height)
            inset_amount = (1 - scale_factor) * min_dim / 2

            # Inset the buildable area to get building footprint
            footprint_list = buffer(buildable, -inset_amount)
            if footprint_list and footprint_list[0].area > 0:
                building_footprint_poly = footprint_list[0]
            else:
                building_footprint_poly = buildable
        else:
            building_footprint_poly = buildable

        config = {
            "buildable_area": polygon_to_points(buildable),
            "building_footprint": polygon_to_points(building_footprint_poly),
            "parking": {
                "stalls": parking_stalls,
                "total": actual_parking,
                "required": required_parking,
                "surplus": parking_surplus
            },
            "building": {
                "floors": actual_floors,
                "total_sf": total_building_sf,
                "footprint_sf": building_footprint_area,
                "units": max_units,
                "type": bt_type
            },
            "score": efficiency
        }

        return FeasibilityResponse(
            ok=True,
            summary=summary,
            configurations=[config],
            building_type=bt_type
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "engine": "SiteGen"}
