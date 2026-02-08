# GenFabTools Parking Engine - Frontend Application

React + TypeScript frontend for early-stage parking feasibility analysis.

## Overview

This frontend is a **decision lens**, not a design tool.

- Displays conceptual, rule-based results
- Supports scenario-based decision making
- Never implies construction readiness or code compliance

All geometry and metrics come from the backend. The frontend does NOT compute or modify parking layouts.

## Architecture

```
parking-app/
├── app/                    # App shell and layout components
│   ├── ParkingApp.tsx      # Main application with three-panel layout
│   ├── ScenarioManager.tsx # Scenario list and selection
│   ├── InputPanel.tsx      # Left panel container
│   ├── ResultsPanel.tsx    # Right panel container
│   └── EvaluateButton.tsx  # Backend evaluation trigger
│
├── state/                  # State management
│   └── scenarioStore.tsx   # Immutable scenario-based state (React Context)
│
├── panels/                 # Input and display panels
│   ├── SiteDefinitionPanel.tsx    # Site boundary input
│   ├── ParkingConfigPanel.tsx     # Parking type and options
│   ├── ConstraintsPanel.tsx       # CAD/BIM constraint import
│   └── MetricsPanel.tsx           # Results and metrics display
│
├── canvas/                 # 2D rendering
│   ├── ParkingCanvas.tsx   # Main canvas with layer composition
│   └── layers/             # Individual render layers
│       ├── SiteBoundaryLayer.tsx
│       ├── ConstraintsLayer.tsx
│       ├── StallsLayer.tsx
│       ├── AislesLayer.tsx
│       ├── RampsLayer.tsx
│       ├── CoresLayer.tsx
│       └── ZonesLayer.tsx
│
├── api/                    # Backend integration
│   └── parkingApi.ts       # Evaluation endpoint, file imports
│
├── utils/                  # Utility functions
│   └── index.ts            # Colors, transforms, formatting
│
├── types.ts                # TypeScript interfaces
└── index.ts                # Module exports
```

## Key Principles

### 1. Frontend is Read-Only

The frontend visualizes backend results. It does NOT:

- Modify stall geometry
- Validate ADA or code compliance
- Optimize layouts
- Align stalls to columns
- Interpret CAD/BIM files
- Generate drawings
- Perform calculations

### 2. Scenario-Based State

All user actions operate on immutable scenarios:

```typescript
interface Scenario {
    id: string;
    name: string;
    siteBoundary: Polygon | null;
    parkingConfig: ParkingConfig;
    constraintsEnabled: boolean;
    constraints: ImportedConstraint[];
    result?: EvaluationResult;
}
```

- No global mutable parking state
- Backend evaluation returns complete results
- Old scenarios remain available for comparison

### 3. Layer-Based Rendering

Canvas renders in a specific order:

1. Site boundary
2. Zones (background)
3. Imported constraints (colored by type)
4. Aisles
5. Parking stalls
6. Ramps
7. Cores

No dragging, snapping, or editing.

## Usage

### Import the Application

```tsx
import { ParkingApp } from "./parking-app";

function App() {
    return <ParkingApp />;
}
```

### Import Individual Components

```tsx
import {
    ScenarioProvider,
    useScenario,
    ParkingCanvas,
    SiteDefinitionPanel,
    MetricsPanel,
} from "./parking-app";
```

### Use the API

```tsx
import {
    evaluateParkingScenario,
    importConstraints,
} from "./parking-app";

// Evaluate a scenario
const result = await evaluateParkingScenario(
    siteBoundary,
    parkingConfig,
    constraints
);
```

## Backend Integration

Single evaluation endpoint:

```
POST /api/parking/evaluate
```

Request:

```json
{
    "siteBoundary": { "points": [...] },
    "parkingConfig": {
        "parkingType": "surface",
        "aisleDirection": "TWO_WAY",
        "setback": 5.0
    },
    "constraints": [...]
}
```

Response:

```json
{
    "success": true,
    "result": {
        "scenarioId": "...",
        "timestamp": "...",
        "parkingResult": {
            "type": "surface",
            "bays": [...],
            "metrics": {...}
        },
        "constraintImpact": {...},
        "warnings": []
    }
}
```

## Constraint Colors

| Type | Color | Hex |
|------|-------|-----|
| Column | Brown | #8B4513 |
| Core | Royal Blue | #4169E1 |
| Wall | Dim Gray | #696969 |
| MEP Room | Dark Orchid | #9932CC |
| Shaft | Dark Slate Gray | #2F4F4F |
| Void | Crimson | #DC143C |
| Unknown | Gray | #808080 |

## Stall Colors

| Type | Color | Hex |
|------|-------|-----|
| Standard | Green | #4CAF50 |
| Compact | Light Green | #8BC34A |
| ADA | Blue | #2196F3 |
| ADA Van | Dark Blue | #1976D2 |

## Styling

Uses Tailwind CSS for styling. No additional CSS files required.

## Dependencies

- React 19+
- React DOM
- TypeScript

## Explicit Exclusions

The frontend does NOT:

- Produce construction documents
- Certify code compliance
- Handle non-orthogonal geometries
- Generate DXF/DWG exports
- Consider grading or stormwater
- Perform structural calculations
- Relocate columns for optimization
- Optimize for maximum stalls

## License

Internal use only. Part of GenFabTools platform.

---

## V1.0 Scope Lock

**Release Date:** January 2025

### What's Included in V1

| Feature | Status |
|---------|--------|
| **Surface Parking** | ✅ Included |
| Rectangular site input | ✅ Included |
| DXF boundary import | ✅ Included |
| One-way / Two-way aisles | ✅ Included |
| Setback configuration | ✅ Included |
| Stall count metrics | ✅ Included |
| Efficiency metrics (SF/stall) | ✅ Included |
| ADA stall calculation | ✅ Included |
| CAD constraint import (DXF) | ✅ Included |
| Constraint impact display | ✅ Included |
| Multi-scenario comparison | ✅ Included |
| "How This Result Was Generated" | ✅ Included |
| "Why Not More Stalls?" hint | ✅ Included |
| **Structured Parking** | 🚧 Coming Next |
| Multi-level calculation | ⏳ Not in V1 |
| Ramp layout | ⏳ Not in V1 |
| Core placement | ⏳ Not in V1 |
| Column grid constraints | ⏳ Not in V1 |

### Determinism

V1 is **fully deterministic**:

- Same inputs always produce same outputs
- No randomization in layout algorithm
- Results are reproducible across sessions

### Edge States Handled

| Condition | Display |
|-----------|---------|
| No site defined | "Ready to evaluate" with instructions |
| Site too small | Error with 50' minimum guidance |
| Zero stalls fit | Warning with adjustment suggestions |
| Backend unavailable | "Unable to connect" with retry prompt |
| Invalid polygon | "Invalid site shape" with guidance |

### Explicit Exclusions (Not in Roadmap)

- Construction document generation
- Code compliance certification
- DXF/DWG export
- Grading or stormwater analysis
- Structural calculations
- Column relocation optimization
- Non-orthogonal geometries
