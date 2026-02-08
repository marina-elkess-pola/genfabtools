"""
SiteFit Constraints Module

Provides zoning rules, setback requirements, and building constraints.
"""

from .setback_rules import (
    SetbackRule, SetbackType, SetbackConfig, EdgeSetback,
    apply_setbacks, calculate_buildable_area, identify_edge_types,
    get_standard_setbacks, get_urban_setbacks, get_suburban_setbacks
)
from .zoning import (
    ZoningDistrict, ZoningConfig, ZoningResult, ZoningType,
    calculate_far, check_height_limit, check_lot_coverage,
    calculate_max_building_area, validate_zoning, get_common_zoning
)
from .parking_ratio import (
    UseType, ParkingRatio, ResidentialParkingRatios, CommercialParkingRatios,
    ParkingRequirement, calculate_residential_parking, calculate_commercial_parking,
    calculate_parking_from_unit_mix, calculate_mixed_use_parking,
    check_parking_compliance, estimate_parking_area, calculate_parking_levels,
    get_parking_summary, get_parking_by_jurisdiction
)

__all__ = [
    # Setback exports
    "SetbackRule", "SetbackType", "SetbackConfig", "EdgeSetback",
    "apply_setbacks", "calculate_buildable_area", "identify_edge_types",
    "get_standard_setbacks", "get_urban_setbacks", "get_suburban_setbacks",
    # Zoning exports
    "ZoningDistrict", "ZoningConfig", "ZoningResult", "ZoningType",
    "calculate_far", "check_height_limit", "check_lot_coverage",
    "calculate_max_building_area", "validate_zoning", "get_common_zoning",
    # Parking ratio exports
    "UseType", "ParkingRatio", "ResidentialParkingRatios", "CommercialParkingRatios",
    "ParkingRequirement", "calculate_residential_parking", "calculate_commercial_parking",
    "calculate_parking_from_unit_mix", "calculate_mixed_use_parking",
    "check_parking_compliance", "estimate_parking_area", "calculate_parking_levels",
    "get_parking_summary", "get_parking_by_jurisdiction",
]
