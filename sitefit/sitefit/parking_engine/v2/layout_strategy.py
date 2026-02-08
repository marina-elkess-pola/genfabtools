"""
GenFabTools Parking Engine v2 — Layout Strategy System

ARCHITECTURE:
This module defines the LayoutStrategy system that encapsulates all
parking layout parameters and rules for each configuration.

Each strategy defines:
- Module depth (aisle + stalls)
- Aisle width
- Stall orientation rules
- Circulation type (one-way or two-way)
- Stall attachment rules (one-sided or double-loaded)

LAYOUT GENERATION ORDER:
1. Select strategy based on angle
2. Generate circulation graph FIRST
3. Attach stalls to circulation edges
4. VALIDATE: no stall-aisle intersections
5. Fill entire site (no early stopping)

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from enum import Enum

from sitefit.core.geometry import Point, Polygon, Line


# =============================================================================
# LAYOUT STRATEGY ENUM
# =============================================================================

class LayoutStrategy(str, Enum):
    """
    Parking layout strategy.

    Each strategy defines a complete set of rules for generating a parking layout.
    """
    PERPENDICULAR_90 = "90"  # 90° perpendicular, two-way, double-loaded
    ANGLED_60 = "60"         # 60° angled, one-way, single-sided
    ANGLED_45 = "45"         # 45° angled, one-way, single-sided

    @property
    def degrees(self) -> int:
        """Return angle in degrees."""
        return int(self.value)

    @property
    def is_angled(self) -> bool:
        """True if angled parking (not perpendicular)."""
        return self != LayoutStrategy.PERPENDICULAR_90

    @property
    def is_perpendicular(self) -> bool:
        """True if perpendicular (90°) parking."""
        return self == LayoutStrategy.PERPENDICULAR_90


# =============================================================================
# CIRCULATION TYPE
# =============================================================================

class CirculationType(str, Enum):
    """Circulation type for a strategy."""
    ONE_WAY = "ONE_WAY"
    TWO_WAY = "TWO_WAY"


# =============================================================================
# STALL ATTACHMENT MODE
# =============================================================================

class StallAttachment(str, Enum):
    """How stalls attach to aisles."""
    SINGLE_SIDED = "SINGLE_SIDED"  # Stalls on one side only
    DOUBLE_LOADED = "DOUBLE_LOADED"  # Stalls on both sides


# =============================================================================
# STRATEGY PARAMETERS — Frozen Configuration
# =============================================================================

@dataclass(frozen=True)
class StrategyParams:
    """
    Complete parameter set for a layout strategy.

    All dimensions in feet.
    """
    strategy: LayoutStrategy
    stall_width: float           # Width of stall perpendicular to orientation
    stall_depth: float           # Depth of stall along orientation
    aisle_width: float           # Aisle width
    circulation: CirculationType
    attachment: StallAttachment
    angle_radians: float         # Stall angle in radians

    @property
    def module_depth(self) -> float:
        """
        Module depth = space needed for one aisle with attached stalls.

        For single-sided: footprint_depth + aisle_width
        For double-loaded: footprint_depth + aisle_width + footprint_depth

        Uses footprint_depth_from_aisle which accounts for angled parking.
        """
        depth = self.footprint_depth_from_aisle
        if self.attachment == StallAttachment.DOUBLE_LOADED:
            return depth + self.aisle_width + depth
        else:
            return depth + self.aisle_width

    @property
    def footprint_width_along_aisle(self) -> float:
        """
        Width of stall footprint parallel to aisle.
        For angled parking: stall_width / sin(angle)
        """
        sin_angle = math.sin(self.angle_radians)
        if sin_angle < 0.01:
            return self.stall_width
        return self.stall_width / sin_angle

    @property
    def footprint_depth_from_aisle(self) -> float:
        """
        Depth of stall footprint perpendicular to aisle.
        For angled parking: stall_depth * sin(angle) + stall_width * cos(angle)
        """
        sin_angle = math.sin(self.angle_radians)
        cos_angle = math.cos(self.angle_radians)
        return self.stall_depth * sin_angle + self.stall_width * cos_angle


# =============================================================================
# STRATEGY REGISTRY — Predefined Configurations
# =============================================================================

def _create_strategy_params(strategy: LayoutStrategy) -> StrategyParams:
    """Create parameters for a strategy."""
    # Standard stall dimensions
    STALL_WIDTH = 9.0  # feet
    STALL_DEPTH = 18.0  # feet

    if strategy == LayoutStrategy.PERPENDICULAR_90:
        return StrategyParams(
            strategy=strategy,
            stall_width=STALL_WIDTH,
            stall_depth=STALL_DEPTH,
            aisle_width=24.0,  # Two-way perpendicular
            circulation=CirculationType.TWO_WAY,
            attachment=StallAttachment.DOUBLE_LOADED,
            angle_radians=math.pi / 2,  # 90°
        )
    elif strategy == LayoutStrategy.ANGLED_60:
        return StrategyParams(
            strategy=strategy,
            stall_width=STALL_WIDTH,
            stall_depth=STALL_DEPTH,
            aisle_width=14.0,  # One-way angled
            circulation=CirculationType.ONE_WAY,
            attachment=StallAttachment.SINGLE_SIDED,
            angle_radians=math.pi / 3,  # 60°
        )
    elif strategy == LayoutStrategy.ANGLED_45:
        return StrategyParams(
            strategy=strategy,
            stall_width=STALL_WIDTH,
            stall_depth=STALL_DEPTH,
            aisle_width=13.0,  # One-way angled
            circulation=CirculationType.ONE_WAY,
            attachment=StallAttachment.SINGLE_SIDED,
            angle_radians=math.pi / 4,  # 45°
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


STRATEGY_PARAMS: Dict[LayoutStrategy, StrategyParams] = {
    strategy: _create_strategy_params(strategy)
    for strategy in LayoutStrategy
}


def get_strategy_params(strategy: LayoutStrategy) -> StrategyParams:
    """Get parameters for a layout strategy."""
    return STRATEGY_PARAMS[strategy]


def get_strategy_from_angle(angle: int) -> LayoutStrategy:
    """Map angle (90, 60, 45) to LayoutStrategy."""
    if angle == 90:
        return LayoutStrategy.PERPENDICULAR_90
    elif angle == 60:
        return LayoutStrategy.ANGLED_60
    elif angle == 45:
        return LayoutStrategy.ANGLED_45
    else:
        raise ValueError(f"Unsupported angle: {angle}. Use 90, 60, or 45.")


# =============================================================================
# CIRCULATION SEGMENT
# =============================================================================

class SegmentType(str, Enum):
    """Type of circulation segment."""
    AISLE = "aisle"          # Has stalls attached
    CONNECTOR = "connector"  # Just circulation, no stalls


@dataclass
class CirculationSegment:
    """
    A segment of the circulation graph.

    Each segment is part of a connected circulation network.
    AISLE segments have stalls; CONNECTOR segments do not.
    """
    index: int
    segment_type: SegmentType
    start: Point
    end: Point
    direction: Tuple[float, float]  # Unit vector
    stall_side: int = 0  # -1=left, +1=right, 0=both or none

    @property
    def length(self) -> float:
        """Segment length in feet."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return math.sqrt(dx * dx + dy * dy)

    @property
    def centerline(self) -> Line:
        """Return segment as a Line."""
        return Line(self.start, self.end)

    def to_dict(self) -> dict:
        """Serialize segment."""
        return {
            "index": self.index,
            "type": self.segment_type.value,
            "start": {"x": self.start.x, "y": self.start.y},
            "end": {"x": self.end.x, "y": self.end.y},
            "direction": list(self.direction),
            "length": round(self.length, 2),
        }


# =============================================================================
# CIRCULATION GRAPH
# =============================================================================

@dataclass
class CirculationGraph:
    """
    Complete circulation network for a parking zone.

    This is the PRIMARY data structure. All layout derives from this.

    INVARIANTS:
    - Segments form a connected graph
    - For closed loop: last segment connects to first
    - No orphaned segments
    """
    segments: List[CirculationSegment] = field(default_factory=list)
    is_closed: bool = False

    @property
    def segment_count(self) -> int:
        """Total segments."""
        return len(self.segments)

    @property
    def aisle_count(self) -> int:
        """Number of aisle segments."""
        return sum(1 for s in self.segments if s.segment_type == SegmentType.AISLE)

    @property
    def total_length(self) -> float:
        """Total path length."""
        return sum(s.length for s in self.segments)

    def to_polyline(self) -> List[Tuple[float, float]]:
        """Return as polyline for rendering."""
        if not self.segments:
            return []
        pts: List[Tuple[float, float]] = []
        for seg in self.segments:
            if not pts:
                pts.append((seg.start.x, seg.start.y))
            pts.append((seg.end.x, seg.end.y))
        if self.is_closed and len(pts) > 1:
            pts.append(pts[0])
        return pts

    def validate(self) -> List[str]:
        """
        Validate circulation graph integrity.

        Returns list of errors (empty = valid).
        """
        errors: List[str] = []

        if len(self.segments) < 1:
            errors.append(f"Graph has no segments")
            return errors

        # Check continuity only for closed loops (serpentine)
        # For non-closed graphs (parallel independent aisles), segments don't connect
        if self.is_closed:
            for i in range(len(self.segments) - 1):
                curr = self.segments[i]
                next_seg = self.segments[i + 1]
                gap = math.sqrt(
                    (next_seg.start.x - curr.end.x) ** 2 +
                    (next_seg.start.y - curr.end.y) ** 2
                )
                if gap > 0.1:
                    errors.append(
                        f"Gap of {gap:.2f} ft between segments {i} and {i+1}")

            # Check closure
            first = self.segments[0]
            last = self.segments[-1]
            gap = math.sqrt(
                (first.start.x - last.end.x) ** 2 +
                (first.start.y - last.end.y) ** 2
            )
            if gap > 0.1:
                errors.append(
                    f"Graph marked closed but has gap of {gap:.2f} ft")

        # Must have at least one aisle
        if self.aisle_count == 0:
            errors.append("Graph has no aisle segments")

        return errors

    def to_dict(self) -> dict:
        """Serialize graph."""
        return {
            "segment_count": self.segment_count,
            "aisle_count": self.aisle_count,
            "total_length": round(self.total_length, 2),
            "is_closed": self.is_closed,
            "segments": [s.to_dict() for s in self.segments],
            "polyline": self.to_polyline(),
        }


# =============================================================================
# STALL — Generated from circulation
# =============================================================================

@dataclass
class LayoutStall:
    """
    A parking stall generated from circulation.

    Stalls are derived from circulation segments, NOT independent.
    """
    id: str
    segment_index: int          # Which segment this belongs to
    anchor: Point               # Attachment point on aisle edge
    polygon: Polygon            # Stall boundary
    angle: float                # Stall angle in degrees
    direction: Tuple[float, float]  # Stall facing direction

    def to_dict(self) -> dict:
        """Serialize stall."""
        return {
            "id": self.id,
            "segment_index": self.segment_index,
            "angle": self.angle,
            "geometry": {
                "points": [{"x": p.x, "y": p.y} for p in self.polygon.vertices]
            }
        }


# =============================================================================
# AISLE — Generated from circulation
# =============================================================================

@dataclass
class LayoutAisle:
    """
    An aisle generated from a circulation segment.

    Aisles are derived from circulation segments, NOT independent.
    """
    id: str
    segment_index: int          # Which segment this belongs to
    polygon: Polygon            # Aisle boundary
    centerline: Line            # Aisle centerline
    width: float                # Aisle width
    is_one_way: bool            # One-way traffic

    def to_dict(self) -> dict:
        """Serialize aisle."""
        return {
            "id": self.id,
            "segment_index": self.segment_index,
            "width": self.width,
            "is_one_way": self.is_one_way,
            "geometry": {
                "points": [{"x": p.x, "y": p.y} for p in self.polygon.vertices]
            },
            "centerline": {
                "start": {"x": self.centerline.start.x, "y": self.centerline.start.y},
                "end": {"x": self.centerline.end.x, "y": self.centerline.end.y},
            }
        }


# =============================================================================
# LAYOUT VALIDATION ERROR
# =============================================================================

class V2LayoutError(Exception):
    """Explicit V2 layout error — do NOT fallback to V1."""
    pass


# =============================================================================
# LAYOUT RESULT
# =============================================================================

@dataclass
class StrategyLayoutResult:
    """
    Result of strategy-based layout generation.

    Contains validation status and all generated geometry.
    """
    strategy: LayoutStrategy
    circulation: CirculationGraph
    stalls: List[LayoutStall]
    aisles: List[LayoutAisle]
    validation_errors: List[str] = field(default_factory=list)
    intersection_errors: List[str] = field(
        default_factory=list)  # Stall-aisle overlaps

    @property
    def is_valid(self) -> bool:
        """Layout is valid if no errors."""
        return len(self.validation_errors) == 0 and len(self.intersection_errors) == 0

    @property
    def stall_count(self) -> int:
        """Number of stalls (0 if invalid)."""
        if not self.is_valid:
            return 0
        return len(self.stalls)

    def to_dict(self) -> dict:
        """Serialize result."""
        return {
            "strategy": self.strategy.value,
            "is_valid": self.is_valid,
            "stall_count": self.stall_count,
            "aisle_count": len(self.aisles),
            "circulation": self.circulation.to_dict(),
            "validation_errors": self.validation_errors,
            "intersection_errors": self.intersection_errors,
        }


# =============================================================================
# CIRCULATION GENERATOR
# =============================================================================

class CirculationGenerator:
    """
    Generates circulation graph for a zone.

    This is the FIRST step in layout generation.
    Only after circulation is valid do we attach stalls.
    """

    def __init__(self, params: StrategyParams):
        self.params = params

    def generate_for_rectangular_zone(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
    ) -> CirculationGraph:
        """
        Generate circulation for a rectangular zone.

        For angled (one-way): Creates a closed loop
        For perpendicular (two-way): Creates parallel aisles
        """
        width = max_x - min_x
        height = max_y - min_y

        print(
            f"[CIRCULATION] Generating for {self.params.strategy.value}° layout")
        print(f"[CIRCULATION] Zone: {width:.1f} x {height:.1f} ft")
        print(f"[CIRCULATION] Module depth: {self.params.module_depth:.1f} ft")

        if self.params.circulation == CirculationType.ONE_WAY:
            return self._generate_closed_loop(min_x, min_y, max_x, max_y, width, height)
        else:
            return self._generate_parallel_aisles(min_x, min_y, max_x, max_y, width, height)

    def _generate_closed_loop(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
        width: float, height: float,
    ) -> CirculationGraph:
        """
        Generate closed loop circulation for one-way angled parking.

        Fills ENTIRE zone with as many aisle passes as possible.
        """
        segments: List[CirculationSegment] = []
        segment_idx = 0

        # Stall depth for edge inset
        stall_footprint_depth = self.params.footprint_depth_from_aisle
        aisle_half = self.params.aisle_width / 2
        end_overhang = self._calculate_end_overhang()

        # Calculate how many aisle passes fit
        # First aisle needs stall_depth from bottom edge
        # Each subsequent aisle needs module_depth spacing
        first_inset = stall_footprint_depth + aisle_half
        remaining_height = height - first_inset - \
            stall_footprint_depth  # Top also needs stall depth

        if remaining_height < 0:
            print(f"[CIRCULATION] Insufficient height for any aisles")
            return CirculationGraph(segments=[], is_closed=False)

        # Calculate number of complete modules
        module_depth = self.params.module_depth
        num_aisles = 1 + int(remaining_height / module_depth)

        # Cap at reasonable maximum and ensure at least 2 for a loop
        num_aisles = max(2, min(num_aisles, 50))

        print(
            f"[CIRCULATION] Generating {num_aisles} aisle segments for closed loop")

        # Generate aisle segments with serpentine pattern
        for i in range(num_aisles):
            aisle_y = min_y + first_inset + i * module_depth

            # Ensure we don't exceed top boundary
            if aisle_y + aisle_half + stall_footprint_depth > max_y:
                break

            # Serpentine: even goes right, odd goes left
            # Stalls always extend OUTWARD (toward min_y / below the aisle)
            if i % 2 == 0:
                start = Point(min_x + end_overhang, aisle_y)
                end = Point(max_x - end_overhang, aisle_y)
                direction = (1.0, 0.0)
                stall_side = +1  # Right side when facing +X = below
            else:
                start = Point(max_x - end_overhang, aisle_y)
                end = Point(min_x + end_overhang, aisle_y)
                direction = (-1.0, 0.0)
                # Left side when facing -X = below (same as even)
                stall_side = -1

            segments.append(CirculationSegment(
                index=segment_idx,
                segment_type=SegmentType.AISLE,
                start=start,
                end=end,
                direction=direction,
                stall_side=stall_side,
            ))
            segment_idx += 1

            # Add connector to next aisle (except after last)
            if i < num_aisles - 1:
                next_y = min_y + first_inset + (i + 1) * module_depth
                if i % 2 == 0:
                    # Connector on right side going up
                    conn_start = end
                    conn_end = Point(max_x - end_overhang, next_y)
                else:
                    # Connector on left side going up
                    conn_start = end
                    conn_end = Point(min_x + end_overhang, next_y)

                conn_dir = self._unit_vector(conn_start, conn_end)
                segments.append(CirculationSegment(
                    index=segment_idx,
                    segment_type=SegmentType.CONNECTOR,
                    start=conn_start,
                    end=conn_end,
                    direction=conn_dir,
                    stall_side=0,
                ))
                segment_idx += 1

        # Close the loop: connector from last aisle back to first
        if len(segments) >= 2:
            last_aisle = [s for s in segments if s.segment_type ==
                          SegmentType.AISLE][-1]
            first_aisle = segments[0]

            # Connector down one side, then across bottom
            # First vertical connector
            vert_start = last_aisle.end
            vert_end = Point(last_aisle.end.x, first_aisle.start.y)
            if abs(vert_start.y - vert_end.y) > 0.1:
                segments.append(CirculationSegment(
                    index=segment_idx,
                    segment_type=SegmentType.CONNECTOR,
                    start=vert_start,
                    end=vert_end,
                    direction=self._unit_vector(vert_start, vert_end),
                    stall_side=0,
                ))
                segment_idx += 1
                vert_start = vert_end

            # Horizontal connector to close
            if abs(vert_start.x - first_aisle.start.x) > 0.1:
                segments.append(CirculationSegment(
                    index=segment_idx,
                    segment_type=SegmentType.CONNECTOR,
                    start=vert_start,
                    end=first_aisle.start,
                    direction=self._unit_vector(vert_start, first_aisle.start),
                    stall_side=0,
                ))
                segment_idx += 1

        graph = CirculationGraph(segments=segments, is_closed=True)
        print(
            f"[CIRCULATION] Generated {len(segments)} total segments, closed={graph.is_closed}")
        return graph

    def _generate_parallel_aisles(
        self,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
        width: float, height: float,
    ) -> CirculationGraph:
        """
        Generate parallel aisles for two-way perpendicular parking.

        Fills ENTIRE zone with as many double-loaded modules as possible.
        """
        segments: List[CirculationSegment] = []
        segment_idx = 0

        stall_depth = self.params.stall_depth
        aisle_half = self.params.aisle_width / 2
        module_depth = self.params.module_depth

        # First aisle is centered at stall_depth + aisle_half from bottom
        first_aisle_y = min_y + stall_depth + aisle_half

        # Calculate how many modules fit
        remaining_height = height - stall_depth - aisle_half  # First stall row
        num_modules = 1 + int(remaining_height / module_depth)
        num_modules = max(1, min(num_modules, 50))

        print(f"[CIRCULATION] Generating {num_modules} parallel aisles")

        for i in range(num_modules):
            aisle_y = first_aisle_y + i * module_depth

            # Check bounds
            if aisle_y - aisle_half < min_y or aisle_y + aisle_half > max_y:
                if i > 0:  # Keep at least one
                    break

            start = Point(min_x, aisle_y)
            end = Point(max_x, aisle_y)

            segments.append(CirculationSegment(
                index=segment_idx,
                segment_type=SegmentType.AISLE,
                start=start,
                end=end,
                direction=(1.0, 0.0),
                stall_side=0,  # Both sides for 90°
            ))
            segment_idx += 1

        return CirculationGraph(segments=segments, is_closed=False)

    def _calculate_end_overhang(self) -> float:
        """Calculate end overhang for angled stalls."""
        cos_angle = math.cos(self.params.angle_radians)
        return self.params.stall_depth * cos_angle

    def _unit_vector(self, start: Point, end: Point) -> Tuple[float, float]:
        """Calculate unit direction vector."""
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.001:
            return (1.0, 0.0)
        return (dx / length, dy / length)


# =============================================================================
# STALL GENERATOR
# =============================================================================

class StallGenerator:
    """
    Generates stalls from circulation segments.

    Stalls are attached to aisle segments based on stall_side.
    """

    def __init__(self, params: StrategyParams):
        self.params = params

    def generate_for_segment(
        self,
        segment: CirculationSegment,
        aisle_polygon: Polygon,
        zone_polygon: Polygon,
    ) -> List[LayoutStall]:
        """
        Generate stalls for a circulation segment.

        Stalls are placed along the segment at regular intervals.
        Only stalls that fit within zone are included.
        """
        if segment.segment_type != SegmentType.AISLE:
            return []

        stalls: List[LayoutStall] = []
        stall_width_along = self.params.footprint_width_along_aisle
        stall_depth = self.params.footprint_depth_from_aisle
        aisle_half = self.params.aisle_width / 2

        # Calculate number of stalls that fit
        segment_length = segment.length
        num_stalls = int(segment_length / stall_width_along)

        if num_stalls == 0:
            return []

        dx, dy = segment.direction

        # Determine stall sides based on attachment mode
        if self.params.attachment == StallAttachment.DOUBLE_LOADED:
            sides = [-1, +1]  # Both sides
        else:
            # Single-sided: use segment's stall_side
            sides = [segment.stall_side] if segment.stall_side != 0 else [+1]

        # Convert to Shapely for geometry checks
        # aisle_polygon is a custom Polygon from sitefit.core.geometry
        aisle_shapely = aisle_polygon.to_shapely()
        # zone_polygon may be Shapely or custom
        if hasattr(zone_polygon, 'to_shapely'):
            zone_shapely = zone_polygon.to_shapely()
        else:
            zone_shapely = zone_polygon  # Already Shapely

        for side in sides:
            # Normal vector for this side
            if side > 0:
                normal = (dy, -dx)  # Right side
            else:
                normal = (-dy, dx)  # Left side

            for i in range(num_stalls):
                stall_id = f"stall-{segment.index}-{side}-{i}"

                # Position along segment
                offset = (i + 0.5) * stall_width_along
                center_x = segment.start.x + offset * dx
                center_y = segment.start.y + offset * dy

                # Anchor at aisle edge
                anchor_x = center_x + aisle_half * normal[0]
                anchor_y = center_y + aisle_half * normal[1]
                anchor = Point(anchor_x, anchor_y)

                # Generate stall polygon
                stall_poly = self._create_stall_polygon(
                    anchor, normal, dx, dy, stall_width_along, stall_depth
                )

                # Check stall is within zone
                stall_shapely = stall_poly.to_shapely()
                if not zone_shapely.contains(stall_shapely):
                    continue

                # CRITICAL: Check stall does NOT overlap aisle (touching edges OK)
                if stall_shapely.intersects(aisle_shapely):
                    intersection = stall_shapely.intersection(aisle_shapely)
                    overlap_area = intersection.area
                    if overlap_area > 0.5:  # More than 0.5 sq ft = real overlap
                        continue

                stalls.append(LayoutStall(
                    id=stall_id,
                    segment_index=segment.index,
                    anchor=anchor,
                    polygon=stall_poly,
                    angle=self.params.strategy.degrees,
                    direction=normal,
                ))

        return stalls

    def _create_stall_polygon(
        self,
        anchor: Point,
        normal: Tuple[float, float],
        aisle_dx: float,
        aisle_dy: float,
        width: float,
        depth: float,
    ) -> Polygon:
        """Create stall polygon from anchor point."""
        # Stall is width along aisle, depth perpendicular
        half_width = width / 2

        # Four corners
        # Front-left and front-right are at anchor level
        # Back-left and back-right are at anchor + depth*normal
        fl = Point(
            anchor.x - half_width * aisle_dx,
            anchor.y - half_width * aisle_dy,
        )
        fr = Point(
            anchor.x + half_width * aisle_dx,
            anchor.y + half_width * aisle_dy,
        )
        br = Point(
            fr.x + depth * normal[0],
            fr.y + depth * normal[1],
        )
        bl = Point(
            fl.x + depth * normal[0],
            fl.y + depth * normal[1],
        )

        return Polygon([fl, fr, br, bl])


# =============================================================================
# AISLE GENERATOR
# =============================================================================

class AisleGenerator:
    """
    Generates aisle polygons from circulation segments.
    """

    def __init__(self, params: StrategyParams):
        self.params = params

    def generate_for_segment(self, segment: CirculationSegment) -> Optional[LayoutAisle]:
        """Generate aisle polygon for a segment."""
        if segment.segment_type != SegmentType.AISLE:
            return None

        dx, dy = segment.direction
        half_width = self.params.aisle_width / 2

        # Normal vectors for left and right edges
        left_normal = (-dy, dx)
        right_normal = (dy, -dx)

        # Four corners of aisle
        start_left = Point(
            segment.start.x + half_width * left_normal[0],
            segment.start.y + half_width * left_normal[1],
        )
        start_right = Point(
            segment.start.x + half_width * right_normal[0],
            segment.start.y + half_width * right_normal[1],
        )
        end_right = Point(
            segment.end.x + half_width * right_normal[0],
            segment.end.y + half_width * right_normal[1],
        )
        end_left = Point(
            segment.end.x + half_width * left_normal[0],
            segment.end.y + half_width * left_normal[1],
        )

        polygon = Polygon([start_left, start_right, end_right, end_left])

        return LayoutAisle(
            id=f"aisle-{segment.index}",
            segment_index=segment.index,
            polygon=polygon,
            centerline=segment.centerline,
            width=self.params.aisle_width,
            is_one_way=self.params.circulation == CirculationType.ONE_WAY,
        )


# =============================================================================
# INTERSECTION VALIDATOR
# =============================================================================

def validate_no_intersections(
    stalls: List[LayoutStall],
    aisles: List[LayoutAisle],
) -> List[str]:
    """
    HARD validation: Check no stall intersects any aisle.

    Returns list of intersection errors.
    If non-empty, layout MUST be rejected.
    """
    errors: List[str] = []

    for aisle in aisles:
        aisle_shapely = aisle.polygon.to_shapely()

        for stall in stalls:
            stall_shapely = stall.polygon.to_shapely()

            if stall_shapely.intersects(aisle_shapely):
                intersection = stall_shapely.intersection(aisle_shapely)
                area = intersection.area
                # More than 0.5 sq ft overlap (touching edges OK)
                if area > 0.5:
                    errors.append(
                        f"Stall {stall.id} intersects aisle {aisle.id} (area={area:.2f} sq ft)"
                    )

    return errors


# =============================================================================
# STRATEGY LAYOUT GENERATOR — Main Entry Point
# =============================================================================

class StrategyLayoutGenerator:
    """
    Generates complete parking layout using a strategy.

    ALGORITHM:
    1. Get strategy parameters
    2. Generate circulation graph FIRST
    3. Validate circulation
    4. Generate aisles from circulation
    5. Generate stalls from circulation
    6. VALIDATE: no stall-aisle intersections
    7. Return result (valid or with errors)
    """

    def __init__(self, strategy: LayoutStrategy):
        self.strategy = strategy
        self.params = get_strategy_params(strategy)
        self.circ_gen = CirculationGenerator(self.params)
        self.aisle_gen = AisleGenerator(self.params)
        self.stall_gen = StallGenerator(self.params)

    def generate_for_zone(
        self,
        zone_polygon: Polygon,
        min_x: float, min_y: float,
        max_x: float, max_y: float,
    ) -> StrategyLayoutResult:
        """
        Generate layout for a rectangular zone.

        Returns StrategyLayoutResult with validation status.
        """
        print(f"\n[STRATEGY] Generating {self.strategy.value}° layout")
        print(
            f"[STRATEGY] Params: module_depth={self.params.module_depth:.1f}, aisle_width={self.params.aisle_width:.1f}")

        # Step 1: Generate circulation FIRST
        circulation = self.circ_gen.generate_for_rectangular_zone(
            min_x, min_y, max_x, max_y)

        # Step 2: Validate circulation
        circ_errors = circulation.validate()
        if circ_errors:
            print(f"[STRATEGY] Circulation validation FAILED: {circ_errors}")
            return StrategyLayoutResult(
                strategy=self.strategy,
                circulation=circulation,
                stalls=[],
                aisles=[],
                validation_errors=circ_errors,
            )

        print(
            f"[STRATEGY] Circulation valid: {circulation.segment_count} segments, {circulation.aisle_count} aisles")

        # Step 3: Generate aisles from circulation
        aisles: List[LayoutAisle] = []
        for segment in circulation.segments:
            aisle = self.aisle_gen.generate_for_segment(segment)
            if aisle:
                aisles.append(aisle)

        print(f"[STRATEGY] Generated {len(aisles)} aisle polygons")

        # Step 4: Generate stalls from circulation
        all_stalls: List[LayoutStall] = []
        for segment in circulation.segments:
            if segment.segment_type == SegmentType.AISLE:
                # Find matching aisle polygon
                aisle = next(
                    (a for a in aisles if a.segment_index == segment.index), None)
                if aisle:
                    stalls = self.stall_gen.generate_for_segment(
                        segment, aisle.polygon, zone_polygon)
                    all_stalls.extend(stalls)

        print(f"[STRATEGY] Generated {len(all_stalls)} stalls")

        # Step 5: HARD VALIDATION — no intersections
        intersection_errors = validate_no_intersections(all_stalls, aisles)
        if intersection_errors:
            print(
                f"[STRATEGY] INTERSECTION ERRORS: {len(intersection_errors)}")
            for err in intersection_errors[:5]:  # Log first 5
                print(f"  {err}")

        result = StrategyLayoutResult(
            strategy=self.strategy,
            circulation=circulation,
            stalls=all_stalls,
            aisles=aisles,
            validation_errors=[],
            intersection_errors=intersection_errors,
        )

        print(
            f"[STRATEGY] Result: valid={result.is_valid}, stalls={result.stall_count}")
        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_layout_for_angle(
    angle: int,
    zone_polygon: Polygon,
    min_x: float, min_y: float,
    max_x: float, max_y: float,
) -> StrategyLayoutResult:
    """
    Generate layout for an angle (90, 60, or 45).

    This is the main entry point from zone_orchestrator.
    """
    strategy = get_strategy_from_angle(angle)
    generator = StrategyLayoutGenerator(strategy)
    return generator.generate_for_zone(zone_polygon, min_x, min_y, max_x, max_y)
