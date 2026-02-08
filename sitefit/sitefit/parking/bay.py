"""
Parking Bay Module

A parking bay is a complete parking module consisting of:
- Drive aisle (one-way or two-way)
- Stalls on one side (single-loaded) or both sides (double-loaded)

This is the fundamental repeating unit for parking layout generation.

Typical double-loaded bay at 90°:
    ┌─────────────────────────────────────────┐
    │  STALL  │  STALL  │  STALL  │  STALL   │  ← 18' deep
    ├─────────────────────────────────────────┤
    │              DRIVE AISLE                │  ← 24' wide
    ├─────────────────────────────────────────┤
    │  STALL  │  STALL  │  STALL  │  STALL   │  ← 18' deep
    └─────────────────────────────────────────┘
                      60' total width
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

from sitefit.core.geometry import Point, Line, Polygon, Rectangle
from sitefit.core.operations import clip_line_to_polygon
from sitefit.parking.stall import Stall, StallType, calculate_stalls_per_length
from sitefit.parking.drive_aisle import DriveAisle, AisleType, calculate_bay_width


class BayType(Enum):
    """Types of parking bays."""
    DOUBLE_LOADED = "double_loaded"  # Stalls on both sides of aisle
    SINGLE_LOADED = "single_loaded"  # Stalls on one side only
    ANGLED_ONE_WAY = "angled_one_way"  # One-way with angled stalls
    PARALLEL = "parallel"  # Parallel parking along street


@dataclass
class StallPlacement:
    """
    Represents a single placed stall with position and orientation.

    Attributes:
        origin: Bottom-left corner of stall (at drive aisle edge)
        polygon: The stall footprint polygon
        stall: The stall configuration
        side: Which side of aisle ('left' or 'right')
        index: Index along the bay (0, 1, 2, ...)
    """
    origin: Point
    polygon: Polygon
    stall: Stall
    side: str  # 'left' or 'right'
    index: int

    @property
    def center(self) -> Point:
        """Get center point of the stall."""
        return self.polygon.centroid

    @property
    def is_ada(self) -> bool:
        """Check if this is an ADA stall."""
        return self.stall.is_ada


@dataclass
class ParkingBay:
    """
    A complete parking bay with aisle and stalls.

    Attributes:
        centerline: The centerline of the drive aisle
        stall: Stall configuration
        aisle: Drive aisle configuration
        double_loaded: Whether stalls are on both sides
        stalls_left: Placed stalls on left side of aisle
        stalls_right: Placed stalls on right side of aisle

    Examples:
        >>> bay = ParkingBay.create_double_loaded(
        ...     centerline=Line(Point(0, 30), Point(100, 30)),
        ...     stall=Stall.standard(),
        ...     aisle=DriveAisle.two_way()
        ... )
        >>> bay.total_stalls
        22
        >>> bay.total_width
        60.0
    """
    centerline: Line
    stall: Stall
    aisle: DriveAisle
    double_loaded: bool = True
    stalls_left: List[StallPlacement] = field(default_factory=list)
    stalls_right: List[StallPlacement] = field(default_factory=list)
    _aisle_polygon: Polygon = field(default=None, repr=False)
    _bay_polygon: Polygon = field(default=None, repr=False)

    def __post_init__(self):
        """Generate stall placements if not provided."""
        if not self.stalls_left and not self.stalls_right:
            self._generate_stalls()
        self._generate_polygons()

    def _generate_stalls(self):
        """Generate stall placements along the centerline."""
        # Calculate how many stalls fit
        bay_length = self.centerline.length
        stalls_count = calculate_stalls_per_length(bay_length, self.stall)

        if stalls_count == 0:
            return

        # Get direction vectors
        dx, dy = self.centerline.direction
        nx, ny = self.centerline.normal  # Perpendicular to centerline

        # Stall width along the aisle
        stall_spacing = self.stall.effective_width

        # Start position (centered on centerline)
        total_stalls_length = stalls_count * stall_spacing
        start_offset = (bay_length - total_stalls_length) / 2

        # Distance from centerline to stall edge
        aisle_half = self.aisle.half_width
        stall_depth = self.stall.effective_depth

        # Generate stalls on both sides
        for i in range(stalls_count):
            # Position along centerline
            t = start_offset + (i + 0.5) * stall_spacing
            cx = self.centerline.start.x + dx * t
            cy = self.centerline.start.y + dy * t

            # Left side stall (positive normal direction)
            if self.double_loaded:
                left_origin = Point(
                    cx + nx * aisle_half - dx * stall_spacing / 2,
                    cy + ny * aisle_half - dy * stall_spacing / 2
                )
                left_poly = self._create_stall_polygon(
                    left_origin, stall_spacing, stall_depth,
                    dx, dy, nx, ny, side='left'
                )
                self.stalls_left.append(StallPlacement(
                    origin=left_origin,
                    polygon=left_poly,
                    stall=self.stall,
                    side='left',
                    index=i
                ))

            # Right side stall (negative normal direction)
            right_origin = Point(
                cx - nx * aisle_half - dx * stall_spacing / 2,
                cy - ny * aisle_half - dy * stall_spacing / 2
            )
            right_poly = self._create_stall_polygon(
                right_origin, stall_spacing, stall_depth,
                dx, dy, -nx, -ny, side='right'
            )
            self.stalls_right.append(StallPlacement(
                origin=right_origin,
                polygon=right_poly,
                stall=self.stall,
                side='right',
                index=i
            ))

    def _create_stall_polygon(
        self,
        origin: Point,
        width: float,
        depth: float,
        dx: float, dy: float,  # Direction along aisle
        nx: float, ny: float,  # Direction into stall
        side: str
    ) -> Polygon:
        """Create a stall polygon at the given position."""
        # Four corners of the stall
        # Starting from origin, going around counter-clockwise
        p1 = origin  # Corner at aisle
        p2 = Point(origin.x + dx * width, origin.y + dy * width)  # Along aisle
        p3 = Point(p2.x + nx * depth, p2.y + ny * depth)  # Back corner
        p4 = Point(origin.x + nx * depth, origin.y + ny * depth)  # Back corner

        return Polygon([p1, p2, p3, p4])

    def _generate_polygons(self):
        """Generate aisle and bay polygons."""
        self._aisle_polygon = self.aisle.to_polygon(self.centerline)

        # Bay polygon includes aisle + stalls
        half_aisle = self.aisle.half_width
        stall_depth = self.stall.effective_depth

        if self.double_loaded:
            total_half = half_aisle + stall_depth
        else:
            total_half = half_aisle + stall_depth  # Single loaded still extends one side

        # Create bay polygon by offsetting centerline
        left_line = self.centerline.offset(
            total_half if self.double_loaded else half_aisle)
        right_line = self.centerline.offset(-total_half)

        vertices = [
            left_line.start,
            left_line.end,
            right_line.end,
            right_line.start,
        ]
        self._bay_polygon = Polygon(vertices)

    @property
    def total_stalls(self) -> int:
        """Total number of stalls in this bay."""
        return len(self.stalls_left) + len(self.stalls_right)

    @property
    def stalls_per_side(self) -> int:
        """Number of stalls on each side."""
        return max(len(self.stalls_left), len(self.stalls_right))

    @property
    def total_width(self) -> float:
        """
        Total width of the bay perpendicular to centerline.

        For double-loaded: stall_depth + aisle_width + stall_depth
        For single-loaded: stall_depth + aisle_width
        """
        return calculate_bay_width(
            self.stall.effective_depth,
            self.aisle.width,
            self.double_loaded
        )

    @property
    def length(self) -> float:
        """Length of the bay along the centerline."""
        return self.centerline.length

    @property
    def area(self) -> float:
        """Total area of the bay (aisle + stalls)."""
        return self._bay_polygon.area if self._bay_polygon else 0

    @property
    def aisle_polygon(self) -> Polygon:
        """Get the drive aisle polygon."""
        return self._aisle_polygon

    @property
    def bay_polygon(self) -> Polygon:
        """Get the complete bay polygon (aisle + stalls)."""
        return self._bay_polygon

    @property
    def all_stalls(self) -> List[StallPlacement]:
        """Get all stalls (left + right)."""
        return self.stalls_left + self.stalls_right

    @property
    def stall_polygons(self) -> List[Polygon]:
        """Get all stall polygons."""
        return [s.polygon for s in self.all_stalls]

    @property
    def efficiency(self) -> float:
        """
        Calculate parking efficiency (stalls per 1000 SF of bay area).

        Typical efficient surface parking: 3.0-3.5 stalls per 1000 SF
        """
        if self.area == 0:
            return 0
        return (self.total_stalls / self.area) * 1000

    def stalls_in_range(self, start: float, end: float) -> List[StallPlacement]:
        """
        Get stalls within a range along the centerline.

        Args:
            start: Start position along centerline (0 to 1)
            end: End position along centerline (0 to 1)

        Returns:
            List of stalls in the specified range
        """
        result = []
        for stall in self.all_stalls:
            # Project stall center onto centerline
            t = self._project_to_centerline(stall.center)
            if start <= t <= end:
                result.append(stall)
        return result

    def _project_to_centerline(self, point: Point) -> float:
        """Project a point onto the centerline, return parameter 0-1."""
        dx = self.centerline.end.x - self.centerline.start.x
        dy = self.centerline.end.y - self.centerline.start.y
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            return 0

        t = ((point.x - self.centerline.start.x) * dx +
             (point.y - self.centerline.start.y) * dy) / length_sq
        return max(0, min(1, t))

    def clip_to_polygon(self, boundary: Polygon) -> Optional[ParkingBay]:
        """
        Clip this bay to fit within a polygon boundary.

        Returns a new ParkingBay with adjusted centerline and stalls,
        or None if the bay doesn't intersect the boundary.
        """
        # Clip centerline to boundary
        clipped_lines = clip_line_to_polygon(self.centerline, boundary)

        if not clipped_lines:
            return None

        # Use the longest clipped segment
        clipped_line = max(clipped_lines, key=lambda l: l.length)

        # Create new bay with clipped centerline
        return ParkingBay.create(
            centerline=clipped_line,
            stall=self.stall,
            aisle=self.aisle,
            double_loaded=self.double_loaded
        )

    def to_dict(self) -> dict:
        """Convert bay to dictionary for JSON serialization."""
        return {
            "centerline": {
                "start": self.centerline.start.to_dict(),
                "end": self.centerline.end.to_dict(),
            },
            "total_stalls": self.total_stalls,
            "total_width": self.total_width,
            "length": self.length,
            "double_loaded": self.double_loaded,
            "stall_type": self.stall.stall_type.value,
            "aisle_type": self.aisle.aisle_type.value,
            "stalls": [
                {
                    "side": s.side,
                    "index": s.index,
                    "center": s.center.to_dict(),
                    "polygon": s.polygon.to_dicts(),
                }
                for s in self.all_stalls
            ]
        }

    # ==========================================================================
    # Factory Methods
    # ==========================================================================

    @classmethod
    def create(
        cls,
        centerline: Line,
        stall: Stall = None,
        aisle: DriveAisle = None,
        double_loaded: bool = True
    ) -> ParkingBay:
        """
        Create a parking bay with default or custom configuration.

        Args:
            centerline: Center of the drive aisle
            stall: Stall configuration (default: standard 90°)
            aisle: Aisle configuration (default: two-way 24')
            double_loaded: Whether to put stalls on both sides
        """
        if stall is None:
            stall = Stall.standard()
        if aisle is None:
            aisle = DriveAisle.two_way()

        return cls(
            centerline=centerline,
            stall=stall,
            aisle=aisle,
            double_loaded=double_loaded
        )

    @classmethod
    def create_double_loaded(
        cls,
        centerline: Line,
        stall: Stall = None,
        aisle: DriveAisle = None
    ) -> ParkingBay:
        """Create a double-loaded parking bay (stalls on both sides)."""
        return cls.create(centerline, stall, aisle, double_loaded=True)

    @classmethod
    def create_single_loaded(
        cls,
        centerline: Line,
        stall: Stall = None,
        aisle: DriveAisle = None
    ) -> ParkingBay:
        """Create a single-loaded parking bay (stalls on one side only)."""
        return cls.create(centerline, stall, aisle, double_loaded=False)

    @classmethod
    def create_angled(
        cls,
        centerline: Line,
        angle: float = 60,
        double_loaded: bool = True
    ) -> ParkingBay:
        """
        Create an angled parking bay.

        Args:
            centerline: Center of drive aisle
            angle: Parking angle (45, 60, or 90 degrees)
            double_loaded: Stalls on both sides
        """
        stall = Stall.standard(angle=angle)
        aisle = DriveAisle.one_way(parking_angle=angle)

        return cls.create(centerline, stall, aisle, double_loaded)

    @classmethod
    def create_at_y(
        cls,
        y: float,
        x_start: float,
        x_end: float,
        stall: Stall = None,
        aisle: DriveAisle = None,
        double_loaded: bool = True
    ) -> ParkingBay:
        """
        Create a horizontal bay at a specific Y coordinate.

        Convenience method for creating bays in a grid layout.
        """
        centerline = Line(Point(x_start, y), Point(x_end, y))
        return cls.create(centerline, stall, aisle, double_loaded)

    @classmethod
    def create_at_x(
        cls,
        x: float,
        y_start: float,
        y_end: float,
        stall: Stall = None,
        aisle: DriveAisle = None,
        double_loaded: bool = True
    ) -> ParkingBay:
        """
        Create a vertical bay at a specific X coordinate.

        Convenience method for creating bays in a grid layout.
        """
        centerline = Line(Point(x, y_start), Point(x, y_end))
        return cls.create(centerline, stall, aisle, double_loaded)

    def __repr__(self) -> str:
        load_type = "double" if self.double_loaded else "single"
        return f"ParkingBay({load_type}, {self.total_stalls} stalls, {self.length:.0f}' long)"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_bay_grid(
    bounds: Rectangle,
    bay_spacing: float = None,
    stall: Stall = None,
    aisle: DriveAisle = None,
    horizontal: bool = True,
    double_loaded: bool = True
) -> List[ParkingBay]:
    """
    Create a grid of parking bays filling a rectangle.

    Args:
        bounds: Rectangle to fill with bays
        bay_spacing: Spacing between bay centerlines (default: auto)
        stall: Stall configuration
        aisle: Aisle configuration
        horizontal: If True, bays run left-right; if False, top-bottom
        double_loaded: Stalls on both sides of aisles

    Returns:
        List of parking bays
    """
    if stall is None:
        stall = Stall.standard()
    if aisle is None:
        aisle = DriveAisle.two_way()

    bay_width = calculate_bay_width(
        stall.effective_depth, aisle.width, double_loaded)

    if bay_spacing is None:
        bay_spacing = bay_width

    bays = []

    if horizontal:
        # Bays run horizontally (left to right)
        y = bounds.min_y + bay_width / 2
        while y + bay_width / 2 <= bounds.max_y:
            centerline = Line(
                Point(bounds.min_x, y),
                Point(bounds.max_x, y)
            )
            bay = ParkingBay.create(centerline, stall, aisle, double_loaded)
            bays.append(bay)
            y += bay_spacing
    else:
        # Bays run vertically (top to bottom)
        x = bounds.min_x + bay_width / 2
        while x + bay_width / 2 <= bounds.max_x:
            centerline = Line(
                Point(x, bounds.min_y),
                Point(x, bounds.max_y)
            )
            bay = ParkingBay.create(centerline, stall, aisle, double_loaded)
            bays.append(bay)
            x += bay_spacing

    return bays


def count_total_stalls(bays: List[ParkingBay]) -> int:
    """Count total stalls across multiple bays."""
    return sum(bay.total_stalls for bay in bays)


def total_bay_area(bays: List[ParkingBay]) -> float:
    """Calculate total area of multiple bays."""
    return sum(bay.area for bay in bays)


def average_efficiency(bays: List[ParkingBay]) -> float:
    """Calculate average parking efficiency across bays."""
    total_stalls = count_total_stalls(bays)
    total_area = total_bay_area(bays)

    if total_area == 0:
        return 0

    return (total_stalls / total_area) * 1000
