# SiteFit - Real Estate Feasibility Engine

## Overview

An automated site planning tool that generates optimized building massing and parking layouts given site constraints.

---

## STRATEGY: Build in Layers (Bottom-Up)

### Phase 1: Geometry Foundation

Everything depends on solid geometry operations. We build this first.

### Phase 2: Parking Engine

Parking is the most constrained element - it often dictates what's possible on a site.

### Phase 3: Building Massing

Once parking is solved, stack building mass above/around it.

### Phase 4: Constraint System

Zoning rules, setbacks, FAR limits, height limits, parking ratios.

### Phase 5: Optimizer

Test multiple configurations, score and rank them.

### Phase 6: API + Visualization

Expose to web frontend with real-time feedback.

---

## FILE STRUCTURE

```
sitefit/
│
├── core/                       # PHASE 1: Geometry Foundation
│   ├── __init__.py
│   ├── geometry.py             # Point, Line, Polygon, Rectangle classes
│   ├── operations.py           # Union, intersection, difference, buffer, clip
│   ├── spatial_index.py        # R-tree for fast collision detection
│   └── units.py                # Unit conversion (ft, m, degrees)
│
├── parking/                    # PHASE 2: Parking Engine
│   ├── __init__.py
│   ├── stall.py                # Stall dimensions, types (standard, compact, ADA)
│   ├── drive_aisle.py          # Aisle widths, one-way vs two-way
│   ├── bay.py                  # Double-loaded parking bay (aisle + stalls on both sides)
│   ├── layout_generator.py     # Place bays at different angles, find best fit
│   ├── circulation.py          # Connect bays with drive lanes, entries/exits
│   └── optimizer.py            # Maximize stall count while meeting constraints
│
├── building/                   # PHASE 3: Building Massing
│   ├── __init__.py
│   ├── floor_plate.py          # Single floor outline with area calculation
│   ├── massing.py              # Stack floor plates into 3D mass
│   ├── setbacks.py             # Apply setback rules to create buildable area
│   ├── structured_parking.py   # Parking podiums and wrapped parking
│   └── unit_mix.py             # Residential unit distribution (studio, 1BR, 2BR)
│
├── constraints/                # PHASE 4: Zoning & Rules
│   ├── __init__.py
│   ├── zoning.py               # FAR, lot coverage, height limits
│   ├── parking_ratio.py        # Required stalls per unit/SF
│   ├── setback_rules.py        # Front, side, rear setback requirements
│   ├── fire_access.py          # Fire lane requirements
│   └── ada.py                  # ADA parking requirements
│
├── optimizer/                  # PHASE 5: Multi-Configuration Testing
│   ├── __init__.py
│   ├── configuration.py        # A single site configuration (parking + building)
│   ├── scorer.py               # Score a configuration (efficiency, profit, etc.)
│   ├── generator.py            # Generate many configurations with variations
│   └── solver.py               # Find optimal configuration
│
├── api/                        # PHASE 6: Web API
│   ├── __init__.py
│   ├── app.py                  # FastAPI application
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── parking.py          # /parking/* endpoints
│   │   ├── building.py         # /building/* endpoints
│   │   ├── feasibility.py      # /feasibility/* endpoints (full analysis)
│   │   └── export.py           # /export/* endpoints (DXF, JSON, etc.)
│   └── schemas.py              # Pydantic models for request/response
│
├── visualization/              # Optional: Server-side rendering
│   ├── __init__.py
│   ├── renderer_2d.py          # Generate SVG/PNG of layouts
│   └── renderer_3d.py          # Generate 3D preview (optional)
│
├── tests/                      # Unit tests for each module
│   ├── test_geometry.py
│   ├── test_parking.py
│   ├── test_building.py
│   └── test_optimizer.py
│
├── examples/                   # Sample inputs for testing
│   ├── simple_rectangle.json
│   ├── l_shaped_site.json
│   └── complex_site.json
│
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## DEPENDENCY FLOW (How Files Affect Each Other)

```
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                               │
│  (api/app.py, api/routes/*)                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        OPTIMIZER                                │
│  Takes constraints + site → generates + scores configurations   │
│  (optimizer/solver.py, optimizer/generator.py)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   CONSTRAINTS    │ │    BUILDING      │ │     PARKING      │
│ (zoning, ratios) │ │ (massing, units) │ │ (bays, stalls)   │
└──────────────────┘ └──────────────────┘ └──────────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CORE GEOMETRY                               │
│  All modules depend on this for polygon operations              │
│  (core/geometry.py, core/operations.py)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## BUILD ORDER (Step by Step)

### Step 1: core/geometry.py

- Point, Line, Polygon classes
- Area, perimeter, centroid calculations
- **Test:** Create polygons, verify area calculations

### Step 2: core/operations.py  

- Polygon boolean operations (union, intersection, difference)
- Buffer (inset/offset polygons)
- Line clipping against polygons
- **Test:** Buffer a rectangle inward, verify dimensions
- **Depends on:** geometry.py

### Step 3: parking/stall.py + parking/drive_aisle.py

- Define stall dimensions (9'x18' standard, etc.)
- Define aisle widths (24' two-way, 12' one-way)
- **Test:** Create stalls, verify dimensions
- **Depends on:** core/geometry.py

### Step 4: parking/bay.py

- Double-loaded bay = aisle + stalls on both sides
- Calculate bay width (stall + aisle + stall)
- Generate bay geometry given a centerline
- **Test:** Create bay, count stalls, verify geometry
- **Depends on:** stall.py, drive_aisle.py, core/geometry.py

### Step 5: parking/layout_generator.py

- Given a polygon, place parallel bays at angle (0°, 45°, 60°, 90°)
- Clip bays to polygon boundary
- Handle obstacles (columns, ramps, etc.)
- **Test:** Fill a rectangle with bays, count total stalls
- **Depends on:** bay.py, core/operations.py

### Step 6: parking/circulation.py

- Connect bays with drive lanes
- Add entry/exit points
- Ensure all stalls are reachable
- **Test:** Verify path from entry to all stalls
- **Depends on:** layout_generator.py, core/operations.py

### Step 7: parking/optimizer.py

- Try multiple angles, find best stall count
- Respect exclusion zones
- **Test:** Optimize parking on L-shaped site
- **Depends on:** layout_generator.py, circulation.py

### Step 8: constraints/setback_rules.py + constraints/zoning.py

- Define setback requirements
- Apply setbacks to site → buildable area
- FAR, height, lot coverage limits
- **Test:** Apply setbacks, verify reduced area
- **Depends on:** core/operations.py

### Step 9: building/floor_plate.py + building/setbacks.py

- Create floor plate from buildable area
- Calculate gross/net area
- **Test:** Create floor plate, verify area
- **Depends on:** core/geometry.py, constraints/setback_rules.py

### Step 10: building/massing.py

- Stack floor plates with step-backs
- Track total building area
- **Test:** Stack 5 floors, verify total SF
- **Depends on:** floor_plate.py

### Step 11: building/unit_mix.py

- Distribute units by type on each floor
- Calculate unit count
- **Test:** 10,000 SF floor → how many units fit?
- **Depends on:** floor_plate.py

### Step 12: constraints/parking_ratio.py

- Given unit count → required parking stalls
- Given commercial SF → required stalls
- **Test:** 100 units at 1.5 ratio = 150 stalls
- **Depends on:** building/unit_mix.py

### Step 13: optimizer/configuration.py

- Combine parking layout + building massing into one config
- **Depends on:** parking/*, building/*

### Step 14: optimizer/scorer.py

- Score configuration: efficiency, unit count, parking surplus/deficit
- **Depends on:** configuration.py, constraints/*

### Step 15: optimizer/generator.py + optimizer/solver.py

- Generate variations (different angles, building footprints)
- Find best scoring configuration
- **Depends on:** scorer.py, configuration.py

### Step 16: api/app.py + api/routes/*

- Expose endpoints for frontend
- **Depends on:** optimizer/*, parking/*, building/*

---

## KEY ALGORITHMS

### Parking Layout (parking/layout_generator.py)

1. Inset boundary by half-aisle width
2. Find longest edge → use as primary direction
3. Generate parallel lines at bay-width spacing
4. Clip lines to boundary
5. Convert lines to bays (add stalls on both sides)
6. Count stalls, repeat for other angles
7. Return best configuration

### Building Massing (building/massing.py)

1. Start with buildable area (after setbacks)
2. Calculate max floors from height limit
3. Stack floor plates, apply step-backs if required
4. Calculate total SF, check against FAR limit
5. Reduce floors if FAR exceeded

### Optimizer (optimizer/solver.py)

1. Generate N configurations with variations:
   - Parking angle: 0°, 45°, 60°, 90°
   - Building position: centered, left-biased, right-biased
   - Parking location: surface, structured, wrapped
2. Score each configuration
3. Filter by constraint satisfaction
4. Rank by objective (max units, max profit, etc.)
5. Return top configurations

---

## READY TO START?

Confirm this architecture makes sense, then we'll implement Step 1 (core/geometry.py) with full tests.

Each file will be self-contained with docstrings and type hints.
We'll test each module before moving to the next.
