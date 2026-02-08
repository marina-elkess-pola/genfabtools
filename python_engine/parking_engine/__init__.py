"""
GenFabTools Parking Engine
==========================

Core modules for parking layout generation.

Modules:
    geometry    - Polygon operations (offset, subtraction, partitioning)
    rules       - Dimension rules and constraints
    layout      - Surface parking layout generation
    metrics     - Capacity and efficiency calculations
    structured  - Structured parking skeleton (Phase 2)
    irregular   - Irregular geometry support (Phase 3)
    structured_layout - Structured parking stall placement (Phase 4)
    cad_constraints - CAD/BIM constraint integration (Phase 5)
"""

from .geometry import Polygon, Point, offset_polygon, offset_polygon_directional, subtract_polygon, partition_rectangle
from .rules import ParkingRules, StallType, AisleDirection
from .layout import (
    SurfaceParkingLayout,
    generate_surface_layout,
    generate_surface_layout_irregular,
    IrregularLayoutResult,
)
from .metrics import compute_metrics, LayoutMetrics

# Phase 2: Structured Parking Skeleton
from .structured import (
    StructuredParkingLayout,
    ParkingLevel,
    Ramp,
    VerticalCore,
    RampType,
    CoreType,
    generate_structured_parking_skeleton,
)
from .structured_metrics import (
    StructuredMetrics,
    compute_structured_metrics,
    estimate_structured_capacity,
)

# Phase 3: Irregular Geometry Support
from .irregular import (
    ZoneType,
    ParkingZone,
    DecompositionResult,
    extract_parking_zones,
    classify_polygon,
    is_convex,
    decompose_l_shape,
    find_largest_inscribed_rectangle,
)

# Phase 4: Structured Parking Stall Placement
from .structured_layout import (
    StructuralBayConfig,
    LevelLayout,
    StructuredLayoutWithStalls,
    StructuredLayoutMetrics,
    generate_structured_parking_layout,
    compute_structured_layout_metrics,
)

# Phase 5: CAD/BIM Constraint Integration
from .cad_constraints import (
    ConstraintType,
    ImportedConstraint,
    ConstraintSet,
    ConstraintImpact,
    LevelConstraintImpact,
    load_constraints_from_file,
    LoadResult,
    LoadError,
    UnitSystem,
    normalize_geometry,
    normalize_constraint_set,
    NormalizationConfig,
    classify_by_layer,
    classify_by_category,
    validate_polygon,
    validate_constraint,
    validate_constraint_set,
    apply_constraints_to_surface_layout,
    apply_constraints_to_structured_layout,
    compute_constraint_impact,
    ConstrainedSurfaceLayout,
    ConstrainedStructuredLayout,
)

# Phase 6: DXF Export
from .dxf_export import (
    export_surface_layout_to_dxf,
    export_layout_dict_to_dxf,
    LAYER_SITE_BOUNDARY,
    LAYER_STALL_STANDARD,
    LAYER_STALL_ADA,
    LAYER_ACCESS_AISLE,
    LAYER_AISLES,
    LAYER_RAMPS,
    LAYER_CORES,
)

__version__ = "0.5.0"
__all__ = [
    # Geometry
    "Polygon",
    "Point",
    "offset_polygon",
    "subtract_polygon",
    "partition_rectangle",
    # Rules
    "ParkingRules",
    "StallType",
    "AisleDirection",
    # Surface Layout
    "SurfaceParkingLayout",
    "generate_surface_layout",
    # Irregular Surface Layout (Phase 3)
    "generate_surface_layout_irregular",
    "IrregularLayoutResult",
    "ZoneType",
    "ParkingZone",
    "DecompositionResult",
    "extract_parking_zones",
    "classify_polygon",
    "is_convex",
    "decompose_l_shape",
    "find_largest_inscribed_rectangle",
    # Surface Metrics
    "compute_metrics",
    "LayoutMetrics",
    # Structured Parking Skeleton (Phase 2)
    "StructuredParkingLayout",
    "ParkingLevel",
    "Ramp",
    "VerticalCore",
    "RampType",
    "CoreType",
    "generate_structured_parking_skeleton",
    "StructuredMetrics",
    "compute_structured_metrics",
    "estimate_structured_capacity",
    # Structured Parking Stall Placement (Phase 4)
    "StructuralBayConfig",
    "LevelLayout",
    "StructuredLayoutWithStalls",
    "StructuredLayoutMetrics",
    "generate_structured_parking_layout",
    "compute_structured_layout_metrics",
    # CAD/BIM Constraint Integration (Phase 5)
    "ConstraintType",
    "ImportedConstraint",
    "ConstraintSet",
    "ConstraintImpact",
    "LevelConstraintImpact",
    "load_constraints_from_file",
    "LoadResult",
    "LoadError",
    "UnitSystem",
    "normalize_geometry",
    "normalize_constraint_set",
    "NormalizationConfig",
    "classify_by_layer",
    "classify_by_category",
    "validate_polygon",
    "validate_constraint",
    "validate_constraint_set",
    "apply_constraints_to_surface_layout",
    "apply_constraints_to_structured_layout",
    "compute_constraint_impact",
    "ConstrainedSurfaceLayout",
    "ConstrainedStructuredLayout",
    # DXF Export (Phase 6)
    "export_surface_layout_to_dxf",
    "export_layout_dict_to_dxf",
    "LAYER_SITE_BOUNDARY",
    "LAYER_STALL_STANDARD",
    "LAYER_STALL_ADA",
    "LAYER_ACCESS_AISLE",
    "LAYER_AISLES",
    "LAYER_RAMPS",
    "LAYER_CORES",
]
