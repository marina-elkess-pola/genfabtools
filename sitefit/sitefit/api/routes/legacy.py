"""
api/routes/legacy.py - Legacy API Compatibility Routes

Provides endpoints matching the python_engine/app.py API format so
existing ParkCore frontend works seamlessly with SiteFit.

Endpoints:
- POST /parking/generate - Generate parking layouts
- POST /parking/circulation - Generate parallel module layouts
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from sitefit.core.geometry import Point, Polygon, Rectangle
from sitefit.parking.layout_generator import generate_parking_layout, LayoutResult
from sitefit.parking.optimizer import optimize_parking

router = APIRouter()


# =============================================================================
# LEGACY REQUEST/RESPONSE MODELS (matching python_engine)
# =============================================================================

class LegacyPoint(BaseModel):
    x: float
    y: float


class LegacyConstraints(BaseModel):
    stallWidth: float = 9.0
    stallLength: float = 18.0
    aisleWidth: float = 24.0
    angleDeg: float = 90.0
    setback: float = 5.0


class LegacyExclusionZone(BaseModel):
    type: str = "exclusion"
    polygon: List[LegacyPoint]


class LegacyGenerateRequest(BaseModel):
    boundary: Optional[List[LegacyPoint]] = None
    constraints: Optional[LegacyConstraints] = None
    exclusions: Optional[List[LegacyExclusionZone]] = None
    parkingType: str = "surface"
    numLevels: int = 1


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def legacy_points_to_polygon(points: List[LegacyPoint]) -> Polygon:
    """Convert legacy point list to SiteFit Polygon."""
    return Polygon([Point(p.x, p.y) for p in points])


def layout_result_to_legacy(result: LayoutResult, name: str = "sitefit-layout") -> Dict[str, Any]:
    """Convert SiteFit LayoutResult to legacy python_engine format."""
    # Extract stalls from bays
    stalls = []
    stall_id = 0

    for bay in result.bays:
        for placement in bay.all_stalls:
            stall_id += 1
            polygon = placement.polygon
            verts = polygon.vertices
            center = polygon.centroid
            stalls.append({
                "id": stall_id,
                "polygon": [{"x": v.x, "y": v.y} for v in verts],
                "center": {"x": center.x, "y": center.y},
                "width": bay.stall.width,
                "depth": bay.stall.depth,
                "angle": bay.stall.angle  # Use stall.angle, not bay.angle
            })

    # Extract aisle/street geometry from bays
    streets = []
    for i, bay in enumerate(result.bays):
        aisle_poly = bay.aisle_polygon
        if aisle_poly:
            bounds = aisle_poly.bounds
            streets.append({
                "id": i + 1,
                "polyline": [
                    {"x": bounds[0], "y": (bounds[1] + bounds[3]) / 2},
                    {"x": bounds[2], "y": (bounds[1] + bounds[3]) / 2}
                ],
                "width": bay.aisle.width,
                "from": {"x": bounds[0], "y": (bounds[1] + bounds[3]) / 2},
                "to": {"x": bounds[2], "y": (bounds[1] + bounds[3]) / 2}
            })

    return {
        "name": name,
        "streets": streets,
        "aisles": [],
        "stalls": stalls,
        "stallCount": len(stalls),
        "connected": True,
        "safeZone": [],
        "stats": {
            "total_stalls": result.total_stalls,
            "bay_count": len(result.bays),
            "angle": result.angle,
            "efficiency": result.efficiency
        }
    }


# =============================================================================
# LEGACY ENDPOINTS
# =============================================================================

@router.post("/generate")
async def parking_generate(req: LegacyGenerateRequest) -> Dict[str, Any]:
    """
    Generate parking layouts - compatible with python_engine API.

    Returns optimized layouts at multiple angles.
    """
    try:
        # Parse boundary
        if req.boundary and len(req.boundary) >= 3:
            site = legacy_points_to_polygon(req.boundary)
        else:
            # Default rectangle
            site = Rectangle(
                origin=Point(0, 0),
                width=200,
                height=150
            ).to_polygon()

        # Parse exclusions
        exclusions = []
        if req.exclusions:
            for exc in req.exclusions:
                if exc.polygon and len(exc.polygon) >= 3:
                    exclusions.append(legacy_points_to_polygon(exc.polygon))

        # Generate layout using correct API
        result = generate_parking_layout(
            site=site,
            exclusions=exclusions if exclusions else None,
            stall_type="standard",
            double_loaded=True,
            angles=[90, 60, 45, 0]
        )

        iterations = []
        if result and result.total_stalls > 0:
            layout = layout_result_to_legacy(result, f"{result.angle}° layout")

            # Multiply by levels if structured
            if req.parkingType != "surface" and req.numLevels > 1:
                layout["stallCount"] *= req.numLevels
                layout["name"] += f" × {req.numLevels} levels"

            iterations.append(layout)

        return {
            "ok": True,
            "iterations": iterations,
            "parkingType": req.parkingType,
            "numLevels": req.numLevels
        }

    except Exception as e:
        print(f"[ERROR] parking_generate failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "error": str(e),
            "iterations": [],
            "parkingType": req.parkingType or "surface",
            "numLevels": 1
        }


@router.post("/circulation")
async def parking_circulation(req: LegacyGenerateRequest) -> Dict[str, Any]:
    """
    Generate parallel module parking layout - compatible with python_engine API.

    Uses 60ft module spacing with optimized stall placement.
    """
    try:
        # Parse boundary
        if req.boundary and len(req.boundary) >= 3:
            site = legacy_points_to_polygon(req.boundary)
        else:
            site = Rectangle(
                origin=Point(0, 0),
                width=200,
                height=150
            ).to_polygon()

        # Parse exclusions
        exclusions = []
        if req.exclusions:
            for exc in req.exclusions:
                if exc.polygon and len(exc.polygon) >= 3:
                    exclusions.append(legacy_points_to_polygon(exc.polygon))

        # Use optimizer to find best configuration at 90° (parallel module)
        summary = optimize_parking(
            site=site,
            exclusions=exclusions if exclusions else None,
            objective="max_stalls",
            angles=[90],  # Parallel module uses 90° stalls
            min_stalls=0
        )

        if summary.best_result:
            layout = layout_result_to_legacy(
                summary.best_result.layout, "parallel-module-60ft")

            # Add module-specific stats
            layout["stats"]["module_spacing"] = 60.0
            layout["stats"]["first_line_offset"] = 30.0

            return {
                "ok": True,
                "iterations": [layout],
                "parkingType": req.parkingType,
                "numLevels": req.numLevels
            }
        else:
            return {
                "ok": True,
                "iterations": [],
                "parkingType": req.parkingType,
                "numLevels": req.numLevels
            }

    except Exception as e:
        print(f"[ERROR] parking_circulation failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "error": str(e),
            "iterations": [],
            "parkingType": "surface",
            "numLevels": 1
        }
