"""
Floor Plate Module

Defines single floor outlines with area calculations and space breakdowns.

A floor plate represents one level of a building with:
- Gross area: Total floor area within exterior walls
- Net area: Usable/leasable area (after corridors, stairs, etc.)
- Efficiency: Net-to-gross ratio (typically 80-90%)

Space breakdown:
- Core: Elevators, stairs, MEP shafts
- Corridors: Common circulation
- Units/Spaces: Usable program areas
- Amenities: Common amenity spaces

This module handles:
1. Creating floor plates from polygons
2. Calculating gross and net areas
3. Tracking floor-by-floor variations
4. Supporting different floor types (ground, typical, penthouse)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

from sitefit.core.geometry import Point, Polygon, Rectangle
from sitefit.core.operations import inset


class FloorType(Enum):
    """Types of floors in a building."""
    GROUND = "ground"           # Ground floor (retail, lobby)
    TYPICAL = "typical"         # Typical residential/office floor
    PODIUM = "podium"           # Parking podium level
    AMENITY = "amenity"         # Amenity floor
    MECHANICAL = "mechanical"   # Mechanical/equipment floor
    PENTHOUSE = "penthouse"     # Penthouse level
    ROOFTOP = "rooftop"         # Rooftop amenity/equipment


@dataclass
class FloorConfig:
    """
    Configuration for floor plate calculations.

    Attributes:
        floor_to_floor_height: Floor-to-floor height in feet
        ground_floor_height: Ground floor height (often taller)
        core_area_ratio: Core area as ratio of gross (elevators, stairs, etc.)
        corridor_ratio: Corridor area as ratio of gross
        efficiency: Net-to-gross efficiency (0-1)
        wall_thickness: Exterior wall thickness
        min_unit_depth: Minimum unit depth from window
        max_unit_depth: Maximum unit depth from window
    """
    floor_to_floor_height: float = 10.0  # 10' typical residential
    ground_floor_height: float = 15.0    # 15' ground floor
    core_area_ratio: float = 0.08        # 8% core
    corridor_ratio: float = 0.07         # 7% corridors
    efficiency: float = 0.85             # 85% net-to-gross
    wall_thickness: float = 1.0          # 1' walls
    min_unit_depth: float = 25.0         # Min 25' deep units
    max_unit_depth: float = 40.0         # Max 40' deep units

    @property
    def net_ratio(self) -> float:
        """Net area ratio (1 - core - corridor)."""
        return 1.0 - self.core_area_ratio - self.corridor_ratio

    @classmethod
    def residential(cls) -> FloorConfig:
        """Typical residential configuration."""
        return cls(
            floor_to_floor_height=10.0,
            ground_floor_height=15.0,
            core_area_ratio=0.08,
            corridor_ratio=0.07,
            efficiency=0.85
        )

    @classmethod
    def office(cls) -> FloorConfig:
        """Typical office configuration."""
        return cls(
            floor_to_floor_height=13.0,
            ground_floor_height=18.0,
            core_area_ratio=0.15,
            corridor_ratio=0.05,
            efficiency=0.80
        )

    @classmethod
    def retail(cls) -> FloorConfig:
        """Retail/ground floor configuration."""
        return cls(
            floor_to_floor_height=15.0,
            ground_floor_height=15.0,
            core_area_ratio=0.05,
            corridor_ratio=0.05,
            efficiency=0.90
        )

    @classmethod
    def hotel(cls) -> FloorConfig:
        """Hotel configuration."""
        return cls(
            floor_to_floor_height=11.0,
            ground_floor_height=16.0,
            core_area_ratio=0.10,
            corridor_ratio=0.10,
            efficiency=0.80
        )


@dataclass
class FloorPlate:
    """
    A single floor of a building.

    Attributes:
        polygon: Floor outline (exterior walls)
        floor_number: Floor number (1-based, ground = 1)
        floor_type: Type of floor
        floor_height: Floor-to-floor height
        config: Floor configuration
        name: Optional floor name/label
    """
    polygon: Polygon
    floor_number: int
    floor_type: FloorType = FloorType.TYPICAL
    floor_height: float = 10.0
    config: FloorConfig = field(default_factory=FloorConfig)
    name: str = ""

    def __post_init__(self):
        if self.floor_number < 1:
            raise ValueError("Floor number must be 1 or greater")
        if self.floor_height <= 0:
            raise ValueError("Floor height must be positive")

    @property
    def gross_area(self) -> float:
        """Gross floor area (total area within exterior walls)."""
        return self.polygon.area

    @property
    def net_area(self) -> float:
        """Net floor area (usable/leasable area)."""
        return self.gross_area * self.config.efficiency

    @property
    def core_area(self) -> float:
        """Core area (elevators, stairs, mechanical shafts)."""
        return self.gross_area * self.config.core_area_ratio

    @property
    def corridor_area(self) -> float:
        """Corridor/circulation area."""
        return self.gross_area * self.config.corridor_ratio

    @property
    def efficiency(self) -> float:
        """Net-to-gross efficiency ratio."""
        return self.config.efficiency

    @property
    def perimeter(self) -> float:
        """Floor plate perimeter."""
        return self.polygon.perimeter

    @property
    def centroid(self) -> Point:
        """Floor plate centroid."""
        return self.polygon.centroid

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Bounding box (min_x, min_y, max_x, max_y)."""
        return self.polygon.bounds

    @property
    def width(self) -> float:
        """Floor plate width (x-direction)."""
        min_x, _, max_x, _ = self.bounds
        return max_x - min_x

    @property
    def depth(self) -> float:
        """Floor plate depth (y-direction)."""
        _, min_y, _, max_y = self.bounds
        return max_y - min_y

    @property
    def elevation(self) -> float:
        """Floor elevation (height above grade)."""
        if self.floor_number == 1:
            return 0.0

        # Ground floor is taller
        ground_height = self.config.ground_floor_height
        typical_height = self.config.floor_to_floor_height

        return ground_height + (self.floor_number - 2) * typical_height

    @property
    def is_ground_floor(self) -> bool:
        """Whether this is the ground floor."""
        return self.floor_number == 1 or self.floor_type == FloorType.GROUND

    def get_usable_polygon(self) -> Optional[Polygon]:
        """
        Get the usable area polygon (inset by wall thickness).

        Returns:
            Usable area polygon, or None if too small
        """
        result = inset(self.polygon, self.config.wall_thickness)
        if result:
            return max(result, key=lambda p: p.area)
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "floor_number": self.floor_number,
            "floor_type": self.floor_type.value,
            "floor_height": self.floor_height,
            "gross_area": round(self.gross_area, 1),
            "net_area": round(self.net_area, 1),
            "efficiency": round(self.efficiency, 3),
            "core_area": round(self.core_area, 1),
            "corridor_area": round(self.corridor_area, 1),
            "perimeter": round(self.perimeter, 1),
            "elevation": round(self.elevation, 1),
            "width": round(self.width, 1),
            "depth": round(self.depth, 1),
            "name": self.name
        }

    @classmethod
    def from_polygon(
        cls,
        polygon: Polygon,
        floor_number: int = 1,
        floor_type: FloorType = None,
        config: FloorConfig = None
    ) -> FloorPlate:
        """
        Create a floor plate from a polygon.

        Args:
            polygon: Floor outline
            floor_number: Floor number (1-based)
            floor_type: Type of floor (auto-detect if None)
            config: Floor configuration

        Returns:
            FloorPlate instance
        """
        config = config or FloorConfig()

        # Auto-detect floor type
        if floor_type is None:
            if floor_number == 1:
                floor_type = FloorType.GROUND
            else:
                floor_type = FloorType.TYPICAL

        # Set floor height based on type
        if floor_type == FloorType.GROUND:
            floor_height = config.ground_floor_height
        else:
            floor_height = config.floor_to_floor_height

        return cls(
            polygon=polygon,
            floor_number=floor_number,
            floor_type=floor_type,
            floor_height=floor_height,
            config=config
        )

    @classmethod
    def from_rectangle(
        cls,
        width: float,
        depth: float,
        floor_number: int = 1,
        origin: Point = None,
        **kwargs
    ) -> FloorPlate:
        """
        Create a rectangular floor plate.

        Args:
            width: Floor width (x-direction)
            depth: Floor depth (y-direction)
            floor_number: Floor number
            origin: Bottom-left corner (default: 0,0)

        Returns:
            FloorPlate instance
        """
        origin = origin or Point(0, 0)
        polygon = Polygon([
            origin,
            Point(origin.x + width, origin.y),
            Point(origin.x + width, origin.y + depth),
            Point(origin.x, origin.y + depth)
        ])
        return cls.from_polygon(polygon, floor_number, **kwargs)


# =============================================================================
# FLOOR PLATE CREATION FUNCTIONS
# =============================================================================

def create_floor_plate(
    polygon: Polygon,
    floor_number: int = 1,
    floor_type: FloorType = None,
    config: FloorConfig = None
) -> FloorPlate:
    """
    Create a single floor plate.

    Args:
        polygon: Floor outline
        floor_number: Floor number (1-based)
        floor_type: Type of floor
        config: Floor configuration

    Returns:
        FloorPlate instance

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (100,0), (100,80), (0,80)])
        >>> floor = create_floor_plate(site, floor_number=1)
        >>> floor.gross_area
        8000.0
    """
    return FloorPlate.from_polygon(polygon, floor_number, floor_type, config)


def create_floor_plates(
    polygons: List[Polygon],
    config: FloorConfig = None,
    ground_type: FloorType = FloorType.GROUND
) -> List[FloorPlate]:
    """
    Create multiple floor plates from a list of polygons.

    Each polygon becomes one floor, with floor 1 at index 0.

    Args:
        polygons: List of floor outlines (ground floor first)
        config: Floor configuration
        ground_type: Type for ground floor

    Returns:
        List of FloorPlate instances
    """
    floors = []
    for i, polygon in enumerate(polygons):
        floor_number = i + 1
        floor_type = ground_type if floor_number == 1 else FloorType.TYPICAL

        floor = FloorPlate.from_polygon(
            polygon,
            floor_number=floor_number,
            floor_type=floor_type,
            config=config
        )
        floors.append(floor)

    return floors


def create_uniform_floor_plates(
    polygon: Polygon,
    num_floors: int,
    config: FloorConfig = None,
    ground_type: FloorType = FloorType.GROUND
) -> List[FloorPlate]:
    """
    Create multiple identical floor plates.

    Args:
        polygon: Floor outline (same for all floors)
        num_floors: Number of floors
        config: Floor configuration
        ground_type: Type for ground floor

    Returns:
        List of FloorPlate instances
    """
    return create_floor_plates([polygon] * num_floors, config, ground_type)


# =============================================================================
# AREA CALCULATION FUNCTIONS
# =============================================================================

def calculate_gross_area(floors: List[FloorPlate]) -> float:
    """
    Calculate total gross floor area.

    Args:
        floors: List of floor plates

    Returns:
        Total gross floor area in SF

    Examples:
        >>> floors = [floor1, floor2, floor3]  # 8000 SF each
        >>> calculate_gross_area(floors)
        24000.0
    """
    return sum(f.gross_area for f in floors)


def calculate_net_area(floors: List[FloorPlate]) -> float:
    """
    Calculate total net floor area.

    Args:
        floors: List of floor plates

    Returns:
        Total net floor area in SF
    """
    return sum(f.net_area for f in floors)


def calculate_efficiency(floors: List[FloorPlate]) -> float:
    """
    Calculate overall net-to-gross efficiency.

    Args:
        floors: List of floor plates

    Returns:
        Efficiency ratio (0-1)
    """
    gross = calculate_gross_area(floors)
    if gross == 0:
        return 0.0
    return calculate_net_area(floors) / gross


def calculate_total_height(floors: List[FloorPlate]) -> float:
    """
    Calculate total building height.

    Args:
        floors: List of floor plates

    Returns:
        Total height in feet
    """
    return sum(f.floor_height for f in floors)


def calculate_floor_area_by_type(
    floors: List[FloorPlate]
) -> Dict[FloorType, float]:
    """
    Calculate gross area by floor type.

    Args:
        floors: List of floor plates

    Returns:
        Dictionary of floor type to gross area
    """
    result = {}
    for floor in floors:
        if floor.floor_type not in result:
            result[floor.floor_type] = 0.0
        result[floor.floor_type] += floor.gross_area
    return result


def get_floor_summary(floors: List[FloorPlate]) -> Dict[str, Any]:
    """
    Get summary statistics for floor plates.

    Args:
        floors: List of floor plates

    Returns:
        Summary dictionary
    """
    if not floors:
        return {"num_floors": 0, "total_gross": 0, "total_net": 0}

    gross = calculate_gross_area(floors)
    net = calculate_net_area(floors)
    height = calculate_total_height(floors)
    by_type = calculate_floor_area_by_type(floors)

    return {
        "num_floors": len(floors),
        "total_gross_sf": round(gross, 0),
        "total_net_sf": round(net, 0),
        "total_height_ft": round(height, 1),
        "efficiency": round(net / gross if gross > 0 else 0, 3),
        "avg_floor_area": round(gross / len(floors), 0),
        "ground_floor_area": round(floors[0].gross_area, 0),
        "typical_floor_area": round(floors[-1].gross_area, 0) if len(floors) > 1 else 0,
        "area_by_type": {k.value: round(v, 0) for k, v in by_type.items()}
    }


# =============================================================================
# FLOOR PLATE ANALYSIS
# =============================================================================

def check_floor_depth(
    floor: FloorPlate,
    max_depth: float = 40.0,
    check_from_perimeter: bool = True
) -> Tuple[bool, float]:
    """
    Check if floor plate depth is within acceptable range.

    For residential, units need to be within ~40' of windows.

    Args:
        floor: Floor plate to check
        max_depth: Maximum acceptable depth from perimeter
        check_from_perimeter: If True, check distance from edges

    Returns:
        Tuple of (passes, max_depth_found)
    """
    # Simple check using bounding box dimensions
    width = floor.width
    depth = floor.depth

    # The narrowest dimension determines max core distance
    min_dimension = min(width, depth)
    max_core_distance = min_dimension / 2

    passes = max_core_distance <= max_depth
    return passes, max_core_distance


def estimate_window_line(floor: FloorPlate) -> float:
    """
    Estimate the length of window line (exterior perimeter).

    Args:
        floor: Floor plate

    Returns:
        Window line length in feet
    """
    return floor.perimeter


def estimate_units_per_floor(
    floor: FloorPlate,
    avg_unit_size: float = 850,
    efficiency: float = None
) -> int:
    """
    Estimate number of units that fit on a floor.

    Args:
        floor: Floor plate
        avg_unit_size: Average unit size in SF
        efficiency: Net-to-gross efficiency (uses floor config if None)

    Returns:
        Estimated unit count
    """
    if efficiency is None:
        efficiency = floor.efficiency

    usable_area = floor.gross_area * efficiency
    return int(usable_area / avg_unit_size)
