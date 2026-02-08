# GenFabTools Parking Design & Feasibility Tool

## Technical Foundation Specification

**Document Version:** 1.1
**Date:** 2026-01-31  
**Classification:** Internal Technical Specification

---

## A. Scope & Limitations

### What the Tool Does

The GenFabTools Parking module provides **early-stage conceptual analysis** for parking feasibility and schematic layout generation. It enables users to:

- Estimate parking capacity for a given site boundary and typology
- Generate rule-based conceptual parking layouts (surface, structured, underground)
- Compare alternative parking schemes by yield, efficiency, and cost order-of-magnitude
- Identify geometric, access, and regulatory constraints at the feasibility stage
- Produce exportable conceptual diagrams and summary metrics for stakeholder communication

### What the Tool Does NOT Do

| Exclusion | Rationale |
|-----------|-----------|
| Final construction documentation | Requires licensed professional stamp and detailed engineering |
| Code compliance certification | Varies by jurisdiction; requires legal/professional sign-off |
| Structural design or load calculations | Requires licensed structural engineer |
| Stormwater management design | Requires licensed civil engineer and site-specific hydrology |
| ADA/accessibility certification | Requires code official review and accessibility specialist |
| Fire access / life-safety certification | Requires fire marshal approval and life-safety engineer |
| Geotechnical or foundation design | Requires subsurface investigation and geotechnical engineer |
| Traffic impact analysis | Requires licensed traffic engineer and local agency coordination |

### Advisory Nature

All outputs are:

- **Conceptual**: Suitable for feasibility, not permit submission
- **Rule-based**: Derived from configurable heuristics, not jurisdiction-specific code parsing
- **Non-binding**: Do not constitute professional engineering or architectural advice
- **Order-of-magnitude**: Cost and capacity figures are planning-level estimates (±20–30%)

---

## B. Target Users & Workflows

### Primary User Profiles

| User Type | Primary Objective | Typical Session |
|-----------|-------------------|-----------------|
| **Real Estate Developer** | Determine if site can support required parking count within budget | 5–15 min quick feasibility |
| **Architect** | Explore parking typology options and their site impact | 15–45 min scenario comparison |
| **Urban Designer** | Evaluate parking placement relative to massing and public realm | 30–60 min iterative refinement |
| **Parking Consultant** | Generate preliminary layouts for client presentations | 30–90 min detailed scheme development |
| **Civil Engineer (Conceptual)** | Assess grading, access, and circulation feasibility | 15–30 min constraint review |

### Key Workflows

#### Workflow 1: Quick Feasibility Check

1. User imports or draws site boundary
2. User specifies target parking count or demand ratio
3. System evaluates feasibility across typologies (surface, structure, underground)
4. System returns capacity ranges, footprint requirements, and order-of-magnitude costs
5. User exports summary report

#### Workflow 2: Typology Comparison

1. User defines site boundary and constraints (setbacks, access points, no-build zones)
2. System generates conceptual layouts for each applicable typology
3. User compares metrics: efficiency (SF/stall), yield, cost, footprint
4. User selects preferred typology for further refinement

#### Workflow 3: Schematic Refinement

1. User selects typology and adjusts parameters (stall size, aisle width, drive lane configuration)
2. System regenerates layout with updated geometry
3. User adjusts access points, ramp locations, pedestrian paths
4. System validates against rule-based constraints (turning radii, slope limits, clearances)
5. User exports conceptual plan and metrics

#### Workflow 4: Multi-Level Structured Parking

1. User defines footprint and level count
2. System generates floor-by-floor conceptual layout with ramp/elevator cores
3. User reviews efficiency metrics per level
4. System estimates structural bay implications (rule-of-thumb, not engineered)

---

## C. Engineering & Design Disciplines Involved

The following disciplines contribute **rule-of-thumb constraints and heuristics** to the tool logic. These are not substitutes for licensed professional design.

### Disciplines & Contributions

| Discipline | Contribution to Tool | Nature of Input |
|------------|---------------------|-----------------|
| **Parking Planning** | Stall dimensions, aisle widths, circulation patterns, efficiency benchmarks | Industry standards (NPA, ITE, ULI) |
| **Traffic Engineering** | Access point spacing, turning radii, ramp grades, sight triangles | Rule-of-thumb; not traffic study |
| **Civil Engineering** | Grading limits, stormwater allowances, utility setbacks | Heuristic; not site-specific design |
| **Structural Engineering** | Bay spacing rules, floor-to-floor heights, ramp slope limits | Parametric rules; not structural analysis |
| **Architecture** | Integration with building footprints, pedestrian access, facade zones | Schematic coordination |
| **Accessibility** | ADA stall counts, access aisle widths, path of travel rules | Code minimums; not compliance certification |
| **Fire/Life Safety** | Fire apparatus access heuristics, clearance envelopes, and preliminary egress allowances | Generic rules; not fire marshal approval |
| **Geotechnical (Indirect)** | Depth limits for underground parking flagging | User-input constraint; not subsurface analysis |

### Heuristic Disclaimer

All discipline-specific logic embedded in the tool represents **generalized best practices and industry rules-of-thumb**. Site-specific conditions, local amendments, and professional judgment supersede tool outputs.

---

## D. High-Level System Architecture

### Architecture Principles

- **Separation of Concerns**: Geometry, layout logic, rules, and visualization are distinct modules
- **Technology Agnostic Core**: Core algorithms independent of specific frameworks where feasible
- **Scalable Web-Based Deployment**: Stateless compute with persistent project storage
- **Extensibility**: Plugin architecture for future typologies and rule sets

### System Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Web Application (SPA)                            │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │    │
│  │  │ Site Editor  │  │ Scheme View  │  │ Metrics & Report Panel   │   │    │
│  │  │ (2D Canvas)  │  │ (2D/3D)      │  │                          │   │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                     │
│         Authentication │ Rate Limiting │ Request Routing │ Caching          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
┌───────────────────┐    ┌───────────────────────┐    ┌─────────────────────┐
│  PROJECT SERVICE  │    │   COMPUTE SERVICE     │    │   EXPORT SERVICE    │
│                   │    │                       │    │                     │
│ • CRUD Operations │    │ • Layout Generation   │    │ • PDF Reports       │
│ • Version History │    │ • Capacity Analysis   │    │ • DXF/DWG Export    │
│ • Collaboration   │    │ • Constraint Check    │    │ • Data Export (CSV) │
└───────────────────┘    └───────────────────────┘    └─────────────────────┘
            │                         │
            ▼                         ▼
┌───────────────────┐    ┌───────────────────────────────────────────────────┐
│   DATA STORE      │    │              COMPUTE ENGINE CORE                  │
│                   │    │                                                   │
│ • Project DB      │    │  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│ • Rule Sets       │    │  │  GEOMETRY   │  │   LAYOUT    │  │   RULES   │ │
│ • Typology Lib    │    │  │  PROCESSOR  │  │   ENGINE    │  │  ENGINE   │ │
│ • User Accounts   │    │  │             │  │             │  │           │ │
│                   │    │  │ • Boundary  │  │ • Surface   │  │ • Stall   │ │
│                   │    │  │ • Offset    │  │ • Structure │  │ • Aisle   │ │
│                   │    │  │ • Boolean   │  │ • U/G       │  │ • Access  │ │
│                   │    │  │ • Partition │  │ • Hybrid    │  │ • ADA     │ │
│                   │    │  └─────────────┘  └─────────────┘  └───────────┘ │
│                   │    │                                                   │
└───────────────────┘    └───────────────────────────────────────────────────┘
```

### Module Descriptions

#### Geometry Processor

- Polygon operations: offset, union, intersection, difference
- Subdivision and partitioning algorithms
- Coordinate system handling (local site coordinates, geo-referenced)
- Import parsing (GeoJSON, DXF boundary extraction)

#### Layout Engine

- Stall placement algorithms per typology
- Aisle and drive lane generation
- Ramp and circulation path routing
- Multi-level stacking logic for structures

#### Rules Engine

- Configurable constraint definitions (dimensions, ratios, counts)
- Validation pipeline for generated layouts
- Rule set versioning and jurisdiction templating
- Conflict detection and user notification

#### Frontend Visualization

- 2D plan view with interactive editing
- 3D massing preview for structured/underground
- Real-time metric updates
- Annotation and measurement tools

---

## E. Conceptual Data Models

### Core Entities

```
PROJECT
├── id: UUID
├── name: String
├── created_at: Timestamp
├── updated_at: Timestamp
├── owner_id: UUID (User)
├── collaborators: [UUID]
├── sites: [SITE]
└── schemes: [PARKING_SCHEME]

SITE
├── id: UUID
├── project_id: UUID
├── name: String
├── boundary: Polygon (GeoJSON)
├── coordinate_system: Enum (LOCAL | WGS84 | STATE_PLANE)
├── constraints: [SITE_CONSTRAINT]
├── access_points: [ACCESS_POINT]
└── grade_data: Optional<GRADE_MODEL>

SITE_CONSTRAINT
├── id: UUID
├── type: Enum (SETBACK | NO_BUILD | EASEMENT | UTILITY | EXISTING_STRUCTURE)
├── geometry: Polygon | LineString
├── buffer_distance: Optional<Float>
└── note: String

ACCESS_POINT
├── id: UUID
├── location: Point
├── type: Enum (VEHICULAR | PEDESTRIAN | SERVICE)
├── width: Float
├── direction: Enum (IN | OUT | BIDIRECTIONAL)
└── connects_to: Enum (PUBLIC_ROAD | PRIVATE_DRIVE | INTERNAL)

PARKING_SCHEME
├── id: UUID
├── project_id: UUID
├── site_id: UUID
├── name: String
├── typology: TYPOLOGY_TYPE
├── parameters: SCHEME_PARAMETERS
├── layout: LAYOUT_RESULT
├── metrics: SCHEME_METRICS
├── status: Enum (DRAFT | VALID | INVALID | ARCHIVED)
└── validation_results: [VALIDATION_RESULT]

TYPOLOGY_TYPE
├── Enum: SURFACE | ABOVE_GROUND_STRUCTURE | UNDERGROUND | HYBRID

SCHEME_PARAMETERS
├── stall_template: STALL_TEMPLATE
├── aisle_width: Float
├── drive_lane_config: Enum (ONE_WAY | TWO_WAY)
├── level_count: Integer (for structures)
├── floor_to_floor_height: Float (for structures)
├── ramp_configuration: RAMP_CONFIG
└── custom_overrides: JSON

STALL_TEMPLATE
├── id: UUID
├── name: String (e.g., "Standard", "Compact", "ADA", "EV")
├── width: Float
├── length: Float
├── angle: Float (0, 45, 60, 90)
└── access_aisle_width: Optional<Float> (for ADA)

LAYOUT_RESULT
├── levels: [LEVEL_LAYOUT]
├── circulation_paths: [PATH]
├── ramps: [RAMP]
└── cores: [VERTICAL_CORE]

LEVEL_LAYOUT
├── level_index: Integer
├── elevation: Float
├── boundary: Polygon
├── stalls: [STALL_INSTANCE]
├── aisles: [AISLE]
├── drive_lanes: [DRIVE_LANE]
└── end_islands: [ISLAND]

STALL_INSTANCE
├── id: UUID
├── template_id: UUID
├── geometry: Polygon
├── centroid: Point
├── orientation: Float (degrees)
├── type_tag: Enum (STANDARD | COMPACT | ADA | EV | RESERVED)
└── aisle_id: UUID

SCHEME_METRICS
├── total_stalls: Integer
├── stalls_by_type: Map<String, Integer>
├── gross_area_sf: Float
├── net_parking_area_sf: Float
├── efficiency_sf_per_stall: Float
├── circulation_percentage: Float
├── ada_stall_count: Integer
├── ada_rules_satisfied: Boolean (rule-based check)
├── estimated_cost_range: COST_RANGE
└── footprint_utilization: Float

COST_RANGE
├── low: Float
├── mid: Float
├── high: Float
├── unit: Enum (PER_STALL | PER_SF | TOTAL)
└── basis_year: Integer
└── Costs exclude land acquisition, financing, design fees, permitting, utility relocation, and escalation beyond the basis year

RULESET
├── id: UUID
├── name: String
├── version: String
├── jurisdiction_hint: String (informational only)
├── stall_rules: [DIMENSION_RULE]
├── aisle_rules: [DIMENSION_RULE]
├── ada_rules: ADA_RULESET
├── ramp_rules: RAMP_RULESET
├── access_rules: ACCESS_RULESET
└── is_default: Boolean

VALIDATION_RESULT
├── rule_id: UUID
├── rule_name: String
├── status: Enum (PASS | WARN | FAIL)
├── message: String
├── affected_elements: [UUID]
└── severity: Enum (INFO | ADVISORY | CRITICAL)
```

### Entity Relationships

```
User ──────┬────────────────────────────────────────────┐
           │ owns/collaborates                          │
           ▼                                            │
       PROJECT ──────┬──────────────────────────────────┤
                     │ contains                         │
           ┌─────────┴─────────┐                        │
           ▼                   ▼                        │
         SITE            PARKING_SCHEME ◄───────────────┤
           │                   │                        │
           │ constrains        │ uses                   │
           ▼                   ▼                        │
   SITE_CONSTRAINT         RULESET ◄────────────────────┘
   ACCESS_POINT            TYPOLOGY_TEMPLATE            │
                           STALL_TEMPLATE               │
                                                        │
                     generates                          │
                         │                              │
                         ▼                              │
                   LAYOUT_RESULT ───► SCHEME_METRICS    │
                         │                              │
                         ▼                              │
              VALIDATION_RESULT ◄───────────────────────┘
```

---

## F. Algorithmic Approach (High Level)

### F.1 Surface Parking Layout Algorithm

**Objective**: Maximize stall count within site boundary while satisfying circulation and access constraints.

#### Logic Flow

```
1. INPUT PROCESSING
   ├── Parse site boundary polygon
   ├── Apply setback offsets to derive net parking area
   ├── Identify access point locations and orientations
   └── Parse no-build zones and subtract from available area

2. DRIVE LANE SKELETON GENERATION
   ├── Generate candidate drive lane spines connecting access points
   ├── Apply minimum turning radius constraints at direction changes
   ├── Evaluate one-way vs. two-way configurations
   └── Select primary circulation spine based on efficiency heuristic

3. PARKING BAY PARTITIONING
   ├── Offset drive lanes by aisle width to define bay edges
   ├── Partition remaining area into rectangular parking bays
   ├── Orient bays perpendicular or angled to drive lanes
   └── Handle irregular geometry with end triangulation

4. STALL PLACEMENT
   ├── For each bay:
   │   ├── Determine optimal stall angle (90°, 60°, 45°, 0°)
   │   ├── Calculate stall count based on bay dimensions
   │   ├── Place stalls with required aisle frontage
   │   └── Mark end-of-row positions for landscape islands or end stalls
   └── Insert ADA stalls at accessible locations (near entries, flat grade)

5. CIRCULATION REFINEMENT
   ├── Verify all stalls have unobstructed aisle access
   ├── Check turning movements at aisle intersections
   ├── Validate fire lane widths if applicable
   └── Adjust drive lane geometry for dead-end turnarounds

6. VALIDATION & METRICS
   ├── Run ruleset validation on all placed elements
   ├── Calculate efficiency metrics
   └── Flag constraint violations for user review
```

#### Key Heuristics

- **Double-loaded aisles preferred**: Stalls on both sides of aisle maximize efficiency
- **90° stalls for maximum density**: Angled stalls trade density for easier maneuvering
- **One-way aisles reduce width**: 12–14' vs. 22–26' for two-way
- **End islands every 15–20 stalls**: Rule-of-thumb for landscaping and pedestrian refuge

---

### F.2 Above-Ground Structured Parking Algorithm

**Objective**: Stack parking levels to achieve target capacity within footprint, respecting structural and circulation constraints.

#### Logic Flow

```
1. FOOTPRINT ANALYSIS
   ├── Determine available footprint (may differ from site boundary)
   ├── Apply setbacks and height limit constraints
   ├── Calculate maximum buildable envelope
   └── Identify ramp/core placement zones (typically corners or ends)

2. STRUCTURAL BAY LAYOUT
   ├── Establish structural grid based on rule-of-thumb spans:
   │   ├── Short span: 16–18' typical (single bay = 2 stalls + aisle)
   │   ├── Long span: 55–65' typical (triple bay = 3 modules)
   │   └── Column placement at bay intersections
   ├── Orient grid for optimal stall-to-column relationship
   └── 90° stalls: columns between stall pairs
       Angled stalls: columns at aisle edge

3. FLOOR PLATE LAYOUT
   ├── Apply level-0 logic (surface parking algorithm) to floor plate
   ├── Reserve areas for:
   │   ├── Ramp runs (helical, speed ramp, or sloped floor)
   │   ├── Stair/elevator cores
   │   ├── Mechanical/electrical rooms (ground floor)
   │   └── Pedestrian paths to cores
   └── Generate typical floor layout

4. VERTICAL CIRCULATION DESIGN
   ├── Select ramp type based on footprint constraints:
   │   ├── Single-threaded helix: compact, slower
   │   ├── Double-threaded helix: higher capacity
   │   ├── Express ramps: separate up/down
   │   └── Sloped floors: integrated, less lost area
   ├── Calculate ramp slope (max 6.67% for long ramps, 12% for short)
   ├── Position ramps for traffic flow (entry to upper, exit from upper)
   └── Connect ramps to drive aisles on each level

5. LEVEL STACKING
   ├── Replicate floor plate for each level
   ├── Adjust top level for:
   │   ├── Rooftop parking (if applicable)
   │   ├── Reduced column-free spans for shorter heights
   │   └── Drainage considerations
   └── Calculate floor-to-floor height (10'–11' typical)

6. CAPACITY & EFFICIENCY CALCULATION
   ├── Sum stalls across all levels
   ├── Calculate gross SF, net parking SF, efficiency (SF/stall)
   ├── Typical target: 300–350 SF/stall including circulation
   └── Flag if below 280 or above 400 (outlier efficiency)

7. COST ORDER-OF-MAGNITUDE
   ├── Apply unit cost factors (per stall or per SF)
   ├── Structured parking: $25,000–$45,000/stall (2026 basis, varies by region)
   └── Present as range, not point estimate
```

#### Key Heuristics

- **Double-loaded 60' bay**: Most efficient for 90° parking (8.5' stalls + 24' aisle)
- **10'-6" floor-to-floor minimum**: Allows for structure, MEP, and clearance
- **1 stair + 1 elevator per 250 stalls**: Rule-of-thumb for vertical circulation
- **5% area loss per ramp**: Approximate impact of helical ramp penetrations

---

### F.3 Underground Parking Algorithm

**Objective**: Maximize parking capacity below grade while respecting excavation limits, structural constraints, and egress requirements.

#### Logic Flow

```
1. EXCAVATION ENVELOPE DEFINITION
   ├── Offset site boundary for shoring/retention wall setbacks
   ├── Apply maximum depth constraint (user input or heuristic):
   │   ├── Single level: 12–15' below grade
   │   ├── Two levels: 25–30' below grade
   │   ├── Three+ levels: cost escalates significantly
   │   └── Flag groundwater / rock if user indicates
   └── Define net excavation polygon per level

2. STRUCTURAL CONSIDERATIONS
   ├── Assume cast-in-place concrete or post-tensioned slab
   ├── Column grid: similar to above-ground (18' x 60' bays typical)
   ├── Foundation walls at perimeter (8"–12" typical)
   ├── Reserve areas for:
   │   ├── Building core penetrations (if below building)
   │   ├── Ramp openings
   │   └── Mechanical/ventilation rooms
   └── Headroom: 8'-6" clear minimum, 9'-0" preferred

3. FLOOR PLATE LAYOUT
   ├── Apply structured parking logic to underground footprint
   ├── Key differences:
   │   ├── No weather exposure considerations
   │   ├── Higher ventilation requirements (enclosed space)
   │   ├── Stricter fire/life-safety egress (pressurized stairs)
   │   └── Waterproofing at lowest level
   └── Place ADA stalls near elevators (not ramps)

4. RAMP DESIGN
   ├── Entry ramp from grade to P1:
   │   ├── Max slope: 12% transition, 15–20% main run
   │   ├── Transition zones at top and bottom (8% for 10')
   │   └── Minimum width: 12' one-way, 22' two-way
   ├── Inter-level ramps (if multi-level):
   │   ├── Shorter runs acceptable
   │   ├── Consider sloped floor design for efficiency
   │   └── Alternating one-way preferred for safety
   └── Emergency egress: stairs at max 200' travel distance

5. CAPACITY CALCULATION
   ├── Underground typically higher efficiency (no exposed ramps)
   ├── Target: 280–320 SF/stall
   ├── Loss factors:
   │   ├── Mechanical rooms: 3–5% per level
   │   ├── Ramp penetrations: 5–8% per level
   │   └── Core areas: varies by building above
   └── Sum stalls across levels

6. COST ESTIMATION
   ├── Underground costs significantly higher:
   │   ├── $40,000–$70,000/stall (2026 basis)
   │   ├── Escalates 20–30% per additional level
   │   └── Rock or high water table: +30–50%
   ├── Present as range with explicit caveats
   └── Flag for geotechnical investigation requirement
```

#### Key Heuristics

- **Excavation costs dominate**: First level is most expensive (mobilization, shoring)
- **Natural ventilation impossible**: Mechanical ventilation required for CO and fire smoke
- **Two levels often optimal**: Third level rarely cost-justified unless land extremely expensive
- **Below-building integration**: Most efficient when under building footprint

---

### F.4 Hybrid Configuration Logic

For sites requiring mixed typologies (e.g., surface + structure, or podium + underground):

```
1. ZONE ALLOCATION
   ├── Partition site into typology zones based on constraints:
   │   ├── Building footprint → underground below, structure above
   │   ├── Setback zones → surface or landscape
   │   ├── Height-limited areas → surface only
   │   └── Fire lane reserves → no parking
   └── Define interface points between zones

2. INDEPENDENT LAYOUT
   ├── Apply typology-specific algorithm to each zone
   ├── Ensure access continuity between zones
   └── Align drive lanes at zone boundaries

3. UNIFIED CIRCULATION
   ├── Connect zone layouts via drive lanes or ramps
   ├── Verify wayfinding clarity (single entry, clear paths)
   └── Check for conflicting traffic patterns

4. AGGREGATED METRICS
   ├── Sum capacities across zones
   ├── Weight-average efficiency metrics
   ├── Sum cost estimates with zone-specific factors
   └── Present as unified scheme with zone breakdown
```

---

## G. MVP Definition

### MVP Scope (v1.0)

The Minimum Viable Product delivers core feasibility functionality for the most common use case: **surface parking on a simple site**.

#### Included in MVP

| Feature | Description |
|---------|-------------|
| **Site Boundary Input** | Draw polygon or import GeoJSON |
| **Setback Definition** | Uniform or per-edge setback distances |
| **Access Point Placement** | Single or multiple vehicular access points |
| **Surface Parking Layout** | Automated 90° stall layout generation |
| **Stall Type Mix** | Standard, compact, ADA distribution |
| **Basic Metrics** | Stall count, gross area, efficiency (SF/stall) |
| **Aisle Configuration** | One-way and two-way options |
| **Rule-Based Validation** | Minimum dimension checks, ADA count validation |
| **2D Plan Export** | PDF and PNG export of layout |
| **Metrics Report** | Summary table exportable as PDF or CSV |
| **Single Ruleset** | US-centric defaults (configurable dimensions) |

#### Deferred to Post-MVP

| Feature | Target Release |
|---------|----------------|
| Above-ground structured parking | v1.5 |
| Underground parking | v1.5 |
| Hybrid configurations | v2.0 |
| Multi-level visualization (3D) | v1.5 |
| DXF/DWG export | v1.2 |
| Grading / slope analysis | v2.0 |
| Stormwater detention areas | v2.0 |
| Multiple jurisdiction rulesets | v1.5 |
| Collaboration / multi-user | v2.0 |
| Cost estimation module | v1.5 |
| API access for third-party integration | v2.0 |
| GIS base map integration | v1.2 |
| Revit / CAD import of existing conditions | v2.0 |
| EV charging stall designation | v1.2 |
| Landscaping / island placement | v1.5 |
| Traffic simulation or queueing analysis | v3.0+ |

### MVP Success Criteria

1. User can complete a surface parking feasibility analysis in under 10 minutes
2. Generated layouts achieve industry-standard efficiency (300–350 SF/stall) on rectangular sites
3. ADA stall counts meet rule-based minimums
4. Exported plans are presentation-ready for client meetings
5. System handles sites up to 10 acres without performance degradation

### MVP Technical Constraints

- Single-user, project-based (no real-time collaboration)
- Web browser-based (Chrome, Edge, Firefox; no desktop client)
- Stateless compute (no persistent background processing)
- English language only
- US customary units (feet, SF) with metric toggle

---

## Appendix: Reference Standards (Informational)

The following standards inform default rulesets. The tool does not certify compliance with any standard.

| Standard | Publisher | Use in Tool |
|----------|-----------|-------------|
| Parking Structures (various editions) | National Parking Association (NPA) | Dimension defaults, efficiency benchmarks |
| Parking Generation (5th Ed.) | Institute of Transportation Engineers (ITE) | Demand ratio references |
| Shared Parking (3rd Ed.) | Urban Land Institute (ULI) | Multi-use adjustment factors |
| ADA Accessibility Guidelines | US Access Board | ADA stall count and dimension rules |
| IBC Chapter 11 | International Code Council | Accessibility minimums |
| Local Zoning Codes | Various | Jurisdiction-specific (user-configured) |

---

## H. User-Authored Geometry Inputs & Constraint Integration

### H.1 Purpose

The system shall allow users to import **externally authored drawings and models** to act as **geometric constraints and structural guides** during parking layout generation, particularly for **above-ground and underground structured parking**.

User-authored geometry is intended to **inform and constrain** the parking layout logic and shall **not** be treated as authoritative construction documentation or verified design intent.

---

### H.2 Supported Import Formats

The system shall support the following input formats for constraint geometry:

| Format          | Intended Use                                                                     |
| --------------- | -------------------------------------------------------------------------------- |
| **DXF / DWG**   | 2D plans, column grids, walls, mechanical rooms, shafts                          |
| **3DM (Rhino)** | Conceptual structural layouts and core volumes (converted to planar constraints) |
| **OBJ**         | Mesh-based volumes simplified to 2D footprints                                   |
| **RVT (Revit)** | Category-filtered extraction of structural and architectural elements            |

Imported geometry shall be associated with a specific **Site**, **Parking Scheme**, and—where applicable—a specific **Parking Level**.

---

### H.3 Interpreted Geometry Semantics

Imported drawings and models are interpreted strictly as **constraint geometry**, not as validated or complete design intent.

The system shall classify imported geometry into one of the following semantic categories:

| Category                          | Interpretation                                          |
| --------------------------------- | ------------------------------------------------------- |
| **Structural Columns**            | Fixed obstructions; stalls and aisles may not intersect |
| **Walls / Cores**                 | No-parking zones; affect circulation and bay continuity |
| **Mechanical / Electrical Rooms** | Hard exclusions removed from available parking area     |
| **Shafts / Voids**                | Vertical exclusions applied across affected levels      |
| **Circulation Exclusions**        | Areas reserved for ramps, loading, or service access    |
| **Unclassified Geometry**         | User-tagged constraints with user-defined behavior      |

Unclassified geometry shall default to **no-parking exclusion** unless explicitly overridden by the user.

---

### H.4 Geometry Processing Requirements

The **Geometry Processor** shall be extended to support user-authored inputs with the following capabilities:

- Layer and category filtering (DXF/DWG, RVT)
- Block and instance expansion (DXF/DWG)
- Unit normalization and coordinate system alignment
- Projection of 3D geometry to active parking planes
- Simplification of curves, meshes, and NURBS into planar polygons
- Geometry validation (self-intersections, invalid topology)
- Semantic tagging and persistence per imported element

All imported geometry shall be converted into internal **polygonal representations** prior to layout processing.

---

### H.5 Layout Engine Integration (Structured Parking)

For **structured and underground parking typologies**, the Layout Engine shall:

- Respect fixed column positions as **non-movable constraints**
- Adapt parking bay modules dynamically to column spacing
- Fit stalls **between** columns where feasible
- Shift aisle centerlines to avoid column conflicts
- Exclude stalls that violate minimum clearance rules
- Flag inefficient or incompatible column grids
- Generate warnings when imported geometry materially reduces parking efficiency

The system shall **not** attempt to redesign, relocate, or optimize user-provided structural elements.

---

### H.6 Validation & User Feedback

When user-authored geometry constrains parking feasibility, the system shall:

- Identify conflicting elements visually in the plan view
- Report affected stalls, bays, and circulation paths
- Provide advisory warnings (e.g., *“Column spacing incompatible with 90° parking”*)
- Allow users to toggle constraint visibility and influence

All validation remains **rule-based and advisory**.

---

### H.7 Explicit Limitations

The system does **not**:

- Validate correctness or completeness of imported drawings or models
- Interpret structural intent, loads, or constructability
- Resolve conflicts between architectural and structural design
- Replace coordination between licensed professionals

All imported geometry is treated as **user-asserted constraints** and is subject to professional verification outside the system.

---

*This document defines the technical foundation for the GenFabTools Parking module. Implementation details, technology stack selection, and detailed specifications will follow in subsequent documentation phases.*
