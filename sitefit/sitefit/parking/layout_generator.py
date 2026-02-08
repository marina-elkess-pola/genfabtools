"""
Parking Layout Generator

Given a site polygon, generates optimized parking layouts by:
1. Placing parallel parking bays at various angles (0°, 45°, 60°, 90°)
2. Clipping bays to site boundary
3. Avoiding exclusion zones (obstacles, ramps, columns)
4. Finding the configuration with maximum stall count

This is the core engine for automated parking design.

Key Algorithm:
1. Inset boundary by drive aisle half-width
2. Find longest edge → use as primary direction (or test all angles)
3. Generate parallel lines at bay-width spacing
4. Clip lines to boundary
5. Convert lines to bays (add stalls on both sides)
6. Remove/clip bays that overlap exclusions
7. Count stalls, repeat for other angles
8. Return best configuration
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

from sitefit.core.geometry import Point, Line, Polygon, Rectangle
from sitefit.core.operations import (
    inset, difference, subtract_all, clip_line_to_polygon,
    generate_parallel_lines, polygons_intersect, polygon_contains
)
from sitefit.parking.stall import Stall, StallType
from sitefit.parking.drive_aisle import DriveAisle, AisleType, calculate_bay_width
from sitefit.parking.bay import ParkingBay, BayType, StallPlacement, count_total_stalls


class LayoutAngle(Enum):
    """Common parking layout angles."""
    PARALLEL = 0       # Parallel to longest edge
    ANGLED_30 = 30     # 30-degree angled
    ANGLED_45 = 45     # 45-degree angled
    ANGLED_60 = 60     # 60-degree angled
    PERPENDICULAR = 90  # Perpendicular (90 degrees)


@dataclass
class Exclusion:
    """
    An area to exclude from parking (obstacle, ramp, building, etc.)

    Attributes:
        polygon: The exclusion zone boundary
        exclusion_type: Type of exclusion (for reporting)
        buffer: Additional clearance around the exclusion
    """
    polygon: Polygon
    exclusion_type: str = "obstacle"
    buffer: float = 0.0

    def buffered_polygon(self) -> Polygon:
        """Get the exclusion with buffer applied."""
        if self.buffer > 0:
            from sitefit.core.operations import buffer as buffer_polygon
            result = buffer_polygon(self.polygon, self.buffer)
            # buffer returns a list, take the first/largest polygon
            if result:
                return max(result, key=lambda p: p.area)
            return self.polygon
        return self.polygon


@dataclass
class LayoutResult:
    """
    Result of a parking layout generation.

    Attributes:
        bays: List of parking bays
        total_stalls: Total parking stalls
        angle: Layout angle in degrees
        efficiency: Stalls per 1000 SF of site area
        coverage_ratio: Ratio of parking area to site area
        site_area: Total site area
        parking_area: Area used by parking bays
        excluded_area: Area of exclusions
    """
    bays: List[ParkingBay]
    total_stalls: int
    angle: float
    efficiency: float
    coverage_ratio: float
    site_area: float
    parking_area: float
    excluded_area: float = 0.0

    @property
    def net_site_area(self) -> float:
        """Site area minus exclusions."""
        return self.site_area - self.excluded_area

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_stalls": self.total_stalls,
            "angle": self.angle,
            "efficiency": round(self.efficiency, 2),
            "coverage_ratio": round(self.coverage_ratio, 3),
            "site_area": round(self.site_area, 1),
            "parking_area": round(self.parking_area, 1),
            "excluded_area": round(self.excluded_area, 1),
            "bay_count": len(self.bays),
            "bays": [bay.to_dict() for bay in self.bays]
        }


@dataclass
class LayoutConfig:
    """
    Configuration for layout generation.

    Attributes:
        stall: Stall configuration
        aisle: Drive aisle configuration
        double_loaded: Whether to use double-loaded bays
        min_bay_length: Minimum bay length (fewer than 2 stalls is useless)
        setback: Inset from site boundary
        angles_to_try: List of angles to test
    """
    stall: Stall = field(default_factory=Stall.standard)
    aisle: DriveAisle = field(default_factory=DriveAisle.two_way)
    double_loaded: bool = True
    min_bay_length: float = 18.0  # At least 2 stalls
    setback: float = 0.0  # Distance from site boundary
    angles_to_try: List[float] = field(default_factory=lambda: [0, 45, 60, 90])

    @property
    def bay_width(self) -> float:
        """Total width of a parking bay."""
        return calculate_bay_width(
            self.stall.effective_depth,
            self.aisle.width,
            self.double_loaded
        )


class ParkingLayoutGenerator:
    """
    Generates parking layouts for a site.

    Usage:
        >>> site = Polygon([...])  # Site boundary
        >>> generator = ParkingLayoutGenerator(site)
        >>> result = generator.generate()  # Best layout
        >>> result.total_stalls
        150

        >>> # Try specific angle
        >>> result = generator.generate_at_angle(45)

        >>> # Get all angles
        >>> results = generator.generate_all_angles()
    """

    def __init__(
        self,
        site: Polygon,
        exclusions: List[Exclusion] = None,
        config: LayoutConfig = None
    ):
        """
        Initialize the layout generator.

        Args:
            site: Site boundary polygon
            exclusions: List of areas to exclude from parking
            config: Layout configuration (stall size, aisle width, etc.)
        """
        self.site = site
        self.exclusions = exclusions or []
        self.config = config or LayoutConfig()

        # Calculate site metrics
        self.site_area = site.area
        self.excluded_area = sum(e.polygon.area for e in self.exclusions)

        # Prepare the parkable area (site minus exclusions and setbacks)
        self._prepare_parkable_area()

    def _prepare_parkable_area(self):
        """Prepare the area available for parking."""
        # Start with the site
        self.parkable_area = self.site

        # Apply setback if configured
        if self.config.setback > 0:
            self.parkable_area = inset(self.parkable_area, self.config.setback)
            if self.parkable_area is None:
                self.parkable_area = self.site  # Setback too large, use full site

        # Subtract exclusions
        if self.exclusions:
            exclusion_polygons = [e.buffered_polygon()
                                  for e in self.exclusions]
            result = subtract_all(self.parkable_area, exclusion_polygons)
            if result:
                # subtract_all returns a list; use the largest polygon
                self.parkable_area = max(result, key=lambda p: p.area)

    def generate(self) -> LayoutResult:
        """
        Generate the best parking layout by testing all configured angles.

        Returns:
            LayoutResult with the highest stall count
        """
        results = self.generate_all_angles()

        if not results:
            return self._empty_result(0)

        # Return the result with most stalls
        return max(results, key=lambda r: r.total_stalls)

    def generate_all_angles(self) -> List[LayoutResult]:
        """
        Generate layouts at all configured angles.

        Returns:
            List of LayoutResult, one for each angle
        """
        results = []

        for angle in self.config.angles_to_try:
            result = self.generate_at_angle(angle)
            results.append(result)

        return results

    def generate_at_angle(self, angle: float) -> LayoutResult:
        """
        Generate a parking layout at a specific angle.

        Args:
            angle: Parking angle in degrees (0 = parallel to X axis)

        Returns:
            LayoutResult with bays placed at this angle
        """
        if self.parkable_area is None or self.parkable_area.area < 100:
            return self._empty_result(angle)

        # Get the direction vector for this angle
        angle_rad = math.radians(angle)
        direction = (math.cos(angle_rad), math.sin(angle_rad))

        # Generate bay centerlines
        centerlines = self._generate_bay_centerlines(direction)

        if not centerlines:
            return self._empty_result(angle)

        # Convert centerlines to bays
        bays = self._create_bays_from_centerlines(centerlines, angle)

        # Remove bays that overlap with exclusions
        bays = self._filter_bays_by_exclusions(bays)

        # Calculate metrics
        total_stalls = count_total_stalls(bays)
        parking_area = sum(bay.area for bay in bays) if bays else 0
        efficiency = (total_stalls / self.site_area) * \
            1000 if self.site_area > 0 else 0
        coverage = parking_area / self.site_area if self.site_area > 0 else 0

        return LayoutResult(
            bays=bays,
            total_stalls=total_stalls,
            angle=angle,
            efficiency=efficiency,
            coverage_ratio=coverage,
            site_area=self.site_area,
            parking_area=parking_area,
            excluded_area=self.excluded_area
        )

    def _generate_bay_centerlines(self, direction: Tuple[float, float]) -> List[Line]:
        """
        Generate parallel lines that will become bay centerlines.

        Args:
            direction: Unit vector for bay direction (dx, dy)

        Returns:
            List of Lines clipped to parkable area
        """
        dx, dy = direction

        # Bay spacing is the full bay width
        spacing = self.config.bay_width

        # Generate lines perpendicular to direction, spaced by bay width
        # The normal to direction gives us the offset direction
        nx, ny = -dy, dx  # Perpendicular (rotate 90°)

        # Calculate angle for generate_parallel_lines
        line_angle = math.degrees(math.atan2(dy, dx))

        # Generate parallel lines across the parkable area
        lines = generate_parallel_lines(
            polygon=self.parkable_area,
            spacing=spacing,
            angle=line_angle
        )

        # Filter out lines that are too short
        min_length = self.config.min_bay_length
        lines = [line for line in lines if line.length >= min_length]

        return lines

    def _create_bays_from_centerlines(
        self,
        centerlines: List[Line],
        angle: float
    ) -> List[ParkingBay]:
        """
        Convert centerlines to parking bays.

        Args:
            centerlines: List of bay centerlines
            angle: Parking angle for stall configuration

        Returns:
            List of ParkingBay objects
        """
        bays = []

        # Get stall and aisle for this angle
        if angle == 90:
            stall = self.config.stall
            aisle = self.config.aisle
        else:
            # For angled parking, adjust stall and aisle
            stall = Stall.standard(angle=angle)
            aisle = DriveAisle.one_way(parking_angle=angle)

        for centerline in centerlines:
            # Create bay from centerline
            bay = ParkingBay.create(
                centerline=centerline,
                stall=stall,
                aisle=aisle,
                double_loaded=self.config.double_loaded
            )

            # Clip bay to parkable area
            clipped = bay.clip_to_polygon(self.parkable_area)

            if clipped and clipped.total_stalls > 0:
                bays.append(clipped)

        return bays

    def _filter_bays_by_exclusions(self, bays: List[ParkingBay]) -> List[ParkingBay]:
        """
        Remove or clip bays that overlap with exclusions.

        Args:
            bays: List of parking bays

        Returns:
            Filtered list with overlapping bays removed
        """
        if not self.exclusions:
            return bays

        filtered = []

        for bay in bays:
            overlaps = False

            for exclusion in self.exclusions:
                excl_poly = exclusion.buffered_polygon()

                # Check if bay polygon overlaps with exclusion
                if polygons_intersect(bay.bay_polygon, excl_poly):
                    overlaps = True
                    break

            if not overlaps:
                filtered.append(bay)

        return filtered

    def _empty_result(self, angle: float) -> LayoutResult:
        """Create an empty result for when no bays fit."""
        return LayoutResult(
            bays=[],
            total_stalls=0,
            angle=angle,
            efficiency=0,
            coverage_ratio=0,
            site_area=self.site_area,
            parking_area=0,
            excluded_area=self.excluded_area
        )

    def get_best_angle(self) -> float:
        """
        Determine the best parking angle based on site shape.

        Uses the longest edge of the site to determine primary orientation.

        Returns:
            Recommended angle in degrees
        """
        longest_edge = self.site.longest_edge
        if longest_edge is None:
            return 90  # Default to perpendicular

        # Get angle of longest edge
        edge_angle = longest_edge.angle

        # Normalize to 0-180 range
        edge_angle = edge_angle % 180

        return edge_angle

    def estimate_capacity(self) -> int:
        """
        Quick estimate of parking capacity without full generation.

        Returns:
            Estimated number of stalls
        """
        if self.parkable_area is None:
            return 0

        net_area = self.parkable_area.area

        # Typical efficiency: ~3.5 stalls per 1000 SF for surface parking
        # This accounts for aisles and circulation
        return int(net_area * 3.5 / 1000)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_parking_layout(
    site: Polygon,
    exclusions: List[Polygon] = None,
    stall_type: str = "standard",
    double_loaded: bool = True,
    angles: List[float] = None
) -> LayoutResult:
    """
    Generate the best parking layout for a site.

    This is the main entry point for simple use cases.

    Args:
        site: Site boundary polygon
        exclusions: List of exclusion polygons (obstacles)
        stall_type: "standard", "compact", or "ada"
        double_loaded: Use double-loaded bays
        angles: List of angles to try (default: [0, 45, 60, 90])

    Returns:
        LayoutResult with the best configuration

    Examples:
        >>> site = Polygon([Point(0,0), Point(200,0), Point(200,150), Point(0,150)])
        >>> result = generate_parking_layout(site)
        >>> result.total_stalls
        84
    """
    # Convert exclusion polygons to Exclusion objects
    excl_objects = []
    if exclusions:
        excl_objects = [Exclusion(polygon=p) for p in exclusions]

    # Get stall configuration
    if stall_type == "compact":
        stall = Stall.compact()
    elif stall_type == "ada":
        stall = Stall.ada()
    else:
        stall = Stall.standard()

    # Create config
    config = LayoutConfig(
        stall=stall,
        double_loaded=double_loaded,
        angles_to_try=angles or [0, 45, 60, 90]
    )

    # Generate layout
    generator = ParkingLayoutGenerator(site, excl_objects, config)
    return generator.generate()


def compare_layouts(
    site: Polygon,
    exclusions: List[Polygon] = None
) -> List[LayoutResult]:
    """
    Compare parking layouts at different angles.

    Args:
        site: Site boundary polygon
        exclusions: List of exclusion polygons

    Returns:
        List of LayoutResult, sorted by stall count (descending)
    """
    excl_objects = []
    if exclusions:
        excl_objects = [Exclusion(polygon=p) for p in exclusions]

    generator = ParkingLayoutGenerator(site, excl_objects)
    results = generator.generate_all_angles()

    # Sort by stall count
    return sorted(results, key=lambda r: r.total_stalls, reverse=True)


def layout_for_rectangle(
    width: float,
    length: float,
    angle: float = 90
) -> LayoutResult:
    """
    Generate parking layout for a simple rectangle.

    Args:
        width: Site width in feet
        length: Site length in feet
        angle: Parking angle (default: 90° perpendicular)

    Returns:
        LayoutResult
    """
    site = Rectangle(Point(0, 0), width, length).to_polygon()

    config = LayoutConfig(angles_to_try=[angle])
    generator = ParkingLayoutGenerator(site, config=config)

    return generator.generate_at_angle(angle)


def stalls_per_acre(result: LayoutResult) -> float:
    """
    Calculate stalls per acre for a layout result.

    Args:
        result: LayoutResult from generation

    Returns:
        Stalls per acre (43,560 SF = 1 acre)
    """
    if result.site_area == 0:
        return 0

    acres = result.site_area / 43560
    return result.total_stalls / acres if acres > 0 else 0
