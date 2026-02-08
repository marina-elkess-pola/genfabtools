"""
GenFabTools Parking Engine v2 — Residual Recovery Module

Identifies and recovers parking stalls from residual (leftover) polygons
after zone layouts are complete.

Residual Recovery Process:
1. Calculate residual polygons (site minus zone coverage minus placed stalls)
2. Filter to polygons above minimum area threshold (150 sq ft)
3. Sort in deterministic order: Area (desc), Centroid X, Centroid Y
4. Attempt 60° stall placement in each residual polygon
5. Track recovered stall count

Constraints:
- Recovery is OPTIONAL (recoverResidual = false by default)
- Uses 60° geometry ONLY (no other angles)
- Does NOT modify existing zone layouts
- Does NOT add compact stalls
- No new angles introduced
- No circulation logic

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any, Dict
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union

from sitefit.core.geometry import Point, Polygon, Line
from sitefit.parking.bay import ParkingBay
from sitefit.parking_engine.v2.geometry_60 import (
    Stall60,
    Aisle60,
    create_stall_60,
    create_stall_row_60,
    create_aisle_60,
    create_double_loaded_row_60,
    calculate_stalls_per_row,
    calculate_rows_in_depth,
    AISLE_WIDTH_60,
    ROW_SPACING_60,
    STALL_FOOTPRINT_DEPTH_60,
    STALL_FOOTPRINT_WIDTH_60,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Minimum area for residual polygon processing (sq ft)
MIN_RESIDUAL_AREA: float = 150.0

# Default recovery flag (off by default)
DEFAULT_RECOVER_RESIDUAL: bool = False


# =============================================================================
# RESIDUAL POLYGON TYPES
# =============================================================================

@dataclass(frozen=True)
class ResidualPolygon:
    """
    A residual (leftover) polygon after zone layout.

    Attributes:
        polygon: The residual polygon geometry
        area: Area in square feet
        centroid: Center point for sorting
        source_description: Optional description of origin
    """
    polygon: Polygon
    area: float
    centroid: Point
    source_description: str = ""

    @classmethod
    def from_polygon(cls, polygon: Polygon, source: str = "") -> ResidualPolygon:
        """Create a ResidualPolygon from a Polygon."""
        return cls(
            polygon=polygon,
            area=polygon.area,
            centroid=polygon.centroid,
            source_description=source,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "area": round(self.area, 2),
            "centroid": {"x": round(self.centroid.x, 2), "y": round(self.centroid.y, 2)},
            "source_description": self.source_description,
            "polygon": self.polygon.to_dicts(),
        }


@dataclass
class RecoveryResult:
    """
    Result of residual recovery for a single polygon.

    Attributes:
        residual: The residual polygon that was processed
        stalls_recovered: Number of stalls placed
        stalls: List of 60° stalls placed
        aisles: List of 60° aisles placed
    """
    residual: ResidualPolygon
    stalls_recovered: int
    stalls: List[Stall60] = field(default_factory=list)
    aisles: List[Aisle60] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "residual": self.residual.to_dict(),
            "stalls_recovered": self.stalls_recovered,
            "stalls": [s.to_dict() for s in self.stalls],
            "aisles": [a.to_dict() for a in self.aisles],
        }


@dataclass
class ResidualRecoveryResult:
    """
    Combined result of all residual recovery.

    Attributes:
        residuals_found: Total residual polygons found
        residuals_processed: Number of residuals processed (above min area)
        residuals_skipped: Number of residuals below min area threshold
        total_stalls_recovered: Total stalls recovered from all residuals
        recovery_results: Individual recovery results
        all_stalls: All recovered stalls combined
        all_aisles: All recovered aisles combined
    """
    residuals_found: int
    residuals_processed: int
    residuals_skipped: int
    total_stalls_recovered: int
    recovery_results: List[RecoveryResult] = field(default_factory=list)

    @property
    def all_stalls(self) -> List[Stall60]:
        """Return all recovered stalls from all residuals."""
        stalls = []
        for r in self.recovery_results:
            stalls.extend(r.stalls)
        return stalls

    @property
    def all_aisles(self) -> List[Aisle60]:
        """Return all recovered aisles from all residuals."""
        aisles = []
        for r in self.recovery_results:
            aisles.extend(r.aisles)
        return aisles

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "residuals_found": self.residuals_found,
            "residuals_processed": self.residuals_processed,
            "residuals_skipped": self.residuals_skipped,
            "total_stalls_recovered": self.total_stalls_recovered,
            "recovery_results": [r.to_dict() for r in self.recovery_results],
        }


# =============================================================================
# SORTING FUNCTIONS
# =============================================================================

def _sort_key(residual: ResidualPolygon) -> Tuple[float, float, float]:
    """
    Generate sort key for deterministic ordering.

    Order: Area (descending), Centroid X (ascending), Centroid Y (ascending)

    Args:
        residual: The residual polygon to sort

    Returns:
        Tuple for sorting (negative area for descending)
    """
    return (
        -residual.area,           # Descending by area
        residual.centroid.x,      # Ascending by X
        residual.centroid.y,      # Ascending by Y
    )


def sort_residuals_for_processing(residuals: List[ResidualPolygon]) -> List[ResidualPolygon]:
    """
    Sort residual polygons in deterministic order for processing.

    Order:
    1. Area (descending) - process larger areas first
    2. Centroid X (ascending) - left-to-right
    3. Centroid Y (ascending) - bottom-to-top

    Args:
        residuals: List of residual polygons to sort

    Returns:
        Sorted list of residual polygons
    """
    return sorted(residuals, key=_sort_key)


# =============================================================================
# RESIDUAL DETECTION
# =============================================================================

def _polygon_to_shapely(polygon: Polygon) -> ShapelyPolygon:
    """Convert our Polygon to Shapely Polygon."""
    return polygon.to_shapely()


def _shapely_to_polygon(shapely_poly: ShapelyPolygon) -> Optional[Polygon]:
    """Convert Shapely Polygon back to our Polygon."""
    if shapely_poly.is_empty or shapely_poly.area < 1.0:
        return None

    # Handle both Polygon and MultiPolygon
    if shapely_poly.geom_type == 'MultiPolygon':
        # Return the largest polygon from the MultiPolygon
        largest = max(shapely_poly.geoms, key=lambda g: g.area)
        shapely_poly = largest

    if shapely_poly.geom_type != 'Polygon':
        return None

    # Extract exterior coordinates
    coords = list(shapely_poly.exterior.coords)[:-1]  # Remove closing point
    if len(coords) < 3:
        return None

    vertices = [Point(x, y) for x, y in coords]
    return Polygon(vertices)


def _extract_polygons_from_shapely(shapely_geom) -> List[Polygon]:
    """Extract all polygons from a Shapely geometry (Polygon or MultiPolygon)."""
    polygons = []

    if shapely_geom.is_empty:
        return polygons

    if shapely_geom.geom_type == 'Polygon':
        poly = _shapely_to_polygon(shapely_geom)
        if poly is not None:
            polygons.append(poly)
    elif shapely_geom.geom_type == 'MultiPolygon':
        for geom in shapely_geom.geoms:
            poly = _shapely_to_polygon(geom)
            if poly is not None:
                polygons.append(poly)
    elif shapely_geom.geom_type == 'GeometryCollection':
        for geom in shapely_geom.geoms:
            polygons.extend(_extract_polygons_from_shapely(geom))

    return polygons


def identify_residual_polygons(
    site_boundary: Polygon,
    occupied_polygons: List[Polygon],
    min_area: float = MIN_RESIDUAL_AREA,
) -> Tuple[List[ResidualPolygon], int]:
    """
    Identify residual (leftover) polygons after subtracting occupied areas.

    Args:
        site_boundary: The overall site boundary
        occupied_polygons: List of polygons occupied by stalls/bays
        min_area: Minimum area threshold for processing (default 150 sq ft)

    Returns:
        Tuple of (list of ResidualPolygon above threshold, count of skipped)
    """
    site_shapely = _polygon_to_shapely(site_boundary)

    if not occupied_polygons:
        # Entire site is residual
        residual = ResidualPolygon.from_polygon(site_boundary, "entire_site")
        if residual.area >= min_area:
            return ([residual], 0)
        else:
            return ([], 1)

    # Union all occupied polygons
    occupied_shapely = [_polygon_to_shapely(p) for p in occupied_polygons]
    occupied_union = unary_union(occupied_shapely)

    # Subtract from site
    residual_shapely = site_shapely.difference(occupied_union)

    # Extract all polygons from result
    result_polygons = _extract_polygons_from_shapely(residual_shapely)

    # Create ResidualPolygon objects
    residuals: List[ResidualPolygon] = []
    skipped = 0

    for i, poly in enumerate(result_polygons):
        residual = ResidualPolygon.from_polygon(poly, f"residual_{i}")
        if residual.area >= min_area:
            residuals.append(residual)
        else:
            skipped += 1

    return (residuals, skipped)


# =============================================================================
# RESIDUAL STALL PLACEMENT
# =============================================================================

def recover_stalls_from_residual(
    residual: ResidualPolygon,
    existing_stalls: List[Stall60],
) -> RecoveryResult:
    """
    Attempt to place 60° stalls in a residual polygon.

    Uses the 60° geometry module to fill the residual with stalls.
    Stalls must not overlap with existing stalls.

    Args:
        residual: The residual polygon to fill
        existing_stalls: List of existing stalls to avoid overlap

    Returns:
        RecoveryResult with placed stalls
    """
    polygon = residual.polygon
    min_x, min_y, max_x, max_y = polygon.bounds
    width = max_x - min_x
    height = max_y - min_y

    # Determine primary direction (along longest edge)
    if width >= height:
        direction = "horizontal"
        aisle_length = width
        available_depth = height
    else:
        direction = "vertical"
        aisle_length = height
        available_depth = width

    # Calculate how many rows fit
    num_rows = calculate_rows_in_depth(available_depth)

    if num_rows == 0:
        # Too small for any rows
        return RecoveryResult(
            residual=residual,
            stalls_recovered=0,
        )

    zone_shapely = polygon.to_shapely()
    existing_shapely = [s.polygon.to_shapely() for s in existing_stalls]

    # Track placed stalls during recovery to avoid self-overlap
    placed_shapely: List[ShapelyPolygon] = []

    stalls_60: List[Stall60] = []
    aisles_60: List[Aisle60] = []

    # Generate rows
    for row_idx in range(num_rows):
        if direction == "horizontal":
            # Horizontal aisle
            y_offset = min_y + (row_idx + 0.5) * ROW_SPACING_60
            aisle_start = Point(min_x, y_offset)
            aisle_end = Point(max_x, y_offset)
        else:
            # Vertical aisle
            x_offset = min_x + (row_idx + 0.5) * ROW_SPACING_60
            aisle_start = Point(x_offset, min_y)
            aisle_end = Point(x_offset, max_y)

        aisle = create_aisle_60(aisle_start, aisle_end)

        # Create stall rows on both sides
        left_row = create_stall_row_60(aisle.left_edge, direction=1)
        right_row = create_stall_row_60(
            aisle.right_edge.reversed(), direction=-1)

        row_has_stalls = False

        # Filter stalls: must be in residual and not overlap existing or placed
        # Check against dynamically updated list to avoid overlap within same row
        for stall in left_row.stalls:
            # Build current exclusion list (includes stalls placed so far)
            current_existing = existing_shapely + placed_shapely
            if _stall_valid_for_recovery(stall, zone_shapely, current_existing):
                stalls_60.append(stall)
                placed_shapely.append(stall.polygon.to_shapely())
                row_has_stalls = True

        for stall in right_row.stalls:
            # Build current exclusion list (includes stalls placed so far)
            current_existing = existing_shapely + placed_shapely
            if _stall_valid_for_recovery(stall, zone_shapely, current_existing):
                stalls_60.append(stall)
                placed_shapely.append(stall.polygon.to_shapely())
                row_has_stalls = True

        if row_has_stalls:
            aisles_60.append(aisle)

    return RecoveryResult(
        residual=residual,
        stalls_recovered=len(stalls_60),
        stalls=stalls_60,
        aisles=aisles_60,
    )


def _stall_valid_for_recovery(
    stall: Stall60,
    residual_shapely: ShapelyPolygon,
    existing_shapely: List[ShapelyPolygon],
) -> bool:
    """
    Check if a stall is valid for recovery placement.

    Stall must be:
    1. Fully within the residual polygon
    2. Not overlapping any existing stalls

    Args:
        stall: The stall to check
        residual_shapely: The residual polygon (Shapely)
        existing_shapely: List of existing stall polygons (Shapely)

    Returns:
        True if stall can be placed
    """
    stall_shapely = stall.polygon.to_shapely()

    # Must be within residual
    if not residual_shapely.contains(stall_shapely):
        return False

    # Must not overlap existing stalls
    for existing in existing_shapely:
        if stall_shapely.intersects(existing):
            # Allow touching but not overlapping
            intersection = stall_shapely.intersection(existing)
            if intersection.area > 0.1:  # Tolerance
                return False

    return True


# =============================================================================
# MAIN RECOVERY FUNCTION
# =============================================================================

def perform_residual_recovery(
    site_boundary: Polygon,
    occupied_polygons: List[Polygon],
    existing_stalls: List[Stall60],
    recover_residual: bool = DEFAULT_RECOVER_RESIDUAL,
    min_area: float = MIN_RESIDUAL_AREA,
) -> ResidualRecoveryResult:
    """
    Perform residual recovery pass on leftover areas.

    This is the main entry point for residual recovery. It:
    1. Identifies residual polygons (site minus occupied)
    2. Filters to polygons above minimum area
    3. Sorts in deterministic order
    4. Attempts 60° stall placement in each

    Args:
        site_boundary: The overall site boundary
        occupied_polygons: List of polygons occupied by stalls/bays
        existing_stalls: List of existing 60° stalls (to avoid overlap)
        recover_residual: Whether to perform recovery (False = skip)
        min_area: Minimum area threshold (default 150 sq ft)

    Returns:
        ResidualRecoveryResult with all recovery data
    """
    # If recovery disabled, return empty result
    if not recover_residual:
        return ResidualRecoveryResult(
            residuals_found=0,
            residuals_processed=0,
            residuals_skipped=0,
            total_stalls_recovered=0,
        )

    # Identify residual polygons
    residuals, skipped = identify_residual_polygons(
        site_boundary=site_boundary,
        occupied_polygons=occupied_polygons,
        min_area=min_area,
    )

    total_found = len(residuals) + skipped

    if not residuals:
        return ResidualRecoveryResult(
            residuals_found=total_found,
            residuals_processed=0,
            residuals_skipped=skipped,
            total_stalls_recovered=0,
        )

    # Sort residuals in deterministic order
    sorted_residuals = sort_residuals_for_processing(residuals)

    # Process each residual
    recovery_results: List[RecoveryResult] = []
    total_stalls_recovered = 0
    all_placed_stalls: List[Stall60] = list(existing_stalls)

    for residual in sorted_residuals:
        result = recover_stalls_from_residual(
            residual=residual,
            existing_stalls=all_placed_stalls,
        )
        recovery_results.append(result)
        total_stalls_recovered += result.stalls_recovered

        # Add placed stalls to existing for next iteration
        all_placed_stalls.extend(result.stalls)

    return ResidualRecoveryResult(
        residuals_found=total_found,
        residuals_processed=len(sorted_residuals),
        residuals_skipped=skipped,
        total_stalls_recovered=total_stalls_recovered,
        recovery_results=recovery_results,
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_occupied_polygons_from_bays(bays: List[ParkingBay]) -> List[Polygon]:
    """
    Extract occupied polygons from v1 parking bays.

    Args:
        bays: List of parking bays

    Returns:
        List of bay polygons
    """
    return [bay.bay_polygon for bay in bays if bay.bay_polygon is not None]


def get_occupied_polygons_from_stalls_60(stalls: List[Stall60]) -> List[Polygon]:
    """
    Extract occupied polygons from 60° stalls.

    Args:
        stalls: List of 60° stalls

    Returns:
        List of stall polygons
    """
    return [stall.polygon for stall in stalls]


def get_residual_processing_order(residuals: List[ResidualPolygon]) -> List[str]:
    """
    Get the processing order of residuals (for debugging/testing).

    Args:
        residuals: List of residual polygons

    Returns:
        List of source descriptions in processing order
    """
    sorted_residuals = sort_residuals_for_processing(residuals)
    return [r.source_description for r in sorted_residuals]
