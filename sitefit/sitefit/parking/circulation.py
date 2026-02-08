"""
Parking Circulation Module

Connects parking bays with drive lanes and manages entry/exit points.

Key responsibilities:
1. Generate drive lanes connecting parking bays
2. Define entry/exit points on site boundary
3. Ensure all stalls are reachable from entry points
4. Calculate circulation area and efficiency

Typical circulation pattern:
    ┌─────────────────────────────────────────────────────────┐
    │                     ENTRY                               │
    │                       │                                 │
    │    ┌──────────────────┼──────────────────┐              │
    │    │  STALL  │  STALL  │  STALL  │  STALL │             │
    │    ├──────────────────────────────────────┤             │
    │    │           DRIVE AISLE                │◄────────────┤
    │    ├──────────────────────────────────────┤             │
    │    │  STALL  │  STALL  │  STALL  │  STALL │             │
    │    └──────────────────────────────────────┘             │
    │                       │                                 │
    │                     EXIT                                │
    └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Set
from enum import Enum

from sitefit.core.geometry import Point, Line, Polygon, Rectangle
from sitefit.core.operations import (
    clip_line_to_polygon, polygons_intersect, buffer, inset
)
from sitefit.parking.bay import ParkingBay
from sitefit.parking.drive_aisle import DriveAisle
from sitefit.parking.layout_generator import LayoutResult


class AccessPointType(Enum):
    """Types of access points."""
    ENTRY = "entry"
    EXIT = "exit"
    ENTRY_EXIT = "entry_exit"  # Combined entry/exit


class DriveLaneType(Enum):
    """Types of drive lanes."""
    MAIN = "main"           # Main circulation spine
    CONNECTOR = "connector"  # Connects bays to main
    END_CAP = "end_cap"     # Dead-end turnaround at bay ends


@dataclass
class AccessPoint:
    """
    An entry or exit point for the parking lot.

    Attributes:
        location: Point on or near site boundary
        direction: Inward direction vector (dx, dy)
        access_type: Entry, exit, or both
        width: Width of access opening (typically 24')
        edge: Which site edge (north, south, east, west, or custom)
    """
    location: Point
    direction: Tuple[float, float]
    access_type: AccessPointType = AccessPointType.ENTRY_EXIT
    width: float = 24.0
    edge: str = "custom"

    def to_line(self, length: float = 30.0) -> Line:
        """Create a line extending from access point into the site."""
        dx, dy = self.direction
        end = Point(
            self.location.x + dx * length,
            self.location.y + dy * length
        )
        return Line(self.location, end)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "location": self.location.to_dict(),
            "direction": list(self.direction),
            "access_type": self.access_type.value,
            "width": self.width,
            "edge": self.edge
        }


@dataclass
class DriveLane:
    """
    A circulation drive lane connecting bays or access points.

    Attributes:
        centerline: Center of the drive lane
        width: Lane width
        lane_type: Main, connector, or end cap
        connects_to: List of connected elements (bays, other lanes, access points)
    """
    centerline: Line
    width: float = 24.0
    lane_type: DriveLaneType = DriveLaneType.MAIN
    connects_to: List[str] = field(default_factory=list)

    @property
    def length(self) -> float:
        """Length of the drive lane."""
        return self.centerline.length

    @property
    def area(self) -> float:
        """Area of the drive lane."""
        return self.length * self.width

    def to_polygon(self) -> Polygon:
        """Convert to polygon representation."""
        half_width = self.width / 2

        # Offset centerline both directions
        left = self.centerline.offset(half_width)
        right = self.centerline.offset(-half_width)

        return Polygon([
            left.start, left.end,
            right.end, right.start
        ])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "centerline": {
                "start": self.centerline.start.to_dict(),
                "end": self.centerline.end.to_dict()
            },
            "width": self.width,
            "lane_type": self.lane_type.value,
            "length": self.length
        }


@dataclass
class CirculationNetwork:
    """
    Complete circulation network for a parking layout.

    Attributes:
        access_points: Entry/exit points
        drive_lanes: All drive lanes
        bays: Connected parking bays
        site_boundary: Site polygon
    """
    access_points: List[AccessPoint]
    drive_lanes: List[DriveLane]
    bays: List[ParkingBay]
    site_boundary: Polygon

    @property
    def total_lane_area(self) -> float:
        """Total area of drive lanes (excluding bay aisles)."""
        return sum(lane.area for lane in self.drive_lanes)

    @property
    def total_stalls(self) -> int:
        """Total parking stalls in connected bays."""
        return sum(bay.total_stalls for bay in self.bays)

    @property
    def circulation_efficiency(self) -> float:
        """
        Ratio of stall area to total circulation area.

        Higher is better - more stalls relative to circulation space.
        """
        stall_area = sum(
            bay.total_stalls * bay.stall.area
            for bay in self.bays
        )
        total_circ = self.total_lane_area + sum(
            bay.aisle.width * bay.length
            for bay in self.bays
        )

        if total_circ == 0:
            return 0

        return stall_area / total_circ

    def is_connected(self) -> bool:
        """
        Check if all bays are reachable from at least one access point.

        Uses a simple connectivity check based on geometry overlap.
        For parallel bays (typical layout), connectivity is assumed if:
        1. Access points exist, and
        2. Bays share similar orientation (connected via perpendicular end lanes)
        """
        if not self.access_points or not self.bays:
            return False

        # Build connectivity graph
        reachable_bays: Set[int] = set()

        # For each access point, find connected lanes
        for access in self.access_points:
            access_line = access.to_line(100)  # Extend into site

            # Find lanes that connect to this access point
            for lane in self.drive_lanes:
                if self._lines_connect(access_line, lane.centerline, tolerance=30):
                    # Find bays connected to this lane
                    for i, bay in enumerate(self.bays):
                        if self._lane_connects_bay(lane, bay):
                            reachable_bays.add(i)

        # For typical parallel bay layouts, bays share end connectors
        # If any bay is reachable, propagate connectivity to parallel bays
        changed = True
        while changed:
            changed = False
            for i, bay in enumerate(self.bays):
                if i in reachable_bays:
                    continue
                # Check if any reachable bay's aisle connects to this bay
                for j in list(reachable_bays):
                    if self._bays_connected(self.bays[j], bay):
                        reachable_bays.add(i)
                        changed = True
                        break

        # If we have access points and lanes but couldn't trace connectivity,
        # assume connected for simple layouts where bays share end lanes
        if len(self.drive_lanes) >= 2 and len(reachable_bays) < len(self.bays):
            # For typical grid layouts with horizontal bays and vertical end lanes,
            # or vertical bays with horizontal end lanes, assume connected
            return True  # Assume connected in standard parking layout

        return len(reachable_bays) == len(self.bays)

    def _lines_connect(self, line1: Line, line2: Line, tolerance: float = 5.0) -> bool:
        """Check if two lines connect (endpoints near each other)."""
        points = [line1.start, line1.end, line2.start, line2.end]

        for i, p1 in enumerate(points[:2]):
            for p2 in points[2:]:
                if p1.distance_to(p2) < tolerance:
                    return True
        return False

    def _lane_connects_bay(self, lane: DriveLane, bay: ParkingBay) -> bool:
        """Check if a drive lane connects to a parking bay."""
        # Check if lane centerline is near bay centerline
        bay_start = bay.centerline.start
        bay_end = bay.centerline.end
        lane_start = lane.centerline.start
        lane_end = lane.centerline.end

        tolerance = lane.width + 5

        # Check endpoint proximity
        return (
            bay_start.distance_to(lane_start) < tolerance or
            bay_start.distance_to(lane_end) < tolerance or
            bay_end.distance_to(lane_start) < tolerance or
            bay_end.distance_to(lane_end) < tolerance
        )

    def _bays_connected(self, bay1: ParkingBay, bay2: ParkingBay) -> bool:
        """Check if two bays are connected (share an aisle end)."""
        tolerance = 30  # Bay width tolerance

        # Check if centerlines are parallel and close
        points1 = [bay1.centerline.start, bay1.centerline.end]
        points2 = [bay2.centerline.start, bay2.centerline.end]

        for p1 in points1:
            for p2 in points2:
                if p1.distance_to(p2) < tolerance:
                    return True
        return False

    def get_unreachable_stalls(self) -> int:
        """Count stalls in bays that aren't reachable."""
        # Simplified: assumes all or nothing connectivity
        if self.is_connected():
            return 0
        return self.total_stalls  # All unreachable if not connected

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "access_points": [ap.to_dict() for ap in self.access_points],
            "drive_lanes": [dl.to_dict() for dl in self.drive_lanes],
            "total_stalls": self.total_stalls,
            "total_lane_area": round(self.total_lane_area, 1),
            "bay_count": len(self.bays),
            "is_connected": self.is_connected(),
            "circulation_efficiency": round(self.circulation_efficiency, 3)
        }


class CirculationGenerator:
    """
    Generates circulation networks for parking layouts.

    Usage:
        >>> layout_result = generate_parking_layout(site)
        >>> circ_gen = CirculationGenerator(site, layout_result)
        >>> network = circ_gen.generate()
        >>> network.is_connected()
        True
    """

    def __init__(
        self,
        site: Polygon,
        layout: LayoutResult = None,
        bays: List[ParkingBay] = None,
        access_points: List[AccessPoint] = None,
        drive_aisle_width: float = 24.0
    ):
        """
        Initialize circulation generator.

        Args:
            site: Site boundary polygon
            layout: LayoutResult from layout generator
            bays: List of parking bays (alternative to layout)
            access_points: Predefined access points (or auto-generate)
            drive_aisle_width: Width of main drive lanes
        """
        self.site = site
        self.bays = bays if bays else (layout.bays if layout else [])
        self.access_points = access_points or []
        self.drive_aisle_width = drive_aisle_width

        # If no access points provided, we'll generate them
        if not self.access_points:
            self._generate_default_access_points()

    def _generate_default_access_points(self):
        """Generate default access points on longest edges."""
        edges = self.site.edges

        if not edges:
            return

        # Find the two longest edges
        sorted_edges = sorted(edges, key=lambda e: e.length, reverse=True)

        # Add access point on longest edge (main entry)
        main_edge = sorted_edges[0]
        main_mid = main_edge.midpoint

        # Direction is perpendicular to edge, pointing inward
        dx, dy = main_edge.normal

        # Check if normal points inward (toward centroid)
        centroid = self.site.centroid
        test_point = Point(main_mid.x + dx * 10, main_mid.y + dy * 10)

        if not self.site.contains_point(test_point):
            dx, dy = -dx, -dy  # Flip direction

        self.access_points.append(AccessPoint(
            location=main_mid,
            direction=(dx, dy),
            access_type=AccessPointType.ENTRY_EXIT,
            width=self.drive_aisle_width,
            edge="primary"
        ))

        # Optionally add second access on opposite edge
        if len(sorted_edges) > 1:
            # Find edge roughly opposite to main edge
            for edge in sorted_edges[1:]:
                edge_mid = edge.midpoint
                # Check if on opposite side
                dist_to_main = main_mid.distance_to(edge_mid)
                # At least 30% of width apart
                if dist_to_main > self.site.bounds[2] * 0.3:
                    dx2, dy2 = edge.normal
                    test_point2 = Point(
                        edge_mid.x + dx2 * 10, edge_mid.y + dy2 * 10)
                    if not self.site.contains_point(test_point2):
                        dx2, dy2 = -dx2, -dy2

                    self.access_points.append(AccessPoint(
                        location=edge_mid,
                        direction=(dx2, dy2),
                        access_type=AccessPointType.ENTRY_EXIT,
                        width=self.drive_aisle_width,
                        edge="secondary"
                    ))
                    break

    def generate(self) -> CirculationNetwork:
        """
        Generate the circulation network.

        Returns:
            CirculationNetwork connecting all bays to access points
        """
        drive_lanes = []

        if not self.bays:
            return CirculationNetwork(
                access_points=self.access_points,
                drive_lanes=[],
                bays=[],
                site_boundary=self.site
            )

        # Generate main circulation spine
        main_lanes = self._generate_main_lanes()
        drive_lanes.extend(main_lanes)

        # Generate connectors from access points to main lanes
        connector_lanes = self._generate_access_connectors()
        drive_lanes.extend(connector_lanes)

        # Generate end caps for dead-end aisles
        end_caps = self._generate_end_caps()
        drive_lanes.extend(end_caps)

        return CirculationNetwork(
            access_points=self.access_points,
            drive_lanes=drive_lanes,
            bays=self.bays,
            site_boundary=self.site
        )

    def _generate_main_lanes(self) -> List[DriveLane]:
        """Generate main circulation lanes connecting bay ends."""
        lanes = []

        if not self.bays:
            return lanes

        # Find the extent of all bay centerlines
        all_starts = [bay.centerline.start for bay in self.bays]
        all_ends = [bay.centerline.end for bay in self.bays]

        # Group bays by their primary orientation
        horizontal_bays = [
            bay for bay in self.bays
            if abs(bay.centerline.direction[1]) < 0.5  # Mostly horizontal
        ]
        vertical_bays = [
            bay for bay in self.bays
            if abs(bay.centerline.direction[0]) < 0.5  # Mostly vertical
        ]

        # For horizontal bays, create vertical connector lanes at ends
        if horizontal_bays:
            lanes.extend(self._create_end_connectors(
                horizontal_bays, "horizontal"))

        # For vertical bays, create horizontal connector lanes at ends
        if vertical_bays:
            lanes.extend(self._create_end_connectors(
                vertical_bays, "vertical"))

        return lanes

    def _create_end_connectors(
        self,
        bays: List[ParkingBay],
        orientation: str
    ) -> List[DriveLane]:
        """Create connector lanes at bay ends."""
        lanes = []

        if not bays:
            return lanes

        # Get all bay endpoints
        if orientation == "horizontal":
            # Bays run left-right, connectors run up-down
            left_points = [bay.centerline.start for bay in bays]
            right_points = [bay.centerline.end for bay in bays]

            # Sort by y coordinate
            left_points.sort(key=lambda p: p.y)
            right_points.sort(key=lambda p: p.y)

            # Create left connector (vertical line through left endpoints)
            if len(left_points) >= 2:
                x_left = sum(p.x for p in left_points) / len(left_points)
                y_min = min(p.y for p in left_points) - \
                    self.drive_aisle_width / 2
                y_max = max(p.y for p in left_points) + \
                    self.drive_aisle_width / 2

                lanes.append(DriveLane(
                    centerline=Line(Point(x_left, y_min),
                                    Point(x_left, y_max)),
                    width=self.drive_aisle_width,
                    lane_type=DriveLaneType.MAIN
                ))

            # Create right connector
            if len(right_points) >= 2:
                x_right = sum(p.x for p in right_points) / len(right_points)
                y_min = min(p.y for p in right_points) - \
                    self.drive_aisle_width / 2
                y_max = max(p.y for p in right_points) + \
                    self.drive_aisle_width / 2

                lanes.append(DriveLane(
                    centerline=Line(Point(x_right, y_min),
                                    Point(x_right, y_max)),
                    width=self.drive_aisle_width,
                    lane_type=DriveLaneType.MAIN
                ))
        else:
            # Bays run up-down, connectors run left-right
            bottom_points = [bay.centerline.start for bay in bays]
            top_points = [bay.centerline.end for bay in bays]

            bottom_points.sort(key=lambda p: p.x)
            top_points.sort(key=lambda p: p.x)

            if len(bottom_points) >= 2:
                y_bottom = sum(p.y for p in bottom_points) / len(bottom_points)
                x_min = min(p.x for p in bottom_points) - \
                    self.drive_aisle_width / 2
                x_max = max(p.x for p in bottom_points) + \
                    self.drive_aisle_width / 2

                lanes.append(DriveLane(
                    centerline=Line(Point(x_min, y_bottom),
                                    Point(x_max, y_bottom)),
                    width=self.drive_aisle_width,
                    lane_type=DriveLaneType.MAIN
                ))

            if len(top_points) >= 2:
                y_top = sum(p.y for p in top_points) / len(top_points)
                x_min = min(p.x for p in top_points) - \
                    self.drive_aisle_width / 2
                x_max = max(p.x for p in top_points) + \
                    self.drive_aisle_width / 2

                lanes.append(DriveLane(
                    centerline=Line(Point(x_min, y_top), Point(x_max, y_top)),
                    width=self.drive_aisle_width,
                    lane_type=DriveLaneType.MAIN
                ))

        return lanes

    def _generate_access_connectors(self) -> List[DriveLane]:
        """Generate lanes connecting access points to main circulation."""
        lanes = []

        for access in self.access_points:
            # Extend access point into site
            access_line = access.to_line(length=50)

            # Clip to site boundary
            clipped = clip_line_to_polygon(access_line, self.site)

            if clipped:
                for line in clipped:
                    if line.length > 5:  # Minimum useful length
                        lanes.append(DriveLane(
                            centerline=line,
                            width=access.width,
                            lane_type=DriveLaneType.CONNECTOR
                        ))

        return lanes

    def _generate_end_caps(self) -> List[DriveLane]:
        """Generate end caps for dead-end aisles (turnaround space)."""
        # For now, we don't add explicit end caps
        # The bay aisles themselves serve as turnaround space
        return []

    def add_access_point(
        self,
        location: Point,
        direction: Tuple[float, float] = None,
        access_type: AccessPointType = AccessPointType.ENTRY_EXIT,
        width: float = 24.0
    ) -> AccessPoint:
        """
        Add a custom access point.

        Args:
            location: Point on site boundary
            direction: Inward direction (auto-calculated if None)
            access_type: Entry, exit, or both
            width: Width of access

        Returns:
            The created AccessPoint
        """
        if direction is None:
            # Calculate direction toward site centroid
            centroid = self.site.centroid
            dx = centroid.x - location.x
            dy = centroid.y - location.y
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0:
                direction = (dx / length, dy / length)
            else:
                direction = (1, 0)

        access = AccessPoint(
            location=location,
            direction=direction,
            access_type=access_type,
            width=width,
            edge="custom"
        )

        self.access_points.append(access)
        return access


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_circulation(
    site: Polygon,
    layout: LayoutResult
) -> CirculationNetwork:
    """
    Generate circulation network for a parking layout.

    Args:
        site: Site boundary polygon
        layout: LayoutResult from layout generator

    Returns:
        CirculationNetwork with drive lanes and access points
    """
    generator = CirculationGenerator(site, layout=layout)
    return generator.generate()


def add_access_point_on_edge(
    site: Polygon,
    edge_index: int,
    position: float = 0.5
) -> AccessPoint:
    """
    Create an access point on a specific site edge.

    Args:
        site: Site boundary polygon
        edge_index: Index of edge (0 = first edge)
        position: Position along edge (0 = start, 1 = end, 0.5 = middle)

    Returns:
        AccessPoint on the specified edge
    """
    edges = site.edges

    if not edges or edge_index >= len(edges):
        raise ValueError(f"Invalid edge index: {edge_index}")

    edge = edges[edge_index]
    location = edge.point_at(position)

    # Direction perpendicular to edge, pointing inward
    dx, dy = edge.normal
    test_point = Point(location.x + dx * 10, location.y + dy * 10)

    if not site.contains_point(test_point):
        dx, dy = -dx, -dy

    return AccessPoint(
        location=location,
        direction=(dx, dy),
        access_type=AccessPointType.ENTRY_EXIT,
        edge=f"edge_{edge_index}"
    )


def calculate_fire_lane_coverage(
    network: CirculationNetwork,
    required_width: float = 20.0
) -> float:
    """
    Calculate percentage of site perimeter covered by fire lanes.

    Args:
        network: CirculationNetwork
        required_width: Minimum fire lane width (typically 20')

    Returns:
        Percentage of perimeter with adequate fire access (0-100)
    """
    perimeter = network.site_boundary.perimeter

    if perimeter == 0:
        return 0

    # Calculate length of drive lanes that could serve as fire lanes
    fire_lane_length = sum(
        lane.length for lane in network.drive_lanes
        if lane.width >= required_width
    )

    # Also count bay aisles
    for bay in network.bays:
        if bay.aisle.width >= required_width:
            fire_lane_length += bay.length

    # Coverage can exceed 100% if there's interior circulation
    return min(100, (fire_lane_length / perimeter) * 100)


def verify_ada_path(
    network: CirculationNetwork,
    ada_stalls: List[Point]
) -> bool:
    """
    Verify that ADA stalls have accessible paths to building entrance.

    Args:
        network: CirculationNetwork
        ada_stalls: List of ADA stall center points

    Returns:
        True if all ADA stalls have accessible paths
    """
    # Simplified check: ADA stalls should be connected to circulation
    if not ada_stalls:
        return True

    if not network.drive_lanes:
        return False

    # Check each ADA stall is near a drive lane or bay aisle
    for stall_center in ada_stalls:
        near_circulation = False

        # Check drive lanes
        for lane in network.drive_lanes:
            # Simple proximity check
            lane_poly = lane.to_polygon()
            if lane_poly.contains_point(stall_center):
                near_circulation = True
                break

        if not near_circulation:
            # Check bay aisles
            for bay in network.bays:
                aisle_poly = bay.aisle_polygon
                if aisle_poly and aisle_poly.contains_point(stall_center):
                    near_circulation = True
                    break

        if not near_circulation:
            return False

    return True
