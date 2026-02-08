"""
GenFabTools Parking Engine v2 — Angled Parking Geometry Module

Provides geometry calculations for angled parking stalls (30°, 45°, 60°).
Generalizes the angle-specific logic from geometry_60.py.

SUPPORTED ANGLES:
- 30°: Narrow footprint, 12' one-way aisle
- 45°: Medium footprint, 13' one-way aisle
- 60°: Wide footprint, 14' one-way aisle
- 90°: Perpendicular (for reference, uses different aisle widths)

FROZEN STALL DIMENSIONS (industry standard):
- Stall width: 9.0 ft (perpendicular to stall direction)
- Stall depth: 18.0 ft (length of stall)

Only one-way aisles are supported for angled parking.
Two-way angled parking is NOT supported.

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional, Dict

from sitefit.core.geometry import Point, Polygon, Line


# =============================================================================
# PARKING ANGLE ENUM
# =============================================================================

class ParkingAngle(str, Enum):
    """
    Supported parking angles.

    Each angle has specific geometry calculations and aisle requirements.
    """
    DEGREES_30 = "30"
    DEGREES_45 = "45"
    DEGREES_60 = "60"
    DEGREES_90 = "90"  # Perpendicular (reference only)

    @property
    def degrees(self) -> float:
        """Return angle in degrees."""
        return float(self.value)

    @property
    def radians(self) -> float:
        """Return angle in radians."""
        return math.radians(float(self.value))

    @property
    def rotation_from_perpendicular(self) -> float:
        """
        Return the rotation angle from perpendicular in degrees.

        For angled parking, stalls are rotated from perpendicular (90°).
        - 30° parking: rotation = 60° from perpendicular
        - 45° parking: rotation = 45° from perpendicular
        - 60° parking: rotation = 30° from perpendicular
        - 90° parking: rotation = 0° (no rotation)
        """
        return 90.0 - float(self.value)


# =============================================================================
# FROZEN CONSTANTS — Stall Dimensions (DO NOT MODIFY)
# =============================================================================

# Standard stall dimensions (industry standard)
STALL_WIDTH: float = 9.0   # feet, perpendicular to stall direction
STALL_DEPTH: float = 18.0  # feet, length of stall


# =============================================================================
# ANGLE-SPECIFIC AISLE WIDTHS (One-Way Only)
# =============================================================================
# Per ITE/industry standards for one-way traffic

AISLE_WIDTH_30: float = 12.0  # feet
AISLE_WIDTH_45: float = 13.0  # feet
AISLE_WIDTH_60: float = 14.0  # feet
AISLE_WIDTH_90: float = 24.0  # feet (two-way for perpendicular)

AISLE_WIDTHS: Dict[ParkingAngle, float] = {
    ParkingAngle.DEGREES_30: AISLE_WIDTH_30,
    ParkingAngle.DEGREES_45: AISLE_WIDTH_45,
    ParkingAngle.DEGREES_60: AISLE_WIDTH_60,
    ParkingAngle.DEGREES_90: AISLE_WIDTH_90,
}


# =============================================================================
# CIRCULATION MODE — Aisle Traffic Direction
# =============================================================================

class CirculationMode(str, Enum):
    """
    Aisle circulation mode.

    TWO_WAY: Bidirectional traffic (no forced direction, no arrows)
    ONE_WAY_FORWARD: Unidirectional traffic, forward along aisle centerline
    ONE_WAY_REVERSE: Unidirectional traffic, reverse along aisle centerline

    For one-way parking:
    - Aisles alternate direction row-by-row to form a valid loop
    - Stalls face the direction of travel

    For two-way parking:
    - Aisles are bidirectional (no arrows)
    - 90° perpendicular parking typically uses two-way

    For angled parking (30°, 45°, 60°):
    - One-way is strongly recommended for safety
    - Two-way is supported but not ideal for angled stalls
    """
    TWO_WAY = "TWO_WAY"
    ONE_WAY_FORWARD = "ONE_WAY_FORWARD"
    ONE_WAY_REVERSE = "ONE_WAY_REVERSE"

    @property
    def is_one_way(self) -> bool:
        """Return True if this is a one-way circulation mode."""
        return self in (CirculationMode.ONE_WAY_FORWARD, CirculationMode.ONE_WAY_REVERSE)

    @property
    def is_two_way(self) -> bool:
        """Return True if this is two-way circulation."""
        return self == CirculationMode.TWO_WAY


# =============================================================================
# STALL ROW GENERATOR
# =============================================================================

@dataclass(frozen=True)
class StallFootprint:
    """
    Calculated footprint of an angled stall on the ground.

    Attributes:
        width_along_aisle: Width of stall footprint parallel to aisle (feet)
        depth_from_aisle: Depth of stall footprint perpendicular to aisle (feet)
        angle: Parking angle (degrees)
    """
    width_along_aisle: float
    depth_from_aisle: float
    angle: float

    @property
    def area(self) -> float:
        """Area of the footprint (approximate rectangle)."""
        return self.width_along_aisle * self.depth_from_aisle


@dataclass(frozen=True)
class AngledStall:
    """
    A single angled parking stall.

    Attributes:
        anchor: Corner of the stall footprint where it meets the aisle edge
        angle: Parking angle in degrees (30, 45, 60, or 90)
        direction: 1 for left side of aisle, -1 for right side
        aisle_direction: (dx, dy) unit vector along aisle centerline
        aisle_normal: (nx, ny) unit vector pointing from aisle toward stall
        polygon: The 4-vertex polygon representing the stall footprint
    """
    anchor: Point
    angle: float
    direction: int
    aisle_direction: Tuple[float, float]
    aisle_normal: Tuple[float, float]
    polygon: Polygon = field(compare=False)

    @property
    def center(self) -> Point:
        """Return the center point of the stall."""
        return self.polygon.centroid

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "anchor": {"x": self.anchor.x, "y": self.anchor.y},
            "angle": self.angle,
            "direction": self.direction,
            "aisle_direction": list(self.aisle_direction),
            "aisle_normal": list(self.aisle_normal),
            "polygon": self.polygon.to_dicts(),
        }


class StallRowGenerator:
    """
    Generator for angled parking stall rows.

    Computes stall footprint projections, validates against setbacks,
    and generates exact polygon vertices for each stall.

    Supports 30°, 45°, and 60° angled parking with one-way aisles only.

    Usage:
        generator = StallRowGenerator(angle=ParkingAngle.DEGREES_45)
        footprint = generator.compute_stall_footprint()
        aisle_width = generator.get_aisle_width()
        stalls = generator.generate_row(aisle_edge, aisle_direction=(1, 0), direction=1)
    """

    def __init__(self, angle: ParkingAngle):
        """
        Initialize generator for a specific parking angle.

        Args:
            angle: The parking angle (30°, 45°, 60°, or 90°)
        """
        if angle == ParkingAngle.DEGREES_90:
            raise ValueError(
                "90° perpendicular parking should use the v1 engine. "
                "StallRowGenerator is for angled parking only (30°, 45°, 60°)."
            )
        self._angle = angle
        self._footprint: Optional[StallFootprint] = None

    @property
    def angle(self) -> ParkingAngle:
        """Return the parking angle."""
        return self._angle

    @property
    def stall_width(self) -> float:
        """Return the stall width (perpendicular to stall direction)."""
        return STALL_WIDTH

    @property
    def stall_depth(self) -> float:
        """Return the stall depth (length of stall)."""
        return STALL_DEPTH

    def compute_stall_footprint(self) -> StallFootprint:
        """
        Compute the actual footprint of an angled parking stall on the ground.

        For angled parking at angle θ (from aisle):
        - Footprint width (along aisle) = W*sin(θ) + D*cos(θ)
        - Footprint depth (from aisle) = W*cos(θ) + D*sin(θ)

        Where W = stall width, D = stall depth, θ = parking angle.

        Returns:
            StallFootprint with width_along_aisle and depth_from_aisle
        """
        if self._footprint is not None:
            return self._footprint

        theta = self._angle.radians
        sin_theta = math.sin(theta)
        cos_theta = math.cos(theta)

        W = STALL_WIDTH
        D = STALL_DEPTH

        # Width along aisle (projection of stall onto aisle direction)
        width_along_aisle = W * sin_theta + D * cos_theta

        # Depth from aisle (projection of stall perpendicular to aisle)
        depth_from_aisle = W * cos_theta + D * sin_theta

        self._footprint = StallFootprint(
            width_along_aisle=width_along_aisle,
            depth_from_aisle=depth_from_aisle,
            angle=self._angle.degrees,
        )
        return self._footprint

    def get_aisle_width(self) -> float:
        """
        Return the minimum aisle width for this parking angle.

        Returns:
            Aisle width in feet (one-way only)
        """
        return AISLE_WIDTHS[self._angle]

    def calculate_module_depth(self) -> float:
        """
        Calculate the total module depth for double-loaded parking.

        Module depth = stall_depth + aisle_width + stall_depth
        (for double-loaded rows with stalls on both sides)

        Returns:
            Total module depth in feet
        """
        footprint = self.compute_stall_footprint()
        aisle_width = self.get_aisle_width()
        return 2 * footprint.depth_from_aisle + aisle_width

    def calculate_row_end_overhang(self) -> float:
        """
        Calculate how far angled stalls extend past the aisle endpoint.

        For angled parking, stalls at the end of a row extend beyond the
        aisle edge due to their angle. This overhang must be subtracted
        from the usable row length on each end.

        For 45° parking: overhang = stall_depth * cos(45°) ≈ 12.73 ft
        For 30° parking: overhang = stall_depth * cos(30°) ≈ 15.59 ft
        For 60° parking: overhang = stall_depth * cos(60°) ≈ 9.0 ft

        Returns:
            Overhang distance in feet (one end)
        """
        theta = self._angle.radians
        return STALL_DEPTH * math.cos(theta)

    def calculate_usable_row_length(self, aisle_length: float) -> float:
        """
        Calculate the usable row length after accounting for end overhang.

        Angled stalls extend past the aisle endpoints. This method returns
        the actual usable length for stall placement.

        Args:
            aisle_length: Total aisle length (feet)

        Returns:
            Usable row length for stall placement (feet)
        """
        overhang = self.calculate_row_end_overhang()
        # Subtract overhang from both ends
        usable = aisle_length - 2 * overhang
        return max(0, usable)

    def calculate_stalls_per_row(self, row_length: float) -> int:
        """
        Calculate how many stalls fit in a row of given length.

        Uses deterministic floor calculation — no partial stalls.

        Args:
            row_length: Available length along the aisle (feet)

        Returns:
            Number of stalls that fit (deterministic)
        """
        footprint = self.compute_stall_footprint()
        if row_length < footprint.width_along_aisle:
            return 0
        return int(row_length // footprint.width_along_aisle)

    def validate_against_setbacks(
        self,
        stall_polygon: Polygon,
        buildable_bounds: Tuple[float, float, float, float],
    ) -> bool:
        """
        Validate that a stall polygon fits within the buildable bounds.

        Args:
            stall_polygon: The stall polygon to validate
            buildable_bounds: (min_x, min_y, max_x, max_y) of buildable area

        Returns:
            True if stall is fully within bounds, False otherwise
        """
        min_x, min_y, max_x, max_y = buildable_bounds

        for point in stall_polygon.vertices:
            if point.x < min_x or point.x > max_x:
                return False
            if point.y < min_y or point.y > max_y:
                return False
        return True

    def create_stall(
        self,
        anchor: Point,
        aisle_direction: Tuple[float, float],
        direction: int = 1,
    ) -> AngledStall:
        """
        Create an angled parking stall at the given anchor point.

        The stall is oriented to face TOWARD the aisle centerline.
        Uses explicit aisle_normal vector — does NOT infer from polygon winding.

        Args:
            anchor: The corner point where stall meets aisle edge
            aisle_direction: (dx, dy) unit vector along aisle centerline
            direction: 1 for left side of aisle, -1 for right side

        Returns:
            An AngledStall object with computed polygon facing the aisle
        """
        if direction not in (1, -1):
            raise ValueError("direction must be 1 or -1")

        W = STALL_WIDTH
        D = STALL_DEPTH

        # Compute aisle normal (perpendicular to aisle direction)
        # Left-hand perpendicular: rotate 90° counter-clockwise = (-dy, dx)
        # Right-hand perpendicular: rotate 90° clockwise = (dy, -dx)
        dx, dy = aisle_direction

        # Normal pointing outward from aisle:
        # - Left side (direction=1): normal points left (negative right-hand perp)
        # - Right side (direction=-1): normal points right (positive right-hand perp)
        #
        # For stalls to FACE the aisle, we need them to extend in the normal direction
        # Left-side stalls: extend in left normal direction (stall faces right toward aisle)
        # Right-side stalls: extend in right normal direction (stall faces left toward aisle)
        if direction == 1:
            # Left side: stall extends perpendicular-left from aisle
            aisle_normal = (-dy, dx)  # 90° CCW rotation
        else:
            # Right side: stall extends perpendicular-right from aisle
            aisle_normal = (dy, -dx)  # 90° CW rotation

        nx, ny = aisle_normal

        # Rotation angle: The parking angle determines how much the stall
        # is rotated FROM the aisle direction TOWARD the normal.
        # For 45° parking: stall_axis is 45° from aisle direction toward normal
        theta = self._angle.radians

        # Stall axis direction: blend of aisle_direction and normal based on parking angle
        # stall_axis = cos(theta) * aisle_dir + sin(theta) * normal
        # This gives the direction the CAR faces (nose pointing into stall)
        stall_axis_x = math.cos(theta) * dx + math.sin(theta) * nx
        stall_axis_y = math.cos(theta) * dy + math.sin(theta) * ny

        # Perpendicular to stall axis (for stall width direction)
        # CRITICAL: Width direction must be consistent with aisle direction
        # so that stalls are laid out along the aisle edge, not into it.
        #
        # For left stalls: width goes in +aisle_direction (left-hand perpendicular of stall_axis)
        # For right stalls: width goes in -aisle_direction (right-hand perpendicular of stall_axis)
        #
        # The issue is that a single perpendicular formula produces width that may
        # extend into the aisle for one side. We fix this by ensuring width direction
        # is consistent with the aisle edge direction (which is always along aisle_direction).
        if direction == 1:
            # Left side: width direction follows aisle direction (positive progression)
            width_dir_x = -stall_axis_y
            width_dir_y = stall_axis_x
        else:
            # Right side: width direction still follows aisle direction
            # But stall orientation is mirrored, so we flip the width perpendicular
            width_dir_x = stall_axis_y
            width_dir_y = -stall_axis_x

        # Build polygon vertices (counter-clockwise winding for positive area)
        # Start at anchor (on aisle edge), go along width, then back along depth
        #
        # Stall layout:
        #   anchor -> (anchor + W*width_dir) -> far corners -> back to anchor
        #
        corners = [
            Point(anchor.x, anchor.y),  # anchor
            Point(anchor.x + W * width_dir_x, anchor.y +
                  W * width_dir_y),  # along width
            Point(
                anchor.x + W * width_dir_x + D * stall_axis_x,
                anchor.y + W * width_dir_y + D * stall_axis_y
            ),  # far corner
            Point(anchor.x + D * stall_axis_x, anchor.y +
                  D * stall_axis_y),  # back corner
        ]

        polygon = Polygon(corners)

        return AngledStall(
            anchor=anchor,
            angle=self._angle.degrees,
            direction=direction,
            aisle_direction=aisle_direction,
            aisle_normal=aisle_normal,
            polygon=polygon,
        )

    def generate_row(
        self,
        aisle_edge: Line,
        aisle_direction: Tuple[float, float],
        direction: int = 1,
        buildable_bounds: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[AngledStall]:
        """
        Generate a row of angled stalls along an aisle edge.

        Stalls are placed deterministically from the start of the aisle edge,
        with each stall's footprint width determining spacing.

        All stalls face TOWARD the aisle centerline. The aisle_direction vector
        is used to compute the normal, ensuring consistent orientation.

        Args:
            aisle_edge: The line along which to place stalls (edge of aisle)
            aisle_direction: (dx, dy) unit vector along aisle CENTERLINE
            direction: 1 for left side of aisle, -1 for right side
            buildable_bounds: Optional (min_x, min_y, max_x, max_y) for validation

        Returns:
            List of AngledStall objects, all facing the aisle
        """
        if direction not in (1, -1):
            raise ValueError("direction must be 1 or -1")

        footprint = self.compute_stall_footprint()
        row_length = aisle_edge.length
        num_stalls = self.calculate_stalls_per_row(row_length)

        if num_stalls == 0:
            return []

        # Walk along the aisle edge (parallel to aisle_direction)
        edge_dx, edge_dy = aisle_edge.direction

        stalls = []
        for i in range(num_stalls):
            # Calculate anchor point for this stall along the edge
            offset = i * footprint.width_along_aisle
            anchor = Point(
                aisle_edge.start.x + edge_dx * offset,
                aisle_edge.start.y + edge_dy * offset,
            )

            # Pass aisle_direction (not edge direction) for normal computation
            stall = self.create_stall(anchor, aisle_direction, direction)

            # Validate against setbacks if provided
            if buildable_bounds is not None:
                if not self.validate_against_setbacks(stall.polygon, buildable_bounds):
                    # Skip stalls that violate setbacks
                    continue

            stalls.append(stall)

        return stalls


# =============================================================================
# ANGLED AISLE
# =============================================================================

@dataclass
class AngledAisle:
    """
    An aisle for angled parking.

    Attributes:
        centerline: The center line of the aisle
        width: Aisle width (determined by parking angle)
        angle: Parking angle for stalls along this aisle
        circulation: Traffic circulation mode (ONE_WAY only)
        polygon: The aisle polygon (rectangle)
    """
    centerline: Line
    width: float
    angle: ParkingAngle
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD
    polygon: Polygon = field(default=None)

    def __post_init__(self):
        if self.polygon is None:
            object.__setattr__(self, 'polygon', self._build_polygon())

    def _build_polygon(self) -> Polygon:
        """Build aisle rectangle from centerline."""
        half_width = self.width / 2

        # Get perpendicular offset points
        left_edge = self.centerline.offset(half_width)
        right_edge = self.centerline.offset(-half_width)

        # Build polygon: left edge forward, then right edge backward
        vertices = [
            left_edge.start,
            left_edge.end,
            right_edge.end,
            right_edge.start,
        ]
        return Polygon(vertices)

    @property
    def length(self) -> float:
        """Length of the aisle."""
        return self.centerline.length

    @property
    def left_edge(self) -> Line:
        """Left edge of the aisle (for stall placement)."""
        return self.centerline.offset(self.width / 2)

    @property
    def right_edge(self) -> Line:
        """Right edge of the aisle (for stall placement)."""
        return self.centerline.offset(-self.width / 2)

    @property
    def flow_direction(self) -> Optional[Tuple[float, float]]:
        """
        Return the traffic flow direction vector (normalized).

        Returns:
            (dx, dy) direction vector for one-way, None for two-way
        """
        if self.circulation == CirculationMode.TWO_WAY:
            return None  # No directional arrows for two-way
        elif self.circulation == CirculationMode.ONE_WAY_FORWARD:
            return self.centerline.direction
        else:  # ONE_WAY_REVERSE
            dx, dy = self.centerline.direction
            return (-dx, -dy)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        flow = self.flow_direction
        return {
            "centerline": {
                "start": self.centerline.start.to_dict(),
                "end": self.centerline.end.to_dict(),
            },
            "width": self.width,
            "angle": self.angle.value,
            "circulation": self.circulation.value,
            "flowDirection": list(flow) if flow else None,
            "polygon": self.polygon.to_dicts(),
        }


def create_angled_aisle(
    start: Point,
    end: Point,
    angle: ParkingAngle,
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD,
) -> AngledAisle:
    """
    Create an aisle for angled parking.

    Args:
        start: Start point of aisle centerline
        end: End point of aisle centerline
        angle: Parking angle (determines aisle width)
        circulation: Traffic circulation mode (default: ONE_WAY_FORWARD)

    Returns:
        An AngledAisle object with appropriate width for the angle
    """
    centerline = Line(start, end)
    width = AISLE_WIDTHS[angle]
    return AngledAisle(
        centerline=centerline,
        width=width,
        angle=angle,
        circulation=circulation,
    )


# =============================================================================
# DOUBLE-LOADED ROW
# =============================================================================

@dataclass
class DoubleLoadedAngledRow:
    """
    A double-loaded parking row with angled stalls on both sides.

    Attributes:
        aisle: The central one-way aisle
        left_stalls: Stalls on the left side of the aisle
        right_stalls: Stalls on the right side of the aisle
        angle: The parking angle
    """
    aisle: AngledAisle
    left_stalls: List[AngledStall]
    right_stalls: List[AngledStall]
    angle: ParkingAngle

    @property
    def total_stalls(self) -> int:
        """Total number of stalls in both rows."""
        return len(self.left_stalls) + len(self.right_stalls)

    @property
    def module_depth(self) -> float:
        """Total depth from outer edge to outer edge."""
        generator = StallRowGenerator(self.angle)
        return generator.calculate_module_depth()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "aisle": self.aisle.to_dict(),
            "left_stalls": [s.to_dict() for s in self.left_stalls],
            "right_stalls": [s.to_dict() for s in self.right_stalls],
            "total_stalls": self.total_stalls,
            "angle": self.angle.value,
        }


# =============================================================================
# LANE — Explicit Index-Based Parking Unit
# =============================================================================

@dataclass
class Lane:
    """
    A lane is the fundamental unit of parking layout.

    Each lane consists of:
    - One aisle centerline with a fixed direction
    - One left stall row (uses -normal direction)
    - One right stall row (uses +normal direction)

    Lanes are indexed sequentially (lane_0, lane_1, ...) and positioned
    at fixed perpendicular offsets from the zone origin.

    This explicit lane model ensures:
    - Deterministic stall placement
    - Consistent stall normals across the entire lane
    - No per-row direction inference
    - Architecturally legible layouts

    Attributes:
        index: Lane index (0, 1, 2, ...)
        aisle_centerline: The centerline Line of the aisle
        aisle_direction: (dx, dy) unit vector along aisle (FROZEN per lane)
        aisle_normal_left: (nx, ny) unit vector for left stalls (toward stalls)
        aisle_normal_right: (nx, ny) unit vector for right stalls (toward stalls)
        left_stalls: Stalls on left side of aisle (use aisle_normal_left)
        right_stalls: Stalls on right side of aisle (use aisle_normal_right)
        aisle: The AngledAisle object (for polygon/width)
        circulation: Traffic circulation mode for this lane
        angle: Parking angle (30°, 45°, 60°)
    """
    index: int
    aisle_centerline: Line
    aisle_direction: Tuple[float, float]
    aisle_normal_left: Tuple[float, float]
    aisle_normal_right: Tuple[float, float]
    left_stalls: List[AngledStall]
    right_stalls: List[AngledStall]
    aisle: AngledAisle
    circulation: CirculationMode
    angle: ParkingAngle

    @property
    def total_stalls(self) -> int:
        """Total number of stalls in this lane."""
        return len(self.left_stalls) + len(self.right_stalls)

    @property
    def lane_depth(self) -> float:
        """
        Depth of this lane (stall_depth + aisle_width + stall_depth).

        This is the perpendicular space consumed by one lane.
        """
        generator = StallRowGenerator(self.angle)
        return generator.calculate_module_depth()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
            "aisle_direction": list(self.aisle_direction),
            "aisle_normal_left": list(self.aisle_normal_left),
            "aisle_normal_right": list(self.aisle_normal_right),
            "left_stall_count": len(self.left_stalls),
            "right_stall_count": len(self.right_stalls),
            "total_stalls": self.total_stalls,
            "circulation": self.circulation.value,
            "angle": self.angle.value,
            "aisle": self.aisle.to_dict(),
        }


def compute_lane_count(available_depth: float, angle: ParkingAngle) -> int:
    """
    Compute the maximum number of full lanes that fit in the given depth.

    Uses floor division — no partial lanes allowed.

    Args:
        available_depth: Available perpendicular depth (feet)
        angle: Parking angle (30°, 45°, 60°)

    Returns:
        Number of complete lanes that fit
    """
    generator = StallRowGenerator(angle)
    lane_depth = generator.calculate_module_depth()

    if available_depth < lane_depth:
        return 0

    return int(available_depth // lane_depth)


def compute_lane_offset(lane_index: int, angle: ParkingAngle) -> float:
    """
    Compute the perpendicular offset from zone origin to lane centerline.

    Each lane is positioned at a fixed offset:
    offset = (lane_index + 0.5) * lane_depth

    This places the aisle centerline at the center of each lane module.

    Args:
        lane_index: Lane index (0, 1, 2, ...)
        angle: Parking angle

    Returns:
        Offset distance from zone origin (feet)
    """
    generator = StallRowGenerator(angle)
    lane_depth = generator.calculate_module_depth()
    return (lane_index + 0.5) * lane_depth


def generate_lane(
    lane_index: int,
    aisle_start: Point,
    aisle_end: Point,
    angle: ParkingAngle,
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD,
    buildable_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> Lane:
    """
    Generate a complete lane at the given index.

    A lane is generated with:
    - Fixed aisle_direction (derived from start→end, FROZEN for entire lane)
    - Left stalls using negative normal (toward left)
    - Right stalls using positive normal (toward right)

    Direction inference is NOT used. All stalls in a lane share the same
    aisle_direction vector.

    Args:
        lane_index: Lane index (0, 1, 2, ...)
        aisle_start: Start point of aisle centerline
        aisle_end: End point of aisle centerline
        angle: Parking angle (30°, 45°, 60°)
        circulation: Traffic circulation mode
        buildable_bounds: Optional (min_x, min_y, max_x, max_y) for validation

    Returns:
        A Lane object with consistent stall orientation
    """
    # Create aisle
    aisle = create_angled_aisle(aisle_start, aisle_end, angle, circulation)
    generator = StallRowGenerator(angle)

    # FROZEN aisle direction — same for ALL stalls in this lane
    aisle_direction = aisle.centerline.direction
    dx, dy = aisle_direction

    # Compute normals — perpendicular to aisle direction
    # Left normal: 90° CCW rotation = (-dy, dx)
    # Right normal: 90° CW rotation = (dy, -dx)
    aisle_normal_left = (-dy, dx)
    aisle_normal_right = (dy, -dx)

    # Generate left stalls (direction=1 → uses aisle_normal_left internally)
    left_stalls = generator.generate_row(
        aisle.left_edge,
        aisle_direction=aisle_direction,
        direction=1,  # Left side of aisle
        buildable_bounds=buildable_bounds,
    )

    # Generate right stalls (direction=-1 → uses aisle_normal_right internally)
    right_stalls = generator.generate_row(
        aisle.right_edge,
        aisle_direction=aisle_direction,
        direction=-1,  # Right side of aisle
        buildable_bounds=buildable_bounds,
    )

    return Lane(
        index=lane_index,
        aisle_centerline=aisle.centerline,
        aisle_direction=aisle_direction,
        aisle_normal_left=aisle_normal_left,
        aisle_normal_right=aisle_normal_right,
        left_stalls=left_stalls,
        right_stalls=right_stalls,
        aisle=aisle,
        circulation=circulation,
        angle=angle,
    )


def create_double_loaded_angled_row(
    aisle_start: Point,
    aisle_end: Point,
    angle: ParkingAngle,
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD,
    buildable_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> DoubleLoadedAngledRow:
    """
    Create a double-loaded row with angled stalls on both sides.

    All stalls face TOWARD the aisle centerline (required for one-way traffic).
    Orientation is derived from the aisle_direction vector, NOT from polygon winding.

    Args:
        aisle_start: Start point of aisle centerline
        aisle_end: End point of aisle centerline
        angle: Parking angle (30°, 45°, or 60°)
        circulation: Traffic circulation mode (default: ONE_WAY_FORWARD)
        buildable_bounds: Optional (min_x, min_y, max_x, max_y) for validation

    Returns:
        A DoubleLoadedAngledRow with stalls on both sides facing the aisle
    """
    aisle = create_angled_aisle(aisle_start, aisle_end, angle, circulation)
    generator = StallRowGenerator(angle)

    # Aisle direction (from start to end) — used for normal computation
    aisle_direction = aisle.centerline.direction

    # Left row: stalls on left side of aisle, facing toward aisle (direction=1)
    # Use left_edge for anchor placement, aisle_direction for orientation
    left_stalls = generator.generate_row(
        aisle.left_edge,
        aisle_direction=aisle_direction,
        direction=1,
        buildable_bounds=buildable_bounds,
    )

    # Right row: stalls on right side of aisle, facing toward aisle (direction=-1)
    # Use right_edge for anchor placement, aisle_direction for orientation
    # Note: we do NOT reverse the edge — the aisle_direction handles orientation
    right_stalls = generator.generate_row(
        aisle.right_edge,
        aisle_direction=aisle_direction,
        direction=-1,
        buildable_bounds=buildable_bounds,
    )

    return DoubleLoadedAngledRow(
        aisle=aisle,
        left_stalls=left_stalls,
        right_stalls=right_stalls,
        angle=angle,
    )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_geometry_constants(angle: ParkingAngle) -> dict:
    """
    Return geometry constants for a specific parking angle.

    Args:
        angle: The parking angle

    Returns:
        Dictionary with all dimensions for that angle
    """
    generator = StallRowGenerator(
        angle) if angle != ParkingAngle.DEGREES_90 else None

    if generator:
        footprint = generator.compute_stall_footprint()
        module_depth = generator.calculate_module_depth()
    else:
        # 90° reference values
        footprint = None
        module_depth = 2 * STALL_DEPTH + AISLE_WIDTH_90

    return {
        "stall_width": STALL_WIDTH,
        "stall_depth": STALL_DEPTH,
        "aisle_width": AISLE_WIDTHS[angle],
        "angle_degrees": angle.degrees,
        "footprint_width": footprint.width_along_aisle if footprint else STALL_WIDTH,
        "footprint_depth": footprint.depth_from_aisle if footprint else STALL_DEPTH,
        "module_depth": module_depth,
    }


def calculate_rows_in_depth(available_depth: float, angle: ParkingAngle) -> int:
    """
    Calculate how many double-loaded rows fit in a given depth.

    Uses deterministic floor calculation — no partial rows.

    Args:
        available_depth: Available depth (feet)
        angle: The parking angle

    Returns:
        Number of double-loaded rows that fit
    """
    if angle == ParkingAngle.DEGREES_90:
        module_depth = 2 * STALL_DEPTH + AISLE_WIDTH_90
    else:
        generator = StallRowGenerator(angle)
        module_depth = generator.calculate_module_depth()

    if available_depth < module_depth:
        return 0

    return int(available_depth // module_depth)
