"""
optimizer/generator.py - Configuration Generator Module

Generates multiple configuration variations for optimization:
- Vary parking angles (0°, 45°, 60°, 90°)
- Vary building footprints and heights
- Vary building placement on site
- Vary parking location (surface, structure, underground)

Depends on:
- configuration.py
- parking/* modules
- building/* modules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple, Iterator, TYPE_CHECKING
import itertools

from sitefit.core.geometry import Polygon, Rectangle, Point
from sitefit.core.operations import inset, difference

if TYPE_CHECKING:
    from sitefit.constraints.zoning import ZoningDistrict


class VariationType(Enum):
    """Types of variations to generate."""
    PARKING_ANGLE = "parking_angle"
    BUILDING_COVERAGE = "building_coverage"
    BUILDING_HEIGHT = "building_height"
    PARKING_LOCATION = "parking_location"
    BUILDING_POSITION = "building_position"
    UNIT_MIX = "unit_mix"


@dataclass
class VariationParameter:
    """
    A parameter to vary in configuration generation.

    Defines the range and step size for a single parameter.
    """
    name: str
    variation_type: VariationType
    min_value: float
    max_value: float
    step: float
    current_value: Optional[float] = None

    def get_values(self) -> List[float]:
        """Get all values in the range."""
        values = []
        v = self.min_value
        while v <= self.max_value:
            values.append(v)
            v += self.step
        return values

    @property
    def value_count(self) -> int:
        """Get number of values."""
        return len(self.get_values())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.variation_type.value,
            "min": self.min_value,
            "max": self.max_value,
            "step": self.step,
            "values": self.get_values(),
        }


@dataclass
class GeneratorConfig:
    """
    Configuration for the generator.

    Defines what variations to generate and constraints to apply.
    """
    # Parking variations
    parking_angles: List[float] = field(
        default_factory=lambda: [0, 45, 60, 90])
    parking_locations: List[str] = field(default_factory=lambda: ["surface"])

    # Building variations
    min_coverage: float = 0.2
    max_coverage: float = 0.6
    coverage_step: float = 0.1

    min_floors: int = 2
    max_floors: int = 10
    floor_step: int = 1

    # Building position variations
    building_positions: List[str] = field(default_factory=lambda: ["center"])

    # Unit assumptions
    avg_unit_size: float = 850.0  # SF per unit
    net_to_gross_ratio: float = 0.85

    # Constraints
    max_configurations: int = 100
    require_compliance: bool = False
    zoning: Optional[ZoningDistrict] = None

    # Generation options
    include_parking_only: bool = False
    include_building_only: bool = False

    @property
    def coverage_values(self) -> List[float]:
        """Get building coverage values."""
        values = []
        c = self.min_coverage
        while c <= self.max_coverage + 0.001:
            values.append(round(c, 2))
            c += self.coverage_step
        return values

    @property
    def floor_values(self) -> List[int]:
        """Get floor count values."""
        return list(range(self.min_floors, self.max_floors + 1, self.floor_step))

    @property
    def total_combinations(self) -> int:
        """Calculate total number of combinations."""
        return (
            len(self.parking_angles) *
            len(self.parking_locations) *
            len(self.coverage_values) *
            len(self.floor_values) *
            len(self.building_positions)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "parking_angles": self.parking_angles,
            "parking_locations": self.parking_locations,
            "coverage_values": self.coverage_values,
            "floor_values": self.floor_values,
            "building_positions": self.building_positions,
            "max_configurations": self.max_configurations,
            "total_combinations": self.total_combinations,
        }


@dataclass
class GenerationResult:
    """
    Result from configuration generation.
    """
    configurations: List[Any]  # List[SiteConfiguration]
    total_generated: int
    total_possible: int
    filtered_count: int
    generation_time_ms: float
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_generated": self.total_generated,
            "total_possible": self.total_possible,
            "filtered_count": self.filtered_count,
            "generation_time_ms": round(self.generation_time_ms, 1),
            "parameters": self.parameters,
        }


# =============================================================================
# CONFIGURATION GENERATORS
# =============================================================================

def generate_configurations(
    site_boundary: Polygon,
    config: Optional[GeneratorConfig] = None,
    buildable_boundary: Optional[Polygon] = None,
    zoning: Optional[ZoningDistrict] = None
) -> GenerationResult:
    """
    Generate multiple configuration variations.

    Args:
        site_boundary: Site boundary polygon
        config: Generator configuration
        buildable_boundary: Optional buildable area after setbacks
        zoning: Optional zoning constraints

    Returns:
        GenerationResult with configurations
    """
    import time
    start_time = time.time()

    if config is None:
        config = GeneratorConfig()

    if buildable_boundary is None:
        # Default 10' setback
        buildable_result = inset(site_boundary, 10.0)
        if buildable_result:
            buildable_boundary = _get_largest_polygon(buildable_result)
        else:
            buildable_boundary = site_boundary

    if zoning:
        config.zoning = zoning

    configurations = []
    filtered = 0

    # Generate all combinations
    for combo in _generate_combinations(config):
        if len(configurations) >= config.max_configurations:
            break

        angle, location, coverage, floors, position = combo

        # Create configuration
        cfg = _create_variation(
            site_boundary=site_boundary,
            buildable_boundary=buildable_boundary,
            parking_angle=angle,
            parking_location=location,
            building_coverage=coverage,
            floor_count=floors,
            building_position=position,
            config=config,
        )

        if cfg is None:
            filtered += 1
            continue

        # Check compliance if required
        if config.require_compliance:
            cfg.calculate_results()
            if cfg.result and not (
                cfg.result.zoning_compliant and
                cfg.result.parking_compliant and
                cfg.result.height_compliant
            ):
                filtered += 1
                continue

        configurations.append(cfg)

    end_time = time.time()

    return GenerationResult(
        configurations=configurations,
        total_generated=len(configurations),
        total_possible=config.total_combinations,
        filtered_count=filtered,
        generation_time_ms=(end_time - start_time) * 1000,
        parameters=config.to_dict(),
    )


def generate_parking_variations(
    site_boundary: Polygon,
    angles: Optional[List[float]] = None,
    building_footprint: Optional[Polygon] = None
) -> List[Any]:
    """
    Generate parking layout variations at different angles.

    Args:
        site_boundary: Site boundary
        angles: Parking angles to try
        building_footprint: Optional building footprint to exclude

    Returns:
        List of SiteConfigurations with parking only
    """
    from sitefit.optimizer.configuration import (
        create_configuration,
        create_parking_element,
        ElementType,
    )
    from sitefit.parking.optimizer import optimize_parking

    if angles is None:
        angles = [0, 45, 60, 90]

    configurations = []

    # Get parking area (exclude building if provided)
    parking_area = site_boundary
    if building_footprint:
        try:
            result = difference(site_boundary, building_footprint)
            if result and result.area > 0:
                parking_area = result
        except Exception:
            pass

    for angle in angles:
        try:
            # Optimize parking at this angle
            layout = optimize_parking(
                parking_area,
                target_angle=angle,
                max_iterations=1  # Just use this angle
            )

            if layout and layout.best_result:
                config = create_configuration(
                    site_boundary=site_boundary,
                    name=f"Parking_{int(angle)}deg",
                    parking_angle=angle,
                )

                parking = create_parking_element(
                    footprint=parking_area,
                    stall_count=layout.best_result.total_stalls,
                    stall_angle=angle,
                    name=f"Surface Parking {int(angle)}°",
                )

                config.add_element(parking)
                configurations.append(config)
        except Exception:
            continue

    return configurations


def generate_building_variations(
    site_boundary: Polygon,
    buildable_boundary: Optional[Polygon] = None,
    coverages: Optional[List[float]] = None,
    floors: Optional[List[int]] = None,
    avg_unit_size: float = 850.0
) -> List[Any]:
    """
    Generate building massing variations.

    Args:
        site_boundary: Site boundary
        buildable_boundary: Buildable area after setbacks
        coverages: Building coverage ratios to try
        floors: Floor counts to try
        avg_unit_size: Average unit size for unit count calculation

    Returns:
        List of SiteConfigurations with building only
    """
    from sitefit.optimizer.configuration import (
        create_configuration,
        create_building_element,
    )

    if buildable_boundary is None:
        buildable_result = inset(site_boundary, 10.0)
        if buildable_result:
            buildable_boundary = _get_largest_polygon(buildable_result)
        else:
            buildable_boundary = site_boundary

    if coverages is None:
        coverages = [0.3, 0.4, 0.5]

    if floors is None:
        floors = [3, 4, 5, 6]

    configurations = []

    for coverage in coverages:
        for floor_count in floors:
            try:
                # Calculate building footprint
                target_area = buildable_boundary.area * coverage
                building_footprint = _create_building_footprint(
                    buildable_boundary, target_area
                )

                if building_footprint is None:
                    continue

                # Calculate units
                gross_area = building_footprint.area * floor_count
                net_area = gross_area * 0.85
                total_units = int(net_area / avg_unit_size)

                config = create_configuration(
                    site_boundary=site_boundary,
                    buildable_boundary=buildable_boundary,
                    name=f"Building_{int(coverage*100)}cov_{floor_count}fl",
                    building_coverage=coverage,
                )

                building = create_building_element(
                    footprint=building_footprint,
                    floors=floor_count,
                    total_units=total_units,
                    site_area=site_boundary.area,
                    name=f"{floor_count}-Story Building",
                )

                config.add_element(building)
                configurations.append(config)
            except Exception:
                continue

    return configurations


def generate_mixed_variations(
    site_boundary: Polygon,
    buildable_boundary: Optional[Polygon] = None,
    config: Optional[GeneratorConfig] = None
) -> List[Any]:
    """
    Generate complete configurations with building and parking.

    Args:
        site_boundary: Site boundary
        buildable_boundary: Buildable area
        config: Generator configuration

    Returns:
        List of complete SiteConfigurations
    """
    if config is None:
        config = GeneratorConfig()

    result = generate_configurations(
        site_boundary=site_boundary,
        config=config,
        buildable_boundary=buildable_boundary,
    )

    return result.configurations


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_combinations(config: GeneratorConfig) -> Iterator[Tuple]:
    """Generate all parameter combinations."""
    return itertools.product(
        config.parking_angles,
        config.parking_locations,
        config.coverage_values,
        config.floor_values,
        config.building_positions,
    )


def _create_variation(
    site_boundary: Polygon,
    buildable_boundary: Polygon,
    parking_angle: float,
    parking_location: str,
    building_coverage: float,
    floor_count: int,
    building_position: str,
    config: GeneratorConfig,
) -> Optional[Any]:
    """Create a single configuration variation."""
    from sitefit.optimizer.configuration import (
        create_configuration,
        create_building_element,
        create_parking_element,
        ElementType,
    )

    try:
        # Create base configuration
        cfg = create_configuration(
            site_boundary=site_boundary,
            buildable_boundary=buildable_boundary,
            name=f"Config_{int(parking_angle)}deg_{int(building_coverage*100)}cov_{floor_count}fl",
            zoning=config.zoning,
            parking_angle=parking_angle,
            building_coverage=building_coverage,
            parking_location=parking_location,
        )

        # Create building footprint
        target_building_area = buildable_boundary.area * building_coverage
        building_footprint = _create_positioned_building(
            buildable_boundary,
            target_building_area,
            building_position
        )

        if building_footprint is None:
            return None

        # Calculate units
        gross_area = building_footprint.area * floor_count
        net_area = gross_area * config.net_to_gross_ratio
        total_units = max(1, int(net_area / config.avg_unit_size))

        # Create building element
        building = create_building_element(
            footprint=building_footprint,
            floors=floor_count,
            total_units=total_units,
            site_area=site_boundary.area,
        )
        cfg.add_element(building)

        # Create parking area (remaining space)
        parking_area = _get_parking_area(
            buildable_boundary, building_footprint)

        if parking_area and parking_area.area > 100:  # Minimum parking area
            # Estimate stall count based on area
            stall_count = _estimate_stalls(parking_area, parking_angle)

            if stall_count > 0:
                element_type = ElementType.PARKING_SURFACE
                if parking_location == "structure":
                    element_type = ElementType.PARKING_STRUCTURE
                elif parking_location == "underground":
                    element_type = ElementType.PARKING_UNDERGROUND

                parking = create_parking_element(
                    footprint=parking_area,
                    stall_count=stall_count,
                    element_type=element_type,
                    stall_angle=parking_angle,
                )
                cfg.add_element(parking)

        return cfg
    except Exception:
        return None


def _create_building_footprint(
    buildable_boundary: Polygon,
    target_area: float
) -> Optional[Polygon]:
    """Create a building footprint with target area."""
    # Use inset to create a smaller polygon
    boundary_area = buildable_boundary.area

    if target_area >= boundary_area:
        return buildable_boundary

    # Calculate inset to achieve target area
    # Approximation: inset_distance = (boundary_area - target_area) / perimeter
    ratio = (target_area / boundary_area) ** 0.5

    # Create centered rectangle
    bounds = buildable_boundary.bounds
    width = (bounds[2] - bounds[0]) * ratio
    height = (bounds[3] - bounds[1]) * ratio

    center_x = (bounds[0] + bounds[2]) / 2
    center_y = (bounds[1] + bounds[3]) / 2

    origin = Point(center_x - width/2, center_y - height/2)
    return Rectangle(origin, width, height).to_polygon()


def _create_positioned_building(
    buildable_boundary: Polygon,
    target_area: float,
    position: str
) -> Optional[Polygon]:
    """Create a building footprint at specified position."""
    bounds = buildable_boundary.bounds
    min_x, min_y, max_x, max_y = bounds

    boundary_area = buildable_boundary.area
    if target_area >= boundary_area:
        return buildable_boundary

    # Calculate dimensions
    ratio = (target_area / boundary_area) ** 0.5
    width = (max_x - min_x) * ratio
    height = (max_y - min_y) * ratio

    # Position the building
    if position == "center":
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        origin = Point(center_x - width/2, center_y - height/2)
    elif position == "north":
        center_x = (min_x + max_x) / 2
        origin = Point(center_x - width/2, max_y - height - 5)
    elif position == "south":
        center_x = (min_x + max_x) / 2
        origin = Point(center_x - width/2, min_y + 5)
    elif position == "east":
        center_y = (min_y + max_y) / 2
        origin = Point(max_x - width - 5, center_y - height/2)
    elif position == "west":
        center_y = (min_y + max_y) / 2
        origin = Point(min_x + 5, center_y - height/2)
    else:
        # Default to center
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        origin = Point(center_x - width/2, center_y - height/2)

    return Rectangle(origin, max(width, 10), max(height, 10)).to_polygon()


def _get_parking_area(
    buildable_boundary: Polygon,
    building_footprint: Polygon
) -> Optional[Polygon]:
    """Get remaining area for parking after building."""
    try:
        result = difference(buildable_boundary, building_footprint)
        if result and result.area > 0:
            return result
    except Exception:
        pass
    return None


def _estimate_stalls(parking_area: Polygon, angle: float) -> int:
    """Estimate number of stalls that fit in area."""
    # Standard stall is 9' x 18' = 162 SF
    # Add aisle allocation (~50% more)
    sf_per_stall = 162 * 1.5  # ~243 SF per stall including circulation

    # Angle affects efficiency
    efficiency_multipliers = {
        0: 0.70,   # Parallel - less efficient
        45: 0.80,  # 45 degree
        60: 0.85,  # 60 degree
        90: 0.90,  # Perpendicular - most efficient
    }

    efficiency = efficiency_multipliers.get(int(angle), 0.80)

    return int((parking_area.area * efficiency) / sf_per_stall)


def _get_largest_polygon(polygons: List[Polygon]) -> Polygon:
    """Get the largest polygon from a list."""
    if not polygons:
        raise ValueError("Empty polygon list")
    return max(polygons, key=lambda p: p.area)


# =============================================================================
# PRESET CONFIGURATIONS
# =============================================================================

def get_quick_generation_config() -> GeneratorConfig:
    """Get configuration for quick generation (fewer variations)."""
    return GeneratorConfig(
        parking_angles=[45, 90],
        parking_locations=["surface"],
        min_coverage=0.3,
        max_coverage=0.5,
        coverage_step=0.2,
        min_floors=4,
        max_floors=6,
        floor_step=2,
        building_positions=["center"],
        max_configurations=20,
    )


def get_comprehensive_generation_config() -> GeneratorConfig:
    """Get configuration for comprehensive generation."""
    return GeneratorConfig(
        parking_angles=[0, 30, 45, 60, 90],
        parking_locations=["surface", "structure"],
        min_coverage=0.2,
        max_coverage=0.6,
        coverage_step=0.05,
        min_floors=2,
        max_floors=15,
        floor_step=1,
        building_positions=["center", "north", "south"],
        max_configurations=500,
    )


def get_high_density_config() -> GeneratorConfig:
    """Get configuration focused on high-density options."""
    return GeneratorConfig(
        parking_angles=[60, 90],
        parking_locations=["structure", "underground"],
        min_coverage=0.4,
        max_coverage=0.7,
        coverage_step=0.1,
        min_floors=8,
        max_floors=20,
        floor_step=2,
        building_positions=["center"],
        max_configurations=50,
    )
