"""
SiteFit Building Module

Provides building massing, floor plates, and unit distribution.
"""

from .floor_plate import (
    FloorPlate, FloorType, FloorConfig,
    create_floor_plate, create_floor_plates,
    calculate_gross_area, calculate_net_area, calculate_efficiency
)
from .setbacks import (
    BuildableArea, BuildableAreaResult,
    calculate_buildable_envelope, apply_building_setbacks,
    get_buildable_area_for_floor, calculate_step_backs
)
from .massing import (
    MassingType, StepBack, MassingConfig, BuildingMass,
    generate_massing, generate_bar_massing, generate_podium_tower_massing,
    generate_stepped_massing, generate_massing_from_zoning,
    generate_massing_to_target, calculate_far_utilization,
    estimate_additional_floors, compare_massings, get_massing_summary
)
from .unit_mix import (
    UnitType, UnitSpec, UnitMixTarget, UnitCount,
    FloorUnitMix, BuildingUnitMix,
    calculate_units_for_area, calculate_floor_unit_mix,
    calculate_building_unit_mix, get_default_unit_specs,
    estimate_units_from_area, calculate_avg_unit_size,
    calculate_required_parking_from_units, get_unit_mix_summary
)

__all__ = [
    # Floor plate exports
    "FloorPlate", "FloorType", "FloorConfig",
    "create_floor_plate", "create_floor_plates",
    "calculate_gross_area", "calculate_net_area", "calculate_efficiency",
    # Building setbacks exports
    "BuildableArea", "BuildableAreaResult",
    "calculate_buildable_envelope", "apply_building_setbacks",
    "get_buildable_area_for_floor", "calculate_step_backs",
    # Massing exports
    "MassingType", "StepBack", "MassingConfig", "BuildingMass",
    "generate_massing", "generate_bar_massing", "generate_podium_tower_massing",
    "generate_stepped_massing", "generate_massing_from_zoning",
    "generate_massing_to_target", "calculate_far_utilization",
    "estimate_additional_floors", "compare_massings", "get_massing_summary",
    # Unit mix exports
    "UnitType", "UnitSpec", "UnitMixTarget", "UnitCount",
    "FloorUnitMix", "BuildingUnitMix",
    "calculate_units_for_area", "calculate_floor_unit_mix",
    "calculate_building_unit_mix", "get_default_unit_specs",
    "estimate_units_from_area", "calculate_avg_unit_size",
    "calculate_required_parking_from_units", "get_unit_mix_summary",
]
