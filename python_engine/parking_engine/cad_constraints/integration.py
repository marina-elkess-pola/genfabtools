"""
CAD/BIM Constraint Integration
==============================

Integration of imported CAD/BIM constraints with the parking engine.

This module provides clean interfaces to apply imported constraints
to surface and structured parking layouts:

Surface Parking:
    - Subtract constraint polygons from site boundary
    - Treat constraints as VOID zones during decomposition
    - Generate parking only in remaining geometry

Structured Parking:
    - For each level, subtract imported constraints (in addition to ramps/cores)
    - Drop stalls intersecting constraints
    - Track stalls lost per constraint type

Constraints act as hard exclusions only.
The engine does NOT relocate stalls to avoid constraints.

Current Limitations (v1):
    - Each zone uses the same orientation strategy (horizontal preferred)
    - Residual areas after bay placement are not re-evaluated
    - Alternative circulation strategies (secondary aisles, reoriented bays)
      could recover additional stalls but are not currently implemented
    - Future versions may add:
        * Per-zone orientation optimization
        * Residual area subdivision with secondary aisles
        * Mixed orientation layouts (e.g., angled parking in tight areas)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from ..geometry import Polygon, Point, subtract_polygon, rectangles_overlap
from ..rules import ParkingRules, AisleDirection
from ..layout import (
    SurfaceParkingLayout,
    ParkingBay,
    Stall,
    Aisle,
    generate_surface_layout,
)
from ..structured import StructuredParkingLayout, ParkingLevel
from ..structured_layout import (
    LevelLayout,
    StructuredLayoutWithStalls,
    StructuralBayConfig,
    generate_level_layout,
    validate_stalls_avoid_exclusions,
    compute_net_parkable_geometry,
    _prefix_layout_ids,
)

from .models import (
    ImportedConstraint,
    ConstraintType,
    ConstraintSet,
    ConstraintImpact,
    LevelConstraintImpact,
)


# =============================================================================
# CONSTRAINED SURFACE LAYOUT
# =============================================================================

@dataclass
class ConstrainedSurfaceLayout:
    """
    Surface parking layout with CAD/BIM constraints applied.

    Wraps a SurfaceParkingLayout with constraint metadata.
    """
    layout: Optional[SurfaceParkingLayout]
    constraints_applied: ConstraintSet
    constraint_impact: ConstraintImpact

    # Processing metadata
    original_site_area: float = 0.0
    constrained_site_area: float = 0.0
    constraints_subtracted: int = 0
    stalls_removed: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def total_stalls(self) -> int:
        """Total stalls in constrained layout."""
        if self.layout is None:
            return 0
        return self.layout.total_stalls

    @property
    def area_reduction_pct(self) -> float:
        """Percentage of site area lost to constraints."""
        if self.original_site_area == 0:
            return 0.0
        return 100.0 * (1.0 - self.constrained_site_area / self.original_site_area)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout": self.layout.to_dict() if self.layout else None,
            "constraints_applied": self.constraints_applied.to_dict(),
            "constraint_impact": self.constraint_impact.to_dict(),
            "original_site_area_sf": round(self.original_site_area, 2),
            "constrained_site_area_sf": round(self.constrained_site_area, 2),
            "area_reduction_pct": round(self.area_reduction_pct, 1),
            "constraints_subtracted": self.constraints_subtracted,
            "stalls_removed": self.stalls_removed,
            "total_stalls": self.total_stalls,
            "notes": self.notes,
        }

    def summary(self) -> str:
        lines = [
            "=== Constrained Surface Parking Layout ===",
            "",
            f"Constraints Applied: {self.constraints_subtracted}",
            f"Original Site Area: {self.original_site_area:,.0f} SF",
            f"Constrained Area: {self.constrained_site_area:,.0f} SF ({self.area_reduction_pct:.1f}% reduction)",
            f"Total Stalls: {self.total_stalls}",
            "",
        ]
        lines.append(self.constraint_impact.summary())
        if self.notes:
            lines.append("")
            lines.append("Notes:")
            for note in self.notes[:5]:
                lines.append(f"  • {note}")
        return "\n".join(lines)


def apply_constraints_to_surface_layout(
    site_boundary: Polygon,
    constraints: ConstraintSet,
    rules: Optional[ParkingRules] = None,
    aisle_direction: AisleDirection = AisleDirection.TWO_WAY,
    setback: float = 5.0,
    setbacks: Optional[dict] = None,
    orientation: str = "auto",
    compute_unconstrained_baseline: bool = True,
) -> ConstrainedSurfaceLayout:
    """
    Apply CAD/BIM constraints to a surface parking layout.

    Process:
        1. Optionally compute unconstrained layout for baseline
        2. Subtract constraint polygons from site boundary
        3. Decompose remaining geometry into independent zones
        4. Generate layout for EACH valid zone independently
        5. Merge zone layouts into single result
        6. Remove any stalls that overlap constraints
        7. Compute constraint impact metrics

    When constraints split the site into multiple disconnected regions,
    each region is treated as an independent parking zone. This ensures
    valid parking areas are not discarded just because they're separated.

    Args:
        site_boundary: Original site boundary polygon
        constraints: Set of imported constraints to apply
        rules: Parking dimension rules
        aisle_direction: One-way or two-way aisles
        setback: Uniform setback distance from site boundary
        setbacks: Per-edge setbacks dict (overrides uniform setback)
        orientation: Bay orientation
        compute_unconstrained_baseline: Whether to compute baseline for comparison

    Returns:
        ConstrainedSurfaceLayout with applied constraints
    """
    rules = rules or ParkingRules()
    notes = []
    original_site_area = site_boundary.area

    # Step 1: Optionally compute unconstrained baseline
    unconstrained_stalls = 0
    if compute_unconstrained_baseline:
        try:
            baseline_layout = generate_surface_layout(
                site_boundary=site_boundary,
                rules=rules,
                aisle_direction=aisle_direction,
                setback=setback if setbacks is None else None,
                setbacks=setbacks,
                orientation=orientation,
            )
            unconstrained_stalls = baseline_layout.total_stalls
        except Exception as e:
            notes.append(f"Baseline layout failed: {e}")

    # Step 2: Subtract constraints and get ALL valid zones (multi-zone)
    zones, subtraction_notes = _subtract_constraints_multizone(
        site_boundary, constraints.get_polygons()
    )
    notes.extend(subtraction_notes)

    constraints_subtracted = len(constraints.constraints)

    # Calculate total constrained area across all zones
    constrained_site_area = sum(zone.area for zone in zones)

    # Step 3: Check if any remaining area is viable
    if not zones:
        notes.append("All parkable area consumed by constraints")
        return ConstrainedSurfaceLayout(
            layout=None,
            constraints_applied=constraints,
            constraint_impact=ConstraintImpact(
                unconstrained_stalls=unconstrained_stalls,
                constrained_stalls=0,
                total_stalls_lost=unconstrained_stalls,
                total_area_lost=original_site_area,
                efficiency_delta=1.0,
            ),
            original_site_area=original_site_area,
            constrained_site_area=0.0,
            constraints_subtracted=constraints_subtracted,
            notes=notes,
        )

    # Step 4: Generate layout for EACH zone independently
    zone_layouts = []
    zone_failures = 0

    for zone_idx, zone in enumerate(zones):
        try:
            zone_layout = generate_surface_layout(
                site_boundary=zone,
                rules=rules,
                aisle_direction=aisle_direction,
                setback=setback if setbacks is None else None,
                setbacks=setbacks,
                orientation=orientation,
            )
            zone_layouts.append(zone_layout)
            notes.append(
                f"Zone {zone_idx}: {zone_layout.total_stalls} stalls in {zone.area:.0f} SF")
        except Exception as e:
            zone_failures += 1
            notes.append(f"Zone {zone_idx} layout failed: {e}")

    if not zone_layouts:
        notes.append("All zone layouts failed")
        return ConstrainedSurfaceLayout(
            layout=None,
            constraints_applied=constraints,
            constraint_impact=ConstraintImpact(
                unconstrained_stalls=unconstrained_stalls,
                constrained_stalls=0,
                total_stalls_lost=unconstrained_stalls,
                total_area_lost=original_site_area,
                efficiency_delta=1.0,
            ),
            original_site_area=original_site_area,
            constrained_site_area=constrained_site_area,
            constraints_subtracted=constraints_subtracted,
            notes=notes,
        )

    # Step 5: Merge zone layouts into single result
    layout = _merge_surface_layouts(
        zone_layouts,
        original_site=site_boundary,
        rules=rules,
        aisle_direction=aisle_direction,
    )

    notes.append(
        f"Merged {len(zone_layouts)} zones: {layout.total_stalls} total stalls")

    # Step 6: Validate and remove overlapping stalls (safety check)
    stalls_removed = 0
    constraint_polygons = constraints.get_polygons()
    all_stalls = layout.all_stalls

    valid_stalls, invalid_stalls, warnings = validate_stalls_avoid_exclusions(
        all_stalls, constraint_polygons
    )
    stalls_removed = len(invalid_stalls)
    notes.extend(warnings)

    # Remove invalid stalls from bays
    if invalid_stalls:
        invalid_ids = {s.id for s in invalid_stalls}
        for bay in layout.bays:
            bay.north_stalls = [
                s for s in bay.north_stalls if s.id not in invalid_ids]
            bay.south_stalls = [
                s for s in bay.south_stalls if s.id not in invalid_ids]

    # Step 7: Compute constraint impact
    constrained_stalls = layout.total_stalls
    impact = _compute_surface_impact(
        constraints=constraints,
        unconstrained_stalls=unconstrained_stalls,
        constrained_stalls=constrained_stalls,
        stalls_removed=stalls_removed,
        original_area=original_site_area,
        constrained_area=constrained_site_area,
    )

    return ConstrainedSurfaceLayout(
        layout=layout,
        constraints_applied=constraints,
        constraint_impact=impact,
        original_site_area=original_site_area,
        constrained_site_area=constrained_site_area,
        constraints_subtracted=constraints_subtracted,
        stalls_removed=stalls_removed,
        notes=notes,
    )


def _subtract_constraints_from_site(
    site: Polygon,
    constraint_polygons: List[Polygon],
) -> Tuple[Optional[Polygon], List[str]]:
    """
    Subtract constraint polygons from site boundary.

    Returns the largest remaining rectangular region.

    DEPRECATED: Use _subtract_constraints_multizone for proper zone handling.
    """
    notes = []

    if not constraint_polygons:
        return site, notes

    # Use existing subtract logic, similar to structured layout
    remaining = site

    for i, constraint in enumerate(constraint_polygons):
        # Check if constraint overlaps site
        if not rectangles_overlap(remaining, constraint):
            continue

        # Subtract constraint
        fragments = subtract_polygon(remaining, constraint)

        if not fragments:
            notes.append(f"Constraint {i} consumed entire remaining site")
            return None, notes

        # Keep largest fragment
        remaining = max(fragments, key=lambda p: p.area)
        notes.append(
            f"Subtracted constraint {i}, {len(fragments)} fragments, keeping {remaining.area:.0f} SF")

    return remaining, notes


# Minimum viable zone size (sq ft) - must fit at least one double-loaded bay
MIN_ZONE_AREA = 1000.0  # ~20 stalls minimum
MIN_ZONE_WIDTH = 30.0   # Must fit one module width
MIN_ZONE_HEIGHT = 30.0  # Must fit at least one stall depth


def _subtract_constraints_multizone(
    site: Polygon,
    constraint_polygons: List[Polygon],
) -> Tuple[List[Polygon], List[str]]:
    """
    Subtract constraint polygons from site boundary, preserving ALL valid zones.

    Unlike _subtract_constraints_from_site which keeps only the largest fragment,
    this function preserves all fragments that meet minimum size thresholds.
    This enables parking generation in disconnected zones after constraint splitting.

    Args:
        site: Original site boundary polygon
        constraint_polygons: List of constraint polygons to subtract

    Returns:
        Tuple of (list of valid zone polygons, list of processing notes)
    """
    notes = []

    if not constraint_polygons:
        return [site], notes

    # Start with the original site as the only zone
    zones = [site]

    for i, constraint in enumerate(constraint_polygons):
        new_zones = []

        for zone in zones:
            # Check if constraint overlaps this zone
            if not rectangles_overlap(zone, constraint):
                # No overlap - keep zone as-is
                new_zones.append(zone)
                continue

            # Subtract constraint from this zone
            fragments = subtract_polygon(zone, constraint)

            if not fragments:
                notes.append(
                    f"Constraint {i} consumed zone ({zone.area:.0f} SF)")
                continue

            # Filter fragments by minimum size thresholds
            for frag in fragments:
                frag_area = frag.area
                frag_bounds = frag.bounds
                frag_width = frag_bounds[2] - frag_bounds[0]
                frag_height = frag_bounds[3] - frag_bounds[1]

                if (frag_area >= MIN_ZONE_AREA and
                    frag_width >= MIN_ZONE_WIDTH and
                        frag_height >= MIN_ZONE_HEIGHT):
                    new_zones.append(frag)
                else:
                    notes.append(
                        f"Discarded small fragment ({frag_area:.0f} SF, {frag_width:.0f}x{frag_height:.0f})")

        zones = new_zones

        if not zones:
            notes.append(f"Constraint {i} consumed all remaining zones")
            return [], notes

    notes.append(
        f"Zone decomposition: {len(zones)} parkable zones after constraint subtraction")
    for j, zone in enumerate(zones):
        notes.append(f"  Zone {j}: {zone.area:.0f} SF")

    return zones, notes


def _merge_surface_layouts(
    layouts: List[SurfaceParkingLayout],
    original_site: Polygon,
    rules: ParkingRules,
    aisle_direction: AisleDirection,
) -> SurfaceParkingLayout:
    """
    Merge multiple zone layouts into a single SurfaceParkingLayout.

    Each zone layout gets a unique prefix on IDs to avoid collisions.
    Combined metrics represent the sum of all zones.

    Args:
        layouts: List of zone layouts to merge
        original_site: Original site boundary (for reference)
        rules: Parking rules used
        aisle_direction: Aisle direction used

    Returns:
        Merged SurfaceParkingLayout containing all bays from all zones
    """
    if not layouts:
        # Return empty layout
        return SurfaceParkingLayout(
            site_boundary=original_site,
            net_parking_area=Polygon(
                [Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)]),
            bays=[],
            drive_lanes=[],
            rules=rules,
            aisle_direction=aisle_direction,
            orientation="horizontal",
        )

    if len(layouts) == 1:
        # Single zone - no merge needed, but update site boundary
        layout = layouts[0]
        return SurfaceParkingLayout(
            site_boundary=original_site,
            net_parking_area=layout.net_parking_area,
            bays=layout.bays,
            drive_lanes=layout.drive_lanes,
            rules=layout.rules,
            aisle_direction=layout.aisle_direction,
            orientation=layout.orientation,
        )

    # Merge multiple zone layouts
    merged_bays = []
    merged_drive_lanes = []
    net_areas = []

    for zone_idx, layout in enumerate(layouts):
        zone_prefix = f"z{zone_idx}_"

        # Prefix bay and stall IDs to avoid collisions
        for bay in layout.bays:
            # Create new bay with prefixed IDs
            prefixed_bay = ParkingBay(
                id=zone_prefix + bay.id,
                aisle=Aisle(
                    id=zone_prefix + bay.aisle.id,
                    geometry=bay.aisle.geometry,
                    direction=bay.aisle.direction,
                    bay_id=zone_prefix + bay.id,
                ),
                north_stalls=[
                    Stall(
                        id=zone_prefix + s.id,
                        geometry=s.geometry,
                        stall_type=s.stall_type,
                        bay_id=zone_prefix + bay.id,
                        row=s.row,
                        access_aisle=s.access_aisle,
                    )
                    for s in bay.north_stalls
                ],
                south_stalls=[
                    Stall(
                        id=zone_prefix + s.id,
                        geometry=s.geometry,
                        stall_type=s.stall_type,
                        bay_id=zone_prefix + bay.id,
                        row=s.row,
                        access_aisle=s.access_aisle,
                    )
                    for s in bay.south_stalls
                ],
            )
            merged_bays.append(prefixed_bay)

        # Collect drive lanes
        merged_drive_lanes.extend(layout.drive_lanes)
        net_areas.append(layout.net_parking_area)

    # Use the largest zone's net area for reporting (or combine bounds)
    if net_areas:
        combined_net_area = max(net_areas, key=lambda p: p.area)
    else:
        combined_net_area = Polygon(
            [Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)])

    return SurfaceParkingLayout(
        site_boundary=original_site,
        net_parking_area=combined_net_area,
        bays=merged_bays,
        drive_lanes=merged_drive_lanes,
        rules=rules,
        aisle_direction=aisle_direction,
        orientation=layouts[0].orientation if layouts else "horizontal",
    )

    return remaining, notes


def _compute_surface_impact(
    constraints: ConstraintSet,
    unconstrained_stalls: int,
    constrained_stalls: int,
    stalls_removed: int,
    original_area: float,
    constrained_area: float,
) -> ConstraintImpact:
    """
    Compute impact metrics for surface parking constraints.
    """
    total_stalls_lost = unconstrained_stalls - constrained_stalls
    total_area_lost = original_area - constrained_area

    # Compute efficiency delta
    efficiency_delta = 0.0
    if unconstrained_stalls > 0:
        efficiency_delta = total_stalls_lost / unconstrained_stalls

    # Approximate loss per constraint type
    stalls_lost_by_type: Dict[str, int] = {}
    area_lost_by_type: Dict[str, float] = {}

    if constraints.count > 0 and total_stalls_lost > 0:
        # Distribute losses proportionally by constraint area
        total_constraint_area = constraints.total_area
        for ctype, clist in constraints.by_type.items():
            type_area = sum(c.area for c in clist)
            type_key = ctype.to_string()

            if total_constraint_area > 0:
                ratio = type_area / total_constraint_area
                stalls_lost_by_type[type_key] = round(
                    total_stalls_lost * ratio)
                area_lost_by_type[type_key] = type_area
            else:
                stalls_lost_by_type[type_key] = 0
                area_lost_by_type[type_key] = type_area

    return ConstraintImpact(
        total_stalls_lost=total_stalls_lost,
        total_area_lost=total_area_lost,
        stalls_lost_by_type=stalls_lost_by_type,
        area_lost_by_type=area_lost_by_type,
        unconstrained_stalls=unconstrained_stalls,
        constrained_stalls=constrained_stalls,
        efficiency_delta=efficiency_delta,
    )


# =============================================================================
# CONSTRAINED STRUCTURED LAYOUT
# =============================================================================

@dataclass
class ConstrainedStructuredLayout:
    """
    Structured parking layout with CAD/BIM constraints applied.

    Extends StructuredLayoutWithStalls with constraint tracking.
    """
    layout: Optional[StructuredLayoutWithStalls]
    constraints_applied: ConstraintSet
    constraint_impact: ConstraintImpact
    level_impacts: List[LevelConstraintImpact] = field(default_factory=list)

    # Processing metadata
    notes: List[str] = field(default_factory=list)

    @property
    def total_stalls(self) -> int:
        if self.layout is None:
            return 0
        return self.layout.total_stalls

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout": self.layout.to_dict() if self.layout else None,
            "constraints_applied": self.constraints_applied.to_dict(),
            "constraint_impact": self.constraint_impact.to_dict(),
            "level_impacts": [li.to_dict() for li in self.level_impacts],
            "total_stalls": self.total_stalls,
            "notes": self.notes,
        }

    def summary(self) -> str:
        lines = [
            "=== Constrained Structured Parking Layout ===",
            "",
        ]
        if self.layout:
            lines.append(self.layout.summary())
        lines.append("")
        lines.append(self.constraint_impact.summary())

        if self.level_impacts:
            lines.append("")
            lines.append("Per-Level Constraint Impact:")
            for li in self.level_impacts:
                lines.append(
                    f"  L{li.level_index}: {li.stalls_lost} stalls lost, "
                    f"{li.area_lost:.0f} SF excluded"
                )

        return "\n".join(lines)


def apply_constraints_to_structured_layout(
    structured_layout: StructuredParkingLayout,
    constraints: ConstraintSet,
    rules: Optional[ParkingRules] = None,
    aisle_direction: AisleDirection = AisleDirection.TWO_WAY,
    setback: float = 0.0,
    orientation: str = "auto",
    bay_config: Optional[StructuralBayConfig] = None,
    compute_unconstrained_baseline: bool = True,
) -> ConstrainedStructuredLayout:
    """
    Apply CAD/BIM constraints to a structured parking layout.

    Process:
        1. Optionally compute unconstrained layout for baseline
        2. For each level:
            a. Add constraint polygons to exclusion list
            b. Generate layout with exclusions
            c. Remove stalls overlapping constraints
            d. Track impact per constraint type
        3. Aggregate constraint impacts

    Args:
        structured_layout: Skeleton from generate_structured_parking_skeleton()
        constraints: Set of imported constraints to apply
        rules: Parking dimension rules
        aisle_direction: One-way or two-way aisles
        setback: Setback distance
        orientation: Bay orientation
        bay_config: Structural bay heuristics
        compute_unconstrained_baseline: Whether to compute baseline

    Returns:
        ConstrainedStructuredLayout with applied constraints
    """
    rules = rules or structured_layout.rules
    bay_config = bay_config or StructuralBayConfig()
    notes = []

    # Step 1: Optionally compute unconstrained baseline
    unconstrained_stalls = 0
    if compute_unconstrained_baseline:
        from ..structured_layout import generate_structured_parking_layout
        try:
            baseline = generate_structured_parking_layout(
                structured_layout=structured_layout,
                rules=rules,
                aisle_direction=aisle_direction,
                setback=setback,
                orientation=orientation,
                bay_config=bay_config,
            )
            unconstrained_stalls = baseline.total_stalls
        except Exception as e:
            notes.append(f"Baseline layout failed: {e}")

    # Step 2: Generate constrained layout for each level
    level_layouts = []
    level_impacts = []
    total_stalls = 0
    stalls_by_type: Dict[str, int] = {}
    stalls_per_level = []
    stalls_lost_to_constraints = 0
    inefficiency_notes = []

    constraint_polygons = constraints.get_polygons()

    for level in structured_layout.levels:
        # Generate layout with constraints as additional exclusions
        level_layout, level_impact = _generate_constrained_level_layout(
            level=level,
            constraints=constraints,
            constraint_polygons=constraint_polygons,
            rules=rules,
            aisle_direction=aisle_direction,
            setback=setback,
            orientation=orientation,
        )

        level_layouts.append(level_layout)
        level_impacts.append(level_impact)

        # Aggregate
        level_stall_count = level_layout.stall_count
        stalls_per_level.append(level_stall_count)
        total_stalls += level_stall_count
        stalls_lost_to_constraints += level_impact.stalls_lost

        for stall in level_layout.all_stalls:
            key = stall.stall_type.value
            stalls_by_type[key] = stalls_by_type.get(key, 0) + 1

        if not level_layout.placement_successful:
            inefficiency_notes.append(
                f"Level {level.level_index}: Placement failed")

    # Step 3: Create layout wrapper
    constrained_layout = StructuredLayoutWithStalls(
        skeleton=structured_layout,
        level_layouts=level_layouts,
        bay_config=bay_config,
        aisle_direction=aisle_direction,
        total_stalls=total_stalls,
        total_stalls_by_type=stalls_by_type,
        stalls_per_level=stalls_per_level,
        stalls_lost_to_exclusions=stalls_lost_to_constraints,
        inefficiency_notes=inefficiency_notes,
    )

    # Step 4: Compute overall constraint impact
    impact = _compute_structured_impact(
        constraints=constraints,
        level_impacts=level_impacts,
        unconstrained_stalls=unconstrained_stalls,
        constrained_stalls=total_stalls,
    )

    return ConstrainedStructuredLayout(
        layout=constrained_layout,
        constraints_applied=constraints,
        constraint_impact=impact,
        level_impacts=level_impacts,
        notes=notes,
    )


def _generate_constrained_level_layout(
    level: ParkingLevel,
    constraints: ConstraintSet,
    constraint_polygons: List[Polygon],
    rules: ParkingRules,
    aisle_direction: AisleDirection,
    setback: float,
    orientation: str,
) -> Tuple[LevelLayout, LevelConstraintImpact]:
    """
    Generate layout for a single level with constraints applied.
    """
    notes = []

    # Compute net parkable geometry with constraints as additional exclusions
    net_parkable, exclusions = compute_net_parkable_geometry(
        level, additional_exclusions=constraint_polygons
    )

    # Calculate constraint area on this level
    constraint_area_on_level = 0.0
    constraints_on_level = 0
    for cp in constraint_polygons:
        if rectangles_overlap(level.gross_footprint, cp):
            # Approximate overlap area
            overlap_area = _estimate_overlap_area(level.gross_footprint, cp)
            constraint_area_on_level += overlap_area
            constraints_on_level += 1

    # Generate layout
    level_layout = generate_level_layout(
        level=level,
        rules=rules,
        aisle_direction=aisle_direction,
        setback=setback,
        orientation=orientation,
    )

    # Override exclusions to include constraints
    level_layout.excluded_areas = exclusions

    # Validate stalls don't overlap constraints
    if level_layout.surface_layout:
        all_stalls = level_layout.all_stalls
        valid_stalls, invalid_stalls, warnings = validate_stalls_avoid_exclusions(
            all_stalls, constraint_polygons
        )

        stalls_lost = len(invalid_stalls)
        notes.extend(warnings)

        # Remove invalid stalls
        if invalid_stalls:
            invalid_ids = {s.id for s in invalid_stalls}
            for bay in level_layout.surface_layout.bays:
                bay.north_stalls = [
                    s for s in bay.north_stalls if s.id not in invalid_ids]
                bay.south_stalls = [
                    s for s in bay.south_stalls if s.id not in invalid_ids]
    else:
        stalls_lost = 0

    # Track stalls lost by constraint type
    stalls_lost_by_type: Dict[str, int] = {}
    area_lost_by_type: Dict[str, float] = {}

    if stalls_lost > 0 and constraints.count > 0:
        for ctype, clist in constraints.by_type.items():
            type_key = ctype.to_string()
            type_area = sum(
                _estimate_overlap_area(level.gross_footprint, c.geometry)
                for c in clist
            )
            if constraint_area_on_level > 0:
                ratio = type_area / constraint_area_on_level
                stalls_lost_by_type[type_key] = round(stalls_lost * ratio)
            area_lost_by_type[type_key] = type_area

    level_impact = LevelConstraintImpact(
        level_index=level.level_index,
        stalls_lost=stalls_lost,
        area_lost=constraint_area_on_level,
        stalls_lost_by_type=stalls_lost_by_type,
        area_lost_by_type=area_lost_by_type,
        constraints_applied=constraints_on_level,
    )

    level_layout.placement_notes.extend(notes)

    return level_layout, level_impact


def _estimate_overlap_area(p1: Polygon, p2: Polygon) -> float:
    """
    Estimate overlap area between two rectangles.
    """
    min1_x, min1_y, max1_x, max1_y = p1.bounds
    min2_x, min2_y, max2_x, max2_y = p2.bounds

    overlap_min_x = max(min1_x, min2_x)
    overlap_max_x = min(max1_x, max2_x)
    overlap_min_y = max(min1_y, min2_y)
    overlap_max_y = min(max1_y, max2_y)

    if overlap_max_x <= overlap_min_x or overlap_max_y <= overlap_min_y:
        return 0.0

    return (overlap_max_x - overlap_min_x) * (overlap_max_y - overlap_min_y)


def _compute_structured_impact(
    constraints: ConstraintSet,
    level_impacts: List[LevelConstraintImpact],
    unconstrained_stalls: int,
    constrained_stalls: int,
) -> ConstraintImpact:
    """
    Compute aggregate constraint impact across all levels.
    """
    total_stalls_lost = sum(li.stalls_lost for li in level_impacts)
    total_area_lost = sum(li.area_lost for li in level_impacts)

    # Aggregate by type
    stalls_lost_by_type: Dict[str, int] = {}
    area_lost_by_type: Dict[str, float] = {}

    for li in level_impacts:
        for ctype, count in li.stalls_lost_by_type.items():
            stalls_lost_by_type[ctype] = stalls_lost_by_type.get(
                ctype, 0) + count
        for ctype, area in li.area_lost_by_type.items():
            area_lost_by_type[ctype] = area_lost_by_type.get(ctype, 0) + area

    # Efficiency delta
    efficiency_delta = 0.0
    if unconstrained_stalls > 0:
        efficiency_delta = (unconstrained_stalls -
                            constrained_stalls) / unconstrained_stalls

    return ConstraintImpact(
        total_stalls_lost=total_stalls_lost,
        total_area_lost=total_area_lost,
        stalls_lost_by_type=stalls_lost_by_type,
        area_lost_by_type=area_lost_by_type,
        unconstrained_stalls=unconstrained_stalls,
        constrained_stalls=constrained_stalls,
        efficiency_delta=efficiency_delta,
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def compute_constraint_impact(
    constraints: ConstraintSet,
    site_or_layout,
    **layout_options,
) -> ConstraintImpact:
    """
    Compute the impact of constraints on a site or layout.

    This is a convenience function that applies constraints and
    returns only the impact metrics.

    Args:
        constraints: Set of constraints to apply
        site_or_layout: Either a Polygon (surface) or StructuredParkingLayout
        **layout_options: Options passed to layout generation

    Returns:
        ConstraintImpact with stalls/area lost
    """
    if isinstance(site_or_layout, Polygon):
        result = apply_constraints_to_surface_layout(
            site_boundary=site_or_layout,
            constraints=constraints,
            **layout_options,
        )
        return result.constraint_impact

    elif isinstance(site_or_layout, StructuredParkingLayout):
        result = apply_constraints_to_structured_layout(
            structured_layout=site_or_layout,
            constraints=constraints,
            **layout_options,
        )
        return result.constraint_impact

    else:
        raise TypeError(
            f"Expected Polygon or StructuredParkingLayout, got {type(site_or_layout)}"
        )


def create_constraint_from_polygon(
    polygon: Polygon,
    constraint_type: ConstraintType = ConstraintType.UNKNOWN,
    source_format: str = "dxf",
    layer: str = "constraints",
    constraint_id: Optional[str] = None,
) -> ImportedConstraint:
    """
    Create an ImportedConstraint from a Polygon.

    Convenience function for programmatic constraint creation.
    """
    return ImportedConstraint(
        geometry=polygon,
        constraint_type=constraint_type,
        source_format=source_format,
        source_layer_or_category=layer,
        source_id=constraint_id,
        confidence=1.0 if constraint_type != ConstraintType.UNKNOWN else 0.5,
    )


def create_constraint_set_from_polygons(
    polygons: List[Polygon],
    constraint_type: ConstraintType = ConstraintType.UNKNOWN,
    source_format: str = "dxf",
    layer: str = "constraints",
) -> ConstraintSet:
    """
    Create a ConstraintSet from a list of Polygons.

    Convenience function for programmatic constraint creation.
    """
    constraints = [
        create_constraint_from_polygon(
            polygon=p,
            constraint_type=constraint_type,
            source_format=source_format,
            layer=layer,
            constraint_id=f"constraint_{i}",
        )
        for i, p in enumerate(polygons)
    ]
    return ConstraintSet(
        constraints=constraints,
        source_format=source_format,
    )
