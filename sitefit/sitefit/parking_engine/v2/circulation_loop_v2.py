"""
GenFabTools Parking Engine v2 — CirculationLoop

ARCHITECTURE:
This module generates ONE continuous, closed, one-way circulation loop.
No stalls. No parking rows. No connectors. No fallback to V1.

The loop is generated FIRST. Once frozen, it is NEVER modified.

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum

from shapely.geometry import Polygon as ShapelyPolygon, LineString, LinearRing
from shapely.ops import unary_union


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

DEFAULT_AISLE_WIDTH = 15.0  # One-way aisle width (feet)
MIN_LOOP_DIMENSION = 30.0   # Minimum loop dimension to be valid

# Aisle widths by circulation mode
AISLE_WIDTH_ONE_WAY = 15.0   # One-way circulation aisle width
AISLE_WIDTH_TWO_WAY = 24.0   # Two-way circulation aisle width


# =============================================================================
# CIRCULATION MODE
# =============================================================================

class CirculationMode(str, Enum):
    """
    Circulation mode for the loop.

    ONE_WAY: Unidirectional traffic (narrower aisles, single-loaded for angled)
    TWO_WAY: Bidirectional traffic (wider aisles, double-loaded)

    Mode affects:
    - Aisle width (ONE_WAY=15ft, TWO_WAY=24ft)
    - Loading type (ONE_WAY=single-loaded for angled, TWO_WAY=double-loaded)
    - Supported angles (45°/60° are ONE_WAY only)
    """
    ONE_WAY = "ONE_WAY"
    TWO_WAY = "TWO_WAY"


# =============================================================================
# CIRCULATION DIRECTION
# =============================================================================

class CirculationDirection(str, Enum):
    """Direction of traffic flow around the loop."""
    CLOCKWISE = "CLOCKWISE"
    COUNTER_CLOCKWISE = "COUNTER_CLOCKWISE"


# =============================================================================
# SETBACKS
# =============================================================================

@dataclass(frozen=True)
class Setbacks:
    """
    Setback distances from site boundary edges.

    All values in feet.
    """
    north: float = 0.0
    south: float = 0.0
    east: float = 0.0
    west: float = 0.0

    @classmethod
    def uniform(cls, value: float) -> "Setbacks":
        """Create uniform setbacks on all sides."""
        return cls(north=value, south=value, east=value, west=value)


# =============================================================================
# V2 LAYOUT ERROR — NO FALLBACK TO V1
# =============================================================================

class V2LayoutError(Exception):
    """
    Explicit V2 layout error.

    When raised, the orchestrator must NOT fallback to V1.
    Return empty layout instead.
    """
    pass


# =============================================================================
# LOOP EDGE — One edge of the circulation loop
# =============================================================================

@dataclass(frozen=True)
class LoopEdge:
    """
    One edge of the circulation loop.

    Edges are ordered to form a continuous closed ring.
    Direction vectors point along the direction of travel.

    Attributes:
        index: Edge index (0 to 3 for rectangular loop)
        start: Start point (x, y)
        end: End point (x, y)
        direction: Unit vector along edge (direction of travel)
        normal: Unit vector perpendicular to edge (points inward)
        length: Edge length in feet
    """
    index: int
    start: Tuple[float, float]
    end: Tuple[float, float]
    direction: Tuple[float, float]
    normal: Tuple[float, float]
    length: float

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start": {"x": self.start[0], "y": self.start[1]},
            "end": {"x": self.end[0], "y": self.end[1]},
            "direction": {"dx": self.direction[0], "dy": self.direction[1]},
            "normal": {"nx": self.normal[0], "ny": self.normal[1]},
            "length": round(self.length, 2),
        }


# =============================================================================
# FROZEN CIRCULATION LOOP
# =============================================================================

@dataclass(frozen=True)
class CirculationLoop:
    """
    Frozen circulation loop geometry.

    Once created, this geometry CANNOT be modified.
    This is the ONLY circulation object. No stalls, no rows, no connectors.

    Attributes:
        loop_polygon: The circulation loop as a Shapely polygon (frozen)
        loop_centerline: Closed ring representing loop centerline
        loop_edges: Ordered edges with direction vectors
        circulation_direction: Direction of travel (clockwise/counter-clockwise)
        aisle_width: Width of the circulation aisle
    """
    loop_polygon: ShapelyPolygon
    loop_centerline: LinearRing
    loop_edges: Tuple[LoopEdge, ...]
    circulation_direction: CirculationDirection
    aisle_width: float

    def __post_init__(self):
        """Validate that loop is frozen and immutable."""
        if not isinstance(self.loop_polygon, ShapelyPolygon):
            raise V2LayoutError("loop_polygon must be a Shapely Polygon")
        if not isinstance(self.loop_centerline, LinearRing):
            raise V2LayoutError("loop_centerline must be a LinearRing")

    @property
    def is_valid(self) -> bool:
        """True if the loop is valid (continuous, non-self-intersecting)."""
        return (
            self.loop_polygon.is_valid and
            not self.loop_polygon.is_empty and
            self.loop_centerline.is_valid and
            self.loop_centerline.is_ring
        )

    @property
    def is_closed(self) -> bool:
        """True if the loop forms a closed ring."""
        return self.loop_centerline.is_ring

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        return self.loop_polygon.bounds

    @property
    def total_length(self) -> float:
        """Total length of the loop centerline."""
        return self.loop_centerline.length

    @property
    def edge_count(self) -> int:
        """Number of edges in the loop."""
        return len(self.loop_edges)

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is inside the loop polygon."""
        from shapely.geometry import Point as ShapelyPoint
        return self.loop_polygon.contains(ShapelyPoint(x, y))

    def to_dict(self) -> dict:
        """Serialize loop for JSON output."""
        centerline_coords = list(self.loop_centerline.coords)
        polygon_coords = list(self.loop_polygon.exterior.coords)

        return {
            "is_valid": self.is_valid,
            "is_closed": self.is_closed,
            "circulation_direction": self.circulation_direction.value,
            "aisle_width": self.aisle_width,
            "total_length": round(self.total_length, 2),
            "edge_count": self.edge_count,
            "centerline": [{"x": c[0], "y": c[1]} for c in centerline_coords],
            "polygon": [{"x": c[0], "y": c[1]} for c in polygon_coords[:-1]],
            "edges": [e.to_dict() for e in self.loop_edges],
        }


# =============================================================================
# CIRCULATION LOOP GENERATOR
# =============================================================================

class CirculationLoopGenerator:
    """
    Generates ONE continuous closed circulation loop.

    No stalls. No rows. No connectors. No V1 fallback.

    The loop is a simple rectangular ring aligned to site bbox.
    Loop centerline forms a closed ring.
    Loop polygon width = aisle_width, offset from centerline.

    Usage:
        generator = CirculationLoopGenerator(
            aisle_width=15.0,
            circulation_direction=CirculationDirection.CLOCKWISE,
        )
        loop = generator.generate(site_boundary, setbacks)
    """

    def __init__(
        self,
        aisle_width: float = DEFAULT_AISLE_WIDTH,
        circulation_direction: CirculationDirection = CirculationDirection.CLOCKWISE,
    ):
        self.aisle_width = aisle_width
        self.circulation_direction = circulation_direction

    def generate(
        self,
        site_boundary: ShapelyPolygon,
        setbacks: Setbacks,
    ) -> CirculationLoop:
        """
        Generate a frozen circulation loop.

        Args:
            site_boundary: Site boundary polygon
            setbacks: Setback distances from each edge

        Returns:
            Frozen CirculationLoop

        Raises:
            V2LayoutError: If loop cannot be generated (NO V1 FALLBACK)
        """
        print(f"\n[CIRCULATION-LOOP] Generating one-way loop")
        print(f"[CIRCULATION-LOOP] Aisle width: {self.aisle_width} ft")
        print(
            f"[CIRCULATION-LOOP] Direction: {self.circulation_direction.value}")

        # Step 1: Compute buildable polygon (site minus setbacks)
        buildable = self._compute_buildable_polygon(site_boundary, setbacks)
        if buildable is None or buildable.is_empty:
            raise V2LayoutError("Buildable polygon is empty after setbacks")

        min_x, min_y, max_x, max_y = buildable.bounds
        width = max_x - min_x
        height = max_y - min_y

        print(
            f"[CIRCULATION-LOOP] Buildable area: {width:.1f} x {height:.1f} ft")

        # Step 2: Validate dimensions
        half_aisle = self.aisle_width / 2
        min_dimension = self.aisle_width * 2 + MIN_LOOP_DIMENSION

        if width < min_dimension or height < min_dimension:
            raise V2LayoutError(
                f"Buildable area too small: {width:.1f}x{height:.1f} ft, "
                f"minimum: {min_dimension:.1f}x{min_dimension:.1f} ft"
            )

        # Step 3: Generate loop centerline (rectangular ring)
        # Centerline is inset by half aisle width from buildable bounds
        cx_min = min_x + half_aisle
        cy_min = min_y + half_aisle
        cx_max = max_x - half_aisle
        cy_max = max_y - half_aisle

        # Create centerline as closed ring
        if self.circulation_direction == CirculationDirection.CLOCKWISE:
            # Clockwise: bottom→right→top→left→bottom
            centerline_coords = [
                (cx_min, cy_min),  # Bottom-left
                (cx_max, cy_min),  # Bottom-right
                (cx_max, cy_max),  # Top-right
                (cx_min, cy_max),  # Top-left
                (cx_min, cy_min),  # Close ring
            ]
        else:
            # Counter-clockwise: bottom→left→top→right→bottom
            centerline_coords = [
                (cx_min, cy_min),  # Bottom-left
                (cx_min, cy_max),  # Top-left
                (cx_max, cy_max),  # Top-right
                (cx_max, cy_min),  # Bottom-right
                (cx_min, cy_min),  # Close ring
            ]

        centerline = LinearRing(centerline_coords)

        if not centerline.is_valid or not centerline.is_ring:
            raise V2LayoutError("Failed to create valid loop centerline")

        print(
            f"[CIRCULATION-LOOP] Centerline length: {centerline.length:.1f} ft")

        # Step 4: Generate loop polygon (offset centerline by half aisle width)
        # The loop polygon is a "hollow rectangle" or ring shape
        # Outer boundary = centerline offset outward by half_aisle
        # Inner boundary = centerline offset inward by half_aisle
        outer_ring = centerline.buffer(half_aisle, cap_style=3, join_style=2)
        inner_ring = centerline.buffer(-half_aisle, cap_style=3, join_style=2)

        # Loop polygon is outer minus inner (the aisle itself)
        loop_polygon = outer_ring.difference(inner_ring)

        if loop_polygon.is_empty or not loop_polygon.is_valid:
            raise V2LayoutError("Failed to create valid loop polygon")

        # Handle MultiPolygon case - take the largest
        if loop_polygon.geom_type == 'MultiPolygon':
            loop_polygon = max(loop_polygon.geoms, key=lambda g: g.area)

        print(
            f"[CIRCULATION-LOOP] Loop polygon area: {loop_polygon.area:.1f} sq ft")

        # Step 5: Generate ordered loop edges with direction vectors
        edges = self._create_loop_edges(
            centerline_coords[:-1])  # Exclude closing point

        # Step 6: Validate loop is fully inside buildable polygon
        if not buildable.contains(loop_polygon):
            # Allow slight tolerance for floating point
            if not buildable.buffer(0.1).contains(loop_polygon):
                raise V2LayoutError(
                    "Loop polygon extends outside buildable area")

        # Step 7: Validate loop is continuous and non-self-intersecting
        if not centerline.is_simple:
            raise V2LayoutError("Loop centerline self-intersects")

        # Step 8: Create frozen CirculationLoop
        circulation_loop = CirculationLoop(
            loop_polygon=loop_polygon,
            loop_centerline=centerline,
            loop_edges=tuple(edges),
            circulation_direction=self.circulation_direction,
            aisle_width=self.aisle_width,
        )

        print(f"[CIRCULATION-LOOP] Generated {len(edges)} edges")
        print(f"[CIRCULATION-LOOP] Loop is valid: {circulation_loop.is_valid}")
        print(
            f"[CIRCULATION-LOOP] Loop is closed: {circulation_loop.is_closed}")

        if not circulation_loop.is_valid:
            raise V2LayoutError("Generated loop failed validation")

        return circulation_loop

    def _compute_buildable_polygon(
        self,
        site_boundary: ShapelyPolygon,
        setbacks: Setbacks,
    ) -> Optional[ShapelyPolygon]:
        """
        Compute buildable polygon by insetting site boundary by setbacks.

        For now, uses bbox-based approach for rectangular sites.
        """
        min_x, min_y, max_x, max_y = site_boundary.bounds

        # Apply directional setbacks
        inner_min_x = min_x + setbacks.west
        inner_min_y = min_y + setbacks.south
        inner_max_x = max_x - setbacks.east
        inner_max_y = max_y - setbacks.north

        # Validate positive dimensions
        if inner_max_x <= inner_min_x or inner_max_y <= inner_min_y:
            return None

        # Create buildable rectangle
        return ShapelyPolygon([
            (inner_min_x, inner_min_y),
            (inner_max_x, inner_min_y),
            (inner_max_x, inner_max_y),
            (inner_min_x, inner_max_y),
        ])

    def _create_loop_edges(
        self,
        centerline_coords: List[Tuple[float, float]],
    ) -> List[LoopEdge]:
        """
        Create ordered loop edges from centerline coordinates.

        Each edge has direction and normal vectors.
        """
        edges = []
        n = len(centerline_coords)

        for i in range(n):
            start = centerline_coords[i]
            end = centerline_coords[(i + 1) % n]

            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.sqrt(dx * dx + dy * dy)

            if length < 0.001:
                continue  # Skip zero-length edges

            # Direction vector (normalized)
            direction = (dx / length, dy / length)

            # Normal vector (perpendicular, points inward for clockwise)
            # For clockwise: rotate direction 90° clockwise = (dy, -dx)
            # For counter-clockwise: rotate 90° counter-clockwise = (-dy, dx)
            if self.circulation_direction == CirculationDirection.CLOCKWISE:
                normal = (direction[1], -direction[0])
            else:
                normal = (-direction[1], direction[0])

            edges.append(LoopEdge(
                index=i,
                start=start,
                end=end,
                direction=direction,
                normal=normal,
                length=length,
            ))

        return edges


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate_circulation_loop(
    site_boundary: ShapelyPolygon,
    setbacks: Optional[Setbacks] = None,
    aisle_width: Optional[float] = None,
    circulation_direction: CirculationDirection = CirculationDirection.CLOCKWISE,
    circulation_mode: CirculationMode = CirculationMode.ONE_WAY,
    parking_angle: int = 90,
) -> CirculationLoop:
    """
    Generate a circulation loop for the given site.

    This is the main entry point for circulation generation.

    Mode-based aisle width:
    - ONE_WAY: 15 ft
    - TWO_WAY: 24 ft

    Angle validation:
    - 45°/60° with TWO_WAY → raises V2LayoutError
    - 90° works with both ONE_WAY and TWO_WAY

    Args:
        site_boundary: Site boundary polygon
        setbacks: Setback distances (default: 0 on all sides)
        aisle_width: Override aisle width (default: derived from mode)
        circulation_direction: Direction of travel (default: clockwise)
        circulation_mode: Circulation mode (default: ONE_WAY)
        parking_angle: Parking angle in degrees (default: 90)

    Returns:
        Frozen CirculationLoop

    Raises:
        V2LayoutError: If loop cannot be generated or angle/mode incompatible
    """
    if setbacks is None:
        setbacks = Setbacks.uniform(0.0)

    # Validate angle + mode compatibility
    if parking_angle in (45, 60) and circulation_mode == CirculationMode.TWO_WAY:
        raise V2LayoutError(
            f"{parking_angle}° parking requires ONE_WAY circulation mode. "
            f"TWO_WAY is not supported for angled parking."
        )

    # Determine aisle width from mode if not explicitly provided
    if aisle_width is None:
        if circulation_mode == CirculationMode.ONE_WAY:
            aisle_width = AISLE_WIDTH_ONE_WAY
        else:
            aisle_width = AISLE_WIDTH_TWO_WAY

    print(f"[CIRCULATION-LOOP] Mode: {circulation_mode.value}")

    generator = CirculationLoopGenerator(
        aisle_width=aisle_width,
        circulation_direction=circulation_direction,
    )

    return generator.generate(site_boundary, setbacks)


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_circulation_loop(loop: CirculationLoop) -> List[str]:
    """
    Validate a circulation loop.

    Returns list of errors (empty if valid).
    """
    errors = []

    if not loop.is_valid:
        errors.append("Loop polygon is invalid")

    if not loop.is_closed:
        errors.append("Loop centerline is not closed")

    if loop.edge_count < 3:
        errors.append(f"Loop has only {loop.edge_count} edges (minimum 3)")

    # Check edge continuity
    edges = loop.loop_edges
    for i in range(len(edges)):
        curr = edges[i]
        next_edge = edges[(i + 1) % len(edges)]

        gap = math.sqrt(
            (next_edge.start[0] - curr.end[0]) ** 2 +
            (next_edge.start[1] - curr.end[1]) ** 2
        )

        if gap > 0.1:
            errors.append(
                f"Gap of {gap:.2f} ft between edges {i} and {(i+1) % len(edges)}")

    return errors


# =============================================================================
# STALL DIMENSIONS
# =============================================================================

STALL_WIDTH = 9.0   # Standard stall width (feet)
STALL_LENGTH = 18.0  # Standard stall length/depth (feet)
# Alias for backward compatibility
STALL_DEPTH = STALL_LENGTH


# =============================================================================
# ANGLE-DEPENDENT STALL GEOMETRY FUNCTIONS
# =============================================================================

def compute_stall_spacing(angle: int) -> float:
    """
    Compute spacing between stall anchors along edge.

    spacing = stall_width / sin(angle)

    For 90°: spacing = 9.0 ft
    For 60°: spacing = 9 / sin(60°) = 10.39 ft
    For 45°: spacing = 9 / sin(45°) = 12.73 ft
    """
    if angle == 90:
        return STALL_WIDTH
    angle_rad = math.radians(angle)
    return STALL_WIDTH / math.sin(angle_rad)


def compute_module_depth(angle: int, buffer: float = 0.0) -> float:
    """
    Compute effective module depth (perpendicular projection from aisle edge).

    depth = stall_length * sin(angle) + buffer

    For 90°: depth = 18.0 ft
    For 60°: depth = 18 * sin(60°) = 15.59 ft
    For 45°: depth = 18 * sin(45°) = 12.73 ft
    """
    if angle == 90:
        return STALL_LENGTH + buffer
    angle_rad = math.radians(angle)
    return STALL_LENGTH * math.sin(angle_rad) + buffer


def compute_projection_vector(
    angle: int,
    edge_direction: Tuple[float, float],
    normal: Tuple[float, float],
) -> Tuple[float, float]:
    """
    Compute the projection vector for stall body direction.

    For 90°: projection is same as normal (perpendicular to aisle)
    For 60°: rotate normal by 30° toward travel direction
    For 45°: rotate normal by 45° toward travel direction

    The rotation direction depends on which side of the aisle:
    - Stalls on right side of travel: rotate clockwise
    - Stalls on left side of travel: rotate counter-clockwise

    Args:
        angle: Parking angle (45, 60, 90)
        edge_direction: Unit vector along aisle edge (travel direction)
        normal: Unit normal vector (perpendicular to edge, pointing toward stall)

    Returns:
        Unit projection vector for stall body direction
    """
    if angle == 90:
        return normal

    # Rotation angle from normal toward travel direction
    # For angled parking, cars enter at an angle
    # Rotation: 90 - parking_angle degrees
    rotation_deg = 90 - angle  # 30° for 60° parking, 45° for 45° parking
    rotation_rad = math.radians(rotation_deg)

    nx, ny = normal
    dx, dy = edge_direction

    # Determine rotation direction based on which side of aisle
    # Cross product of edge_direction and normal tells us the side
    cross = dx * ny - dy * nx
    # cross > 0: normal is to the left of travel (CCW rotation needed)
    # cross < 0: normal is to the right of travel (CW rotation needed)

    if cross > 0:
        # CCW rotation
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
    else:
        # CW rotation (negative angle)
        cos_r = math.cos(-rotation_rad)
        sin_r = math.sin(-rotation_rad)

    # Rotate normal vector
    proj_x = nx * cos_r - ny * sin_r
    proj_y = nx * sin_r + ny * cos_r

    return (proj_x, proj_y)


# =============================================================================
# PARKING BAND — Parallelogram band for angled parking (45°/60°)
# =============================================================================

@dataclass(frozen=True)
class ParkingBand:
    """
    A parallelogram-shaped parking band for angled parking.

    For 45° and 60° parking, stalls are NOT attached directly to circulation edges.
    Instead, a parking band is projected downstream along the travel vector.

    The band is a parallelogram with:
    - One edge along the circulation aisle
    - Depth = module_depth(angle) perpendicular to circulation
    - Stalls placed along the travel vector inside the band

    Attributes:
        id: Unique band identifier
        edge_index: Index of the circulation edge this band is based on
        polygon: Band footprint as Shapely parallelogram
        travel_vector: Unit vector of traffic travel direction
        normal_out: Unit normal pointing away from circulation (toward band)
        angle: Parking angle (45 or 60)
        band_depth: Perpendicular depth of the band
        stalls: List of stalls within this band
    """
    id: str
    edge_index: int
    polygon: ShapelyPolygon
    travel_vector: Tuple[float, float]
    normal_out: Tuple[float, float]
    angle: int
    band_depth: float
    stalls: Tuple['AttachedStall', ...] = field(default_factory=tuple)

    @property
    def stall_count(self) -> int:
        return len(self.stalls)

    def to_dict(self) -> dict:
        coords = list(self.polygon.exterior.coords)
        return {
            "id": self.id,
            "edge_index": self.edge_index,
            "angle": self.angle,
            "band_depth": self.band_depth,
            "stall_count": self.stall_count,
            "travel_vector": {"x": self.travel_vector[0], "y": self.travel_vector[1]},
            "normal_out": {"x": self.normal_out[0], "y": self.normal_out[1]},
            "geometry": {
                "points": [{"x": c[0], "y": c[1]} for c in coords[:-1]]
            },
            "stalls": [s.to_dict() for s in self.stalls],
        }


# =============================================================================
# ANGLE-AWARE PARKING BAND GENERATOR
# =============================================================================

class AngleAwareParkingBandGenerator:
    """
    Generate parking bands for angled parking (45° and 60°).

    ARCHITECTURE:
    - For 45°/60° parking, stalls are NOT attached directly to circulation edges
    - Instead, a parallelogram band is projected outward from circulation
    - Stalls are placed along the travel vector (not perpendicular to edge)
    - Each band is single-loaded by definition
    - Bands that intersect circulation or site boundary are discarded entirely

    The circulation loop remains FROZEN and unchanged.

    Usage:
        generator = AngleAwareParkingBandGenerator(angle=45)
        result = generator.generate_bands(circulation, buildable_polygon)
    """

    def __init__(self, angle: int):
        """
        Initialize band generator.

        Args:
            angle: Parking angle (45 or 60 only)
        """
        if angle not in (45, 60):
            raise V2LayoutError(
                f"AngleAwareParkingBandGenerator only supports 45° and 60°. Got {angle}°"
            )

        self.angle = angle
        self.stall_spacing = compute_stall_spacing(angle)
        self.module_depth = compute_module_depth(angle)

        # Corner clearance multipliers
        if angle == 60:
            self.corner_clearance_multiplier = 1.2
        else:  # 45
            self.corner_clearance_multiplier = 1.5

    def _is_edge_direction_compatible(self, edge: LoopEdge) -> bool:
        """
        Check if edge direction is compatible with angled parking.

        Only horizontal edges are allowed for 45°/60° parking.
        """
        EPSILON = 0.01
        dx, dy = edge.direction
        return abs(dy) < EPSILON

    def generate_bands(
        self,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> List[ParkingBand]:
        """
        Generate parking bands from circulation edges.

        For each compatible edge:
        1. Derive travel vector from circulation direction
        2. Compute band parallelogram outside of circulation
        3. Validate band doesn't intersect circulation or site boundary
        4. Populate stalls along travel vector if band is valid
        5. Discard entire band if it intersects anything

        Args:
            circulation: Frozen circulation loop (NOT modified)
            buildable_polygon: Site boundary / buildable area

        Returns:
            List of valid parking bands with stalls
        """
        print(f"\n[BAND-GEN] Generating {self.angle}° parking bands")
        print(f"[BAND-GEN] Module depth: {self.module_depth:.2f} ft")
        print(f"[BAND-GEN] Stall spacing: {self.stall_spacing:.2f} ft")

        bands: List[ParkingBand] = []

        for edge in circulation.loop_edges:
            # Only horizontal edges for angled parking
            if not self._is_edge_direction_compatible(edge):
                dx, dy = edge.direction
                print(
                    f"[BAND-GEN] Edge {edge.index}: direction ({dx:.2f}, {dy:.2f}) incompatible, skipping")
                continue

            band = self._create_band_for_edge(
                edge, circulation, buildable_polygon)
            if band is not None:
                bands.append(band)
                print(
                    f"[BAND-GEN] Edge {edge.index}: created band with {band.stall_count} stalls")
            else:
                print(
                    f"[BAND-GEN] Edge {edge.index}: band discarded (intersection)")

        total_stalls = sum(b.stall_count for b in bands)
        print(
            f"[BAND-GEN] Generated {len(bands)} bands, {total_stalls} total stalls")

        return bands

    def _create_band_for_edge(
        self,
        edge: LoopEdge,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> Optional[ParkingBand]:
        """
        Create a parking band for a single edge.

        Returns None if band intersects circulation or is outside buildable area.
        """
        # Travel vector = edge direction (direction of traffic flow)
        travel_dx, travel_dy = edge.direction

        # Normal pointing OUTWARD from circulation (away from center)
        # Edge normal points inward for clockwise, so outward is negative
        normal_out = (-edge.normal[0], -edge.normal[1])

        # Band starts at outer edge of aisle
        aisle_half = circulation.aisle_width / 2

        # Corner clearance
        corner_clearance = circulation.aisle_width * self.corner_clearance_multiplier

        # Usable edge length after corner clearance
        usable_length = edge.length - 2 * corner_clearance
        if usable_length < self.stall_spacing:
            return None

        # Band parallelogram vertices:
        # Start/end points along edge, offset outward by aisle_half, then extend by module_depth

        # Edge start + corner clearance
        band_start_x = edge.start[0] + corner_clearance * \
            travel_dx + aisle_half * normal_out[0]
        band_start_y = edge.start[1] + corner_clearance * \
            travel_dy + aisle_half * normal_out[1]

        # Edge end - corner clearance
        band_end_x = edge.end[0] - corner_clearance * \
            travel_dx + aisle_half * normal_out[0]
        band_end_y = edge.end[1] - corner_clearance * \
            travel_dy + aisle_half * normal_out[1]

        # Outer edge of band (offset by module_depth)
        band_start_outer_x = band_start_x + self.module_depth * normal_out[0]
        band_start_outer_y = band_start_y + self.module_depth * normal_out[1]
        band_end_outer_x = band_end_x + self.module_depth * normal_out[0]
        band_end_outer_y = band_end_y + self.module_depth * normal_out[1]

        # Create band polygon (parallelogram)
        band_polygon = ShapelyPolygon([
            (band_start_x, band_start_y),
            (band_end_x, band_end_y),
            (band_end_outer_x, band_end_outer_y),
            (band_start_outer_x, band_start_outer_y),
        ])

        # VALIDATION: Discard entire band if it intersects circulation
        if circulation.loop_polygon.intersects(band_polygon):
            intersection = circulation.loop_polygon.intersection(band_polygon)
            if hasattr(intersection, 'area') and intersection.area > 1.0:
                print(
                    f"[BAND-GEN] Edge {edge.index}: band intersects circulation (area={intersection.area:.1f})")
                return None

        # VALIDATION: Discard band if any part is outside buildable area
        if not buildable_polygon.contains(band_polygon):
            # Check if it's mostly inside
            intersection = buildable_polygon.intersection(band_polygon)
            if hasattr(intersection, 'area'):
                overlap_ratio = intersection.area / band_polygon.area
                if overlap_ratio < 0.9:  # Less than 90% inside
                    print(
                        f"[BAND-GEN] Edge {edge.index}: band outside buildable (overlap={overlap_ratio*100:.0f}%)")
                    return None

        # Generate stalls along the travel vector within the band
        stalls = self._populate_stalls_in_band(
            edge_index=edge.index,
            band_polygon=band_polygon,
            travel_vector=(travel_dx, travel_dy),
            normal_out=normal_out,
            band_start=(band_start_x, band_start_y),
            usable_length=usable_length,
            circulation=circulation,
            buildable_polygon=buildable_polygon,
        )

        return ParkingBand(
            id=f"band-{edge.index}",
            edge_index=edge.index,
            polygon=band_polygon,
            travel_vector=(travel_dx, travel_dy),
            normal_out=normal_out,
            angle=self.angle,
            band_depth=self.module_depth,
            stalls=tuple(stalls),
        )

    def _populate_stalls_in_band(
        self,
        edge_index: int,
        band_polygon: ShapelyPolygon,
        travel_vector: Tuple[float, float],
        normal_out: Tuple[float, float],
        band_start: Tuple[float, float],
        usable_length: float,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> List['AttachedStall']:
        """
        Populate stalls along the travel vector within the band.

        Stalls are placed along the travel vector (not perpendicular to edge).
        Each stall is a parallelogram matching the parking angle.
        """
        stalls = []

        # Number of stalls that fit
        num_stalls = int(usable_length / self.stall_spacing)
        if num_stalls == 0:
            return []

        # Center the stalls within usable length
        total_stall_length = num_stalls * self.stall_spacing
        start_offset = (usable_length - total_stall_length) / 2

        travel_dx, travel_dy = travel_vector

        for i in range(num_stalls):
            stall_id = f"stall-{edge_index}-band-{i}"

            # Anchor position along band (center of stall at aisle edge)
            offset = start_offset + (i + 0.5) * self.stall_spacing
            anchor_x = band_start[0] + offset * travel_dx
            anchor_y = band_start[1] + offset * travel_dy
            anchor = (anchor_x, anchor_y)

            # Create stall polygon (parallelogram)
            stall_poly = self._create_stall_polygon(
                anchor=anchor,
                travel_vector=travel_vector,
                normal_out=normal_out,
            )

            # Validate stall is within band and buildable area
            if not band_polygon.contains(stall_poly):
                # Check overlap ratio
                intersection = band_polygon.intersection(stall_poly)
                if hasattr(intersection, 'area') and intersection.area / stall_poly.area < 0.95:
                    continue

            if not buildable_polygon.contains(stall_poly):
                continue

            # Final check: no intersection with circulation
            if circulation.loop_polygon.intersects(stall_poly):
                intersection = circulation.loop_polygon.intersection(
                    stall_poly)
                if hasattr(intersection, 'area') and intersection.area > 0.5:
                    continue

            stalls.append(AttachedStall(
                id=stall_id,
                edge_index=edge_index,
                anchor=anchor,
                polygon=stall_poly,
                angle=self.angle,
                side=-1,  # Always outside for angled parking
            ))

        return stalls

    def _create_stall_polygon(
        self,
        anchor: Tuple[float, float],
        travel_vector: Tuple[float, float],
        normal_out: Tuple[float, float],
    ) -> ShapelyPolygon:
        """
        Create a parallelogram stall polygon for angled parking.

        The stall body extends along the projection vector (rotated from normal).
        Front edge is along travel vector with width = stall_spacing.
        """
        ax, ay = anchor
        travel_dx, travel_dy = travel_vector

        # Compute projection vector (direction stall body extends)
        proj = compute_projection_vector(self.angle, travel_vector, normal_out)
        proj_x, proj_y = proj

        # Half spacing for front edge width
        half_spacing = self.stall_spacing / 2

        # Front-left and front-right at aisle edge (anchor is center)
        fl = (ax - half_spacing * travel_dx, ay - half_spacing * travel_dy)
        fr = (ax + half_spacing * travel_dx, ay + half_spacing * travel_dy)

        # Back extends STALL_LENGTH along projection vector
        bl = (fl[0] + STALL_LENGTH * proj_x, fl[1] + STALL_LENGTH * proj_y)
        br = (fr[0] + STALL_LENGTH * proj_x, fr[1] + STALL_LENGTH * proj_y)

        return ShapelyPolygon([fl, fr, br, bl])


# =============================================================================
# ATTACHED STALL — Stall attached to circulation edge
# =============================================================================

@dataclass(frozen=True)
class AttachedStall:
    """
    A parking stall attached to a circulation edge.

    Stalls are generated by attaching to frozen circulation edges.
    The stall polygon extends AWAY from the circulation.

    Attributes:
        id: Unique stall identifier
        edge_index: Index of the circulation edge this stall attaches to
        anchor: Anchor point where stall meets aisle edge (x, y)
        polygon: Stall footprint as Shapely polygon
        angle: Parking angle in degrees (90, 60, or 45)
        side: +1 for outside (right of travel), -1 for inside (left of travel)
    """
    id: str
    edge_index: int
    anchor: Tuple[float, float]
    polygon: ShapelyPolygon
    angle: int
    side: int

    def to_dict(self) -> dict:
        coords = list(self.polygon.exterior.coords)
        return {
            "id": self.id,
            "edge_index": self.edge_index,
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
            "angle": self.angle,
            "side": self.side,
            "geometry": {
                "points": [{"x": c[0], "y": c[1]} for c in coords[:-1]]
            }
        }


# =============================================================================
# STALL ATTACHMENT RESULT
# =============================================================================

@dataclass
class StallAttachmentResult:
    """
    Result of attaching stalls to circulation edges.

    Attributes:
        circulation: The frozen circulation loop (unchanged)
        stalls: List of attached stalls
        is_valid: True if all stalls are valid (no intersection with circulation)
        validation_errors: List of validation errors
    """
    circulation: CirculationLoop
    stalls: List[AttachedStall]
    is_valid: bool
    validation_errors: List[str] = field(default_factory=list)

    @property
    def stall_count(self) -> int:
        return len(self.stalls) if self.is_valid else 0

    def to_dict(self) -> dict:
        return {
            "stall_count": self.stall_count,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
            "stalls": [s.to_dict() for s in self.stalls] if self.is_valid else [],
        }


# =============================================================================
# STALL ATTACHMENT GENERATOR
# =============================================================================

class StallAttachmentGenerator:
    """
    Attaches parking stalls to frozen circulation edges.

    DOES NOT modify circulation geometry.
    Stalls extend AWAY from the circulation loop.

    Loading rules by circulation mode:
    - TWO_WAY: Double-loaded (both sides of edge) - 90° only
    - ONE_WAY + 90°: Double-loaded
    - ONE_WAY + 45°/60°: Single-loaded (outside of loop only)

    Usage:
        generator = StallAttachmentGenerator(angle=45, circulation_mode=CirculationMode.ONE_WAY)
        result = generator.attach_to_loop(circulation_loop, buildable_polygon)
    """

    def __init__(self, angle: int, circulation_mode: CirculationMode = CirculationMode.ONE_WAY):
        """
        Initialize stall attachment generator.

        Args:
            angle: Parking angle (90, 60, or 45)
            circulation_mode: Circulation mode (ONE_WAY or TWO_WAY)
        """
        if angle not in (90, 60, 45):
            raise V2LayoutError(f"Unsupported parking angle: {angle}")

        # Validate angle + mode compatibility
        if angle in (45, 60) and circulation_mode == CirculationMode.TWO_WAY:
            raise V2LayoutError(
                f"{angle}° parking requires ONE_WAY circulation. TWO_WAY not supported."
            )

        self.angle = angle
        self.circulation_mode = circulation_mode

        # Determine loading type based on circulation mode
        # TWO_WAY: always double-loaded (90° only)
        # ONE_WAY + 90°: double-loaded
        # ONE_WAY + angled: single-loaded
        if circulation_mode == CirculationMode.TWO_WAY:
            self.is_double_loaded = True
        elif angle == 90:
            self.is_double_loaded = True
        else:
            self.is_double_loaded = False

        # Use angle-dependent stall geometry functions
        # Spacing: distance between stall anchors along edge
        self.stall_spacing = compute_stall_spacing(angle)
        # Module depth: perpendicular projection from aisle edge
        self.module_depth = compute_module_depth(angle)

        # For backward compatibility, keep footprint_width as spacing
        self.footprint_width = self.stall_spacing
        self.footprint_depth = self.module_depth

        # Corner clearance multipliers based on angle
        # Required clearance for vehicle turning envelope at corners
        if angle == 90:
            self.corner_clearance_multiplier = 1.0
        elif angle == 60:
            self.corner_clearance_multiplier = 1.2
        else:  # 45
            self.corner_clearance_multiplier = 1.5

    def _compute_corner_clearance(self, aisle_width: float) -> float:
        """
        Compute corner clearance distance based on angle and aisle width.

        Corner clearance prevents stalls from invading turning envelopes.

        Returns:
            Corner clearance distance in feet
        """
        return aisle_width * self.corner_clearance_multiplier

    def _is_edge_direction_compatible(self, edge: LoopEdge) -> bool:
        """
        Check if edge direction is compatible with the parking angle.

        Direction rules:
        - 90° parking: All edges allowed (double-loaded)
        - 60° parking: Only horizontal edges (|direction.y| < ε)
        - 45° parking: Only horizontal edges (|direction.y| < ε)

        Args:
            edge: Circulation edge to check

        Returns:
            True if edge is compatible with parking angle
        """
        EPSILON = 0.01

        if self.angle == 90:
            # 90° parking: all edges allowed
            return True

        # 45° and 60° parking: only horizontal edges
        # Horizontal means edge direction is predominantly along X axis
        # i.e. |direction.y| < ε
        dx, dy = edge.direction
        is_horizontal = abs(dy) < EPSILON

        return is_horizontal

    def attach_to_loop(
        self,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> StallAttachmentResult:
        """
        Attach stalls to frozen circulation edges.

        Args:
            circulation: Frozen circulation loop (NOT modified)
            buildable_polygon: Buildable area for containment check

        Returns:
            StallAttachmentResult with attached stalls

        Raises:
            V2LayoutError: If any stall intersects circulation (HARD FAIL)
        """
        corner_clearance = self._compute_corner_clearance(
            circulation.aisle_width)

        print(
            f"\n[STALL-ATTACH] Attaching {self.angle}° stalls to circulation")
        print(f"[STALL-ATTACH] Double-loaded: {self.is_double_loaded}")
        print(
            f"[STALL-ATTACH] Stall dimensions: {STALL_WIDTH:.1f}' wide x {STALL_LENGTH:.1f}' long")
        print(
            f"[STALL-ATTACH] Spacing along edge: {self.stall_spacing:.2f} ft (width/sin({self.angle}°))")
        print(
            f"[STALL-ATTACH] Module depth: {self.module_depth:.2f} ft (length*sin({self.angle}°))")
        print(
            f"[STALL-ATTACH] Corner clearance: {corner_clearance:.1f} ft (multiplier: {self.corner_clearance_multiplier})")

        all_stalls: List[AttachedStall] = []
        aisle_half = circulation.aisle_width / 2
        compatible_edge_count = 0
        skipped_edge_count = 0

        # Iterate edges in order
        for edge in circulation.loop_edges:
            # EDGE DIRECTION FILTERING: Check if edge is compatible with parking angle
            # This check is applied BEFORE corner clearance logic
            if not self._is_edge_direction_compatible(edge):
                dx, dy = edge.direction
                print(
                    f"[STALL-ATTACH] Edge {edge.index}: direction ({dx:.2f}, {dy:.2f}) incompatible with {self.angle}°, skipping")
                skipped_edge_count += 1
                continue

            compatible_edge_count += 1

            # Determine which sides to place stalls
            if self.is_double_loaded:
                # 90°: Both sides
                sides = [+1, -1]
            else:
                # 45°/60°: Outside only (opposite of normal)
                # Normal points INWARD, so outside is -normal direction
                sides = [-1]  # Outside of loop

            for side in sides:
                edge_stalls = self._generate_stalls_for_edge(
                    edge=edge,
                    side=side,
                    aisle_half=aisle_half,
                    circulation=circulation,
                    buildable_polygon=buildable_polygon,
                )
                all_stalls.extend(edge_stalls)

        print(
            f"[STALL-ATTACH] Compatible edges: {compatible_edge_count}, skipped: {skipped_edge_count}")
        print(
            f"[STALL-ATTACH] Generated {len(all_stalls)} stalls before validation")

        # HARD VALIDATION: Check no stall intersects circulation
        validation_errors = self._validate_no_intersection(
            all_stalls, circulation)

        if validation_errors:
            print(
                f"[STALL-ATTACH] VALIDATION FAILED: {len(validation_errors)} errors")
            for err in validation_errors[:5]:
                print(f"  {err}")
            # HARD FAIL - raise error, DO NOT return partial stalls
            raise V2LayoutError(
                f"Stall-circulation intersection: {len(validation_errors)} stalls overlap circulation"
            )

        print(
            f"[STALL-ATTACH] Validation passed: {len(all_stalls)} stalls attached")

        return StallAttachmentResult(
            circulation=circulation,
            stalls=all_stalls,
            is_valid=True,
            validation_errors=[],
        )

    def _generate_stalls_for_edge(
        self,
        edge: LoopEdge,
        side: int,
        aisle_half: float,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> List[AttachedStall]:
        """
        Generate stalls along one side of an edge with corner clearance.

        Corner clearance prevents stalls from invading turning envelopes.
        Stalls are only placed within the usable segment of the edge.

        Args:
            edge: Circulation edge
            side: +1 for right side (inward), -1 for left side (outward)
            aisle_half: Half of aisle width
            circulation: Circulation loop (for intersection check)
            buildable_polygon: For containment check

        Returns:
            List of stalls for this edge/side
        """
        stalls = []

        # Direction along edge
        dx, dy = edge.direction

        # Normal for this side
        # Edge normal points inward for clockwise
        # side=+1 means inward (same as normal), side=-1 means outward (opposite)
        if side > 0:
            normal = edge.normal
        else:
            normal = (-edge.normal[0], -edge.normal[1])

        # Compute corner clearance for turning envelope
        corner_clearance = self._compute_corner_clearance(
            circulation.aisle_width)

        # Define usable edge segment (excluding corner clearance zones)
        corner_clearance_start = corner_clearance
        corner_clearance_end = corner_clearance

        # Usable length after removing corner clearances
        usable_length = edge.length - corner_clearance_start - corner_clearance_end

        # Check if edge has enough usable length for at least one stall
        if usable_length < self.footprint_width:
            print(
                f"[STALL-ATTACH] Edge {edge.index}: usable length {usable_length:.1f} < stall width {self.footprint_width:.1f}, skipping")
            return []

        # Number of stalls that fit in usable segment
        num_stalls = int(usable_length / self.footprint_width)
        if num_stalls == 0:
            return []

        # Starting offset to center stalls within usable segment
        total_stall_length = num_stalls * self.footprint_width
        start_offset = corner_clearance_start + \
            (usable_length - total_stall_length) / 2

        for i in range(num_stalls):
            stall_id = f"stall-{edge.index}-{side}-{i}"

            # Position along edge (center of stall footprint)
            offset = start_offset + (i + 0.5) * self.footprint_width
            cx = edge.start[0] + offset * dx
            cy = edge.start[1] + offset * dy

            # Anchor point at aisle edge
            anchor_x = cx + aisle_half * normal[0]
            anchor_y = cy + aisle_half * normal[1]
            anchor = (anchor_x, anchor_y)

            # Create stall polygon
            stall_poly = self._create_stall_polygon(
                anchor=anchor,
                normal=normal,
                aisle_dx=dx,
                aisle_dy=dy,
            )

            # Check stall is within buildable polygon
            if not buildable_polygon.contains(stall_poly):
                continue

            # Pre-check stall doesn't intersect circulation (skip if it does)
            if circulation.loop_polygon.intersects(stall_poly):
                intersection = circulation.loop_polygon.intersection(
                    stall_poly)
                if intersection.area > 0.5:  # More than edge touching
                    continue

            stalls.append(AttachedStall(
                id=stall_id,
                edge_index=edge.index,
                anchor=anchor,
                polygon=stall_poly,
                angle=self.angle,
                side=side,
            ))

        return stalls

    def _create_stall_polygon(
        self,
        anchor: Tuple[float, float],
        normal: Tuple[float, float],
        aisle_dx: float,
        aisle_dy: float,
    ) -> ShapelyPolygon:
        """
        Create stall polygon from anchor point with angle-dependent geometry.

        For 90° parking:
            - Rectangle extending perpendicular to aisle
            - Width = 9', Length = 18'

        For angled parking (45°, 60°):
            - Parallelogram with rotated projection
            - Front edge along aisle, stall body extends at angle
            - Spacing along aisle = stall_width / sin(angle)
            - Actual stall is still 9' x 18', just rotated

        Args:
            anchor: Center point where stall meets aisle edge
            normal: Normal vector pointing away from aisle (toward stall body)
            aisle_dx, aisle_dy: Unit vector along aisle direction

        Returns:
            Shapely polygon representing stall footprint
        """
        ax, ay = anchor
        edge_dir = (aisle_dx, aisle_dy)

        if self.angle == 90:
            # 90° parking: simple rectangle
            half_width = STALL_WIDTH / 2
            depth = STALL_LENGTH
            nx, ny = normal

            # Front-left and front-right at anchor (edge of aisle)
            fl = (ax - half_width * aisle_dx, ay - half_width * aisle_dy)
            fr = (ax + half_width * aisle_dx, ay + half_width * aisle_dy)

            # Back-left and back-right extended by depth along normal
            bl = (fl[0] + depth * nx, fl[1] + depth * ny)
            br = (fr[0] + depth * nx, fr[1] + depth * ny)

            return ShapelyPolygon([fl, fr, br, bl])

        else:
            # Angled parking: parallelogram
            # The stall is 9' wide x 18' long, rotated by the parking angle

            # Compute projection vector (direction car body extends)
            proj = compute_projection_vector(self.angle, edge_dir, normal)
            proj_x, proj_y = proj

            # Front edge of stall is along aisle, width = spacing
            half_spacing = self.stall_spacing / 2

            # Front-left and front-right at aisle edge
            fl = (ax - half_spacing * aisle_dx, ay - half_spacing * aisle_dy)
            fr = (ax + half_spacing * aisle_dx, ay + half_spacing * aisle_dy)

            # Stall body extends STALL_LENGTH along projection vector
            bl = (fl[0] + STALL_LENGTH * proj_x, fl[1] + STALL_LENGTH * proj_y)
            br = (fr[0] + STALL_LENGTH * proj_x, fr[1] + STALL_LENGTH * proj_y)

            return ShapelyPolygon([fl, fr, br, bl])

    def _validate_no_intersection(
        self,
        stalls: List[AttachedStall],
        circulation: CirculationLoop,
    ) -> List[str]:
        """
        HARD validation: No stall may intersect circulation polygon.

        Returns list of errors (empty if valid).
        If not empty, layout MUST be aborted.
        """
        errors = []

        for stall in stalls:
            if circulation.loop_polygon.intersects(stall.polygon):
                intersection = circulation.loop_polygon.intersection(
                    stall.polygon)
                area = intersection.area
                if area > 0.5:  # More than edge touching
                    errors.append(
                        f"Stall {stall.id} intersects circulation (area={area:.2f} sq ft)"
                    )

        return errors


# =============================================================================
# CONVENIENCE FUNCTION FOR STALL ATTACHMENT
# =============================================================================

def attach_stalls_to_circulation(
    circulation: CirculationLoop,
    buildable_polygon: ShapelyPolygon,
    angle: int,
    circulation_mode: CirculationMode = CirculationMode.ONE_WAY,
) -> StallAttachmentResult:
    """
    Attach stalls to a frozen circulation loop.

    This is the main entry point for stall attachment.
    Circulation geometry is NOT modified.

    For 45° and 60°:
        Uses AngleAwareParkingBandGenerator to create parking bands
        Stalls are placed along travel vector, not perpendicular to edges
        Bands that intersect circulation or site boundary are discarded entirely

    For 90°:
        Uses StallAttachmentGenerator for direct edge attachment
        Double-loaded for both ONE_WAY and TWO_WAY

    Args:
        circulation: Frozen circulation loop
        buildable_polygon: Buildable area polygon
        angle: Parking angle (90, 60, or 45)
        circulation_mode: Circulation mode (ONE_WAY or TWO_WAY)

    Returns:
        StallAttachmentResult with attached stalls

    Raises:
        V2LayoutError: If any stall intersects circulation or angle/mode incompatible
    """
    if angle in (45, 60):
        # Use band generator for angled parking
        band_generator = AngleAwareParkingBandGenerator(angle=angle)
        bands = band_generator.generate_bands(circulation, buildable_polygon)

        # Collect all stalls from all bands
        all_stalls = []
        for band in bands:
            all_stalls.extend(band.stalls)

        return StallAttachmentResult(
            circulation=circulation,
            stalls=all_stalls,
            is_valid=True,
            validation_errors=[],
        )
    else:
        # Use direct edge attachment for 90°
        generator = StallAttachmentGenerator(
            angle=angle, circulation_mode=circulation_mode)
        return generator.attach_to_loop(circulation, buildable_polygon)
