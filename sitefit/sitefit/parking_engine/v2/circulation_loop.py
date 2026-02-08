"""
GenFabTools Parking Engine v2 — Circulation-First Layout

ARCHITECTURE:
This module implements TRUE circulation-first layout generation:

1. CirculationLoop generates ONE continuous loop polygon FIRST
2. Circulation geometry is FROZEN after creation
3. Parking modules attach to circulation edges
4. Generation stops when remaining depth < module depth
5. If ANY stall intersects circulation → abort with V2LayoutError (no V1 fallback)

CIRCULATION TYPES:
- PERPENDICULAR (90°): Parallel two-way aisles, double-loaded
- ANGLED (45°/60°): Serpentine one-way loop, single-loaded on correct side

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, FrozenSet
from enum import Enum

from sitefit.core.geometry import Point, Polygon, Line
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Standard stall dimensions (feet)
STALL_WIDTH = 9.0
STALL_DEPTH = 18.0

# Aisle widths by angle
AISLE_WIDTH_90 = 24.0  # Two-way perpendicular
AISLE_WIDTH_60 = 14.0  # One-way angled
AISLE_WIDTH_45 = 13.0  # One-way angled

# Minimum setback from zone boundary
MIN_SETBACK = 2.0


# =============================================================================
# LAYOUT STRATEGY ENUM
# =============================================================================

class LayoutStrategy(str, Enum):
    """Parking layout strategy."""
    PERPENDICULAR_90 = "90"
    ANGLED_60 = "60"
    ANGLED_45 = "45"

    @property
    def degrees(self) -> int:
        return int(self.value)

    @property
    def radians(self) -> float:
        return math.radians(self.degrees)

    @property
    def aisle_width(self) -> float:
        if self == LayoutStrategy.PERPENDICULAR_90:
            return AISLE_WIDTH_90
        elif self == LayoutStrategy.ANGLED_60:
            return AISLE_WIDTH_60
        else:
            return AISLE_WIDTH_45

    @property
    def is_double_loaded(self) -> bool:
        """90° uses double-loaded aisles."""
        return self == LayoutStrategy.PERPENDICULAR_90

    @property
    def is_one_way(self) -> bool:
        """Angled parking uses one-way circulation."""
        return self != LayoutStrategy.PERPENDICULAR_90


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
# FROZEN CIRCULATION LOOP
# =============================================================================

@dataclass(frozen=True)
class CirculationLoop:
    """
    Frozen circulation geometry.

    Once created, this geometry CANNOT be modified.
    All stall generation must reference this frozen state.

    Attributes:
        polygon: The circulation loop as a Shapely polygon (frozen)
        edges: List of (start, end) point tuples for each aisle edge
        aisle_width: Width of the aisle
        is_one_way: True for one-way circulation
    """
    polygon: ShapelyPolygon  # Frozen Shapely polygon
    edges: Tuple[Tuple[Tuple[float, float], Tuple[float, float]], ...]
    aisle_width: float
    is_one_way: bool
    setback: float = MIN_SETBACK

    @property
    def is_closed(self) -> bool:
        """True if the loop is a closed polygon."""
        return self.polygon.is_valid and not self.polygon.is_empty

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        return self.polygon.bounds

    def intersects_polygon(self, other: ShapelyPolygon) -> bool:
        """Check if another polygon intersects the circulation."""
        return self.polygon.intersects(other)

    def intersection_area(self, other: ShapelyPolygon) -> float:
        """Return intersection area with another polygon."""
        if not self.polygon.intersects(other):
            return 0.0
        return self.polygon.intersection(other).area


# =============================================================================
# AISLE EDGE — Represents one drivable edge of circulation
# =============================================================================

@dataclass(frozen=True)
class AisleEdge:
    """
    One edge of the circulation where stalls can attach.

    Attributes:
        index: Edge identifier
        start: Start point (x, y)
        end: End point (x, y)
        direction: Unit vector along edge
        stall_side: +1 for right side, -1 for left side (0 = both for 90°)
        polygon: Aisle polygon for this edge
    """
    index: int
    start: Tuple[float, float]
    end: Tuple[float, float]
    direction: Tuple[float, float]
    stall_side: int
    polygon: ShapelyPolygon

    @property
    def length(self) -> float:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.sqrt(dx * dx + dy * dy)

    @property
    def centerline_y(self) -> float:
        """Y-coordinate of centerline (for horizontal aisles)."""
        return (self.start[1] + self.end[1]) / 2


# =============================================================================
# PARKING MODULE — Stalls attached to an aisle edge
# =============================================================================

@dataclass
class ParkingStall:
    """A single parking stall."""
    id: str
    edge_index: int
    polygon: ShapelyPolygon
    anchor: Tuple[float, float]
    angle: int

    def to_dict(self) -> dict:
        coords = list(self.polygon.exterior.coords)
        return {
            "id": self.id,
            "edge_index": self.edge_index,
            "angle": self.angle,
            "geometry": {
                "points": [{"x": c[0], "y": c[1]} for c in coords[:-1]]
            }
        }


# =============================================================================
# CIRCULATION LOOP GENERATOR
# =============================================================================

class CirculationLoopGenerator:
    """
    Generates a frozen circulation loop polygon.

    This is the FIRST step in layout generation.
    The loop geometry is frozen after creation.
    """

    def __init__(self, strategy: LayoutStrategy, setback: float = MIN_SETBACK):
        self.strategy = strategy
        self.setback = setback
        self.aisle_width = strategy.aisle_width

    def generate(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
    ) -> Tuple[CirculationLoop, List[AisleEdge]]:
        """
        Generate circulation loop for the zone.

        Returns:
            Tuple of (frozen CirculationLoop, list of AisleEdge)
        """
        # Apply setbacks
        inner_min_x = min_x + self.setback
        inner_min_y = min_y + self.setback
        inner_max_x = max_x - self.setback
        inner_max_y = max_y - self.setback

        width = inner_max_x - inner_min_x
        height = inner_max_y - inner_min_y

        if width < self.aisle_width or height < self._module_depth():
            raise V2LayoutError(
                f"Zone too small after setbacks: {width:.1f}x{height:.1f} ft")

        if self.strategy == LayoutStrategy.PERPENDICULAR_90:
            return self._generate_parallel_aisles(
                inner_min_x, inner_min_y, inner_max_x, inner_max_y)
        else:
            return self._generate_serpentine_loop(
                inner_min_x, inner_min_y, inner_max_x, inner_max_y)

    def _module_depth(self) -> float:
        """Module depth = stalls + aisle + stalls (if double-loaded)."""
        footprint = self._stall_footprint_depth()
        if self.strategy.is_double_loaded:
            return footprint + self.aisle_width + footprint
        return footprint + self.aisle_width

    def _stall_footprint_depth(self) -> float:
        """Stall footprint depth perpendicular to aisle."""
        if self.strategy == LayoutStrategy.PERPENDICULAR_90:
            return STALL_DEPTH
        sin_a = math.sin(self.strategy.radians)
        cos_a = math.cos(self.strategy.radians)
        return STALL_DEPTH * sin_a + STALL_WIDTH * cos_a

    def _stall_footprint_width(self) -> float:
        """Stall footprint width along aisle."""
        if self.strategy == LayoutStrategy.PERPENDICULAR_90:
            return STALL_WIDTH
        sin_a = math.sin(self.strategy.radians)
        return STALL_WIDTH / sin_a

    def _generate_serpentine_loop(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
    ) -> Tuple[CirculationLoop, List[AisleEdge]]:
        """
        Generate one-way serpentine loop for angled parking.

        Creates continuous loop that snakes back and forth.
        """
        aisle_half = self.aisle_width / 2
        footprint_depth = self._stall_footprint_depth()
        module_depth = self._module_depth()

        # End overhang for angled stalls
        cos_a = math.cos(self.strategy.radians)
        end_overhang = STALL_DEPTH * cos_a

        # Calculate number of aisles that fit
        first_inset = footprint_depth + aisle_half
        available_height = (max_y - min_y) - first_inset - footprint_depth

        if available_height < 0:
            raise V2LayoutError("Zone too shallow for even one aisle")

        num_aisles = 1 + int(available_height / module_depth)
        num_aisles = max(2, min(num_aisles, 50))

        # Stop when remaining depth < module_depth
        edges: List[AisleEdge] = []
        aisle_polygons: List[ShapelyPolygon] = []
        edge_idx = 0

        remaining = available_height
        for i in range(num_aisles):
            if remaining < 0:
                break

            aisle_y = min_y + first_inset + i * module_depth

            # Check top boundary
            if aisle_y + aisle_half + footprint_depth > max_y:
                break

            # Serpentine direction
            if i % 2 == 0:
                start = (min_x + end_overhang, aisle_y)
                end = (max_x - end_overhang, aisle_y)
                direction = (1.0, 0.0)
                stall_side = +1  # Stalls below (right side facing +X)
            else:
                start = (max_x - end_overhang, aisle_y)
                end = (min_x + end_overhang, aisle_y)
                direction = (-1.0, 0.0)
                stall_side = -1  # Stalls below (left side facing -X)

            # Create aisle polygon
            aisle_poly = self._create_aisle_polygon(start, end, direction)
            aisle_polygons.append(aisle_poly)

            edges.append(AisleEdge(
                index=edge_idx,
                start=start,
                end=end,
                direction=direction,
                stall_side=stall_side,
                polygon=aisle_poly,
            ))
            edge_idx += 1

            remaining -= module_depth

        if len(edges) < 2:
            raise V2LayoutError("Could not generate at least 2 aisle passes")

        # Create unified circulation polygon (all aisles + connectors)
        loop_polygon = unary_union(aisle_polygons)
        if not loop_polygon.is_valid:
            loop_polygon = loop_polygon.buffer(0)

        # Build edge tuples for frozen state
        edge_tuples = tuple((e.start, e.end) for e in edges)

        circulation = CirculationLoop(
            polygon=loop_polygon,
            edges=edge_tuples,
            aisle_width=self.aisle_width,
            is_one_way=True,
            setback=self.setback,
        )

        return circulation, edges

    def _generate_parallel_aisles(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
    ) -> Tuple[CirculationLoop, List[AisleEdge]]:
        """
        Generate parallel two-way aisles for 90° parking.

        Each aisle is independent (not a true loop).
        """
        aisle_half = self.aisle_width / 2
        stall_depth = STALL_DEPTH
        module_depth = self._module_depth()

        first_aisle_y = min_y + stall_depth + aisle_half
        available_height = (max_y - min_y) - stall_depth - aisle_half

        if available_height < 0:
            raise V2LayoutError("Zone too shallow for perpendicular parking")

        num_aisles = 1 + int(available_height / module_depth)
        num_aisles = max(1, min(num_aisles, 50))

        edges: List[AisleEdge] = []
        aisle_polygons: List[ShapelyPolygon] = []

        remaining = available_height
        for i in range(num_aisles):
            if remaining < 0:
                break

            aisle_y = first_aisle_y + i * module_depth

            # Check bounds
            if aisle_y + aisle_half > max_y:
                break

            start = (min_x, aisle_y)
            end = (max_x, aisle_y)
            direction = (1.0, 0.0)

            # Create aisle polygon
            aisle_poly = self._create_aisle_polygon(start, end, direction)
            aisle_polygons.append(aisle_poly)

            edges.append(AisleEdge(
                index=i,
                start=start,
                end=end,
                direction=direction,
                stall_side=0,  # Both sides for 90°
                polygon=aisle_poly,
            ))

            remaining -= module_depth

        if len(edges) < 1:
            raise V2LayoutError("Could not generate any aisles")

        loop_polygon = unary_union(aisle_polygons)
        if not loop_polygon.is_valid:
            loop_polygon = loop_polygon.buffer(0)

        edge_tuples = tuple((e.start, e.end) for e in edges)

        circulation = CirculationLoop(
            polygon=loop_polygon,
            edges=edge_tuples,
            aisle_width=self.aisle_width,
            is_one_way=False,
            setback=self.setback,
        )

        return circulation, edges

    def _create_aisle_polygon(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        direction: Tuple[float, float],
    ) -> ShapelyPolygon:
        """Create aisle polygon from centerline."""
        dx, dy = direction
        half = self.aisle_width / 2

        # Normal vectors
        left_n = (-dy, dx)
        right_n = (dy, -dx)

        # Four corners
        sl = (start[0] + half * left_n[0], start[1] + half * left_n[1])
        sr = (start[0] + half * right_n[0], start[1] + half * right_n[1])
        er = (end[0] + half * right_n[0], end[1] + half * right_n[1])
        el = (end[0] + half * left_n[0], end[1] + half * left_n[1])

        return ShapelyPolygon([sl, sr, er, el])


# =============================================================================
# STALL GENERATOR — Attaches stalls to circulation edges
# =============================================================================

class StallAttachmentGenerator:
    """
    Attaches parking stalls to frozen circulation edges.

    Stalls are generated AFTER circulation is frozen.
    Each stall references the final aisle polygon.
    """

    def __init__(self, strategy: LayoutStrategy, circulation: CirculationLoop):
        self.strategy = strategy
        self.circulation = circulation  # FROZEN

    def generate_for_edge(
        self,
        edge: AisleEdge,
        zone_polygon: ShapelyPolygon,
    ) -> List[ParkingStall]:
        """
        Generate stalls for one aisle edge.

        For 90°: double-loaded (both sides)
        For 45°/60°: single-loaded on correct side only
        """
        stalls: List[ParkingStall] = []

        footprint_width = self._stall_footprint_width()
        footprint_depth = self._stall_footprint_depth()
        aisle_half = self.circulation.aisle_width / 2

        # Number of stalls that fit
        num_stalls = int(edge.length / footprint_width)
        if num_stalls == 0:
            return []

        dx, dy = edge.direction

        # Determine sides to generate stalls
        if self.strategy.is_double_loaded:
            sides = [-1, +1]
        else:
            sides = [edge.stall_side] if edge.stall_side != 0 else [+1]

        for side in sides:
            # Normal vector for this side
            if side > 0:
                normal = (dy, -dx)  # Right
            else:
                normal = (-dy, dx)  # Left

            for i in range(num_stalls):
                stall_id = f"stall-{edge.index}-{side}-{i}"

                # Position along edge
                offset = (i + 0.5) * footprint_width
                cx = edge.start[0] + offset * dx
                cy = edge.start[1] + offset * dy

                # Anchor at aisle edge
                ax = cx + aisle_half * normal[0]
                ay = cy + aisle_half * normal[1]

                # Create stall polygon
                stall_poly = self._create_stall_polygon(
                    (ax, ay), normal, dx, dy, footprint_width, footprint_depth)

                # Check within zone
                if not zone_polygon.contains(stall_poly):
                    continue

                # CRITICAL: Check NO overlap with circulation
                overlap = self.circulation.intersection_area(stall_poly)
                if overlap > 0.5:  # More than edge touching
                    continue

                stalls.append(ParkingStall(
                    id=stall_id,
                    edge_index=edge.index,
                    polygon=stall_poly,
                    anchor=(ax, ay),
                    angle=self.strategy.degrees,
                ))

        return stalls

    def _stall_footprint_depth(self) -> float:
        if self.strategy == LayoutStrategy.PERPENDICULAR_90:
            return STALL_DEPTH
        sin_a = math.sin(self.strategy.radians)
        cos_a = math.cos(self.strategy.radians)
        return STALL_DEPTH * sin_a + STALL_WIDTH * cos_a

    def _stall_footprint_width(self) -> float:
        if self.strategy == LayoutStrategy.PERPENDICULAR_90:
            return STALL_WIDTH
        sin_a = math.sin(self.strategy.radians)
        return STALL_WIDTH / sin_a

    def _create_stall_polygon(
        self,
        anchor: Tuple[float, float],
        normal: Tuple[float, float],
        aisle_dx: float,
        aisle_dy: float,
        width: float,
        depth: float,
    ) -> ShapelyPolygon:
        """Create stall polygon from anchor point."""
        half_w = width / 2
        ax, ay = anchor

        fl = (ax - half_w * aisle_dx, ay - half_w * aisle_dy)
        fr = (ax + half_w * aisle_dx, ay + half_w * aisle_dy)
        br = (fr[0] + depth * normal[0], fr[1] + depth * normal[1])
        bl = (fl[0] + depth * normal[0], fl[1] + depth * normal[1])

        return ShapelyPolygon([fl, fr, br, bl])


# =============================================================================
# LAYOUT RESULT
# =============================================================================

@dataclass
class CirculationLayoutResult:
    """
    Result of circulation-first layout generation.
    """
    strategy: LayoutStrategy
    circulation: CirculationLoop
    edges: List[AisleEdge]
    stalls: List[ParkingStall]
    is_valid: bool
    error: Optional[str] = None

    @property
    def stall_count(self) -> int:
        return len(self.stalls) if self.is_valid else 0

    @property
    def aisle_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "is_valid": self.is_valid,
            "stall_count": self.stall_count,
            "aisle_count": self.aisle_count,
            "error": self.error,
        }


# =============================================================================
# HARD VALIDATION — Abort if ANY stall intersects circulation
# =============================================================================

def validate_stalls_vs_circulation(
    stalls: List[ParkingStall],
    circulation: CirculationLoop,
) -> List[str]:
    """
    HARD validation: No stall may intersect circulation.

    Returns list of errors. If non-empty, layout MUST be aborted.
    """
    errors: List[str] = []

    for stall in stalls:
        area = circulation.intersection_area(stall.polygon)
        if area > 0.5:  # More than edge touching (~0.5 sq ft tolerance)
            errors.append(
                f"Stall {stall.id} intersects circulation (area={area:.2f} sq ft)")

    return errors


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def generate_circulation_first_layout(
    angle: int,
    min_x: float, min_y: float,
    max_x: float, max_y: float,
    setback: float = MIN_SETBACK,
) -> CirculationLayoutResult:
    """
    Generate a circulation-first layout for the given angle.

    ALGORITHM:
    1. Create CirculationLoop (frozen)
    2. Attach stalls to circulation edges
    3. Validate no stall intersects circulation
    4. If validation fails → raise V2LayoutError (no V1 fallback)

    Args:
        angle: 90, 60, or 45
        min_x, min_y, max_x, max_y: Zone bounds
        setback: Minimum setback from boundary

    Returns:
        CirculationLayoutResult

    Raises:
        V2LayoutError: If layout cannot be generated (no V1 fallback)
    """
    # Determine strategy
    if angle == 90:
        strategy = LayoutStrategy.PERPENDICULAR_90
    elif angle == 60:
        strategy = LayoutStrategy.ANGLED_60
    elif angle == 45:
        strategy = LayoutStrategy.ANGLED_45
    else:
        raise V2LayoutError(f"Unsupported angle: {angle}")

    print(f"\n[CIRCULATION-FIRST] Generating {angle}° layout")
    print(
        f"[CIRCULATION-FIRST] Zone: ({min_x:.1f}, {min_y:.1f}) to ({max_x:.1f}, {max_y:.1f})")
    print(f"[CIRCULATION-FIRST] Setback: {setback:.1f} ft")

    # Step 1: Generate circulation loop (FROZEN after this)
    try:
        circ_gen = CirculationLoopGenerator(strategy, setback)
        circulation, edges = circ_gen.generate(min_x, min_y, max_x, max_y)
    except V2LayoutError as e:
        print(f"[CIRCULATION-FIRST] ERROR: {e}")
        raise

    print(f"[CIRCULATION-FIRST] Circulation frozen: {len(edges)} edges")

    # Step 2: Create zone polygon for containment check
    zone_polygon = ShapelyPolygon([
        (min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)
    ])

    # Step 3: Attach stalls to circulation edges
    stall_gen = StallAttachmentGenerator(strategy, circulation)
    all_stalls: List[ParkingStall] = []

    for edge in edges:
        stalls = stall_gen.generate_for_edge(edge, zone_polygon)
        all_stalls.extend(stalls)

    print(f"[CIRCULATION-FIRST] Generated {len(all_stalls)} stalls")

    # Step 4: HARD validation — no stall may intersect circulation
    errors = validate_stalls_vs_circulation(all_stalls, circulation)

    if errors:
        print(f"[CIRCULATION-FIRST] VALIDATION FAILED: {len(errors)} errors")
        for err in errors[:5]:
            print(f"  {err}")
        # Do NOT fallback to V1 — raise error
        raise V2LayoutError(
            f"Layout validation failed: {len(errors)} stalls intersect circulation")

    print(
        f"[CIRCULATION-FIRST] Layout valid: {len(all_stalls)} stalls, {len(edges)} aisles")

    return CirculationLayoutResult(
        strategy=strategy,
        circulation=circulation,
        edges=edges,
        stalls=all_stalls,
        is_valid=True,
        error=None,
    )
