"""
Building Setbacks Module

Applies setback rules to create buildable envelopes for buildings.

This module bridges the constraints system (setback_rules.py, zoning.py)
with the building massing system, translating zoning requirements into
actual buildable areas.

Key concepts:
- Buildable envelope: 3D space where building can exist
- Step-backs: Upper floor setbacks from lower floor edges
- Tower vs podium: Different setbacks for base and tower portions
- Sky exposure planes: Angled setback planes from property lines

This module handles:
1. Creating buildable polygons from site and setbacks
2. Calculating floor-by-floor buildable areas with step-backs
3. Supporting different building typologies (tower, podium, courtyard)
4. Providing height-related constraints per location on site
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

from sitefit.core.geometry import Point, Polygon
from sitefit.core.operations import inset
from sitefit.constraints.setback_rules import (
    SetbackConfig, apply_setbacks, StepBackRule, SetbackType
)
from sitefit.constraints.zoning import ZoningDistrict


def _get_largest_polygon(result: List) -> Optional[Polygon]:
    """Get the largest polygon from a list, or None if empty."""
    if not result:
        return None
    return max(result, key=lambda p: p.area)


class BuildingTypology(Enum):
    """Building typologies affecting setback application."""
    BAR = "bar"               # Simple bar/slab building
    TOWER = "tower"           # Point tower
    PODIUM_TOWER = "podium_tower"  # Tower on podium
    COURTYARD = "courtyard"   # Courtyard building (donut)
    L_SHAPED = "l_shaped"     # L-shaped building
    U_SHAPED = "u_shaped"     # U-shaped building


@dataclass
class BuildableArea:
    """
    Buildable area for a specific floor or range of floors.

    Attributes:
        polygon: The buildable polygon for this floor/range
        floor_range: Tuple of (min_floor, max_floor) this applies to
        max_height: Maximum height at this location (feet)
        setback_from_property: Distance from property line
        constraints: Additional constraints/notes
    """
    polygon: Polygon
    floor_range: Tuple[int, int] = (1, 999)  # Default: all floors
    max_height: Optional[float] = None
    setback_from_property: float = 0.0
    constraints: Dict[str, Any] = field(default_factory=dict)

    @property
    def area(self) -> float:
        """Buildable area in SF."""
        return self.polygon.area

    @property
    def min_floor(self) -> int:
        """Minimum floor number."""
        return self.floor_range[0]

    @property
    def max_floor(self) -> int:
        """Maximum floor number (or 999 for unlimited)."""
        return self.floor_range[1]

    def applies_to_floor(self, floor_number: int) -> bool:
        """Check if this buildable area applies to a floor."""
        return self.min_floor <= floor_number <= self.max_floor

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "area_sf": round(self.area, 0),
            "floor_range": list(self.floor_range),
            "max_height": self.max_height,
            "setback_from_property": self.setback_from_property,
            "constraints": self.constraints
        }


@dataclass
class BuildableAreaResult:
    """
    Complete buildable area analysis for a site.

    Attributes:
        site: Original site polygon
        ground_buildable: Buildable area at ground level
        upper_buildables: List of buildable areas for upper floors
        max_height: Maximum building height
        max_floors: Maximum number of floors
        zoning: Zoning district used
        setbacks: Setback configuration used
    """
    site: Polygon
    ground_buildable: BuildableArea
    upper_buildables: List[BuildableArea] = field(default_factory=list)
    max_height: Optional[float] = None
    max_floors: Optional[int] = None
    zoning: Optional[ZoningDistrict] = None
    setbacks: Optional[SetbackConfig] = None

    @property
    def site_area(self) -> float:
        """Original site area."""
        return self.site.area

    @property
    def ground_buildable_area(self) -> float:
        """Ground floor buildable area."""
        return self.ground_buildable.area

    @property
    def coverage_ratio(self) -> float:
        """Building coverage ratio (ground buildable / site)."""
        if self.site_area == 0:
            return 0.0
        return self.ground_buildable_area / self.site_area

    def get_buildable_for_floor(self, floor_number: int) -> Optional[BuildableArea]:
        """
        Get the buildable area for a specific floor.

        Args:
            floor_number: Floor number (1-based)

        Returns:
            BuildableArea for that floor, or None if floor not allowed
        """
        # Check if floor exceeds max
        if self.max_floors and floor_number > self.max_floors:
            return None

        # Check upper floor buildables (more specific first)
        for buildable in self.upper_buildables:
            if buildable.applies_to_floor(floor_number):
                return buildable

        # Fall back to ground buildable if floor 1
        if floor_number == 1:
            return self.ground_buildable

        # For upper floors without specific rules, use ground
        return self.ground_buildable

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "site_area": round(self.site_area, 0),
            "ground_buildable_area": round(self.ground_buildable_area, 0),
            "coverage_ratio": round(self.coverage_ratio, 3),
            "max_height": self.max_height,
            "max_floors": self.max_floors,
            "ground_buildable": self.ground_buildable.to_dict(),
            "upper_buildables": [b.to_dict() for b in self.upper_buildables],
            "zoning_name": self.zoning.name if self.zoning else None
        }


# =============================================================================
# BUILDABLE AREA CALCULATION
# =============================================================================

def calculate_buildable_envelope(
    site: Polygon,
    setbacks: SetbackConfig = None,
    zoning: ZoningDistrict = None,
    step_backs: List[StepBackRule] = None
) -> BuildableAreaResult:
    """
    Calculate the complete buildable envelope for a site.

    Args:
        site: Site boundary polygon
        setbacks: Setback configuration
        zoning: Zoning district (for height/FAR limits)
        step_backs: Upper floor step-back rules

    Returns:
        BuildableAreaResult with ground and upper floor buildables

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (200,0), (200,150), (0,150)])
        >>> setbacks = SetbackConfig(front=25, side=10, rear=20)
        >>> result = calculate_buildable_envelope(site, setbacks)
        >>> result.ground_buildable_area < site.area
        True
    """
    setbacks = setbacks or SetbackConfig()
    step_backs = step_backs or []

    # Calculate ground floor buildable area
    ground_polygon = apply_setbacks(site, setbacks)

    if ground_polygon is None:
        # Setbacks too large for site
        ground_polygon = site

    ground_buildable = BuildableArea(
        polygon=ground_polygon,
        floor_range=(1, 1),
        setback_from_property=setbacks.min_setback
    )

    # Calculate upper floor buildable areas with step-backs
    upper_buildables = []

    if step_backs:
        # Group step-backs by floor they start at
        current_polygon = ground_polygon
        sorted_steps = sorted(step_backs, key=lambda s: s.applies_above_floor)

        prev_floor = 1
        for step in sorted_steps:
            # Buildable from prev_floor+1 to step.applies_above_floor
            if step.applies_above_floor > prev_floor:
                upper_buildables.append(BuildableArea(
                    polygon=current_polygon,
                    floor_range=(prev_floor + 1, step.applies_above_floor)
                ))

            # Apply step-back
            result = inset(current_polygon, step.additional_setback)
            if result:
                current_polygon = _get_largest_polygon(result)
                if current_polygon is None:
                    break
            else:
                break

            prev_floor = step.applies_above_floor

        # Remaining floors use the most-inset polygon
        if current_polygon:
            upper_buildables.append(BuildableArea(
                polygon=current_polygon,
                floor_range=(prev_floor + 1, 999)
            ))
    else:
        # No step-backs - upper floors same as ground
        upper_buildables.append(BuildableArea(
            polygon=ground_polygon,
            floor_range=(2, 999)
        ))

    # Get zoning limits
    max_height = zoning.max_height_ft if zoning else None
    max_floors = zoning.max_stories if zoning else None

    return BuildableAreaResult(
        site=site,
        ground_buildable=ground_buildable,
        upper_buildables=upper_buildables,
        max_height=max_height,
        max_floors=max_floors,
        zoning=zoning,
        setbacks=setbacks
    )


def apply_building_setbacks(
    site: Polygon,
    front: float = 25.0,
    side: float = 10.0,
    rear: float = 20.0,
    uniform: bool = False
) -> Optional[Polygon]:
    """
    Apply building setbacks to a site polygon.

    Simple convenience function for quick setback application.

    Args:
        site: Site boundary polygon
        front: Front setback distance
        side: Side setback distance
        rear: Rear setback distance
        uniform: If True, use front setback for all sides

    Returns:
        Buildable area polygon, or None if setbacks too large

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (100,0), (100,80), (0,80)])
        >>> buildable = apply_building_setbacks(site, front=20, side=10, rear=15)
        >>> buildable.area < site.area
        True
    """
    if uniform:
        config = SetbackConfig.uniform_setback(front)
    else:
        config = SetbackConfig(front=front, side=side, rear=rear)

    return apply_setbacks(site, config)


def get_buildable_area_for_floor(
    site: Polygon,
    floor_number: int,
    setbacks: SetbackConfig = None,
    step_backs: List[StepBackRule] = None
) -> Optional[Polygon]:
    """
    Get the buildable polygon for a specific floor.

    Args:
        site: Site boundary polygon
        floor_number: Floor number (1-based)
        setbacks: Base setback configuration
        step_backs: Step-back rules for upper floors

    Returns:
        Buildable polygon for that floor

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (200,0), (200,150), (0,150)])
        >>> floor1 = get_buildable_area_for_floor(site, 1)
        >>> floor5 = get_buildable_area_for_floor(site, 5, step_backs=[...])
        >>> floor5.area <= floor1.area  # Upper floors may be smaller
        True
    """
    result = calculate_buildable_envelope(
        site, setbacks, step_backs=step_backs)
    buildable = result.get_buildable_for_floor(floor_number)

    if buildable:
        return buildable.polygon
    return None


def calculate_step_backs(
    site: Polygon,
    setbacks: SetbackConfig,
    step_back_floors: List[int],
    step_back_distances: List[float]
) -> List[Polygon]:
    """
    Calculate buildable polygons at each step-back level.

    Args:
        site: Site boundary polygon
        setbacks: Base setback configuration
        step_back_floors: Floor numbers where step-backs occur
        step_back_distances: Step-back distances at each floor

    Returns:
        List of buildable polygons (one per level)

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (200,0), (200,150), (0,150)])
        >>> setbacks = SetbackConfig.residential()
        >>> polygons = calculate_step_backs(site, setbacks, [3, 6], [10, 15])
        >>> len(polygons)
        3  # Ground, floors 3-5, floors 6+
    """
    # Start with base buildable area
    base_polygon = apply_setbacks(site, setbacks)
    if base_polygon is None:
        return []

    polygons = [base_polygon]
    current = base_polygon

    for distance in step_back_distances:
        result = inset(current, distance)
        if result:
            current = _get_largest_polygon(result)
            if current:
                polygons.append(current)
            else:
                break
        else:
            break

    return polygons


# =============================================================================
# BUILDING ENVELOPE ANALYSIS
# =============================================================================

def calculate_max_building_area(
    site: Polygon,
    setbacks: SetbackConfig,
    zoning: ZoningDistrict,
    floor_height: float = 10.0
) -> Dict[str, float]:
    """
    Calculate maximum possible building area under zoning.

    Args:
        site: Site boundary polygon
        setbacks: Setback configuration
        zoning: Zoning district
        floor_height: Typical floor height

    Returns:
        Dictionary with area calculations
    """
    # Get buildable area
    buildable = apply_setbacks(site, setbacks)
    if buildable is None:
        return {
            "site_area": site.area,
            "buildable_area": 0,
            "max_floors": 0,
            "max_building_area": 0
        }

    buildable_area = buildable.area

    # Max floors from height
    if zoning.max_height_ft > 0:
        # First floor is typically taller
        remaining = zoning.max_height_ft - 15  # Ground floor at 15'
        max_floors = 1 + max(0, int(remaining / floor_height))
    else:
        max_floors = zoning.max_stories

    # Limit by zoning stories
    max_floors = min(max_floors, zoning.max_stories)

    # Max building area from floors
    max_from_floors = buildable_area * max_floors

    # Max from FAR
    max_from_far = site.area * zoning.max_far

    # Actual max is the lesser
    max_building_area = min(max_from_floors, max_from_far)

    # Adjust floors if FAR is limiting
    if max_from_far < max_from_floors:
        max_floors = int(max_from_far / buildable_area)

    return {
        "site_area": round(site.area, 0),
        "buildable_area": round(buildable_area, 0),
        "coverage_ratio": round(buildable_area / site.area, 3),
        "max_floors": max_floors,
        "max_height": zoning.max_height_ft,
        "max_far": zoning.max_far,
        "max_building_area": round(max_building_area, 0),
        "far_limiting": max_from_far < max_from_floors,
        "height_limiting": max_from_floors <= max_from_far
    }


def estimate_floor_count(
    total_building_area: float,
    floor_plate_area: float,
    max_floors: int = 999
) -> int:
    """
    Estimate number of floors needed for a target building area.

    Args:
        total_building_area: Target gross building area
        floor_plate_area: Area per floor
        max_floors: Maximum allowed floors

    Returns:
        Number of floors needed
    """
    if floor_plate_area <= 0:
        return 0

    floors = math.ceil(total_building_area / floor_plate_area)
    return min(floors, max_floors)


def check_building_envelope_compliance(
    site: Polygon,
    building_footprint: Polygon,
    building_height: float,
    setbacks: SetbackConfig,
    zoning: ZoningDistrict
) -> Dict[str, Any]:
    """
    Check if a building complies with setback and zoning requirements.

    Args:
        site: Site boundary polygon
        building_footprint: Proposed building footprint
        building_height: Proposed building height
        setbacks: Required setbacks
        zoning: Zoning district

    Returns:
        Compliance check results
    """
    violations = []
    warnings = []

    # Get required buildable area
    buildable = apply_setbacks(site, setbacks)
    if buildable is None:
        violations.append("Setbacks exceed site dimensions")
        return {
            "compliant": False,
            "violations": violations,
            "warnings": warnings
        }

    # Check if building is within buildable area
    # Simplified check: compare areas
    if building_footprint.area > buildable.area:
        violations.append(
            f"Building footprint {building_footprint.area:.0f} SF "
            f"exceeds buildable area {buildable.area:.0f} SF"
        )

    # Check height
    if building_height > zoning.max_height_ft:
        violations.append(
            f"Building height {building_height:.0f}' exceeds "
            f"maximum {zoning.max_height_ft:.0f}'"
        )
    elif building_height > zoning.max_height_ft * 0.9:
        warnings.append(
            f"Building height {building_height:.0f}' is near "
            f"maximum {zoning.max_height_ft:.0f}'"
        )

    # Check lot coverage
    coverage = building_footprint.area / site.area
    if coverage > zoning.max_lot_coverage:
        violations.append(
            f"Lot coverage {coverage:.1%} exceeds "
            f"maximum {zoning.max_lot_coverage:.1%}"
        )

    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "building_footprint": round(building_footprint.area, 0),
        "buildable_area": round(buildable.area, 0),
        "coverage": round(coverage, 3),
        "height": building_height
    }
