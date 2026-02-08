"""
api/routes/parking.py - Parking API Routes

Endpoints for parking layout generation and optimization.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import time
import uuid

from sitefit.api.schemas import (
    ParkingLayoutRequest,
    ParkingLayoutResponse,
    ParkingOptimizeRequest,
    ParkingOptimizeResponse,
    PointSchema,
    StallResponse
)
from sitefit.core.geometry import Point, Polygon, Rectangle
from sitefit.parking.stall import Stall, StallType
from sitefit.parking.bay import ParkingBay
from sitefit.parking.layout_generator import generate_parking_layout
from sitefit.parking.optimizer import optimize_parking

router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def polygon_from_schema(schema) -> Polygon:
    """Convert PolygonSchema to Polygon."""
    points = [Point(p.x, p.y) for p in schema.points]
    return Polygon(points)


def stall_type_from_schema(type_str: str) -> StallType:
    """Convert string to StallType enum."""
    mapping = {
        "standard": StallType.STANDARD,
        "compact": StallType.COMPACT,
        "accessible": StallType.ACCESSIBLE,
        "ev": StallType.EV
    }
    return mapping.get(type_str, StallType.STANDARD)


def stall_to_response(stall: Stall, index: int) -> StallResponse:
    """Convert Stall to StallResponse."""
    corners = stall.get_corners()
    return StallResponse(
        id=f"stall_{index}",
        geometry=[PointSchema(x=p.x, y=p.y) for p in corners],
        stall_type=stall.stall_type.value,
        is_accessible=stall.stall_type == StallType.ACCESSIBLE
    )


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/layout", response_model=ParkingLayoutResponse)
async def create_parking_layout(request: ParkingLayoutRequest) -> ParkingLayoutResponse:
    """
    Generate a parking layout for the given site boundary.

    Returns stall positions, drive lanes, and efficiency metrics.
    """
    try:
        # Convert boundary
        boundary = polygon_from_schema(request.site_boundary)
        site_area = boundary.area

        if site_area <= 0:
            raise HTTPException(
                status_code=400, detail="Invalid site boundary - area must be positive")

        # Map stall type
        stall_type_str = {
            "standard": "standard",
            "compact": "compact",
            "accessible": "ada",
            "ev": "standard"
        }.get(request.stall_type.value, "standard")

        # Generate layout directly with the polygon
        result = generate_parking_layout(
            site=boundary,
            stall_type=stall_type_str,
            angles=[request.stall_angle]  # Test only the requested angle
        )

        # Get total stalls from result
        total_stalls = result.total_stalls

        # Calculate efficiency (stalls per 1000 SF)
        efficiency = (total_stalls / site_area) * 1000 if site_area > 0 else 0

        # Get stalls from all bays
        stalls = []
        stall_index = 0
        for bay in result.bays:
            for placement in bay.all_stalls:
                corners = [
                    PointSchema(x=v.x, y=v.y) for v in placement.polygon.vertices
                ]
                stalls.append(StallResponse(
                    id=f"stall_{stall_index}",
                    geometry=corners,
                    stall_type=placement.stall.stall_type.value if hasattr(
                        placement.stall, 'stall_type') else "standard",
                    is_accessible=False
                ))
                stall_index += 1

        return ParkingLayoutResponse(
            total_stalls=total_stalls,
            stall_angle=request.stall_angle,
            standard_stalls=total_stalls,
            accessible_stalls=0,
            stalls=stalls,
            efficiency=round(efficiency, 2),
            site_area=round(site_area, 2)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize", response_model=ParkingOptimizeResponse)
async def optimize_parking_endpoint(request: ParkingOptimizeRequest) -> ParkingOptimizeResponse:
    """
    Find the optimal parking layout by testing multiple angles.

    Returns the best configuration and comparison of all tested angles.
    """
    start_time = time.time()

    try:
        # Convert boundary
        boundary = polygon_from_schema(request.site_boundary)
        site_area = boundary.area

        # Test each angle
        results_by_angle: Dict[str, Any] = {}
        best_angle = 90.0
        best_count = 0

        for angle in request.angles_to_try:
            result = generate_parking_layout(
                site=boundary,
                angles=[angle]
            )

            stall_count = result.total_stalls
            results_by_angle[str(angle)] = {
                "stall_count": stall_count,
                "efficiency": round((stall_count / site_area) * 1000, 2) if site_area > 0 else 0
            }

            if stall_count > best_count:
                best_count = stall_count
                best_angle = angle

        elapsed_ms = (time.time() - start_time) * 1000

        return ParkingOptimizeResponse(
            best_angle=best_angle,
            best_stall_count=best_count,
            results_by_angle=results_by_angle,
            optimization_time_ms=round(elapsed_ms, 2)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stall-dimensions")
async def get_stall_dimensions() -> Dict[str, Any]:
    """Get standard stall dimensions for different types."""
    return {
        "standard": {
            "width": 9.0,
            "length": 18.0,
            "description": "Standard parking stall"
        },
        "compact": {
            "width": 8.0,
            "length": 16.0,
            "description": "Compact vehicle stall"
        },
        "accessible": {
            "width": 11.0,
            "length": 18.0,
            "description": "ADA accessible stall with access aisle"
        },
        "ev": {
            "width": 9.0,
            "length": 18.0,
            "description": "Electric vehicle charging stall"
        },
        "drive_aisle": {
            "one_way": 12.0,
            "two_way": 24.0,
            "description": "Drive aisle widths"
        }
    }


@router.get("/efficiency-estimate")
async def estimate_efficiency(
    area_sf: float,
    stall_angle: float = 90.0
) -> Dict[str, Any]:
    """
    Estimate parking capacity for a given area.

    Uses industry-standard ratios for quick estimation.
    """
    if area_sf <= 0:
        raise HTTPException(status_code=400, detail="Area must be positive")

    # Industry estimates: 300-350 SF per stall including circulation
    # Angle efficiency adjustments
    angle_efficiency = {
        0: 0.85,   # Parallel - least efficient
        45: 1.0,   # 45-degree - baseline
        60: 1.05,  # 60-degree - slightly better
        90: 1.1    # 90-degree - most efficient for space
    }

    base_sf_per_stall = 325
    efficiency_factor = angle_efficiency.get(int(stall_angle), 1.0)
    adjusted_sf_per_stall = base_sf_per_stall / efficiency_factor

    estimated_stalls = int(area_sf / adjusted_sf_per_stall)

    return {
        "area_sf": area_sf,
        "stall_angle": stall_angle,
        "estimated_stalls": estimated_stalls,
        "sf_per_stall": round(adjusted_sf_per_stall, 1),
        "note": "Estimate based on typical surface parking ratios. Actual count may vary based on site geometry."
    }
