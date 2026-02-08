"""
Core Geometry Classes

Provides Point, Line, Polygon, and Rectangle primitives.
All coordinates are in feet (default) or user-specified units.
Uses Shapely internally for robust computational geometry.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Iterator, Union
from shapely.geometry import (
    Point as ShapelyPoint,
    LineString as ShapelyLine,
    Polygon as ShapelyPolygon,
)
from shapely.affinity import rotate as shapely_rotate, translate as shapely_translate


# =============================================================================
# POINT
# =============================================================================

@dataclass(frozen=True)
class Point:
    """
    A 2D point with x, y coordinates.

    Immutable (frozen) for use as dict keys and in sets.

    Examples:
        >>> p1 = Point(0, 0)
        >>> p2 = Point(10, 10)
        >>> p1.distance_to(p2)
        14.142135623730951
    """
    x: float
    y: float

    def __post_init__(self):
        # Ensure coordinates are floats
        object.__setattr__(self, 'x', float(self.x))
        object.__setattr__(self, 'y', float(self.y))

    def distance_to(self, other: Point) -> float:
        """Calculate Euclidean distance to another point."""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def midpoint_to(self, other: Point) -> Point:
        """Return the midpoint between this point and another."""
        return Point((self.x + other.x) / 2, (self.y + other.y) / 2)

    def translate(self, dx: float, dy: float) -> Point:
        """Return a new point translated by (dx, dy)."""
        return Point(self.x + dx, self.y + dy)

    def rotate(self, angle_degrees: float, origin: Optional[Point] = None) -> Point:
        """
        Rotate point around origin by angle (in degrees, counter-clockwise).
        If origin is None, rotates around (0, 0).
        """
        if origin is None:
            origin = Point(0, 0)

        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Translate to origin
        dx = self.x - origin.x
        dy = self.y - origin.y

        # Rotate
        new_x = dx * cos_a - dy * sin_a
        new_y = dx * sin_a + dy * cos_a

        # Translate back
        return Point(new_x + origin.x, new_y + origin.y)

    def to_tuple(self) -> Tuple[float, float]:
        """Return as (x, y) tuple."""
        return (self.x, self.y)

    def to_shapely(self) -> ShapelyPoint:
        """Convert to Shapely Point."""
        return ShapelyPoint(self.x, self.y)

    @classmethod
    def from_tuple(cls, coords: Tuple[float, float]) -> Point:
        """Create Point from (x, y) tuple."""
        return cls(coords[0], coords[1])

    @classmethod
    def from_dict(cls, d: dict) -> Point:
        """Create Point from dict with 'x' and 'y' keys."""
        return cls(d['x'], d['y'])

    def to_dict(self) -> dict:
        """Convert to dict with 'x' and 'y' keys."""
        return {'x': self.x, 'y': self.y}

    def __repr__(self) -> str:
        return f"Point({self.x:.2f}, {self.y:.2f})"


# =============================================================================
# LINE
# =============================================================================

@dataclass
class Line:
    """
    A line segment defined by start and end points.

    Examples:
        >>> line = Line(Point(0, 0), Point(10, 0))
        >>> line.length
        10.0
        >>> line.midpoint
        Point(5.00, 0.00)
    """
    start: Point
    end: Point

    @property
    def length(self) -> float:
        """Calculate the length of the line segment."""
        return self.start.distance_to(self.end)

    @property
    def midpoint(self) -> Point:
        """Return the midpoint of the line segment."""
        return self.start.midpoint_to(self.end)

    @property
    def angle(self) -> float:
        """Return the angle of the line in degrees (0-360, from positive x-axis)."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        angle = math.degrees(math.atan2(dy, dx))
        return angle if angle >= 0 else angle + 360

    @property
    def direction(self) -> Tuple[float, float]:
        """Return normalized direction vector (dx, dy)."""
        length = self.length
        if length == 0:
            return (0, 0)
        return (
            (self.end.x - self.start.x) / length,
            (self.end.y - self.start.y) / length
        )

    @property
    def normal(self) -> Tuple[float, float]:
        """Return normalized perpendicular vector (rotated 90° counter-clockwise)."""
        dx, dy = self.direction
        return (-dy, dx)

    def point_at(self, t: float) -> Point:
        """
        Return point at parameter t along the line.
        t=0 returns start, t=1 returns end.
        """
        return Point(
            self.start.x + t * (self.end.x - self.start.x),
            self.start.y + t * (self.end.y - self.start.y)
        )

    def translate(self, dx: float, dy: float) -> Line:
        """Return a new line translated by (dx, dy)."""
        return Line(
            self.start.translate(dx, dy),
            self.end.translate(dx, dy)
        )

    def rotate(self, angle_degrees: float, origin: Optional[Point] = None) -> Line:
        """Rotate line around origin (or line midpoint if origin is None)."""
        if origin is None:
            origin = self.midpoint
        return Line(
            self.start.rotate(angle_degrees, origin),
            self.end.rotate(angle_degrees, origin)
        )

    def offset(self, distance: float) -> Line:
        """
        Return a parallel line offset by distance.
        Positive distance offsets to the left (counter-clockwise).
        """
        nx, ny = self.normal
        dx = nx * distance
        dy = ny * distance
        return self.translate(dx, dy)

    def extend(self, start_amount: float = 0, end_amount: float = 0) -> Line:
        """Extend the line by given amounts at start and end."""
        dx, dy = self.direction
        new_start = Point(
            self.start.x - dx * start_amount,
            self.start.y - dy * start_amount
        )
        new_end = Point(
            self.end.x + dx * end_amount,
            self.end.y + dy * end_amount
        )
        return Line(new_start, new_end)

    def subdivide(self, n: int) -> List[Point]:
        """Divide line into n equal segments, return n+1 points."""
        return [self.point_at(i / n) for i in range(n + 1)]

    def to_shapely(self) -> ShapelyLine:
        """Convert to Shapely LineString."""
        return ShapelyLine([self.start.to_tuple(), self.end.to_tuple()])

    def to_points(self) -> List[Point]:
        """Return [start, end] as list."""
        return [self.start, self.end]

    def reversed(self) -> Line:
        """Return line with start and end swapped."""
        return Line(self.end, self.start)

    def __repr__(self) -> str:
        return f"Line({self.start} -> {self.end}, len={self.length:.2f})"


# =============================================================================
# POLYGON
# =============================================================================

@dataclass
class Polygon:
    """
    A closed polygon defined by a list of vertices.

    Vertices should be in counter-clockwise order for positive area.
    The polygon is automatically closed (last vertex connects to first).

    Supports polygons with holes (interior rings) via Shapely.

    Examples:
        >>> poly = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        >>> poly.area
        5000.0
        >>> poly.perimeter
        300.0
    """
    vertices: List[Point]
    _shapely: ShapelyPolygon = field(default=None, repr=False, compare=False)
    _shapely_override: ShapelyPolygon = field(
        default=None, repr=False, compare=False)

    def __post_init__(self):
        if len(self.vertices) < 3:
            raise ValueError("Polygon must have at least 3 vertices")
        # Use pre-built Shapely polygon if provided (preserves holes)
        if self._shapely_override is not None:
            self._shapely = self._shapely_override
        else:
            # Create Shapely polygon for robust operations
            coords = [v.to_tuple() for v in self.vertices]
            self._shapely = ShapelyPolygon(coords)

    @property
    def area(self) -> float:
        """Calculate the area of the polygon (always positive)."""
        return abs(self._shapely.area)

    @property
    def perimeter(self) -> float:
        """Calculate the perimeter of the polygon."""
        return self._shapely.length

    @property
    def centroid(self) -> Point:
        """Return the centroid (center of mass) of the polygon."""
        c = self._shapely.centroid
        return Point(c.x, c.y)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Return bounding box as (min_x, min_y, max_x, max_y)."""
        return self._shapely.bounds

    @property
    def width(self) -> float:
        """Return width of bounding box."""
        min_x, _, max_x, _ = self.bounds
        return max_x - min_x

    @property
    def height(self) -> float:
        """Return height of bounding box."""
        _, min_y, _, max_y = self.bounds
        return max_y - min_y

    @property
    def edges(self) -> List[Line]:
        """Return list of edges as Line objects."""
        edges = []
        n = len(self.vertices)
        for i in range(n):
            edges.append(Line(self.vertices[i], self.vertices[(i + 1) % n]))
        return edges

    @property
    def is_convex(self) -> bool:
        """Check if polygon is convex."""
        return self._shapely.convex_hull.equals(self._shapely)

    @property
    def is_valid(self) -> bool:
        """Check if polygon is valid (no self-intersections)."""
        return self._shapely.is_valid

    def longest_edge(self) -> Line:
        """Return the longest edge of the polygon."""
        return max(self.edges, key=lambda e: e.length)

    def contains_point(self, point: Point) -> bool:
        """Check if point is inside the polygon."""
        return self._shapely.contains(point.to_shapely())

    def translate(self, dx: float, dy: float) -> Polygon:
        """Return a new polygon translated by (dx, dy)."""
        new_vertices = [v.translate(dx, dy) for v in self.vertices]
        return Polygon(new_vertices)

    def rotate(self, angle_degrees: float, origin: Optional[Point] = None) -> Polygon:
        """Rotate polygon around origin (or centroid if origin is None)."""
        if origin is None:
            origin = self.centroid
        new_vertices = [v.rotate(angle_degrees, origin) for v in self.vertices]
        return Polygon(new_vertices)

    def scale(self, factor: float, origin: Optional[Point] = None) -> Polygon:
        """Scale polygon by factor around origin (or centroid if None)."""
        if origin is None:
            origin = self.centroid
        new_vertices = []
        for v in self.vertices:
            new_x = origin.x + (v.x - origin.x) * factor
            new_y = origin.y + (v.y - origin.y) * factor
            new_vertices.append(Point(new_x, new_y))
        return Polygon(new_vertices)

    def to_shapely(self) -> ShapelyPolygon:
        """Return Shapely polygon."""
        return self._shapely

    def to_tuples(self) -> List[Tuple[float, float]]:
        """Return vertices as list of (x, y) tuples."""
        return [v.to_tuple() for v in self.vertices]

    def to_dicts(self) -> List[dict]:
        """Return vertices as list of {'x': x, 'y': y} dicts."""
        return [v.to_dict() for v in self.vertices]

    @classmethod
    def from_tuples(cls, coords: List[Tuple[float, float]]) -> Polygon:
        """Create Polygon from list of (x, y) tuples."""
        vertices = [Point(x, y) for x, y in coords]
        return cls(vertices)

    @classmethod
    def from_dicts(cls, dicts: List[dict]) -> Polygon:
        """Create Polygon from list of {'x': x, 'y': y} dicts."""
        vertices = [Point.from_dict(d) for d in dicts]
        return cls(vertices)

    @classmethod
    def from_shapely(cls, shapely_poly: ShapelyPolygon) -> Polygon:
        """Create Polygon from Shapely polygon, preserving holes."""
        coords = list(shapely_poly.exterior.coords)[
            :-1]  # Remove closing point
        vertices = [Point(x, y) for x, y in coords]
        # Pass the original Shapely polygon to preserve holes
        poly = cls.__new__(cls)
        poly.vertices = vertices
        poly._shapely = shapely_poly
        poly._shapely_override = shapely_poly
        return poly

    def __iter__(self) -> Iterator[Point]:
        """Iterate over vertices."""
        return iter(self.vertices)

    def __len__(self) -> int:
        """Return number of vertices."""
        return len(self.vertices)

    def __repr__(self) -> str:
        return f"Polygon({len(self.vertices)} vertices, area={self.area:.2f})"


# =============================================================================
# RECTANGLE
# =============================================================================

@dataclass
class Rectangle:
    """
    An axis-aligned rectangle defined by origin, width, and height.

    The origin is the bottom-left corner.

    Examples:
        >>> rect = Rectangle(Point(0, 0), 100, 50)
        >>> rect.area
        5000.0
        >>> rect.center
        Point(50.00, 25.00)
    """
    origin: Point
    width: float
    height: float

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Width and height must be positive")

    @property
    def area(self) -> float:
        """Calculate area of rectangle."""
        return self.width * self.height

    @property
    def perimeter(self) -> float:
        """Calculate perimeter of rectangle."""
        return 2 * (self.width + self.height)

    @property
    def center(self) -> Point:
        """Return center point of rectangle."""
        return Point(
            self.origin.x + self.width / 2,
            self.origin.y + self.height / 2
        )

    @property
    def corners(self) -> List[Point]:
        """Return corners in counter-clockwise order starting from origin."""
        x, y = self.origin.x, self.origin.y
        return [
            self.origin,                          # bottom-left
            Point(x + self.width, y),             # bottom-right
            Point(x + self.width, y + self.height),  # top-right
            Point(x, y + self.height),            # top-left
        ]

    @property
    def min_x(self) -> float:
        return self.origin.x

    @property
    def max_x(self) -> float:
        return self.origin.x + self.width

    @property
    def min_y(self) -> float:
        return self.origin.y

    @property
    def max_y(self) -> float:
        return self.origin.y + self.height

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        return (self.min_x, self.min_y, self.max_x, self.max_y)

    def to_polygon(self) -> Polygon:
        """Convert to Polygon."""
        return Polygon(self.corners)

    def contains_point(self, point: Point) -> bool:
        """Check if point is inside rectangle."""
        return (
            self.min_x <= point.x <= self.max_x and
            self.min_y <= point.y <= self.max_y
        )

    def intersects(self, other: Rectangle) -> bool:
        """Check if this rectangle intersects another."""
        return not (
            self.max_x < other.min_x or
            self.min_x > other.max_x or
            self.max_y < other.min_y or
            self.min_y > other.max_y
        )

    def translate(self, dx: float, dy: float) -> Rectangle:
        """Return a new rectangle translated by (dx, dy)."""
        return Rectangle(self.origin.translate(dx, dy), self.width, self.height)

    def inset(self, amount: float) -> Rectangle:
        """
        Return a new rectangle inset by amount on all sides.
        Raises ValueError if inset would result in zero or negative dimensions.
        """
        new_width = self.width - 2 * amount
        new_height = self.height - 2 * amount
        if new_width <= 0 or new_height <= 0:
            raise ValueError(
                f"Inset {amount} too large for rectangle {self.width}x{self.height}")
        return Rectangle(
            self.origin.translate(amount, amount),
            new_width,
            new_height
        )

    def expand(self, amount: float) -> Rectangle:
        """Return a new rectangle expanded by amount on all sides."""
        return Rectangle(
            self.origin.translate(-amount, -amount),
            self.width + 2 * amount,
            self.height + 2 * amount
        )

    @classmethod
    def from_bounds(cls, min_x: float, min_y: float, max_x: float, max_y: float) -> Rectangle:
        """Create Rectangle from bounding box coordinates."""
        return cls(Point(min_x, min_y), max_x - min_x, max_y - min_y)

    @classmethod
    def from_center(cls, center: Point, width: float, height: float) -> Rectangle:
        """Create Rectangle from center point and dimensions."""
        origin = Point(center.x - width / 2, center.y - height / 2)
        return cls(origin, width, height)

    @classmethod
    def from_polygon(cls, polygon: Polygon) -> Rectangle:
        """Create bounding Rectangle from any Polygon."""
        min_x, min_y, max_x, max_y = polygon.bounds
        return cls.from_bounds(min_x, min_y, max_x, max_y)

    def __repr__(self) -> str:
        return f"Rectangle({self.origin}, {self.width}x{self.height})"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def distance(p1: Point, p2: Point) -> float:
    """Calculate distance between two points."""
    return p1.distance_to(p2)


def angle_between(p1: Point, p2: Point, p3: Point) -> float:
    """
    Calculate angle at p2 formed by p1-p2-p3 (in degrees).
    Returns angle between 0 and 180.
    """
    v1 = (p1.x - p2.x, p1.y - p2.y)
    v2 = (p3.x - p2.x, p3.y - p2.y)

    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
    mag2 = math.sqrt(v2[0]**2 + v2[1]**2)

    if mag1 == 0 or mag2 == 0:
        return 0

    # Clamp for numerical stability
    cos_angle = max(-1, min(1, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def bounding_box(points: List[Point]) -> Rectangle:
    """Calculate bounding box of a list of points."""
    if not points:
        raise ValueError("Cannot calculate bounding box of empty list")

    min_x = min(p.x for p in points)
    max_x = max(p.x for p in points)
    min_y = min(p.y for p in points)
    max_y = max(p.y for p in points)

    return Rectangle.from_bounds(min_x, min_y, max_x, max_y)
