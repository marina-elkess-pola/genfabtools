"""
GenFabTools Parking Engine v2 — 60° Angle Geometry Module

Provides geometry calculations for 60-degree angled parking stalls.
Standalone module with no dependencies on v1 or zone orchestrator.

FROZEN CONSTANTS (do not modify):
- Stall width (parallel to aisle): 10.4 ft
- Stall depth (perpendicular): 21.0 ft
- Aisle width (one-way): 14.0 ft
- Module depth (derived): ~60.77 ft (2 × stall footprint depth + aisle)
- Row spacing: MODULE_DEPTH_60 (~60.77 ft)

Constraints:
- One-way aisles only (two-way 60° not supported)
- Deterministic placement only
- No recovery logic

**GEOMETRY CONSTANTS FROZEN — DO NOT REINTRODUCE HARDCODED SPACING VALUES.**

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional

from sitefit.core.geometry import Point, Polygon, Line


# =============================================================================
# CIRCULATION MODE — Aisle Traffic Direction
# =============================================================================

class CirculationMode(str, Enum):
    """
    Aisle circulation mode.

    TWO_WAY: Bidirectional traffic (no forced direction)
    ONE_WAY_FORWARD: Unidirectional traffic, forward along aisle centerline
    ONE_WAY_REVERSE: Unidirectional traffic, reverse along aisle centerline

    Note: Circulation mode affects traffic arrows ONLY.
    Stall geometry is INDEPENDENT of circulation mode.
    Circulation must never flip, rotate, or mirror stalls.
    """
    TWO_WAY = "TWO_WAY"
    ONE_WAY_FORWARD = "ONE_WAY_FORWARD"
    ONE_WAY_REVERSE = "ONE_WAY_REVERSE"


# =============================================================================
# CONSTANTS — 60° Geometry (FROZEN — DO NOT MODIFY)
# =============================================================================

# Stall dimensions
STALL_WIDTH_60: float = 10.4  # feet, parallel to aisle
STALL_DEPTH_60: float = 21.0  # feet, perpendicular to aisle

# Aisle dimensions (one-way only)
AISLE_WIDTH_60: float = 14.0  # feet

# Module depth will be calculated after stall footprint is determined
# (stall_depth on each side + aisle in center)

# 60 degrees in radians
ANGLE_60_DEGREES: float = 60.0
ANGLE_60_RADIANS: float = math.radians(60.0)


# =============================================================================
# DERIVED CONSTANTS (calculated from base dimensions — DO NOT HARDCODE)
# =============================================================================

# For 60° parking, the stall is angled 60° from the aisle direction.
# This is equivalent to 30° from perpendicular (90° - 60° = 30°).
# The rotation angle applied to the stall rectangle is 30°.
ROTATION_ANGLE_60_DEGREES: float = 30.0  # Rotation from perpendicular
ROTATION_ANGLE_60_RADIANS: float = math.radians(30.0)


def _calculate_stall_footprint() -> Tuple[float, float]:
    """
    Calculate the actual footprint of a 60° parking stall on the ground.

    For 60° parking (stall at 60° from aisle = 30° from perpendicular):
    - Footprint width (along aisle) = W*cos(30°) + D*sin(30°)
    - Footprint depth (from aisle) = W*sin(30°) + D*cos(30°)

    Returns:
        (footprint_width, footprint_depth) in feet
    """
    sin_30 = math.sin(ROTATION_ANGLE_60_RADIANS)
    cos_30 = math.cos(ROTATION_ANGLE_60_RADIANS)

    # Width along aisle after rotation
    footprint_width = STALL_WIDTH_60 * cos_30 + STALL_DEPTH_60 * sin_30

    # Depth from aisle after rotation
    footprint_depth = STALL_WIDTH_60 * sin_30 + STALL_DEPTH_60 * cos_30

    return footprint_width, footprint_depth


# Calculated footprint values
STALL_FOOTPRINT_WIDTH_60, STALL_FOOTPRINT_DEPTH_60 = _calculate_stall_footprint()

# Module depth: double-loaded module = stall + aisle + stall
# This is the minimum spacing between module centerlines to avoid overlap
MODULE_DEPTH_60: float = 2 * STALL_FOOTPRINT_DEPTH_60 + AISLE_WIDTH_60

# Row-to-row spacing (center-to-center of parallel aisles)
# Must equal MODULE_DEPTH_60 to prevent overlapping stalls between modules
ROW_SPACING_60: float = MODULE_DEPTH_60


# =============================================================================
# STALL GEOMETRY
# =============================================================================

@dataclass(frozen=True)
class Stall60:
    """
    A single 60-degree parking stall.

    Attributes:
        anchor: Bottom-left corner of the stall footprint (on aisle edge)
        angle: Rotation angle in degrees (60 or -60 for opposite direction)
        polygon: The 4-vertex polygon representing the stall footprint
    """
    anchor: Point
    angle: float  # +60 or -60 degrees
    polygon: Polygon = field(compare=False)

    @property
    def center(self) -> Point:
        """Return the center point of the stall."""
        return self.polygon.centroid

    @property
    def area(self) -> float:
        """Return the area of the stall polygon."""
        return self.polygon.area

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "anchor": {"x": self.anchor.x, "y": self.anchor.y},
            "angle": self.angle,
            "polygon": self.polygon.to_dicts(),
        }


def create_stall_60(
    anchor: Point,
    direction: int = 1,
) -> Stall60:
    """
    Create a 60-degree parking stall at the given anchor point.

    The anchor point is the corner of the stall where it meets the aisle edge.
    Direction determines which side of the aisle:
    - direction = 1: Left side of aisle (stall extends in +Y)
    - direction = -1: Right side of aisle (stall extends in -Y)

    For one-way 60° parking, both sides angle in the same traffic direction,
    creating a herringbone pattern efficient for one-way flow.

    Args:
        anchor: The corner point where stall meets aisle
        direction: 1 for left side, -1 for right side

    Returns:
        A Stall60 object with computed polygon
    """
    if direction not in (1, -1):
        raise ValueError("direction must be 1 or -1")

    width = STALL_WIDTH_60
    depth = STALL_DEPTH_60

    # For 60° parking:
    # - Left side (direction=1): depth in +Y, rotation = +30°
    # - Right side (direction=-1): depth in -Y, rotation = -30°
    # This ensures stalls on both sides angle with traffic and don't cross aisle

    effective_depth = depth * direction
    rotation_rad = ROTATION_ANGLE_60_RADIANS * direction

    # Corners in local coordinates (counter-clockwise from anchor)
    local_corners = [
        Point(0, 0),                      # anchor on aisle edge
        Point(width, 0),                  # along aisle edge
        Point(width, effective_depth),   # far corner
        Point(0, effective_depth),       # far corner
    ]

    # Rotate around anchor
    sin_a = math.sin(rotation_rad)
    cos_a = math.cos(rotation_rad)

    rotated_corners = []
    for p in local_corners:
        rx = p.x * cos_a - p.y * sin_a
        ry = p.x * sin_a + p.y * cos_a
        rotated_corners.append(Point(anchor.x + rx, anchor.y + ry))

    polygon = Polygon(rotated_corners)

    # Store the parking angle (60°), not the rotation angle
    angle_deg = ANGLE_60_DEGREES * direction

    return Stall60(
        anchor=anchor,
        angle=angle_deg,
        polygon=polygon,
    )


# =============================================================================
# ROW GEOMETRY
# =============================================================================

@dataclass
class StallRow60:
    """
    A row of 60-degree parking stalls along an aisle edge.

    Attributes:
        stalls: List of stalls in the row
        aisle_edge: The line along which stalls are placed
        direction: 1 for right-angled, -1 for left-angled
    """
    stalls: List[Stall60]
    aisle_edge: Line
    direction: int

    @property
    def count(self) -> int:
        """Number of stalls in the row."""
        return len(self.stalls)

    @property
    def row_length(self) -> float:
        """Total length of the row (aisle edge length)."""
        return self.aisle_edge.length

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "stall_count": self.count,
            "direction": self.direction,
            "aisle_edge": {
                "start": self.aisle_edge.start.to_dict(),
                "end": self.aisle_edge.end.to_dict(),
            },
            "stalls": [s.to_dict() for s in self.stalls],
        }


def calculate_stalls_per_row(row_length: float) -> int:
    """
    Calculate how many 60° stalls fit in a row of given length.

    Uses deterministic floor calculation — no partial stalls.

    Args:
        row_length: Available length along the aisle (feet)

    Returns:
        Number of stalls that fit (deterministic)
    """
    if row_length < STALL_FOOTPRINT_WIDTH_60:
        return 0
    return int(row_length // STALL_FOOTPRINT_WIDTH_60)


def create_stall_row_60(
    aisle_edge: Line,
    direction: int = 1,
) -> StallRow60:
    """
    Create a row of 60-degree stalls along an aisle edge.

    Stalls are placed deterministically from the start of the aisle edge,
    with each stall's footprint width determining spacing.

    Args:
        aisle_edge: The line along which to place stalls
        direction: 1 for stalls angling right, -1 for angling left

    Returns:
        A StallRow60 containing all placed stalls
    """
    if direction not in (1, -1):
        raise ValueError("direction must be 1 or -1")

    row_length = aisle_edge.length
    num_stalls = calculate_stalls_per_row(row_length)

    if num_stalls == 0:
        return StallRow60(stalls=[], aisle_edge=aisle_edge, direction=direction)

    # Get direction vector along aisle
    dx, dy = aisle_edge.direction

    stalls = []
    for i in range(num_stalls):
        # Calculate anchor point for this stall
        offset = i * STALL_FOOTPRINT_WIDTH_60
        anchor = Point(
            aisle_edge.start.x + dx * offset,
            aisle_edge.start.y + dy * offset,
        )
        stall = create_stall_60(anchor, direction)
        stalls.append(stall)

    return StallRow60(stalls=stalls, aisle_edge=aisle_edge, direction=direction)


# =============================================================================
# AISLE GEOMETRY
# =============================================================================

@dataclass
class Aisle60:
    """
    An aisle for 60-degree parking with explicit circulation mode.

    Attributes:
        centerline: The center line of the aisle
        width: Aisle width (fixed at 14.0 ft for 60°)
        circulation: Traffic circulation mode (TWO_WAY, ONE_WAY_FORWARD, ONE_WAY_REVERSE)
        polygon: The aisle polygon (rectangle)

    Note: Circulation mode affects traffic arrows ONLY.
    Stall geometry is INDEPENDENT of circulation mode.
    Circulation must never flip, rotate, or mirror stalls.
    """
    centerline: Line
    width: float = AISLE_WIDTH_60
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD
    polygon: Polygon = field(default=None)

    def __post_init__(self):
        if self.polygon is None:
            # Build aisle rectangle from centerline
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
            self.polygon = Polygon(vertices)

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
            (dx, dy) for one-way, None for two-way

        Note: This is derived from centerline direction and circulation mode.
        Does NOT affect stall geometry.
        """
        if self.circulation == CirculationMode.TWO_WAY:
            return None
        elif self.circulation == CirculationMode.ONE_WAY_FORWARD:
            return self.centerline.direction
        else:  # ONE_WAY_REVERSE
            dx, dy = self.centerline.direction
            return (-dx, -dy)

    @property
    def is_one_way(self) -> bool:
        """Check if aisle has one-way circulation."""
        return self.circulation != CirculationMode.TWO_WAY

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "centerline": {
                "start": self.centerline.start.to_dict(),
                "end": self.centerline.end.to_dict(),
            },
            "width": self.width,
            "circulation": self.circulation.value,
            "flowDirection": self.flow_direction,
            "polygon": self.polygon.to_dicts(),
        }


def create_aisle_60(
    start: Point,
    end: Point,
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD,
) -> Aisle60:
    """
    Create an aisle for 60-degree parking with explicit circulation mode.

    Args:
        start: Start point of aisle centerline
        end: End point of aisle centerline
        circulation: Traffic circulation mode (default: ONE_WAY_FORWARD)

    Returns:
        An Aisle60 object with fixed width from spec and explicit circulation

    Note: Circulation mode affects traffic arrows ONLY.
    Stall geometry is INDEPENDENT of circulation mode.
    """
    centerline = Line(start, end)
    return Aisle60(centerline=centerline, circulation=circulation)


# =============================================================================
# DOUBLE-LOADED ROW GEOMETRY
# =============================================================================

@dataclass
class DoubleLoadedRow60:
    """
    A double-loaded parking row with 60-degree stalls on both sides.

    For 60° parking, this requires a one-way aisle with stalls angling
    in the same direction on both sides (creating a herringbone-like pattern).

    Attributes:
        aisle: The central one-way aisle
        left_row: Stalls on the left side of the aisle
        right_row: Stalls on the right side of the aisle
    """
    aisle: Aisle60
    left_row: StallRow60
    right_row: StallRow60

    @property
    def total_stalls(self) -> int:
        """Total number of stalls in both rows."""
        return self.left_row.count + self.right_row.count

    @property
    def total_width(self) -> float:
        """
        Total width from outer edge to outer edge.

        = stall_depth + aisle_width + stall_depth
        """
        return STALL_FOOTPRINT_DEPTH_60 + AISLE_WIDTH_60 + STALL_FOOTPRINT_DEPTH_60

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "aisle": self.aisle.to_dict(),
            "left_row": self.left_row.to_dict(),
            "right_row": self.right_row.to_dict(),
            "total_stalls": self.total_stalls,
        }


def create_double_loaded_row_60(
    aisle_start: Point,
    aisle_end: Point,
    circulation: CirculationMode = CirculationMode.ONE_WAY_FORWARD,
) -> DoubleLoadedRow60:
    """
    Create a double-loaded row with 60-degree stalls on both sides.

    Both rows angle in the same direction (required for 60° one-way traffic).

    Args:
        aisle_start: Start point of aisle centerline
        aisle_end: End point of aisle centerline
        circulation: Traffic circulation mode (default: ONE_WAY_FORWARD)

    Returns:
        A DoubleLoadedRow60 with stalls on both sides

    Note: Circulation mode affects traffic arrows ONLY.
    Stall geometry is INDEPENDENT of circulation mode.
    """
    aisle = create_aisle_60(aisle_start, aisle_end, circulation=circulation)

    # Left row: stalls angle to the right (direction = 1)
    # Their anchors are on the left edge of the aisle
    left_row = create_stall_row_60(aisle.left_edge, direction=1)

    # Right row: stalls angle to the left (direction = -1)
    # Their anchors are on the right edge of the aisle
    # Note: For the right side, we use the reversed edge so stalls face outward
    right_edge_reversed = aisle.right_edge.reversed()
    right_row = create_stall_row_60(right_edge_reversed, direction=-1)

    return DoubleLoadedRow60(
        aisle=aisle,
        left_row=left_row,
        right_row=right_row,
    )


# =============================================================================
# LAYOUT METRICS
# =============================================================================

def get_geometry_60_constants() -> dict:
    """
    Return all 60° geometry constants for reference.

    Returns:
        Dictionary with all fixed dimensions
    """
    return {
        "stall_width": STALL_WIDTH_60,
        "stall_depth": STALL_DEPTH_60,
        "aisle_width": AISLE_WIDTH_60,
        "row_spacing": ROW_SPACING_60,
        "angle_degrees": ANGLE_60_DEGREES,
        "footprint_width": STALL_FOOTPRINT_WIDTH_60,
        "footprint_depth": STALL_FOOTPRINT_DEPTH_60,
    }


def calculate_row_spacing_60() -> float:
    """
    Return the row-to-row spacing for 60° parking.

    This is a fixed value from the spec (56.0 ft).

    Returns:
        Row spacing in feet
    """
    return ROW_SPACING_60


def calculate_rows_in_depth(available_depth: float) -> int:
    """
    Calculate how many double-loaded rows fit in a given depth.

    Uses deterministic floor calculation — no partial rows.

    Args:
        available_depth: Available depth (feet)

    Returns:
        Number of double-loaded rows that fit
    """
    # First row needs full width, subsequent rows offset by row_spacing
    if available_depth < ROW_SPACING_60:
        return 0

    # First row uses ROW_SPACING_60, each additional row adds ROW_SPACING_60
    rows = int(available_depth // ROW_SPACING_60)
    return max(rows, 0)
