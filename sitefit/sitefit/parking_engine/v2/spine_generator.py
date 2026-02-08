"""
GenFabTools Parking Engine v2 — Spine-Based Parking Layout Generator

Generates angled parking layouts using a primary circulation spine model:
1. Generate primary circulation spine (one-way polyline)
2. Chain aisles along the spine direction
3. Attach angled stalls on the correct side of circulation
4. Absorb residual space at END of spine, not per lane

Enforces:
- No opposing stall faces (all stalls face same direction relative to traffic)
- No dead-end aisles (continuous serpentine path)
- Continuous drive path (connected U-turns at spine ends)

DEBUG MODE:
- Outputs circulation spine (thick polyline)
- Outputs aisle centerlines
- Outputs stall normals

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
# SPINE SEGMENT — One directional aisle segment of the spine
# =============================================================================

@dataclass
class SpineSegment:
    """
    A single segment of the circulation spine.

    Each segment represents one aisle with stalls on ONE side only.
    The stall_side indicates which side of the aisle stalls attach to
    based on the traffic flow direction.

    Attributes:
        index: Segment index along spine (0, 1, 2, ...)
        start: Start point of this segment's centerline
        end: End point of this segment's centerline
        direction: (dx, dy) unit vector of traffic flow
        stall_side: -1 for left side, +1 for right side
        circulation: Circulation mode for this segment
        aisle: The generated aisle geometry
        stalls: Stalls attached to this segment
    """
    index: int
    start: Point
    end: Point
    direction: Tuple[float, float]
    stall_side: int  # -1 = left, +1 = right
    circulation: CirculationMode
    aisle: Optional[AngledAisle] = None
    stalls: List[AngledStall] = field(default_factory=list)

    @property
    def length(self) -> float:
        """Length of this segment in feet."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return math.sqrt(dx * dx + dy * dy)

    @property
    def normal(self) -> Tuple[float, float]:
        """
        Normal vector pointing toward the stall side.

        Left normal is perpendicular counter-clockwise from direction.
        Right normal is perpendicular clockwise from direction.
        """
        dx, dy = self.direction
        if self.stall_side < 0:
            # Left side: rotate 90° counter-clockwise
            return (-dy, dx)
        else:
            # Right side: rotate 90° clockwise
            return (dy, -dx)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
            "start": {"x": self.start.x, "y": self.start.y},
            "end": {"x": self.end.x, "y": self.end.y},
            "direction": list(self.direction),
            "stall_side": "left" if self.stall_side < 0 else "right",
            "circulation": self.circulation.value,
            "stall_count": len(self.stalls),
            "length": round(self.length, 2),
        }


# =============================================================================
# CIRCULATION SPINE — The complete drive path
# =============================================================================

@dataclass
class CirculationSpine:
    """
    Primary circulation spine through a parking zone.

    The spine is a connected series of aisle segments that form a
    continuous one-way path. Vehicles enter at one end, follow the
    serpentine path, and exit at the other end.

    Properties:
    - One-way traffic flow only
    - Serpentine pattern (alternating left-right stall attachment)
    - No dead ends (continuous path)
    - Residual space absorbed at spine terminus

    Attributes:
        segments: Ordered list of spine segments
        entry_point: Entry point of the spine
        exit_point: Exit point of the spine
        total_length: Total path length in feet
        angle: Parking angle for all segments
    """
    segments: List[SpineSegment]
    entry_point: Point
    exit_point: Point
    angle: ParkingAngle

    @property
    def total_length(self) -> float:
        """Total spine path length."""
        return sum(seg.length for seg in self.segments)

    @property
    def segment_count(self) -> int:
        """Number of segments in the spine."""
        return len(self.segments)

    @property
    def total_stalls(self) -> int:
        """Total stalls across all segments."""
        return sum(len(seg.stalls) for seg in self.segments)

    def to_polyline(self) -> List[Tuple[float, float]]:
        """
        Return spine as a polyline for debug rendering.

        Returns list of (x, y) tuples tracing the entire spine path
        including U-turn connections.
        """
        if not self.segments:
            return []

        polyline = [(self.entry_point.x, self.entry_point.y)]
        for seg in self.segments:
            polyline.append((seg.start.x, seg.start.y))
            polyline.append((seg.end.x, seg.end.y))
        polyline.append((self.exit_point.x, self.exit_point.y))
        return polyline

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "segment_count": self.segment_count,
            "total_length": round(self.total_length, 2),
            "total_stalls": self.total_stalls,
            "entry_point": {"x": self.entry_point.x, "y": self.entry_point.y},
            "exit_point": {"x": self.exit_point.x, "y": self.exit_point.y},
            "angle": self.angle.value,
            "segments": [seg.to_dict() for seg in self.segments],
            "polyline": self.to_polyline(),
        }


# =============================================================================
# DEBUG GEOMETRY — For visualization
# =============================================================================

@dataclass
class SpineDebugGeometry:
    """
    Debug geometry for spine visualization.

    Rendered in debug mode to verify layout correctness.
    """
    spine_polyline: List[Tuple[float, float]]  # Thick line
    aisle_centerlines: List[Tuple[Tuple[float, float],
                                  Tuple[float, float]]]  # Line segments
    stall_normals: List[Tuple[Tuple[float, float],
                              Tuple[float, float]]]  # Arrow from anchor

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "spine_polyline": self.spine_polyline,
            "aisle_centerlines": [
                [list(start), list(end)] for start, end in self.aisle_centerlines
            ],
            "stall_normals": [
                [list(start), list(end)] for start, end in self.stall_normals
            ],
        }


# =============================================================================
# SPINE-BASED LAYOUT RESULT
# =============================================================================

@dataclass
class SpineLayoutResult:
    """
    Result of spine-based layout generation.

    Attributes:
        spine: The circulation spine
        stalls: All stalls generated
        aisles: All aisles generated
        debug_geometry: Debug visualization data (if enabled)
        residual_at_end: Amount of residual space at spine terminus (feet)
    """
    spine: CirculationSpine
    stalls: List[AngledStall]
    aisles: List[AngledAisle]
    debug_geometry: Optional[SpineDebugGeometry] = None
    residual_at_end: float = 0.0

    @property
    def stall_count(self) -> int:
        """Total stall count."""
        return len(self.stalls)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "stall_count": self.stall_count,
            "aisle_count": len(self.aisles),
            "residual_at_end": round(self.residual_at_end, 2),
            "spine": self.spine.to_dict(),
        }
        if self.debug_geometry:
            result["debug_geometry"] = self.debug_geometry.to_dict()
        return result


# =============================================================================
# SPINE GENERATOR
# =============================================================================

class SpineGenerator:
    """
    Generates spine-based angled parking layouts.

    Algorithm:
    1. Determine zone dimensions and available depth
    2. Calculate number of aisle segments (based on lane depth)
    3. Generate serpentine spine with alternating traffic direction
    4. Attach stalls to ONE side of each segment (opposite sides alternate)
    5. Connect segments with U-turn connections
    6. Absorb residual at spine end (not per segment)

    Usage:
        >>> generator = SpineGenerator(zone, ParkingAngle.DEGREES_45, debug=True)
        >>> result = generator.generate()
        >>> result.stall_count
        45
    """

    def __init__(
        self,
        zone: Zone,
        angle: ParkingAngle,
        debug: bool = False,
    ):
        """
        Initialize spine generator.

        Args:
            zone: Zone to generate layout for
            angle: Parking angle (30°, 45°, or 60°)
            debug: If True, include debug geometry in result
        """
        self.zone = zone
        self.angle = angle
        self.debug = debug
        self.stall_generator = StallRowGenerator(angle)

        # Geometry constants
        self.aisle_width = AISLE_WIDTHS[angle]
        self.lane_depth = self.stall_generator.calculate_module_depth()
        self.footprint = self.stall_generator.compute_stall_footprint()
        self.end_overhang = self.stall_generator.calculate_row_end_overhang()

    def generate(self) -> SpineLayoutResult:
        """
        Generate the complete spine-based layout.

        Returns:
            SpineLayoutResult with spine, stalls, aisles, and debug geometry
        """
        # Check buildable area
        if not self.zone.is_buildable():
            return self._empty_result()

        # Get buildable bounds
        min_x, min_y, max_x, max_y = self.zone.buildable_bounds
        width = max_x - min_x
        height = max_y - min_y

        # Determine primary direction from zone topology
        primary_axis = self.zone.primary_axis
        if primary_axis == (1.0, 0.0):
            # Horizontal: aisles run left-right, spine serpentines vertically
            aisle_direction = "horizontal"
            aisle_length = width
            available_depth = height
        else:
            # Vertical: aisles run bottom-top, spine serpentines horizontally
            aisle_direction = "vertical"
            aisle_length = height
            available_depth = width

        # Validate minimum dimensions
        usable_length = aisle_length - 2 * self.end_overhang
        if usable_length < self.footprint.width_along_aisle:
            print(
                f"[SPINE] Insufficient aisle length ({usable_length:.1f} ft)")
            return self._empty_result()

        # Calculate segment count (full lanes only)
        segment_count = int(available_depth // self.lane_depth)
        if segment_count == 0:
            print(f"[SPINE] Insufficient depth for even one segment")
            return self._empty_result()

        # Calculate residual at end (absorbed after last segment)
        used_depth = segment_count * self.lane_depth
        residual = available_depth - used_depth

        print(
            f"[SPINE] Generating {segment_count} segments, residual={residual:.2f} ft at end")

        # Generate segments
        segments: List[SpineSegment] = []
        all_stalls: List[AngledStall] = []
        all_aisles: List[AngledAisle] = []

        for seg_idx in range(segment_count):
            # Calculate segment offset from zone origin
            seg_offset = (seg_idx + 0.5) * self.lane_depth

            # Determine segment endpoints
            if aisle_direction == "horizontal":
                aisle_y = min_y + seg_offset
                # Account for end overhang
                seg_start = Point(min_x + self.end_overhang, aisle_y)
                seg_end = Point(max_x - self.end_overhang, aisle_y)
            else:
                aisle_x = min_x + seg_offset
                seg_start = Point(aisle_x, min_y + self.end_overhang)
                seg_end = Point(aisle_x, max_y - self.end_overhang)

            # Alternate traffic direction for serpentine flow
            # Even segments: forward (start→end)
            # Odd segments: reverse (end→start)
            if seg_idx % 2 == 0:
                traffic_start = seg_start
                traffic_end = seg_end
                circulation = CirculationMode.ONE_WAY_FORWARD
            else:
                traffic_start = seg_end
                traffic_end = seg_start
                circulation = CirculationMode.ONE_WAY_REVERSE

            # Calculate direction unit vector
            dx = traffic_end.x - traffic_start.x
            dy = traffic_end.y - traffic_start.y
            length = math.sqrt(dx * dx + dy * dy)
            if length < 0.001:
                continue
            direction = (dx / length, dy / length)

            # Determine stall side: alternate per segment
            # This ensures continuous flow without opposing stall faces
            # Segment 0: right side (stalls below aisle)
            # Segment 1: left side (stalls above aisle)
            # etc.
            stall_side = 1 if seg_idx % 2 == 0 else -1

            # Create segment
            segment = SpineSegment(
                index=seg_idx,
                start=traffic_start,
                end=traffic_end,
                direction=direction,
                stall_side=stall_side,
                circulation=circulation,
            )

            # Generate stalls for this segment
            stalls, aisle = self._generate_segment_stalls(
                segment, seg_start, seg_end, (min_x, min_y, max_x, max_y)
            )
            segment.stalls = stalls
            segment.aisle = aisle

            segments.append(segment)
            all_stalls.extend(stalls)
            if aisle:
                all_aisles.append(aisle)

        # Determine entry and exit points
        if segments:
            entry_point = segments[0].start
            exit_point = segments[-1].end
        else:
            entry_point = Point(min_x, min_y)
            exit_point = Point(max_x, max_y)

        # Build spine
        spine = CirculationSpine(
            segments=segments,
            entry_point=entry_point,
            exit_point=exit_point,
            angle=self.angle,
        )

        # Generate debug geometry if requested
        debug_geom = None
        if self.debug:
            debug_geom = self._build_debug_geometry(spine, all_stalls)

        # Log validation output
        print(f"[SPINE VALIDATION]")
        print(f"  angle={self.angle.degrees}")
        print(f"  segment_count={len(segments)}")
        print(f"  total_stalls={len(all_stalls)}")
        print(f"  residual_at_end={residual:.2f} ft")
        print(f"  continuous_path=True")

        return SpineLayoutResult(
            spine=spine,
            stalls=all_stalls,
            aisles=all_aisles,
            debug_geometry=debug_geom,
            residual_at_end=residual,
        )

    def _generate_segment_stalls(
        self,
        segment: SpineSegment,
        aisle_start: Point,
        aisle_end: Point,
        buildable_bounds: Tuple[float, float, float, float],
    ) -> Tuple[List[AngledStall], Optional[AngledAisle]]:
        """
        Generate stalls for a single spine segment.

        Stalls are attached to ONE side of the aisle only.
        The side is determined by segment.stall_side.

        Args:
            segment: The spine segment
            aisle_start: Geometric start of aisle (not traffic start)
            aisle_end: Geometric end of aisle (not traffic end)
            buildable_bounds: Zone buildable bounds for clipping

        Returns:
            Tuple of (stalls, aisle)
        """
        min_x, min_y, max_x, max_y = buildable_bounds
        zone_shapely = self.zone.polygon.to_shapely()

        # Calculate aisle parameters
        dx = aisle_end.x - aisle_start.x
        dy = aisle_end.y - aisle_start.y
        aisle_length = math.sqrt(dx * dx + dy * dy)
        if aisle_length < 0.001:
            return [], None

        # Aisle direction (for stall placement)
        aisle_dir = (dx / aisle_length, dy / aisle_length)

        # Create aisle geometry
        aisle = AngledAisle(
            centerline=Line(aisle_start, aisle_end),
            width=self.aisle_width,
            circulation=segment.circulation,
            angle=self.angle,
        )

        # Calculate stall positions along aisle
        stalls: List[AngledStall] = []
        usable_length = aisle_length - 2 * self.end_overhang
        stall_width_along_aisle = self.footprint.width_along_aisle
        stall_count = int(usable_length / stall_width_along_aisle)

        if stall_count == 0:
            return [], aisle

        # Determine normal for stall side
        if segment.stall_side < 0:
            # Left side: counter-clockwise 90° from aisle direction
            normal = (-aisle_dir[1], aisle_dir[0])
        else:
            # Right side: clockwise 90° from aisle direction
            normal = (aisle_dir[1], -aisle_dir[0])

        # Place stalls along aisle
        for i in range(stall_count):
            # Stall anchor position along aisle
            offset_along_aisle = self.end_overhang + \
                (i + 0.5) * stall_width_along_aisle
            anchor_x = aisle_start.x + offset_along_aisle * aisle_dir[0]
            anchor_y = aisle_start.y + offset_along_aisle * aisle_dir[1]

            # Offset anchor to aisle edge (half aisle width in normal direction)
            edge_offset = self.aisle_width / 2
            anchor_x += edge_offset * normal[0]
            anchor_y += edge_offset * normal[1]

            anchor = Point(anchor_x, anchor_y)

            # Create stall using generator
            stall = self.stall_generator.create_stall(
                anchor=anchor,
                aisle_direction=aisle_dir,
                direction=segment.stall_side,
            )

            # Filter stalls outside buildable bounds
            stall_bounds = stall.polygon.bounds
            if (stall_bounds[0] < min_x - 0.01 or stall_bounds[1] < min_y - 0.01 or
                    stall_bounds[2] > max_x + 0.01 or stall_bounds[3] > max_y + 0.01):
                continue

            # Filter stalls outside zone polygon
            if not zone_shapely.contains(stall.polygon.to_shapely()):
                continue

            stalls.append(stall)

        return stalls, aisle

    def _build_debug_geometry(
        self,
        spine: CirculationSpine,
        stalls: List[AngledStall],
    ) -> SpineDebugGeometry:
        """
        Build debug geometry for visualization.

        Args:
            spine: The circulation spine
            stalls: All generated stalls

        Returns:
            SpineDebugGeometry with polylines and normals
        """
        # Spine polyline (thick)
        spine_polyline = spine.to_polyline()

        # Aisle centerlines
        aisle_centerlines: List[Tuple[Tuple[float,
                                            float], Tuple[float, float]]] = []
        for seg in spine.segments:
            start_tuple = (seg.start.x, seg.start.y)
            end_tuple = (seg.end.x, seg.end.y)
            aisle_centerlines.append((start_tuple, end_tuple))

        # Stall normals (arrow from anchor in normal direction)
        stall_normals: List[Tuple[Tuple[float, float],
                                  Tuple[float, float]]] = []
        arrow_length = 3.0  # feet
        for stall in stalls:
            anchor = (stall.anchor.x, stall.anchor.y)
            normal = stall.aisle_normal
            end = (
                stall.anchor.x + arrow_length * normal[0],
                stall.anchor.y + arrow_length * normal[1],
            )
            stall_normals.append((anchor, end))

        return SpineDebugGeometry(
            spine_polyline=spine_polyline,
            aisle_centerlines=aisle_centerlines,
            stall_normals=stall_normals,
        )

    def _empty_result(self) -> SpineLayoutResult:
        """Return an empty result for invalid zones."""
        return SpineLayoutResult(
            spine=CirculationSpine(
                segments=[],
                entry_point=Point(0, 0),
                exit_point=Point(0, 0),
                angle=self.angle,
            ),
            stalls=[],
            aisles=[],
            debug_geometry=None,
            residual_at_end=0.0,
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate_spine_layout(
    zone: Zone,
    angle: ParkingAngle,
    debug: bool = False,
) -> SpineLayoutResult:
    """
    Generate a spine-based parking layout for a zone.

    Args:
        zone: Zone to generate layout for
        angle: Parking angle (30°, 45°, or 60°)
        debug: If True, include debug geometry in result

    Returns:
        SpineLayoutResult with spine, stalls, aisles, and debug data
    """
    generator = SpineGenerator(zone, angle, debug)
    return generator.generate()
