"""
Zoning Module

Defines zoning district parameters and validates building designs
against zoning requirements.

Key zoning parameters:
- FAR (Floor Area Ratio): Total building SF / Lot SF
- Lot Coverage: Building footprint / Lot area
- Height Limit: Maximum building height
- Density: Maximum units per acre

Common zoning districts:
- R-1: Single-family residential (low density)
- R-3: Multi-family residential (high density)
- C-1: Commercial (neighborhood)
- C-3: Commercial (regional)
- M-1: Industrial (light)
- MU: Mixed-use

This module handles:
1. Defining zoning district parameters
2. Calculating FAR from building design
3. Checking lot coverage limits
4. Validating height restrictions
5. Calculating maximum allowable building area
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

from sitefit.core.geometry import Polygon


class ZoningType(Enum):
    """Standard zoning district types."""
    R1 = "R-1"      # Single-family residential
    R2 = "R-2"      # Two-family residential
    R3 = "R-3"      # Multi-family residential
    R4 = "R-4"      # High-density residential
    C1 = "C-1"      # Neighborhood commercial
    C2 = "C-2"      # Community commercial
    C3 = "C-3"      # Regional commercial
    M1 = "M-1"      # Light industrial
    M2 = "M-2"      # Heavy industrial
    MU = "MU"       # Mixed-use
    PD = "PD"       # Planned development
    CUSTOM = "custom"


@dataclass
class ZoningDistrict:
    """
    Zoning district definition with all constraints.

    Attributes:
        name: District name/code
        zoning_type: Type classification
        max_far: Maximum Floor Area Ratio
        max_lot_coverage: Maximum lot coverage (0-1)
        max_height_ft: Maximum building height in feet
        max_stories: Maximum number of stories
        max_density: Maximum units per acre
        min_lot_size: Minimum lot size in SF
        min_open_space: Minimum open space ratio (0-1)
        parking_ratio: Required parking stalls per unit
        description: Human-readable description
    """
    name: str
    zoning_type: ZoningType = ZoningType.CUSTOM
    max_far: float = 1.0
    max_lot_coverage: float = 0.5
    max_height_ft: float = 35.0
    max_stories: int = 3
    max_density: Optional[float] = None  # Units per acre
    min_lot_size: float = 0.0
    min_open_space: float = 0.0
    parking_ratio: float = 1.0  # Stalls per unit
    description: str = ""

    def __post_init__(self):
        if self.max_far < 0:
            raise ValueError("FAR cannot be negative")
        if not 0 <= self.max_lot_coverage <= 1:
            raise ValueError("Lot coverage must be between 0 and 1")
        if self.max_height_ft < 0:
            raise ValueError("Height cannot be negative")

    @property
    def max_height_stories(self) -> int:
        """Max stories based on height (assuming 12' per floor)."""
        return min(self.max_stories, int(self.max_height_ft / 12))

    @classmethod
    def residential_low(cls, name: str = "R-1") -> ZoningDistrict:
        """Low-density residential district."""
        return cls(
            name=name,
            zoning_type=ZoningType.R1,
            max_far=0.5,
            max_lot_coverage=0.4,
            max_height_ft=35.0,
            max_stories=2,
            max_density=8,  # 8 units/acre
            parking_ratio=2.0,
            description="Low-density single-family residential"
        )

    @classmethod
    def residential_medium(cls, name: str = "R-3") -> ZoningDistrict:
        """Medium-density residential district."""
        return cls(
            name=name,
            zoning_type=ZoningType.R3,
            max_far=1.5,
            max_lot_coverage=0.6,
            max_height_ft=45.0,
            max_stories=4,
            max_density=30,  # 30 units/acre
            parking_ratio=1.5,
            description="Medium-density multi-family residential"
        )

    @classmethod
    def residential_high(cls, name: str = "R-4") -> ZoningDistrict:
        """High-density residential district."""
        return cls(
            name=name,
            zoning_type=ZoningType.R4,
            max_far=3.0,
            max_lot_coverage=0.7,
            max_height_ft=75.0,
            max_stories=6,
            max_density=60,  # 60 units/acre
            parking_ratio=1.0,
            description="High-density multi-family residential"
        )

    @classmethod
    def commercial_neighborhood(cls, name: str = "C-1") -> ZoningDistrict:
        """Neighborhood commercial district."""
        return cls(
            name=name,
            zoning_type=ZoningType.C1,
            max_far=1.0,
            max_lot_coverage=0.6,
            max_height_ft=35.0,
            max_stories=2,
            parking_ratio=4.0,  # Per 1000 SF
            description="Neighborhood commercial"
        )

    @classmethod
    def commercial_regional(cls, name: str = "C-3") -> ZoningDistrict:
        """Regional commercial district."""
        return cls(
            name=name,
            zoning_type=ZoningType.C3,
            max_far=2.5,
            max_lot_coverage=0.7,
            max_height_ft=60.0,
            max_stories=5,
            parking_ratio=4.0,  # Per 1000 SF
            description="Regional commercial"
        )

    @classmethod
    def mixed_use(cls, name: str = "MU") -> ZoningDistrict:
        """Mixed-use district."""
        return cls(
            name=name,
            zoning_type=ZoningType.MU,
            max_far=4.0,
            max_lot_coverage=0.8,
            max_height_ft=85.0,
            max_stories=7,
            max_density=100,
            parking_ratio=1.0,
            description="Mixed-use residential and commercial"
        )

    @classmethod
    def industrial_light(cls, name: str = "M-1") -> ZoningDistrict:
        """Light industrial district."""
        return cls(
            name=name,
            zoning_type=ZoningType.M1,
            max_far=1.0,
            max_lot_coverage=0.6,
            max_height_ft=45.0,
            max_stories=3,
            parking_ratio=1.0,  # Per 1000 SF
            description="Light industrial/manufacturing"
        )


@dataclass
class ZoningConfig:
    """
    Site-specific zoning configuration.

    Combines district rules with site-specific overrides or conditions.
    """
    district: ZoningDistrict
    lot_area: float  # Site area in SF
    bonuses: Dict[str, float] = field(default_factory=dict)  # FAR bonuses
    restrictions: Dict[str, Any] = field(default_factory=dict)

    @property
    def effective_far(self) -> float:
        """FAR including any bonuses."""
        base_far = self.district.max_far
        bonus_far = sum(self.bonuses.values())
        return base_far + bonus_far

    @property
    def max_building_area(self) -> float:
        """Maximum total building area based on FAR."""
        return self.lot_area * self.effective_far

    @property
    def max_footprint(self) -> float:
        """Maximum building footprint based on lot coverage."""
        return self.lot_area * self.district.max_lot_coverage


@dataclass
class ZoningResult:
    """
    Result of zoning validation.

    Attributes:
        compliant: Whether the design meets all zoning requirements
        far: Calculated FAR
        lot_coverage: Calculated lot coverage
        height: Building height
        violations: List of zoning violations
        warnings: List of warnings (near limits)
    """
    compliant: bool
    far: float
    lot_coverage: float
    height: float
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "compliant": self.compliant,
            "far": round(self.far, 3),
            "lot_coverage": round(self.lot_coverage, 3),
            "height": round(self.height, 1),
            "violations": self.violations,
            "warnings": self.warnings,
            "details": self.details
        }


# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================

def calculate_far(
    total_building_area: float,
    lot_area: float
) -> float:
    """
    Calculate Floor Area Ratio.

    FAR = Total Building Area / Lot Area

    Args:
        total_building_area: Total gross floor area of building
        lot_area: Total lot/site area

    Returns:
        FAR value

    Examples:
        >>> calculate_far(30000, 10000)
        3.0
    """
    if lot_area <= 0:
        raise ValueError("Lot area must be positive")
    return total_building_area / lot_area


def calculate_lot_coverage(
    footprint_area: float,
    lot_area: float
) -> float:
    """
    Calculate lot coverage ratio.

    Lot Coverage = Building Footprint / Lot Area

    Args:
        footprint_area: Building footprint area
        lot_area: Total lot area

    Returns:
        Lot coverage ratio (0-1)

    Examples:
        >>> calculate_lot_coverage(5000, 10000)
        0.5
    """
    if lot_area <= 0:
        raise ValueError("Lot area must be positive")
    return footprint_area / lot_area


def check_height_limit(
    building_height: float,
    max_height: float,
    tolerance: float = 0.0
) -> Tuple[bool, float]:
    """
    Check if building height is within limit.

    Args:
        building_height: Proposed building height
        max_height: Maximum allowed height
        tolerance: Allowed overage (for parapet, equipment, etc.)

    Returns:
        Tuple of (passes, margin)
    """
    margin = max_height + tolerance - building_height
    passes = margin >= 0
    return passes, margin


def check_lot_coverage(
    footprint_area: float,
    lot_area: float,
    max_coverage: float
) -> Tuple[bool, float]:
    """
    Check if lot coverage is within limit.

    Args:
        footprint_area: Building footprint area
        lot_area: Total lot area
        max_coverage: Maximum allowed coverage (0-1)

    Returns:
        Tuple of (passes, margin as ratio)
    """
    actual_coverage = calculate_lot_coverage(footprint_area, lot_area)
    margin = max_coverage - actual_coverage
    passes = margin >= 0
    return passes, margin


def calculate_max_building_area(
    lot_area: float,
    far: float
) -> float:
    """
    Calculate maximum building area from FAR.

    Args:
        lot_area: Site area in SF
        far: Maximum FAR

    Returns:
        Maximum total building area in SF

    Examples:
        >>> calculate_max_building_area(10000, 2.5)
        25000.0
    """
    return lot_area * far


def calculate_max_floors_from_height(
    max_height: float,
    floor_height: float = 12.0,
    ground_floor_height: float = 15.0
) -> int:
    """
    Calculate maximum floors from height limit.

    Args:
        max_height: Maximum building height in feet
        floor_height: Typical floor-to-floor height
        ground_floor_height: Ground floor height (often taller)

    Returns:
        Maximum number of floors
    """
    if max_height <= 0:
        return 0

    # Ground floor is taller
    if max_height < ground_floor_height:
        return 0 if max_height < floor_height else 1

    remaining = max_height - ground_floor_height
    upper_floors = int(remaining / floor_height)
    return 1 + upper_floors


def calculate_max_units(
    lot_area: float,
    density: float
) -> int:
    """
    Calculate maximum units from density limit.

    Args:
        lot_area: Site area in SF
        density: Maximum units per acre

    Returns:
        Maximum number of units

    Examples:
        >>> calculate_max_units(43560, 20)  # 1 acre at 20 DU/acre
        20
    """
    acres = lot_area / 43560  # SF per acre
    return int(acres * density)


def calculate_required_parking(
    unit_count: int,
    parking_ratio: float,
    commercial_sf: float = 0,
    commercial_ratio: float = 4.0
) -> int:
    """
    Calculate required parking stalls.

    Args:
        unit_count: Number of residential units
        parking_ratio: Stalls per unit
        commercial_sf: Commercial square footage
        commercial_ratio: Stalls per 1000 SF commercial

    Returns:
        Required parking stalls
    """
    residential_stalls = unit_count * parking_ratio
    commercial_stalls = (commercial_sf / 1000) * commercial_ratio
    return int(math.ceil(residential_stalls + commercial_stalls))


# =============================================================================
# VALIDATION
# =============================================================================

def validate_zoning(
    lot_area: float,
    building_footprint: float,
    total_building_area: float,
    building_height: float,
    district: ZoningDistrict,
    unit_count: int = 0
) -> ZoningResult:
    """
    Validate a building design against zoning requirements.

    Args:
        lot_area: Site area in SF
        building_footprint: Building footprint area
        total_building_area: Total building gross floor area
        building_height: Building height in feet
        district: Zoning district rules
        unit_count: Number of units (for density check)

    Returns:
        ZoningResult with compliance status and details
    """
    violations = []
    warnings = []

    # Calculate metrics
    far = calculate_far(total_building_area, lot_area)
    lot_coverage = calculate_lot_coverage(building_footprint, lot_area)

    # Check FAR
    if far > district.max_far:
        violations.append(
            f"FAR {far:.2f} exceeds maximum {district.max_far:.2f}"
        )
    elif far > district.max_far * 0.9:
        warnings.append(
            f"FAR {far:.2f} is near maximum {district.max_far:.2f}"
        )

    # Check lot coverage
    if lot_coverage > district.max_lot_coverage:
        violations.append(
            f"Lot coverage {lot_coverage:.1%} exceeds maximum {district.max_lot_coverage:.1%}"
        )
    elif lot_coverage > district.max_lot_coverage * 0.9:
        warnings.append(
            f"Lot coverage {lot_coverage:.1%} is near maximum {district.max_lot_coverage:.1%}"
        )

    # Check height
    if building_height > district.max_height_ft:
        violations.append(
            f"Height {building_height:.0f}' exceeds maximum {district.max_height_ft:.0f}'"
        )
    elif building_height > district.max_height_ft * 0.9:
        warnings.append(
            f"Height {building_height:.0f}' is near maximum {district.max_height_ft:.0f}'"
        )

    # Check density if applicable
    if unit_count > 0 and district.max_density:
        max_units = calculate_max_units(lot_area, district.max_density)
        if unit_count > max_units:
            violations.append(
                f"Unit count {unit_count} exceeds maximum {max_units}"
            )

    # Build result
    compliant = len(violations) == 0

    return ZoningResult(
        compliant=compliant,
        far=far,
        lot_coverage=lot_coverage,
        height=building_height,
        violations=violations,
        warnings=warnings,
        details={
            "max_far": district.max_far,
            "max_lot_coverage": district.max_lot_coverage,
            "max_height": district.max_height_ft,
            "far_margin": district.max_far - far,
            "coverage_margin": district.max_lot_coverage - lot_coverage,
            "height_margin": district.max_height_ft - building_height
        }
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_common_zoning(zone_type: str) -> ZoningDistrict:
    """
    Get a common zoning district by type name.

    Args:
        zone_type: "R-1", "R-3", "R-4", "C-1", "C-3", "MU", "M-1"

    Returns:
        ZoningDistrict configuration
    """
    zones = {
        "R-1": ZoningDistrict.residential_low,
        "R-2": lambda: ZoningDistrict(
            name="R-2",
            zoning_type=ZoningType.R2,
            max_far=0.75,
            max_lot_coverage=0.45,
            max_height_ft=35.0,
            max_stories=2,
            max_density=15
        ),
        "R-3": ZoningDistrict.residential_medium,
        "R-4": ZoningDistrict.residential_high,
        "C-1": ZoningDistrict.commercial_neighborhood,
        "C-2": lambda: ZoningDistrict(
            name="C-2",
            zoning_type=ZoningType.C2,
            max_far=1.5,
            max_lot_coverage=0.65,
            max_height_ft=45.0,
            max_stories=3
        ),
        "C-3": ZoningDistrict.commercial_regional,
        "MU": ZoningDistrict.mixed_use,
        "M-1": ZoningDistrict.industrial_light,
        "M-2": lambda: ZoningDistrict(
            name="M-2",
            zoning_type=ZoningType.M2,
            max_far=0.75,
            max_lot_coverage=0.5,
            max_height_ft=60.0,
            max_stories=4
        ),
    }

    factory = zones.get(zone_type.upper())
    if factory is None:
        raise ValueError(f"Unknown zoning type: {zone_type}")

    return factory()


def analyze_site_potential(
    site: Polygon,
    district: ZoningDistrict
) -> Dict[str, Any]:
    """
    Analyze development potential of a site under zoning.

    Args:
        site: Site boundary polygon
        district: Zoning district

    Returns:
        Dictionary with development metrics
    """
    lot_area = site.area

    max_footprint = lot_area * district.max_lot_coverage
    max_building_area = lot_area * district.max_far
    max_floors = district.max_height_stories

    # Estimate buildable area per floor (assuming footprint)
    area_per_floor = max_footprint

    # Estimate max units
    max_units = None
    if district.max_density:
        max_units = calculate_max_units(lot_area, district.max_density)

    # Required parking
    required_parking = None
    if max_units:
        required_parking = calculate_required_parking(
            max_units,
            district.parking_ratio
        )

    return {
        "lot_area_sf": round(lot_area, 0),
        "lot_area_acres": round(lot_area / 43560, 3),
        "max_footprint_sf": round(max_footprint, 0),
        "max_building_area_sf": round(max_building_area, 0),
        "max_floors": max_floors,
        "max_height_ft": district.max_height_ft,
        "max_units": max_units,
        "required_parking": required_parking,
        "max_far": district.max_far,
        "max_lot_coverage": district.max_lot_coverage,
        "zoning_type": district.name
    }
