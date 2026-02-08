"""
Rules Engine
============

Defines dimension rules and constraints for parking layout generation.
All values are rule-of-thumb defaults based on industry standards.

This module does NOT provide jurisdiction-specific code compliance.
All outputs are conceptual and advisory only.

Reference: NPA Parking Structures guidelines, ITE standards (informational only)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class StallType(Enum):
    """Parking stall types."""
    STANDARD = "standard"
    COMPACT = "compact"
    ADA = "ada"
    ADA_VAN = "ada_van"


class AisleDirection(Enum):
    """Drive aisle traffic direction."""
    ONE_WAY = "one_way"
    TWO_WAY = "two_way"


@dataclass
class StallDimensions:
    """Dimensions for a specific stall type (90-degree stalls only for MVP)."""
    width: float      # Stall width in feet
    length: float     # Stall length in feet (depth from aisle)

    @property
    def area(self) -> float:
        """Stall area in square feet."""
        return self.width * self.length


@dataclass
class ADAStallDimensions:
    """ADA-accessible stall dimensions including access aisle."""
    stall_width: float        # Parking stall width
    stall_length: float       # Parking stall length
    access_aisle_width: float  # Adjacent access aisle width

    @property
    def total_width(self) -> float:
        """Total width including access aisle."""
        return self.stall_width + self.access_aisle_width

    @property
    def area(self) -> float:
        """Total area including access aisle."""
        return self.total_width * self.stall_length


@dataclass
class ParkingRules:
    """
    Collection of parking dimension rules.

    All dimensions in feet. All rules are defaults that can be overridden.
    These represent typical US standards and are NOT code-compliant guarantees.
    """

    # Stall dimensions by type
    stall_standard: StallDimensions = field(
        default_factory=lambda: StallDimensions(width=9.0, length=18.0)
    )
    stall_compact: StallDimensions = field(
        default_factory=lambda: StallDimensions(width=8.0, length=16.0)
    )
    stall_ada: ADAStallDimensions = field(
        default_factory=lambda: ADAStallDimensions(
            stall_width=11.0,
            stall_length=18.0,
            access_aisle_width=5.0
        )
    )
    stall_ada_van: ADAStallDimensions = field(
        default_factory=lambda: ADAStallDimensions(
            stall_width=11.0,
            stall_length=18.0,
            access_aisle_width=8.0
        )
    )

    # Aisle widths by direction
    aisle_one_way: float = 12.0    # Minimum for 90-degree stalls
    aisle_two_way: float = 24.0    # Standard two-way drive aisle

    # Drive lane widths (end-of-row circulation)
    drive_lane_one_way: float = 12.0
    drive_lane_two_way: float = 22.0

    # Site setbacks
    setback_default: float = 5.0   # Default setback from boundary

    # End island / landscaping
    end_island_width: float = 4.0  # Minimum end island width
    end_island_frequency: int = 15  # Max stalls before end island required

    # Minimum dimensions
    min_bay_depth: float = 36.0    # Minimum for single-loaded bay
    min_aisle_length: float = 40.0  # Minimum useful aisle length

    def get_stall_dimensions(self, stall_type: StallType) -> StallDimensions:
        """Get stall dimensions for a given type."""
        if stall_type == StallType.STANDARD:
            return self.stall_standard
        elif stall_type == StallType.COMPACT:
            return self.stall_compact
        elif stall_type == StallType.ADA:
            return StallDimensions(
                width=self.stall_ada.total_width,
                length=self.stall_ada.stall_length
            )
        elif stall_type == StallType.ADA_VAN:
            return StallDimensions(
                width=self.stall_ada_van.total_width,
                length=self.stall_ada_van.stall_length
            )
        else:
            return self.stall_standard

    def get_aisle_width(self, direction: AisleDirection) -> float:
        """Get aisle width for a given traffic direction."""
        if direction == AisleDirection.ONE_WAY:
            return self.aisle_one_way
        else:
            return self.aisle_two_way

    def get_module_width(self, direction: AisleDirection, double_loaded: bool = True) -> float:
        """
        Calculate total module width (stalls + aisle).

        Double-loaded: stall + aisle + stall
        Single-loaded: stall + aisle
        """
        aisle = self.get_aisle_width(direction)
        stall_length = self.stall_standard.length

        if double_loaded:
            return stall_length + aisle + stall_length
        else:
            return stall_length + aisle

    def to_dict(self) -> Dict:
        """Serialize rules to dictionary."""
        return {
            "stall_standard": {
                "width": self.stall_standard.width,
                "length": self.stall_standard.length
            },
            "stall_compact": {
                "width": self.stall_compact.width,
                "length": self.stall_compact.length
            },
            "stall_ada": {
                "stall_width": self.stall_ada.stall_width,
                "stall_length": self.stall_ada.stall_length,
                "access_aisle_width": self.stall_ada.access_aisle_width
            },
            "aisle_one_way": self.aisle_one_way,
            "aisle_two_way": self.aisle_two_way,
            "setback_default": self.setback_default,
        }


def calculate_ada_stall_requirement(total_stalls: int) -> Dict[str, int]:
    """
    Calculate required ADA stalls based on total stall count.

    Based on 2010 ADA Standards Table 208.2 (informational only).
    This is a rule-of-thumb; actual requirements vary by jurisdiction.

    Args:
        total_stalls: Total number of parking stalls

    Returns:
        Dictionary with 'total_ada', 'standard_ada', 'van_accessible' counts
    """
    if total_stalls <= 0:
        return {"total_ada": 0, "standard_ada": 0, "van_accessible": 0}

    # ADA table lookup (simplified)
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
        # 2% of total
        total_ada = max(9, int(total_stalls * 0.02))
    else:
        # 20 + 1 per 100 over 1000
        total_ada = 20 + ((total_stalls - 1000) // 100)

    # Van accessible: 1 per 6 ADA stalls (minimum 1)
    van_accessible = max(1, (total_ada + 5) // 6)
    standard_ada = total_ada - van_accessible

    return {
        "total_ada": total_ada,
        "standard_ada": standard_ada,
        "van_accessible": van_accessible
    }


def validate_aisle_width(width: float, direction: AisleDirection, stall_angle: int = 90) -> bool:
    """
    Validate if aisle width meets minimum requirements.

    For 90-degree stalls:
    - One-way: minimum 12'
    - Two-way: minimum 22', preferred 24'

    Args:
        width: Aisle width in feet
        direction: Traffic direction
        stall_angle: Stall angle in degrees (90 for MVP)

    Returns:
        True if width meets minimum requirements
    """
    if stall_angle != 90:
        raise ValueError("MVP only supports 90-degree stalls")

    if direction == AisleDirection.ONE_WAY:
        return width >= 12.0
    else:
        return width >= 22.0


def validate_stall_dimensions(
    width: float,
    length: float,
    stall_type: StallType
) -> bool:
    """
    Validate if stall dimensions meet minimum requirements.

    Args:
        width: Stall width in feet
        length: Stall length in feet
        stall_type: Type of stall

    Returns:
        True if dimensions meet minimums
    """
    minimums = {
        StallType.STANDARD: (8.5, 17.0),
        StallType.COMPACT: (7.5, 15.0),
        StallType.ADA: (13.0, 17.0),      # Including 5' access aisle
        StallType.ADA_VAN: (16.0, 17.0),  # Including 8' access aisle
    }

    min_width, min_length = minimums.get(stall_type, (8.5, 17.0))
    return width >= min_width and length >= min_length
