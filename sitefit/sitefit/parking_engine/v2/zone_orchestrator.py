"""
GenFabTools Parking Engine v2 — Zone-Aware Layout Orchestrator

Orchestrates layout generation across multiple zones:
1. Iterates zones in deterministic order (sorted by ID)
2. For each zone, selects appropriate engine:
   - 90°: v1 ParkingLayoutGenerator
   - 60°: v2 60° geometry module
3. Generates stalls strictly within zone polygon
4. Stitches zone results into single layout result
5. Tracks stall counts per zone

Constraints:
- v1 layout engine is NOT modified
- No residual recovery (Phase 4)
- No circulation logic
- Zones must never overlap in output

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from sitefit.core.geometry import Point, Polygon, Line
from sitefit.parking.layout_generator import (
    ParkingLayoutGenerator,
    LayoutConfig,
    LayoutResult,
    Exclusion,
)
from sitefit.parking.bay import ParkingBay
from sitefit.parking_engine.v2.zones import (
    Zone,
    ZoneType,
    AngleConfig,
    validate_zones,
    sort_zones_for_processing,
    create_default_zone,
)
from sitefit.parking_engine.v2.geometry_60 import (
    Stall60,
    Aisle60,
    StallRow60,
    DoubleLoadedRow60,
    CirculationMode,
    create_stall_60,
    create_stall_row_60,
    create_aisle_60,
    create_double_loaded_row_60,
    calculate_stalls_per_row,
    calculate_rows_in_depth,
    AISLE_WIDTH_60,
    ROW_SPACING_60,
    MODULE_DEPTH_60,
    STALL_FOOTPRINT_DEPTH_60,
)
from sitefit.parking_engine.v2.geometry_angled import (
    ParkingAngle,
    StallRowGenerator,
    AngledStall,
    AngledAisle,
    DoubleLoadedAngledRow,
    Lane,
    CirculationMode as AngledCirculationMode,
    create_double_loaded_angled_row,
    generate_lane,
    compute_lane_count,
)
from sitefit.parking_engine.v2.circulation_loop_v2 import (
    CirculationLoop,
    LoopEdge,
    Setbacks,
    CirculationDirection,
    CirculationMode,
    V2LayoutError,
    generate_circulation_loop,
    validate_circulation_loop,
    attach_stalls_to_circulation,
    AttachedStall,
    StallAttachmentResult,
    AISLE_WIDTH_ONE_WAY,
    AISLE_WIDTH_TWO_WAY,
)
from sitefit.parking_engine.v2.layout_strategy import (
    LayoutStrategy,
    StrategyLayoutGenerator,
    StrategyLayoutResult,
    LayoutStall,
    LayoutAisle,
    get_strategy_from_angle,
    generate_layout_for_angle,
    # V2LayoutError is imported from circulation_loop
)


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class ZoneLayoutResult:
    """
    Layout result for a single zone.

    Attributes:
        zone_id: ID of the zone
        zone_name: Name of the zone
        zone_type: Type of zone (GENERAL, RESERVED)
        angle_config: Angle configuration used
        stall_count: Number of stalls placed in this zone
        bays: List of parking bays (for 90° layouts)
        stalls_60: List of 60° stalls (for 60° layouts)
        aisles_60: List of 60° aisles (for 60° layouts)
        stalls_angled: List of angled stalls (for 30°/45° layouts)
        aisles_angled: List of angled aisles (for 30°/45° layouts)
        area: Zone area in square feet
    """
    zone_id: str
    zone_name: str
    zone_type: ZoneType
    angle_config: AngleConfig
    stall_count: int
    bays: List[ParkingBay] = field(default_factory=list)
    stalls_60: List[Stall60] = field(default_factory=list)
    aisles_60: List[Aisle60] = field(default_factory=list)
    stalls_angled: List[AngledStall] = field(default_factory=list)
    aisles_angled: List[AngledAisle] = field(default_factory=list)
    stalls_strategy: List[LayoutStall] = field(
        default_factory=list)  # New strategy stalls
    aisles_strategy: List[LayoutAisle] = field(
        default_factory=list)  # New strategy aisles
    strategy_valid: bool = True  # Strategy validation status
    area: float = 0.0
    # Debug geometry (spine polyline, aisle centerlines, stall normals)
    debug_geometry: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "zone_type": self.zone_type.value,
            "angle_config": self.angle_config.value,
            "stall_count": self.stall_count,
            "area": round(self.area, 2),
        }

        if self.bays:
            result["bays"] = [bay.to_dict() for bay in self.bays]

        if self.stalls_60:
            result["stalls_60"] = [s.to_dict() for s in self.stalls_60]

        if self.aisles_60:
            result["aisles_60"] = [a.to_dict() for a in self.aisles_60]

        if self.stalls_angled:
            result["stalls_angled"] = [s.to_dict() for s in self.stalls_angled]

        if self.aisles_angled:
            result["aisles_angled"] = [a.to_dict() for a in self.aisles_angled]

        if self.stalls_strategy:
            result["stalls_strategy"] = [s.to_dict()
                                         for s in self.stalls_strategy]

        if self.aisles_strategy:
            result["aisles_strategy"] = [a.to_dict()
                                         for a in self.aisles_strategy]

        result["strategy_valid"] = self.strategy_valid

        if self.debug_geometry:
            result["debug_geometry"] = self.debug_geometry

        return result


@dataclass
class OrchestratedLayoutResult:
    """
    Combined layout result from all zones.

    Attributes:
        zone_results: Results for each zone
        total_stalls: Total stalls across all zones
        total_area: Total area across all zones
        zones_processed: Number of zones processed
        validation_errors: Any validation errors encountered
    """
    zone_results: List[ZoneLayoutResult]
    total_stalls: int
    total_area: float
    zones_processed: int
    validation_errors: List[str] = field(default_factory=list)

    @property
    def stalls_by_zone(self) -> Dict[str, int]:
        """Return stall counts keyed by zone ID."""
        return {r.zone_id: r.stall_count for r in self.zone_results}

    @property
    def all_bays(self) -> List[ParkingBay]:
        """Return all bays from all zones."""
        bays = []
        for r in self.zone_results:
            bays.extend(r.bays)
        return bays

    @property
    def all_stalls_60(self) -> List[Stall60]:
        """Return all 60° stalls from all zones."""
        stalls = []
        for r in self.zone_results:
            stalls.extend(r.stalls_60)
        return stalls

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_stalls": self.total_stalls,
            "total_area": round(self.total_area, 2),
            "zones_processed": self.zones_processed,
            "zone_results": [r.to_dict() for r in self.zone_results],
            "stalls_by_zone": self.stalls_by_zone,
            "validation_errors": self.validation_errors,
        }


# =============================================================================
# ZONE ORCHESTRATOR
# =============================================================================

class ZoneOrchestrator:
    """
    Orchestrates layout generation across multiple zones.

    For each zone:
    - 90°: Calls v1 ParkingLayoutGenerator (unchanged)
    - 60°: Uses v2 60° geometry module

    Zones are processed in deterministic order (sorted by ID).
    Stalls are clipped to zone boundaries.

    Usage:
        >>> site = Polygon([...])
        >>> zones = [Zone(...), Zone(...)]
        >>> orchestrator = ZoneOrchestrator(site, zones)
        >>> result = orchestrator.generate()
        >>> result.total_stalls
        150
    """

    def __init__(
        self,
        site_boundary: Polygon,
        zones: Optional[List[Zone]] = None,
        layout_config: Optional[LayoutConfig] = None,
    ):
        """
        Initialize the zone orchestrator.

        Args:
            site_boundary: Overall site boundary polygon
            zones: List of zones (if None, creates default zone covering site)
            layout_config: Configuration for v1 layout engine
        """
        self.site_boundary = site_boundary
        self.layout_config = layout_config or LayoutConfig()

        # Use default zone if none provided (backwards compatibility)
        if zones is None or len(zones) == 0:
            self.zones = [create_default_zone(site_boundary)]
        else:
            self.zones = zones

        # Validate zones
        self.validation_errors = validate_zones(self.zones)

    def generate(self) -> OrchestratedLayoutResult:
        """
        Generate layouts for all zones and stitch results together.

        Zones are processed in deterministic order (sorted by ID).

        Returns:
            OrchestratedLayoutResult with all zone layouts combined
        """
        # Sort zones for deterministic processing
        sorted_zones = sort_zones_for_processing(self.zones)

        zone_results: List[ZoneLayoutResult] = []
        total_stalls = 0
        total_area = 0.0

        for zone in sorted_zones:
            # Use new strategy-based layout for all angles
            if zone.angle_config == AngleConfig.DEGREES_90:
                result = self._generate_strategy_layout(zone, 90)
            elif zone.angle_config == AngleConfig.DEGREES_60:
                result = self._generate_strategy_layout(zone, 60)
            elif zone.angle_config == AngleConfig.DEGREES_45:
                result = self._generate_strategy_layout(zone, 45)
            elif zone.angle_config == AngleConfig.DEGREES_30:
                # 30° not yet supported in strategy, use 45°
                result = self._generate_strategy_layout(zone, 45)
            else:
                # Default to 60°
                result = self._generate_strategy_layout(zone, 60)

            zone_results.append(result)
            total_stalls += result.stall_count
            total_area += result.area

        return OrchestratedLayoutResult(
            zone_results=zone_results,
            total_stalls=total_stalls,
            total_area=total_area,
            zones_processed=len(sorted_zones),
            validation_errors=self.validation_errors,
        )

    def _generate_90_layout(self, zone: Zone) -> ZoneLayoutResult:
        """
        Generate 90° layout for a zone using v1 engine.

        The v1 engine is called with the zone polygon as the site.
        No modifications to v1 engine are made.

        Args:
            zone: Zone to generate layout for

        Returns:
            ZoneLayoutResult with bays from v1 engine
        """
        # Create v1 generator with zone polygon as site
        # Only try 90° angle since that's what the zone specifies
        config = LayoutConfig(
            stall=self.layout_config.stall,
            aisle=self.layout_config.aisle,
            double_loaded=self.layout_config.double_loaded,
            min_bay_length=self.layout_config.min_bay_length,
            setback=self.layout_config.setback,
            angles_to_try=[90],  # Only 90° for this zone
        )

        generator = ParkingLayoutGenerator(
            site=zone.polygon,
            exclusions=[],  # Exclusions handled at site level, not zone level
            config=config,
        )

        v1_result = generator.generate()

        # Filter bays to ensure they're within zone boundary
        clipped_bays = self._clip_bays_to_zone(v1_result.bays, zone)

        # Recount stalls after clipping
        stall_count = sum(bay.total_stalls for bay in clipped_bays)

        return ZoneLayoutResult(
            zone_id=zone.id,
            zone_name=zone.name,
            zone_type=zone.zone_type,
            angle_config=zone.angle_config,
            stall_count=stall_count,
            bays=clipped_bays,
            area=zone.area,
        )

    def _generate_60_layout(self, zone: Zone) -> ZoneLayoutResult:
        """
        Generate 60° layout for a zone using DoubleLoadedRow60 modules.

        COMPOSITION RULE: 60° parking MUST be placed as double-loaded modules.
        Each module is an atomic unit containing:
        - Stalls (one direction)
        - Aisle (center)
        - Stalls (opposite direction)

        Modules are stacked at MODULE_DEPTH_60 intervals to prevent overlap.

        SETBACK ENFORCEMENT: All placement uses buildable_bounds (setback-adjusted).
        CIRCULATION: Aisle direction derived from zone.primary_axis and zone.circulation_mode.

        Args:
            zone: Zone to generate layout for

        Returns:
            ZoneLayoutResult with 60° stalls and aisles
        """
        # Check if zone has buildable area after setbacks
        if not zone.is_buildable():
            return ZoneLayoutResult(
                zone_id=zone.id,
                zone_name=zone.name,
                zone_type=zone.zone_type,
                angle_config=zone.angle_config,
                stall_count=0,
                area=zone.area,
            )

        # Get BUILDABLE bounds (setback-adjusted, not raw polygon)
        min_x, min_y, max_x, max_y = zone.buildable_bounds
        width = max_x - min_x
        height = max_y - min_y

        # Derive direction from zone's primary axis (topology-based, not hardcoded)
        primary_axis = zone.primary_axis
        if primary_axis == (1.0, 0.0):
            # Primary axis is horizontal: aisles run left-right
            direction = "horizontal"
            aisle_length = width
            available_depth = height
        else:
            # Primary axis is vertical: aisles run bottom-top
            direction = "vertical"
            aisle_length = height
            available_depth = width

        # Calculate how many complete modules fit in buildable area
        # Each module is MODULE_DEPTH_60 wide (stalls + aisle + stalls)
        num_modules = int(available_depth / MODULE_DEPTH_60)

        if num_modules == 0:
            # Buildable area too small for any modules
            return ZoneLayoutResult(
                zone_id=zone.id,
                zone_name=zone.name,
                zone_type=zone.zone_type,
                angle_config=zone.angle_config,
                stall_count=0,
                area=zone.area,
            )

        zone_shapely = zone.polygon.to_shapely()
        stalls_60: List[Stall60] = []
        aisles_60: List[Aisle60] = []

        # Get zone's circulation mode for aisle creation
        circulation = zone.circulation_mode

        # Generate modules within buildable bounds
        for module_idx in range(num_modules):
            # Calculate aisle centerline position within BUILDABLE area
            # First module starts at half MODULE_DEPTH_60 from buildable edge
            offset = (module_idx + 0.5) * MODULE_DEPTH_60

            if direction == "horizontal":
                # Horizontal aisle running left to right
                aisle_y = min_y + offset
                aisle_start = Point(min_x, aisle_y)
                aisle_end = Point(max_x, aisle_y)
            else:
                # Vertical aisle running bottom to top
                aisle_x = min_x + offset
                aisle_start = Point(aisle_x, min_y)
                aisle_end = Point(aisle_x, max_y)

            # Create complete double-loaded module with circulation mode
            module: DoubleLoadedRow60 = create_double_loaded_row_60(
                aisle_start, aisle_end, circulation=circulation
            )

            # Collect stalls that are within zone boundary (original polygon)
            for stall in module.left_row.stalls:
                if self._stall_within_zone(stall, zone_shapely):
                    stalls_60.append(stall)

            for stall in module.right_row.stalls:
                if self._stall_within_zone(stall, zone_shapely):
                    stalls_60.append(stall)

            # Add aisle if module has any stalls
            if module.left_row.count > 0 or module.right_row.count > 0:
                aisles_60.append(module.aisle)

        return ZoneLayoutResult(
            zone_id=zone.id,
            zone_name=zone.name,
            zone_type=zone.zone_type,
            angle_config=zone.angle_config,
            stall_count=len(stalls_60),
            stalls_60=stalls_60,
            aisles_60=aisles_60,
            area=zone.area,
        )

    def _generate_strategy_layout(self, zone: Zone, angle: int) -> ZoneLayoutResult:
        """
        Generate layout using CIRCULATION-FIRST approach.

        CIRCULATION-FIRST MODEL:
        1. Generate CirculationLoop (FROZEN after creation)
        2. Attach stalls to frozen circulation edges
        3. If circulation fails → raise V2LayoutError (NO V1 fallback)
        4. If any stall intersects circulation → raise V2LayoutError

        Args:
            zone: Zone to generate layout for
            angle: Parking angle (90, 60, or 45)

        Returns:
            ZoneLayoutResult with circulation geometry and attached stalls
        """
        if not zone.is_buildable():
            return ZoneLayoutResult(
                zone_id=zone.id,
                zone_name=zone.name,
                zone_type=zone.zone_type,
                angle_config=zone.angle_config,
                stall_count=0,
                area=zone.area,
                debug_geometry={"validation_errors": ["Zone not buildable"]},
            )

        # Get site boundary as Shapely polygon
        site_shapely = zone.polygon.to_shapely()

        # Get zone setbacks (or use defaults)
        if hasattr(zone, 'setbacks') and zone.setbacks is not None:
            setbacks = Setbacks(
                north=zone.setbacks.north,
                south=zone.setbacks.south,
                east=zone.setbacks.east,
                west=zone.setbacks.west,
            )
        else:
            setbacks = Setbacks.uniform(2.0)

        # Determine circulation mode based on angle
        # 45°/60°: ONE_WAY only (angled parking requires single direction)
        # 90°: TWO_WAY for double-loaded geometry
        if angle in (45, 60):
            circulation_mode = CirculationMode.ONE_WAY
            aisle_width = AISLE_WIDTH_ONE_WAY  # 15 ft
        else:  # 90
            circulation_mode = CirculationMode.TWO_WAY
            aisle_width = AISLE_WIDTH_TWO_WAY  # 24 ft

        try:
            # STEP 1: Generate circulation loop ONLY (FROZEN after creation)
            circulation_loop = generate_circulation_loop(
                site_boundary=site_shapely,
                setbacks=setbacks,
                aisle_width=aisle_width,
                circulation_direction=CirculationDirection.CLOCKWISE,
                circulation_mode=circulation_mode,
                parking_angle=angle,
            )
        except V2LayoutError as e:
            # HARD FAILURE - do NOT fallback to V1
            print(f"[CIRCULATION-FIRST] V2 error: {e}")
            return ZoneLayoutResult(
                zone_id=zone.id,
                zone_name=zone.name,
                zone_type=zone.zone_type,
                angle_config=zone.angle_config,
                stall_count=0,
                area=zone.area,
                debug_geometry={"validation_errors": [str(e)]},
                strategy_valid=False,
            )

        # Validate the circulation loop
        validation_errors = validate_circulation_loop(circulation_loop)
        if validation_errors:
            print(
                f"[CIRCULATION-FIRST] Validation errors: {validation_errors}")
            return ZoneLayoutResult(
                zone_id=zone.id,
                zone_name=zone.name,
                zone_type=zone.zone_type,
                angle_config=zone.angle_config,
                stall_count=0,
                area=zone.area,
                debug_geometry={"validation_errors": validation_errors},
                strategy_valid=False,
            )

        # STEP 2: Attach stalls to frozen circulation edges
        try:
            stall_result = attach_stalls_to_circulation(
                circulation=circulation_loop,
                buildable_polygon=site_shapely,
                angle=angle,
                circulation_mode=circulation_mode,
            )
        except V2LayoutError as e:
            # HARD FAILURE - stalls intersect circulation
            print(f"[CIRCULATION-FIRST] Stall attachment error: {e}")
            return ZoneLayoutResult(
                zone_id=zone.id,
                zone_name=zone.name,
                zone_type=zone.zone_type,
                angle_config=zone.angle_config,
                stall_count=0,
                area=zone.area,
                debug_geometry={"validation_errors": [str(e)]},
                strategy_valid=False,
            )

        # Build debug geometry from circulation loop
        loop_dict = circulation_loop.to_dict()

        # Extract loop polygon coordinates for frontend rendering
        # The loop_polygon is a ring (donut shape) with outer and inner boundaries
        loop_poly = circulation_loop.loop_polygon
        outer_coords = list(loop_poly.exterior.coords)
        inner_coords = list(
            loop_poly.interiors[0].coords) if loop_poly.interiors else []

        # Extract centerline for debug visualization
        centerline_coords = list(circulation_loop.loop_centerline.coords)

        debug_dict = {
            "circulation_loop": loop_dict,
            "loop_edges": [
                [list(e.start), list(e.end)]
                for e in circulation_loop.loop_edges
            ],
            "stall_count": stall_result.stall_count,
            # Loop polygon as outer + inner ring for rendering
            "loop_polygon_outer": [[c[0], c[1]] for c in outer_coords[:-1]],
            "loop_polygon_inner": [[c[0], c[1]] for c in inner_coords[:-1]] if inner_coords else [],
            # Centerline polyline for debug overlay
            "loop_polyline": [[c[0], c[1]] for c in centerline_coords],
            # Aisle width for reference
            "aisle_width": circulation_loop.aisle_width,
            "circulation_mode": circulation_mode.value,
        }

        # Convert loop edges to AngledAisle format for rendering compatibility
        # Determine ParkingAngle from the angle
        if angle == 45:
            parking_angle = ParkingAngle.DEGREES_45
        elif angle == 60:
            parking_angle = ParkingAngle.DEGREES_60
        else:
            parking_angle = ParkingAngle.DEGREES_90

        angled_aisles = []
        for edge in circulation_loop.loop_edges:
            # Create aisle polygon from edge (width = aisle_width)
            half_w = aisle_width / 2
            dx, dy = edge.direction
            nx, ny = edge.normal

            # Four corners of aisle polygon
            p1 = (edge.start[0] - half_w * nx, edge.start[1] - half_w * ny)
            p2 = (edge.start[0] + half_w * nx, edge.start[1] + half_w * ny)
            p3 = (edge.end[0] + half_w * nx, edge.end[1] + half_w * ny)
            p4 = (edge.end[0] - half_w * nx, edge.end[1] - half_w * ny)

            angled_aisles.append(AngledAisle(
                centerline=Line(
                    Point(edge.start[0], edge.start[1]),
                    Point(edge.end[0], edge.end[1]),
                ),
                width=aisle_width,
                angle=parking_angle,
                circulation=AngledCirculationMode.ONE_WAY_FORWARD,
                polygon=Polygon([
                    Point(p1[0], p1[1]),
                    Point(p2[0], p2[1]),
                    Point(p3[0], p3[1]),
                    Point(p4[0], p4[1]),
                ]),
            ))

        # Convert attached stalls to AngledStall format for rendering
        angled_stalls = []
        for stall in stall_result.stalls:
            coords = list(stall.polygon.exterior.coords)
            # Get the edge this stall is attached to for direction info
            edge = circulation_loop.loop_edges[stall.edge_index]

            angled_stalls.append(AngledStall(
                anchor=Point(stall.anchor[0], stall.anchor[1]),
                angle=float(stall.angle),
                direction=stall.side,
                aisle_direction=edge.direction,
                aisle_normal=edge.normal if stall.side > 0 else (
                    -edge.normal[0], -edge.normal[1]),
                polygon=Polygon([
                    Point(c[0], c[1]) for c in coords[:-1]
                ]),
            ))

        return ZoneLayoutResult(
            zone_id=zone.id,
            zone_name=zone.name,
            zone_type=zone.zone_type,
            angle_config=zone.angle_config,
            stall_count=stall_result.stall_count,
            stalls_angled=angled_stalls,
            aisles_angled=angled_aisles,
            area=zone.area,
            debug_geometry=debug_dict,
            strategy_valid=True,
        )

    def _clip_bays_to_zone(self, bays: List[ParkingBay], zone: Zone) -> List[ParkingBay]:
        """
        Filter bays to only include those within the zone.

        A bay is included if its center is within the zone polygon.
        This is a simple containment check, not geometric clipping.

        Args:
            bays: List of bays from v1 engine
            zone: Zone to check containment

        Returns:
            List of bays within the zone
        """
        zone_shapely = zone.polygon.to_shapely()
        clipped = []

        for bay in bays:
            # Check if bay center is within zone
            # This ensures bays are fully "owned" by the zone
            bay_center = bay.bay_polygon.centroid
            bay_center_shapely = bay_center.to_shapely()

            if zone_shapely.contains(bay_center_shapely):
                clipped.append(bay)

        return clipped

    def _stall_within_zone(self, stall: Stall60, zone_shapely) -> bool:
        """
        Check if a 60° stall is within the zone boundary.

        A stall is included if its polygon is fully within the zone.

        Args:
            stall: 60° stall to check
            zone_shapely: Shapely polygon of the zone

        Returns:
            True if stall is within zone
        """
        stall_shapely = stall.polygon.to_shapely()
        return zone_shapely.contains(stall_shapely)

    def _angled_stall_within_zone(self, stall: AngledStall, zone_shapely) -> bool:
        """
        Check if an angled stall (30°/45°) is within the zone boundary.

        A stall is included if its polygon is fully within the zone.

        Args:
            stall: AngledStall to check
            zone_shapely: Shapely polygon of the zone

        Returns:
            True if stall is within zone
        """
        stall_shapely = stall.polygon.to_shapely()
        return zone_shapely.contains(stall_shapely)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def orchestrate_layout(
    site_boundary: Polygon,
    zones: Optional[List[Zone]] = None,
    layout_config: Optional[LayoutConfig] = None,
) -> OrchestratedLayoutResult:
    """
    Convenience function to orchestrate layout generation.

    Args:
        site_boundary: Overall site boundary polygon
        zones: List of zones (if None, creates default zone)
        layout_config: Configuration for v1 layout engine

    Returns:
        OrchestratedLayoutResult with all zone layouts combined
    """
    orchestrator = ZoneOrchestrator(
        site_boundary=site_boundary,
        zones=zones,
        layout_config=layout_config,
    )
    return orchestrator.generate()


def get_zone_order(zones: List[Zone]) -> List[str]:
    """
    Return the processing order of zones (for debugging/testing).

    Args:
        zones: List of zones

    Returns:
        List of zone IDs in processing order
    """
    sorted_zones = sort_zones_for_processing(zones)
    return [z.id for z in sorted_zones]
