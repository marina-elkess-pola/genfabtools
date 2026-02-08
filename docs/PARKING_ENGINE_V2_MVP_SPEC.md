# GenFabTools Parking Engine v2 — MVP Specification

> **Document Status:** LOCKED  
> **Version:** 2.0.0-MVP  
> **Date:** February 6, 2026  
> **Author:** Technical Review Process

---

## 1. Overview

### 1.1 Purpose

Parking Engine v2 improves **design intelligence and layout iteration** for early-stage parking feasibility analysis. It does not expand exports, codes, or integrations.

### 1.2 Relationship to v1

**v1 is frozen.** This specification defines additive features only. All v1 behavior, API contracts, and output formats remain unchanged.

| Version | Status | Modifications Allowed |
|---------|--------|----------------------|
| v1.x | FROZEN | Bug fixes only (no behavior changes) |
| v2.0 | ACTIVE | This specification only |

---

## 2. Scope

### 2.1 In Scope (v2 MVP)

| Feature | Description |
|---------|-------------|
| **Zone Data Model** | Named polygons with type, optional stall count targets |
| **Zone Types (2)** | `GENERAL`, `RESERVED` (ADA is a global regulatory overlay, not a zone) |
| **60° Angled Parking** | Fixed-angle stall geometry, one-way aisles only |
| **Zone-Aware Layout** | Orchestrator calls v1 engine per zone, stitches results |
| **Residual Recovery** | Optional post-pass: attempt 60° stalls in leftover polygons |
| **Connectivity Check** | Boolean verification that all aisles connect |
| **Basic Zone UI** | Minimal input for zone definition (no canvas editing) |

### 2.2 Out of Scope (Deferred)

| Feature | Deferred To | Reason |
|---------|-------------|--------|
| Zone types: `VISITOR`, `EMPLOYEE`, `EV`, `LOADING` | v2.1+ | Scope reduction |
| Proximity to entrance logic | v2.1+ | Requires entrance definition |
| Compact stall insertion | v3+ | New stall type, not recovery |
| Herringbone pattern layouts | v2.1+ | Specific layout strategy |
| Circulation graph construction | v2.1+ | Too complex for MVP |
| Circulation scoring (0.0-1.0) | v2.1+ | Requires graph feature |
| Fire lane injection | Never | Breaks determinism |
| Curved aisles | Never | Architectural constraint |
| Mixed angles in same zone | Never | Simplification constraint |
| BIM/Revit integration | Never (v2) | Non-goal |
| New jurisdictions or codes | Never (v2) | Non-goal |

---

## 3. Technical Specification

### 3.1 New Domain Concepts

```
Zone
├── id: string (UUID)
├── name: string
├── type: ZoneType
├── polygon: Polygon
├── stallTarget: number | null (optional min/max)
└── angleConfig: AngleConfig

ZoneType = "GENERAL" | "RESERVED"

AngleConfig = "90_DEGREES" | "60_DEGREES"

ResidualPolygon
├── polygon: Polygon
├── sourceZone: string (zone ID)
└── area: number (sq ft)
```

### 3.2 60° Geometry Parameters

| Parameter | 90° (v1) | 60° (v2) |
|-----------|----------|----------|
| Stall width (parallel to aisle) | 9.0 ft | 10.4 ft |
| Stall depth (perpendicular) | 18.0 ft | 21.0 ft |
| Aisle width (two-way) | 24.0 ft | N/A |
| Aisle width (one-way) | 12.0 ft | 14.0 ft |
| Row-to-row spacing | 60.0 ft | 56.0 ft |

**Constraint:** 60° layouts require one-way aisle pairs. Two-way 60° aisles are not supported.

### 3.3 Pipeline Architecture

```
INPUT
  Site Boundary + Constraints + Zones (optional, default = single GENERAL zone)
      │
      ▼
PHASE 1: Zone Layout
  For each zone in priority order:
    - Apply zone-specific angle config
    - Call v1 layout engine for zone polygon
    - Collect stalls and aisles
      │
      ▼
PHASE 2: Residual Recovery (optional, flag-controlled)
  - Identify residual polygons (min area: 150 sq ft)
  - Attempt 60° stall insertion in leftovers
  - Process polygons in deterministic order
      │
      ▼
PHASE 3: Connectivity Check
  - Verify all aisles connect (boolean)
  - No optimization, no scoring, no injection
      │
      ▼
OUTPUT
  Stalls + Aisles + Zones + Residual Recovered + Metrics
```

### 3.4 API Changes (Additive Only)

**Request additions:**

```json
{
  "zones": [
    {
      "id": "zone-1",
      "name": "Main Lot",
      "type": "GENERAL",
      "polygon": { ... },
      "angleConfig": "90_DEGREES"
    }
  ],
  "allowAngledParking": true,
  "recoverResidual": false
}
```

**Response additions:**

```json
{
  "zones": [
    {
      "id": "zone-1",
      "name": "Main Lot",
      "stallCount": 120
    }
  ],
  "angledStalls": 15,
  "residualRecovered": 8,
  "circulationConnected": true
}
```

**Backwards compatibility:** If `zones` is omitted, the entire site is treated as a single `GENERAL` zone (v1 behavior).

### 3.5 File Structure

All v2 logic resides under `sitefit/sitefit/parking_engine/v2/`. Do not introduce new domain logic directly under `sitefit/`.

```
sitefit/sitefit/parking_engine/v2/
├── __init__.py
├── zones.py           # Zone data model
├── geometry_60.py     # 60° stall geometry
├── orchestrator.py    # Zone-aware layout orchestrator
├── residual.py        # Residual recovery pass
└── connectivity.py    # Connectivity check
```

v1 code remains untouched under `sitefit/sitefit/parking/`.

---

## 4. Determinism Guarantee

All v2 features must produce **identical output for identical input**. This section defines how determinism is preserved.

### 4.1 Deterministic Processing Rules

| Feature | Determinism Mechanism |
|---------|----------------------|
| Zone layout | Sequential processing in `zone.id` alphabetical order |
| 60° stall placement | Same algorithm as v1, different geometry constants |
| Residual recovery | Process polygons by: (1) area descending, (2) centroid X, (3) centroid Y |
| Connectivity check | Read-only analysis, no output modification |

### 4.2 Prohibited Operations

The following operations are **prohibited** because they break determinism:

1. **Fire lane injection** — Would generate geometry not in input
2. **Random sampling** — All operations must be deterministic
3. **Optimization heuristics with randomness** — No simulated annealing, genetic algorithms
4. **Time-dependent logic** — No behavior changes based on timestamps

### 4.3 Verification

For any input `I`, the function `evaluate(I)` must satisfy:

```
evaluate(I) === evaluate(I)  // Always true
```

This will be enforced via snapshot testing in CI.

---

## 5. Design Constraints (Hard Rules)

These constraints are **non-negotiable** and protect the system from scope creep:

1. **No curved aisles** — All geometry is rectilinear or 60° fixed-angle
2. **No mixed angles in same zone** — A zone is 90° or 60°, not both
3. **Zones must be non-overlapping** — Simplifies layout logic
4. **Fire lane requirements are not zone-aware** — Global 26-ft clear path
5. **60° is one-way only** — No two-way 60° aisles
6. **v1 engine is called, not modified** — Zone orchestrator wraps v1

---

## 6. Implementation Order

| Phase | Deliverable | Dependencies |
|-------|-------------|--------------|
| 1 | Zone data model and API schema | None |
| 2 | 60° geometry module | None |
| 3 | Zone-aware layout orchestrator | Phases 1, 2 |
| 4 | Residual recovery pass | Phase 3 |
| 5 | Connectivity check | Phase 3 |

Each phase is independently testable and shippable.

---

## 7. Acceptance Criteria

### 7.1 Functional

- [ ] Zones can be defined via API
- [ ] 60° stalls render correctly with one-way aisles
- [ ] Layout respects zone boundaries (stalls don't span zones)
- [ ] Residual recovery flag controls post-pass behavior
- [ ] `circulationConnected` returns accurate boolean

### 7.2 Non-Functional

- [ ] Identical input produces identical output (determinism)
- [ ] v1 API calls without zones behave exactly as before
- [ ] No performance regression >10% vs v1 for equivalent input

---

## 8. Revision History

| Date | Version | Change |
|------|---------|--------|
| 2026-02-06 | 2.0.0-MVP | Initial locked specification |
| 2026-02-06 | 2.0.0-MVP-r1 | Corrections: removed ADA zone type (global overlay), set recoverResidual default=false, defined v2 file structure |

---

## 9. Approval

This document is the **single source of truth** for Parking Engine v2 MVP.

All implementation must conform to this specification. Any proposed changes require:

1. Written justification
2. Impact analysis on determinism
3. Explicit version bump proposal

**v1 remains frozen. v2 is additive only.**
