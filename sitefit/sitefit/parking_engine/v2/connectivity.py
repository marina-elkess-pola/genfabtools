"""
GenFabTools Parking Engine v2 — Circulation Connectivity Module

Provides a boolean check for whether all drive aisles form a single
connected component. Connected means every aisle is reachable from
any other via shared endpoints or intersections.

This module:
- Does NOT inject or generate aisles
- Does NOT modify layout results
- Does NOT introduce complex circulation graphs
- Does NOT add metrics other than a boolean

Uses Union-Find (Disjoint Set Union) for O(n α(n)) ≈ O(n) performance.

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Protocol, Union, Any
import math

from sitefit.core.geometry import Point, Line


# =============================================================================
# CONSTANTS
# =============================================================================

# Distance tolerance for considering two points as "shared"
# Points within this distance are treated as the same location
ENDPOINT_TOLERANCE: float = 0.5  # feet

# Minimum intersection length to consider aisles as connected
INTERSECTION_TOLERANCE: float = 0.1  # feet


# =============================================================================
# AISLE PROTOCOL (supports both v1 and v2 aisle types)
# =============================================================================

class AisleProtocol(Protocol):
    """
    Protocol for aisle objects that can be checked for connectivity.

    Aisles must have a centerline (Line) or start/end points.
    Supports Aisle60 from v2 and DriveAisle from v1.
    """
    @property
    def centerline(self) -> Line:
        """The centerline of the aisle."""
        ...


# =============================================================================
# UNION-FIND (DISJOINT SET UNION)
# =============================================================================

class UnionFind:
    """
    Union-Find data structure for efficient connected component tracking.

    Uses path compression and union by rank for near O(1) operations.
    """

    def __init__(self, n: int):
        """Initialize with n elements (0 to n-1)."""
        self.parent = list(range(n))
        self.rank = [0] * n
        self.component_count = n

    def find(self, x: int) -> int:
        """Find the root of x with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """
        Union the sets containing x and y.

        Returns True if x and y were in different sets.
        """
        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return False

        # Union by rank
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1

        self.component_count -= 1
        return True

    def is_connected(self) -> bool:
        """Check if all elements are in a single component."""
        return self.component_count == 1

    def get_component_count(self) -> int:
        """Return the number of disjoint components."""
        return self.component_count


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_aisle_endpoints(aisle: Any) -> Tuple[Point, Point]:
    """
    Extract start and end points from an aisle object.

    Supports:
    - Objects with .centerline attribute (Aisle60, etc.)
    - Objects with .start and .end attributes (Line)
    - Tuples of (start, end) Points
    """
    if hasattr(aisle, 'centerline'):
        return (aisle.centerline.start, aisle.centerline.end)
    elif hasattr(aisle, 'start') and hasattr(aisle, 'end'):
        return (aisle.start, aisle.end)
    elif isinstance(aisle, tuple) and len(aisle) == 2:
        return aisle
    else:
        raise TypeError(f"Cannot extract endpoints from {type(aisle)}")


def _points_are_close(p1: Point, p2: Point, tolerance: float = ENDPOINT_TOLERANCE) -> bool:
    """Check if two points are within tolerance distance."""
    return p1.distance_to(p2) <= tolerance


def _aisles_share_endpoint(
    aisle_a: Tuple[Point, Point],
    aisle_b: Tuple[Point, Point],
    tolerance: float = ENDPOINT_TOLERANCE,
) -> bool:
    """
    Check if two aisles share an endpoint.

    Endpoints are (start, end) tuples. Two aisles share an endpoint
    if any combination of their endpoints are within tolerance.
    """
    a_start, a_end = aisle_a
    b_start, b_end = aisle_b

    return (
        _points_are_close(a_start, b_start, tolerance) or
        _points_are_close(a_start, b_end, tolerance) or
        _points_are_close(a_end, b_start, tolerance) or
        _points_are_close(a_end, b_end, tolerance)
    )


def _lines_intersect(
    line_a: Tuple[Point, Point],
    line_b: Tuple[Point, Point],
) -> bool:
    """
    Check if two line segments intersect (not just share endpoints).

    Uses Shapely for robust intersection testing.
    """
    from shapely.geometry import LineString as ShapelyLine

    a_start, a_end = line_a
    b_start, b_end = line_b

    # Create Shapely lines
    shapely_a = ShapelyLine([(a_start.x, a_start.y), (a_end.x, a_end.y)])
    shapely_b = ShapelyLine([(b_start.x, b_start.y), (b_end.x, b_end.y)])

    # Check intersection
    if not shapely_a.intersects(shapely_b):
        return False

    # Get intersection geometry
    intersection = shapely_a.intersection(shapely_b)

    # Must have non-trivial intersection (not just touching at a point)
    # For line-line, intersection is typically a point or segment
    if intersection.is_empty:
        return False

    # Point intersection is allowed (lines crossing)
    if intersection.geom_type == 'Point':
        return True

    # Segment overlap with length
    if intersection.geom_type == 'LineString' and intersection.length > INTERSECTION_TOLERANCE:
        return True

    return False


def _aisles_are_connected(
    aisle_a: Tuple[Point, Point],
    aisle_b: Tuple[Point, Point],
    tolerance: float = ENDPOINT_TOLERANCE,
) -> bool:
    """
    Check if two aisles are connected.

    Connected means:
    1. They share an endpoint (within tolerance), OR
    2. They intersect (crossing or overlapping)
    """
    # Fast path: check shared endpoints first
    if _aisles_share_endpoint(aisle_a, aisle_b, tolerance):
        return True

    # Check intersection
    return _lines_intersect(aisle_a, aisle_b)


# =============================================================================
# MAIN CONNECTIVITY CHECK
# =============================================================================

def check_circulation_connected(
    aisles: List[Any],
    tolerance: float = ENDPOINT_TOLERANCE,
    check_intersections: bool = True,
) -> bool:
    """
    Check if all drive aisles form a single connected component.

    Connectivity means every aisle segment is reachable from any other
    via shared endpoints or intersections.

    Args:
        aisles: List of aisle objects (Aisle60, Line, or (Point, Point) tuples)
        tolerance: Distance tolerance for shared endpoints (default 0.5 ft)
        check_intersections: If True, also check for crossing aisles (default True)

    Returns:
        True if all aisles are connected, False otherwise
        Returns True for empty or single-aisle lists (trivially connected)

    Performance:
        O(n²) for pairwise comparison, O(n α(n)) ≈ O(n) for Union-Find
        With spatial indexing: O(n log n) average case

    Examples:
        >>> from sitefit.core.geometry import Point
        >>> # Connected T-junction
        >>> aisle1 = (Point(0, 0), Point(100, 0))
        >>> aisle2 = (Point(50, 0), Point(50, 100))
        >>> check_circulation_connected([aisle1, aisle2])
        True

        >>> # Disconnected parallel aisles
        >>> aisle3 = (Point(0, 50), Point(100, 50))
        >>> check_circulation_connected([aisle1, aisle3])
        False
    """
    # Trivially connected: 0 or 1 aisle
    if len(aisles) <= 1:
        return True

    # Extract endpoints for all aisles
    endpoints: List[Tuple[Point, Point]] = []
    for aisle in aisles:
        try:
            endpoints.append(_get_aisle_endpoints(aisle))
        except TypeError:
            # Skip invalid aisles
            continue

    n = len(endpoints)
    if n <= 1:
        return True

    # Build spatial index: map grid cell to list of (aisle_index, point)
    # Use a smaller cell size for precise endpoint matching
    cell_size = max(tolerance * 2, 1.0)
    cell_to_points: Dict[Tuple[int, int], List[Tuple[int, Point]]] = {}

    def grid_cell(p: Point) -> Tuple[int, int]:
        return (int(p.x / cell_size), int(p.y / cell_size))

    def nearby_cells(p: Point) -> List[Tuple[int, int]]:
        cx, cy = grid_cell(p)
        return [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]

    # Index all aisle endpoints
    for i, (start, end) in enumerate(endpoints):
        for pt in [start, end]:
            cell = grid_cell(pt)
            if cell not in cell_to_points:
                cell_to_points[cell] = []
            cell_to_points[cell].append((i, pt))

    # Initialize Union-Find
    uf = UnionFind(n)

    # For each aisle endpoint, find nearby points from other aisles
    for i, (start, end) in enumerate(endpoints):
        for pt in [start, end]:
            # Check all nearby cells for close points
            for cell in nearby_cells(pt):
                if cell not in cell_to_points:
                    continue
                for j, other_pt in cell_to_points[cell]:
                    if i == j:
                        continue
                    if uf.find(i) == uf.find(j):
                        continue  # Already in same component

                    # Check if points are close
                    if _points_are_close(pt, other_pt, tolerance):
                        uf.union(i, j)
                        if uf.is_connected():
                            return True

    # If check_intersections is enabled, do the expensive intersection check
    if check_intersections and not uf.is_connected():
        for i in range(n):
            for j in range(i + 1, n):
                if uf.find(i) == uf.find(j):
                    continue
                if _lines_intersect(endpoints[i], endpoints[j]):
                    uf.union(i, j)
                    if uf.is_connected():
                        return True

    return uf.is_connected()


def get_connected_components(
    aisles: List[Any],
    tolerance: float = ENDPOINT_TOLERANCE,
) -> List[List[int]]:
    """
    Get the connected components of aisles (for debugging/diagnostics).

    Args:
        aisles: List of aisle objects
        tolerance: Distance tolerance for shared endpoints

    Returns:
        List of component lists, each containing aisle indices
    """
    if not aisles:
        return []

    # Extract endpoints
    endpoints: List[Tuple[Point, Point]] = []
    for aisle in aisles:
        try:
            endpoints.append(_get_aisle_endpoints(aisle))
        except TypeError:
            continue

    n = len(endpoints)
    if n == 0:
        return []

    # Initialize Union-Find
    uf = UnionFind(n)

    # Check all pairs
    for i in range(n):
        for j in range(i + 1, n):
            if _aisles_are_connected(endpoints[i], endpoints[j], tolerance):
                uf.union(i, j)

    # Group by root
    components: Dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        if root not in components:
            components[root] = []
        components[root].append(i)

    return list(components.values())


def count_connected_components(
    aisles: List[Any],
    tolerance: float = ENDPOINT_TOLERANCE,
) -> int:
    """
    Count the number of connected components.

    Args:
        aisles: List of aisle objects
        tolerance: Distance tolerance for shared endpoints

    Returns:
        Number of disjoint aisle networks
    """
    if not aisles:
        return 0

    # Extract endpoints
    endpoints: List[Tuple[Point, Point]] = []
    for aisle in aisles:
        try:
            endpoints.append(_get_aisle_endpoints(aisle))
        except TypeError:
            continue

    n = len(endpoints)
    if n == 0:
        return 0

    # Initialize Union-Find
    uf = UnionFind(n)

    # Check all pairs
    for i in range(n):
        for j in range(i + 1, n):
            if _aisles_are_connected(endpoints[i], endpoints[j], tolerance):
                uf.union(i, j)

    return uf.get_component_count()


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class ConnectivityResult:
    """
    Result of connectivity check with additional diagnostics.

    Attributes:
        is_connected: Whether all aisles form a single component
        aisle_count: Total number of aisles checked
        component_count: Number of disjoint components
    """
    is_connected: bool
    aisle_count: int
    component_count: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_connected": self.is_connected,
            "aisle_count": self.aisle_count,
            "component_count": self.component_count,
        }


def check_circulation_connectivity(
    aisles: List[Any],
    tolerance: float = ENDPOINT_TOLERANCE,
) -> ConnectivityResult:
    """
    Check circulation connectivity with full diagnostics.

    Args:
        aisles: List of aisle objects
        tolerance: Distance tolerance for shared endpoints

    Returns:
        ConnectivityResult with is_connected and component counts
    """
    if not aisles:
        return ConnectivityResult(
            is_connected=True,
            aisle_count=0,
            component_count=0,
        )

    # Extract endpoints
    endpoints: List[Tuple[Point, Point]] = []
    for aisle in aisles:
        try:
            endpoints.append(_get_aisle_endpoints(aisle))
        except TypeError:
            continue

    n = len(endpoints)
    if n == 0:
        return ConnectivityResult(
            is_connected=True,
            aisle_count=0,
            component_count=0,
        )

    if n == 1:
        return ConnectivityResult(
            is_connected=True,
            aisle_count=1,
            component_count=1,
        )

    # Initialize Union-Find
    uf = UnionFind(n)

    # Check all pairs
    for i in range(n):
        for j in range(i + 1, n):
            if _aisles_are_connected(endpoints[i], endpoints[j], tolerance):
                uf.union(i, j)

    return ConnectivityResult(
        is_connected=uf.is_connected(),
        aisle_count=n,
        component_count=uf.get_component_count(),
    )
