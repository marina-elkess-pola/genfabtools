"""
Structured Parking Stall Placement
==================================

Places parking stalls within structured parking levels by reusing
the surface parking layout engine.

PHASE 4: Stall placement in structured parking.

Strategy:
1. For each level, subtract ramp and core footprints from floor plate
2. Treat remaining geometry as surface parking site
3. Apply existing surface parking layout engine
4. Aggregate results across levels

All outputs are conceptual and advisory.
This is NOT a structural engineering or construction tool.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

from .geometry import Polygon, Point, rectangles_overlap
from .rules import ParkingRules, AisleDirection
from .layout import (
    SurfaceParkingLayout,
    ParkingBay,
    Stall,
    Aisle,
    generate_surface_layout,
)
from .structured import (
    StructuredParkingLayout,
    ParkingLevel,
    Ramp,
    VerticalCore,
)


# =============================================================================
# STRUCTURAL BAY HEURISTICS
# =============================================================================

@dataclass
class StructuralBayConfig:
    """
    Configurable heuristics for structural bay layout.

    These are rule-of-thumb values, not engineering calculations.
    """
    # Typical double-loaded bay depth
    typical_bay_depth: float = 60.0  # 18' stall + 24' aisle + 18' stall

    # Single-loaded bay depth
    single_bay_depth: float = 42.0  # 18' stall + 24' aisle

    # Minimum aisle length for efficiency
    min_aisle_length: float = 40.0

    # Structural bay grid (for future column placement)
    structural_bay_width: float = 30.0  # Typical column spacing
    structural_bay_length: float = 60.0  # Typical double-loaded depth

    # Tolerance for bay alignment (feet)
    alignment_tolerance: float = 2.0

    def to_dict(self) -> Dict:
        return {
            "typical_bay_depth_ft": self.typical_bay_depth,
            "single_bay_depth_ft": self.single_bay_depth,
            "min_aisle_length_ft": self.min_aisle_length,
            "structural_bay_width_ft": self.structural_bay_width,
            "structural_bay_length_ft": self.structural_bay_length,
            "alignment_tolerance_ft": self.alignment_tolerance,
        }


# =============================================================================
# LEVEL STALL PLACEMENT
# =============================================================================

@dataclass
class LevelLayout:
    """
    Stall layout for a single parking level.

    Wraps a SurfaceParkingLayout with level-specific metadata.
    """
    level_index: int
    surface_layout: Optional[SurfaceParkingLayout]
    excluded_areas: List[Polygon]
    net_parkable_area: Polygon

    # Placement status
    placement_successful: bool = True
    placement_notes: List[str] = field(default_factory=list)

    @property
    def stall_count(self) -> int:
        """Total stalls on this level."""
        if self.surface_layout is None:
            return 0
        return self.surface_layout.total_stalls

    @property
    def bay_count(self) -> int:
        """Number of parking bays on this level."""
        if self.surface_layout is None:
            return 0
        return len(self.surface_layout.bays)

    @property
    def bays(self) -> List[ParkingBay]:
        """Parking bays on this level."""
        if self.surface_layout is None:
            return []
        return self.surface_layout.bays

    @property
    def all_stalls(self) -> List[Stall]:
        """All stalls on this level."""
        if self.surface_layout is None:
            return []
        return self.surface_layout.all_stalls

    @property
    def net_area(self) -> float:
        """Net parkable area in square feet."""
        return self.net_parkable_area.area

    @property
    def excluded_area(self) -> float:
        """Total excluded area (ramps + cores)."""
        return sum(p.area for p in self.excluded_areas)

    @property
    def efficiency_sf_per_stall(self) -> float:
        """Square feet per stall on this level."""
        if self.stall_count == 0:
            return 0.0
        return self.net_area / self.stall_count

    def to_dict(self) -> Dict:
        return {
            "level_index": self.level_index,
            "stall_count": self.stall_count,
            "bay_count": self.bay_count,
            "net_area_sf": round(self.net_area, 1),
            "excluded_area_sf": round(self.excluded_area, 1),
            "efficiency_sf_per_stall": round(self.efficiency_sf_per_stall, 1) if self.stall_count > 0 else None,
            "placement_successful": self.placement_successful,
            "placement_notes": self.placement_notes,
            "bays": [bay.to_dict() for bay in self.bays],
        }


# =============================================================================
# EXCLUSION ZONE HANDLING
# =============================================================================

def compute_net_parkable_geometry(
    level: ParkingLevel,
    additional_exclusions: Optional[List[Polygon]] = None,
) -> Tuple[Polygon, List[Polygon]]:
    """
    Compute the net parkable geometry for a level after exclusions.

    For rectangular floor plates with rectangular exclusions, this
    returns the largest usable rectangular region.

    Args:
        level: ParkingLevel with gross footprint and reservations
        additional_exclusions: Extra exclusion zones

    Returns:
        Tuple of (net_parkable_polygon, list_of_all_exclusions)
    """
    exclusions = []
    exclusions.extend(level.ramp_reservations)
    exclusions.extend(level.core_reservations)
    if additional_exclusions:
        exclusions.extend(additional_exclusions)

    gross = level.gross_footprint
    min_x, min_y, max_x, max_y = gross.bounds

    if not exclusions:
        return gross, []

    # Strategy: Find the largest rectangular region avoiding exclusions
    # For simplicity, we try different rectangular regions

    # Get exclusion bounds
    exclusion_bounds = [e.bounds for e in exclusions]

    # Try to find usable rectangular regions
    # This is a simplified approach - we shrink the gross footprint
    # to avoid overlapping with exclusions

    # Find exclusion extents
    max_excl_left = min_x
    max_excl_right = max_x
    max_excl_bottom = min_y
    max_excl_top = max_y

    for ex_min_x, ex_min_y, ex_max_x, ex_max_y in exclusion_bounds:
        # Check if exclusion is on an edge
        if abs(ex_max_x - max_x) < 1.0:  # On right edge
            max_excl_right = min(max_excl_right, ex_min_x)
        if abs(ex_min_x - min_x) < 1.0:  # On left edge
            max_excl_left = max(max_excl_left, ex_max_x)
        if abs(ex_max_y - max_y) < 1.0:  # On top edge
            max_excl_top = min(max_excl_top, ex_min_y)
        if abs(ex_min_y - min_y) < 1.0:  # On bottom edge
            max_excl_bottom = max(max_excl_bottom, ex_max_y)

    # Check for center exclusions that we can't easily work around
    # For now, just shrink the parking area
    net_region = Polygon.from_bounds(
        max_excl_left, max_excl_bottom,
        max_excl_right, max_excl_top
    )

    # Verify net region doesn't overlap any exclusions
    for excl in exclusions:
        if rectangles_overlap(net_region, excl):
            # If there's overlap, try alternative approaches
            net_region = _find_largest_clear_rectangle(gross, exclusions)
            break

    return net_region, exclusions


def _find_largest_clear_rectangle(
    gross: Polygon,
    exclusions: List[Polygon],
) -> Polygon:
    """
    Find the largest rectangle within gross that doesn't overlap exclusions.

    Uses a simple grid-based approach for rectangular exclusions.
    """
    min_x, min_y, max_x, max_y = gross.bounds
    width = max_x - min_x
    height = max_y - min_y

    best_area = 0.0
    best_rect = gross

    # Collect all x and y coordinates from exclusions
    x_coords = sorted(set([min_x, max_x] +
                          [e.bounds[0] for e in exclusions] +
                          [e.bounds[2] for e in exclusions]))
    y_coords = sorted(set([min_y, max_y] +
                          [e.bounds[1] for e in exclusions] +
                          [e.bounds[3] for e in exclusions]))

    # Try each combination of x and y ranges
    for i, x1 in enumerate(x_coords):
        for j, x2 in enumerate(x_coords[i+1:], i+1):
            for k, y1 in enumerate(y_coords):
                for l, y2 in enumerate(y_coords[k+1:], k+1):
                    candidate = Polygon.from_bounds(x1, y1, x2, y2)

                    # Check if candidate overlaps any exclusion
                    overlaps = any(rectangles_overlap(candidate, e)
                                   for e in exclusions)

                    if not overlaps and candidate.area > best_area:
                        best_area = candidate.area
                        best_rect = candidate

    return best_rect


def validate_stalls_avoid_exclusions(
    stalls: List[Stall],
    exclusions: List[Polygon],
) -> Tuple[List[Stall], List[Stall], List[str]]:
    """
    Validate that stalls do not overlap exclusion zones.

    Returns:
        Tuple of (valid_stalls, invalid_stalls, warning_messages)
    """
    valid = []
    invalid = []
    warnings = []

    for stall in stalls:
        overlaps_exclusion = False
        for excl in exclusions:
            if rectangles_overlap(stall.geometry, excl):
                overlaps_exclusion = True
                warnings.append(
                    f"Stall {stall.id} overlaps exclusion zone"
                )
                break

        if overlaps_exclusion:
            invalid.append(stall)
        else:
            valid.append(stall)

    return valid, invalid, warnings


# =============================================================================
# LEVEL LAYOUT GENERATION
# =============================================================================

def generate_level_layout(
    level: ParkingLevel,
    rules: ParkingRules,
    aisle_direction: AisleDirection,
    setback: float = 0.0,
    orientation: str = "auto",
    level_id_prefix: str = "L",
) -> LevelLayout:
    """
    Generate parking stall layout for a single level.

    Reuses the surface parking layout engine by:
    1. Computing net parkable geometry (excluding ramps/cores)
    2. Generating surface layout for that geometry
    3. Validating stalls don't overlap exclusions
    4. Prefixing stall/bay IDs with level identifier

    Args:
        level: ParkingLevel with geometry and exclusions
        rules: Parking dimension rules
        aisle_direction: One-way or two-way aisles
        setback: Additional setback from parking area edge
        orientation: Bay orientation ("horizontal", "vertical", "auto")
        level_id_prefix: Prefix for element IDs

    Returns:
        LevelLayout with stalls placed
    """
    notes = []

    # Step 1: Compute net parkable geometry
    net_parkable, exclusions = compute_net_parkable_geometry(level)

    # Step 2: Check if net area is large enough for parking
    min_parking_area = 1000.0  # Minimum viable parking area (SF)
    if net_parkable.area < min_parking_area:
        notes.append(
            f"Net parkable area ({net_parkable.area:.0f} SF) too small for parking")
        return LevelLayout(
            level_index=level.level_index,
            surface_layout=None,
            excluded_areas=exclusions,
            net_parkable_area=net_parkable,
            placement_successful=False,
            placement_notes=notes,
        )

    # Step 3: Check dimensions
    if not net_parkable.is_rectangular:
        notes.append(
            "Net parkable area is not rectangular - using bounding box")
        min_x, min_y, max_x, max_y = net_parkable.bounds
        net_parkable = Polygon.from_bounds(min_x, min_y, max_x, max_y)

    min_dimension = min(net_parkable.width, net_parkable.height)
    module_width = rules.get_module_width(aisle_direction, double_loaded=True)

    if min_dimension < module_width:
        notes.append(
            f"Dimension {min_dimension:.0f}' too narrow for double-loaded bay ({module_width:.0f}' required)")
        # Try single-loaded
        single_module = rules.get_module_width(
            aisle_direction, double_loaded=False)
        if min_dimension < single_module:
            notes.append(
                f"Also too narrow for single-loaded bay ({single_module:.0f}' required)")
            return LevelLayout(
                level_index=level.level_index,
                surface_layout=None,
                excluded_areas=exclusions,
                net_parkable_area=net_parkable,
                placement_successful=False,
                placement_notes=notes,
            )

    # Step 4: Generate surface layout
    try:
        surface_layout = generate_surface_layout(
            site_boundary=net_parkable,
            rules=rules,
            aisle_direction=aisle_direction,
            setback=setback,
            orientation=orientation,
        )
    except ValueError as e:
        notes.append(f"Layout generation failed: {str(e)}")
        return LevelLayout(
            level_index=level.level_index,
            surface_layout=None,
            excluded_areas=exclusions,
            net_parkable_area=net_parkable,
            placement_successful=False,
            placement_notes=notes,
        )

    # Step 5: Validate stalls don't overlap exclusions
    all_stalls = surface_layout.all_stalls
    valid_stalls, invalid_stalls, warnings = validate_stalls_avoid_exclusions(
        all_stalls, exclusions
    )
    notes.extend(warnings)

    # Step 6: Remove invalid stalls from bays
    if invalid_stalls:
        invalid_ids = {s.id for s in invalid_stalls}
        notes.append(
            f"Removed {len(invalid_stalls)} stalls overlapping exclusions")

        for bay in surface_layout.bays:
            bay.north_stalls = [
                s for s in bay.north_stalls if s.id not in invalid_ids]
            bay.south_stalls = [
                s for s in bay.south_stalls if s.id not in invalid_ids]

    # Step 7: Rename elements with level prefix
    level_prefix = f"{level_id_prefix}{level.level_index}"
    _prefix_layout_ids(surface_layout, level_prefix)

    return LevelLayout(
        level_index=level.level_index,
        surface_layout=surface_layout,
        excluded_areas=exclusions,
        net_parkable_area=net_parkable,
        placement_successful=True,
        placement_notes=notes,
    )


def _prefix_layout_ids(layout: SurfaceParkingLayout, prefix: str) -> None:
    """
    Prefix all element IDs in a layout with level identifier.

    Modifies layout in place.
    """
    for bay in layout.bays:
        old_bay_id = bay.id
        new_bay_id = f"{prefix}_{bay.id}"
        bay.id = new_bay_id
        bay.aisle.id = f"{prefix}_{bay.aisle.id}"
        bay.aisle.bay_id = new_bay_id

        for stall in bay.north_stalls:
            stall.id = f"{prefix}_{stall.id}"
            stall.bay_id = new_bay_id

        for stall in bay.south_stalls:
            stall.id = f"{prefix}_{stall.id}"
            stall.bay_id = new_bay_id


# =============================================================================
# STRUCTURED LAYOUT WITH STALLS
# =============================================================================

@dataclass
class StructuredLayoutWithStalls:
    """
    Complete structured parking layout with placed stalls.

    Extends the skeleton with actual stall placements per level.
    """
    skeleton: StructuredParkingLayout
    level_layouts: List[LevelLayout]
    bay_config: StructuralBayConfig
    aisle_direction: AisleDirection

    # Aggregated results
    total_stalls: int = 0
    total_stalls_by_type: Dict[str, int] = field(default_factory=dict)
    stalls_per_level: List[int] = field(default_factory=list)

    # Metrics
    stalls_lost_to_exclusions: int = 0
    inefficiency_notes: List[str] = field(default_factory=list)

    @property
    def level_count(self) -> int:
        return len(self.level_layouts)

    @property
    def avg_stalls_per_level(self) -> float:
        if self.level_count == 0:
            return 0.0
        return self.total_stalls / self.level_count

    @property
    def total_net_area(self) -> float:
        return sum(ll.net_area for ll in self.level_layouts)

    @property
    def overall_efficiency_sf_per_stall(self) -> float:
        if self.total_stalls == 0:
            return 0.0
        return self.total_net_area / self.total_stalls

    def get_level_layout(self, level_index: int) -> Optional[LevelLayout]:
        """Get layout for a specific level."""
        for ll in self.level_layouts:
            if ll.level_index == level_index:
                return ll
        return None

    def to_dict(self) -> Dict:
        return {
            "skeleton": self.skeleton.to_dict(),
            "bay_config": self.bay_config.to_dict(),
            "aisle_direction": self.aisle_direction.value,
            "total_stalls": self.total_stalls,
            "total_stalls_by_type": self.total_stalls_by_type,
            "stalls_per_level": self.stalls_per_level,
            "avg_stalls_per_level": round(self.avg_stalls_per_level, 1),
            "total_net_area_sf": round(self.total_net_area, 1),
            "overall_efficiency_sf_per_stall": round(self.overall_efficiency_sf_per_stall, 1) if self.total_stalls > 0 else None,
            "stalls_lost_to_exclusions": self.stalls_lost_to_exclusions,
            "inefficiency_notes": self.inefficiency_notes,
            "levels": [ll.to_dict() for ll in self.level_layouts],
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=== Structured Parking Layout (with Stalls) ===",
            "",
            f"Levels: {self.level_count}",
            f"Total Stalls: {self.total_stalls}",
            f"Avg Stalls/Level: {self.avg_stalls_per_level:.1f}",
            "",
            f"Total Net Area: {self.total_net_area:,.0f} SF",
            f"Overall Efficiency: {self.overall_efficiency_sf_per_stall:.0f} SF/stall" if self.total_stalls > 0 else "No stalls placed",
            "",
            "Per-Level Breakdown:",
        ]

        for ll in self.level_layouts:
            status = "✓" if ll.placement_successful else "✗"
            lines.append(
                f"  L{ll.level_index}: {ll.stall_count} stalls, "
                f"{ll.net_area:,.0f} SF net, "
                f"{ll.efficiency_sf_per_stall:.0f} SF/stall {status}" if ll.stall_count > 0
                else f"  L{ll.level_index}: No stalls placed {status}"
            )
            for note in ll.placement_notes[:2]:  # Limit notes shown
                lines.append(f"       → {note}")

        if self.stalls_lost_to_exclusions > 0:
            lines.append("")
            lines.append(
                f"Stalls lost to exclusions: {self.stalls_lost_to_exclusions}")

        if self.inefficiency_notes:
            lines.append("")
            lines.append("Inefficiency Notes:")
            for note in self.inefficiency_notes[:5]:
                lines.append(f"  • {note}")

        return "\n".join(lines)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def generate_structured_parking_layout(
    structured_layout: StructuredParkingLayout,
    rules: Optional[ParkingRules] = None,
    aisle_direction: AisleDirection = AisleDirection.TWO_WAY,
    setback: float = 0.0,
    orientation: str = "auto",
    bay_config: Optional[StructuralBayConfig] = None,
) -> StructuredLayoutWithStalls:
    """
    Generate structured parking layout with stall placement.

    Takes an existing structured parking skeleton and places stalls
    on each level by reusing the surface parking layout engine.

    Args:
        structured_layout: Skeleton layout from generate_structured_parking_skeleton()
        rules: Parking dimension rules (uses skeleton's rules if None)
        aisle_direction: One-way or two-way aisles
        setback: Additional setback from parking area edge
        orientation: Bay orientation ("horizontal", "vertical", "auto")
        bay_config: Structural bay heuristics (uses defaults if None)

    Returns:
        StructuredLayoutWithStalls with placed stalls

    Example:
        >>> skeleton = generate_structured_parking_skeleton(footprint, level_count=4)
        >>> layout = generate_structured_parking_layout(
        ...     skeleton,
        ...     aisle_direction=AisleDirection.TWO_WAY,
        ... )
        >>> print(f"Total stalls: {layout.total_stalls}")
    """
    rules = rules or structured_layout.rules
    bay_config = bay_config or StructuralBayConfig()

    level_layouts = []
    total_stalls = 0
    stalls_by_type: Dict[str, int] = {}
    stalls_per_level = []
    stalls_lost = 0
    inefficiency_notes = []

    # Generate layout for each level
    for level in structured_layout.levels:
        level_layout = generate_level_layout(
            level=level,
            rules=rules,
            aisle_direction=aisle_direction,
            setback=setback,
            orientation=orientation,
        )
        level_layouts.append(level_layout)

        # Aggregate stalls
        level_stall_count = level_layout.stall_count
        stalls_per_level.append(level_stall_count)
        total_stalls += level_stall_count

        # Count by type
        for stall in level_layout.all_stalls:
            key = stall.stall_type.value
            stalls_by_type[key] = stalls_by_type.get(key, 0) + 1

        # Track inefficiencies
        if not level_layout.placement_successful:
            inefficiency_notes.append(
                f"Level {level.level_index}: Placement failed"
            )

        for note in level_layout.placement_notes:
            if "overlaps" in note.lower() or "removed" in note.lower():
                stalls_lost += 1

    # Check for bay alignment consistency across levels
    alignment_notes = _check_bay_alignment(level_layouts, bay_config)
    inefficiency_notes.extend(alignment_notes)

    return StructuredLayoutWithStalls(
        skeleton=structured_layout,
        level_layouts=level_layouts,
        bay_config=bay_config,
        aisle_direction=aisle_direction,
        total_stalls=total_stalls,
        total_stalls_by_type=stalls_by_type,
        stalls_per_level=stalls_per_level,
        stalls_lost_to_exclusions=stalls_lost,
        inefficiency_notes=inefficiency_notes,
    )


def _check_bay_alignment(
    level_layouts: List[LevelLayout],
    config: StructuralBayConfig,
) -> List[str]:
    """
    Check if bays are consistently aligned across levels.

    Flags misalignment but does NOT auto-correct.
    """
    notes = []

    if len(level_layouts) < 2:
        return notes

    # Get bay positions from first level with stalls
    reference_level = None
    reference_bays = []

    for ll in level_layouts:
        if ll.bay_count > 0:
            reference_level = ll.level_index
            reference_bays = [(bay.id, bay.aisle.geometry.bounds)
                              for bay in ll.bays]
            break

    if not reference_bays:
        return notes

    # Compare other levels
    for ll in level_layouts:
        if ll.level_index == reference_level or ll.bay_count == 0:
            continue

        level_bays = [(bay.id, bay.aisle.geometry.bounds) for bay in ll.bays]

        # Check if bay count differs
        if len(level_bays) != len(reference_bays):
            notes.append(
                f"Level {ll.level_index} has {len(level_bays)} bays vs "
                f"Level {reference_level} with {len(reference_bays)} bays"
            )
            continue

        # Check alignment of each bay
        for i, (ref_id, ref_bounds) in enumerate(reference_bays):
            if i >= len(level_bays):
                break

            _, level_bounds = level_bays[i]

            # Check if aisle positions match within tolerance
            x_diff = abs(ref_bounds[0] - level_bounds[0])
            y_diff = abs(ref_bounds[1] - level_bounds[1])

            if x_diff > config.alignment_tolerance or y_diff > config.alignment_tolerance:
                notes.append(
                    f"Bay misalignment: L{ll.level_index} bay {i} offset "
                    f"by ({x_diff:.1f}', {y_diff:.1f}') from L{reference_level}"
                )

    return notes


# =============================================================================
# EXTENDED METRICS
# =============================================================================

@dataclass
class StructuredLayoutMetrics:
    """
    Comprehensive metrics for structured parking with stalls.
    """
    # Structure dimensions
    level_count: int
    floor_to_floor_height: float
    total_height: float

    # Stall counts
    total_stalls: int
    stalls_per_level: List[int]
    avg_stalls_per_level: float
    stalls_by_type: Dict[str, int]

    # Areas
    footprint_area: float
    total_gross_area: float
    total_net_area: float
    total_reserved_area: float

    # Efficiency
    overall_efficiency_sf_per_stall: float
    level_efficiencies: List[float]
    avg_level_efficiency: float

    # Losses
    stalls_lost_to_ramps: int
    stalls_lost_to_cores: int
    total_stalls_lost: int

    # Comparison to estimates
    estimated_vs_actual_ratio: float

    def to_dict(self) -> Dict:
        return {
            "structure": {
                "level_count": self.level_count,
                "floor_to_floor_height_ft": self.floor_to_floor_height,
                "total_height_ft": self.total_height,
            },
            "stalls": {
                "total": self.total_stalls,
                "per_level": self.stalls_per_level,
                "avg_per_level": round(self.avg_stalls_per_level, 1),
                "by_type": self.stalls_by_type,
            },
            "areas": {
                "footprint_sf": round(self.footprint_area, 1),
                "total_gross_sf": round(self.total_gross_area, 1),
                "total_net_sf": round(self.total_net_area, 1),
                "total_reserved_sf": round(self.total_reserved_area, 1),
            },
            "efficiency": {
                "overall_sf_per_stall": round(self.overall_efficiency_sf_per_stall, 1) if self.total_stalls > 0 else None,
                "level_efficiencies_sf_per_stall": [round(e, 1) for e in self.level_efficiencies],
                "avg_level_efficiency_sf_per_stall": round(self.avg_level_efficiency, 1) if self.avg_level_efficiency > 0 else None,
            },
            "losses": {
                "stalls_lost_to_ramps": self.stalls_lost_to_ramps,
                "stalls_lost_to_cores": self.stalls_lost_to_cores,
                "total_stalls_lost": self.total_stalls_lost,
            },
            "comparison": {
                "estimated_vs_actual_ratio": round(self.estimated_vs_actual_ratio, 3),
                "note": "Ratio > 1.0 means actual exceeds estimate",
            },
        }


def compute_structured_layout_metrics(
    layout: StructuredLayoutWithStalls,
) -> StructuredLayoutMetrics:
    """
    Compute comprehensive metrics for a structured layout with stalls.

    Args:
        layout: StructuredLayoutWithStalls to analyze

    Returns:
        StructuredLayoutMetrics with computed values
    """
    skeleton = layout.skeleton

    # Structure dimensions
    level_count = skeleton.level_count
    floor_to_floor = skeleton.floor_to_floor_height
    total_height = skeleton.total_height

    # Stall counts
    total_stalls = layout.total_stalls
    stalls_per_level = layout.stalls_per_level
    avg_stalls = layout.avg_stalls_per_level
    stalls_by_type = layout.total_stalls_by_type

    # Areas
    footprint_area = skeleton.gross_footprint_area
    total_gross = skeleton.total_gross_area
    total_net = layout.total_net_area
    total_reserved = skeleton.total_ramp_area + skeleton.total_core_area

    # Efficiency
    overall_efficiency = layout.overall_efficiency_sf_per_stall
    level_efficiencies = [
        ll.efficiency_sf_per_stall for ll in layout.level_layouts
        if ll.stall_count > 0
    ]
    avg_level_efficiency = (
        sum(level_efficiencies) / len(level_efficiencies)
        if level_efficiencies else 0.0
    )

    # Estimate losses to exclusions
    # Use rule-of-thumb: typical 325 SF/stall for lost area
    ramp_area_per_level = skeleton.total_ramp_area
    core_area_per_level = skeleton.total_core_area

    stalls_lost_ramps = int(ramp_area_per_level * level_count / 325)
    stalls_lost_cores = int(core_area_per_level * level_count / 325)
    total_lost = stalls_lost_ramps + stalls_lost_cores

    # Compare to skeleton estimate
    estimated_total = int(footprint_area / 325) * level_count
    ratio = total_stalls / estimated_total if estimated_total > 0 else 0.0

    return StructuredLayoutMetrics(
        level_count=level_count,
        floor_to_floor_height=floor_to_floor,
        total_height=total_height,
        total_stalls=total_stalls,
        stalls_per_level=stalls_per_level,
        avg_stalls_per_level=avg_stalls,
        stalls_by_type=stalls_by_type,
        footprint_area=footprint_area,
        total_gross_area=total_gross,
        total_net_area=total_net,
        total_reserved_area=total_reserved * level_count,
        overall_efficiency_sf_per_stall=overall_efficiency,
        level_efficiencies=level_efficiencies,
        avg_level_efficiency=avg_level_efficiency,
        stalls_lost_to_ramps=stalls_lost_ramps,
        stalls_lost_to_cores=stalls_lost_cores,
        total_stalls_lost=total_lost,
        estimated_vs_actual_ratio=ratio,
    )
