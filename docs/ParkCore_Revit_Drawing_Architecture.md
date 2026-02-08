# ParkCore Drawing Architecture Proposal (Revit-integrated)

## Objective

Make ParkCore's drawing workflows flexible and architect-grade accurate by integrating with Autodesk Revit, aligning with real-world design processes while keeping the web app responsive and modern.

## Recommendation Summary

- Primary language: C# (.NET 8) targeting Revit API for in-application tools and data exchange.
- Interop: Revit add-in (C#) + Local service bridge for web app via REST/websocket.
- Secondary scripting: Python (RevitPythonShell or pyRevit) for rapid prototypes and certain automation.
- Keep frontend web stack (Vite/React) for UI; use TypeScript for shared schemas.

## Rationale

- Revit API is first-class in C#/.NET; full access to `Autodesk.Revit.DB` for geometry, parameters, transactions, and document management.
- Deterministic geometry ops (e.g., `Curve`, `Solid`, `XYZ`) and transaction safety require .NET.
- Ecosystem maturity: templates, debugging, deployment, installer story.

## Architecture Overview

1. Revit Add-in (`ParkCore.RevitAddin`)
   - C#/.NET 8 class library; compiled to .NET Framework compatibility via Revit constraints (version-specific). Use multi-targeting and shim if necessary.
   - Commands: `ExternalCommand`, `ExternalApplication` with UI ribbon panel.
   - Features: ParkCore drawing helpers (placement, circulation, parking layout), model validation, parameter syncing.
   - IO: JSON over localhost websocket/REST to the ParkCore web app backend.

2. Local Bridge Service (`ParkCore.LocalBridge`)
   - Node.js service (existing backend) or .NET minimal API for lower-latency.
   - Responsibilities: session auth, schema validation, queuing, conflict resolution.
   - Message types: Place/Update/Delete, Analyze, Sync Parameters, Export.

3. Web App (`ParkCore.Web`)
   - React/TypeScript UI for controls, visualization, and state.
   - Shared types via `openapi.json` or `zod` schema; use `proto` if latency-critical.

## Integration Flow

- Architect performs operations in Revit. Add-in captures context (levels, scope boxes, grids).
- Add-in sends intent to Bridge; Bridge validates and forwards to web backend; UI reflects state.
- For reversed flow (web → Revit), the Bridge pushes commands; Add-in executes within Revit `Transaction` scope.

## Versioning & Compatibility

- Revit version-specific builds (e.g., 2021–2025). Maintain per-version `addin` manifest.
- API shims for differences (e.g., `CurveLoop`, `Transaction` nuances).

## Security & Deployment

- Localhost-only by default; opt-in network exposure.
- Signed add-in DLLs; MSI installer with per-user install.
- Telemetry via optional opt-in.

## Phased Rollout

- Phase 0: Prototype with pyRevit/RevitPythonShell for circulation helpers.
- Phase 1: C# add-in skeleton + Bridge service; implement placements and sync.
- Phase 2: Advanced geometry (adaptive components, parking stall generation, validation rules).
- Phase 3: Performance pass, caching, partial document updates.

## Open Questions

- Target Revit versions in production?
- Bridge choice: Node (reuse) vs .NET (performance)?
- Offline mode requirements?

## Next Steps

- Confirm requirements above.
- Initialize `revit_addin` solution with command skeletons.
- Define message schemas and start Bridge prototype.
