"""
GenFabTools Parking Engine v2

MVP Features:
- Zone data model (GENERAL, RESERVED)
- 60° angled parking geometry
- Zone-aware layout orchestrator
- Residual recovery (opt-in)
- Connectivity check

v1 remains frozen. v2 is additive only.
"""

from .zones import (
    Zone,
    ZoneType,
    AngleConfig,
    Setbacks,
    validate_zones,
    sort_zones_for_processing,
    create_default_zone,
)
from .schemas import (
    ZoneTypeSchema,
    AngleConfigSchema,
    ZoneSchema,
    ZoneResultSchema,
    V2RequestExtension,
    V2ResponseExtension,
)
from .geometry_60 import (
    # Constants
    STALL_WIDTH_60,
    STALL_DEPTH_60,
    AISLE_WIDTH_60,
    ROW_SPACING_60,
    MODULE_DEPTH_60,
    ANGLE_60_DEGREES,
    STALL_FOOTPRINT_WIDTH_60,
    STALL_FOOTPRINT_DEPTH_60,
    # Circulation
    CirculationMode,
    # Classes
    Stall60,
    StallRow60,
    Aisle60,
    DoubleLoadedRow60,
    # Functions
    create_stall_60,
    create_stall_row_60,
    create_aisle_60,
    create_double_loaded_row_60,
    calculate_stalls_per_row,
    calculate_rows_in_depth,
    calculate_row_spacing_60,
    get_geometry_60_constants,
)
from .zone_orchestrator import (
    ZoneLayoutResult,
    OrchestratedLayoutResult,
    ZoneOrchestrator,
    orchestrate_layout,
    get_zone_order,
)
from .residual_recovery import (
    # Constants
    MIN_RESIDUAL_AREA,
    DEFAULT_RECOVER_RESIDUAL,
    # Classes
    ResidualPolygon,
    RecoveryResult,
    ResidualRecoveryResult,
    # Functions
    sort_residuals_for_processing,
    identify_residual_polygons,
    recover_stalls_from_residual,
    perform_residual_recovery,
    get_occupied_polygons_from_stalls_60,
    get_residual_processing_order,
)
from .connectivity import (
    # Constants
    ENDPOINT_TOLERANCE,
    INTERSECTION_TOLERANCE,
    # Classes
    UnionFind,
    ConnectivityResult,
    # Functions
    check_circulation_connected,
    check_circulation_connectivity,
    get_connected_components,
    count_connected_components,
)
from .geometry_angled import (
    # Enums
    ParkingAngle,
    CirculationMode as AngledCirculationMode,
    # Constants
    STALL_WIDTH,
    STALL_DEPTH,
    AISLE_WIDTH_30,
    AISLE_WIDTH_45,
    AISLE_WIDTH_60 as ANGLED_AISLE_WIDTH_60,
    AISLE_WIDTHS,
    # Classes
    StallFootprint,
    AngledStall,
    StallRowGenerator,
    AngledAisle,
    DoubleLoadedAngledRow,
    # Functions
    create_angled_aisle,
    create_double_loaded_angled_row,
    get_geometry_constants,
    calculate_rows_in_depth as calculate_angled_rows_in_depth,
)

__all__ = [
    # Domain model
    "Zone",
    "ZoneType",
    "AngleConfig",
    "validate_zones",
    "sort_zones_for_processing",
    "create_default_zone",
    # API schemas
    "ZoneTypeSchema",
    "AngleConfigSchema",
    "ZoneSchema",
    "ZoneResultSchema",
    "V2RequestExtension",
    "V2ResponseExtension",
    # 60° Geometry constants
    "STALL_WIDTH_60",
    "STALL_DEPTH_60",
    "AISLE_WIDTH_60",
    "ROW_SPACING_60",
    "MODULE_DEPTH_60",
    "ANGLE_60_DEGREES",
    "STALL_FOOTPRINT_WIDTH_60",
    "STALL_FOOTPRINT_DEPTH_60",
    # 60° Geometry classes
    "Stall60",
    "StallRow60",
    "Aisle60",
    "DoubleLoadedRow60",
    # 60° Geometry functions
    "create_stall_60",
    "create_stall_row_60",
    "create_aisle_60",
    "create_double_loaded_row_60",
    "calculate_stalls_per_row",
    "calculate_rows_in_depth",
    "calculate_row_spacing_60",
    "get_geometry_60_constants",
    # Zone orchestrator
    "ZoneLayoutResult",
    "OrchestratedLayoutResult",
    "ZoneOrchestrator",
    "orchestrate_layout",
    "get_zone_order",
    # Residual recovery constants
    "MIN_RESIDUAL_AREA",
    "DEFAULT_RECOVER_RESIDUAL",
    # Residual recovery classes
    "ResidualPolygon",
    "RecoveryResult",
    "ResidualRecoveryResult",
    # Residual recovery functions
    "sort_residuals_for_processing",
    "identify_residual_polygons",
    "recover_stalls_from_residual",
    "perform_residual_recovery",
    "get_occupied_polygons_from_stalls_60",
    "get_residual_processing_order",
    # Connectivity constants
    "ENDPOINT_TOLERANCE",
    "INTERSECTION_TOLERANCE",
    # Connectivity classes
    "UnionFind",
    "ConnectivityResult",
    # Connectivity functions
    "check_circulation_connected",
    "check_circulation_connectivity",
    "get_connected_components",
    "count_connected_components",
    # Angled geometry enums
    "ParkingAngle",
    "AngledCirculationMode",
    # Angled geometry constants
    "STALL_WIDTH",
    "STALL_DEPTH",
    "AISLE_WIDTH_30",
    "AISLE_WIDTH_45",
    "ANGLED_AISLE_WIDTH_60",
    "AISLE_WIDTHS",
    # Angled geometry classes
    "StallFootprint",
    "AngledStall",
    "StallRowGenerator",
    "AngledAisle",
    "DoubleLoadedAngledRow",
    # Angled geometry functions
    "create_angled_aisle",
    "create_double_loaded_angled_row",
    "get_geometry_constants",
    "calculate_angled_rows_in_depth",
]
