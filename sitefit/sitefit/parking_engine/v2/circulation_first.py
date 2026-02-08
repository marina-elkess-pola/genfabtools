"""
GenFabTools Parking Engine v2 — Circulation-First Parking Layout Generator

CIRCULATION-FIRST APPROACH:
The ENTIRE layout is derived from a SINGLE CLOSED circulation loop.
Aisles exist ONLY as segments of this loop. No independent aisles.

LOOP TOPOLOGY:
- One continuous one-way path
- CLOSED (returns to entry point — no dead ends)
- Rectangular or U-shaped depending on zone
- All segment endpoints are connected (continuity guaranteed)

EXPLICIT RULES:
- ONE loop per zone (no exceptions)
- Aisles are segments WITH stalls
- Connectors are segments WITHOUT stalls
- Stalls attach to ONE side only (outside of loop)
- Stall orientation follows loop direction
- No opposing stall faces
- No double-loaded aisles

VALIDATION GATES (must pass before stall counting):
1. Loop is closed (entry == exit)
2. Loop is continuous (no gaps)
3. All aisles have entry and exit
4. Loop fits within buildable bounds

DEBUG MODE:
- Circulation loop (thick orange, shows direction)
- Loop direction arrows
- Stall normals (where stalls would attach)

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum

from sitefit.core.geometry import Point, Polygon, Line
from sitefit.parking_engine.v2.geometry_angled import (
    ParkingAngle,
    StallRowGenerator,
    AngledStall,
    AngledAisle,
    CirculationMode,
    AISLE_WIDTHS,
)
from sitefit.parking_engine.v2.zones import Zone, AngleConfig


# =============================================================================
# LOOP SEGMENT TYPE
# =============================================================================

class LoopSegmentType(str, Enum):
    """Type of segment in the circulation loop."""
    AISLE = "aisle"          # Aisle segment (has stalls on one side)
    CONNECTOR = "connector"  # Connector segment (no stalls, just circulation)


# =============================================================================
# LOOP SEGMENT — One segment of the closed loop
# =============================================================================

@dataclass
class LoopSegment:
    """
    A single segment of the closed circulation loop.

    Every segment is part of the continuous one-way closed path.
    AISLE segments have stalls on ONE side.
    CONNECTOR segments have no stalls.

    Attributes:
        index: Segment index in loop traversal order
        segment_type: AISLE or CONNECTOR
        start: Start point (traffic enters here)
        end: End point (traffic exits here)
        direction: (dx, dy) unit vector of traffic flow
        stall_side: -1=left, +1=right, 0=none (CONNECTOR only)
        aisle: AngledAisle geometry (AISLE only)
        stalls: Stalls attached (AISLE only)
    """
    index: int
    segment_type: LoopSegmentType
    start: Point
    end: Point
    direction: Tuple[float, float]
    stall_side: int = 0
    aisle: Optional[AngledAisle] = None
    stalls: List[AngledStall] = field(default_factory=list)

    @property
    def length(self) -> float:
        """Length of this segment in feet."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return math.sqrt(dx * dx + dy * dy)

    @property
    def has_stalls(self) -> bool:
        """Whether this segment has stalls."""
        return self.segment_type == LoopSegmentType.AISLE and self.stall_side != 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "index": self.index,
            "type": self.segment_type.value,
            "start": {"x": self.start.x, "y": self.start.y},
            "end": {"x": self.end.x, "y": self.end.y},
            "direction": list(self.direction),
            "stall_side": "left" if self.stall_side < 0 else ("right" if self.stall_side > 0 else "none"),
            "stall_count": len(self.stalls),
            "length": round(self.length, 2),
        }


# =============================================================================
# CIRCULATION LOOP — CLOSED one-way path
# =============================================================================

@dataclass
class CirculationLoop:
    """
    Complete CLOSED circulation loop for a parking zone.

    The loop is a connected series of segments forming a continuous
    one-way CLOSED path. Last segment connects back to first segment.

    CONSTRAINTS:
    - CLOSED: segments[-1].end == segments[0].start
    - CONTINUOUS: segments[i].end == segments[i+1].start for all i
    - ONE-WAY: all segment directions consistent with loop traversal
    - NO DEAD ENDS: every segment has entry and exit
    """
    segments: List[LoopSegment] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        """Check if loop is properly closed."""
        if len(self.segments) < 3:
            return False
        first = self.segments[0]
        last = self.segments[-1]
        dx = first.start.x - last.end.x
        dy = first.start.y - last.end.y
        gap = math.sqrt(dx * dx + dy * dy)
        return gap < 0.1  # 0.1 ft tolerance

    @property
    def entry_point(self) -> Point:
        """Entry point (and exit point for closed loop)."""
        if self.segments:
            return self.segments[0].start
        return Point(0, 0)

    @property
    def total_length(self) -> float:
        """Total loop path length."""
        return sum(seg.length for seg in self.segments)

    @property
    def aisle_count(self) -> int:
        """Number of aisle segments."""
        return sum(1 for seg in self.segments if seg.segment_type == LoopSegmentType.AISLE)

    @property
    def connector_count(self) -> int:
        """Number of connector segments."""
        return sum(1 for seg in self.segments if seg.segment_type == LoopSegmentType.CONNECTOR)

    @property
    def total_stalls(self) -> int:
        """Total stalls across all segments."""
        return sum(len(seg.stalls) for seg in self.segments)

    def to_polyline(self) -> List[Tuple[float, float]]:
        """
        Return loop as a CLOSED polyline for rendering.
        Includes return to start point.
        """
        if not self.segments:
            return []
        polyline: List[Tuple[float, float]] = []
        for seg in self.segments:
            if not polyline:
                polyline.append((seg.start.x, seg.start.y))
            polyline.append((seg.end.x, seg.end.y))
        # Close the loop explicitly
        if self.is_closed:
            polyline.append(
                (self.segments[0].start.x, self.segments[0].start.y))
        return polyline

    def validate(self) -> List[str]:
        """
        Validate loop integrity. Returns list of errors (empty if valid).

        Checks:
        1. Loop is closed
        2. Loop is continuous (no gaps)
        3. Has at least one aisle segment
        4. All aisles have entry and exit (by construction)
        """
        errors = []

        # Check minimum segments
        if len(self.segments) < 3:
            errors.append(
                f"Loop has only {len(self.segments)} segments (need at least 3)")
            return errors

        # Check closure
        if not self.is_closed:
            first = self.segments[0]
            last = self.segments[-1]
            gap = math.sqrt(
                (first.start.x - last.end.x) ** 2 +
                (first.start.y - last.end.y) ** 2
            )
            errors.append(f"Loop is not closed (gap of {gap:.2f} ft)")

        # Check continuity between consecutive segments
        for i in range(len(self.segments) - 1):
            curr = self.segments[i]
            next_seg = self.segments[i + 1]
            gap = math.sqrt(
                (next_seg.start.x - curr.end.x) ** 2 +
                (next_seg.start.y - curr.end.y) ** 2
            )
            if gap > 0.1:
                errors.append(
                    f"Gap of {gap:.2f} ft between segment {i} and {i+1}")

        # Check has at least one aisle
        if self.aisle_count == 0:
            errors.append("Loop has no aisle segments")

        return errors

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "segment_count": len(self.segments),
            "aisle_count": self.aisle_count,
            "connector_count": self.connector_count,
            "total_length": round(self.total_length, 2),
            "total_stalls": self.total_stalls,
            "is_closed": self.is_closed,
            "entry_point": {"x": self.entry_point.x, "y": self.entry_point.y},
            "segments": [seg.to_dict() for seg in self.segments],
            "polyline": self.to_polyline(),
        }


# =============================================================================
# DEBUG GEOMETRY
# =============================================================================

@dataclass
class CirculationDebugGeometry:
    """Debug geometry for circulation visualization."""
    loop_polyline: List[Tuple[float, float]]  # Thick closed polyline
    # Direction arrows along loop
    loop_arrows: List[Tuple[Tuple[float, float], Tuple[float, float]]]
    # Stall attachment points
    stall_normals: List[Tuple[Tuple[float, float], Tuple[float, float]]]
    aisle_regions: List[List[Tuple[float, float]]]  # Aisle bounding boxes

    def to_dict(self) -> dict:
        return {
            "loop_polyline": self.loop_polyline,
            # Frontend expects aisle_arrows
            "aisle_arrows": [[list(s), list(e)] for s, e in self.loop_arrows],
            "stall_normals": [[list(s), list(e)] for s, e in self.stall_normals],
            "u_turn_arcs": [],  # Not used for closed loop
        }


# =============================================================================
# CIRCULATION LAYOUT RESULT
# =============================================================================

@dataclass
class CirculationLayoutResult:
    """Result of circulation-first layout generation."""
    loop: CirculationLoop
    stalls: List[AngledStall]
    aisles: List[AngledAisle]
    debug_geometry: Optional[CirculationDebugGeometry] = None
    validation_errors: List[str] = field(default_factory=list)
    loop_valid: bool = False  # Did loop pass validation?

    @property
    def stall_count(self) -> int:
        # Only count stalls if loop is valid
        if not self.loop_valid:
            return 0
        return len(self.stalls)

    @property
    def is_valid(self) -> bool:
        return self.loop_valid and len(self.validation_errors) == 0

    def to_dict(self) -> dict:
        result = {
            "stall_count": self.stall_count,
            "aisle_count": len(self.aisles),
            "is_valid": self.is_valid,
            "loop_valid": self.loop_valid,
            "loop": self.loop.to_dict(),
        }
        if self.debug_geometry:
            result["debug_geometry"] = self.debug_geometry.to_dict()
        if self.validation_errors:
            result["validation_errors"] = self.validation_errors
        return result


# =============================================================================
# CIRCULATION-FIRST GENERATOR — CLOSED LOOP
# =============================================================================

class CirculationFirstGenerator:
    """
    Generates parking layout from a CLOSED circulation loop.

    ALGORITHM:
    1. Generate closed rectangular loop based on zone bounds
    2. Mark which segments are AISLE (with stalls) vs CONNECTOR (no stalls)
    3. Validate loop integrity BEFORE any stall generation
    4. If loop is valid, attach stalls to AISLE segments (one side only)
    5. Build debug geometry

    LOOP SHAPE (rectangular):
    For a zone with bounds (min_x, min_y, max_x, max_y):

        [C] ←←←←←←←←←←← [AISLE 2] ←←←←←←←←←←← [C]
         ↓                                      ↑
         ↓                                      ↑
        [C]                                    [C]
         ↓                                      ↑
         ↓                                      ↑
        [C] →→→→→→→→→→→ [AISLE 1] →→→→→→→→→→→ [C]

    - Bottom AISLE: stalls below (outside of loop)
    - Top AISLE: stalls above (outside of loop)
    - Left/Right CONNECTORs: no stalls
    """

    def __init__(
        self,
        zone: Zone,
        angle: ParkingAngle,
        debug: bool = True,
    ):
        self.zone = zone
        self.angle = angle
        self.debug = debug
        self.stall_generator = StallRowGenerator(angle)

        # Geometry constants
        self.aisle_width = AISLE_WIDTHS[angle]
        self.stall_depth = self.stall_generator.compute_stall_footprint().depth_from_aisle
        self.stall_width = self.stall_generator.compute_stall_footprint().width_along_aisle
        self.end_overhang = self.stall_generator.calculate_row_end_overhang()

    def generate(self) -> CirculationLayoutResult:
        """
        Generate circulation-first layout with CLOSED loop.

        Returns CirculationLayoutResult with loop, stalls, aisles, and debug data.
        """
        if not self.zone.is_buildable():
            return self._empty_result("Zone not buildable")

        # Get buildable bounds
        min_x, min_y, max_x, max_y = self.zone.buildable_bounds
        width = max_x - min_x
        height = max_y - min_y

        print(
            f"[CIRCULATION-FIRST] Zone bounds: {width:.1f} x {height:.1f} ft")
        print(f"[CIRCULATION-FIRST] Generating CLOSED rectangular loop")

        # Step 1: Generate closed rectangular loop
        loop = self._generate_rectangular_loop(
            min_x, min_y, max_x, max_y, width, height)

        if not loop.segments:
            return self._empty_result("Could not generate circulation loop")

        # Step 2: VALIDATE LOOP BEFORE STALL GENERATION
        validation_errors = loop.validate()
        loop_valid = len(validation_errors) == 0

        print(
            f"[CIRCULATION-FIRST] Loop validation: {'PASSED' if loop_valid else 'FAILED'}")
        for error in validation_errors:
            print(f"  ERROR: {error}")

        # Step 3: Only generate stalls if loop is valid
        all_stalls: List[AngledStall] = []
        all_aisles: List[AngledAisle] = []

        if loop_valid:
            for segment in loop.segments:
                if segment.segment_type == LoopSegmentType.AISLE:
                    stalls, aisle = self._generate_segment_stalls(
                        segment, (min_x, min_y, max_x, max_y)
                    )
                    segment.stalls = stalls
                    segment.aisle = aisle
                    all_stalls.extend(stalls)
                    if aisle:
                        all_aisles.append(aisle)

        # Step 4: Build debug geometry (even if invalid, for visualization)
        debug_geom = None
        if self.debug:
            debug_geom = self._build_debug_geometry(loop, all_stalls)

        print(f"[CIRCULATION-FIRST RESULT]")
        print(f"  angle={self.angle.degrees}°")
        print(f"  loop_segments={len(loop.segments)}")
        print(f"  aisle_segments={loop.aisle_count}")
        print(f"  connector_segments={loop.connector_count}")
        print(f"  loop_closed={loop.is_closed}")
        print(f"  loop_valid={loop_valid}")
        print(f"  total_stalls={len(all_stalls) if loop_valid else 0}")

        return CirculationLayoutResult(
            loop=loop,
            stalls=all_stalls if loop_valid else [],
            aisles=all_aisles if loop_valid else [],
            debug_geometry=debug_geom,
            validation_errors=validation_errors,
            loop_valid=loop_valid,
        )

    def _generate_rectangular_loop(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
        width: float, height: float,
    ) -> CirculationLoop:
        """
        Generate a closed rectangular circulation loop.

        Loop structure (clockwise):
        - Bottom: AISLE (drive right, stalls below)
        - Right: CONNECTOR (drive up)
        - Top: AISLE (drive left, stalls above)
        - Left: CONNECTOR (drive down, returns to start)

        Insets from zone bounds:
        - Bottom aisle: inset by stall_depth (stalls need room below)
        - Top aisle: inset by stall_depth (stalls need room above)
        - Left/right connectors: inset by end_overhang

        Returns closed CirculationLoop.
        """
        segments: List[LoopSegment] = []

        # Calculate insets
        bottom_inset = self.stall_depth + self.aisle_width / 2
        top_inset = self.stall_depth + self.aisle_width / 2
        side_inset = self.end_overhang

        # Aisle Y positions
        bottom_aisle_y = min_y + bottom_inset
        top_aisle_y = max_y - top_inset

        # Check if we have enough space for loop
        min_height_needed = bottom_inset + top_inset + self.aisle_width
        if height < min_height_needed:
            print(
                f"[CIRCULATION-FIRST] Insufficient height for loop: {height:.1f} < {min_height_needed:.1f}")
            return CirculationLoop(segments=[])

        min_width_needed = 2 * side_inset + self.aisle_width
        if width < min_width_needed:
            print(
                f"[CIRCULATION-FIRST] Insufficient width for loop: {width:.1f} < {min_width_needed:.1f}")
            return CirculationLoop(segments=[])

        # Define corner points
        # Bottom-left, bottom-right, top-right, top-left
        bl = Point(min_x + side_inset, bottom_aisle_y)
        br = Point(max_x - side_inset, bottom_aisle_y)
        tr = Point(max_x - side_inset, top_aisle_y)
        tl = Point(min_x + side_inset, top_aisle_y)

        # Segment 0: Bottom AISLE (left to right)
        # Stalls attach BELOW (outside of loop) → stall_side = +1 (right when facing direction)
        # Direction is +X, normal for "below" is -Y, which is "right" relative to direction
        segments.append(LoopSegment(
            index=0,
            segment_type=LoopSegmentType.AISLE,
            start=bl,
            end=br,
            direction=(1.0, 0.0),
            stall_side=+1,  # Right of direction = below = outside
        ))

        # Segment 1: Right CONNECTOR (bottom to top)
        segments.append(LoopSegment(
            index=1,
            segment_type=LoopSegmentType.CONNECTOR,
            start=br,
            end=tr,
            direction=(0.0, 1.0),
            stall_side=0,
        ))

        # Segment 2: Top AISLE (right to left)
        # Stalls attach ABOVE (outside of loop) → stall_side = +1 (right when facing direction)
        # Direction is -X, normal for "above" is +Y, which is "right" relative to -X direction
        segments.append(LoopSegment(
            index=2,
            segment_type=LoopSegmentType.AISLE,
            start=tr,
            end=tl,
            direction=(-1.0, 0.0),
            stall_side=+1,  # Right of direction = above = outside
        ))

        # Segment 3: Left CONNECTOR (top to bottom) — closes the loop
        segments.append(LoopSegment(
            index=3,
            segment_type=LoopSegmentType.CONNECTOR,
            start=tl,
            end=bl,  # Returns to start!
            direction=(0.0, -1.0),
            stall_side=0,
        ))

        loop = CirculationLoop(segments=segments)

        print(f"[CIRCULATION-FIRST] Generated rectangular loop:")
        print(
            f"  corners: BL({bl.x:.1f},{bl.y:.1f}) BR({br.x:.1f},{br.y:.1f}) TR({tr.x:.1f},{tr.y:.1f}) TL({tl.x:.1f},{tl.y:.1f})")
        print(f"  closed={loop.is_closed}")
        print(f"  aisle_count={loop.aisle_count}")
        print(f"  connector_count={loop.connector_count}")

        return loop

    def _generate_segment_stalls(
        self,
        segment: LoopSegment,
        buildable_bounds: Tuple[float, float, float, float],
    ) -> Tuple[List[AngledStall], Optional[AngledAisle]]:
        """
        Generate stalls for an AISLE segment.

        Stalls attach to ONE side only (segment.stall_side).
        Stall orientation follows loop direction.
        """
        if segment.segment_type != LoopSegmentType.AISLE:
            return [], None

        if segment.stall_side == 0:
            return [], None

        min_x, min_y, max_x, max_y = buildable_bounds
        zone_shapely = self.zone.polygon.to_shapely()

        # Create aisle geometry
        dx, dy = segment.direction
        if dx > 0:
            circ_mode = CirculationMode.ONE_WAY_FORWARD
        elif dx < 0:
            circ_mode = CirculationMode.ONE_WAY_REVERSE
        elif dy > 0:
            circ_mode = CirculationMode.ONE_WAY_FORWARD
        else:
            circ_mode = CirculationMode.ONE_WAY_REVERSE

        aisle = AngledAisle(
            centerline=Line(segment.start, segment.end),
            width=self.aisle_width,
            circulation=circ_mode,
            angle=self.angle,
        )

        # Calculate stall positions along aisle
        stalls: List[AngledStall] = []
        aisle_length = segment.length
        stall_count = int(aisle_length / self.stall_width)

        if stall_count == 0:
            return [], aisle

        # Determine normal for stall side
        # stall_side > 0 means stalls on RIGHT of direction
        # stall_side < 0 means stalls on LEFT of direction
        if segment.stall_side > 0:
            # Right side: rotate direction 90° clockwise
            normal = (dy, -dx)
        else:
            # Left side: rotate direction 90° counter-clockwise
            normal = (-dy, dx)

        # Place stalls along aisle
        for i in range(stall_count):
            # Stall anchor position along aisle centerline
            offset_along = (i + 0.5) * self.stall_width
            center_x = segment.start.x + offset_along * dx
            center_y = segment.start.y + offset_along * dy

            # Offset to aisle edge (anchor at edge of aisle)
            edge_offset = self.aisle_width / 2
            anchor_x = center_x + edge_offset * normal[0]
            anchor_y = center_y + edge_offset * normal[1]

            anchor = Point(anchor_x, anchor_y)

            # Create stall with orientation following loop direction
            stall = self.stall_generator.create_stall(
                anchor=anchor,
                aisle_direction=segment.direction,
                direction=segment.stall_side,
            )

            # Filter stalls outside buildable bounds
            stall_bounds = stall.polygon.bounds
            if (stall_bounds[0] < min_x - 0.1 or stall_bounds[1] < min_y - 0.1 or
                    stall_bounds[2] > max_x + 0.1 or stall_bounds[3] > max_y + 0.1):
                continue

            # Filter stalls outside zone polygon
            if not zone_shapely.contains(stall.polygon.to_shapely()):
                continue

            stalls.append(stall)

        return stalls, aisle

    def _build_debug_geometry(
        self,
        loop: CirculationLoop,
        stalls: List[AngledStall],
    ) -> CirculationDebugGeometry:
        """
        Build debug geometry for visualization.

        Shows:
        - Closed loop polyline (thick orange)
        - Direction arrows along each segment (purple)
        - Stall normals (magenta)
        """
        # Closed loop polyline
        loop_polyline = loop.to_polyline()

        # Direction arrows at midpoint of each segment
        loop_arrows: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        arrow_len = 8.0

        for seg in loop.segments:
            mid_x = (seg.start.x + seg.end.x) / 2
            mid_y = (seg.start.y + seg.end.y) / 2
            dx, dy = seg.direction
            end_x = mid_x + arrow_len * dx
            end_y = mid_y + arrow_len * dy
            loop_arrows.append(((mid_x, mid_y), (end_x, end_y)))

        # Stall normals (where stalls attach)
        stall_normals: List[Tuple[Tuple[float, float],
                                  Tuple[float, float]]] = []
        normal_len = 4.0

        for stall in stalls:
            anchor = (stall.anchor.x, stall.anchor.y)
            normal = stall.aisle_normal
            end = (anchor[0] + normal_len * normal[0],
                   anchor[1] + normal_len * normal[1])
            stall_normals.append((anchor, end))

        # Aisle regions (not used, but available)
        aisle_regions: List[List[Tuple[float, float]]] = []

        return CirculationDebugGeometry(
            loop_polyline=loop_polyline,
            loop_arrows=loop_arrows,
            stall_normals=stall_normals,
            aisle_regions=aisle_regions,
        )

    def _empty_result(self, reason: str = "") -> CirculationLayoutResult:
        """Return empty result with error."""
        if reason:
            print(f"[CIRCULATION-FIRST] Empty result: {reason}")
        return CirculationLayoutResult(
            loop=CirculationLoop(segments=[]),
            stalls=[],
            aisles=[],
            debug_geometry=None,
            validation_errors=[reason] if reason else [],
            loop_valid=False,
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate_circulation_layout(
    zone: Zone,
    angle: ParkingAngle,
    debug: bool = True,
) -> CirculationLayoutResult:
    """
    Generate a circulation-first parking layout.

    Creates a CLOSED rectangular loop and generates stalls ONLY after
    the loop passes validation.

    Args:
        zone: Zone to generate layout for
        angle: Parking angle (30°, 45°, or 60°)
        debug: Include debug geometry

    Returns:
        CirculationLayoutResult
    """
    generator = CirculationFirstGenerator(zone, angle, debug)
    return generator.generate()
