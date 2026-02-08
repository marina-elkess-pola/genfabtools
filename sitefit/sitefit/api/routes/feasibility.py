"""
api/routes/feasibility.py - Feasibility API Routes

Endpoints for site feasibility analysis and full configuration studies.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import time
import uuid

from sitefit.api.schemas import (
    FeasibilityRequest,
    FeasibilityResponse,
    OptimizationRequest,
    OptimizationResponse,
    ConfigurationSummary,
    PointSchema,
    ZoningRequest,
    SetbackRequest
)
from sitefit.core.geometry import Point, Polygon, Rectangle
from sitefit.core.operations import inset as polygon_inset
from sitefit.constraints.zoning import ZoningDistrict
from sitefit.building.massing import generate_massing, MassingConfig
from sitefit.building.floor_plate import FloorConfig

router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def polygon_from_schema(schema) -> Polygon:
    """Convert PolygonSchema to Polygon."""
    points = [Point(p.x, p.y) for p in schema.points]
    return Polygon(points)


def apply_setbacks_to_polygon(boundary: Polygon, setbacks: SetbackRequest) -> Polygon:
    """Apply setbacks to a boundary polygon."""
    # Simple inset - average setback
    avg_setback = (setbacks.front + setbacks.rear +
                   setbacks.left + setbacks.right) / 4
    result = polygon_inset(boundary, avg_setback)
    return result[0] if result else boundary


def create_zoning_district(zoning: ZoningRequest) -> ZoningDistrict:
    """Create ZoningDistrict from request."""
    return ZoningDistrict(
        name=zoning.name,
        max_height_ft=zoning.max_height_ft,
        max_far=zoning.max_far,
        max_lot_coverage=zoning.max_lot_coverage,
        parking_ratio=zoning.parking_ratio
    )


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/analyze", response_model=FeasibilityResponse)
async def analyze_site(request: FeasibilityRequest) -> FeasibilityResponse:
    """
    Perform a full feasibility analysis on a site.

    Calculates buildable area, building capacity, parking requirements,
    and compliance with zoning regulations.
    """
    try:
        # Parse site boundary
        boundary = polygon_from_schema(request.site_boundary)
        site_area = boundary.area

        if site_area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid site boundary")

        # Apply setbacks
        if request.setbacks:
            buildable = apply_setbacks_to_polygon(boundary, request.setbacks)
        else:
            result = polygon_inset(boundary, 10.0)  # Default 10' setback
            buildable = result[0] if result else boundary

        buildable_area = buildable.area

        # Calculate building footprint
        building_footprint_area = buildable_area * request.building_coverage

        # Create building massing
        # Approximate a rectangular footprint from buildable bounds
        min_x, min_y, max_x, max_y = buildable.bounds
        building_width = (max_x - min_x) * 0.6
        building_depth = building_footprint_area / \
            building_width if building_width > 0 else 0

        building_footprint = Rectangle(
            origin=Point(min_x + 20, min_y + 20),
            width=max(50, building_width),
            height=max(50, building_depth)
        ).to_polygon()

        # Generate massing using correct API
        floor_height = 10.0
        config = MassingConfig(
            floor_config=FloorConfig(
                floor_to_floor_height=floor_height, efficiency=0.85)
        )

        massing = generate_massing(
            buildable_polygon=building_footprint,
            num_floors=request.floor_count,
            config=config,
            site_polygon=boundary
        )

        total_gross_area = massing.gross_floor_area
        total_net_area = massing.net_floor_area
        total_height = massing.total_height

        # Estimate units
        avg_unit_size = 900
        estimated_units = int(total_net_area / avg_unit_size)
        site_acres = site_area / 43560
        units_per_acre = estimated_units / site_acres if site_acres > 0 else 0

        # Calculate parking requirements
        required_parking = int(estimated_units * request.parking_ratio)

        # Generate parking in remaining area
        parking_area = site_area - building_footprint_area

        # Estimate parking capacity
        sf_per_stall = 350
        provided_parking = int(parking_area / sf_per_stall)
        parking_surplus = provided_parking - required_parking

        # Calculate FAR
        far = total_gross_area / site_area if site_area > 0 else 0

        # Calculate coverage
        site_coverage = building_footprint_area / site_area if site_area > 0 else 0

        # Check compliance
        compliance_issues = []
        is_compliant = True

        if request.zoning:
            zoning = create_zoning_district(request.zoning)

            if zoning.max_height_ft and total_height > zoning.max_height_ft:
                compliance_issues.append(
                    f"Height {total_height:.0f}' exceeds max {zoning.max_height_ft:.0f}'"
                )
                is_compliant = False

            if zoning.max_far and far > zoning.max_far:
                compliance_issues.append(
                    f"FAR {far:.2f} exceeds max {zoning.max_far:.2f}"
                )
                is_compliant = False

            if zoning.max_lot_coverage and site_coverage > zoning.max_lot_coverage:
                compliance_issues.append(
                    f"Coverage {site_coverage:.0%} exceeds max {zoning.max_lot_coverage:.0%}"
                )
                is_compliant = False

        if parking_surplus < 0:
            compliance_issues.append(
                f"Parking shortfall: {abs(parking_surplus)} stalls needed"
            )
            is_compliant = False

        return FeasibilityResponse(
            site_area=round(site_area, 2),
            buildable_area=round(buildable_area, 2),
            building_footprint=round(building_footprint_area, 2),
            total_gross_area=round(total_gross_area, 2),
            total_net_area=round(total_net_area, 2),
            floor_count=request.floor_count,
            total_height=round(total_height, 2),
            estimated_units=estimated_units,
            units_per_acre=round(units_per_acre, 1),
            required_parking=required_parking,
            provided_parking=provided_parking,
            parking_surplus=parking_surplus,
            far=round(far, 3),
            site_coverage=round(site_coverage, 3),
            is_compliant=is_compliant,
            compliance_issues=compliance_issues
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_site(request: OptimizationRequest) -> OptimizationResponse:
    """
    Find optimal site configurations.

    Generates and scores multiple configurations, returning the best options.
    """
    start_time = time.time()

    try:
        # Parse site boundary
        boundary = polygon_from_schema(request.site_boundary)
        site_area = boundary.area

        if site_area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid site boundary")

        # Generate configurations
        configurations = []

        coverage_min, coverage_max = request.coverage_range
        floor_min, floor_max = request.floor_range

        config_id = 0
        for coverage in [coverage_min, (coverage_min + coverage_max) / 2, coverage_max]:
            for floors in range(floor_min, floor_max + 1, 2):
                for angle in request.parking_angles:
                    config_id += 1

                    # Create a simulated configuration
                    building_footprint = site_area * coverage
                    gross_area = building_footprint * floors
                    net_area = gross_area * 0.85

                    avg_unit_size = 900
                    units = int(net_area / avg_unit_size)

                    parking_area = site_area - building_footprint
                    parking_stalls = int(parking_area / 350)

                    far = gross_area / site_area

                    # Score
                    # Normalize to ~200 units max
                    unit_score = min(1.0, units / 200)
                    parking_ratio = parking_stalls / units if units > 0 else 0
                    parking_score = 1.0 if parking_ratio >= 1.0 else parking_ratio
                    efficiency_score = coverage * 0.5 + 0.5

                    total_score = (unit_score * 0.4 +
                                   parking_score * 0.3 + efficiency_score * 0.3)

                    configurations.append({
                        "id": f"config_{config_id}",
                        "name": f"{floors}F-{int(coverage*100)}%COV-{int(angle)}°",
                        "total_score": round(total_score, 3),
                        "units": units,
                        "parking": parking_stalls,
                        "far": round(far, 2),
                        "coverage": coverage,
                        "floors": floors,
                        "angle": angle,
                        "is_compliant": parking_stalls >= units
                    })

        # Sort by score
        configurations.sort(key=lambda x: x["total_score"], reverse=True)
        configurations = configurations[:request.max_configurations]

        # Add ranks
        for i, cfg in enumerate(configurations):
            cfg["rank"] = i + 1

        elapsed = time.time() - start_time

        # Build response
        best = configurations[0]

        return OptimizationResponse(
            best_configuration=ConfigurationSummary(
                id=best["id"],
                name=best["name"],
                total_score=best["total_score"],
                rank=1,
                units=best["units"],
                parking=best["parking"],
                far=best["far"],
                is_compliant=best["is_compliant"]
            ),
            top_configurations=[
                ConfigurationSummary(
                    id=cfg["id"],
                    name=cfg["name"],
                    total_score=cfg["total_score"],
                    rank=cfg["rank"],
                    units=cfg["units"],
                    parking=cfg["parking"],
                    far=cfg["far"],
                    is_compliant=cfg["is_compliant"]
                )
                for cfg in configurations[:10]
            ],
            configurations_evaluated=len(configurations),
            optimization_time_seconds=round(elapsed, 3)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quick-estimate")
async def quick_estimate(
    site_area_sf: float,
    floors: int = 5,
    coverage: float = 0.4,
    parking_ratio: float = 1.5
) -> Dict[str, Any]:
    """
    Quick feasibility estimate without full analysis.

    Provides rough unit counts and parking capacity based on typical ratios.
    """
    if site_area_sf <= 0:
        raise HTTPException(
            status_code=400, detail="Site area must be positive")

    if floors <= 0 or floors > 50:
        raise HTTPException(
            status_code=400, detail="Floors must be between 1 and 50")

    if coverage <= 0 or coverage > 1:
        raise HTTPException(
            status_code=400, detail="Coverage must be between 0 and 1")

    # Calculate
    building_footprint = site_area_sf * coverage
    gross_area = building_footprint * floors
    net_area = gross_area * 0.85

    avg_unit_size = 900
    estimated_units = int(net_area / avg_unit_size)

    required_parking = int(estimated_units * parking_ratio)

    # Remaining area for parking
    parking_area = site_area_sf - building_footprint
    sf_per_stall = 350
    surface_parking = int(parking_area / sf_per_stall)

    parking_deficit = required_parking - surface_parking

    far = gross_area / site_area_sf
    site_acres = site_area_sf / 43560
    units_per_acre = estimated_units / site_acres if site_acres > 0 else 0

    return {
        "inputs": {
            "site_area_sf": site_area_sf,
            "floors": floors,
            "coverage": coverage,
            "parking_ratio": parking_ratio
        },
        "building": {
            "footprint_sf": round(building_footprint, 0),
            "gross_area_sf": round(gross_area, 0),
            "net_area_sf": round(net_area, 0),
            "far": round(far, 2)
        },
        "units": {
            "estimated_count": estimated_units,
            "average_size_sf": avg_unit_size,
            "units_per_acre": round(units_per_acre, 1)
        },
        "parking": {
            "required": required_parking,
            "surface_capacity": surface_parking,
            "deficit": max(0, parking_deficit),
            "structured_needed": "yes" if parking_deficit > 0 else "no"
        },
        "feasibility": "Appears feasible" if parking_deficit <= 0 else f"Parking shortfall of {parking_deficit} stalls - consider structured parking"
    }
