# TestFit Clone - Architecture & Implementation Strategy

## Project Name: **SiteFit**

---

## 🎯 CORE CONCEPT

A real-time site feasibility tool that automatically generates:
1. **Parking layouts** (surface & structured)
2. **Building massing** (footprints, stacking, FAR calculations)
3. **Unit mix optimization** (residential/commercial)
4. **Zoning compliance checking**

All components react to each other in real-time.

---

## 🏗️ SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Site Editor │  │  Controls   │  │  Results Dashboard      │  │
│  │  (Canvas)    │  │  Panel      │  │  (Metrics/3D Preview)   │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘  │
│         │                │                      │                │
│         └────────────────┼──────────────────────┘                │
│                          ▼                                       │
│              ┌───────────────────────┐                          │
│              │   State Manager       │                          │
│              │   (Site Model)        │                          │
│              └───────────┬───────────┘                          │
└──────────────────────────┼──────────────────────────────────────┘
                           │ WebSocket / REST
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     BACKEND (Python FastAPI)                      │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    SOLVER ORCHESTRATOR                      │  │
│  │  Coordinates all engines, manages dependencies & caching    │  │
│  └─────────────────────────┬──────────────────────────────────┘  │
│                            │                                      │
│    ┌───────────┬───────────┼───────────┬───────────┐             │
│    ▼           ▼           ▼           ▼           ▼             │
│ ┌───────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│ │Zoning │ │Parking  │ │Building │ │Unit Mix │ │Financial│       │
│ │Engine │ │Engine   │ │Engine   │ │Engine   │ │Engine   │       │
│ └───┬───┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │
│     │          │           │           │           │             │
│     └──────────┴───────────┴───────────┴───────────┘             │
│                            │                                      │
│                   ┌────────▼────────┐                            │
│                   │  Geometry Core  │                            │
│                   │  (Shapely/CGAL) │                            │
│                   └─────────────────┘                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📁 FILE STRUCTURE

```
testfit_clone/
│
├── ARCHITECTURE.md          # This file
├── README.md                 # Setup & usage instructions
│
├── backend/
│   ├── requirements.txt
│   ├── main.py               # FastAPI entry point
│   ├── config.py             # Global settings, defaults
│   │
│   ├── models/               # Pydantic data models (shared contracts)
│   │   ├── __init__.py
│   │   ├── site.py           # Site, Boundary, Setback, Exclusion
│   │   ├── parking.py        # ParkingConfig, Stall, DriveAisle
│   │   ├── building.py       # Building, Floor, Unit
│   │   ├── zoning.py         # ZoningEnvelope, Constraints
│   │   └── results.py        # SolverResult, Metrics
│   │
│   ├── geometry/             # Pure geometry operations
│   │   ├── __init__.py
│   │   ├── core.py           # Polygon ops, intersections, buffers
│   │   ├── offset.py         # Inward/outward polygon offsetting
│   │   ├── subdivision.py    # Grid subdivision, space partitioning
│   │   └── medial_axis.py    # Skeleton/centerline extraction
│   │
│   ├── engines/              # Domain-specific solvers
│   │   ├── __init__.py
│   │   ├── zoning_engine.py      # Computes buildable envelope
│   │   ├── parking_engine.py     # Generates parking layouts
│   │   ├── building_engine.py    # Stacks floor plates
│   │   ├── unit_mix_engine.py    # Optimizes unit placement
│   │   └── financial_engine.py   # Cost/revenue calculations
│   │
│   ├── orchestrator/         # Coordinates engines
│   │   ├── __init__.py
│   │   ├── solver.py         # Main solver loop
│   │   ├── dependencies.py   # Engine dependency graph
│   │   └── cache.py          # Result caching for speed
│   │
│   ├── api/                  # REST/WebSocket routes
│   │   ├── __init__.py
│   │   ├── routes_site.py    # Site CRUD
│   │   ├── routes_solve.py   # Solve endpoints
│   │   └── routes_export.py  # DXF/JSON export
│   │
│   └── tests/
│       ├── test_geometry.py
│       ├── test_parking.py
│       ├── test_building.py
│       └── test_integration.py
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   │
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       │
│       ├── state/            # Zustand/Redux state management
│       │   ├── siteStore.js      # Site boundary, setbacks
│       │   ├── configStore.js    # Parking/building params
│       │   └── resultsStore.js   # Solver outputs
│       │
│       ├── components/
│       │   ├── Canvas/           # 2D site drawing
│       │   │   ├── SiteCanvas.jsx
│       │   │   ├── ParkingLayer.jsx
│       │   │   ├── BuildingLayer.jsx
│       │   │   └── tools/
│       │   │
│       │   ├── Controls/         # Parameter inputs
│       │   │   ├── ZoningPanel.jsx
│       │   │   ├── ParkingPanel.jsx
│       │   │   ├── BuildingPanel.jsx
│       │   │   └── UnitMixPanel.jsx
│       │   │
│       │   ├── Results/          # Output displays
│       │   │   ├── MetricsDashboard.jsx
│       │   │   ├── ProForma.jsx
│       │   │   └── ThreePreview.jsx   # 3D massing
│       │   │
│       │   └── shared/
│       │       ├── Slider.jsx
│       │       ├── ColorPicker.jsx
│       │       └── Modal.jsx
│       │
│       ├── hooks/
│       │   ├── useSolver.js      # Debounced solve calls
│       │   └── useCanvas.js      # Canvas interaction
│       │
│       ├── services/
│       │   ├── api.js            # REST client
│       │   └── websocket.js      # Real-time updates
│       │
│       └── utils/
│           ├── geometry.js       # Client-side geo helpers
│           └── formatters.js
│
└── shared/                   # Shared constants/types
    └── constants.js          # Stall sizes, defaults
```

---

## 🔄 DATA FLOW & DEPENDENCIES

### Engine Dependency Graph

```
User Input (Site Boundary + Parameters)
         │
         ▼
   ┌─────────────┐
   │ ZONING      │ ← Setbacks, height limits, FAR
   │ ENGINE      │
   └──────┬──────┘
          │ Outputs: buildableEnvelope, maxHeight, maxFAR
          ▼
   ┌─────────────┐
   │ PARKING     │ ← Stall size, aisle width, ratio
   │ ENGINE      │
   └──────┬──────┘
          │ Outputs: stallPolygons[], aislePolygons[], surfaceArea
          │
          ├──────────────────────────────┐
          ▼                              ▼
   ┌─────────────┐                ┌─────────────┐
   │ BUILDING    │                │ STRUCTURED  │
   │ ENGINE      │                │ PARKING     │
   └──────┬──────┘                │ (optional)  │
          │                       └─────────────┘
          │ Outputs: floorPlates[], totalGSF, stories
          ▼
   ┌─────────────┐
   │ UNIT MIX    │ ← Unit types, sizes, counts
   │ ENGINE      │
   └──────┬──────┘
          │ Outputs: units[], unitCounts, avgSize
          ▼
   ┌─────────────┐
   │ FINANCIAL   │ ← Costs/SF, rents, cap rates
   │ ENGINE      │
   └─────────────┘
          │ Outputs: totalCost, NOI, yield
```

### Key Principle: **Cascading Invalidation**
- When user changes **setback** → Zoning recalcs → Parking recalcs → Building recalcs → etc.
- When user changes **stall size** → Only Parking → Building → Unit → Financial recalcs
- Cache results at each stage; only recompute what's affected.

---

## 🔧 IMPLEMENTATION ORDER (Phases)

### **PHASE 1: Geometry Foundation** (Week 1)
Files to create:
1. `backend/geometry/core.py` - Polygon operations
2. `backend/geometry/offset.py` - Setback/buffer operations
3. `backend/models/site.py` - Site data models
4. `backend/tests/test_geometry.py` - Geometry tests

**Exit Criteria:** Can load a site polygon, apply setbacks, get buildable area.

---

### **PHASE 2: Parking Engine** (Week 2)
Files to create:
1. `backend/models/parking.py` - Parking data models
2. `backend/geometry/subdivision.py` - Grid partitioning
3. `backend/engines/parking_engine.py` - Main parking solver
4. `backend/tests/test_parking.py` - Parking tests

**Exit Criteria:** Given a polygon, generates stalls + aisles with count.

---

### **PHASE 3: Zoning Engine** (Week 3)
Files to create:
1. `backend/models/zoning.py` - Zoning constraint models
2. `backend/engines/zoning_engine.py` - Envelope computation
3. `backend/tests/test_zoning.py`

**Exit Criteria:** Computes max building envelope from setbacks + FAR + height.

---

### **PHASE 4: Building Engine** (Week 4)
Files to create:
1. `backend/models/building.py` - Building/floor models
2. `backend/engines/building_engine.py` - Floor plate stacking
3. `backend/tests/test_building.py`

**Exit Criteria:** Stacks floors within envelope, respects podium/tower logic.

---

### **PHASE 5: Orchestrator + API** (Week 5)
Files to create:
1. `backend/orchestrator/solver.py` - Main coordinator
2. `backend/orchestrator/dependencies.py` - Engine DAG
3. `backend/api/routes_solve.py` - Solve endpoint
4. `backend/main.py` - FastAPI app

**Exit Criteria:** Single `/solve` endpoint takes site + params, returns full result.

---

### **PHASE 6: Frontend Canvas** (Week 6-7)
Files to create:
1. `frontend/src/components/Canvas/SiteCanvas.jsx` - Main canvas
2. `frontend/src/state/siteStore.js` - Site state
3. `frontend/src/hooks/useSolver.js` - API integration

**Exit Criteria:** Draw a site, see parking + building rendered.

---

### **PHASE 7: Controls + Real-time** (Week 8)
Files to create:
1. `frontend/src/components/Controls/*.jsx` - All control panels
2. `frontend/src/services/websocket.js` - Real-time updates
3. Debounced solve triggers

**Exit Criteria:** Slide a control, see layout update in <500ms.

---

### **PHASE 8: Unit Mix + Financial** (Week 9-10)
Files to create:
1. `backend/engines/unit_mix_engine.py`
2. `backend/engines/financial_engine.py`
3. `frontend/src/components/Results/ProForma.jsx`

**Exit Criteria:** Full pro forma with unit mix optimization.

---

## 📐 KEY ALGORITHMS

### 1. Parking Layout Algorithm
```
Input: polygon, stallWidth, stallDepth, aisleWidth

1. Find polygon's oriented bounding box (OBB)
2. Test 3 drive aisle orientations: 0°, 45°, 90° (or parallel to longest edge)
3. For each orientation:
   a. Generate parallel drive aisles spaced (2*stallDepth + aisleWidth) apart
   b. Clip aisles to polygon boundary
   c. Place stalls perpendicular to aisles on both sides
   d. Remove stalls that intersect exclusions
   e. Count valid stalls
4. Return orientation with max stall count
```

### 2. Building Stacking Algorithm
```
Input: buildableEnvelope, maxHeight, floorHeight, podiumFloors

1. Start with ground floor = buildableEnvelope
2. For each floor up to podiumFloors:
   - Floor plate = inward offset of envelope (for setback steps)
3. For tower floors above podium:
   - Apply tower setback, get smaller footprint
   - Stack until maxHeight reached or FAR exhausted
4. Return floor plates with heights
```

### 3. Zoning Envelope Algorithm
```
Input: siteBoundary, setbacks{front, side, rear}, heightLimit, FAR

1. Apply setbacks: buildable = siteBoundary.buffer(-setbacks)
2. Compute maxGSF = siteArea * FAR
3. Build 3D envelope:
   - Base = buildable polygon
   - Height = min(heightLimit, maxGSF / buildableArea)
4. Apply stepbacks if required at certain heights
5. Return 3D envelope as floor-by-floor constraints
```

---

## 🔗 API CONTRACTS

### POST /api/solve
```json
{
  "site": {
    "boundary": [[x,y], ...],
    "exclusions": [{"polygon": [...], "type": "easement"}]
  },
  "zoning": {
    "setbacks": {"front": 20, "side": 10, "rear": 15},
    "maxHeight": 85,
    "maxFAR": 3.0
  },
  "parking": {
    "stallWidth": 9,
    "stallDepth": 18,
    "aisleWidth": 24,
    "ratio": 1.5  // stalls per 1000 SF
  },
  "building": {
    "floorHeight": 12,
    "efficiency": 0.85
  }
}
```

### Response
```json
{
  "metrics": {
    "siteArea": 45000,
    "buildableArea": 32000,
    "totalGSF": 96000,
    "parkingStalls": 144,
    "stories": 5,
    "FAR": 2.13
  },
  "geometry": {
    "buildableEnvelope": [[x,y], ...],
    "parking": {
      "stalls": [{"polygon": [...], "type": "standard"}],
      "aisles": [{"polyline": [...], "width": 24}]
    },
    "building": {
      "floors": [{"level": 0, "polygon": [...], "height": 12}]
    }
  }
}
```

---

## ✅ VALIDATION CHECKPOINTS

Before moving to next phase, verify:

| Phase | Checkpoint |
|-------|------------|
| 1 | `polygon.buffer(-10)` returns valid smaller polygon |
| 2 | 200x150 rect generates ~40 stalls with 9x18 + 24ft aisle |
| 3 | FAR=2.0 on 10,000 SF site limits GSF to 20,000 |
| 4 | 5-story building shows 5 floor plates |
| 5 | `/solve` returns complete JSON in <1 second |
| 6 | Canvas renders stalls as colored rectangles |
| 7 | Changing slider triggers re-solve within 300ms |
| 8 | Pro forma shows NOI and yield calculations |

---

## 🚀 GETTING STARTED

Ready to begin? Let's start with **Phase 1: Geometry Foundation**.

First files to create:
1. `backend/requirements.txt`
2. `backend/geometry/core.py`
3. `backend/models/site.py`

Say "Start Phase 1" when ready!
