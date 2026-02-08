"""
building/unit_mix.py - Residential Unit Mix Module

Distributes units by type on each floor and calculates unit counts.
Supports studio, 1BR, 2BR, 3BR and custom unit types.

Depends on: floor_plate.py, massing.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple, Any

from sitefit.building.floor_plate import FloorPlate, FloorType
from sitefit.building.massing import BuildingMass


class UnitType(Enum):
    """Standard residential unit types."""
    STUDIO = "studio"
    ONE_BEDROOM = "1br"
    TWO_BEDROOM = "2br"
    THREE_BEDROOM = "3br"
    PENTHOUSE = "penthouse"
    LOFT = "loft"
    MICRO = "micro"
    AFFORDABLE = "affordable"


@dataclass
class UnitSpec:
    """
    Specification for a unit type.

    Attributes:
        unit_type: Type of unit
        avg_size_sf: Average unit size in square feet
        min_size_sf: Minimum unit size
        max_size_sf: Maximum unit size
        bedrooms: Number of bedrooms
        bathrooms: Number of bathrooms
        target_rent: Target monthly rent (optional)
        parking_spaces: Parking spaces per unit
    """
    unit_type: UnitType
    avg_size_sf: float
    min_size_sf: float = 0.0
    max_size_sf: float = 0.0
    bedrooms: int = 0
    bathrooms: float = 1.0
    target_rent: Optional[float] = None
    parking_spaces: float = 1.0

    def __post_init__(self):
        if self.min_size_sf == 0:
            self.min_size_sf = self.avg_size_sf * 0.8
        if self.max_size_sf == 0:
            self.max_size_sf = self.avg_size_sf * 1.2

    @classmethod
    def studio(cls, avg_size: float = 500) -> 'UnitSpec':
        """Create studio unit spec."""
        return cls(
            unit_type=UnitType.STUDIO,
            avg_size_sf=avg_size,
            bedrooms=0,
            bathrooms=1.0,
            parking_spaces=0.75
        )

    @classmethod
    def one_bedroom(cls, avg_size: float = 700) -> 'UnitSpec':
        """Create 1BR unit spec."""
        return cls(
            unit_type=UnitType.ONE_BEDROOM,
            avg_size_sf=avg_size,
            bedrooms=1,
            bathrooms=1.0,
            parking_spaces=1.0
        )

    @classmethod
    def two_bedroom(cls, avg_size: float = 1000) -> 'UnitSpec':
        """Create 2BR unit spec."""
        return cls(
            unit_type=UnitType.TWO_BEDROOM,
            avg_size_sf=avg_size,
            bedrooms=2,
            bathrooms=2.0,
            parking_spaces=1.5
        )

    @classmethod
    def three_bedroom(cls, avg_size: float = 1300) -> 'UnitSpec':
        """Create 3BR unit spec."""
        return cls(
            unit_type=UnitType.THREE_BEDROOM,
            avg_size_sf=avg_size,
            bedrooms=3,
            bathrooms=2.0,
            parking_spaces=2.0
        )

    @classmethod
    def micro(cls, avg_size: float = 350) -> 'UnitSpec':
        """Create micro unit spec."""
        return cls(
            unit_type=UnitType.MICRO,
            avg_size_sf=avg_size,
            bedrooms=0,
            bathrooms=1.0,
            parking_spaces=0.5
        )

    @classmethod
    def penthouse(cls, avg_size: float = 2500) -> 'UnitSpec':
        """Create penthouse unit spec."""
        return cls(
            unit_type=UnitType.PENTHOUSE,
            avg_size_sf=avg_size,
            bedrooms=3,
            bathrooms=3.0,
            parking_spaces=2.0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "unit_type": self.unit_type.value,
            "avg_size_sf": self.avg_size_sf,
            "min_size_sf": self.min_size_sf,
            "max_size_sf": self.max_size_sf,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "parking_spaces": self.parking_spaces,
        }


@dataclass
class UnitMixTarget:
    """
    Target unit mix as percentages.

    Percentages should sum to 1.0.
    """
    studio_pct: float = 0.15
    one_br_pct: float = 0.40
    two_br_pct: float = 0.35
    three_br_pct: float = 0.10

    def __post_init__(self):
        total = self.studio_pct + self.one_br_pct + self.two_br_pct + self.three_br_pct
        if abs(total - 1.0) > 0.01:
            # Normalize if not 100%
            self.studio_pct /= total
            self.one_br_pct /= total
            self.two_br_pct /= total
            self.three_br_pct /= total

    @classmethod
    def urban_rental(cls) -> 'UnitMixTarget':
        """Urban rental mix - more studios and 1BRs."""
        return cls(
            studio_pct=0.20,
            one_br_pct=0.45,
            two_br_pct=0.30,
            three_br_pct=0.05
        )

    @classmethod
    def suburban_rental(cls) -> 'UnitMixTarget':
        """Suburban rental mix - more 2BRs and 3BRs."""
        return cls(
            studio_pct=0.05,
            one_br_pct=0.30,
            two_br_pct=0.45,
            three_br_pct=0.20
        )

    @classmethod
    def condo(cls) -> 'UnitMixTarget':
        """Condo mix - larger units."""
        return cls(
            studio_pct=0.05,
            one_br_pct=0.25,
            two_br_pct=0.50,
            three_br_pct=0.20
        )

    @classmethod
    def senior_housing(cls) -> 'UnitMixTarget':
        """Senior housing mix - mostly 1BRs."""
        return cls(
            studio_pct=0.25,
            one_br_pct=0.60,
            two_br_pct=0.15,
            three_br_pct=0.0
        )

    @classmethod
    def affordable(cls) -> 'UnitMixTarget':
        """Affordable housing mix - family-sized units."""
        return cls(
            studio_pct=0.10,
            one_br_pct=0.30,
            two_br_pct=0.40,
            three_br_pct=0.20
        )

    def get_percentages(self) -> Dict[UnitType, float]:
        """Get percentages by unit type."""
        return {
            UnitType.STUDIO: self.studio_pct,
            UnitType.ONE_BEDROOM: self.one_br_pct,
            UnitType.TWO_BEDROOM: self.two_br_pct,
            UnitType.THREE_BEDROOM: self.three_br_pct,
        }

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "studio": self.studio_pct,
            "1br": self.one_br_pct,
            "2br": self.two_br_pct,
            "3br": self.three_br_pct,
        }


@dataclass
class UnitCount:
    """Count of units by type."""
    studio: int = 0
    one_br: int = 0
    two_br: int = 0
    three_br: int = 0
    penthouse: int = 0
    other: int = 0

    @property
    def total(self) -> int:
        """Total unit count."""
        return (self.studio + self.one_br + self.two_br +
                self.three_br + self.penthouse + self.other)

    @property
    def total_bedrooms(self) -> int:
        """Total bedroom count."""
        return (0 * self.studio + 1 * self.one_br + 2 * self.two_br +
                3 * self.three_br + 3 * self.penthouse)

    def add(self, unit_type: UnitType, count: int = 1):
        """Add units of a type."""
        if unit_type == UnitType.STUDIO:
            self.studio += count
        elif unit_type == UnitType.ONE_BEDROOM:
            self.one_br += count
        elif unit_type == UnitType.TWO_BEDROOM:
            self.two_br += count
        elif unit_type == UnitType.THREE_BEDROOM:
            self.three_br += count
        elif unit_type == UnitType.PENTHOUSE:
            self.penthouse += count
        else:
            self.other += count

    def get_by_type(self, unit_type: UnitType) -> int:
        """Get count for a unit type."""
        if unit_type == UnitType.STUDIO:
            return self.studio
        elif unit_type == UnitType.ONE_BEDROOM:
            return self.one_br
        elif unit_type == UnitType.TWO_BEDROOM:
            return self.two_br
        elif unit_type == UnitType.THREE_BEDROOM:
            return self.three_br
        elif unit_type == UnitType.PENTHOUSE:
            return self.penthouse
        return self.other

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary."""
        return {
            "studio": self.studio,
            "1br": self.one_br,
            "2br": self.two_br,
            "3br": self.three_br,
            "penthouse": self.penthouse,
            "other": self.other,
            "total": self.total,
            "total_bedrooms": self.total_bedrooms,
        }

    def __add__(self, other: 'UnitCount') -> 'UnitCount':
        """Add two UnitCounts together."""
        return UnitCount(
            studio=self.studio + other.studio,
            one_br=self.one_br + other.one_br,
            two_br=self.two_br + other.two_br,
            three_br=self.three_br + other.three_br,
            penthouse=self.penthouse + other.penthouse,
            other=self.other + other.other,
        )


@dataclass
class FloorUnitMix:
    """Unit mix for a single floor."""
    floor_number: int
    floor_area_sf: float
    net_area_sf: float
    units: UnitCount
    leftover_sf: float = 0.0

    @property
    def unit_count(self) -> int:
        """Total units on this floor."""
        return self.units.total

    @property
    def avg_unit_size(self) -> float:
        """Average unit size on this floor."""
        if self.unit_count > 0:
            return self.net_area_sf / self.unit_count
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "floor_number": self.floor_number,
            "floor_area_sf": round(self.floor_area_sf, 0),
            "net_area_sf": round(self.net_area_sf, 0),
            "unit_count": self.unit_count,
            "units": self.units.to_dict(),
            "avg_unit_size": round(self.avg_unit_size, 0),
            "leftover_sf": round(self.leftover_sf, 0),
        }


@dataclass
class BuildingUnitMix:
    """Complete unit mix for a building."""
    floors: List[FloorUnitMix]
    unit_specs: Dict[UnitType, UnitSpec]
    target_mix: UnitMixTarget

    @property
    def total_units(self) -> UnitCount:
        """Total units across all floors."""
        total = UnitCount()
        for floor in self.floors:
            total = total + floor.units
        return total

    @property
    def unit_count(self) -> int:
        """Total unit count."""
        return self.total_units.total

    @property
    def bedroom_count(self) -> int:
        """Total bedroom count."""
        return self.total_units.total_bedrooms

    @property
    def total_unit_area(self) -> float:
        """Total area in units."""
        return sum(f.net_area_sf for f in self.floors)

    @property
    def avg_unit_size(self) -> float:
        """Average unit size across building."""
        if self.unit_count > 0:
            return self.total_unit_area / self.unit_count
        return 0.0

    def get_actual_mix(self) -> Dict[UnitType, float]:
        """Get actual unit mix as percentages."""
        total = self.total_units
        if total.total == 0:
            return {}

        return {
            UnitType.STUDIO: total.studio / total.total,
            UnitType.ONE_BEDROOM: total.one_br / total.total,
            UnitType.TWO_BEDROOM: total.two_br / total.total,
            UnitType.THREE_BEDROOM: total.three_br / total.total,
        }

    def get_parking_requirement(self) -> float:
        """Calculate required parking based on unit specs."""
        total = 0.0
        units = self.total_units

        for unit_type, spec in self.unit_specs.items():
            count = units.get_by_type(unit_type)
            total += count * spec.parking_spaces

        return total

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        actual_mix = self.get_actual_mix()
        return {
            "unit_count": self.unit_count,
            "bedroom_count": self.bedroom_count,
            "total_unit_area_sf": round(self.total_unit_area, 0),
            "avg_unit_size_sf": round(self.avg_unit_size, 0),
            "units_by_type": self.total_units.to_dict(),
            "actual_mix": {k.value: round(v, 3) for k, v in actual_mix.items()},
            "target_mix": self.target_mix.to_dict(),
            "parking_requirement": round(self.get_parking_requirement(), 1),
            "floors": [f.to_dict() for f in self.floors],
        }


# =============================================================================
# UNIT MIX CALCULATION
# =============================================================================

def get_default_unit_specs() -> Dict[UnitType, UnitSpec]:
    """Get default unit specifications."""
    return {
        UnitType.STUDIO: UnitSpec.studio(),
        UnitType.ONE_BEDROOM: UnitSpec.one_bedroom(),
        UnitType.TWO_BEDROOM: UnitSpec.two_bedroom(),
        UnitType.THREE_BEDROOM: UnitSpec.three_bedroom(),
    }


def calculate_units_for_area(
    net_area_sf: float,
    target_mix: UnitMixTarget,
    unit_specs: Optional[Dict[UnitType, UnitSpec]] = None
) -> Tuple[UnitCount, float]:
    """
    Calculate unit count for a given area based on target mix.

    Args:
        net_area_sf: Net leasable area in square feet
        target_mix: Target unit mix percentages
        unit_specs: Unit specifications (uses defaults if None)

    Returns:
        Tuple of (UnitCount, leftover_area_sf)
    """
    if unit_specs is None:
        unit_specs = get_default_unit_specs()

    if net_area_sf <= 0:
        return UnitCount(), 0.0

    # Calculate weighted average unit size
    weighted_size = 0.0
    percentages = target_mix.get_percentages()

    for unit_type, pct in percentages.items():
        if unit_type in unit_specs:
            weighted_size += pct * unit_specs[unit_type].avg_size_sf

    if weighted_size <= 0:
        return UnitCount(), net_area_sf

    # Calculate total units that fit
    total_units = int(net_area_sf / weighted_size)

    if total_units == 0:
        return UnitCount(), net_area_sf

    # Distribute by type
    units = UnitCount()
    remaining_units = total_units

    # Allocate in order, largest first to minimize rounding errors
    unit_types_by_pct = sorted(
        percentages.items(),
        key=lambda x: x[1],
        reverse=True
    )

    for i, (unit_type, pct) in enumerate(unit_types_by_pct):
        if i == len(unit_types_by_pct) - 1:
            # Last type gets remainder
            count = remaining_units
        else:
            count = int(total_units * pct)

        units.add(unit_type, count)
        remaining_units -= count

    # Calculate actual area used
    used_area = 0.0
    for unit_type, spec in unit_specs.items():
        count = units.get_by_type(unit_type)
        used_area += count * spec.avg_size_sf

    leftover = max(0, net_area_sf - used_area)

    return units, leftover


def calculate_floor_unit_mix(
    floor: FloorPlate,
    target_mix: UnitMixTarget,
    unit_specs: Optional[Dict[UnitType, UnitSpec]] = None
) -> FloorUnitMix:
    """
    Calculate unit mix for a single floor.

    Args:
        floor: Floor plate
        target_mix: Target unit mix
        unit_specs: Unit specifications

    Returns:
        FloorUnitMix with unit distribution
    """
    if unit_specs is None:
        unit_specs = get_default_unit_specs()

    # Skip non-residential floors
    if floor.floor_type in [FloorType.MECHANICAL, FloorType.ROOFTOP]:
        return FloorUnitMix(
            floor_number=floor.floor_number,
            floor_area_sf=floor.gross_area,
            net_area_sf=0,
            units=UnitCount(),
            leftover_sf=0
        )

    units, leftover = calculate_units_for_area(
        floor.net_area, target_mix, unit_specs
    )

    return FloorUnitMix(
        floor_number=floor.floor_number,
        floor_area_sf=floor.gross_area,
        net_area_sf=floor.net_area,
        units=units,
        leftover_sf=leftover
    )


def calculate_building_unit_mix(
    massing: BuildingMass,
    target_mix: Optional[UnitMixTarget] = None,
    unit_specs: Optional[Dict[UnitType, UnitSpec]] = None,
    residential_floor_types: Optional[List[FloorType]] = None
) -> BuildingUnitMix:
    """
    Calculate unit mix for entire building.

    Args:
        massing: Building massing with floor plates
        target_mix: Target unit mix (default: urban rental)
        unit_specs: Unit specifications
        residential_floor_types: Which floor types are residential

    Returns:
        BuildingUnitMix with complete unit distribution
    """
    if target_mix is None:
        target_mix = UnitMixTarget()

    if unit_specs is None:
        unit_specs = get_default_unit_specs()

    if residential_floor_types is None:
        residential_floor_types = [
            FloorType.GROUND,
            FloorType.TYPICAL,
            FloorType.PODIUM,
            FloorType.AMENITY,
            FloorType.PENTHOUSE,
        ]

    floor_mixes = []

    for floor in massing.floors:
        if floor.floor_type in residential_floor_types:
            floor_mix = calculate_floor_unit_mix(floor, target_mix, unit_specs)
        else:
            # Non-residential floor
            floor_mix = FloorUnitMix(
                floor_number=floor.floor_number,
                floor_area_sf=floor.gross_area,
                net_area_sf=0,
                units=UnitCount(),
                leftover_sf=0
            )
        floor_mixes.append(floor_mix)

    return BuildingUnitMix(
        floors=floor_mixes,
        unit_specs=unit_specs,
        target_mix=target_mix
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def estimate_units_from_area(
    total_area_sf: float,
    avg_unit_size: float = 800,
    efficiency: float = 0.85
) -> int:
    """
    Quick estimate of unit count from total building area.

    Args:
        total_area_sf: Total gross floor area
        avg_unit_size: Average unit size
        efficiency: Building efficiency (net/gross)

    Returns:
        Estimated unit count
    """
    net_area = total_area_sf * efficiency
    return int(net_area / avg_unit_size)


def calculate_avg_unit_size(
    target_mix: UnitMixTarget,
    unit_specs: Optional[Dict[UnitType, UnitSpec]] = None
) -> float:
    """
    Calculate weighted average unit size for a mix.

    Args:
        target_mix: Target unit mix percentages
        unit_specs: Unit specifications

    Returns:
        Weighted average unit size in SF
    """
    if unit_specs is None:
        unit_specs = get_default_unit_specs()

    weighted_size = 0.0
    percentages = target_mix.get_percentages()

    for unit_type, pct in percentages.items():
        if unit_type in unit_specs:
            weighted_size += pct * unit_specs[unit_type].avg_size_sf

    return weighted_size


def calculate_required_parking_from_units(
    units: UnitCount,
    unit_specs: Optional[Dict[UnitType, UnitSpec]] = None
) -> float:
    """
    Calculate required parking stalls based on unit count.

    Args:
        units: Unit count by type
        unit_specs: Unit specifications with parking ratios

    Returns:
        Required parking stalls
    """
    if unit_specs is None:
        unit_specs = get_default_unit_specs()

    total_parking = 0.0

    for unit_type, spec in unit_specs.items():
        count = units.get_by_type(unit_type)
        total_parking += count * spec.parking_spaces

    return total_parking


def get_bedroom_count(units: UnitCount) -> int:
    """Get total bedroom count from unit count."""
    return units.total_bedrooms


def optimize_unit_mix_for_target_count(
    net_area_sf: float,
    target_units: int,
    unit_specs: Optional[Dict[UnitType, UnitSpec]] = None
) -> Tuple[UnitMixTarget, UnitCount]:
    """
    Optimize unit mix to achieve target unit count.

    Adjusts mix toward smaller units if more units needed,
    or larger units if fewer needed.

    Args:
        net_area_sf: Available net area
        target_units: Target number of units
        unit_specs: Unit specifications

    Returns:
        Tuple of (optimized UnitMixTarget, resulting UnitCount)
    """
    if unit_specs is None:
        unit_specs = get_default_unit_specs()

    # Calculate avg size needed
    target_avg_size = net_area_sf / target_units if target_units > 0 else 800

    # Standard sizes
    studio_size = unit_specs[UnitType.STUDIO].avg_size_sf
    one_br_size = unit_specs[UnitType.ONE_BEDROOM].avg_size_sf
    two_br_size = unit_specs[UnitType.TWO_BEDROOM].avg_size_sf
    three_br_size = unit_specs[UnitType.THREE_BEDROOM].avg_size_sf

    # Adjust mix based on target size
    if target_avg_size < studio_size:
        # Need very small units - max studios
        mix = UnitMixTarget(
            studio_pct=0.70, one_br_pct=0.25, two_br_pct=0.05, three_br_pct=0.0
        )
    elif target_avg_size < one_br_size:
        # Small units - more studios
        mix = UnitMixTarget(
            studio_pct=0.40, one_br_pct=0.45, two_br_pct=0.15, three_br_pct=0.0
        )
    elif target_avg_size < two_br_size:
        # Medium units - balanced
        mix = UnitMixTarget(
            studio_pct=0.15, one_br_pct=0.45, two_br_pct=0.35, three_br_pct=0.05
        )
    elif target_avg_size < three_br_size:
        # Larger units - more 2BR/3BR
        mix = UnitMixTarget(
            studio_pct=0.05, one_br_pct=0.25, two_br_pct=0.50, three_br_pct=0.20
        )
    else:
        # Very large units - max 3BR
        mix = UnitMixTarget(
            studio_pct=0.0, one_br_pct=0.15, two_br_pct=0.45, three_br_pct=0.40
        )

    units, _ = calculate_units_for_area(net_area_sf, mix, unit_specs)

    return mix, units


def get_unit_mix_summary(building_mix: BuildingUnitMix) -> Dict[str, Any]:
    """Get comprehensive unit mix summary."""
    units = building_mix.total_units
    actual_mix = building_mix.get_actual_mix()

    return {
        "summary": {
            "total_units": units.total,
            "total_bedrooms": units.total_bedrooms,
            "avg_unit_size": round(building_mix.avg_unit_size, 0),
            "parking_required": round(building_mix.get_parking_requirement(), 1),
        },
        "units_by_type": {
            "studio": units.studio,
            "1br": units.one_br,
            "2br": units.two_br,
            "3br": units.three_br,
            "penthouse": units.penthouse,
            "other": units.other,
        },
        "mix_percentages": {
            k.value: f"{v*100:.1f}%" for k, v in actual_mix.items()
        },
        "by_floor": [f.to_dict() for f in building_mix.floors],
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    'UnitType',

    # Classes
    'UnitSpec',
    'UnitMixTarget',
    'UnitCount',
    'FloorUnitMix',
    'BuildingUnitMix',

    # Main functions
    'calculate_units_for_area',
    'calculate_floor_unit_mix',
    'calculate_building_unit_mix',

    # Helper functions
    'get_default_unit_specs',
    'estimate_units_from_area',
    'calculate_avg_unit_size',
    'calculate_required_parking_from_units',
    'get_bedroom_count',
    'optimize_unit_mix_for_target_count',
    'get_unit_mix_summary',
]
