"""
SiteFit Parking Module

Provides parking layout generation including stalls, drive aisles, bays, layout optimization,
and circulation networks.
"""

from .stall import Stall, StallType, STALL_PRESETS
from .drive_aisle import DriveAisle, AisleType, AISLE_PRESETS
from .bay import ParkingBay, BayType, StallPlacement, create_bay_grid, count_total_stalls
from .layout_generator import (
    ParkingLayoutGenerator, LayoutConfig, LayoutResult, LayoutAngle, Exclusion,
    generate_parking_layout, compare_layouts, layout_for_rectangle, stalls_per_acre
)
from .circulation import (
    CirculationGenerator, CirculationNetwork, AccessPoint, DriveLane,
    AccessPointType, DriveLaneType,
    generate_circulation, add_access_point_on_edge, calculate_fire_lane_coverage
)
from .optimizer import (
    ParkingOptimizer, OptimizationConfig, OptimizationResult, OptimizationSummary,
    OptimizationObjective, OptimizationStrategy,
    optimize_parking, quick_optimize, compare_angles, optimize_with_building,
    find_minimum_site_for_stalls
)

__all__ = [
    "Stall", "StallType", "STALL_PRESETS",
    "DriveAisle", "AisleType", "AISLE_PRESETS",
    "ParkingBay", "BayType", "StallPlacement", "create_bay_grid", "count_total_stalls",
    "ParkingLayoutGenerator", "LayoutConfig", "LayoutResult", "LayoutAngle", "Exclusion",
    "generate_parking_layout", "compare_layouts", "layout_for_rectangle", "stalls_per_acre",
    "CirculationGenerator", "CirculationNetwork", "AccessPoint", "DriveLane",
    "AccessPointType", "DriveLaneType",
    "generate_circulation", "add_access_point_on_edge", "calculate_fire_lane_coverage",
    "ParkingOptimizer", "OptimizationConfig", "OptimizationResult", "OptimizationSummary",
    "OptimizationObjective", "OptimizationStrategy",
    "optimize_parking", "quick_optimize", "compare_angles", "optimize_with_building",
    "find_minimum_site_for_stalls",
]
