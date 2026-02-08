"""
Structured Parking Engine (Skeleton)
====================================

Defines the architecture for above-ground structured parking.
This module provides floor plate stacking, ramp connectivity,
and vertical circulation placeholders.

PHASE 2: Architecture only. No stall placement logic.

All outputs are conceptual and advisory.
This is NOT a structural engineering or construction tool.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum

from .geometry import Polygon, Point, offset_polygon
from .rules import ParkingRules


class RampType(Enum):
    """Ramp configuration types."""
    SINGLE_HELIX = "single_helix"
    DOUBLE_HELIX = "double_helix"
    SPEED_RAMP = "speed_ramp"
    SLOPED_FLOOR = "sloped_floor"


class CoreType(Enum):
    """Vertical circulation core types."""
    STAIR_ONLY = "stair_only"
    STAIR_ELEVATOR = "stair_elevator"
    STAIR_MULTI_ELEVATOR = "stair_multi_elevator"


@dataclass
class VerticalCore:
    """
    Vertical circulation core (stairs, elevators).

    Represents a penetration through all levels for pedestrian access.
    """
    id: str
    footprint: Polygon
    core_type: CoreType
    location: str  # Descriptive: "northeast", "southwest", "center", etc.

    @property
    def area(self) -> float:
        """Footprint area in square feet."""
        return self.footprint.area

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "footprint": self.footprint.to_dict(),
            "core_type": self.core_type.value,
            "location": self.location,
            "area_sf": self.area,
        }


@dataclass
class Ramp:
    """
    Vehicular ramp connecting parking levels.

    Represents the ramp footprint and its connectivity between levels.
    """
    id: str
    footprint: Polygon
    ramp_type: RampType
    from_level: int  # Level index (0 = ground)
    to_level: int    # Level index
    slope_percent: float  # Ramp slope as percentage
    width: float     # Clear width in feet

    @property
    def area(self) -> float:
        """Footprint area in square feet."""
        return self.footprint.area

    @property
    def rise(self) -> float:
        """Vertical rise based on slope and run."""
        run = max(self.footprint.width, self.footprint.height)
        return run * (self.slope_percent / 100.0)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "footprint": self.footprint.to_dict(),
            "ramp_type": self.ramp_type.value,
            "from_level": self.from_level,
            "to_level": self.to_level,
            "slope_percent": self.slope_percent,
            "width_ft": self.width,
            "area_sf": self.area,
        }


@dataclass
class ParkingLevel:
    """
    Single level of a structured parking facility.

    Contains the floor plate geometry and reserved areas.
    Does NOT contain stall placement (deferred to future phase).
    """
    level_index: int           # 0 = ground level
    elevation: float           # Elevation above grade (feet)
    gross_footprint: Polygon   # Total floor plate
    net_parking_area: Polygon  # Usable area after exclusions
    is_roof: bool = False      # True if top/roof level
    is_ground: bool = False    # True if ground level (level_index == 0)

    # Reserved areas (subtracted from gross to get net)
    ramp_reservations: List[Polygon] = field(default_factory=list)
    core_reservations: List[Polygon] = field(default_factory=list)

    @property
    def gross_area(self) -> float:
        """Gross floor plate area in square feet."""
        return self.gross_footprint.area

    @property
    def net_area(self) -> float:
        """Net usable parking area in square feet."""
        return self.net_parking_area.area

    @property
    def reserved_area(self) -> float:
        """Total reserved area (ramps + cores)."""
        ramp_area = sum(p.area for p in self.ramp_reservations)
        core_area = sum(p.area for p in self.core_reservations)
        return ramp_area + core_area

    @property
    def efficiency_ratio(self) -> float:
        """Ratio of net to gross area."""
        if self.gross_area == 0:
            return 0.0
        return self.net_area / self.gross_area

    def to_dict(self) -> Dict:
        return {
            "level_index": self.level_index,
            "elevation_ft": self.elevation,
            "is_roof": self.is_roof,
            "is_ground": self.is_ground,
            "gross_area_sf": self.gross_area,
            "net_area_sf": self.net_area,
            "reserved_area_sf": self.reserved_area,
            "efficiency_ratio": round(self.efficiency_ratio, 3),
            "gross_footprint": self.gross_footprint.to_dict(),
            "net_parking_area": self.net_parking_area.to_dict(),
            "ramp_reservations": [p.to_dict() for p in self.ramp_reservations],
            "core_reservations": [p.to_dict() for p in self.core_reservations],
        }


@dataclass
class StructuredParkingLayout:
    """
    Complete structured parking layout (skeleton).

    Contains stacked floor plates, ramps, and vertical cores.
    Stall placement is NOT included in this phase.
    """
    footprint: Polygon                # Base footprint polygon
    levels: List[ParkingLevel]        # All parking levels (bottom to top)
    ramps: List[Ramp]                 # Vehicular ramps
    cores: List[VerticalCore]         # Vertical circulation cores
    floor_to_floor_height: float      # Floor-to-floor height (feet)
    rules: ParkingRules               # Dimension rules reference

    @property
    def level_count(self) -> int:
        """Total number of parking levels."""
        return len(self.levels)

    @property
    def total_height(self) -> float:
        """Total structure height (feet)."""
        if not self.levels:
            return 0.0
        return self.levels[-1].elevation + self.floor_to_floor_height

    @property
    def gross_footprint_area(self) -> float:
        """Gross footprint area (single level)."""
        return self.footprint.area

    @property
    def total_gross_area(self) -> float:
        """Total gross area across all levels."""
        return sum(level.gross_area for level in self.levels)

    @property
    def total_net_area(self) -> float:
        """Total net parking area across all levels."""
        return sum(level.net_area for level in self.levels)

    @property
    def total_ramp_area(self) -> float:
        """Total ramp footprint area."""
        return sum(ramp.area for ramp in self.ramps)

    @property
    def total_core_area(self) -> float:
        """Total core footprint area."""
        return sum(core.area for core in self.cores)

    def get_level(self, index: int) -> Optional[ParkingLevel]:
        """Get level by index."""
        for level in self.levels:
            if level.level_index == index:
                return level
        return None

    def to_dict(self) -> Dict:
        return {
            "footprint": self.footprint.to_dict(),
            "level_count": self.level_count,
            "floor_to_floor_height_ft": self.floor_to_floor_height,
            "total_height_ft": self.total_height,
            "total_gross_area_sf": self.total_gross_area,
            "total_net_area_sf": self.total_net_area,
            "total_ramp_area_sf": self.total_ramp_area,
            "total_core_area_sf": self.total_core_area,
            "levels": [level.to_dict() for level in self.levels],
            "ramps": [ramp.to_dict() for ramp in self.ramps],
            "cores": [core.to_dict() for core in self.cores],
        }


# =============================================================================
# FLOOR PLATE GENERATION
# =============================================================================

def generate_floor_plate(
    footprint: Polygon,
    level_index: int,
    elevation: float,
    ramp_reservations: Optional[List[Polygon]] = None,
    core_reservations: Optional[List[Polygon]] = None,
    setback: float = 0.0,
    is_roof: bool = False,
) -> ParkingLevel:
    """
    Generate a single floor plate for a parking level.

    Args:
        footprint: Gross footprint polygon
        level_index: Level index (0 = ground)
        elevation: Elevation above grade (feet)
        ramp_reservations: Polygons reserved for ramps
        core_reservations: Polygons reserved for cores
        setback: Optional inward setback from footprint edge
        is_roof: Whether this is the roof level

    Returns:
        ParkingLevel with empty floor plate (no stalls)
    """
    ramp_reservations = ramp_reservations or []
    core_reservations = core_reservations or []

    # Apply setback if specified
    if setback > 0:
        gross_footprint = offset_polygon(footprint, setback)
        if gross_footprint is None:
            gross_footprint = footprint
    else:
        gross_footprint = footprint

    # Calculate net parking area (gross minus reservations)
    # For skeleton phase, we approximate by area subtraction
    # Full boolean operations deferred to future phase
    total_reserved = sum(p.area for p in ramp_reservations) + \
        sum(p.area for p in core_reservations)

    # Net area is the same polygon for now (geometric subtraction deferred)
    # We track reservations separately for future processing
    net_parking_area = gross_footprint

    return ParkingLevel(
        level_index=level_index,
        elevation=elevation,
        gross_footprint=gross_footprint,
        net_parking_area=net_parking_area,
        is_roof=is_roof,
        is_ground=(level_index == 0),
        ramp_reservations=ramp_reservations,
        core_reservations=core_reservations,
    )


# =============================================================================
# RAMP AND CORE GENERATION
# =============================================================================

def generate_ramp_footprint(
    structure_footprint: Polygon,
    ramp_type: RampType,
    location: str = "northeast",
    width: float = 16.0,
    length: float = 60.0,
) -> Polygon:
    """
    Generate a ramp footprint polygon at a specified location.

    Args:
        structure_footprint: The structure's base footprint
        ramp_type: Type of ramp
        location: Corner or edge location ("northeast", "southwest", etc.)
        width: Ramp width in feet
        length: Ramp length/run in feet

    Returns:
        Ramp footprint polygon
    """
    min_x, min_y, max_x, max_y = structure_footprint.bounds

    # Position ramp based on location
    if location == "northeast":
        ramp_min_x = max_x - length
        ramp_min_y = max_y - width
        ramp_max_x = max_x
        ramp_max_y = max_y
    elif location == "northwest":
        ramp_min_x = min_x
        ramp_min_y = max_y - width
        ramp_max_x = min_x + length
        ramp_max_y = max_y
    elif location == "southeast":
        ramp_min_x = max_x - length
        ramp_min_y = min_y
        ramp_max_x = max_x
        ramp_max_y = min_y + width
    elif location == "southwest":
        ramp_min_x = min_x
        ramp_min_y = min_y
        ramp_max_x = min_x + length
        ramp_max_y = min_y + width
    else:
        # Default to northeast
        ramp_min_x = max_x - length
        ramp_min_y = max_y - width
        ramp_max_x = max_x
        ramp_max_y = max_y

    return Polygon.from_bounds(ramp_min_x, ramp_min_y, ramp_max_x, ramp_max_y)


def generate_core_footprint(
    structure_footprint: Polygon,
    core_type: CoreType,
    location: str = "center",
    width: float = 20.0,
    depth: float = 25.0,
) -> Polygon:
    """
    Generate a vertical core footprint polygon.

    Args:
        structure_footprint: The structure's base footprint
        core_type: Type of vertical core
        location: Position within structure
        width: Core width in feet
        depth: Core depth in feet

    Returns:
        Core footprint polygon
    """
    min_x, min_y, max_x, max_y = structure_footprint.bounds
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2

    # Position core based on location
    if location == "center":
        core_min_x = cx - width / 2
        core_min_y = cy - depth / 2
    elif location == "north":
        core_min_x = cx - width / 2
        core_min_y = max_y - depth
    elif location == "south":
        core_min_x = cx - width / 2
        core_min_y = min_y
    elif location == "east":
        core_min_x = max_x - width
        core_min_y = cy - depth / 2
    elif location == "west":
        core_min_x = min_x
        core_min_y = cy - depth / 2
    else:
        core_min_x = cx - width / 2
        core_min_y = cy - depth / 2

    return Polygon.from_bounds(
        core_min_x, core_min_y,
        core_min_x + width, core_min_y + depth
    )


# =============================================================================
# VERTICAL STACKING LOGIC
# =============================================================================

def stack_levels(
    footprint: Polygon,
    level_count: int,
    floor_to_floor_height: float,
    ramp_footprints: Optional[List[Polygon]] = None,
    core_footprints: Optional[List[Polygon]] = None,
    ground_elevation: float = 0.0,
) -> List[ParkingLevel]:
    """
    Stack floor plates vertically to create parking levels.

    Args:
        footprint: Base footprint polygon (reused for all levels)
        level_count: Number of parking levels
        floor_to_floor_height: Height between floor slabs (feet)
        ramp_footprints: Ramp reservations to apply to each level
        core_footprints: Core reservations to apply to each level
        ground_elevation: Starting elevation (default 0)

    Returns:
        List of ParkingLevel objects from ground to roof
    """
    if level_count < 1:
        return []

    ramp_footprints = ramp_footprints or []
    core_footprints = core_footprints or []

    levels = []

    for i in range(level_count):
        elevation = ground_elevation + (i * floor_to_floor_height)
        is_roof = (i == level_count - 1)
        is_ground = (i == 0)

        level = generate_floor_plate(
            footprint=footprint,
            level_index=i,
            elevation=elevation,
            ramp_reservations=ramp_footprints.copy(),
            core_reservations=core_footprints.copy(),
            is_roof=is_roof,
        )
        level.is_ground = is_ground

        levels.append(level)

    return levels


def compute_structure_height(
    level_count: int,
    floor_to_floor_height: float,
) -> float:
    """
    Compute total structure height.

    Args:
        level_count: Number of parking levels
        floor_to_floor_height: Height between floor slabs

    Returns:
        Total height in feet
    """
    if level_count < 1:
        return 0.0
    return level_count * floor_to_floor_height


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def generate_structured_parking_skeleton(
    footprint: Polygon,
    level_count: int,
    floor_to_floor_height: float = 10.5,
    ramp_config: Optional[Dict] = None,
    core_config: Optional[Dict] = None,
    rules: Optional[ParkingRules] = None,
) -> StructuredParkingLayout:
    """
    Generate a structured parking layout skeleton.

    Creates stacked floor plates with ramp and core reservations.
    Does NOT place parking stalls (deferred to future phase).

    Args:
        footprint: Base footprint polygon
        level_count: Number of parking levels (minimum 2 typical)
        floor_to_floor_height: Height between floor slabs (default 10.5')
        ramp_config: Optional ramp configuration dict:
            - type: RampType value (default "single_helix")
            - location: Placement location (default "northeast")
            - width: Ramp width in feet (default 16)
            - length: Ramp length in feet (default 60)
        core_config: Optional core configuration dict:
            - type: CoreType value (default "stair_elevator")
            - location: Placement location (default "center")
            - width: Core width in feet (default 20)
            - depth: Core depth in feet (default 25)
        rules: Parking dimension rules (uses defaults if None)

    Returns:
        StructuredParkingLayout with empty floor plates

    Example:
        >>> from parking_engine import Polygon
        >>> footprint = Polygon.from_bounds(0, 0, 300, 180)
        >>> layout = generate_structured_parking_skeleton(
        ...     footprint=footprint,
        ...     level_count=4,
        ...     floor_to_floor_height=10.5,
        ... )
        >>> print(f"Levels: {layout.level_count}, Height: {layout.total_height}'")
    """
    if not footprint.is_rectangular:
        raise ValueError(
            "Structured parking skeleton requires rectangular footprint")

    if level_count < 1:
        raise ValueError("Level count must be at least 1")

    if floor_to_floor_height < 8.0:
        raise ValueError("Floor-to-floor height must be at least 8 feet")

    rules = rules or ParkingRules()

    # Default ramp configuration
    ramp_config = ramp_config or {}
    ramp_type = RampType(ramp_config.get("type", "single_helix"))
    ramp_location = ramp_config.get("location", "northeast")
    ramp_width = ramp_config.get("width", 16.0)
    ramp_length = ramp_config.get("length", 60.0)

    # Default core configuration
    core_config = core_config or {}
    core_type = CoreType(core_config.get("type", "stair_elevator"))
    core_location = core_config.get("location", "center")
    core_width = core_config.get("width", 20.0)
    core_depth = core_config.get("depth", 25.0)

    # Generate ramp footprint
    ramp_footprint = generate_ramp_footprint(
        structure_footprint=footprint,
        ramp_type=ramp_type,
        location=ramp_location,
        width=ramp_width,
        length=ramp_length,
    )

    # Generate core footprint
    core_footprint = generate_core_footprint(
        structure_footprint=footprint,
        core_type=core_type,
        location=core_location,
        width=core_width,
        depth=core_depth,
    )

    # Stack levels
    levels = stack_levels(
        footprint=footprint,
        level_count=level_count,
        floor_to_floor_height=floor_to_floor_height,
        ramp_footprints=[ramp_footprint],
        core_footprints=[core_footprint],
    )

    # Create ramp objects for each inter-level connection
    ramps = []
    for i in range(level_count - 1):
        ramp = Ramp(
            id=f"ramp_{i}_to_{i+1}",
            footprint=ramp_footprint,
            ramp_type=ramp_type,
            from_level=i,
            to_level=i + 1,
            slope_percent=6.67,  # Typical max slope for parking ramps
            width=ramp_width,
        )
        ramps.append(ramp)

    # Create single core (penetrates all levels)
    cores = [
        VerticalCore(
            id="core_0",
            footprint=core_footprint,
            core_type=core_type,
            location=core_location,
        )
    ]

    return StructuredParkingLayout(
        footprint=footprint,
        levels=levels,
        ramps=ramps,
        cores=cores,
        floor_to_floor_height=floor_to_floor_height,
        rules=rules,
    )
