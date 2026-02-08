"""
Geometry Processor
==================

Provides polygon operations for parking layout generation.
Handles rectangular site polygons with offset, subtraction, and partitioning.

Units: All dimensions in feet.
Coordinate system: Origin at lower-left, X positive right, Y positive up.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import math


@dataclass(frozen=True)
class Point:
    """Immutable 2D point."""
    x: float
    y: float

    def __add__(self, other: Point) -> Point:
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Point:
        return Point(self.x * scalar, self.y * scalar)

    def distance_to(self, other: Point) -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Polygon:
    """
    Simple polygon representation for rectangular parking sites.

    Vertices are stored in counter-clockwise order.
    For MVP, primarily handles axis-aligned rectangles.
    """
    vertices: List[Point]

    @classmethod
    def from_bounds(cls, min_x: float, min_y: float, max_x: float, max_y: float) -> Polygon:
        """Create rectangle from bounding box coordinates."""
        return cls([
            Point(min_x, min_y),  # Bottom-left
            Point(max_x, min_y),  # Bottom-right
            Point(max_x, max_y),  # Top-right
            Point(min_x, max_y),  # Top-left
        ])

    @classmethod
    def from_dimensions(cls, width: float, height: float, origin: Optional[Point] = None) -> Polygon:
        """Create rectangle from width and height, optionally positioned at origin."""
        ox, oy = (origin.x, origin.y) if origin else (0.0, 0.0)
        return cls.from_bounds(ox, oy, ox + width, oy + height)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def width(self) -> float:
        """Width (X extent) of bounding box."""
        min_x, _, max_x, _ = self.bounds
        return max_x - min_x

    @property
    def height(self) -> float:
        """Height (Y extent) of bounding box."""
        _, min_y, _, max_y = self.bounds
        return max_y - min_y

    @property
    def area(self) -> float:
        """Calculate polygon area using shoelace formula."""
        n = len(self.vertices)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y
        return abs(area) / 2.0

    @property
    def perimeter(self) -> float:
        """Calculate polygon perimeter."""
        n = len(self.vertices)
        perimeter = 0.0
        for i in range(n):
            j = (i + 1) % n
            perimeter += self.vertices[i].distance_to(self.vertices[j])
        return perimeter

    @property
    def centroid(self) -> Point:
        """Calculate polygon centroid."""
        min_x, min_y, max_x, max_y = self.bounds
        return Point((min_x + max_x) / 2, (min_y + max_y) / 2)

    @property
    def is_rectangular(self) -> bool:
        """Check if polygon is an axis-aligned rectangle."""
        if len(self.vertices) != 4:
            return False
        # Check if all angles are 90 degrees (axis-aligned)
        xs = sorted(set(v.x for v in self.vertices))
        ys = sorted(set(v.y for v in self.vertices))
        return len(xs) == 2 and len(ys) == 2

    def contains_point(self, point: Point) -> bool:
        """Check if point is inside or on boundary of polygon."""
        min_x, min_y, max_x, max_y = self.bounds

        # For rectangular polygons, simple bounds check is sufficient
        # and correctly handles edge/corner cases
        if self.is_rectangular:
            return min_x <= point.x <= max_x and min_y <= point.y <= max_y

        # For non-rectangular polygons, use ray casting
        if not (min_x <= point.x <= max_x and min_y <= point.y <= max_y):
            return False

        n = len(self.vertices)
        inside = False
        j = n - 1
        for i in range(n):
            vi = self.vertices[i]
            vj = self.vertices[j]
            if ((vi.y > point.y) != (vj.y > point.y) and
                    point.x < (vj.x - vi.x) * (point.y - vi.y) / (vj.y - vi.y) + vi.x):
                inside = not inside
            j = i
        return inside

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "vertices": [{"x": v.x, "y": v.y} for v in self.vertices],
            "bounds": self.bounds,
            "area": self.area,
        }


def offset_polygon(polygon: Polygon, distance: float) -> Optional[Polygon]:
    """
    Inward offset (shrink) a polygon by a given distance.

    For rectangular polygons, this produces a smaller concentric rectangle.
    Negative distance would expand the polygon (not typical for setbacks).

    Args:
        polygon: Input polygon (must be rectangular for MVP)
        distance: Offset distance in feet (positive = inward)

    Returns:
        Offset polygon, or None if offset distance exceeds half of width/height
    """
    if not polygon.is_rectangular:
        raise ValueError("MVP only supports rectangular polygons for offset")

    min_x, min_y, max_x, max_y = polygon.bounds

    # Apply inward offset
    new_min_x = min_x + distance
    new_min_y = min_y + distance
    new_max_x = max_x - distance
    new_max_y = max_y - distance

    # Check for valid result (not collapsed)
    if new_max_x <= new_min_x or new_max_y <= new_min_y:
        return None

    return Polygon.from_bounds(new_min_x, new_min_y, new_max_x, new_max_y)


def offset_polygon_directional(
    polygon: Polygon,
    north: float = 0.0,
    south: float = 0.0,
    east: float = 0.0,
    west: float = 0.0,
) -> Optional[Polygon]:
    """
    Inward offset (shrink) a polygon by different distances per edge.

    For rectangular polygons oriented with north=+Y, south=-Y, east=+X, west=-X:
    - North: reduces maxY (top edge)
    - South: increases minY (bottom edge)
    - East: reduces maxX (right edge)
    - West: increases minX (left edge)

    Args:
        polygon: Input polygon (must be rectangular for MVP)
        north: Setback from north (top) edge in feet
        south: Setback from south (bottom) edge in feet
        east: Setback from east (right) edge in feet
        west: Setback from west (left) edge in feet

    Returns:
        Offset polygon, or None if offsets exceed site dimensions
    """
    if not polygon.is_rectangular:
        raise ValueError("MVP only supports rectangular polygons for offset")

    min_x, min_y, max_x, max_y = polygon.bounds

    # Apply directional inward offsets
    # West = left edge (minX moves right)
    # East = right edge (maxX moves left)
    # South = bottom edge (minY moves up)
    # North = top edge (maxY moves down)
    new_min_x = min_x + west
    new_max_x = max_x - east
    new_min_y = min_y + south
    new_max_y = max_y - north

    # Check for valid result (not collapsed)
    if new_max_x <= new_min_x or new_max_y <= new_min_y:
        return None

    return Polygon.from_bounds(new_min_x, new_min_y, new_max_x, new_max_y)


def subtract_polygon(base: Polygon, subtraction: Polygon) -> List[Polygon]:
    """
    Subtract one polygon from another.

    For MVP with rectangular polygons, this handles common cases:
    - Subtraction fully inside base: returns L-shaped or multiple rectangles
    - Subtraction at edge: returns reduced rectangle
    - No overlap: returns original base

    Note: Complex results are approximated as bounding rectangles for MVP.

    Args:
        base: Base polygon to subtract from
        subtraction: Polygon to subtract

    Returns:
        List of resulting polygons (may be empty if fully consumed)
    """
    if not base.is_rectangular or not subtraction.is_rectangular:
        raise ValueError("MVP only supports rectangular polygon subtraction")

    b_min_x, b_min_y, b_max_x, b_max_y = base.bounds
    s_min_x, s_min_y, s_max_x, s_max_y = subtraction.bounds

    # Check for no overlap
    if (s_max_x <= b_min_x or s_min_x >= b_max_x or
            s_max_y <= b_min_y or s_min_y >= b_max_y):
        return [base]

    # Check for full consumption
    if (s_min_x <= b_min_x and s_max_x >= b_max_x and
            s_min_y <= b_min_y and s_max_y >= b_max_y):
        return []

    # Clip subtraction to base bounds
    clip_min_x = max(s_min_x, b_min_x)
    clip_max_x = min(s_max_x, b_max_x)
    clip_min_y = max(s_min_y, b_min_y)
    clip_max_y = min(s_max_y, b_max_y)

    result = []

    # Generate up to 4 rectangles around the subtracted area
    # Bottom strip
    if clip_min_y > b_min_y:
        result.append(Polygon.from_bounds(
            b_min_x, b_min_y, b_max_x, clip_min_y))

    # Top strip
    if clip_max_y < b_max_y:
        result.append(Polygon.from_bounds(
            b_min_x, clip_max_y, b_max_x, b_max_y))

    # Left strip (between top and bottom)
    if clip_min_x > b_min_x:
        result.append(Polygon.from_bounds(
            b_min_x, clip_min_y, clip_min_x, clip_max_y))

    # Right strip (between top and bottom)
    if clip_max_x < b_max_x:
        result.append(Polygon.from_bounds(
            clip_max_x, clip_min_y, b_max_x, clip_max_y))

    return result


def partition_rectangle(
    polygon: Polygon,
    partition_width: float,
    direction: str = "horizontal"
) -> List[Polygon]:
    """
    Partition a rectangle into strips of specified width.

    Used for creating parking bay zones from the net parking area.

    Args:
        polygon: Rectangle to partition
        partition_width: Width of each strip
        direction: "horizontal" (strips run left-right) or "vertical" (strips run up-down)

    Returns:
        List of rectangular strip polygons
    """
    if not polygon.is_rectangular:
        raise ValueError("MVP only supports rectangular polygon partitioning")

    min_x, min_y, max_x, max_y = polygon.bounds
    strips = []

    if direction == "horizontal":
        # Strips run left to right, stacked vertically
        extent = max_y - min_y
        num_full = int(extent // partition_width)

        for i in range(num_full):
            strip_min_y = min_y + i * partition_width
            strip_max_y = strip_min_y + partition_width
            strips.append(Polygon.from_bounds(
                min_x, strip_min_y, max_x, strip_max_y))

        # Remainder strip if any
        remainder = extent - (num_full * partition_width)
        if remainder > 0:
            strips.append(Polygon.from_bounds(
                min_x, min_y + num_full * partition_width, max_x, max_y))

    else:  # vertical
        # Strips run top to bottom, stacked horizontally
        extent = max_x - min_x
        num_full = int(extent // partition_width)

        for i in range(num_full):
            strip_min_x = min_x + i * partition_width
            strip_max_x = strip_min_x + partition_width
            strips.append(Polygon.from_bounds(
                strip_min_x, min_y, strip_max_x, max_y))

        # Remainder strip if any
        remainder = extent - (num_full * partition_width)
        if remainder > 0:
            strips.append(Polygon.from_bounds(
                min_x + num_full * partition_width, min_y, max_x, max_y))

    return strips


def compute_module_width(stall_length: float, aisle_width: float, double_loaded: bool = True) -> float:
    """
    Calculate the width of a parking module (stalls + aisle).

    A double-loaded module has stalls on both sides of the aisle.
    A single-loaded module has stalls on one side only.

    Args:
        stall_length: Length of parking stall (perpendicular to aisle)
        aisle_width: Width of drive aisle
        double_loaded: Whether stalls are on both sides of aisle

    Returns:
        Total module width in feet
    """
    if double_loaded:
        return stall_length + aisle_width + stall_length
    else:
        return stall_length + aisle_width


def rectangles_overlap(r1: Polygon, r2: Polygon) -> bool:
    """Check if two axis-aligned rectangles overlap."""
    min1_x, min1_y, max1_x, max1_y = r1.bounds
    min2_x, min2_y, max2_x, max2_y = r2.bounds

    return not (max1_x <= min2_x or max2_x <= min1_x or
                max1_y <= min2_y or max2_y <= min1_y)
