"""
Irregular Geometry Support
==========================

Extends the geometry processor to handle irregular site polygons
through rectangular decomposition.

Supported geometries:
- L-shaped polygons
- Rectangles with internal voids (cut-outs)
- Convex or mildly concave polygons
- Rectangles with skewed edges

Strategy: Decomposition-first approach
1. Identify largest inscribed rectangles
2. Apply existing rectangular engine to those zones
3. Track remaining unusable areas

All outputs are conceptual and advisory.
This module prioritizes predictability over optimization.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set
from enum import Enum

from .geometry import Polygon, Point


class ZoneType(Enum):
    """Classification of parking zones within irregular sites."""
    RECTANGULAR = "rectangular"      # Full rectangular zone, double-loaded bays
    REMNANT = "remnant"              # Irregular remainder, single-loaded only
    UNUSABLE = "unusable"            # Too narrow/irregular for parking
    VOID = "void"                    # Internal exclusion zone


@dataclass
class ParkingZone:
    """
    A rectangular sub-zone extracted from an irregular site.

    Each zone can be processed independently by the rectangular
    parking engine, then aggregated into the final layout.
    """
    id: str
    geometry: Polygon
    zone_type: ZoneType
    parent_zone_id: Optional[str] = None

    @property
    def area(self) -> float:
        return self.geometry.area

    @property
    def is_parkable(self) -> bool:
        return self.zone_type in (ZoneType.RECTANGULAR, ZoneType.REMNANT)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "geometry": self.geometry.to_dict(),
            "zone_type": self.zone_type.value,
            "area_sf": self.area,
            "is_parkable": self.is_parkable,
        }


@dataclass
class DecompositionResult:
    """
    Result of decomposing an irregular polygon into parking zones.
    """
    original_polygon: Polygon
    zones: List[ParkingZone]
    voids: List[Polygon]

    @property
    def total_area(self) -> float:
        return self.original_polygon.area

    @property
    def parkable_area(self) -> float:
        return sum(z.area for z in self.zones if z.is_parkable)

    @property
    def unusable_area(self) -> float:
        return sum(z.area for z in self.zones if not z.is_parkable)

    @property
    def void_area(self) -> float:
        return sum(v.area for v in self.voids)

    @property
    def usability_ratio(self) -> float:
        if self.total_area == 0:
            return 0.0
        return self.parkable_area / self.total_area

    def to_dict(self) -> dict:
        return {
            "total_area_sf": self.total_area,
            "parkable_area_sf": self.parkable_area,
            "unusable_area_sf": self.unusable_area,
            "void_area_sf": self.void_area,
            "usability_ratio": round(self.usability_ratio, 3),
            "zone_count": len(self.zones),
            "zones": [z.to_dict() for z in self.zones],
        }


# =============================================================================
# POLYGON ANALYSIS
# =============================================================================

def is_axis_aligned_polygon(polygon: Polygon) -> bool:
    """
    Check if all edges of a polygon are axis-aligned (horizontal or vertical).

    This is a prerequisite for simple rectangular decomposition.
    """
    n = len(polygon.vertices)
    if n < 3:
        return False

    for i in range(n):
        p1 = polygon.vertices[i]
        p2 = polygon.vertices[(i + 1) % n]

        # Edge must be horizontal (same y) or vertical (same x)
        if abs(p1.x - p2.x) > 1e-6 and abs(p1.y - p2.y) > 1e-6:
            return False

    return True


def classify_polygon(polygon: Polygon) -> str:
    """
    Classify a polygon by its shape characteristics.

    Returns:
        "rectangle" - 4 vertices, axis-aligned
        "l_shape" - 6 vertices, axis-aligned (L or T shape)
        "orthogonal" - axis-aligned with more than 6 vertices
        "convex" - all interior angles < 180°
        "concave" - has at least one interior angle > 180°
        "complex" - cannot be simply classified
    """
    n = len(polygon.vertices)

    if polygon.is_rectangular:
        return "rectangle"

    if is_axis_aligned_polygon(polygon):
        if n == 6:
            return "l_shape"
        else:
            return "orthogonal"

    # Check convexity
    if is_convex(polygon):
        return "convex"

    return "concave"


def is_convex(polygon: Polygon) -> bool:
    """
    Check if a polygon is convex (all interior angles < 180°).
    """
    n = len(polygon.vertices)
    if n < 3:
        return False

    sign = None
    for i in range(n):
        p0 = polygon.vertices[i]
        p1 = polygon.vertices[(i + 1) % n]
        p2 = polygon.vertices[(i + 2) % n]

        # Cross product of consecutive edges
        cross = (p1.x - p0.x) * (p2.y - p1.y) - (p1.y - p0.y) * (p2.x - p1.x)

        if abs(cross) < 1e-9:
            continue  # Collinear points

        current_sign = cross > 0
        if sign is None:
            sign = current_sign
        elif sign != current_sign:
            return False

    return True


def get_concave_vertices(polygon: Polygon) -> List[int]:
    """
    Identify indices of concave (reflex) vertices in a polygon.

    A concave vertex has an interior angle > 180°.
    """
    n = len(polygon.vertices)
    concave = []

    # Determine winding direction from signed area
    signed_area = 0.0
    for i in range(n):
        j = (i + 1) % n
        signed_area += polygon.vertices[i].x * polygon.vertices[j].y
        signed_area -= polygon.vertices[j].x * polygon.vertices[i].y

    is_ccw = signed_area > 0

    for i in range(n):
        p0 = polygon.vertices[(i - 1) % n]
        p1 = polygon.vertices[i]
        p2 = polygon.vertices[(i + 1) % n]

        cross = (p1.x - p0.x) * (p2.y - p1.y) - (p1.y - p0.y) * (p2.x - p1.x)

        # For CCW polygon, negative cross product indicates concave vertex
        if is_ccw and cross < -1e-9:
            concave.append(i)
        elif not is_ccw and cross > 1e-9:
            concave.append(i)

    return concave


# =============================================================================
# RECTANGULAR DECOMPOSITION
# =============================================================================

def decompose_l_shape(polygon: Polygon) -> List[Polygon]:
    """
    Decompose an L-shaped (6-vertex) axis-aligned polygon into 2 rectangles.

    Strategy: Find the concave vertex and split along its axis.
    """
    if len(polygon.vertices) != 6:
        raise ValueError("L-shape decomposition requires exactly 6 vertices")

    if not is_axis_aligned_polygon(polygon):
        raise ValueError("L-shape decomposition requires axis-aligned polygon")

    # Find the concave vertex
    concave_indices = get_concave_vertices(polygon)
    if len(concave_indices) != 1:
        # Not a simple L-shape, fall back to bounding box decomposition
        return decompose_by_bounding_box(polygon)

    concave_idx = concave_indices[0]
    concave_pt = polygon.vertices[concave_idx]

    # Get bounding box
    min_x, min_y, max_x, max_y = polygon.bounds

    # Determine split direction based on concave vertex position
    # The concave vertex is at the "inner corner" of the L

    # Find adjacent vertices to understand L orientation
    prev_pt = polygon.vertices[(concave_idx - 1) % 6]
    next_pt = polygon.vertices[(concave_idx + 1) % 6]

    rectangles = []

    # Horizontal split (concave vertex defines a horizontal line)
    if abs(prev_pt.y - concave_pt.y) < 1e-6 or abs(next_pt.y - concave_pt.y) < 1e-6:
        # Split horizontally at concave_pt.y
        split_y = concave_pt.y

        # Determine which horizontal strip contains the concave point
        # and split accordingly
        if split_y > (min_y + max_y) / 2:
            # Concave is in upper half - bottom is full width, top is partial
            # Bottom rectangle
            bottom_width = max_x - min_x
            # Find the vertical edge at the concave point
            if concave_pt.x > (min_x + max_x) / 2:
                # L opens to the right
                rectangles.append(Polygon.from_bounds(
                    min_x, min_y, max_x, split_y))
                rectangles.append(Polygon.from_bounds(
                    min_x, split_y, concave_pt.x, max_y))
            else:
                # L opens to the left
                rectangles.append(Polygon.from_bounds(
                    min_x, min_y, max_x, split_y))
                rectangles.append(Polygon.from_bounds(
                    concave_pt.x, split_y, max_x, max_y))
        else:
            # Concave is in lower half
            if concave_pt.x > (min_x + max_x) / 2:
                rectangles.append(Polygon.from_bounds(
                    min_x, split_y, max_x, max_y))
                rectangles.append(Polygon.from_bounds(
                    min_x, min_y, concave_pt.x, split_y))
            else:
                rectangles.append(Polygon.from_bounds(
                    min_x, split_y, max_x, max_y))
                rectangles.append(Polygon.from_bounds(
                    concave_pt.x, min_y, max_x, split_y))

    # Vertical split
    elif abs(prev_pt.x - concave_pt.x) < 1e-6 or abs(next_pt.x - concave_pt.x) < 1e-6:
        split_x = concave_pt.x

        if split_x > (min_x + max_x) / 2:
            if concave_pt.y > (min_y + max_y) / 2:
                rectangles.append(Polygon.from_bounds(
                    min_x, min_y, split_x, max_y))
                rectangles.append(Polygon.from_bounds(
                    split_x, min_y, max_x, concave_pt.y))
            else:
                rectangles.append(Polygon.from_bounds(
                    min_x, min_y, split_x, max_y))
                rectangles.append(Polygon.from_bounds(
                    split_x, concave_pt.y, max_x, max_y))
        else:
            if concave_pt.y > (min_y + max_y) / 2:
                rectangles.append(Polygon.from_bounds(
                    split_x, min_y, max_x, max_y))
                rectangles.append(Polygon.from_bounds(
                    min_x, min_y, split_x, concave_pt.y))
            else:
                rectangles.append(Polygon.from_bounds(
                    split_x, min_y, max_x, max_y))
                rectangles.append(Polygon.from_bounds(
                    min_x, concave_pt.y, split_x, max_y))

    if not rectangles:
        # Fallback: use bounding box decomposition
        return decompose_by_bounding_box(polygon)

    # Validate rectangles are within original polygon
    valid_rectangles = []
    for rect in rectangles:
        if rect.area > 0 and rect.width > 0 and rect.height > 0:
            valid_rectangles.append(rect)

    return valid_rectangles if valid_rectangles else decompose_by_bounding_box(polygon)


def decompose_by_bounding_box(polygon: Polygon) -> List[Polygon]:
    """
    Decompose a polygon by finding the largest inscribed rectangle.

    For irregular polygons, this finds a conservative rectangular
    approximation that fits entirely within the polygon.

    Limitation: This is a heuristic, not an optimal solution.
    """
    min_x, min_y, max_x, max_y = polygon.bounds

    # For axis-aligned polygons, try to find inscribed rectangles
    if is_axis_aligned_polygon(polygon):
        return _decompose_orthogonal_polygon(polygon)

    # For general polygons, use the bounding box shrunk to fit
    # This is a conservative approximation
    inscribed = find_largest_inscribed_rectangle(polygon)
    if inscribed and inscribed.area > 0:
        return [inscribed]

    return []


def _decompose_orthogonal_polygon(polygon: Polygon) -> List[Polygon]:
    """
    Decompose an orthogonal (axis-aligned) polygon into rectangles.

    Uses a horizontal sweep approach to identify rectangular regions.
    """
    if polygon.is_rectangular:
        return [polygon]

    # Collect all unique Y coordinates
    y_coords = sorted(set(v.y for v in polygon.vertices))

    rectangles = []

    # Sweep through horizontal strips
    for i in range(len(y_coords) - 1):
        y_min = y_coords[i]
        y_max = y_coords[i + 1]

        # Find the X extent of the polygon at this Y level
        x_extents = _get_x_extents_at_y(polygon, (y_min + y_max) / 2)

        for x_min, x_max in x_extents:
            if x_max > x_min:
                rect = Polygon.from_bounds(x_min, y_min, x_max, y_max)
                if rect.area > 0:
                    rectangles.append(rect)

    return rectangles


def _get_x_extents_at_y(polygon: Polygon, y: float) -> List[Tuple[float, float]]:
    """
    Get the X extents (horizontal segments) of a polygon at a given Y level.

    Returns list of (x_min, x_max) tuples for each horizontal segment.
    """
    n = len(polygon.vertices)
    intersections = []

    # Find all edge intersections with the horizontal line y
    for i in range(n):
        p1 = polygon.vertices[i]
        p2 = polygon.vertices[(i + 1) % n]

        # Skip horizontal edges
        if abs(p1.y - p2.y) < 1e-9:
            continue

        # Check if edge crosses y
        if (p1.y <= y <= p2.y) or (p2.y <= y <= p1.y):
            # Linear interpolation to find x at y
            t = (y - p1.y) / (p2.y - p1.y)
            x = p1.x + t * (p2.x - p1.x)
            intersections.append(x)

    # Sort and pair intersections
    intersections.sort()

    extents = []
    for i in range(0, len(intersections) - 1, 2):
        if i + 1 < len(intersections):
            extents.append((intersections[i], intersections[i + 1]))

    return extents


def find_largest_inscribed_rectangle(polygon: Polygon) -> Optional[Polygon]:
    """
    Find the largest axis-aligned rectangle inscribed in a polygon.

    Uses a sampling-based heuristic for non-orthogonal polygons.
    This is NOT an optimal algorithm, but provides a reasonable approximation.
    """
    min_x, min_y, max_x, max_y = polygon.bounds

    # For rectangular polygons, return as-is
    if polygon.is_rectangular:
        return polygon

    # Sample approach: try shrinking from bounding box
    # Start with bounding box and shrink until it fits
    best_rect = None
    best_area = 0.0

    # Try centered rectangles at various scales
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    width = max_x - min_x
    height = max_y - min_y

    for scale in [0.9, 0.8, 0.7, 0.6, 0.5]:
        scaled_w = width * scale
        scaled_h = height * scale

        rect = Polygon.from_bounds(
            cx - scaled_w / 2, cy - scaled_h / 2,
            cx + scaled_w / 2, cy + scaled_h / 2
        )

        if polygon_contains_rectangle(polygon, rect):
            if rect.area > best_area:
                best_area = rect.area
                best_rect = rect
                break  # First fit is likely the largest

    # Also try corner-aligned rectangles
    for anchor_x in [min_x, max_x]:
        for anchor_y in [min_y, max_y]:
            for scale in [0.8, 0.6, 0.4]:
                if anchor_x == min_x:
                    rx_min = min_x
                    rx_max = min_x + width * scale
                else:
                    rx_min = max_x - width * scale
                    rx_max = max_x

                if anchor_y == min_y:
                    ry_min = min_y
                    ry_max = min_y + height * scale
                else:
                    ry_min = max_y - height * scale
                    ry_max = max_y

                rect = Polygon.from_bounds(rx_min, ry_min, rx_max, ry_max)

                if polygon_contains_rectangle(polygon, rect) and rect.area > best_area:
                    best_area = rect.area
                    best_rect = rect

    return best_rect


def polygon_contains_rectangle(polygon: Polygon, rect: Polygon) -> bool:
    """
    Check if a polygon fully contains a rectangle.

    Checks all four corners of the rectangle.
    """
    for vertex in rect.vertices:
        if not polygon.contains_point(vertex):
            return False
    return True


# =============================================================================
# ZONE EXTRACTION
# =============================================================================

def extract_parking_zones(
    polygon: Polygon,
    voids: Optional[List[Polygon]] = None,
    min_zone_width: float = 40.0,
    min_zone_area: float = 1000.0,
) -> DecompositionResult:
    """
    Extract parkable rectangular zones from an irregular polygon.

    This is the main entry point for irregular geometry processing.

    Args:
        polygon: Site boundary polygon (may be irregular)
        voids: Internal exclusion zones (cut-outs)
        min_zone_width: Minimum width for a parkable zone (feet)
        min_zone_area: Minimum area for a parkable zone (square feet)

    Returns:
        DecompositionResult with classified zones
    """
    voids = voids or []

    # If rectangular, return as single zone
    if polygon.is_rectangular:
        zone = ParkingZone(
            id="zone_0",
            geometry=polygon,
            zone_type=ZoneType.RECTANGULAR,
        )
        return DecompositionResult(
            original_polygon=polygon,
            zones=[zone],
            voids=voids,
        )

    # Classify polygon
    poly_type = classify_polygon(polygon)

    # Decompose based on type
    if poly_type == "l_shape":
        rectangles = decompose_l_shape(polygon)
    elif poly_type == "orthogonal":
        rectangles = _decompose_orthogonal_polygon(polygon)
    else:
        # Convex or concave: find inscribed rectangles
        rectangles = decompose_by_bounding_box(polygon)

    # Subtract voids from rectangles
    if voids:
        rectangles = _subtract_voids_from_rectangles(rectangles, voids)

    # Classify zones
    zones = []
    zone_idx = 0

    for rect in rectangles:
        if rect.area < min_zone_area:
            zone_type = ZoneType.UNUSABLE
        elif min(rect.width, rect.height) < min_zone_width:
            zone_type = ZoneType.REMNANT  # Narrow, single-loaded only
        else:
            zone_type = ZoneType.RECTANGULAR

        zones.append(ParkingZone(
            id=f"zone_{zone_idx}",
            geometry=rect,
            zone_type=zone_type,
        ))
        zone_idx += 1

    return DecompositionResult(
        original_polygon=polygon,
        zones=zones,
        voids=voids,
    )


def _subtract_voids_from_rectangles(
    rectangles: List[Polygon],
    voids: List[Polygon]
) -> List[Polygon]:
    """
    Subtract void polygons from rectangular zones.

    Uses the existing subtract_polygon logic.
    """
    from .geometry import subtract_polygon, rectangles_overlap

    result = list(rectangles)

    for void in voids:
        new_result = []
        for rect in result:
            # Only process if there's overlap
            if rectangles_overlap(rect, void):
                # Subtract void from rectangle
                try:
                    remaining = subtract_polygon(rect, void)
                    new_result.extend(remaining)
                except ValueError:
                    # Non-rectangular geometry, keep original
                    new_result.append(rect)
            else:
                new_result.append(rect)
        result = new_result

    return result


# =============================================================================
# VALIDATION
# =============================================================================

def validate_stalls_within_boundary(
    stalls: List,
    boundary: Polygon
) -> Tuple[List, List]:
    """
    Validate that all stalls are within the site boundary.

    Args:
        stalls: List of Stall objects
        boundary: Site boundary polygon

    Returns:
        Tuple of (valid_stalls, invalid_stalls)
    """
    valid = []
    invalid = []

    for stall in stalls:
        # Check all corners of the stall
        all_inside = True
        for vertex in stall.geometry.vertices:
            if not boundary.contains_point(vertex):
                all_inside = False
                break

        if all_inside:
            valid.append(stall)
        else:
            invalid.append(stall)

    return valid, invalid


def compute_geometry_loss(
    original: Polygon,
    zones: List[ParkingZone]
) -> dict:
    """
    Compute area lost to irregular geometry.

    Returns metrics about unusable area.
    """
    original_area = original.area
    parkable_area = sum(z.area for z in zones if z.is_parkable)
    unusable_area = sum(z.area for z in zones if not z.is_parkable)

    # Area not captured by any zone
    captured_area = sum(z.area for z in zones)
    uncaptured_area = original_area - captured_area

    return {
        "original_area_sf": original_area,
        "parkable_area_sf": parkable_area,
        "unusable_area_sf": unusable_area,
        "uncaptured_area_sf": uncaptured_area,
        "geometry_loss_sf": unusable_area + uncaptured_area,
        "usability_ratio": parkable_area / original_area if original_area > 0 else 0,
    }
