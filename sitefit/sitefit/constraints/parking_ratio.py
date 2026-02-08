"""
constraints/parking_ratio.py - Parking Ratio Requirements Module

Calculates required parking stalls based on:
- Residential unit count and type
- Commercial square footage by use type
- Mixed-use combinations

Depends on: building/unit_mix.py (deferred import to avoid circular dependency)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple, Any, TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular import:
# parking_ratio -> unit_mix -> massing -> setbacks -> (circular)
if TYPE_CHECKING:
    from sitefit.building.unit_mix import UnitType, UnitCount, BuildingUnitMix


class UseType(Enum):
    """Land use types for parking calculation."""
    # Residential
    RESIDENTIAL_MULTIFAMILY = "residential_multifamily"
    RESIDENTIAL_SINGLE_FAMILY = "residential_single_family"
    RESIDENTIAL_SENIOR = "residential_senior"
    RESIDENTIAL_AFFORDABLE = "residential_affordable"
    RESIDENTIAL_STUDENT = "residential_student"

    # Commercial
    RETAIL = "retail"
    RESTAURANT = "restaurant"
    OFFICE = "office"
    MEDICAL_OFFICE = "medical_office"

    # Industrial
    INDUSTRIAL = "industrial"
    WAREHOUSE = "warehouse"

    # Hospitality
    HOTEL = "hotel"

    # Institutional
    SCHOOL = "school"
    CHURCH = "church"
    HOSPITAL = "hospital"

    # Other
    GYM = "gym"
    THEATER = "theater"
    DAYCARE = "daycare"


@dataclass
class ParkingRatio:
    """
    Parking ratio specification.

    Can be expressed as:
    - Per unit (residential)
    - Per 1000 SF (commercial)
    - Per seat/bed/room (assembly, hotel, hospital)
    """
    use_type: UseType
    ratio: float                    # Base ratio
    unit_basis: str = "unit"        # "unit", "1000sf", "seat", "room", "bed"
    min_ratio: Optional[float] = None
    max_ratio: Optional[float] = None
    description: str = ""

    # Adjustments
    transit_reduction: float = 0.0  # Reduction for transit proximity (0-1)
    affordable_reduction: float = 0.0  # Reduction for affordable housing (0-1)
    shared_parking_factor: float = 1.0  # Factor for shared parking

    def calculate_required(
        self,
        quantity: float,
        apply_transit_reduction: bool = False,
        apply_affordable_reduction: bool = False
    ) -> float:
        """
        Calculate required parking stalls.

        Args:
            quantity: Number of units, SF/1000, seats, etc.
            apply_transit_reduction: Apply transit proximity reduction
            apply_affordable_reduction: Apply affordable housing reduction

        Returns:
            Required parking stalls
        """
        required = quantity * self.ratio

        if apply_transit_reduction and self.transit_reduction > 0:
            required *= (1 - self.transit_reduction)

        if apply_affordable_reduction and self.affordable_reduction > 0:
            required *= (1 - self.affordable_reduction)

        required *= self.shared_parking_factor

        # Apply min/max if specified
        if self.min_ratio is not None:
            min_required = quantity * self.min_ratio
            required = max(required, min_required)

        if self.max_ratio is not None:
            max_required = quantity * self.max_ratio
            required = min(required, max_required)

        return required

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "use_type": self.use_type.value,
            "ratio": self.ratio,
            "unit_basis": self.unit_basis,
            "description": self.description,
        }


@dataclass
class ResidentialParkingRatios:
    """
    Parking ratios by residential unit type.
    """
    studio: float = 1.0
    one_br: float = 1.25
    two_br: float = 1.5
    three_br: float = 2.0

    # Guest parking
    guest_ratio: float = 0.25  # Per unit

    # Reductions
    transit_reduction: float = 0.0
    affordable_reduction: float = 0.0
    senior_reduction: float = 0.25

    @classmethod
    def urban(cls) -> 'ResidentialParkingRatios':
        """Urban parking ratios - lower."""
        return cls(
            studio=0.5,
            one_br=0.75,
            two_br=1.0,
            three_br=1.5,
            guest_ratio=0.1,
            transit_reduction=0.25
        )

    @classmethod
    def suburban(cls) -> 'ResidentialParkingRatios':
        """Suburban parking ratios - higher."""
        return cls(
            studio=1.0,
            one_br=1.5,
            two_br=2.0,
            three_br=2.5,
            guest_ratio=0.25
        )

    @classmethod
    def transit_oriented(cls) -> 'ResidentialParkingRatios':
        """Transit-oriented development ratios."""
        return cls(
            studio=0.25,
            one_br=0.5,
            two_br=0.75,
            three_br=1.0,
            guest_ratio=0.1,
            transit_reduction=0.5
        )

    @classmethod
    def affordable_housing(cls) -> 'ResidentialParkingRatios':
        """Affordable housing ratios."""
        return cls(
            studio=0.5,
            one_br=0.75,
            two_br=1.0,
            three_br=1.25,
            guest_ratio=0.1,
            affordable_reduction=0.25
        )

    @classmethod
    def senior_housing(cls) -> 'ResidentialParkingRatios':
        """Senior housing ratios."""
        return cls(
            studio=0.25,
            one_br=0.5,
            two_br=0.75,
            three_br=1.0,
            guest_ratio=0.1,
            senior_reduction=0.5
        )

    def get_ratio_for_type(self, unit_type: "UnitType") -> float:
        """Get parking ratio for unit type."""
        # Lazy import to avoid circular dependency
        from sitefit.building.unit_mix import UnitType

        if unit_type == UnitType.STUDIO or unit_type == UnitType.MICRO:
            return self.studio
        elif unit_type == UnitType.ONE_BEDROOM:
            return self.one_br
        elif unit_type == UnitType.TWO_BEDROOM:
            return self.two_br
        elif unit_type == UnitType.THREE_BEDROOM or unit_type == UnitType.PENTHOUSE:
            return self.three_br
        else:
            return self.one_br  # Default

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "studio": self.studio,
            "1br": self.one_br,
            "2br": self.two_br,
            "3br": self.three_br,
            "guest": self.guest_ratio,
        }


@dataclass
class CommercialParkingRatios:
    """
    Parking ratios for commercial uses (per 1000 SF).
    """
    retail: float = 4.0
    restaurant: float = 10.0
    office: float = 3.0
    medical_office: float = 5.0
    industrial: float = 1.0
    warehouse: float = 0.5
    gym: float = 5.0

    @classmethod
    def urban(cls) -> 'CommercialParkingRatios':
        """Urban commercial ratios - lower."""
        return cls(
            retail=2.5,
            restaurant=6.0,
            office=2.0,
            medical_office=3.5,
            industrial=0.75,
            warehouse=0.25,
            gym=3.0
        )

    @classmethod
    def suburban(cls) -> 'CommercialParkingRatios':
        """Suburban commercial ratios - higher."""
        return cls(
            retail=5.0,
            restaurant=12.0,
            office=4.0,
            medical_office=6.0,
            industrial=1.5,
            warehouse=0.75,
            gym=6.0
        )

    def get_ratio_for_use(self, use_type: UseType) -> float:
        """Get parking ratio for use type."""
        mapping = {
            UseType.RETAIL: self.retail,
            UseType.RESTAURANT: self.restaurant,
            UseType.OFFICE: self.office,
            UseType.MEDICAL_OFFICE: self.medical_office,
            UseType.INDUSTRIAL: self.industrial,
            UseType.WAREHOUSE: self.warehouse,
            UseType.GYM: self.gym,
        }
        return mapping.get(use_type, 3.0)  # Default

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "retail": self.retail,
            "restaurant": self.restaurant,
            "office": self.office,
            "medical_office": self.medical_office,
            "industrial": self.industrial,
            "warehouse": self.warehouse,
            "gym": self.gym,
        }


@dataclass
class ParkingRequirement:
    """
    Complete parking requirement result.
    """
    residential_spaces: float = 0.0
    guest_spaces: float = 0.0
    commercial_spaces: float = 0.0

    # Breakdown by use
    by_use: Dict[str, float] = field(default_factory=dict)

    # Applied reductions
    transit_reduction_applied: float = 0.0
    affordable_reduction_applied: float = 0.0
    shared_parking_reduction: float = 0.0

    @property
    def total_required(self) -> float:
        """Total required parking spaces."""
        return self.residential_spaces + self.guest_spaces + self.commercial_spaces

    @property
    def total_before_reductions(self) -> float:
        """Total before any reductions."""
        return (self.total_required +
                self.transit_reduction_applied +
                self.affordable_reduction_applied +
                self.shared_parking_reduction)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_required": round(self.total_required, 1),
            "residential_spaces": round(self.residential_spaces, 1),
            "guest_spaces": round(self.guest_spaces, 1),
            "commercial_spaces": round(self.commercial_spaces, 1),
            "by_use": {k: round(v, 1) for k, v in self.by_use.items()},
            "reductions": {
                "transit": round(self.transit_reduction_applied, 1),
                "affordable": round(self.affordable_reduction_applied, 1),
                "shared": round(self.shared_parking_reduction, 1),
            },
        }


# =============================================================================
# PARKING CALCULATION FUNCTIONS
# =============================================================================

def calculate_residential_parking(
    units: UnitCount,
    ratios: Optional[ResidentialParkingRatios] = None,
    include_guest: bool = True
) -> Tuple[float, float, Dict[str, float]]:
    """
    Calculate required residential parking.

    Args:
        units: Unit count by type
        ratios: Parking ratios (default: standard)
        include_guest: Include guest parking

    Returns:
        Tuple of (residential_spaces, guest_spaces, breakdown_by_type)
    """
    if ratios is None:
        ratios = ResidentialParkingRatios()

    breakdown = {}
    total = 0.0

    # Studios
    if units.studio > 0:
        spaces = units.studio * ratios.studio
        breakdown["studio"] = spaces
        total += spaces

    # 1BR
    if units.one_br > 0:
        spaces = units.one_br * ratios.one_br
        breakdown["1br"] = spaces
        total += spaces

    # 2BR
    if units.two_br > 0:
        spaces = units.two_br * ratios.two_br
        breakdown["2br"] = spaces
        total += spaces

    # 3BR
    if units.three_br > 0:
        spaces = units.three_br * ratios.three_br
        breakdown["3br"] = spaces
        total += spaces

    # Penthouse (uses 3BR ratio)
    if units.penthouse > 0:
        spaces = units.penthouse * ratios.three_br
        breakdown["penthouse"] = spaces
        total += spaces

    # Guest parking
    guest = 0.0
    if include_guest:
        guest = units.total * ratios.guest_ratio
        breakdown["guest"] = guest

    return total, guest, breakdown


def calculate_commercial_parking(
    area_by_use: Dict[UseType, float],
    ratios: Optional[CommercialParkingRatios] = None
) -> Tuple[float, Dict[str, float]]:
    """
    Calculate required commercial parking.

    Args:
        area_by_use: Square footage by use type
        ratios: Parking ratios (default: standard)

    Returns:
        Tuple of (total_spaces, breakdown_by_use)
    """
    if ratios is None:
        ratios = CommercialParkingRatios()

    breakdown = {}
    total = 0.0

    for use_type, area_sf in area_by_use.items():
        ratio = ratios.get_ratio_for_use(use_type)
        # Ratio is per 1000 SF
        spaces = (area_sf / 1000) * ratio
        breakdown[use_type.value] = spaces
        total += spaces

    return total, breakdown


def calculate_parking_from_unit_mix(
    building_mix: BuildingUnitMix,
    ratios: Optional[ResidentialParkingRatios] = None,
    include_guest: bool = True,
    apply_transit_reduction: bool = False,
    apply_affordable_reduction: bool = False
) -> ParkingRequirement:
    """
    Calculate parking requirement from building unit mix.

    Args:
        building_mix: Building unit mix
        ratios: Parking ratios
        include_guest: Include guest parking
        apply_transit_reduction: Apply transit reduction
        apply_affordable_reduction: Apply affordable reduction

    Returns:
        ParkingRequirement with full breakdown
    """
    if ratios is None:
        ratios = ResidentialParkingRatios()

    units = building_mix.total_units

    residential, guest, breakdown = calculate_residential_parking(
        units, ratios, include_guest
    )

    # Apply reductions
    transit_reduction = 0.0
    affordable_reduction = 0.0

    if apply_transit_reduction and ratios.transit_reduction > 0:
        transit_reduction = residential * ratios.transit_reduction
        residential *= (1 - ratios.transit_reduction)
        guest *= (1 - ratios.transit_reduction)

    if apply_affordable_reduction and ratios.affordable_reduction > 0:
        affordable_reduction = residential * ratios.affordable_reduction
        residential *= (1 - ratios.affordable_reduction)
        guest *= (1 - ratios.affordable_reduction)

    return ParkingRequirement(
        residential_spaces=residential,
        guest_spaces=guest,
        commercial_spaces=0.0,
        by_use=breakdown,
        transit_reduction_applied=transit_reduction,
        affordable_reduction_applied=affordable_reduction,
    )


def calculate_mixed_use_parking(
    units: Optional[UnitCount] = None,
    commercial_areas: Optional[Dict[UseType, float]] = None,
    residential_ratios: Optional[ResidentialParkingRatios] = None,
    commercial_ratios: Optional[CommercialParkingRatios] = None,
    shared_parking_factor: float = 1.0
) -> ParkingRequirement:
    """
    Calculate parking for mixed-use development.

    Args:
        units: Residential unit count
        commercial_areas: Commercial SF by use type
        residential_ratios: Residential parking ratios
        commercial_ratios: Commercial parking ratios
        shared_parking_factor: Shared parking reduction (0-1, lower = more sharing)

    Returns:
        ParkingRequirement with full breakdown
    """
    result = ParkingRequirement()

    # Residential parking
    if units and units.total > 0:
        residential, guest, breakdown = calculate_residential_parking(
            units, residential_ratios, include_guest=True
        )
        result.residential_spaces = residential
        result.guest_spaces = guest
        result.by_use.update(breakdown)

    # Commercial parking
    if commercial_areas:
        commercial, breakdown = calculate_commercial_parking(
            commercial_areas, commercial_ratios
        )
        result.commercial_spaces = commercial
        result.by_use.update(breakdown)

    # Apply shared parking factor
    if shared_parking_factor < 1.0:
        original_total = result.total_required
        factor = shared_parking_factor

        result.residential_spaces *= factor
        result.guest_spaces *= factor
        result.commercial_spaces *= factor

        result.shared_parking_reduction = original_total * (1 - factor)

    return result


# =============================================================================
# PARKING ANALYSIS
# =============================================================================

def check_parking_compliance(
    provided_spaces: int,
    required: ParkingRequirement,
    min_surplus: int = 0
) -> Dict[str, Any]:
    """
    Check if provided parking meets requirement.

    Args:
        provided_spaces: Number of parking spaces provided
        required: Parking requirement
        min_surplus: Minimum surplus required

    Returns:
        Compliance result with details
    """
    total_required = required.total_required
    surplus = provided_spaces - total_required

    compliant = surplus >= min_surplus

    return {
        "compliant": compliant,
        "provided": provided_spaces,
        "required": round(total_required, 1),
        "surplus": round(surplus, 1),
        "surplus_percentage": round(surplus / total_required * 100, 1) if total_required > 0 else 0,
        "message": (
            f"Parking compliant: {provided_spaces} provided vs {round(total_required)} required"
            if compliant else
            f"Parking deficit: {provided_spaces} provided vs {round(total_required)} required"
        ),
    }


def estimate_parking_area(
    spaces: int,
    sf_per_space: float = 350,
    structured: bool = False
) -> float:
    """
    Estimate parking area required.

    Args:
        spaces: Number of parking spaces
        sf_per_space: Square feet per space (including circulation)
        structured: Whether structured parking

    Returns:
        Required parking area in SF
    """
    # Structured parking is more efficient
    if structured:
        sf_per_space = sf_per_space * 0.9

    return spaces * sf_per_space


def calculate_parking_levels(
    spaces: int,
    area_per_level: float,
    sf_per_space: float = 350
) -> int:
    """
    Calculate number of parking levels needed.

    Args:
        spaces: Number of parking spaces
        area_per_level: Available area per parking level
        sf_per_space: Square feet per space

    Returns:
        Number of parking levels
    """
    spaces_per_level = area_per_level / sf_per_space
    if spaces_per_level <= 0:
        return 0

    return int((spaces + spaces_per_level - 1) / spaces_per_level)


def get_parking_summary(
    units: UnitCount,
    ratios: Optional[ResidentialParkingRatios] = None
) -> Dict[str, Any]:
    """
    Get parking summary for units.

    Args:
        units: Unit count
        ratios: Parking ratios

    Returns:
        Summary dictionary
    """
    if ratios is None:
        ratios = ResidentialParkingRatios()

    residential, guest, breakdown = calculate_residential_parking(
        units, ratios)

    return {
        "total_units": units.total,
        "total_parking": round(residential + guest, 1),
        "residential_parking": round(residential, 1),
        "guest_parking": round(guest, 1),
        "ratio_overall": round((residential + guest) / units.total, 2) if units.total > 0 else 0,
        "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
        "ratios_used": ratios.to_dict(),
    }


# =============================================================================
# COMMON PARKING REQUIREMENTS BY JURISDICTION
# =============================================================================

def get_parking_by_jurisdiction(jurisdiction: str) -> Tuple[ResidentialParkingRatios, CommercialParkingRatios]:
    """
    Get parking ratios for common jurisdictions.

    Args:
        jurisdiction: Jurisdiction name

    Returns:
        Tuple of (residential_ratios, commercial_ratios)
    """
    # Simplified examples - real implementations would be more detailed
    jurisdictions = {
        "los_angeles": (
            ResidentialParkingRatios(
                studio=1.0, one_br=1.5, two_br=2.0, three_br=2.5,
                guest_ratio=0.25, transit_reduction=0.15
            ),
            CommercialParkingRatios(
                retail=4.0, restaurant=10.0, office=3.0,
                medical_office=4.0, industrial=1.0, warehouse=0.5
            )
        ),
        "san_francisco": (
            ResidentialParkingRatios(
                studio=0.25, one_br=0.5, two_br=0.75, three_br=1.0,
                guest_ratio=0.1, transit_reduction=0.5
            ),
            CommercialParkingRatios(
                retail=1.0, restaurant=3.0, office=1.0,
                medical_office=2.0, industrial=0.5, warehouse=0.25
            )
        ),
        "seattle": (
            ResidentialParkingRatios(
                studio=0.5, one_br=0.75, two_br=1.0, three_br=1.5,
                guest_ratio=0.15, transit_reduction=0.25
            ),
            CommercialParkingRatios(
                retail=2.5, restaurant=6.0, office=2.0,
                medical_office=3.0, industrial=0.75, warehouse=0.4
            )
        ),
        "houston": (
            ResidentialParkingRatios(
                studio=1.25, one_br=1.5, two_br=2.0, three_br=2.5,
                guest_ratio=0.25
            ),
            CommercialParkingRatios(
                retail=5.0, restaurant=12.0, office=4.0,
                medical_office=5.0, industrial=1.5, warehouse=0.75
            )
        ),
    }

    key = jurisdiction.lower().replace(" ", "_").replace("-", "_")

    if key in jurisdictions:
        return jurisdictions[key]

    # Default
    return ResidentialParkingRatios(), CommercialParkingRatios()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    'UseType',

    # Classes
    'ParkingRatio',
    'ResidentialParkingRatios',
    'CommercialParkingRatios',
    'ParkingRequirement',

    # Calculation functions
    'calculate_residential_parking',
    'calculate_commercial_parking',
    'calculate_parking_from_unit_mix',
    'calculate_mixed_use_parking',

    # Analysis functions
    'check_parking_compliance',
    'estimate_parking_area',
    'calculate_parking_levels',
    'get_parking_summary',

    # Jurisdiction presets
    'get_parking_by_jurisdiction',
]
