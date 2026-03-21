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
from shapely.geometry import Point as ShapelyPoint
from shapely.ops import unary_union
from shapely.prepared import prep as shapely_prep
from shapely import STRtree
import networkx as nx


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

        # Step 1: Compute buildable polygon (site minus setbacks)
        buildable = self._compute_buildable_polygon(site_boundary, setbacks)
        if buildable is None or buildable.is_empty:
            raise V2LayoutError("Buildable polygon is empty after setbacks")

        min_x, min_y, max_x, max_y = buildable.bounds
        width = max_x - min_x
        height = max_y - min_y

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
    circulation_mode: CirculationMode = CirculationMode.TWO_WAY,
    parking_angle: int = 90,
) -> CirculationLoop:
    """
    Generate a circulation loop for the given site.

    This is the main entry point for circulation generation.

    V2 ENGINE LOCKED TO 90° PARKING ONLY:
    - Only 90° parking supported
    - 90° ALWAYS uses TWO_WAY circulation
    - Aisle width fixed at 24 ft
    - Double-loaded stalls (both sides)

    Args:
        site_boundary: Site boundary polygon
        setbacks: Setback distances (default: 0 on all sides)
        aisle_width: Override aisle width (default: 24 ft for TWO_WAY)
        circulation_direction: Direction of travel (default: clockwise)
        circulation_mode: Circulation mode (must be TWO_WAY for 90°)
        parking_angle: Parking angle in degrees (must be 90)

    Returns:
        Frozen CirculationLoop

    Raises:
        V2LayoutError: If angle != 90 or mode != TWO_WAY
    """
    if setbacks is None:
        setbacks = Setbacks.uniform(0.0)

    # V2 ENGINE: Only 90° parking supported
    if parking_angle != 90:
        raise V2LayoutError("Only 90° parking supported in this phase")

    # V2 ENGINE: 90° ALWAYS uses TWO_WAY
    if circulation_mode == CirculationMode.ONE_WAY:
        raise V2LayoutError(
            "90° parking requires TWO_WAY circulation mode. "
            "ONE_WAY is not supported in V2."
        )

    # Force TWO_WAY aisle width (24 ft)
    aisle_width = AISLE_WIDTH_TWO_WAY

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
# 90° STALL GEOMETRY CONSTANTS (V2 LOCKED TO 90° ONLY)
# =============================================================================

# V2 ENGINE: Angle-dependent functions DISABLED. 90° constants only.
STALL_SPACING_90 = STALL_WIDTH  # 9.0 ft - spacing between stall anchors
MODULE_DEPTH_90 = STALL_LENGTH  # 18.0 ft - perpendicular projection from aisle

# =============================================================================
# MODULE DEPTH CONSTANTS (V2: MODULE-ONLY STALL GENERATION)
# =============================================================================

# For 90° TWO_WAY parking:
# - Perimeter modules: SINGLE-LOADED (stalls face inward only) = 18 ft
# - Interior modules: DOUBLE-LOADED (aisle + stalls both sides) = 60 ft
#
# Interior modules may ONLY be placed adjacent to explicitly generated
# circulation aisles. Floating interior modules are NOT allowed.

# 18 ft (single-loaded, inward-facing only)
PERIMETER_MODULE_DEPTH = STALL_LENGTH
INTERIOR_MODULE_DEPTH = AISLE_WIDTH_TWO_WAY + 2 * \
    STALL_LENGTH  # 60 ft (aisle + both stall rows)


def compute_stall_spacing(angle: int) -> float:
    """
    DISABLED: V2 engine locked to 90° only.

    Returns 9.0 ft (stall width) for 90° parking.
    Raises V2LayoutError for any other angle.
    """
    if angle != 90:
        raise V2LayoutError("Only 90° parking supported in this phase")
    return STALL_SPACING_90


def compute_module_depth(angle: int, buffer: float = 0.0) -> float:
    """
    DISABLED: V2 engine locked to 90° only.

    Returns 18.0 ft (stall length) for 90° parking.
    Raises V2LayoutError for any other angle.
    """
    if angle != 90:
        raise V2LayoutError("Only 90° parking supported in this phase")
    return MODULE_DEPTH_90 + buffer


def compute_projection_vector(
    angle: int,
    edge_direction: Tuple[float, float],
    normal: Tuple[float, float],
) -> Tuple[float, float]:
    """
    DISABLED: V2 engine locked to 90° only.

    For 90°: returns normal (stall perpendicular to aisle).
    Raises V2LayoutError for any other angle.
    """
    if angle != 90:
        raise V2LayoutError("Only 90° parking supported in this phase")
    return normal


# DISABLED: Angle rotation logic removed for V2 90°-only mode
# Original rotation logic preserved below for future re-enablement:
# rotation_deg = 90 - angle  # 30° for 60° parking, 45° for 45° parking
# rotation_rad = math.radians(rotation_deg)
# nx, ny = normal
# dx, dy = edge_direction

# DISABLED: Rotation direction logic removed for V2 90°-only mode
# Preserved for future re-enablement:
#     cross = dx * ny - dy * nx
#     if cross > 0:
#         cos_r = math.cos(rotation_rad)
#         sin_r = math.sin(rotation_rad)
#     else:
#         cos_r = math.cos(-rotation_rad)
#         sin_r = math.sin(-rotation_rad)
#     proj_x = nx * cos_r - ny * sin_r
#     proj_y = nx * sin_r + ny * cos_r
#     return (proj_x, proj_y)


# =============================================================================
# PARKING BAND — DISABLED IN V2 (90° only, no angled parking)
# =============================================================================

# V2 ENGINE: ParkingBand class preserved but NOT USED.
# 90° parking uses direct edge attachment only.

@dataclass(frozen=True)
class ParkingBand:
    """
    DISABLED: V2 engine locked to 90° only.

    A parallelogram-shaped parking band for angled parking (45°/60°).
    This class is preserved for future re-enablement but is not used in V2.
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
# ANGLE-AWARE PARKING BAND GENERATOR — DISABLED IN V2 (90° only)
# =============================================================================

class AngleAwareParkingBandGenerator:
    """
    DISABLED: V2 engine locked to 90° only.

    This class is preserved for future re-enablement but raises V2LayoutError
    if instantiated. 90° parking uses StallAttachmentGenerator instead.
    """

    def __init__(self, angle: int):
        """
        DISABLED: V2 engine locked to 90° only.

        Raises V2LayoutError for any angle.
        """
        raise V2LayoutError(
            "Only 90° parking supported in this phase. "
            "AngleAwareParkingBandGenerator is disabled."
        )

    # NOTE: All band generation methods removed for V2 90°-only mode.
    # Class preserved as stub for future re-enablement of angled parking.


# =============================================================================
# CIRCULATION SPINE — Interior aisle connecting to perimeter loop
# =============================================================================

@dataclass
class CirculationSpine:
    """
    An interior circulation aisle that connects to the perimeter loop.

    SPINE RULES:
    - Must be parallel to the longest site edge
    - Must be offset inward by INTERIOR_MODULE_DEPTH (60 ft) from the perimeter loop
    - Must connect to the perimeter loop at BOTH ends
    - If spine cannot connect or overlaps circulation, throw V2LayoutError

    The spine is a straight aisle segment with:
    - Width = AISLE_WIDTH_TWO_WAY (24 ft)
    - One double-loaded parking module attached (60 ft deep total)

    Attributes:
        spine_id: Unique identifier
        aisle_polygon: Shapely polygon for the aisle
        centerline: Centerline tuple ((x1,y1), (x2,y2))
        connection_points: Two points where spine connects to perimeter
        parent_edge_index: Index of the perimeter edge this spine is parallel to
    """
    spine_id: str
    aisle_polygon: ShapelyPolygon
    centerline: Tuple[Tuple[float, float], Tuple[float, float]]
    connection_points: Tuple[Tuple[float, float], Tuple[float, float]]
    parent_edge_index: int

    @property
    def length(self) -> float:
        p1, p2 = self.centerline
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

    def to_dict(self) -> dict:
        aisle_coords = list(self.aisle_polygon.exterior.coords)
        return {
            "spine_id": self.spine_id,
            "length": self.length,
            "parent_edge_index": self.parent_edge_index,
            "aisle_polygon": [{"x": c[0], "y": c[1]} for c in aisle_coords[:-1]],
            "centerline": {
                "start": {"x": self.centerline[0][0], "y": self.centerline[0][1]},
                "end": {"x": self.centerline[1][0], "y": self.centerline[1][1]},
            },
            "connection_points": [
                {"x": self.connection_points[0][0],
                    "y": self.connection_points[0][1]},
                {"x": self.connection_points[1][0],
                    "y": self.connection_points[1][1]},
            ],
        }


@dataclass
class SpineGenerationResult:
    """
    Result of generating an interior circulation spine.

    Attributes:
        spine: The generated spine (or None if not feasible)
        module: The double-loaded parking module attached to the spine
        is_valid: True if spine was successfully generated
        validation_errors: List of errors if generation failed
    """
    spine: Optional[CirculationSpine]
    module: Optional["ParkingModule"]
    is_valid: bool
    validation_errors: List[str] = field(default_factory=list)

    @property
    def stall_count(self) -> int:
        return self.module.stall_count if self.module else 0

    def get_all_stalls(self) -> List["AttachedStall"]:
        return self.module.stalls if self.module else []


@dataclass
class MultipleAislesResult:
    """
    Result of generating multiple interior drive aisles.

    For 90° parking, multiple parallel aisles are placed at INTERIOR_MODULE_DEPTH
    (60 ft) intervals, each serving stalls on both sides.

    Attributes:
        spines: List of generated interior aisles
        modules: List of parking modules (one per aisle)
        total_stalls: Total stall count across all modules
        is_valid: True if all aisles are valid and connected
        circulation_connected: True if all aisles connect to outer loop
        validation_errors: List of errors if generation failed
    """
    spines: List[CirculationSpine] = field(default_factory=list)
    modules: List["ParkingModule"] = field(default_factory=list)
    total_stalls: int = 0
    is_valid: bool = False
    circulation_connected: bool = False
    validation_errors: List[str] = field(default_factory=list)

    @property
    def aisle_count(self) -> int:
        return len(self.spines)

    def get_all_stalls(self) -> List["AttachedStall"]:
        all_stalls = []
        for module in self.modules:
            all_stalls.extend(module.stalls)
        return all_stalls


# =============================================================================
# PARKING MODULE — Reserved rectangular volume for aisle + stalls
# =============================================================================

@dataclass
class ParkingModule:
    """
    A reserved rectangular volume for parking stalls.

    MODULE-ONLY STALL GENERATION:
    - Stalls are NEVER generated directly - only through modules
    - Modules must be ADJACENT to circulation edges
    - Interior modules require EXPLICIT circulation aisle connection
    - If any module overlaps another module or circulation, throw V2LayoutError

    For 90° TWO_WAY parking:
    - Perimeter modules: 18 ft deep (single-loaded, inward-facing stalls only)
    - Interior modules: 60 ft deep (aisle 24 ft + stalls 18 ft each side)

    Interior modules may ONLY be placed if a connecting circulation aisle
    is explicitly generated. Floating interior modules are NOT allowed.

    Attributes:
        module_id: Unique identifier for this module
        edge_index: Index of circulation edge this module attaches to (-1 for interior)
        side: +1 for RIGHT/INWARD, -1 for LEFT/OUTWARD (0 for double-loaded interior)
        envelope: Reserved footprint polygon (stall zone only, NOT including shared aisle)
        aisle_polygon: Reference to the aisle this module is adjacent to
        stall_zone: The stall area (same as envelope for perimeter modules)
        aisle_centerline: Centerline of the adjacent aisle segment
        level: 0 for perimeter, 1+ for interior (requires explicit circulation)
        stalls: List of stalls (generated AFTER module placement)
    """
    module_id: str
    edge_index: int
    side: int
    envelope: ShapelyPolygon
    aisle_polygon: ShapelyPolygon
    stall_zone: ShapelyPolygon
    aisle_centerline: Tuple[Tuple[float, float], Tuple[float, float]]
    level: int = 0
    stalls: List["AttachedStall"] = field(default_factory=list)

    @property
    def stall_count(self) -> int:
        return len(self.stalls)

    @property
    def has_stalls(self) -> bool:
        return len(self.stalls) > 0

    def to_dict(self) -> dict:
        envelope_coords = list(self.envelope.exterior.coords)
        aisle_coords = list(self.aisle_polygon.exterior.coords)
        return {
            "module_id": self.module_id,
            "edge_index": self.edge_index,
            "side": self.side,
            "level": self.level,
            "stall_count": self.stall_count,
            "envelope": [{"x": c[0], "y": c[1]} for c in envelope_coords[:-1]],
            "aisle_polygon": [{"x": c[0], "y": c[1]} for c in aisle_coords[:-1]],
            "aisle_centerline": {
                "start": {"x": self.aisle_centerline[0][0], "y": self.aisle_centerline[0][1]},
                "end": {"x": self.aisle_centerline[1][0], "y": self.aisle_centerline[1][1]},
            },
        }


# =============================================================================
# MODULE PLACEMENT RESULT
# =============================================================================

@dataclass
class ModulePlacementResult:
    """
    Result of placing parking modules.

    Modules are placed FIRST. Stalls are generated AFTER all modules are placed.

    Attributes:
        circulation: The frozen circulation loop
        modules: List of placed parking modules
        total_stall_count: Total stalls across all modules
        is_valid: True if all modules are valid and non-overlapping
        validation_errors: List of validation errors
    """
    circulation: CirculationLoop
    modules: List[ParkingModule]
    total_stall_count: int
    is_valid: bool
    validation_errors: List[str] = field(default_factory=list)

    def get_all_stalls(self) -> List["AttachedStall"]:
        """Get all stalls from all modules."""
        all_stalls = []
        for module in self.modules:
            all_stalls.extend(module.stalls)
        return all_stalls

    def get_all_envelopes(self) -> List[ShapelyPolygon]:
        """Get all module envelopes for overlap checking."""
        return [m.envelope for m in self.modules]

    def to_dict(self) -> dict:
        return {
            "module_count": len(self.modules),
            "total_stall_count": self.total_stall_count,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
            "modules": [m.to_dict() for m in self.modules],
        }


# =============================================================================
# ATTACHED STALL — Stall inside a parking module
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
# PARKING MODULE GENERATOR — STRICT MODULE-ONLY STALL GENERATION
# =============================================================================

class ParkingModuleGenerator:
    """
    Generates parking modules for frozen circulation edges.

    STRICT MODULE-ONLY APPROACH:
    - Stalls are NEVER generated directly - only through modules
    - Modules must be ADJACENT to frozen circulation edges
    - Interior modules require EXPLICIT circulation aisle extension
    - If any module overlaps another module or circulation, throw V2LayoutError
    - Stalls are ONLY counted if they belong to a valid module

    WORKFLOW:
    1. Circulation is generated FIRST and FROZEN
    2. For each circulation edge, attempt to place a perimeter module (INWARD only)
    3. Validate no overlap between modules or with circulation
    4. Only after ALL modules are placed, generate stalls inside each module
    5. Interior modules require explicit circulation aisle generation (NOT implemented yet)

    For 90° TWO_WAY:
    - Perimeter module depth: 18 ft (single-loaded, inward-facing stalls)
    - Interior module depth: 60 ft (aisle 24 ft + stalls 18 ft each side)
    - Outward-facing modules are REJECTED (would extend outside site boundary)

    Usage:
        generator = ParkingModuleGenerator(angle=90, circulation_mode=CirculationMode.TWO_WAY)
        result = generator.place_modules(circulation_loop, buildable_polygon)
    """

    def __init__(self, angle: int, circulation_mode: CirculationMode = CirculationMode.TWO_WAY):
        """
        Initialize parking module generator.

        Args:
            angle: Parking angle (must be 90)
            circulation_mode: Circulation mode (must be TWO_WAY)
        """
        if angle != 90:
            raise V2LayoutError("Only 90° parking supported in this phase")

        if circulation_mode == CirculationMode.ONE_WAY:
            raise V2LayoutError(
                "90° parking requires TWO_WAY circulation mode. "
                "ONE_WAY is not supported in V2."
            )

        self.angle = 90
        self.circulation_mode = CirculationMode.TWO_WAY
        self.is_double_loaded = True
        self.stall_spacing = STALL_SPACING_90  # 9.0 ft
        self.stall_depth = MODULE_DEPTH_90     # 18.0 ft

    def _compute_corner_clearance(self, aisle_width: float) -> float:
        """Compute corner clearance to prevent module overlaps at corners."""
        aisle_half = aisle_width / 2
        return aisle_half + STALL_LENGTH  # 30 ft for 24 ft aisle

    def _create_module_envelope(
        self,
        edge: LoopEdge,
        side: int,
        aisle_half: float,
        corner_clearance: float,
    ) -> Optional[Tuple[ShapelyPolygon, ShapelyPolygon, ShapelyPolygon, Tuple]]:
        """
        Create the reserved envelope for a parking module.

        The envelope is the STALL ZONE only (not including the aisle).
        The aisle is shared circulation, not reserved by modules.

        Returns tuple of (envelope, aisle_polygon, stall_zone, centerline) or None if invalid.
        """
        dx, dy = edge.direction

        # Normal for this side
        if side > 0:
            normal = (-edge.normal[0], -edge.normal[1])  # INWARD
        else:
            normal = edge.normal  # OUTWARD

        # Usable edge segment (excluding corner clearance zones)
        usable_length = edge.length - 2 * corner_clearance
        if usable_length < self.stall_spacing:
            return None

        # Module envelope dimensions
        # Along edge: from corner_clearance to edge_length - corner_clearance
        start_offset = corner_clearance
        end_offset = edge.length - corner_clearance

        # Start and end points along edge centerline
        p1_x = edge.start[0] + start_offset * dx
        p1_y = edge.start[1] + start_offset * dy
        p2_x = edge.start[0] + end_offset * dx
        p2_y = edge.start[1] + end_offset * dy

        # Aisle edge (at centerline + aisle_half in normal direction)
        # This is where stalls attach
        aisle_edge_start = (p1_x + aisle_half *
                            normal[0], p1_y + aisle_half * normal[1])
        aisle_edge_end = (p2_x + aisle_half *
                          normal[0], p2_y + aisle_half * normal[1])

        # Stall back (aisle edge + stall depth in normal direction)
        stall_back_start = (aisle_edge_start[0] + self.stall_depth * normal[0],
                            aisle_edge_start[1] + self.stall_depth * normal[1])
        stall_back_end = (aisle_edge_end[0] + self.stall_depth * normal[0],
                          aisle_edge_end[1] + self.stall_depth * normal[1])

        # Module envelope = STALL ZONE ONLY (from aisle edge to stall back)
        # This does NOT include the aisle, so it won't overlap with circulation
        envelope = ShapelyPolygon([
            aisle_edge_start, aisle_edge_end, stall_back_end, stall_back_start
        ])

        # Aisle polygon (centerline to aisle edge) - for reference, not part of module
        aisle_polygon = ShapelyPolygon([
            (p1_x, p1_y), (p2_x, p2_y), aisle_edge_end, aisle_edge_start
        ])

        # Stall zone = envelope (same thing for perimeter modules)
        stall_zone = envelope

        # Centerline from edge segment
        centerline = ((p1_x, p1_y), (p2_x, p2_y))

        return envelope, aisle_polygon, stall_zone, centerline

    def _validate_module_placement(
        self,
        module: ParkingModule,
        circulation: CirculationLoop,
        placed_modules: List[ParkingModule],
    ) -> List[str]:
        """
        Validate that a module doesn't overlap circulation or other modules.

        Returns list of errors (empty if valid).
        """
        errors = []

        # Check 1: Module envelope must not intersect circulation polygon
        if circulation.loop_polygon.intersects(module.envelope):
            intersection = circulation.loop_polygon.intersection(
                module.envelope)
            if intersection.area > 0.5:
                errors.append(
                    f"Module {module.module_id} overlaps circulation (area={intersection.area:.2f} sq ft)"
                )

        # Check 2: Module envelope must not intersect other placed modules
        for other in placed_modules:
            if module.envelope.intersects(other.envelope):
                intersection = module.envelope.intersection(other.envelope)
                if intersection.area > 0.5:
                    errors.append(
                        f"Module {module.module_id} overlaps module {other.module_id} (area={intersection.area:.2f} sq ft)"
                    )

        return errors

    def _generate_stalls_in_module(
        self,
        module: ParkingModule,
        buildable_polygon: ShapelyPolygon,
    ) -> List[AttachedStall]:
        """
        Generate stalls inside a module's stall zone.

        Called ONLY after all modules are placed and validated.
        """
        stalls = []

        # Get module parameters
        centerline = module.aisle_centerline
        p1, p2 = centerline

        # Edge direction
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        edge_length = math.sqrt(dx * dx + dy * dy)

        if edge_length < self.stall_spacing:
            return []

        dx /= edge_length
        dy /= edge_length

        # Normal for this side
        if module.side > 0:
            normal = (-dy, dx)  # Perpendicular, flipped for inward
        elif module.side < 0:
            normal = (dy, -dx)  # Perpendicular, for outward
        else:
            # Interior module - determine from envelope geometry
            # Use the stall zone centroid relative to aisle
            aisle_center = module.aisle_polygon.centroid
            stall_center = module.stall_zone.centroid
            nx = stall_center.x - aisle_center.x
            ny = stall_center.y - aisle_center.y
            n_len = math.sqrt(nx*nx + ny*ny)
            if n_len > 0:
                normal = (nx/n_len, ny/n_len)
            else:
                normal = (0, 1)

        # Number of stalls that fit
        num_stalls = int(edge_length / self.stall_spacing)
        if num_stalls == 0:
            return []

        # Center stalls along module
        total_stall_width = num_stalls * self.stall_spacing
        start_offset = (edge_length - total_stall_width) / 2
        aisle_half = AISLE_WIDTH_TWO_WAY / 2

        for i in range(num_stalls):
            stall_id = f"stall-{module.module_id}-{i}"

            # Position along centerline
            offset = start_offset + (i + 0.5) * self.stall_spacing
            cx = p1[0] + offset * dx
            cy = p1[1] + offset * dy

            # Anchor at aisle edge
            anchor_x = cx + aisle_half * normal[0]
            anchor_y = cy + aisle_half * normal[1]
            anchor = (anchor_x, anchor_y)

            # Create stall polygon
            half_width = STALL_WIDTH / 2
            depth = STALL_LENGTH

            fl = (anchor_x - half_width * dx, anchor_y - half_width * dy)
            fr = (anchor_x + half_width * dx, anchor_y + half_width * dy)
            bl = (fl[0] + depth * normal[0], fl[1] + depth * normal[1])
            br = (fr[0] + depth * normal[0], fr[1] + depth * normal[1])

            stall_poly = ShapelyPolygon([fl, fr, br, bl])

            # Check stall is within buildable polygon
            if not buildable_polygon.contains(stall_poly):
                continue

            stalls.append(AttachedStall(
                id=stall_id,
                edge_index=module.edge_index,
                anchor=anchor,
                polygon=stall_poly,
                angle=self.angle,
                side=module.side,
            ))

        return stalls

    def place_modules(
        self,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> ModulePlacementResult:
        """
        Place parking modules along circulation edges.

        MODULE-FIRST APPROACH:
        1. Create module envelope for each edge/side
        2. Validate no overlaps with circulation or other modules
        3. THROW V2LayoutError if any overlap occurs
        4. Generate stalls inside each module ONLY after all modules placed

        Args:
            circulation: Frozen circulation loop
            buildable_polygon: Buildable area polygon

        Returns:
            ModulePlacementResult with placed modules and stalls

        Raises:
            V2LayoutError: If any module overlaps circulation or another module
        """
        corner_clearance = self._compute_corner_clearance(
            circulation.aisle_width)
        aisle_half = circulation.aisle_width / 2

        # PHASE 1: Create and validate module envelopes
        placed_modules: List[ParkingModule] = []
        all_validation_errors: List[str] = []

        for edge in circulation.loop_edges:
            sides = [+1, -1] if self.is_double_loaded else [-1]

            for side in sides:
                module_id = f"edge{edge.index}-{'IN' if side > 0 else 'OUT'}"

                # Create module envelope
                result = self._create_module_envelope(
                    edge=edge,
                    side=side,
                    aisle_half=aisle_half,
                    corner_clearance=corner_clearance,
                )

                if result is None:
                    continue

                envelope, aisle_polygon, stall_zone, centerline = result

                # Check envelope is within buildable area
                if not buildable_polygon.contains(envelope):
                    # Try intersection
                    clipped = envelope.intersection(buildable_polygon)
                    if clipped.is_empty or clipped.area < envelope.area * 0.5:
                        continue
                    envelope = clipped

                module = ParkingModule(
                    module_id=module_id,
                    edge_index=edge.index,
                    side=side,
                    envelope=envelope,
                    aisle_polygon=aisle_polygon,
                    stall_zone=stall_zone,
                    aisle_centerline=centerline,
                    level=0,
                    stalls=[],
                )

                # Validate no overlap with circulation or other modules
                errors = self._validate_module_placement(
                    module, circulation, placed_modules)

                if errors:
                    all_validation_errors.extend(errors)
                    # HARD FAIL on overlap
                    raise V2LayoutError(
                        f"Module overlap detected: {'; '.join(errors)}"
                    )

                placed_modules.append(module)

        # PHASE 2: Generate stalls inside each module
        total_stalls = 0

        for module in placed_modules:
            stalls = self._generate_stalls_in_module(module, buildable_polygon)
            # Update module with stalls (modules are mutable for stall assignment)
            module.stalls.extend(stalls)
            total_stalls += len(stalls)

        return ModulePlacementResult(
            circulation=circulation,
            modules=placed_modules,
            total_stall_count=total_stalls,
            is_valid=True,
            validation_errors=[],
        )


# =============================================================================
# STALL ATTACHMENT GENERATOR — Legacy wrapper using module-first approach
# =============================================================================

class StallAttachmentGenerator:
    """
    Legacy interface for stall attachment.

    DEPRECATED: Use ParkingModuleGenerator directly.

    This class now delegates to ParkingModuleGenerator for module-first placement.
    Maintains backward compatibility with existing code.
    """

    def __init__(self, angle: int, circulation_mode: CirculationMode = CirculationMode.TWO_WAY):
        if angle != 90:
            raise V2LayoutError("Only 90° parking supported in this phase")
        if circulation_mode == CirculationMode.ONE_WAY:
            raise V2LayoutError(
                "90° parking requires TWO_WAY circulation mode.")

        self.angle = 90
        self.circulation_mode = CirculationMode.TWO_WAY
        self.is_double_loaded = True
        self._module_generator = ParkingModuleGenerator(
            angle=90, circulation_mode=circulation_mode)

    def attach_to_loop(
        self,
        circulation: CirculationLoop,
        buildable_polygon: ShapelyPolygon,
    ) -> StallAttachmentResult:
        """
        Attach stalls using module-first approach.

        Delegates to ParkingModuleGenerator and converts result to StallAttachmentResult.
        """
        # Use module-first approach
        module_result = self._module_generator.place_modules(
            circulation, buildable_polygon)

        # Convert to legacy StallAttachmentResult
        all_stalls = module_result.get_all_stalls()

        return StallAttachmentResult(
            circulation=circulation,
            stalls=all_stalls,
            is_valid=module_result.is_valid,
            validation_errors=module_result.validation_errors,
        )


# =============================================================================
# CONVENIENCE FUNCTION FOR STALL ATTACHMENT
# =============================================================================

def attach_stalls_to_circulation(
    circulation: CirculationLoop,
    buildable_polygon: ShapelyPolygon,
    angle: int,
    circulation_mode: CirculationMode = CirculationMode.TWO_WAY,
) -> StallAttachmentResult:
    """
    Attach stalls to a frozen circulation loop.

    V2 ENGINE LOCKED TO 90° ONLY:
    - Only 90° parking supported
    - TWO_WAY circulation required
    - Double-loaded stalls (both sides)
    - Direct edge attachment with axis-aligned rectangles

    Args:
        circulation: Frozen circulation loop
        buildable_polygon: Buildable area polygon
        angle: Parking angle (must be 90)
        circulation_mode: Circulation mode (must be TWO_WAY)

    Returns:
        StallAttachmentResult with attached stalls

    Raises:
        V2LayoutError: If angle != 90 or mode != TWO_WAY
    """
    # V2 ENGINE: Only 90° parking supported
    if angle != 90:
        raise V2LayoutError("Only 90° parking supported in this phase")

    # V2 ENGINE: 90° ALWAYS uses TWO_WAY
    if circulation_mode == CirculationMode.ONE_WAY:
        raise V2LayoutError(
            "90° parking requires TWO_WAY circulation mode. "
            "ONE_WAY is not supported in V2."
        )

    # Use direct edge attachment for 90°
    generator = StallAttachmentGenerator(
        angle=90, circulation_mode=CirculationMode.TWO_WAY)
    return generator.attach_to_loop(circulation, buildable_polygon)


# =============================================================================
# INTERIOR CIRCULATION SPINE GENERATOR
# =============================================================================

def generate_interior_spine(
    circulation: CirculationLoop,
    buildable_polygon: ShapelyPolygon,
) -> SpineGenerationResult:
    """
    Generate an interior circulation spine for additional parking modules.

    SPINE GENERATION RULES:
    1. Spine is parallel to the LONGEST perimeter loop edge
    2. Spine is offset INWARD by INTERIOR_MODULE_DEPTH (60 ft)
    3. Spine connects to perimeter loop at BOTH ends
    4. If spine cannot connect or overlaps circulation, throw V2LayoutError
    5. Exactly ONE double-loaded module is attached to the spine

    The spine provides circulation access to an interior parking module.
    Without this explicit circulation connection, interior modules are NOT allowed.

    Args:
        circulation: The frozen perimeter circulation loop
        buildable_polygon: Buildable area polygon

    Returns:
        SpineGenerationResult with spine and attached module

    Raises:
        V2LayoutError: If spine cannot be generated or overlaps circulation
    """

    # Step 1: Find the longest edge of the perimeter loop
    edges = circulation.loop_edges
    longest_edge = max(edges, key=lambda e: e.length)

    # Step 2: Check if there's enough space for a spine + module
    # Spine needs: 60 ft inset from perimeter edge + 24 ft aisle
    # The spine sits INTERIOR_MODULE_DEPTH (60 ft) inward from the perimeter aisle centerline
    min_required_depth = INTERIOR_MODULE_DEPTH + AISLE_WIDTH_TWO_WAY

    # Get perpendicular distance from longest edge to opposite edge
    dx, dy = longest_edge.direction
    normal = longest_edge.normal  # Points inward

    # Find the interior bounds
    loop_bounds = circulation.loop_polygon.bounds
    min_x, min_y, max_x, max_y = loop_bounds

    # Calculate available interior depth perpendicular to longest edge
    # For horizontal edges (dy ≈ 0), depth is in Y direction
    # For vertical edges (dx ≈ 0), depth is in X direction
    if abs(dx) > abs(dy):
        # Horizontal edge - depth is Y dimension of interior
        interior_height = max_y - min_y - 2 * (AISLE_WIDTH_TWO_WAY / 2)
        available_depth = interior_height
    else:
        # Vertical edge - depth is X dimension of interior
        interior_width = max_x - min_x - 2 * (AISLE_WIDTH_TWO_WAY / 2)
        available_depth = interior_width

    if available_depth < min_required_depth:
        return SpineGenerationResult(
            spine=None,
            module=None,
            is_valid=False,
            validation_errors=[
                f"Insufficient interior depth: {available_depth:.1f} ft < {min_required_depth:.1f} ft required"],
        )

    # Step 3: Compute spine centerline parallel to longest edge
    # Offset inward by INTERIOR_MODULE_DEPTH (60 ft) from the perimeter aisle centerline
    # NOTE: The edge.normal points OUTWARD from the loop, so we NEGATE it to go inward.
    spine_offset = INTERIOR_MODULE_DEPTH  # 60 ft as specified

    # Get perimeter edge centerline start/end
    edge_start = longest_edge.start
    edge_end = longest_edge.end

    # INWARD direction is OPPOSITE of edge normal (normal points outward)
    nx, ny = -normal[0], -normal[1]

    # Offset the edge centerline inward by spine_offset
    spine_start = (
        edge_start[0] + spine_offset * nx,
        edge_start[1] + spine_offset * ny,
    )
    spine_end = (
        edge_end[0] + spine_offset * nx,
        edge_end[1] + spine_offset * ny,
    )

    # Step 4: Trim spine to fit within interior (leave room for connections)
    # The spine must connect to perpendicular perimeter edges at both ends
    # We need to find where the spine intersects the perimeter loop interior

    # Get inner boundary of circulation loop
    if not circulation.loop_polygon.interiors:
        return SpineGenerationResult(
            spine=None,
            module=None,
            is_valid=False,
            validation_errors=["Perimeter loop has no interior boundary"],
        )

    inner_ring = ShapelyPolygon(circulation.loop_polygon.interiors[0])

    # Create a line extending through the spine
    spine_line = LineString([spine_start, spine_end])

    # Check if spine is within the interior
    if not inner_ring.contains(spine_line):
        # Clip spine to interior
        clipped = spine_line.intersection(inner_ring)
        if clipped.is_empty:
            return SpineGenerationResult(
                spine=None,
                module=None,
                is_valid=False,
                validation_errors=["Spine does not fit within interior"],
            )
        if clipped.geom_type == 'LineString':
            coords = list(clipped.coords)
            if len(coords) >= 2:
                spine_start = coords[0]
                spine_end = coords[-1]
        else:
            return SpineGenerationResult(
                spine=None,
                module=None,
                is_valid=False,
                validation_errors=["Spine intersection is not a line"],
            )

    # Step 5: Validate spine length is sufficient for at least one module
    spine_length = math.sqrt(
        (spine_end[0] - spine_start[0])**2 +
        (spine_end[1] - spine_start[1])**2
    )
    min_spine_length = STALL_WIDTH * 2  # At least 2 stalls (18 ft)

    if spine_length < min_spine_length:
        return SpineGenerationResult(
            spine=None,
            module=None,
            is_valid=False,
            validation_errors=[
                f"Spine too short: {spine_length:.1f} ft < {min_spine_length:.1f} ft minimum"],
        )

    # Step 6: Create spine aisle polygon
    aisle_half = AISLE_WIDTH_TWO_WAY / 2

    # Spine direction
    sdx = spine_end[0] - spine_start[0]
    sdy = spine_end[1] - spine_start[1]
    slen = math.sqrt(sdx*sdx + sdy*sdy)
    sdx /= slen
    sdy /= slen

    # Perpendicular to spine (for aisle width)
    snx, sny = -sdy, sdx

    # Four corners of spine aisle polygon
    p1 = (spine_start[0] - aisle_half * snx, spine_start[1] - aisle_half * sny)
    p2 = (spine_start[0] + aisle_half * snx, spine_start[1] + aisle_half * sny)
    p3 = (spine_end[0] + aisle_half * snx, spine_end[1] + aisle_half * sny)
    p4 = (spine_end[0] - aisle_half * snx, spine_end[1] - aisle_half * sny)

    spine_aisle_polygon = ShapelyPolygon([p1, p2, p3, p4])

    # Step 7: Validate spine doesn't overlap with perimeter circulation
    if circulation.loop_polygon.intersects(spine_aisle_polygon):
        intersection = circulation.loop_polygon.intersection(
            spine_aisle_polygon)
        if intersection.area > 1.0:  # Allow small tolerance
            raise V2LayoutError(
                f"Interior spine overlaps perimeter circulation (overlap area: {intersection.area:.1f} sq ft)"
            )

    # Step 8: Find connection points to perimeter loop
    # The spine should connect at both ends to the perimeter loop inner edge
    conn1 = spine_start
    conn2 = spine_end

    # Step 9: Create CirculationSpine object
    spine = CirculationSpine(
        spine_id="interior-spine-0",
        aisle_polygon=spine_aisle_polygon,
        centerline=(spine_start, spine_end),
        connection_points=(conn1, conn2),
        parent_edge_index=longest_edge.index,
    )

    # Step 10: Generate exactly ONE double-loaded parking module attached to spine
    module = _generate_double_loaded_module_on_spine(
        spine=spine,
        buildable_polygon=buildable_polygon,
        circulation=circulation,
    )

    if module is None:
        return SpineGenerationResult(
            spine=spine,
            module=None,
            is_valid=False,
            validation_errors=["Failed to attach module to spine"],
        )

    return SpineGenerationResult(
        spine=spine,
        module=module,
        is_valid=True,
        validation_errors=[],
    )


def _generate_double_loaded_module_on_spine(
    spine: CirculationSpine,
    buildable_polygon: ShapelyPolygon,
    circulation: CirculationLoop,
) -> Optional[ParkingModule]:
    """
    Generate exactly one double-loaded parking module on the interior spine.

    The module includes stalls on BOTH sides of the spine aisle.
    Total module depth: 60 ft (aisle 24 ft + stalls 18 ft each side)

    Args:
        spine: The interior circulation spine
        buildable_polygon: Buildable area polygon
        circulation: Perimeter circulation loop

    Returns:
        ParkingModule with stalls, or None if generation fails
    """

    # Get spine parameters
    p1, p2 = spine.centerline
    spine_length = spine.length

    # Spine direction
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    slen = math.sqrt(dx*dx + dy*dy)
    dx /= slen
    dy /= slen

    # Perpendicular to spine
    nx, ny = -dy, dx

    # Stall dimensions
    stall_width = STALL_WIDTH  # 9 ft
    stall_depth = STALL_LENGTH  # 18 ft
    aisle_half = AISLE_WIDTH_TWO_WAY / 2  # 12 ft

    # Calculate how many stalls fit along spine length
    num_stalls_per_side = int(spine_length / stall_width)
    if num_stalls_per_side < 1:
        return None

    # Module envelope = stall zones on both sides (NOT including aisle)
    # Side 1: aisle_half to aisle_half + stall_depth
    # Side 2: -aisle_half - stall_depth to -aisle_half

    env_p1 = (p1[0] + aisle_half * nx, p1[1] + aisle_half * ny)
    env_p2 = (p2[0] + aisle_half * nx, p2[1] + aisle_half * ny)
    env_p3 = (p2[0] + (aisle_half + stall_depth) * nx,
              p2[1] + (aisle_half + stall_depth) * ny)
    env_p4 = (p1[0] + (aisle_half + stall_depth) * nx,
              p1[1] + (aisle_half + stall_depth) * ny)
    stall_zone_side1 = ShapelyPolygon([env_p1, env_p2, env_p3, env_p4])

    env_p5 = (p1[0] - aisle_half * nx, p1[1] - aisle_half * ny)
    env_p6 = (p2[0] - aisle_half * nx, p2[1] - aisle_half * ny)
    env_p7 = (p2[0] - (aisle_half + stall_depth) * nx,
              p2[1] - (aisle_half + stall_depth) * ny)
    env_p8 = (p1[0] - (aisle_half + stall_depth) * nx,
              p1[1] - (aisle_half + stall_depth) * ny)
    stall_zone_side2 = ShapelyPolygon([env_p5, env_p6, env_p7, env_p8])

    # Combined envelope (both stall zones)
    envelope = unary_union([stall_zone_side1, stall_zone_side2])

    # Validate envelope doesn't overlap perimeter circulation
    if circulation.loop_polygon.intersects(envelope):
        intersection = circulation.loop_polygon.intersection(envelope)
        if intersection.area > 1.0:
            raise V2LayoutError(
                f"Spine module overlaps perimeter circulation (area: {intersection.area:.1f} sq ft)"
            )

    # Generate stalls on both sides
    stalls = []
    stall_id = 0

    for side in [1, -1]:  # +1 for one side, -1 for other side
        normal_dir = (side * nx, side * ny)

        for i in range(num_stalls_per_side):
            # Stall center along spine
            offset = (i + 0.5) * stall_width
            cx = p1[0] + offset * dx
            cy = p1[1] + offset * dy

            # Stall anchor at aisle edge
            anchor_x = cx + aisle_half * normal_dir[0]
            anchor_y = cy + aisle_half * normal_dir[1]

            # Stall polygon corners
            half_w = stall_width / 2
            fl = (cx - half_w * dx + aisle_half * normal_dir[0],
                  cy - half_w * dy + aisle_half * normal_dir[1])
            fr = (cx + half_w * dx + aisle_half * normal_dir[0],
                  cy + half_w * dy + aisle_half * normal_dir[1])
            bl = (fl[0] + stall_depth * normal_dir[0],
                  fl[1] + stall_depth * normal_dir[1])
            br = (fr[0] + stall_depth * normal_dir[0],
                  fr[1] + stall_depth * normal_dir[1])

            stall_poly = ShapelyPolygon([fl, fr, br, bl])

            # Validate stall is within buildable area
            if not buildable_polygon.contains(stall_poly):
                continue  # Skip stalls outside boundary

            stall_id += 1
            stalls.append(AttachedStall(
                id=f"spine-stall-{stall_id}",
                edge_index=-1,  # Interior stalls
                anchor=(anchor_x, anchor_y),
                polygon=stall_poly,
                angle=90,
                side=side,
            ))

    if len(stalls) == 0:
        return None

    # Create the module
    module = ParkingModule(
        module_id="spine-module-0",
        edge_index=-1,  # Interior module
        side=0,  # Double-loaded (both sides)
        envelope=envelope if envelope.geom_type == 'Polygon' else envelope.convex_hull,
        aisle_polygon=spine.aisle_polygon,
        stall_zone=envelope if envelope.geom_type == 'Polygon' else envelope.convex_hull,
        aisle_centerline=spine.centerline,
        level=1,  # Interior level
        stalls=stalls,
    )

    return module
# INTERIOR DENSIFICATION — SINGLE CENTRAL SPINE
# =============================================================================


# Interior module dimensions for 90° double-loaded parking
# Module = aisle (24 ft) + stalls on both sides (18 ft each) = 60 ft total
DOUBLE_LOADED_MODULE_DEPTH = AISLE_WIDTH_TWO_WAY + 2 * STALL_LENGTH  # 60.0 ft
INTERIOR_AISLE_WIDTH = AISLE_WIDTH_TWO_WAY  # 24 ft


@dataclass
class InteriorModule:
    """
    An interior double-loaded 90° parking module.

    Each module is a complete unit:
    - Central aisle (24 ft wide)
    - Stalls on both sides (18 ft deep each)
    - Total module depth: 60 ft

    Attributes:
        module_id: Unique identifier
        aisle_polygon: Shapely polygon for the aisle
        stalls: List of stalls in this module (both sides)
        aisle_centerline: Centerline of the aisle
    """
    module_id: str
    aisle_polygon: ShapelyPolygon
    stalls: List[AttachedStall]
    aisle_centerline: Tuple[Tuple[float, float], Tuple[float, float]]
    level: int = 0  # Recursion level (0 = first interior, 1 = second, etc.)

    @property
    def stall_count(self) -> int:
        return len(self.stalls)

    def to_dict(self) -> dict:
        aisle_coords = list(self.aisle_polygon.exterior.coords)
        return {
            "module_id": self.module_id,
            "level": self.level,
            "stall_count": self.stall_count,
            "aisle_polygon": [{"x": c[0], "y": c[1]} for c in aisle_coords[:-1]],
            "aisle_centerline": {
                "start": {"x": self.aisle_centerline[0][0], "y": self.aisle_centerline[0][1]},
                "end": {"x": self.aisle_centerline[1][0], "y": self.aisle_centerline[1][1]},
            },
        }


@dataclass
class InteriorDensificationResult:
    """
    Result of interior densification phase.

    Attributes:
        modules: List of interior modules generated
        total_stalls: Total stalls from all interior modules
        levels_filled: Number of recursion levels completed
        remaining_polygon: Polygon remaining after densification (may be empty)
    """
    modules: List[InteriorModule]
    total_stalls: int
    levels_filled: int
    remaining_polygon: Optional[ShapelyPolygon]

    def get_all_stalls(self) -> List[AttachedStall]:
        """Get all stalls from all modules."""
        all_stalls = []
        for module in self.modules:
            all_stalls.extend(module.stalls)
        return all_stalls

    def get_all_aisle_polygons(self) -> List[ShapelyPolygon]:
        """Get all aisle polygons from all modules."""
        return [m.aisle_polygon for m in self.modules]

    def to_dict(self) -> dict:
        return {
            "total_stalls": self.total_stalls,
            "levels_filled": self.levels_filled,
            "modules": [m.to_dict() for m in self.modules],
        }


def _generate_interior_stalls_for_edge(
    edge_start: Tuple[float, float],
    edge_end: Tuple[float, float],
    normal: Tuple[float, float],
    available_polygon: ShapelyPolygon,
    module_id: str,
    level: int,
    side_label: str,
    prepared_available: Any = None,  # Pre-prepared geometry for faster contains checks
) -> List[AttachedStall]:
    """
    Generate stalls along one edge of an interior aisle.

    Args:
        edge_start: Start point of aisle edge
        edge_end: End point of aisle edge
        normal: Normal vector pointing away from aisle (toward stalls)
        available_polygon: Available space polygon
        module_id: Module identifier for stall IDs
        level: Recursion level
        side_label: Label for this side (N/S/E/W)
        prepared_available: Pre-prepared geometry for faster contains checks

    Returns:
        List of AttachedStall objects
    """
    print("⚠️ OLD INTERIOR LOGIC RUNNING ⚠️")
    stalls = []

    # Edge direction and length
    dx = edge_end[0] - edge_start[0]
    dy = edge_end[1] - edge_start[1]
    edge_length = math.sqrt(dx * dx + dy * dy)

    if edge_length < STALL_WIDTH:
        return []

    # Normalize direction
    if edge_length > 0:
        dx /= edge_length
        dy /= edge_length

    # Number of stalls that fit
    num_stalls = int(edge_length / STALL_WIDTH)
    if num_stalls == 0:
        return []

    # Center stalls along edge
    total_stall_width = num_stalls * STALL_WIDTH
    start_offset = (edge_length - total_stall_width) / 2

    nx, ny = normal

    # Pre-compute polygon bounds for fast rejection (avoid Shapely calls)
    available_bounds = available_polygon.bounds
    avail_minx, avail_miny, avail_maxx, avail_maxy = available_bounds

    # Use prepared geometry if provided, otherwise create one
    if prepared_available is None:
        prepared_available = shapely_prep(available_polygon)

    for i in range(num_stalls):
        stall_id = f"interior-{module_id}-{side_label}-{i}"

        # Center of stall along edge
        offset = start_offset + (i + 0.5) * STALL_WIDTH
        cx = edge_start[0] + offset * dx
        cy = edge_start[1] + offset * dy

        # Create stall polygon
        half_width = STALL_WIDTH / 2
        depth = STALL_LENGTH

        # Front corners (at aisle edge)
        fl = (cx - half_width * dx, cy - half_width * dy)
        fr = (cx + half_width * dx, cy + half_width * dy)

        # Back corners (extended by depth along normal)
        bl = (fl[0] + depth * nx, fl[1] + depth * ny)
        br = (fr[0] + depth * nx, fr[1] + depth * ny)

        # Fast bounding box pre-check (avoid Shapely if clearly outside)
        stall_minx = min(fl[0], fr[0], bl[0], br[0])
        stall_miny = min(fl[1], fr[1], bl[1], br[1])
        stall_maxx = max(fl[0], fr[0], bl[0], br[0])
        stall_maxy = max(fl[1], fr[1], bl[1], br[1])

        if (stall_maxx < avail_minx or stall_minx > avail_maxx or
                stall_maxy < avail_miny or stall_miny > avail_maxy):
            continue  # Completely outside bounds

        stall_poly = ShapelyPolygon([fl, fr, br, bl])

        # Check stall is within available polygon (use prepared geometry)
        if not prepared_available.contains(stall_poly):
            # Try intersection for partial containment
            if not prepared_available.intersects(stall_poly):
                continue
            clipped = stall_poly.intersection(available_polygon)
            if clipped.area < stall_poly.area * 0.8:
                continue  # Skip if too much clipped

        stalls.append(AttachedStall(
            id=stall_id,
            edge_index=-1,  # Interior stalls have no perimeter edge
            anchor=(cx, cy),
            polygon=stall_poly,
            angle=90,
            side=0,  # Interior stalls use side=0
        ))

    return stalls


# =============================================================================
# SINGLE INTERIOR AISLE — V2 STRICT MODE EXTENSION
# =============================================================================

def generate_single_interior_aisle(
    circulation: CirculationLoop,
    buildable_polygon: ShapelyPolygon,
) -> Tuple[Optional[InteriorModule], List[str], Dict[str, Any]]:
    """
    Generate exactly ONE interior aisle with double-loaded stalls.

    DETERMINISTIC MODULE POSITIONING:
    - Module depth = STALL_LENGTH + AISLE_WIDTH + STALL_LENGTH = 60 ft
    - Only allow interior aisle if buildable_depth >= module_depth
    - Center module in available depth (no guessing offsets)

    Args:
        circulation: Frozen perimeter circulation loop
        buildable_polygon: Buildable area polygon

    Returns:
        Tuple of (InteriorModule or None, validation_errors, debug_info)
        debug_info contains: interiorAisleGenerated, intersectionCount, degreeValidationPassed
    """
    print("🔥🔥🔥 SINGLE SPINE LOGIC RUNNING 🔥🔥🔥")
    print("[DEBUG] generate_single_interior_aisle CALLED")

    # =========================================================================
    # MODULE CONSTANTS (strict geometric module logic)
    # =========================================================================
    STALL_DEPTH = STALL_LENGTH  # 18 ft
    AISLE_WIDTH = AISLE_WIDTH_TWO_WAY  # 24 ft
    MODULE_DEPTH = STALL_DEPTH + AISLE_WIDTH + STALL_DEPTH  # 60 ft

    # Debug tracking
    debug_info: Dict[str, Any] = {
        "interiorAisleGenerated": False,
        "intersectionCount": 0,
        "degreeValidationPassed": False,
        "buildableDepth": 0.0,
        "moduleDepth": MODULE_DEPTH,
    }

    # =========================================================================
    # STEP 1: Get interior polygon (inside the circulation loop)
    # =========================================================================
    if not circulation.loop_polygon.interiors:
        return None, ["No interior space available"], debug_info

    inner_ring = circulation.loop_polygon.interiors[0]
    interior = ShapelyPolygon(inner_ring)

    if interior.is_empty or not interior.is_valid:
        return None, ["Interior polygon invalid"], debug_info

    # =========================================================================
    # STEP 2: Compute buildable depth inside perimeter loop
    # The interior polygon is shrunk by STALL_DEPTH because perimeter stalls
    # already occupy the outer 18ft ring.
    # =========================================================================
    minx, miny, maxx, maxy = interior.bounds
    interior_width = maxx - minx
    interior_height = maxy - miny

    # Shrink interior by STALL_DEPTH to avoid overlap with perimeter stalls
    interior_for_stalls = interior.buffer(-STALL_DEPTH)

    if interior_for_stalls.is_empty or not interior_for_stalls.is_valid:
        return None, ["Interior too small after setback"], debug_info

    if interior_for_stalls.geom_type == 'MultiPolygon':
        interior_for_stalls = max(
            interior_for_stalls.geoms, key=lambda g: g.area)

    # Get buildable bounds after shrinking
    stall_minx, stall_miny, stall_maxx, stall_maxy = interior_for_stalls.bounds
    buildable_width = stall_maxx - stall_minx
    buildable_height = stall_maxy - stall_miny

    # =========================================================================
    # STEP 3: Check if buildable_depth >= MODULE_DEPTH (60 ft)
    # Orientation: aisle runs parallel to the LONGER dimension
    # =========================================================================
    if buildable_width >= buildable_height:
        # Horizontal aisle: module depth is measured in Y direction
        buildable_depth = buildable_height
        orientation = "horizontal"
    else:
        # Vertical aisle: module depth is measured in X direction
        buildable_depth = buildable_width
        orientation = "vertical"

    debug_info["buildableDepth"] = buildable_depth

    if buildable_depth < MODULE_DEPTH:
        return None, [f"Insufficient depth: {buildable_depth:.1f}ft < {MODULE_DEPTH}ft"], debug_info

    # =========================================================================
    # STEP 4: Center module in available depth (deterministic positioning)
    # Module is centered in the interior, using interior bounds (not shrunk)
    # =========================================================================
    # TEMP DEBUG: Widened to 60 ft for visual debugging (normal is 24 ft)
    aisle_half_width = 30  # 60 ft total width (half = 30 ft)
    # aisle_half_width = AISLE_WIDTH / 2  # 12 ft (ORIGINAL)

    if orientation == "horizontal":
        # Aisle runs horizontally (X direction), centered in Y
        center_y = (miny + maxy) / 2  # Center of interior
        aisle_start = (minx, center_y)
        aisle_end = (maxx, center_y)
        aisle_polygon = ShapelyPolygon([
            (minx, center_y - aisle_half_width),
            (maxx, center_y - aisle_half_width),
            (maxx, center_y + aisle_half_width),
            (minx, center_y + aisle_half_width),
        ])
        # Extend centerline outward to reach perimeter centerline
        extended_start = (aisle_start[0] - aisle_half_width, aisle_start[1])
        extended_end = (aisle_end[0] + aisle_half_width, aisle_end[1])
    else:
        # Aisle runs vertically (Y direction), centered in X
        center_x = (minx + maxx) / 2  # Center of interior
        aisle_start = (center_x, miny)
        aisle_end = (center_x, maxy)
        aisle_polygon = ShapelyPolygon([
            (center_x - aisle_half_width, miny),
            (center_x + aisle_half_width, miny),
            (center_x + aisle_half_width, maxy),
            (center_x - aisle_half_width, maxy),
        ])
        # Extend centerline outward to reach perimeter centerline
        extended_start = (aisle_start[0], aisle_start[1] - aisle_half_width)
        extended_end = (aisle_end[0], aisle_end[1] + aisle_half_width)

    # =========================================================================
    # STEP 5: Intersection Validation
    # Interior aisle centerline must intersect perimeter centerline at exactly 2 points
    # =========================================================================
    interior_centerline = LineString([extended_start, extended_end])
    perimeter_centerline = circulation.loop_centerline  # Computed once, reused

    intersection = interior_centerline.intersection(perimeter_centerline)

    # Extract intersection points (computed once, reused for graph)
    if intersection.is_empty:
        debug_info["intersectionCount"] = 0
        return None, ["Interior does not connect at both ends"], debug_info
    elif intersection.geom_type == 'Point':
        intersection_points = [(intersection.x, intersection.y)]
    elif intersection.geom_type == 'MultiPoint':
        intersection_points = [(pt.x, pt.y) for pt in intersection.geoms]
    elif intersection.geom_type == 'LineString':
        # Overlapping segment counts as 2 endpoints
        coords = list(intersection.coords)
        intersection_points = [coords[0], coords[-1]]
    else:
        debug_info["intersectionCount"] = 0
        return None, ["Interior does not connect at both ends"], debug_info

    debug_info["intersectionCount"] = len(intersection_points)

    if len(intersection_points) != 2:
        return None, ["Interior does not connect at both ends"], debug_info

    # =========================================================================
    # STEP 6: Degree Validation (graph connectivity)
    # All nodes must have degree >= 2 after adding interior aisle edge
    # =========================================================================
    # Build perimeter graph from centerline
    G = nx.Graph()
    perimeter_coords = list(perimeter_centerline.coords)
    for i in range(len(perimeter_coords) - 1):
        node_a = (round(perimeter_coords[i][0], 2), round(
            perimeter_coords[i][1], 2))
        node_b = (round(perimeter_coords[i + 1][0], 2),
                  round(perimeter_coords[i + 1][1], 2))
        G.add_edge(node_a, node_b, edge_type="perimeter")

    # Round intersection points for node matching
    intersection_nodes = [(round(pt[0], 2), round(pt[1], 2))
                          for pt in intersection_points]

    # Split perimeter edges at intersection points and add interior edge
    for conn_pt in intersection_nodes:
        for edge in list(G.edges()):
            node_a, node_b = edge
            edge_line = LineString([node_a, node_b])
            if edge_line.distance(ShapelyPoint(conn_pt)) < 0.5:
                G.remove_edge(node_a, node_b)
                G.add_edge(node_a, conn_pt, edge_type="perimeter")
                G.add_edge(conn_pt, node_b, edge_type="perimeter")
                break

    # Add interior aisle edge
    G.add_edge(intersection_nodes[0],
               intersection_nodes[1], edge_type="interior")

    # Check all nodes have degree >= 2
    if any(G.degree(node) == 1 for node in G.nodes()):
        return None, ["Interior creates dead ends"], debug_info

    debug_info["degreeValidationPassed"] = True

    # =========================================================================
    # STEP 7: Stall Generation (after validation passes)
    # =========================================================================
    # Clip aisle to interior
    clipped_aisle = aisle_polygon.intersection(interior)
    if clipped_aisle.is_empty:
        return None, ["Aisle does not fit in interior"], debug_info

    if clipped_aisle.geom_type == 'MultiPolygon':
        clipped_aisle = max(clipped_aisle.geoms, key=lambda g: g.area)

    # Generate stalls on both sides of the aisle
    stalls = []

    # ==========================================================================
    # TEMP: Interior stall generation DISABLED for debugging
    # ==========================================================================
    # Prepare geometry once (avoid re-preparing for each edge)
    # prepared_interior = shapely_prep(interior_for_stalls)
    #
    # if orientation == "horizontal":
    #     center_y = (miny + maxy) / 2  # Center of interior
    #     # South side stalls (below aisle)
    #     stalls.extend(_generate_interior_stalls_for_edge(
    #         edge_start=(stall_minx, center_y - aisle_half_width),
    #         edge_end=(stall_maxx, center_y - aisle_half_width),
    #         normal=(0, -1),
    #         available_polygon=interior_for_stalls,
    #         module_id="interior-0",
    #         level=0,
    #         side_label="S",
    #         prepared_available=prepared_interior,
    #     ))
    #     # North side stalls (above aisle)
    #     stalls.extend(_generate_interior_stalls_for_edge(
    #         edge_start=(stall_minx, center_y + aisle_half_width),
    #         edge_end=(stall_maxx, center_y + aisle_half_width),
    #         normal=(0, 1),
    #         available_polygon=interior_for_stalls,
    #         module_id="interior-0",
    #         level=0,
    #         side_label="N",
    #         prepared_available=prepared_interior,
    #     ))
    # else:
    #     center_x = (minx + maxx) / 2  # Center of interior
    #     # West side stalls (left of aisle)
    #     stalls.extend(_generate_interior_stalls_for_edge(
    #         edge_start=(center_x - aisle_half_width, stall_miny),
    #         edge_end=(center_x - aisle_half_width, stall_maxy),
    #         normal=(-1, 0),
    #         available_polygon=interior_for_stalls,
    #         module_id="interior-0",
    #         level=0,
    #         side_label="W",
    #         prepared_available=prepared_interior,
    #     ))
    #     # East side stalls (right of aisle)
    #     stalls.extend(_generate_interior_stalls_for_edge(
    #         edge_start=(center_x + aisle_half_width, stall_miny),
    #         edge_end=(center_x + aisle_half_width, stall_maxy),
    #         normal=(1, 0),
    #         available_polygon=interior_for_stalls,
    #         module_id="interior-0",
    #         level=0,
    #         side_label="E",
    #         prepared_available=prepared_interior,
    #     ))
    #
    # if len(stalls) == 0:
    #     return None, ["No stalls could be placed on interior aisle"], debug_info
    # ==========================================================================

    # Create the interior module (aisle geometry only, no stalls)
    module = InteriorModule(
        module_id="interior-aisle-0",
        aisle_polygon=clipped_aisle,
        stalls=stalls,  # Empty list - stalls disabled
        aisle_centerline=(aisle_start, aisle_end),
        level=0,
    )

    debug_info["interiorAisleGenerated"] = True
    debug_info["stallCount"] = len(stalls)
    return module, [], debug_info


def attach_stalls_with_interior(
    circulation: CirculationLoop,
    buildable_polygon: ShapelyPolygon,
    angle: int,
    circulation_mode: CirculationMode = CirculationMode.TWO_WAY,
) -> Tuple[StallAttachmentResult, InteriorDensificationResult, Dict[str, Any]]:
    """
    Attach stalls to circulation loop edges + ONE interior aisle.

    V2 STRICT MODE (EXTENDED):
    - Perimeter stalls attached to circulation loop
    - Exactly ONE interior aisle (if fits)
    - Interior aisle is STRAIGHT, TWO_WAY, connects at BOTH ends
    - NO multiple aisles, NO optimization, NO recursive generation

    WORKFLOW:
    1. Generate perimeter loop
    2. Validate loop
    3. Attach perimeter stalls
    4. Try to generate ONE interior aisle
    5. If interior aisle fits, attach double-loaded stalls
    6. Return result

    Args:
        circulation: Frozen circulation loop
        buildable_polygon: Buildable area polygon
        angle: Parking angle (must be 90)
        circulation_mode: Circulation mode (must be TWO_WAY)

    Returns:
        Tuple of (perimeter_result, interior_result, interior_debug_info)
        interior_result contains 0 or 1 module.

    Raises:
        V2LayoutError: If angle != 90 or mode != TWO_WAY
    """
    import time
    print("[DEBUG] attach_stalls_with_interior START")

    # =========================================================================
    # PHASE 1: Perimeter Stall Generation
    # =========================================================================
    t_perimeter_start = time.perf_counter()
    perimeter_result = attach_stalls_to_circulation(
        circulation=circulation,
        buildable_polygon=buildable_polygon,
        angle=angle,
        circulation_mode=circulation_mode,
    )
    t_perimeter_end = time.perf_counter()

    # =========================================================================
    # PHASE 2: Single Interior Aisle Generation
    # =========================================================================
    t_interior_start = time.perf_counter()
    interior_module, errors, interior_debug_info = generate_single_interior_aisle(
        circulation=circulation,
        buildable_polygon=buildable_polygon,
    )
    t_interior_end = time.perf_counter()

    # Build interior result
    if interior_module is not None:
        interior_result = InteriorDensificationResult(
            modules=[interior_module],
            total_stalls=interior_module.stall_count,
            levels_filled=1,
            remaining_polygon=None,
        )
    else:
        interior_result = InteriorDensificationResult(
            modules=[],
            total_stalls=0,
            levels_filled=0,
            remaining_polygon=None,
        )

    return perimeter_result, interior_result, interior_debug_info


# =============================================================================
# V2 LAYOUT RESULT — SINGLE AUTHORITATIVE RETURN TYPE
# =============================================================================

@dataclass
class V2LayoutResult:
    """
    Result of generateParkingLayoutV2 — the single authoritative V2 output.

    This is the ONLY type that should be returned from V2 layout generation.
    All V2 layout data is contained here. No V1-derived data is included.

    Attributes:
        success: True if layout generation succeeded
        circulation: The frozen circulation loop
        stalls: List of all stalls (perimeter + interior)
        aisles: List of all aisles (loop edges + interior spines)
        perimeter_stalls: Count of perimeter stalls
        interior_stalls: Count of interior stalls
        total_stalls: Total stall count
        debug_geometry: Debug geometry for rendering
        validation_errors: List of validation errors (empty if valid)
        interior_debug_info: Debug info from interior aisle generation
    """
    success: bool
    circulation: CirculationLoop
    stalls: List[AttachedStall]
    aisles: List[Dict[str, Any]]
    perimeter_stalls: int
    interior_stalls: int
    total_stalls: int
    debug_geometry: Dict[str, Any]
    validation_errors: List[str] = field(default_factory=list)
    interior_debug_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "success": self.success,
            "total_stalls": self.total_stalls,
            "perimeter_stalls": self.perimeter_stalls,
            "interior_stalls": self.interior_stalls,
            "stalls": [s.to_dict() for s in self.stalls],
            "aisles": self.aisles,
            "debug_geometry": self.debug_geometry,
            "validation_errors": self.validation_errors,
            "interior_debug_info": self.interior_debug_info,
        }


# =============================================================================
# generateParkingLayoutV2 — SINGLE AUTHORITATIVE ENTRYPOINT
# =============================================================================

def generateParkingLayoutV2(
    site_boundary: ShapelyPolygon,
    setbacks: Optional[Setbacks] = None,
    circulation_mode: CirculationMode = CirculationMode.TWO_WAY,
    parking_angle: int = 90,
) -> V2LayoutResult:
    """
    Generate V2 parking layout — SINGLE AUTHORITATIVE ENTRYPOINT.

    This function is the ONLY entry point for V2 layout generation.
    When useV2 === true, the API MUST call ONLY this function.

    V2 CONTRACT ENFORCEMENT (Phase 2 FROZEN):
    1. Circulation loop generation fails → throw V2LayoutError
    2. Perimeter generation fails (zero stalls) → throw V2LayoutError
    3. Interior aisle fails validation → DO NOT throw, just skip interior
    4. Graph connectivity fails → throw V2LayoutError
    5. On V2LayoutError: return zero stalls, include error message, no recovery

    V2 produces EITHER:
    - A valid connected circulation system with stalls
    - OR zero stalls (on error)
    No partial invalid states.

    WORKFLOW:
    1. Generate circulation using V2 logic
    2. Validate circulation is continuous and non-empty
    3. Attach stalls (perimeter + interior spine)
    3.5. Validate perimeter produced stalls
    4. Validate no stall overlaps
    5. Validate no stall intersects circulation
    5.5. Validate graph connectivity
    6. Build aisles from circulation edges + interior spine
    7. Build debug geometry
    8. Return V2LayoutResult

    INVARIANTS:
    - If useV2 === true, do NOT compute, reuse, or display any V1-derived
      metrics, layouts, or explanations.
    - All layout data comes from V2 engine only.
    - No fallback to V1 on failure — raise V2LayoutError instead.

    Args:
        site_boundary: Site boundary as Shapely polygon
        setbacks: Optional setback distances from edges
        circulation_mode: Circulation mode (must be TWO_WAY for 90°)
        parking_angle: Parking angle in degrees (must be 90 in this phase)

    Returns:
        V2LayoutResult with all layout data

    Raises:
        V2LayoutError: If any step fails (no V1 fallback)
    """
    import time
    t_total_start = time.perf_counter()

    if setbacks is None:
        setbacks = Setbacks.uniform(0.0)

    # =========================================================================
    # COMPUTE EFFECTIVE SITE POLYGON (site minus setbacks)
    # This is THE authoritative boundary for stall validation.
    # =========================================================================
    min_x, min_y, max_x, max_y = site_boundary.bounds
    effective_site_polygon = ShapelyPolygon([
        (min_x + setbacks.west, min_y + setbacks.south),
        (max_x - setbacks.east, min_y + setbacks.south),
        (max_x - setbacks.east, max_y - setbacks.north),
        (min_x + setbacks.west, max_y - setbacks.north),
    ])

    # =========================================================================
    # STEP 1: Generate circulation using V2 logic
    # =========================================================================
    t_step1_start = time.perf_counter()

    try:
        circulation = generate_circulation_loop(
            site_boundary=site_boundary,
            setbacks=setbacks,
            aisle_width=AISLE_WIDTH_TWO_WAY,
            circulation_direction=CirculationDirection.CLOCKWISE,
            circulation_mode=circulation_mode,
            parking_angle=parking_angle,
        )
    except V2LayoutError:
        # No connected circulation could be generated
        raise V2LayoutError("NO_CONNECTED_CIRCULATION")

    t_step1_end = time.perf_counter()

    # =========================================================================
    # STEP 2: Validate circulation is continuous and non-empty
    # =========================================================================
    t_step2_start = time.perf_counter()

    # CRITICAL: If no valid connected circulation graph exists, raise immediately.
    # Do not generate stalls. Do not return fallback geometry. Do not compute metrics.
    # Do not call any V1 logic.
    def _validate_connected_circulation(circ: CirculationLoop) -> None:
        """Validate circulation is connected. Raises V2LayoutError if not."""
        if circ is None:
            raise V2LayoutError("NO_CONNECTED_CIRCULATION")

        if not circ.is_valid:
            raise V2LayoutError("NO_CONNECTED_CIRCULATION")

        if not circ.is_closed:
            raise V2LayoutError("NO_CONNECTED_CIRCULATION")

        if circ.edge_count == 0:
            raise V2LayoutError("NO_CONNECTED_CIRCULATION")

        if circ.loop_polygon is None or circ.loop_polygon.is_empty:
            raise V2LayoutError("NO_CONNECTED_CIRCULATION")

        # Validate the loop forms a valid ring (non-self-intersecting)
        if not circ.loop_polygon.is_valid:
            raise V2LayoutError("NO_CONNECTED_CIRCULATION")

    _validate_connected_circulation(circulation)

    # Additional validation for specific issues
    validation_errors = validate_circulation_loop(circulation)
    if validation_errors:
        # Specific validation failure = no connected circulation
        raise V2LayoutError("NO_CONNECTED_CIRCULATION")

    t_step2_end = time.perf_counter()

    # =========================================================================
    # STEP 3: Attach stalls (perimeter + interior)
    # =========================================================================
    t_step3_start = time.perf_counter()

    try:
        perimeter_result, interior_result, interior_debug_info = attach_stalls_with_interior(
            circulation=circulation,
            buildable_polygon=site_boundary,
            angle=parking_angle,
            circulation_mode=circulation_mode,
        )
    except V2LayoutError as e:
        # Re-raise with context
        raise V2LayoutError(f"Stall attachment failed: {e}") from e

    # =========================================================================
    # STEP 3.5: V2 CONTRACT - Perimeter must produce stalls
    # If perimeter generation produces zero stalls, throw V2LayoutError.
    # =========================================================================
    if perimeter_result.stall_count == 0:
        raise V2LayoutError(
            "PERIMETER_GENERATION_FAILED: Perimeter produced zero stalls"
        )

    # =========================================================================
    # AUTHORITATIVE STALL COUNTING (V2 AUDIT)
    # Combine perimeter + interior, then filter to only stalls fully inside
    # effective_site_polygon. This is THE source of truth for stall count.
    # =========================================================================
    perimeter_stalls_raw = perimeter_result.stalls
    interior_stalls_raw = interior_result.get_all_stalls()
    perimeter_count_raw = len(perimeter_stalls_raw)
    interior_count_raw = len(interior_stalls_raw)

    # =========================================================================
    # CREATE SINGLE AUTHORITATIVE FINAL STALL LIST
    # Filter criteria:
    #   1. Stall is not None
    #   2. Stall polygon is not None
    #   3. Stall is fully inside effective_site_polygon (not clipped)
    # =========================================================================
    final_stalls: List[AttachedStall] = []

    # Add valid perimeter stalls
    for stall in perimeter_stalls_raw:
        if stall is None:
            continue
        if stall.polygon is None:
            continue
        if not effective_site_polygon.contains(stall.polygon):
            continue
        final_stalls.append(stall)

    valid_perimeter_count = len(final_stalls)

    # Add valid interior stalls
    for stall in interior_stalls_raw:
        if stall is None:
            continue
        if stall.polygon is None:
            continue
        if not effective_site_polygon.contains(stall.polygon):
            continue
        final_stalls.append(stall)

    valid_interior_count = len(final_stalls) - valid_perimeter_count

    # =========================================================================
    # SINGLE SOURCE OF TRUTH: total_stalls = len(final_stalls)
    # No other place should recompute this count.
    # =========================================================================
    all_stalls = final_stalls
    total_count = len(final_stalls)
    perimeter_count = valid_perimeter_count
    interior_count = valid_interior_count

    t_step3_end = time.perf_counter()

    # =========================================================================
    # STEP 4: Validate no stall overlaps
    # OPTIMIZATION: Use STRtree spatial index for O(n log n) instead of O(n^2)
    # =========================================================================
    t_step4_start = time.perf_counter()

    # Cache stall polygons once (avoid re-creation in loop)
    stall_polygons = [s.polygon for s in all_stalls]

    # Build STRtree for fast spatial queries - O(n log n) vs O(n^2)
    stall_tree = STRtree(stall_polygons)
    checked_pairs = set()  # Track checked pairs to avoid duplicates
    stall_overlap_errors = []

    for i, poly_a in enumerate(stall_polygons):
        # Query tree for potential overlaps (returns indices)
        candidate_indices = stall_tree.query(poly_a)
        for j in candidate_indices:
            if i >= j:  # Skip self and already-checked pairs
                continue
            pair_key = (i, j)
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            poly_b = stall_polygons[j]
            if poly_a.intersects(poly_b):
                intersection = poly_a.intersection(poly_b)
                if intersection.area > 0.5:  # More than 0.5 sq ft = real overlap
                    stall_overlap_errors.append(
                        f"Stall {all_stalls[i].id} overlaps stall {all_stalls[j].id} "
                        f"(area={intersection.area:.2f} sq ft)"
                    )

    if stall_overlap_errors:
        raise V2LayoutError(
            f"Stall overlap detected: {'; '.join(stall_overlap_errors)}"
        )

    t_step4_end = time.perf_counter()

    # =========================================================================
    # STEP 5: Validate no stall intersects circulation
    # OPTIMIZATION: Use prepared geometry for faster intersection checks
    # =========================================================================
    t_step5_start = time.perf_counter()

    circulation_poly = circulation.loop_polygon
    circulation_prepared = shapely_prep(
        circulation_poly)  # Faster intersection checks
    stall_circulation_errors = []

    for i, stall in enumerate(all_stalls):
        stall_poly = stall_polygons[i]  # Reuse cached polygons
        if circulation_prepared.intersects(stall_poly):
            # Check if it's more than just touching edges
            intersection = stall_poly.intersection(circulation_poly)
            if intersection.area > 0.5:  # More than 0.5 sq ft = real overlap
                stall_circulation_errors.append(
                    f"Stall {stall.id} intersects circulation "
                    f"(area={intersection.area:.2f} sq ft)"
                )

    if stall_circulation_errors:
        raise V2LayoutError(
            f"Stall-circulation intersection detected: "
            f"{'; '.join(stall_circulation_errors)}"
        )

    t_step5_end = time.perf_counter()

    # =========================================================================
    # STEP 5.5: Validate graph connectivity (V2 CONTRACT ENFORCEMENT)
    # Perimeter circulation must form a connected loop.
    # Interior aisle connectivity was already validated in Phase 2B.
    # =========================================================================
    t_step55_start = time.perf_counter()

    # Perimeter circulation is a closed loop - verify it's connected
    connectivity_graph = nx.Graph()
    perimeter_coords = list(circulation.loop_centerline.coords)
    for i in range(len(perimeter_coords) - 1):
        node_a = (round(perimeter_coords[i][0], 2), round(
            perimeter_coords[i][1], 2))
        node_b = (round(perimeter_coords[i + 1][0], 2),
                  round(perimeter_coords[i + 1][1], 2))
        connectivity_graph.add_edge(node_a, node_b, edge_type="perimeter")

    # V2 CONTRACT: Perimeter graph must be connected
    if not nx.is_connected(connectivity_graph):
        raise V2LayoutError(
            "DISCONNECTED_CIRCULATION: Perimeter circulation is not connected"
        )

    # Interior aisle connectivity was validated in Phase 2B (generate_single_interior_aisle)
    # If interior_debug_info["interiorAisleGenerated"] == True, interior is connected.
    # If interior was skipped, perimeter-only is still a valid connected circulation.

    t_step55_end = time.perf_counter()

    # =========================================================================
    # STEP 6: Build aisles from circulation edges + interior spine
    # =========================================================================
    t_step6_start = time.perf_counter()

    aisles = []

    # Add circulation loop edges as aisles
    for i, edge in enumerate(circulation.loop_edges):
        # Build aisle polygon from edge
        edge_start = edge.start
        edge_end = edge.end
        dx, dy = edge.direction
        normal_x, normal_y = edge.normal

        half_width = circulation.aisle_width / 2

        # Create aisle rectangle
        p1 = (edge_start[0] + normal_x * half_width,
              edge_start[1] + normal_y * half_width)
        p2 = (edge_start[0] - normal_x * half_width,
              edge_start[1] - normal_y * half_width)
        p3 = (edge_end[0] - normal_x * half_width,
              edge_end[1] - normal_y * half_width)
        p4 = (edge_end[0] + normal_x * half_width,
              edge_end[1] + normal_y * half_width)

        aisles.append({
            "id": f"aisle_loop_{i}",
            "geometry": {
                "points": [
                    {"x": p1[0], "y": p1[1]},
                    {"x": p2[0], "y": p2[1]},
                    {"x": p3[0], "y": p3[1]},
                    {"x": p4[0], "y": p4[1]},
                ]
            },
            "width": circulation.aisle_width,
            "circulation": circulation_mode.value,
            "flowDirection": {"dx": dx, "dy": dy},
            "centerline": {
                "start": {"x": edge_start[0], "y": edge_start[1]},
                "end": {"x": edge_end[0], "y": edge_end[1]},
            },
        })

    # Add interior spine aisles (if any)
    for module in interior_result.modules:
        if module.aisle_polygon:
            coords = list(module.aisle_polygon.exterior.coords)
            aisles.append({
                "id": f"aisle_interior_{module.module_id}",
                "geometry": {
                    "points": [{"x": c[0], "y": c[1]} for c in coords[:-1]]
                },
                "width": AISLE_WIDTH_TWO_WAY,
                "circulation": CirculationMode.TWO_WAY.value,
                "flowDirection": None,
                "centerline": {
                    "start": {"x": module.aisle_centerline[0][0], "y": module.aisle_centerline[0][1]},
                    "end": {"x": module.aisle_centerline[1][0], "y": module.aisle_centerline[1][1]},
                } if module.aisle_centerline else None,
            })

    t_step6_end = time.perf_counter()

    # =========================================================================
    # STEP 7: Build debug geometry
    # =========================================================================
    t_step7_start = time.perf_counter()

    loop_dict = circulation.to_dict()
    loop_poly = circulation.loop_polygon
    outer_coords = list(loop_poly.exterior.coords)
    inner_coords = list(
        loop_poly.interiors[0].coords) if loop_poly.interiors else []
    centerline_coords = list(circulation.loop_centerline.coords)

    debug_geometry = {
        "circulation_loop": loop_dict,
        "loop_edges": [
            [list(e.start), list(e.end)]
            for e in circulation.loop_edges
        ],
        "stall_count": total_count,
        "perimeter_stalls": perimeter_count,
        "interior_stalls": interior_count,
        "interior_levels": interior_result.levels_filled,
        "loop_polygon_outer": [[c[0], c[1]] for c in outer_coords[:-1]],
        "loop_polygon_inner": [[c[0], c[1]] for c in inner_coords[:-1]] if inner_coords else [],
        "loop_polyline": [[c[0], c[1]] for c in centerline_coords],
        "aisle_width": circulation.aisle_width,
        "circulation_mode": circulation_mode.value,
    }

    # =========================================================================
    # STEP 8: Return V2LayoutResult
    # =========================================================================
    t_step7_end = time.perf_counter()

    t_total_end = time.perf_counter()

    return V2LayoutResult(
        success=True,
        circulation=circulation,
        stalls=all_stalls,
        aisles=aisles,
        perimeter_stalls=perimeter_count,
        interior_stalls=interior_count,
        total_stalls=total_count,
        debug_geometry=debug_geometry,
        validation_errors=[],
        interior_debug_info=interior_debug_info,
    )
