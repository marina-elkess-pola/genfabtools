"""
Drive Aisle Definitions

Defines drive aisle widths for different configurations.
All dimensions are in feet.

Industry Standard Widths:
- Two-way traffic: 24' (most common for 90° parking)
- One-way traffic: 12-14' (angled parking typically one-way)
- Fire lane: 20' minimum (26' if no hydrant access)

Aisle widths vary by parking angle:
- 90° parking: 24' two-way, 22' one-way (need room to back out)
- 60° parking: 18' one-way
- 45° parking: 13' one-way  
- 30° parking: 11' one-way
- Parallel: 12' minimum
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

from sitefit.core.geometry import Point, Line, Polygon, Rectangle


class AisleType(Enum):
    """Types of drive aisles."""
    TWO_WAY = "two_way"
    ONE_WAY = "one_way"
    FIRE_LANE = "fire_lane"
    LOADING = "loading"
    DRIVE_THROUGH = "drive_through"


@dataclass
class DriveAisle:
    """
    A drive aisle configuration.

    Attributes:
        width: Aisle width (feet)
        aisle_type: Type of aisle (one-way, two-way, fire lane, etc.)
        parking_angle: Associated parking angle in degrees
        min_turn_radius: Minimum turn radius for vehicles (feet)

    Examples:
        >>> aisle = DriveAisle.two_way()
        >>> aisle.width
        24.0
        >>> aisle.allows_two_way_traffic
        True
    """
    width: float
    aisle_type: AisleType = AisleType.TWO_WAY
    parking_angle: float = 90.0
    min_turn_radius: float = 25.0  # Standard car turning radius

    def __post_init__(self):
        if self.width <= 0:
            raise ValueError("Width must be positive")

    @property
    def allows_two_way_traffic(self) -> bool:
        """Check if aisle allows two-way traffic."""
        return self.aisle_type == AisleType.TWO_WAY

    @property
    def is_fire_lane(self) -> bool:
        """Check if aisle is a fire lane."""
        return self.aisle_type == AisleType.FIRE_LANE

    @property
    def half_width(self) -> float:
        """Half the aisle width (distance from centerline to edge)."""
        return self.width / 2

    def to_rectangle(self, centerline: Line) -> Rectangle:
        """
        Create a rectangle representing the aisle along a centerline.

        Args:
            centerline: Line representing the center of the aisle

        Returns:
            Rectangle representing aisle footprint
        """
        # Get perpendicular offset
        nx, ny = centerline.normal
        half = self.half_width

        # Create rectangle from offset lines
        min_x = min(centerline.start.x, centerline.end.x) - abs(nx * half)
        max_x = max(centerline.start.x, centerline.end.x) + abs(nx * half)
        min_y = min(centerline.start.y, centerline.end.y) - abs(ny * half)
        max_y = max(centerline.start.y, centerline.end.y) + abs(ny * half)

        return Rectangle.from_bounds(min_x, min_y, max_x, max_y)

    def to_polygon(self, centerline: Line) -> Polygon:
        """
        Create polygon representing the aisle along a centerline.

        More accurate than rectangle for angled aisles.
        """
        # Offset the centerline in both directions
        left_line = centerline.offset(self.half_width)
        right_line = centerline.offset(-self.half_width)

        # Create polygon from the four corners
        vertices = [
            left_line.start,
            left_line.end,
            right_line.end,
            right_line.start,
        ]

        return Polygon(vertices)

    def copy(self, **overrides) -> DriveAisle:
        """Create a copy with optional overrides."""
        return DriveAisle(
            width=overrides.get('width', self.width),
            aisle_type=overrides.get('aisle_type', self.aisle_type),
            parking_angle=overrides.get('parking_angle', self.parking_angle),
            min_turn_radius=overrides.get(
                'min_turn_radius', self.min_turn_radius),
        )

    # ==========================================================================
    # Factory Methods for Common Aisle Types
    # ==========================================================================

    @classmethod
    def two_way(cls, parking_angle: float = 90) -> DriveAisle:
        """
        Create a two-way drive aisle.

        Standard 24' width for 90° parking.
        """
        return cls(width=24.0, aisle_type=AisleType.TWO_WAY, parking_angle=parking_angle)

    @classmethod
    def one_way(cls, parking_angle: float = 90) -> DriveAisle:
        """
        Create a one-way drive aisle.

        Width varies by parking angle:
        - 90°: 22' (need room to back out at angle)
        - 60°: 18'
        - 45°: 13'
        - 30°: 11'
        """
        width = cls.recommended_one_way_width(parking_angle)
        return cls(width=width, aisle_type=AisleType.ONE_WAY, parking_angle=parking_angle)

    @classmethod
    def fire_lane(cls) -> DriveAisle:
        """
        Create a fire lane (minimum 20').

        Fire lanes must be kept clear and marked.
        26' required if no fire hydrant access.
        """
        return cls(width=20.0, aisle_type=AisleType.FIRE_LANE, parking_angle=0)

    @classmethod
    def fire_lane_wide(cls) -> DriveAisle:
        """Create a wide fire lane (26') for no hydrant access."""
        return cls(width=26.0, aisle_type=AisleType.FIRE_LANE, parking_angle=0)

    @classmethod
    def loading(cls) -> DriveAisle:
        """Create a loading zone aisle (wider for trucks)."""
        return cls(width=30.0, aisle_type=AisleType.LOADING, parking_angle=0)

    @classmethod
    def drive_through(cls) -> DriveAisle:
        """Create a drive-through lane (single vehicle width)."""
        return cls(width=12.0, aisle_type=AisleType.DRIVE_THROUGH, parking_angle=0)

    @classmethod
    def for_parking_angle(cls, angle: float, two_way: bool = False) -> DriveAisle:
        """
        Create an aisle sized appropriately for the parking angle.

        Args:
            angle: Parking angle in degrees (90, 60, 45, 30, or 0)
            two_way: Whether aisle should support two-way traffic

        Returns:
            Appropriately sized DriveAisle
        """
        if two_way:
            return cls.two_way(parking_angle=angle)
        else:
            return cls.one_way(parking_angle=angle)

    @staticmethod
    def recommended_one_way_width(parking_angle: float) -> float:
        """
        Get recommended one-way aisle width for parking angle.

        Based on vehicle turning requirements.
        """
        # Interpolate for non-standard angles
        if parking_angle >= 90:
            return 22.0
        elif parking_angle >= 75:
            return 20.0
        elif parking_angle >= 60:
            return 18.0
        elif parking_angle >= 50:
            return 15.0
        elif parking_angle >= 45:
            return 13.0
        elif parking_angle >= 30:
            return 11.0
        else:
            return 12.0  # Parallel parking

    @staticmethod
    def recommended_two_way_width(parking_angle: float) -> float:
        """
        Get recommended two-way aisle width for parking angle.

        Two-way aisles are typically 24' regardless of angle.
        """
        return 24.0

    def __repr__(self) -> str:
        angle_str = f", {self.parking_angle}° parking" if self.parking_angle != 90 else ""
        return f"DriveAisle({self.aisle_type.value}, {self.width}'{angle_str})"


# =============================================================================
# PRESET CONFIGURATIONS
# =============================================================================

AISLE_PRESETS = {
    # Two-way aisles
    "two_way_90": DriveAisle.two_way(90),
    "two_way_60": DriveAisle.two_way(60),
    "two_way_45": DriveAisle.two_way(45),

    # One-way aisles (width varies by angle)
    "one_way_90": DriveAisle.one_way(90),
    "one_way_60": DriveAisle.one_way(60),
    "one_way_45": DriveAisle.one_way(45),
    "one_way_30": DriveAisle.one_way(30),

    # Special aisles
    "fire_lane": DriveAisle.fire_lane(),
    "fire_lane_wide": DriveAisle.fire_lane_wide(),
    "loading": DriveAisle.loading(),
    "drive_through": DriveAisle.drive_through(),
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def calculate_bay_width(stall_depth: float, aisle_width: float, double_loaded: bool = True) -> float:
    """
    Calculate total bay width (perpendicular to drive direction).

    A bay consists of:
    - Single-loaded: stalls on one side + aisle
    - Double-loaded: stalls on both sides + aisle

    Args:
        stall_depth: Depth of parking stall (perpendicular to aisle)
        aisle_width: Width of drive aisle
        double_loaded: Whether stalls are on both sides of aisle

    Returns:
        Total bay width in feet

    Examples:
        >>> calculate_bay_width(18, 24, double_loaded=True)
        60.0
        >>> calculate_bay_width(18, 24, double_loaded=False)
        42.0
    """
    if double_loaded:
        return stall_depth + aisle_width + stall_depth
    else:
        return stall_depth + aisle_width


def calculate_parking_module(
    stall_depth: float = 18.0,
    aisle_width: float = 24.0,
    double_loaded: bool = True
) -> dict:
    """
    Calculate a complete parking module dimensions.

    A parking module is the repeating unit in a parking layout:
    stall row + aisle + stall row (for double-loaded)

    Returns:
        Dictionary with module dimensions and metrics
    """
    bay_width = calculate_bay_width(stall_depth, aisle_width, double_loaded)

    # Standard stall width
    stall_width = 9.0

    # For a 60' wide double-loaded bay with 9' stalls:
    # Stalls per side = bay_length / stall_width
    # Total efficiency = stall_area / total_area

    return {
        "bay_width": bay_width,
        "stall_depth": stall_depth,
        "aisle_width": aisle_width,
        "double_loaded": double_loaded,
        "stalls_per_side": 1,  # Per 9' of length
        "stalls_per_module": 2 if double_loaded else 1,  # Per 9' of length
        "area_per_stall": (stall_width * bay_width) / (2 if double_loaded else 1),
    }


def minimum_aisle_width_for_angle(angle: float, vehicle_length: float = 18.0) -> float:
    """
    Calculate minimum aisle width required for parking at specific angle.

    Based on vehicle turning geometry.

    Args:
        angle: Parking angle in degrees
        vehicle_length: Length of vehicle (default 18' for standard car)

    Returns:
        Minimum aisle width in feet
    """
    if angle >= 90:
        # 90° requires most room to back out
        return 22.0
    elif angle == 0:
        # Parallel parking
        return 12.0
    else:
        # Angled parking - calculate based on swing arc
        angle_rad = math.radians(angle)
        # Simplified formula: as angle decreases, less backing room needed
        swing = vehicle_length * math.cos(angle_rad) * 0.6
        return max(11.0, swing)
