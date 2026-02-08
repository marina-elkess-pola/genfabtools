"""
Parking Stall Definitions

Defines stall dimensions for different types (standard, compact, ADA, etc.)
All dimensions are in feet.

Industry Standard Dimensions:
- Standard stall: 9' x 18' (most common)
- Compact stall: 8' x 16' (for smaller cars)
- ADA stall: 8' stall + 5' access aisle = 13' x 18' (accessible)
- ADA van: 8' stall + 8' access aisle = 16' x 18' (van accessible)
- Parallel: 8' x 22' (street parking style)

Angled parking affects effective dimensions:
- 90°: Full stall depth
- 60°: ~85% of depth
- 45°: ~71% of depth
- 30°: ~50% of depth
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, List

from sitefit.core.geometry import Point, Line, Polygon, Rectangle


class StallType(Enum):
    """Types of parking stalls."""
    STANDARD = "standard"
    COMPACT = "compact"
    ADA = "ada"
    ADA_VAN = "ada_van"
    PARALLEL = "parallel"
    MOTORCYCLE = "motorcycle"
    EV_CHARGING = "ev_charging"


@dataclass
class Stall:
    """
    A parking stall with configurable dimensions.

    Attributes:
        width: Stall width perpendicular to the drive aisle (feet)
        depth: Stall depth from aisle edge (feet)
        stall_type: Type of stall (standard, compact, ADA, etc.)
        angle: Parking angle in degrees (0=parallel, 90=perpendicular)
        access_aisle_width: Width of access aisle for ADA stalls (feet)

    Examples:
        >>> stall = Stall.standard()
        >>> stall.width
        9.0
        >>> stall.depth
        18.0
        >>> stall.area
        162.0
    """
    width: float
    depth: float
    stall_type: StallType = StallType.STANDARD
    angle: float = 90.0  # Perpendicular by default
    access_aisle_width: float = 0.0  # Only for ADA stalls

    def __post_init__(self):
        if self.width <= 0 or self.depth <= 0:
            raise ValueError("Width and depth must be positive")
        if not (0 <= self.angle <= 90):
            raise ValueError("Angle must be between 0 and 90 degrees")

    @property
    def area(self) -> float:
        """Calculate stall area in square feet."""
        return self.width * self.depth

    @property
    def total_width(self) -> float:
        """
        Total width including access aisle (for ADA stalls).

        For standard stalls, this equals width.
        For ADA stalls, this includes the striped access aisle.
        """
        return self.width + self.access_aisle_width

    @property
    def effective_depth(self) -> float:
        """
        Effective depth based on parking angle.

        At 90°, full depth is used.
        At lesser angles, cars are angled so less perpendicular depth needed.
        """
        return self.depth * math.sin(math.radians(self.angle))

    @property
    def effective_width(self) -> float:
        """
        Effective width along the drive aisle based on parking angle.

        At 90°, width equals stall width.
        At lesser angles, stalls take more aisle length.
        """
        if self.angle == 90:
            return self.width
        elif self.angle == 0:
            return self.depth  # Parallel parking
        else:
            # Angled parking: width along aisle = width/sin(angle)
            return self.width / math.sin(math.radians(self.angle))

    @property
    def is_ada(self) -> bool:
        """Check if stall is an ADA accessible stall."""
        return self.stall_type in (StallType.ADA, StallType.ADA_VAN)

    def to_rectangle(self, origin: Point = None) -> Rectangle:
        """
        Create a rectangle representing the stall footprint.

        Origin is the corner nearest the drive aisle.
        """
        if origin is None:
            origin = Point(0, 0)
        return Rectangle(origin, self.width, self.depth)

    def to_polygon(self, origin: Point = None, aisle_direction: float = 0) -> Polygon:
        """
        Create polygon representing stall at given origin and orientation.

        Args:
            origin: Bottom-left corner of stall (at drive aisle edge)
            aisle_direction: Direction of drive aisle in degrees (0 = east)

        Returns:
            Polygon representing stall footprint
        """
        if origin is None:
            origin = Point(0, 0)

        rect = self.to_rectangle(origin)
        poly = rect.to_polygon()

        # Rotate if needed
        if aisle_direction != 0:
            poly = poly.rotate(aisle_direction, origin)

        return poly

    def copy(self, **overrides) -> Stall:
        """Create a copy with optional overrides."""
        return Stall(
            width=overrides.get('width', self.width),
            depth=overrides.get('depth', self.depth),
            stall_type=overrides.get('stall_type', self.stall_type),
            angle=overrides.get('angle', self.angle),
            access_aisle_width=overrides.get(
                'access_aisle_width', self.access_aisle_width),
        )

    # ==========================================================================
    # Factory Methods for Common Stall Types
    # ==========================================================================

    @classmethod
    def standard(cls, angle: float = 90) -> Stall:
        """Create a standard parking stall (9' x 18')."""
        return cls(width=9.0, depth=18.0, stall_type=StallType.STANDARD, angle=angle)

    @classmethod
    def compact(cls, angle: float = 90) -> Stall:
        """Create a compact parking stall (8' x 16')."""
        return cls(width=8.0, depth=16.0, stall_type=StallType.COMPACT, angle=angle)

    @classmethod
    def ada(cls, angle: float = 90) -> Stall:
        """
        Create an ADA accessible stall (8' + 5' access aisle).

        Total width is 13' to accommodate wheelchair access.
        """
        return cls(
            width=8.0,
            depth=18.0,
            stall_type=StallType.ADA,
            angle=angle,
            access_aisle_width=5.0
        )

    @classmethod
    def ada_van(cls, angle: float = 90) -> Stall:
        """
        Create an ADA van-accessible stall (8' + 8' access aisle).

        Total width is 16' for van with side lift.
        """
        return cls(
            width=8.0,
            depth=18.0,
            stall_type=StallType.ADA_VAN,
            angle=angle,
            access_aisle_width=8.0
        )

    @classmethod
    def parallel(cls) -> Stall:
        """Create a parallel parking stall (8' x 22')."""
        return cls(width=8.0, depth=22.0, stall_type=StallType.PARALLEL, angle=0)

    @classmethod
    def motorcycle(cls) -> Stall:
        """Create a motorcycle parking stall (4' x 8')."""
        return cls(width=4.0, depth=8.0, stall_type=StallType.MOTORCYCLE, angle=90)

    @classmethod
    def ev_charging(cls, angle: float = 90) -> Stall:
        """Create an EV charging stall (9' x 18', same as standard)."""
        return cls(width=9.0, depth=18.0, stall_type=StallType.EV_CHARGING, angle=angle)

    @classmethod
    def from_angle(cls, angle: float, stall_type: StallType = StallType.STANDARD) -> Stall:
        """
        Create a stall configured for specific parking angle.

        Common angles: 90° (perpendicular), 60°, 45°, 30°, 0° (parallel)
        """
        if stall_type == StallType.STANDARD:
            return cls.standard(angle=angle)
        elif stall_type == StallType.COMPACT:
            return cls.compact(angle=angle)
        elif stall_type == StallType.ADA:
            return cls.ada(angle=angle)
        elif stall_type == StallType.ADA_VAN:
            return cls.ada_van(angle=angle)
        elif stall_type == StallType.PARALLEL:
            return cls.parallel()
        else:
            return cls.standard(angle=angle)

    def __repr__(self) -> str:
        angle_str = f", {self.angle}°" if self.angle != 90 else ""
        return f"Stall({self.stall_type.value}, {self.width}'x{self.depth}'{angle_str})"


# =============================================================================
# PRESET CONFIGURATIONS
# =============================================================================

STALL_PRESETS = {
    "standard_90": Stall.standard(90),
    "standard_60": Stall.standard(60),
    "standard_45": Stall.standard(45),
    "compact_90": Stall.compact(90),
    "compact_60": Stall.compact(60),
    "compact_45": Stall.compact(45),
    "ada": Stall.ada(),
    "ada_van": Stall.ada_van(),
    "parallel": Stall.parallel(),
    "motorcycle": Stall.motorcycle(),
    "ev_charging": Stall.ev_charging(),
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def calculate_stalls_per_length(length: float, stall: Stall) -> int:
    """
    Calculate how many stalls fit along a given length.

    Args:
        length: Available length along the drive aisle (feet)
        stall: Stall configuration

    Returns:
        Number of stalls that fit
    """
    if length <= 0:
        return 0
    return int(length / stall.effective_width)


def required_ada_stalls(total_stalls: int) -> Tuple[int, int]:
    """
    Calculate required ADA stalls based on total parking count.

    Returns tuple of (regular_ada, van_ada) stalls required.

    Based on 2010 ADA Standards for Accessible Design:
    - 1-25 stalls: 1 accessible
    - 26-50 stalls: 2 accessible
    - 51-75 stalls: 3 accessible
    - etc.

    At least 1 in every 6 accessible stalls must be van-accessible.
    """
    if total_stalls <= 0:
        return (0, 0)

    # Determine total accessible stalls required
    if total_stalls <= 25:
        total_ada = 1
    elif total_stalls <= 50:
        total_ada = 2
    elif total_stalls <= 75:
        total_ada = 3
    elif total_stalls <= 100:
        total_ada = 4
    elif total_stalls <= 150:
        total_ada = 5
    elif total_stalls <= 200:
        total_ada = 6
    elif total_stalls <= 300:
        total_ada = 7
    elif total_stalls <= 400:
        total_ada = 8
    elif total_stalls <= 500:
        total_ada = 9
    elif total_stalls <= 1000:
        total_ada = int(total_stalls * 0.02)  # 2%
    else:
        # 20 + 1 per 100 over 1000
        total_ada = 20 + int((total_stalls - 1000) / 100)

    # At least 1 in 6 must be van accessible (minimum 1)
    van_ada = max(1, (total_ada + 5) // 6)
    regular_ada = total_ada - van_ada

    return (regular_ada, van_ada)


def stall_dimensions_for_angle(base_stall: Stall, angle: float) -> dict:
    """
    Calculate effective dimensions for a stall at a specific angle.

    Returns dict with:
    - effective_width: Width along drive aisle
    - effective_depth: Perpendicular depth from aisle
    - stall_module: Total module depth (stall + aisle + stall for double-loaded)
    """
    angled_stall = base_stall.copy(angle=angle)

    return {
        "angle": angle,
        "effective_width": angled_stall.effective_width,
        "effective_depth": angled_stall.effective_depth,
        "base_width": base_stall.width,
        "base_depth": base_stall.depth,
    }
