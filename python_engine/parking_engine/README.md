# GenFabTools Parking Engine

Parking layout engine for early-stage feasibility analysis.

## Overview

This module generates conceptual parking layouts for surface and structured parking. It supports:

**Surface Parking (Phase 1)**

- Rectangular site boundaries
- 90-degree stalls only (MVP)
- One-way and two-way drive aisles
- Double-loaded parking bays
- Standard and ADA stall placement
- Layout comparison and metrics

**Structured Parking Skeleton (Phase 2)**

- Multi-level floor plate stacking
- Ramp and vertical core reservations
- Configurable floor-to-floor heights
- Area-based metrics (stall placement deferred)

**Irregular Geometry Support (Phase 3)**

- L-shaped sites and orthogonal polygons
- Sites with internal voids (cut-outs)
- Concave polygons via rectangular decomposition
- Zone-level decomposition metrics
- Usability ratio and geometry loss tracking

**Structured Stall Placement (Phase 4)**

- Stall placement within structured parking levels
- Automatic ramp and core exclusion
- Per-level and total stall counts
- Bay alignment checking across levels
- Reuses surface parking layout engine

**CAD/BIM Constraint Integration (Phase 5)**

- Import external CAD/BIM geometry (DXF, DWG, RVT)
- Convert to 2D planar constraint polygons
- Classify by semantic type (COLUMN, CORE, WALL, MEP_ROOM, SHAFT, VOID)
- Integrate with surface and structured parking layouts
- Track stalls and area lost due to constraints
- Validation and automatic geometry repair

**All outputs are conceptual and advisory. This is NOT a construction documentation or compliance tool.**

## Installation

The module is pure Python with no external dependencies. Located at:

```
python_engine/parking_engine/
├── __init__.py             # Package exports
├── geometry.py             # Polygon operations
├── rules.py                # Dimension rules
├── layout.py               # Surface parking layout
├── metrics.py              # Surface parking metrics
├── structured.py           # Structured parking skeleton (Phase 2)
├── structured_metrics.py   # Structured metrics (Phase 2)
├── structured_layout.py    # Structured stall placement (Phase 4)
├── irregular.py            # Irregular geometry support (Phase 3)
├── examples.py             # Usage examples
├── test_parking_engine.py  # Surface parking tests
├── test_structured.py      # Structured parking tests
├── test_irregular.py       # Irregular geometry tests
├── test_structured_layout.py # Structured stall placement tests
└── cad_constraints/        # CAD/BIM constraint integration (Phase 5)
    ├── __init__.py         # Module exports
    ├── models.py           # Constraint data models
    ├── loader.py           # DXF/DWG/RVT file loaders
    ├── normalizer.py       # Unit conversion and normalization
    ├── classifiers.py      # Semantic type classification
    ├── validators.py       # Geometry validation and repair
    ├── integration.py      # Layout integration functions
    └── test_cad_constraints.py  # Constraint integration tests
```

## Quick Start

### Surface Parking

```python
from parking_engine import (
    Polygon,
    AisleDirection,
    generate_surface_layout,
    compute_metrics,
)

# Define site (300' x 200')
site = Polygon.from_bounds(0, 0, 300, 200)

# Generate layout
layout = generate_surface_layout(
    site_boundary=site,
    aisle_direction=AisleDirection.TWO_WAY,
    setback=5.0,
)

# Get metrics
metrics = compute_metrics(layout)
print(f"Total stalls: {metrics.total_stalls}")
print(f"Efficiency: {metrics.efficiency_sf_per_stall:.0f} SF/stall")
```

### Irregular Site Geometry (Phase 3)

```python
from parking_engine import (
    Polygon,
    Point,
    AisleDirection,
    generate_surface_layout_irregular,
)

# Define L-shaped site
l_shape = Polygon([
    Point(0, 100),
    Point(0, 200),
    Point(200, 200),
    Point(200, 0),
    Point(100, 0),
    Point(100, 100),
])

# Generate layout (automatically decomposes into rectangular zones)
result = generate_surface_layout_irregular(
    site_boundary=l_shape,
    aisle_direction=AisleDirection.TWO_WAY,
    setback=5.0,
)

print(f"Total stalls: {result.total_stalls}")
print(f"Zones: {len(result.zones)}")
print(f"Usability ratio: {result.usability_ratio:.1%}")
print(f"Decomposition metrics: {result.decomposition_metrics}")
```

### Site with Internal Void

```python
from parking_engine import (
    Polygon,
    generate_surface_layout_irregular,
)

# Site with building cut-out
site = Polygon.from_bounds(0, 0, 300, 200)
void = Polygon.from_bounds(100, 50, 200, 150)  # Building footprint

result = generate_surface_layout_irregular(
    site_boundary=site,
    voids=[void],
)

print(f"Void area excluded: {void.area:,.0f} SF")
print(f"Parkable area: {result.decomposition_metrics['parkable_area_sf']:,.0f} SF")
```

### Structured Parking Skeleton (Phase 2)

```python
from parking_engine import (
    Polygon,
    generate_structured_parking_skeleton,
    compute_structured_metrics,
)

# Define footprint (300' x 180')
footprint = Polygon.from_bounds(0, 0, 300, 180)

# Generate 4-level skeleton
layout = generate_structured_parking_skeleton(
    footprint=footprint,
    level_count=4,
    floor_to_floor_height=10.5,
    ramp_config={"type": "single_helix", "location": "northeast"},
    core_config={"type": "stair_elevator", "location": "center"},
)

# Get metrics
metrics = compute_structured_metrics(layout)
print(f"Levels: {metrics.level_count}")
print(f"Total height: {metrics.total_height}' ")
print(f"Total gross area: {metrics.total_gross_area:,.0f} SF")
print(f"Estimated stalls: {metrics.estimated_total_stalls} (placeholder)")
```

### Structured Stall Placement (Phase 4)

```python
from parking_engine import (
    Polygon,
    AisleDirection,
    generate_structured_parking_skeleton,
    generate_structured_parking_layout,
    compute_structured_layout_metrics,
)

# Define footprint (300' x 180')
footprint = Polygon.from_bounds(0, 0, 300, 180)

# Generate skeleton with ramp and core
skeleton = generate_structured_parking_skeleton(
    footprint=footprint,
    level_count=4,
    floor_to_floor_height=10.5,
    ramp_config={"type": "single_helix", "location": "northeast"},
    core_config={"type": "stair_elevator", "location": "center"},
)

# Place stalls on each level
layout = generate_structured_parking_layout(
    structured_layout=skeleton,
    aisle_direction=AisleDirection.TWO_WAY,
)

# Get comprehensive metrics
metrics = compute_structured_layout_metrics(layout)
print(f"Total stalls: {metrics.total_stalls}")
print(f"Stalls per level: {metrics.stalls_per_level}")
print(f"Efficiency: {metrics.overall_efficiency_sf_per_stall:.0f} SF/stall")
print(f"Stalls lost to ramps/cores: {metrics.total_stalls_lost}")

# Print summary
print(layout.summary())
```

### CAD/BIM Constraint Integration (Phase 5)

```python
from parking_engine import (
    Polygon,
    AisleDirection,
    generate_surface_layout,
    ConstraintType,
    ImportedConstraint,
    ConstraintSet,
    apply_constraints_to_surface_layout,
)

# Define site (300' x 200')
site = Polygon.from_bounds(0, 0, 300, 200)

# Create constraints from imported CAD geometry
constraints = ConstraintSet(
    constraints=[
        ImportedConstraint(
            geometry=Polygon.from_bounds(50, 50, 54, 54),
            constraint_type=ConstraintType.COLUMN,
            layer_name="S-COLS",
            source_file="structure.dxf",
        ),
        ImportedConstraint(
            geometry=Polygon.from_bounds(100, 50, 104, 54),
            constraint_type=ConstraintType.COLUMN,
            layer_name="S-COLS",
            source_file="structure.dxf",
        ),
        ImportedConstraint(
            geometry=Polygon.from_bounds(140, 80, 160, 120),
            constraint_type=ConstraintType.CORE,
            layer_name="A-CORE",
            source_file="architecture.dxf",
        ),
    ],
    source_file="combined_constraints.json",
)

# Apply constraints to layout
result = apply_constraints_to_surface_layout(
    site_boundary=site,
    constraint_set=constraints,
    aisle_direction=AisleDirection.TWO_WAY,
    setback=5.0,
)

# Check impact
print(f"Total stalls: {result.layout.total_stalls}")
print(f"Stalls removed by constraints: {result.impact.stalls_removed}")
print(f"Area lost to constraints: {result.impact.area_lost_sf:.0f} SF")
print(f"Efficiency loss: {result.impact.efficiency_loss_pct:.1f}%")
```

### Loading Constraints from CAD Files

```python
from parking_engine.cad_constraints import (
    DXFLoader,
    classify_by_layer,
    validate_constraint,
    normalize_constraint_set,
    NormalizationConfig,
    UnitSystem,
)

# Load from DXF (geometry provided programmatically)
loader = DXFLoader()
load_result = loader.load_from_geometry(
    geometries=[
        {"points": [(0, 0), (4, 0), (4, 4), (0, 4)], "layer": "S-COLS"},
        {"points": [(50, 50), (70, 50), (70, 90), (50, 90)], "layer": "A-CORE"},
    ],
    source_file="structure.dxf",
)

# Classify constraints by layer name
for constraint in load_result.constraints:
    constraint.constraint_type = classify_by_layer(constraint.layer_name)
    
# Normalize units (if source is in inches)
config = NormalizationConfig(source_unit=UnitSystem.INCHES)
normalized = normalize_constraint_set(load_result.constraint_set, config)

# Validate each constraint
for constraint in normalized.constraints:
    result = validate_constraint(constraint)
    if not result.is_valid:
        print(f"Invalid constraint: {result.errors}")
```

## Module Structure

### geometry.py

Core geometric primitives:

- `Point` - Immutable 2D point with arithmetic operations
- `Polygon` - Simple polygon with area, bounds, containment checks
- `offset_polygon()` - Inward offset (for setbacks)
- `subtract_polygon()` - Boolean subtraction
- `partition_rectangle()` - Divide into strips

### rules.py

Dimension rules and validation:

- `ParkingRules` - Configurable dimension defaults
- `StallType` - Standard, compact, ADA, ADA-van
- `AisleDirection` - One-way, two-way
- `calculate_ada_stall_requirement()` - ADA count lookup
- `validate_aisle_width()` - Minimum width check

### layout.py

Layout generation:

- `generate_surface_layout()` - Main entry point for rectangular sites
- `generate_surface_layout_irregular()` - Entry point for irregular sites (Phase 3)
- `evaluate_layout_options()` - Compare configurations
- `SurfaceParkingLayout` - Result container
- `IrregularLayoutResult` - Result with decomposition metrics (Phase 3)
- `ParkingBay`, `Aisle`, `Stall` - Layout elements

### irregular.py (Phase 3)

Irregular geometry support:

- `extract_parking_zones()` - Decompose irregular site into rectangular zones
- `decompose_l_shape()` - Split L-shaped polygons
- `find_largest_inscribed_rectangle()` - Find inscribed rectangles
- `classify_polygon()` - Identify polygon type (rectangle, l_shape, convex, etc.)
- `validate_stalls_within_boundary()` - Ensure stalls don't exceed site
- `ZoneType` - Zone classifications (RECTANGULAR, REMNANT, UNUSABLE, VOID)
- `ParkingZone` - Extracted rectangular zone
- `DecompositionResult` - Decomposition output with metrics

### metrics.py

Metrics and analysis:

- `compute_metrics()` - Full metrics calculation
- `LayoutMetrics` - Results dataclass
- `compare_layouts()` - Side-by-side comparison
- `estimate_surface_capacity()` - Quick SF-based estimate

### structured_layout.py (Phase 4)

Structured parking stall placement:

- `generate_structured_parking_layout()` - Main entry point for structured stall placement
- `compute_structured_layout_metrics()` - Comprehensive metrics for structured layouts
- `StructuredLayoutWithStalls` - Complete layout with stalls per level
- `LevelLayout` - Single-level stall layout
- `StructuralBayConfig` - Configurable structural bay heuristics
- `StructuredLayoutMetrics` - Metrics including stalls lost to ramps/cores

### cad_constraints/ (Phase 5)

CAD/BIM constraint integration subsystem:

**models.py** - Core data models:

- `ConstraintType` - Enum: COLUMN, CORE, WALL, MEP_ROOM, SHAFT, VOID, UNKNOWN
- `ImportedConstraint` - Single constraint with geometry and metadata
- `ConstraintSet` - Collection of constraints from a source
- `ConstraintImpact` - Metrics on layout impact (stalls removed, area lost)
- `LevelConstraintImpact` - Per-level impact for structured parking

**loader.py** - File format loaders:

- `CADLoader` - Abstract base class
- `DXFLoader` - AutoCAD DXF file loader
- `DWGLoader` - AutoCAD DWG file loader  
- `RVTLoader` - Revit file loader (category-filtered)
- `LoadResult` - Loading result with constraints and errors

**normalizer.py** - Unit conversion:

- `UnitSystem` - Enum: FEET, INCHES, METERS, MILLIMETERS, etc.
- `NormalizationConfig` - Conversion settings
- `normalize_geometry()` - Convert single polygon
- `normalize_constraint_set()` - Convert all constraints

**classifiers.py** - Semantic classification:

- `classify_by_layer()` - Classify by CAD layer name
- `classify_by_category()` - Classify by Revit category
- `classify_by_room_name()` - Classify by room/space name
- `DEFAULT_LAYER_RULES` - Standard layer name patterns
- `DEFAULT_CATEGORY_RULES` - Standard Revit category mappings

**validators.py** - Geometry validation:

- `validate_polygon()` - Check polygon validity
- `validate_constraint()` - Full constraint validation
- `repair_polygon()` - Attempt automatic repair
- `ValidationResult` - Validation output with errors
- `ValidationTolerances` - Configurable tolerance settings

**integration.py** - Layout integration:

- `apply_constraints_to_surface_layout()` - Apply to surface parking
- `apply_constraints_to_structured_layout()` - Apply to structured parking
- `compute_constraint_impact()` - Calculate impact metrics
- `ConstrainedSurfaceLayout` - Surface layout with impact
- `ConstrainedStructuredLayout` - Structured layout with impact

## Usage Examples

### Compare All Layout Options

```python
from parking_engine import Polygon
from parking_engine.layout import evaluate_layout_options
from parking_engine.metrics import compare_layouts

site = Polygon.from_bounds(0, 0, 280, 200)
options = evaluate_layout_options(site, setback=5.0)

# Returns list of (layout, description) sorted by stall count
for layout, desc in options:
    print(f"{desc}: {layout.total_stalls} stalls")
```

### Custom Dimension Rules

```python
from parking_engine import ParkingRules, generate_surface_layout
from parking_engine.rules import StallDimensions

rules = ParkingRules(
    stall_standard=StallDimensions(width=8.5, length=17.0),
    aisle_one_way=13.0,
    aisle_two_way=24.0,
)

layout = generate_surface_layout(site, rules=rules)
```

### Quick Capacity Estimate

```python
from parking_engine.metrics import estimate_surface_capacity

# 2-acre site
estimate = estimate_surface_capacity(
    site_area_sf=2 * 43560,
    efficiency_sf_per_stall=325,
)

print(f"Typical capacity: {estimate['capacity_mid']} stalls")
```

### Structured Capacity Estimate

```python
from parking_engine import estimate_structured_capacity

estimate = estimate_structured_capacity(
    footprint_area_sf=54000,  # 300 x 180
    level_count=4,
)

print(f"Typical capacity: {estimate['capacity_mid']} stalls")
```

### Export to JSON

```python
layout_dict = layout.to_dict()
metrics_dict = metrics.to_dict()

import json
print(json.dumps(metrics_dict, indent=2))
```

## Running Tests

```bash
cd python_engine

# Surface parking tests
python -m parking_engine.test_parking_engine

# Structured parking tests
python -m parking_engine.test_structured

# Irregular geometry tests
python -m parking_engine.test_irregular

# Structured stall placement tests
python -m parking_engine.test_structured_layout

# CAD/BIM constraint tests (Phase 5)
python -m parking_engine.cad_constraints.test_cad_constraints

# All tests
python -m pytest parking_engine/ -v
```

## Scope & Limitations

### What This Does

- Generates conceptual parking layouts for feasibility
- Calculates capacity and efficiency metrics
- Compares layout configurations
- Validates dimensions against rule-of-thumb minimums
- Creates structured parking floor plate skeletons (Phase 2)
- Decomposes irregular sites into rectangular zones (Phase 3)
- Handles L-shaped sites, sites with voids, and concave polygons (Phase 3)
- Places stalls within structured parking levels (Phase 4)
- Respects ramp and core exclusion zones (Phase 4)
- Tracks stalls lost to exclusions and bay alignment (Phase 4)
- Imports CAD/BIM constraints from DXF, DWG, RVT files (Phase 5)
- Classifies constraints by semantic type (COLUMN, CORE, WALL, etc.) (Phase 5)
- Tracks stalls and area lost due to external constraints (Phase 5)
- Reports constraint impact without automatic compensation (Phase 5)

### What This Does NOT Do

- Produce construction documents
- Certify code compliance
- Handle complex non-orthogonal geometries (curved, diagonal edges)
- Generate DXF/DWG exports
- Consider grading or stormwater
- Perform structural calculations or load analysis
- Relocate columns or cores for optimization
- Optimize for maximum possible stalls
- Generate CAD/BIM geometry (import only)
- Support 3DM, OBJ, or IFC file formats
- Validate structural or building code compliance

### Future Extensions

- Angled stalls (45°, 60°)
- Underground parking
- End islands and landscaping
- Grade-aware layouts
- Curved site boundary support
- Explicit column grid modeling

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Application Layer                     │
│          (API routes, frontend, integrations)            │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│                      parking_engine                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  geometry   │  │   layout    │  │     metrics     │  │
│  │             │◄─┤             │──►                 │  │
│  │ • Polygon   │  │ • generate_ │  │ • compute_      │  │
│  │ • offset    │  │   layout()  │  │   metrics()     │  │
│  │ • subtract  │  │ • Bays      │  │ • compare_      │  │
│  └─────────────┘  │ • Stalls    │  │   layouts()     │  │
│         ▲         └──────┬──────┘  └─────────────────┘  │
│         │                │                               │
│         │                ▼                               │
│         │         ┌─────────────┐  ┌─────────────────┐  │
│         └─────────│    rules    │  │   irregular     │  │
│                   │             │  │   (Phase 3)     │  │
│                   │ • Dimensions│  │ • decompose_    │  │
│                   │ • ADA reqs  │  │   l_shape()     │  │
│                   │ • Validation│  │ • extract_zones │  │
│                   └─────────────┘  └─────────────────┘  │
│                                                          │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │  structured │  │ structured_     │  │ structured_ │  │
│  │  (Phase 2)  │  │ metrics         │  │ layout (P4) │  │
│  │ • generate_ │──► • compute_      │◄─┤ • generate_ │  │
│  │   skeleton()│  │   structured_   │  │   layout()  │  │
│  │ • levels    │  │   metrics()     │  │ • stalls    │  │
│  │ • ramps     │  │ • estimate_     │  │ • exclusion │  │
│  │ • cores     │  │   capacity()    │  │   zones     │  │
│  └─────────────┘  └─────────────────┘  └─────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │               cad_constraints (Phase 5)             │ │
│  │  ┌──────────┐  ┌────────────┐  ┌──────────────┐   │ │
│  │  │  loader  │  │ normalizer │  │  classifiers │   │ │
│  │  │ DXF/DWG/ │──► unit conv  │──► layer/cat    │   │ │
│  │  │ RVT      │  │            │  │  patterns    │   │ │
│  │  └──────────┘  └────────────┘  └──────────────┘   │ │
│  │       │                               │            │ │
│  │       ▼                               ▼            │ │
│  │  ┌──────────┐  ┌────────────────────────────┐     │ │
│  │  │validators│  │       integration          │     │ │
│  │  │ • valid  │──► • apply_to_surface_layout  │     │ │
│  │  │ • repair │  │ • apply_to_structured      │     │ │
│  │  └──────────┘  │ • compute_impact           │     │ │
│  │                └────────────────────────────┘     │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## License

Internal use only. Part of GenFabTools platform.
