"""
Core Geometry Operations

Provides boolean operations, buffering, and clipping for polygons and lines.
Uses Shapely for robust computational geometry.
"""

from __future__ import annotations
import math
from typing import List, Optional, Union, Tuple
from shapely.geometry import (
    Polygon as ShapelyPolygon,
    MultiPolygon as ShapelyMultiPolygon,
    LineString as ShapelyLine,
    MultiLineString as ShapelyMultiLine,
    GeometryCollection,
)
from shapely.ops import unary_union, split
from shapely.validation import make_valid

from .geometry import Point, Line, Polygon, Rectangle


# =============================================================================
# POLYGON BOOLEAN OPERATIONS
# =============================================================================

def union(polygons: List[Polygon]) -> List[Polygon]:
    """
    Compute the union of multiple polygons.

    Returns a list of polygons (may be fewer than input if they merge).

    Examples:
        >>> p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        >>> p2 = Polygon.from_tuples([(5, 0), (15, 0), (15, 10), (5, 10)])
        >>> result = union([p1, p2])
        >>> len(result)
        1
        >>> result[0].area
        150.0
    """
    if not polygons:
        return []

    shapely_polys = [p.to_shapely() for p in polygons]
    result = unary_union(shapely_polys)

    return _shapely_to_polygons(result)


def intersection(poly1: Polygon, poly2: Polygon) -> List[Polygon]:
    """
    Compute the intersection of two polygons.

    Returns a list of polygons (empty if no intersection).

    Examples:
        >>> p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        >>> p2 = Polygon.from_tuples([(5, 5), (15, 5), (15, 15), (5, 15)])
        >>> result = intersection(p1, p2)
        >>> result[0].area
        25.0
    """
    result = poly1.to_shapely().intersection(poly2.to_shapely())
    return _shapely_to_polygons(result)


def difference(poly1: Polygon, poly2: Polygon) -> List[Polygon]:
    """
    Subtract poly2 from poly1.

    Returns list of polygons remaining after subtraction.

    Examples:
        >>> site = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        >>> hole = Polygon.from_tuples([(40, 40), (60, 40), (60, 60), (40, 60)])
        >>> result = difference(site, hole)
        >>> result[0].area
        9600.0
    """
    result = poly1.to_shapely().difference(poly2.to_shapely())
    return _shapely_to_polygons(result)


def subtract_all(base: Polygon, holes: List[Polygon]) -> List[Polygon]:
    """
    Subtract multiple polygons from a base polygon.

    Useful for removing obstacles/exclusions from a site.

    Examples:
        >>> site = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        >>> obstacles = [
        ...     Polygon.from_tuples([(10, 10), (20, 10), (20, 20), (10, 20)]),
        ...     Polygon.from_tuples([(80, 80), (90, 80), (90, 90), (80, 90)])
        ... ]
        >>> result = subtract_all(site, obstacles)
        >>> result[0].area
        9800.0
    """
    if not holes:
        return [base]

    # Union all holes first, then subtract
    holes_union = unary_union([h.to_shapely() for h in holes])
    result = base.to_shapely().difference(holes_union)

    return _shapely_to_polygons(result)


def symmetric_difference(poly1: Polygon, poly2: Polygon) -> List[Polygon]:
    """
    Compute symmetric difference (XOR) of two polygons.

    Returns areas that are in either polygon but not in both.
    """
    result = poly1.to_shapely().symmetric_difference(poly2.to_shapely())
    return _shapely_to_polygons(result)


# =============================================================================
# BUFFER OPERATIONS (INSET/OFFSET)
# =============================================================================

def buffer(polygon: Polygon, distance: float, resolution: int = 16) -> List[Polygon]:
    """
    Buffer (offset) a polygon by a distance.

    Positive distance = expand outward
    Negative distance = shrink inward (inset)

    Args:
        polygon: The polygon to buffer
        distance: Buffer distance (negative for inset)
        resolution: Number of segments per quarter circle for rounded corners

    Returns:
        List of resulting polygons (may be empty if inset collapses polygon)

    Examples:
        >>> rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        >>> inset = buffer(rect, -10)
        >>> inset[0].width
        80.0
        >>> inset[0].height
        30.0
    """
    result = polygon.to_shapely().buffer(distance, resolution=resolution)
    return _shapely_to_polygons(result)


def inset(polygon: Polygon, distance: float, resolution: int = 16) -> List[Polygon]:
    """
    Inset (shrink) a polygon by a distance.

    Convenience wrapper for buffer with negative distance.

    Examples:
        >>> rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        >>> result = inset(rect, 10)
        >>> result[0].area
        2400.0  # 80 x 30
    """
    return buffer(polygon, -abs(distance), resolution)


def offset(polygon: Polygon, distance: float, resolution: int = 16) -> List[Polygon]:
    """
    Offset (expand) a polygon by a distance.

    Convenience wrapper for buffer with positive distance.
    """
    return buffer(polygon, abs(distance), resolution)


def buffer_with_square_corners(polygon: Polygon, distance: float) -> List[Polygon]:
    """
    Buffer a polygon with square (mitered) corners instead of rounded.

    Useful for setbacks and building footprints.
    """
    result = polygon.to_shapely().buffer(
        distance,
        join_style=2,  # MITRE
        mitre_limit=5.0
    )
    return _shapely_to_polygons(result)


def inset_square(polygon: Polygon, distance: float) -> List[Polygon]:
    """
    Inset a polygon with square corners.

    Examples:
        >>> rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        >>> result = inset_square(rect, 10)
        >>> result[0].width
        80.0
    """
    return buffer_with_square_corners(polygon, -abs(distance))


# =============================================================================
# LINE CLIPPING
# =============================================================================

def clip_line_to_polygon(line: Line, polygon: Polygon) -> List[Line]:
    """
    Clip a line to the interior of a polygon.

    Returns list of line segments that are inside the polygon.
    May return empty list if line is entirely outside.
    May return multiple segments if line crosses polygon multiple times.

    Examples:
        >>> rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        >>> line = Line(Point(-10, 25), Point(110, 25))
        >>> clipped = clip_line_to_polygon(line, rect)
        >>> len(clipped)
        1
        >>> clipped[0].start.x
        0.0
        >>> clipped[0].end.x
        100.0
    """
    shapely_line = line.to_shapely()
    shapely_poly = polygon.to_shapely()

    result = shapely_line.intersection(shapely_poly)

    return _shapely_to_lines(result)


def clip_lines_to_polygon(lines: List[Line], polygon: Polygon) -> List[Line]:
    """
    Clip multiple lines to a polygon.

    Returns all segments that are inside the polygon.
    """
    result = []
    for line in lines:
        result.extend(clip_line_to_polygon(line, polygon))
    return result


def extend_line_to_polygon(line: Line, polygon: Polygon) -> Optional[Line]:
    """
    Extend a line in both directions until it hits the polygon boundary.

    Useful for creating drive aisles that span the full width of a parking area.

    Returns None if line doesn't intersect polygon.
    """
    # Extend line far in both directions
    dx, dy = line.direction
    length = max(polygon.width, polygon.height) * 2

    extended_start = Point(
        line.start.x - dx * length,
        line.start.y - dy * length
    )
    extended_end = Point(
        line.end.x + dx * length,
        line.end.y + dy * length
    )

    extended = Line(extended_start, extended_end)
    clipped = clip_line_to_polygon(extended, polygon)

    return clipped[0] if clipped else None


# =============================================================================
# PARALLEL LINES GENERATION
# =============================================================================

def generate_parallel_lines(
    polygon: Polygon,
    spacing: float,
    angle: float = 0,
    offset_from_edge: float = 0
) -> List[Line]:
    """
    Generate parallel lines across a polygon at specified spacing and angle.

    This is the core function for parking bay placement.

    Args:
        polygon: The polygon to fill with lines
        spacing: Distance between parallel lines
        angle: Angle in degrees (0 = horizontal, 90 = vertical)
        offset_from_edge: Distance to offset first line from edge

    Returns:
        List of lines clipped to polygon boundary

    Examples:
        >>> rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 60), (0, 60)])
        >>> lines = generate_parallel_lines(rect, spacing=20, angle=0)
        >>> len(lines)
        3  # at y=20, y=40 (y=0 and y=60 are edges)
    """
    if spacing <= 0:
        raise ValueError("Spacing must be positive")

    # Get bounding box
    min_x, min_y, max_x, max_y = polygon.bounds

    # Calculate dimensions with buffer
    width = max_x - min_x
    height = max_y - min_y
    diagonal = math.sqrt(width**2 + height**2)

    # Center of polygon
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2

    # Generate lines perpendicular to angle
    angle_rad = math.radians(angle)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Direction along the lines
    dx = cos_a
    dy = sin_a

    # Perpendicular direction (for spacing)
    px = -sin_a
    py = cos_a

    lines = []

    # Generate lines from center outward
    half_diagonal = diagonal / 2 + spacing
    num_lines = int(half_diagonal / spacing) + 1

    for i in range(-num_lines, num_lines + 1):
        if i == 0 and offset_from_edge > 0:
            continue

        # Offset from center in perpendicular direction
        offset = i * spacing + offset_from_edge

        # Line center point
        line_cx = cx + px * offset
        line_cy = cy + py * offset

        # Line endpoints (extend beyond bounding box)
        start = Point(
            line_cx - dx * diagonal,
            line_cy - dy * diagonal
        )
        end = Point(
            line_cx + dx * diagonal,
            line_cy + dy * diagonal
        )

        # Clip to polygon
        line = Line(start, end)
        clipped = clip_line_to_polygon(line, polygon)
        lines.extend(clipped)

    return lines


def generate_grid_lines(
    polygon: Polygon,
    x_spacing: float,
    y_spacing: float
) -> Tuple[List[Line], List[Line]]:
    """
    Generate a grid of horizontal and vertical lines.

    Returns:
        Tuple of (horizontal_lines, vertical_lines)
    """
    horizontal = generate_parallel_lines(polygon, y_spacing, angle=0)
    vertical = generate_parallel_lines(polygon, x_spacing, angle=90)
    return horizontal, vertical


# =============================================================================
# POLYGON VALIDITY AND REPAIR
# =============================================================================

def make_polygon_valid(polygon: Polygon) -> List[Polygon]:
    """
    Repair an invalid polygon (self-intersecting, etc.).

    Returns list of valid polygons.
    """
    shapely_poly = polygon.to_shapely()
    if shapely_poly.is_valid:
        return [polygon]

    valid = make_valid(shapely_poly)
    return _shapely_to_polygons(valid)


def simplify(polygon: Polygon, tolerance: float = 0.1) -> Polygon:
    """
    Simplify polygon by removing unnecessary vertices.

    Useful for cleaning up buffered polygons.
    """
    simplified = polygon.to_shapely().simplify(tolerance)
    result = _shapely_to_polygons(simplified)
    return result[0] if result else polygon


# =============================================================================
# SPATIAL RELATIONSHIPS
# =============================================================================

def polygons_intersect(poly1: Polygon, poly2: Polygon) -> bool:
    """Check if two polygons intersect."""
    return poly1.to_shapely().intersects(poly2.to_shapely())


def polygon_contains(outer: Polygon, inner: Polygon) -> bool:
    """Check if outer polygon completely contains inner polygon."""
    return outer.to_shapely().contains(inner.to_shapely())


def polygon_touches(poly1: Polygon, poly2: Polygon) -> bool:
    """Check if polygons touch (share boundary but don't overlap)."""
    return poly1.to_shapely().touches(poly2.to_shapely())


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Check if point is inside polygon."""
    return polygon.to_shapely().contains(point.to_shapely())


def line_intersects_polygon(line: Line, polygon: Polygon) -> bool:
    """Check if line intersects polygon."""
    return line.to_shapely().intersects(polygon.to_shapely())


# =============================================================================
# AREA CALCULATIONS
# =============================================================================

def total_area(polygons: List[Polygon]) -> float:
    """Calculate total area of multiple polygons."""
    return sum(p.area for p in polygons)


def intersection_area(poly1: Polygon, poly2: Polygon) -> float:
    """Calculate area of intersection between two polygons."""
    result = intersection(poly1, poly2)
    return total_area(result)


def coverage_ratio(inner_polygons: List[Polygon], outer: Polygon) -> float:
    """
    Calculate what fraction of outer polygon is covered by inner polygons.

    Useful for lot coverage calculations.
    """
    inner_area = total_area(inner_polygons)
    return inner_area / outer.area if outer.area > 0 else 0


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _shapely_to_polygons(geom) -> List[Polygon]:
    """Convert Shapely geometry to list of Polygon objects."""
    if geom is None or geom.is_empty:
        return []

    if isinstance(geom, ShapelyPolygon):
        if geom.is_empty:
            return []
        return [Polygon.from_shapely(geom)]

    if isinstance(geom, ShapelyMultiPolygon):
        return [Polygon.from_shapely(p) for p in geom.geoms if not p.is_empty]

    if isinstance(geom, GeometryCollection):
        result = []
        for g in geom.geoms:
            if isinstance(g, ShapelyPolygon) and not g.is_empty:
                result.append(Polygon.from_shapely(g))
        return result

    return []


def _shapely_to_lines(geom) -> List[Line]:
    """Convert Shapely geometry to list of Line objects."""
    if geom is None or geom.is_empty:
        return []

    if isinstance(geom, ShapelyLine):
        coords = list(geom.coords)
        if len(coords) >= 2:
            return [Line(Point(coords[0][0], coords[0][1]),
                         Point(coords[-1][0], coords[-1][1]))]
        return []

    if isinstance(geom, ShapelyMultiLine):
        lines = []
        for line in geom.geoms:
            coords = list(line.coords)
            if len(coords) >= 2:
                lines.append(Line(Point(coords[0][0], coords[0][1]),
                                  Point(coords[-1][0], coords[-1][1])))
        return lines

    if isinstance(geom, GeometryCollection):
        result = []
        for g in geom.geoms:
            result.extend(_shapely_to_lines(g))
        return result

    return []


def convex_hull(polygon: Polygon) -> Polygon:
    """Return the convex hull of a polygon."""
    hull = polygon.to_shapely().convex_hull
    return Polygon.from_shapely(hull)


def minimum_bounding_rectangle(polygon: Polygon) -> Rectangle:
    """
    Return the minimum axis-aligned bounding rectangle.

    (For minimum-area rotated rectangle, use minimum_rotated_rectangle)
    """
    return Rectangle.from_polygon(polygon)


def split_polygon_with_line(polygon: Polygon, line: Line) -> List[Polygon]:
    """
    Split a polygon into two or more parts using a line.

    Useful for dividing a site.
    """
    # Extend line to ensure it crosses polygon
    extended = line.extend(1000, 1000)

    shapely_line = extended.to_shapely()
    shapely_poly = polygon.to_shapely()

    result = split(shapely_poly, shapely_line)

    return _shapely_to_polygons(result)
