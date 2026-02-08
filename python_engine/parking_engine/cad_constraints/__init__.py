"""
CAD/BIM Constraint Integration Subsystem
=========================================

Phase 5: Import external CAD/BIM geometry as parking constraints.

This subsystem allows users to import DXF, DWG, and RVT files,
converting elements into 2D planar constraint polygons that
act as hard exclusion zones for parking layout generation.

Modules:
    models      - Core data models (ImportedConstraint, ConstraintType)
    loader      - File format loaders (DXF, DWG, RVT)
    normalizer  - Unit conversion, coordinate alignment, 2D flattening
    classifiers - Semantic classification (COLUMN, CORE, WALL, etc.)
    validators  - Geometry validation (closed, no self-intersections)
    integration - Integration with surface and structured parking engines

Supported Formats:
    - DXF (2D plans)
    - DWG (2D plans)
    - RVT (category-filtered extraction)

Explicitly Excluded:
    - 3DM, OBJ, IFC
    - 3D solids or meshes
    - Sloped or curved geometry

All geometry is flattened to 2D and treated as hard constraints.
Imported geometry acts as no-parking exclusion zones only.
This module does NOT generate or modify CAD/BIM files.
"""

from .models import (
    ConstraintType,
    ImportedConstraint,
    ConstraintSet,
    ConstraintImpact,
    LevelConstraintImpact,
)
from .loader import (
    CADLoader,
    DXFLoader,
    DWGLoader,
    RVTLoader,
    load_constraints_from_file,
    LoadResult,
    LoadError,
)
from .normalizer import (
    UnitSystem,
    normalize_geometry,
    normalize_constraint_set,
    NormalizationConfig,
)
from .classifiers import (
    ClassificationRule,
    LayerClassifier,
    CategoryClassifier,
    classify_by_layer,
    classify_by_category,
    DEFAULT_LAYER_RULES,
    DEFAULT_CATEGORY_RULES,
)
from .validators import (
    ValidationResult,
    ValidationError,
    validate_polygon,
    validate_constraint,
    validate_constraint_set,
    VALIDATION_TOLERANCES,
)
from .integration import (
    apply_constraints_to_surface_layout,
    apply_constraints_to_structured_layout,
    compute_constraint_impact,
    ConstrainedSurfaceLayout,
    ConstrainedStructuredLayout,
)

__all__ = [
    # Models
    "ConstraintType",
    "ImportedConstraint",
    "ConstraintSet",
    "ConstraintImpact",
    "LevelConstraintImpact",
    # Loader
    "CADLoader",
    "DXFLoader",
    "DWGLoader",
    "RVTLoader",
    "load_constraints_from_file",
    "LoadResult",
    "LoadError",
    # Normalizer
    "UnitSystem",
    "normalize_geometry",
    "normalize_constraint_set",
    "NormalizationConfig",
    # Classifiers
    "ClassificationRule",
    "LayerClassifier",
    "CategoryClassifier",
    "classify_by_layer",
    "classify_by_category",
    "DEFAULT_LAYER_RULES",
    "DEFAULT_CATEGORY_RULES",
    # Validators
    "ValidationResult",
    "ValidationError",
    "validate_polygon",
    "validate_constraint",
    "validate_constraint_set",
    "VALIDATION_TOLERANCES",
    # Integration
    "apply_constraints_to_surface_layout",
    "apply_constraints_to_structured_layout",
    "compute_constraint_impact",
    "ConstrainedSurfaceLayout",
    "ConstrainedStructuredLayout",
]
