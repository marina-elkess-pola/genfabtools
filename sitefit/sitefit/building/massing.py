"""
building/massing.py - Building Massing Module

Stacks floor plates into 3D building mass with step-backs.
Tracks total building area and validates against zoning constraints.

Depends on: floor_plate.py, setbacks.py, constraints/zoning.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Tuple, Any

from sitefit.core.geometry import Polygon, Point
from sitefit.core.operations import inset
from sitefit.building.floor_plate import (
    FloorPlate, FloorType, FloorConfig,
    create_floor_plate, calculate_gross_area, calculate_net_area,
    calculate_total_height
)
from sitefit.building.setbacks import (
    BuildableAreaResult, calculate_buildable_envelope
)
from sitefit.constraints.zoning import ZoningDistrict, validate_zoning
from sitefit.constraints.setback_rules import SetbackConfig


class MassingType(Enum):
    """Building massing typology."""
    BAR = "bar"                     # Simple rectangular bar
    TOWER = "tower"                 # Point tower
    PODIUM_TOWER = "podium_tower"   # Wide podium with tower above
    SLAB = "slab"                   # Wide, shallow floor plate
    COURTYARD = "courtyard"         # U or O shaped with courtyard
    L_SHAPED = "l_shaped"           # L-shaped footprint
    STEPPED = "stepped"             # Multiple step-backs


@dataclass
class StepBack:
    """Defines a step-back at a specific floor."""
    floor_number: int           # Floor where step-back starts
    inset_distance: float       # How far to inset (feet)
    # Which edges: 'front', 'side', 'rear', 'all'
    edges: Optional[List[str]] = None

    def __post_init__(self):
        if self.edges is None:
            self.edges = ['all']


@dataclass
class MassingConfig:
    """Configuration for building massing."""
    floor_config: FloorConfig = field(default_factory=FloorConfig)
    massing_type: MassingType = MassingType.BAR
    step_backs: List[StepBack] = field(default_factory=list)

    # Podium configuration (for PODIUM_TOWER type)
    podium_floors: int = 0
    tower_floor_plate_ratio: float = 0.6  # Tower is 60% of podium footprint

    # Tower configuration
    tower_setback: float = 15.0  # Feet from podium edge

    # Height limits
    max_floors: Optional[int] = None
    max_height: Optional[float] = None  # Feet

    @classmethod
    def residential_tower(cls) -> 'MassingConfig':
        """Preset for residential tower."""
        return cls(
            floor_config=FloorConfig.residential(),
            massing_type=MassingType.TOWER,
            max_floors=20,
        )

    @classmethod
    def residential_podium(cls, podium_floors: int = 5) -> 'MassingConfig':
        """Preset for residential podium with tower."""
        return cls(
            floor_config=FloorConfig.residential(),
            massing_type=MassingType.PODIUM_TOWER,
            podium_floors=podium_floors,
            tower_floor_plate_ratio=0.5,
            max_floors=25,
        )

    @classmethod
    def office_building(cls) -> 'MassingConfig':
        """Preset for office building."""
        return cls(
            floor_config=FloorConfig.office(),
            massing_type=MassingType.SLAB,
            max_floors=15,
        )

    @classmethod
    def mixed_use(cls, retail_floors: int = 1) -> 'MassingConfig':
        """Preset for mixed-use with retail podium."""
        return cls(
            floor_config=FloorConfig.residential(),
            massing_type=MassingType.PODIUM_TOWER,
            podium_floors=retail_floors,
            tower_floor_plate_ratio=0.7,
        )


@dataclass
class BuildingMass:
    """
    Represents a complete building massing.

    Contains all floor plates stacked vertically.
    """
    floors: List[FloorPlate]
    config: MassingConfig
    site_polygon: Polygon
    buildable_polygon: Polygon

    @property
    def num_floors(self) -> int:
        """Total number of floors."""
        return len(self.floors)

    @property
    def total_height(self) -> float:
        """Total building height in feet."""
        return calculate_total_height(self.floors)

    @property
    def gross_floor_area(self) -> float:
        """Total gross floor area (GFA) in square feet."""
        return calculate_gross_area(self.floors)

    @property
    def net_floor_area(self) -> float:
        """Total net floor area in square feet."""
        return calculate_net_area(self.floors)

    @property
    def site_area(self) -> float:
        """Site area in square feet."""
        return self.site_polygon.area

    @property
    def building_footprint(self) -> float:
        """Ground floor footprint in square feet."""
        if self.floors:
            return self.floors[0].gross_area
        return 0.0

    @property
    def lot_coverage(self) -> float:
        """Lot coverage ratio (footprint / site area)."""
        if self.site_area > 0:
            return self.building_footprint / self.site_area
        return 0.0

    @property
    def floor_area_ratio(self) -> float:
        """Floor Area Ratio (GFA / site area)."""
        if self.site_area > 0:
            return self.gross_floor_area / self.site_area
        return 0.0

    @property
    def average_floor_area(self) -> float:
        """Average floor plate size."""
        if self.floors:
            return self.gross_floor_area / len(self.floors)
        return 0.0

    @property
    def efficiency(self) -> float:
        """Overall building efficiency (net / gross)."""
        if self.gross_floor_area > 0:
            return self.net_floor_area / self.gross_floor_area
        return 0.0

    def get_floor(self, floor_number: int) -> Optional[FloorPlate]:
        """Get floor plate by floor number (1-indexed)."""
        for floor in self.floors:
            if floor.floor_number == floor_number:
                return floor
        return None

    def get_floors_by_type(self, floor_type: FloorType) -> List[FloorPlate]:
        """Get all floors of a specific type."""
        return [f for f in self.floors if f.floor_type == floor_type]

    def get_area_by_floor_type(self) -> Dict[FloorType, float]:
        """Get gross area breakdown by floor type."""
        result = {}
        for floor in self.floors:
            if floor.floor_type not in result:
                result[floor.floor_type] = 0.0
            result[floor.floor_type] += floor.gross_area
        return result

    def get_elevation_at_floor(self, floor_number: int) -> float:
        """Get elevation at top of specified floor."""
        floor = self.get_floor(floor_number)
        if floor:
            return floor.elevation + floor.floor_height
        return 0.0

    def validate_zoning(self, zoning: ZoningDistrict) -> Dict[str, Any]:
        """Validate building against zoning requirements."""
        return validate_zoning(
            site_area=self.site_area,
            building_area=self.gross_floor_area,
            building_height=self.total_height,
            lot_coverage=self.lot_coverage,
            zoning=zoning
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "num_floors": self.num_floors,
            "total_height_ft": round(self.total_height, 1),
            "gross_floor_area_sf": round(self.gross_floor_area, 0),
            "net_floor_area_sf": round(self.net_floor_area, 0),
            "site_area_sf": round(self.site_area, 0),
            "building_footprint_sf": round(self.building_footprint, 0),
            "lot_coverage": round(self.lot_coverage, 3),
            "floor_area_ratio": round(self.floor_area_ratio, 2),
            "efficiency": round(self.efficiency, 3),
            "massing_type": self.config.massing_type.value,
            "floors": [f.to_dict() for f in self.floors],
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_largest_polygon(polygons: List[Polygon]) -> Optional[Polygon]:
    """Get the largest polygon from a list."""
    if not polygons:
        return None
    return max(polygons, key=lambda p: p.area)


def _apply_step_back(polygon: Polygon, step_back: StepBack) -> Polygon:
    """
    Apply a step-back to a polygon.

    For simplicity, this insets the entire polygon. Edge-specific
    step-backs would require more complex geometry operations.
    """
    if step_back.inset_distance <= 0:
        return polygon

    inset_result = inset(polygon, step_back.inset_distance)
    if isinstance(inset_result, list):
        result = _get_largest_polygon(inset_result)
        return result if result else polygon
    return inset_result if inset_result else polygon


def _calculate_max_floors(
    height_limit: Optional[float],
    config: FloorConfig,
    max_floors_config: Optional[int] = None
) -> Optional[int]:
    """Calculate maximum floors from height limit."""
    if height_limit is None and max_floors_config is None:
        return None

    floors_from_height = None
    if height_limit:
        # Floor 1 is ground floor height, rest are typical
        remaining_height = height_limit - config.ground_floor_height
        if remaining_height > 0:
            typical_floors = int(remaining_height /
                                 config.floor_to_floor_height)
            floors_from_height = 1 + typical_floors
        else:
            floors_from_height = 1

    if floors_from_height and max_floors_config:
        return min(floors_from_height, max_floors_config)

    return floors_from_height or max_floors_config


# =============================================================================
# MASSING GENERATION
# =============================================================================

def generate_bar_massing(
    buildable_polygon: Polygon,
    num_floors: int,
    config: MassingConfig,
    site_polygon: Optional[Polygon] = None
) -> BuildingMass:
    """
    Generate simple bar (rectangular) massing.

    All floors have the same footprint (no step-backs by default).
    """
    floors = []
    current_polygon = buildable_polygon

    for floor_num in range(1, num_floors + 1):
        # Check for step-backs at this floor
        for step_back in config.step_backs:
            if step_back.floor_number == floor_num:
                current_polygon = _apply_step_back(current_polygon, step_back)

        # Determine floor type
        if floor_num == 1:
            floor_type = FloorType.GROUND
        else:
            floor_type = FloorType.TYPICAL

        floor = create_floor_plate(
            current_polygon,
            floor_number=floor_num,
            floor_type=floor_type,
            config=config.floor_config
        )
        floors.append(floor)

    return BuildingMass(
        floors=floors,
        config=config,
        site_polygon=site_polygon or buildable_polygon,
        buildable_polygon=buildable_polygon
    )


def generate_podium_tower_massing(
    buildable_polygon: Polygon,
    num_floors: int,
    config: MassingConfig,
    site_polygon: Optional[Polygon] = None
) -> BuildingMass:
    """
    Generate podium with tower massing.

    Lower floors are full podium footprint, upper floors are reduced tower.
    """
    floors = []
    podium_floors = config.podium_floors or 5
    tower_ratio = config.tower_floor_plate_ratio

    # Generate podium floors
    for floor_num in range(1, min(podium_floors + 1, num_floors + 1)):
        if floor_num == 1:
            floor_type = FloorType.GROUND
        else:
            floor_type = FloorType.PODIUM

        floor = create_floor_plate(
            buildable_polygon,
            floor_number=floor_num,
            floor_type=floor_type,
            config=config.floor_config
        )
        floors.append(floor)

    # Generate tower floors (inset from podium)
    if num_floors > podium_floors:
        # Calculate tower inset to achieve target ratio
        # For simplicity, use uniform inset
        tower_inset = config.tower_setback

        tower_polygon_result = inset(buildable_polygon, tower_inset)
        if isinstance(tower_polygon_result, list):
            tower_polygon = _get_largest_polygon(tower_polygon_result)
        else:
            tower_polygon = tower_polygon_result

        if tower_polygon and tower_polygon.area > 0:
            for floor_num in range(podium_floors + 1, num_floors + 1):
                floor = create_floor_plate(
                    tower_polygon,
                    floor_number=floor_num,
                    floor_type=FloorType.TYPICAL,
                    config=config.floor_config
                )
                floors.append(floor)

    return BuildingMass(
        floors=floors,
        config=config,
        site_polygon=site_polygon or buildable_polygon,
        buildable_polygon=buildable_polygon
    )


def generate_stepped_massing(
    buildable_polygon: Polygon,
    num_floors: int,
    step_backs: List[StepBack],
    config: MassingConfig,
    site_polygon: Optional[Polygon] = None
) -> BuildingMass:
    """
    Generate massing with multiple step-backs.

    Each step-back reduces the floor plate at specified floors.
    """
    floors = []
    current_polygon = buildable_polygon

    # Sort step-backs by floor number
    sorted_step_backs = sorted(step_backs, key=lambda sb: sb.floor_number)
    step_back_index = 0

    for floor_num in range(1, num_floors + 1):
        # Apply any step-backs for this floor
        while (step_back_index < len(sorted_step_backs) and
               sorted_step_backs[step_back_index].floor_number <= floor_num):
            current_polygon = _apply_step_back(
                current_polygon,
                sorted_step_backs[step_back_index]
            )
            step_back_index += 1

        # Determine floor type
        if floor_num == 1:
            floor_type = FloorType.GROUND
        else:
            floor_type = FloorType.TYPICAL

        floor = create_floor_plate(
            current_polygon,
            floor_number=floor_num,
            floor_type=floor_type,
            config=config.floor_config
        )
        floors.append(floor)

    return BuildingMass(
        floors=floors,
        config=config,
        site_polygon=site_polygon or buildable_polygon,
        buildable_polygon=buildable_polygon
    )


def generate_massing(
    buildable_polygon: Polygon,
    num_floors: int,
    config: Optional[MassingConfig] = None,
    site_polygon: Optional[Polygon] = None
) -> BuildingMass:
    """
    Generate building massing based on configuration.

    Args:
        buildable_polygon: The buildable area polygon
        num_floors: Number of floors to generate
        config: Massing configuration (default: bar building)
        site_polygon: Original site polygon (for FAR calculations)

    Returns:
        BuildingMass object with all floor plates
    """
    if config is None:
        config = MassingConfig()

    if config.massing_type == MassingType.PODIUM_TOWER:
        return generate_podium_tower_massing(
            buildable_polygon, num_floors, config, site_polygon
        )
    elif config.massing_type == MassingType.STEPPED or config.step_backs:
        return generate_stepped_massing(
            buildable_polygon, num_floors, config.step_backs, config, site_polygon
        )
    else:
        # Default to bar massing
        return generate_bar_massing(
            buildable_polygon, num_floors, config, site_polygon
        )


# =============================================================================
# MASSING FROM ZONING
# =============================================================================

def generate_massing_from_zoning(
    site_polygon: Polygon,
    setbacks: SetbackConfig,
    zoning: ZoningDistrict,
    config: Optional[MassingConfig] = None
) -> BuildingMass:
    """
    Generate maximum allowed building massing given zoning constraints.

    Args:
        site_polygon: Site boundary polygon
        setbacks: Setback configuration
        zoning: Zoning district with FAR, height, coverage limits
        config: Massing configuration

    Returns:
        BuildingMass that maximizes building area within zoning limits
    """
    if config is None:
        config = MassingConfig()

    # Calculate buildable envelope
    envelope = calculate_buildable_envelope(site_polygon, setbacks, zoning)

    # Determine max floors from height and config
    max_floors = _calculate_max_floors(
        envelope.max_height,
        config.floor_config,
        config.max_floors
    )

    if max_floors is None:
        max_floors = 10  # Default if no limit

    # Generate massing
    massing = generate_massing(
        envelope.ground_buildable.polygon,
        max_floors,
        config,
        site_polygon
    )

    # Check FAR and reduce floors if needed
    if zoning.max_far:
        max_gfa = site_polygon.area * zoning.max_far

        while massing.gross_floor_area > max_gfa and massing.num_floors > 1:
            # Reduce by one floor
            massing = generate_massing(
                envelope.ground_buildable.polygon,
                massing.num_floors - 1,
                config,
                site_polygon
            )

    return massing


def generate_massing_to_target(
    site_polygon: Polygon,
    setbacks: SetbackConfig,
    target_gfa: float,
    config: Optional[MassingConfig] = None,
    zoning: Optional[ZoningDistrict] = None
) -> BuildingMass:
    """
    Generate building massing to achieve target GFA.

    Args:
        site_polygon: Site boundary polygon
        setbacks: Setback configuration
        target_gfa: Target gross floor area in square feet
        config: Massing configuration
        zoning: Optional zoning constraints

    Returns:
        BuildingMass closest to target GFA within constraints
    """
    if config is None:
        config = MassingConfig()

    # Calculate buildable envelope
    envelope = calculate_buildable_envelope(site_polygon, setbacks, zoning)
    floor_plate_area = envelope.ground_buildable_area

    if floor_plate_area <= 0:
        raise ValueError("No buildable area after setbacks")

    # Calculate floors needed
    floors_needed = int(target_gfa / floor_plate_area) + 1

    # Apply height limit if zoning specified
    max_floors = _calculate_max_floors(
        envelope.max_height if zoning else None,
        config.floor_config,
        config.max_floors
    )

    if max_floors:
        floors_needed = min(floors_needed, max_floors)

    return generate_massing(
        envelope.ground_buildable.polygon,
        floors_needed,
        config,
        site_polygon
    )


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def calculate_far_utilization(
    massing: BuildingMass,
    max_far: float
) -> Tuple[float, float]:
    """
    Calculate FAR utilization.

    Returns:
        Tuple of (utilized_far, utilization_percentage)
    """
    utilized_far = massing.floor_area_ratio
    utilization = (utilized_far / max_far * 100) if max_far > 0 else 0
    return utilized_far, utilization


def estimate_additional_floors(
    massing: BuildingMass,
    max_far: float
) -> int:
    """
    Estimate how many more floors could be added within FAR limit.
    """
    if not massing.floors:
        return 0

    max_gfa = massing.site_area * max_far
    remaining_gfa = max_gfa - massing.gross_floor_area

    if remaining_gfa <= 0:
        return 0

    avg_floor_area = massing.average_floor_area
    if avg_floor_area <= 0:
        return 0

    return int(remaining_gfa / avg_floor_area)


def compare_massings(massings: List[BuildingMass]) -> List[Dict[str, Any]]:
    """
    Compare multiple massing options.

    Returns list of dictionaries with key metrics for comparison.
    """
    results = []

    for i, massing in enumerate(massings):
        results.append({
            "option": i + 1,
            "massing_type": massing.config.massing_type.value,
            "num_floors": massing.num_floors,
            "gfa_sf": round(massing.gross_floor_area, 0),
            "nfa_sf": round(massing.net_floor_area, 0),
            "height_ft": round(massing.total_height, 1),
            "far": round(massing.floor_area_ratio, 2),
            "coverage": round(massing.lot_coverage, 3),
            "efficiency": round(massing.efficiency, 3),
        })

    return results


def get_massing_summary(massing: BuildingMass) -> Dict[str, Any]:
    """Get comprehensive massing summary."""
    area_by_type = massing.get_area_by_floor_type()

    return {
        "overview": {
            "num_floors": massing.num_floors,
            "total_height_ft": round(massing.total_height, 1),
            "massing_type": massing.config.massing_type.value,
        },
        "areas": {
            "gross_floor_area_sf": round(massing.gross_floor_area, 0),
            "net_floor_area_sf": round(massing.net_floor_area, 0),
            "site_area_sf": round(massing.site_area, 0),
            "footprint_sf": round(massing.building_footprint, 0),
        },
        "ratios": {
            "floor_area_ratio": round(massing.floor_area_ratio, 2),
            "lot_coverage": round(massing.lot_coverage, 3),
            "efficiency": round(massing.efficiency, 3),
        },
        "floor_types": {
            ft.value: round(area, 0) for ft, area in area_by_type.items()
        },
        "floor_details": [f.to_dict() for f in massing.floors],
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    'MassingType',

    # Classes
    'StepBack',
    'MassingConfig',
    'BuildingMass',

    # Generation functions
    'generate_massing',
    'generate_bar_massing',
    'generate_podium_tower_massing',
    'generate_stepped_massing',
    'generate_massing_from_zoning',
    'generate_massing_to_target',

    # Analysis functions
    'calculate_far_utilization',
    'estimate_additional_floors',
    'compare_massings',
    'get_massing_summary',
]
