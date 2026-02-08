#!/usr/bin/env python3
"""
Smart Parking Design System v10
===============================
Implements the Parking Design Equation:
Parking_Layout = f(Boundary, Constraints, Circulation_Optimization, Stall_Maximization)

NEW in v10: Centerline-Based Street Detection for User Drawings
- Identifies obstacles from uploaded drawings
- Computes continuous centerlines (medial axis) in free space around obstacles
- Validates street width by measuring distance from centerline to obstacles
- Only draws streets where: distance_to_obstacle >= half_street_width on both sides
                           AND centerline continuity is maintained

Steps:
1. Evaluate Boundary - Analyze shape, area, perimeter, entry/exit
2. Identify Constraints - Classify obstacles (immovable vs flexible)
3. Compute Centerlines - Find medial axis / skeleton in free space
4. Validate Street Corridors - Check width clearance on both sides
5. Build Connected Streets - Only where validation passes
6. Optimize Circulation - Pathfinding, minimize congestion
7. Maximize Stalls - Iterative placement with angled options
"""

from typing import List, Dict, Any, Tuple, Optional, Set
import math
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import heapq


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class StallAngle(Enum):
    PARALLEL = 0       # 0° - parallel to aisle
    ANGLED_45 = 45     # 45° - angled parking
    ANGLED_60 = 60     # 60° - angled parking
    PERPENDICULAR = 90  # 90° - standard perpendicular


class ConstraintType(Enum):
    IMMOVABLE = "immovable"  # Columns, walls, buildings
    FLEXIBLE = "flexible"    # Trees, planters (can potentially move)
    UTILITY = "utility"      # Manholes, utilities (small but fixed)


@dataclass
class Constraint:
    """Represents an obstacle/constraint in the parking lot."""
    minX: float
    maxX: float
    minY: float
    maxY: float
    type: ConstraintType = ConstraintType.IMMOVABLE
    buffer: float = 2.0  # Required clearance around obstacle

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.minX + self.maxX) / 2, (self.minY + self.maxY) / 2)

    @property
    def width(self) -> float:
        return self.maxX - self.minX

    @property
    def height(self) -> float:
        return self.maxY - self.minY

    def expanded(self) -> Dict[str, float]:
        """Return constraint box expanded by buffer."""
        return {
            "minX": self.minX - self.buffer,
            "maxX": self.maxX + self.buffer,
            "minY": self.minY - self.buffer,
            "maxY": self.maxY + self.buffer
        }


@dataclass
class Street:
    """Represents a drive aisle/street."""
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    is_horizontal: bool
    id: int = 0

    @property
    def length(self) -> float:
        return math.sqrt((self.x2 - self.x1)**2 + (self.y2 - self.y1)**2)

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def to_dict(self) -> Dict:
        return {
            "from": {"x": self.x1, "y": self.y1},
            "to": {"x": self.x2, "y": self.y2},
            "width": self.width,
            "type": "drive-lane",
            "orientation": "horizontal" if self.is_horizontal else "vertical"
        }

    def get_box(self) -> Dict[str, float]:
        hw = self.width / 2
        if self.is_horizontal:
            return {"minX": self.x1, "maxX": self.x2,
                    "minY": self.y1 - hw, "maxY": self.y1 + hw}
        else:
            return {"minX": self.x1 - hw, "maxX": self.x1 + hw,
                    "minY": self.y1, "maxY": self.y2}


@dataclass
class Stall:
    """Represents a parking stall."""
    id: int
    cx: float  # center x
    cy: float  # center y
    width: float
    length: float
    angle: float  # degrees
    stall_type: str = "standard"

    def get_box(self) -> Dict[str, float]:
        """Get axis-aligned bounding box."""
        if self.angle == 0 or self.angle == 180:
            hw, hl = self.width / 2, self.length / 2
        elif self.angle == 90 or self.angle == 270:
            hw, hl = self.length / 2, self.width / 2
        else:
            # For angled parking, compute actual bounding box
            rad = math.radians(self.angle)
            cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
            hw = (self.width * cos_a + self.length * sin_a) / 2
            hl = (self.width * sin_a + self.length * cos_a) / 2
        return {"minX": self.cx - hw, "maxX": self.cx + hw,
                "minY": self.cy - hl, "maxY": self.cy + hl}

    def get_polygon(self) -> List[Dict[str, float]]:
        """Get actual rotated polygon corners."""
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        corners = [
            (-self.width/2, -self.length/2),
            (self.width/2, -self.length/2),
            (self.width/2, self.length/2),
            (-self.width/2, self.length/2)
        ]
        return [{"x": self.cx + dx * cos_a - dy * sin_a,
                 "y": self.cy + dx * sin_a + dy * cos_a}
                for dx, dy in corners]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "center": {"x": self.cx, "y": self.cy},
            "width": self.width,
            "length": self.length,
            "angle": self.angle,
            "type": self.stall_type,
            "polygon": self.get_polygon()
        }


@dataclass
class BoundaryAnalysis:
    """Results of boundary evaluation."""
    minX: float
    maxX: float
    minY: float
    maxY: float
    area: float
    perimeter: float
    usable_minX: float
    usable_maxX: float
    usable_minY: float
    usable_maxY: float
    usable_area: float
    entry_points: List[Dict[str, float]] = field(default_factory=list)
    exit_points: List[Dict[str, float]] = field(default_factory=list)


# =============================================================================
# GEOMETRY UTILITIES
# =============================================================================

def boxes_overlap(a: Dict, b: Dict) -> bool:
    """Check if two axis-aligned boxes overlap."""
    return not (a["maxX"] <= b["minX"] or a["minX"] >= b["maxX"] or
                a["maxY"] <= b["minY"] or a["minY"] >= b["maxY"])


def point_in_box(x: float, y: float, box: Dict) -> bool:
    """Check if point is inside box."""
    return box["minX"] <= x <= box["maxX"] and box["minY"] <= y <= box["maxY"]


def segments_intersect(h_y: float, h_x1: float, h_x2: float,
                       v_x: float, v_y1: float, v_y2: float) -> bool:
    """Check if horizontal segment intersects vertical segment."""
    return h_x1 <= v_x <= h_x2 and v_y1 <= h_y <= v_y2


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)


def point_to_segment_distance(px: float, py: float,
                              x1: float, y1: float,
                              x2: float, y2: float) -> float:
    """Calculate minimum distance from a point to a line segment."""
    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        # Segment is a point
        return math.sqrt((px - x1)**2 + (py - y1)**2)

    # Project point onto line, clamped to segment
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return math.sqrt((px - closest_x)**2 + (py - closest_y)**2)


def point_to_box_distance(px: float, py: float, box: Dict) -> float:
    """Calculate minimum distance from a point to an axis-aligned box."""
    # Clamp point to box
    cx = max(box["minX"], min(px, box["maxX"]))
    cy = max(box["minY"], min(py, box["maxY"]))

    return math.sqrt((px - cx)**2 + (py - cy)**2)


# =============================================================================
# CENTERLINE-BASED STREET DETECTION (NEW in v10)
# =============================================================================
# This approach:
# 1. Creates a distance field from all obstacles
# 2. Finds the medial axis / skeleton (centerlines of free space)
# 3. Validates each centerline point has sufficient clearance for a street
# 4. Only places streets where both sides have >= half_street_width clearance

@dataclass
class CenterlinePoint:
    """A point on the medial axis / centerline with clearance info."""
    x: float
    y: float
    clearance: float  # Distance to nearest obstacle
    direction: Tuple[float, float] = (0, 0)  # Direction along centerline
    is_junction: bool = False  # True if this is a branching point


@dataclass
class CenterlineSegment:
    """A validated segment of centerline that can become a street."""
    points: List[CenterlinePoint]
    min_clearance: float  # Minimum clearance along this segment
    is_valid_street: bool  # True if clearance >= half_street_width on both sides
    is_continuous: bool  # True if segment is continuous (no gaps)
    orientation: str  # "horizontal", "vertical", or "diagonal"

    @property
    def start(self) -> Tuple[float, float]:
        return (self.points[0].x, self.points[0].y) if self.points else (0, 0)

    @property
    def end(self) -> Tuple[float, float]:
        return (self.points[-1].x, self.points[-1].y) if self.points else (0, 0)

    @property
    def length(self) -> float:
        """Calculate the actual span length (not path length)."""
        if len(self.points) < 2:
            return 0
        # Use direct distance from start to end for length
        # This is more accurate for axis-aligned streets
        if self.orientation == "horizontal":
            return abs(self.points[-1].x - self.points[0].x)
        elif self.orientation == "vertical":
            return abs(self.points[-1].y - self.points[0].y)
        else:
            return distance(self.start, self.end)


class DistanceField:
    """
    A 2D grid storing the distance to the nearest obstacle at each point.
    Used to compute medial axis / centerlines.
    """

    def __init__(self, boundary: BoundaryAnalysis,
                 constraints: List['Constraint'],
                 resolution: float = 2.0):
        """
        Initialize distance field.

        Args:
            boundary: The lot boundary
            constraints: List of obstacles
            resolution: Grid cell size in feet (smaller = more accurate but slower)
        """
        self.boundary = boundary
        self.resolution = resolution

        # Calculate grid dimensions
        self.width = int(
            (boundary.usable_maxX - boundary.usable_minX) / resolution) + 1
        self.height = int(
            (boundary.usable_maxY - boundary.usable_minY) / resolution) + 1
        self.origin_x = boundary.usable_minX
        self.origin_y = boundary.usable_minY

        # Initialize grid with infinity (no obstacle nearby)
        self.grid = [[float('inf')] * self.width for _ in range(self.height)]

        # Build obstacle boxes (expanded by buffer)
        self.obstacle_boxes = [c.expanded() for c in constraints]

        # Add boundary edges as "obstacles" for centerline detection
        # This ensures centerlines stay away from edges too
        self._compute_distance_field()

    def _compute_distance_field(self):
        """Compute distance to nearest obstacle for each grid cell."""
        for gy in range(self.height):
            for gx in range(self.width):
                # Convert grid coords to world coords
                wx = self.origin_x + gx * self.resolution
                wy = self.origin_y + gy * self.resolution

                min_dist = float('inf')

                # Check distance to each obstacle
                for box in self.obstacle_boxes:
                    dist = point_to_box_distance(wx, wy, box)
                    min_dist = min(min_dist, dist)

                # Check if point is INSIDE an obstacle (negative distance)
                for box in self.obstacle_boxes:
                    if point_in_box(wx, wy, box):
                        min_dist = 0
                        break

                # Also consider distance to boundary edges
                dist_left = wx - self.boundary.usable_minX
                dist_right = self.boundary.usable_maxX - wx
                dist_bottom = wy - self.boundary.usable_minY
                dist_top = self.boundary.usable_maxY - wy

                min_dist = min(min_dist, dist_left, dist_right,
                               dist_bottom, dist_top)

                self.grid[gy][gx] = max(0, min_dist)

    def get_distance(self, x: float, y: float) -> float:
        """Get distance to nearest obstacle at world coordinates."""
        gx = int((x - self.origin_x) / self.resolution)
        gy = int((y - self.origin_y) / self.resolution)

        if 0 <= gx < self.width and 0 <= gy < self.height:
            return self.grid[gy][gx]
        return 0  # Outside grid = on boundary

    def is_local_maximum(self, gx: int, gy: int) -> bool:
        """
        Check if a grid cell is a local maximum in the distance field.
        Local maxima form the medial axis / skeleton.
        """
        if gx <= 0 or gx >= self.width - 1 or gy <= 0 or gy >= self.height - 1:
            return False

        center_val = self.grid[gy][gx]
        if center_val <= 0:
            return False

        # Check 8-neighborhood - must be >= all neighbors in at least one direction
        # This creates ridge detection for the medial axis
        neighbors = [
            self.grid[gy-1][gx-1], self.grid[gy-1][gx], self.grid[gy-1][gx+1],
            self.grid[gy][gx-1],                         self.grid[gy][gx+1],
            self.grid[gy+1][gx-1], self.grid[gy+1][gx], self.grid[gy+1][gx+1]
        ]

        # Ridge detection: local max in at least one perpendicular direction
        # Horizontal ridge (vertical gradient)
        if center_val >= self.grid[gy-1][gx] and center_val >= self.grid[gy+1][gx]:
            return True
        # Vertical ridge (horizontal gradient)
        if center_val >= self.grid[gy][gx-1] and center_val >= self.grid[gy][gx+1]:
            return True
        # Diagonal ridges
        if center_val >= self.grid[gy-1][gx-1] and center_val >= self.grid[gy+1][gx+1]:
            return True
        if center_val >= self.grid[gy-1][gx+1] and center_val >= self.grid[gy+1][gx-1]:
            return True

        return False


def extract_medial_axis(dist_field: DistanceField,
                        min_clearance: float = 12.0) -> List[CenterlinePoint]:
    """
    Extract the medial axis (skeleton) from the distance field.
    Only includes points with at least min_clearance.

    Args:
        dist_field: The computed distance field
        min_clearance: Minimum distance to obstacle required (half street width)

    Returns:
        List of centerline points forming the medial axis
    """
    centerline_points = []

    for gy in range(1, dist_field.height - 1):
        for gx in range(1, dist_field.width - 1):
            # Check if this is a ridge point (local max in distance field)
            if dist_field.is_local_maximum(gx, gy):
                clearance = dist_field.grid[gy][gx]

                # Only include if clearance is sufficient for a street
                if clearance >= min_clearance:
                    wx = dist_field.origin_x + gx * dist_field.resolution
                    wy = dist_field.origin_y + gy * dist_field.resolution

                    # Compute local direction (gradient perpendicular)
                    dx = dist_field.grid[gy][gx+1] - dist_field.grid[gy][gx-1]
                    dy = dist_field.grid[gy+1][gx] - dist_field.grid[gy-1][gx]

                    # Direction along ridge is perpendicular to gradient
                    length = math.sqrt(dx*dx + dy*dy) or 1
                    direction = (-dy/length, dx/length)

                    centerline_points.append(CenterlinePoint(
                        x=wx, y=wy,
                        clearance=clearance,
                        direction=direction
                    ))

    return centerline_points


def trace_centerline_segments(points: List[CenterlinePoint],
                              half_street_width: float,
                              min_segment_length: float = 30.0,
                              max_gap: float = 6.0) -> List[CenterlineSegment]:
    """
    Connect centerline points into continuous segments.
    Validates that each segment maintains sufficient clearance.

    KEY PRINCIPLE: Only draw streets where:
    1. Distance to obstacle >= half_street_width on BOTH sides (clearance check)
    2. Continuity is maintained (no gaps in centerline points)

    When a gap is detected (no valid centerline points), the segment is split.

    Args:
        points: List of centerline points from medial axis extraction
        half_street_width: Required clearance on each side (street_width / 2)
        min_segment_length: Minimum length for a valid street segment
        max_gap: Maximum allowed gap between points to consider them connected

    Returns:
        List of validated centerline segments
    """
    if not points:
        return []

    segments = []
    resolution = max_gap
    band_size = 20.0  # 20ft bands for grouping

    # HORIZONTAL CORRIDOR DETECTION
    y_corridors = {}
    for p in points:
        # Only include points with sufficient clearance
        if p.clearance < half_street_width:
            continue
        band_y = round(p.y / band_size) * band_size
        if band_y not in y_corridors:
            y_corridors[band_y] = []
        y_corridors[band_y].append(p)

    # Process each horizontal corridor
    for band_y, band_points in y_corridors.items():
        if len(band_points) < 5:
            continue

        # Sort by X position
        band_points.sort(key=lambda p: p.x)

        # SPLIT INTO CONTINUOUS RUNS - key for avoiding obstacles
        # A gap larger than max_gap indicates an obstacle
        runs = []
        current_run = [band_points[0]]

        for i in range(1, len(band_points)):
            prev_p = band_points[i - 1]
            curr_p = band_points[i]
            gap = curr_p.x - prev_p.x

            if gap <= max_gap:
                # Continuous, add to current run
                current_run.append(curr_p)
            else:
                # Gap detected - obstacle here, start new run
                if len(current_run) >= 5:
                    runs.append(current_run)
                current_run = [curr_p]

        # Don't forget last run
        if len(current_run) >= 5:
            runs.append(current_run)

        # Create segment for each continuous run
        for run_points in runs:
            avg_y = sum(p.y for p in run_points) / len(run_points)
            x_start = run_points[0].x
            x_end = run_points[-1].x
            length = x_end - x_start

            if length < min_segment_length:
                continue

            min_clearance = min(p.clearance for p in run_points)

            segments.append(CenterlineSegment(
                points=run_points,
                min_clearance=min_clearance,
                is_valid_street=min_clearance >= half_street_width,
                is_continuous=True,
                orientation="horizontal"
            ))

    # VERTICAL CORRIDOR DETECTION
    x_corridors = {}
    for p in points:
        # Only include points with sufficient clearance
        if p.clearance < half_street_width:
            continue
        band_x = round(p.x / band_size) * band_size
        if band_x not in x_corridors:
            x_corridors[band_x] = []
        x_corridors[band_x].append(p)

    for band_x, band_points in x_corridors.items():
        if len(band_points) < 5:
            continue

        # Sort by Y position
        band_points.sort(key=lambda p: p.y)

        # SPLIT INTO CONTINUOUS RUNS
        runs = []
        current_run = [band_points[0]]

        for i in range(1, len(band_points)):
            prev_p = band_points[i - 1]
            curr_p = band_points[i]
            gap = curr_p.y - prev_p.y

            if gap <= max_gap:
                current_run.append(curr_p)
            else:
                # Gap detected - obstacle here
                if len(current_run) >= 5:
                    runs.append(current_run)
                current_run = [curr_p]

        if len(current_run) >= 5:
            runs.append(current_run)

        # Create segment for each continuous run
        for run_points in runs:
            avg_x = sum(p.x for p in run_points) / len(run_points)
            y_start = run_points[0].y
            y_end = run_points[-1].y
            length = y_end - y_start

            if length < min_segment_length:
                continue

            min_clearance = min(p.clearance for p in run_points)

            segments.append(CenterlineSegment(
                points=run_points,
                min_clearance=min_clearance,
                is_valid_street=min_clearance >= half_street_width,
                is_continuous=True,
                orientation="vertical"
            ))

    # Sort segments by clearance * length (prioritize better and longer corridors)
    segments.sort(key=lambda s: s.min_clearance * s.length, reverse=True)

    # Remove overlapping segments using STRICT SPACING RULES
    # The 60-Foot Rule: Parallel streets must be exactly 60' apart
    # Min spacing check: Delete any line < 50' from another parallel line
    h_segs = [s for s in segments if s.orientation == "horizontal"]
    v_segs = [s for s in segments if s.orientation == "vertical"]

    # Use strict spacing rules (STREET_SPACING = 60, MIN_PARALLEL_SPACING = 50)
    h_segs = _remove_overlapping_segments_single(
        h_segs, STREET_SPACING, is_horizontal=True)
    v_segs = _remove_overlapping_segments_single(
        v_segs, MIN_PARALLEL_SPACING, is_horizontal=False)

    return h_segs + v_segs


def _remove_overlapping_segments_single(segments: List[CenterlineSegment],
                                        min_spacing: float,
                                        is_horizontal: bool) -> List[CenterlineSegment]:
    """
    Remove overlapping/too-close segments of same orientation.
    Enforces strict spacing rules: no parallel lines within min_spacing.
    Snaps positions to grid and merges close lines.
    """
    if len(segments) <= 1:
        return segments

    # Sort by clearance*length score (best corridors first)
    segments.sort(key=lambda s: s.min_clearance * s.length, reverse=True)

    kept = []
    for seg in segments:
        if is_horizontal:
            avg_pos = sum(p.y for p in seg.points) / len(seg.points)
        else:
            avg_pos = sum(p.x for p in seg.points) / len(seg.points)

        # Snap position to grid
        avg_pos = snap_to_grid(avg_pos)

        # Check if too close to already kept segment (within min_spacing)
        too_close = False
        for k in kept:
            if is_horizontal:
                k_pos = snap_to_grid(
                    sum(p.y for p in k.points) / len(k.points))
            else:
                k_pos = snap_to_grid(
                    sum(p.x for p in k.points) / len(k.points))

            # Lines within MERGE_THRESHOLD (5') should be merged (handled elsewhere)
            # Lines within min_spacing but > MERGE_THRESHOLD should be deleted
            if abs(avg_pos - k_pos) < min_spacing:
                too_close = True
                break

        if not too_close:
            kept.append(seg)

    return kept


def validate_street_corridor(segment: CenterlineSegment,
                             constraints: List['Constraint'],
                             street_width: float,
                             boundary: BoundaryAnalysis) -> Dict[str, Any]:
    """
    Validate that a centerline segment can become a street.

    Conditions for a valid street:
    1. Distance to obstacle >= half_street_width on BOTH sides along entire segment
    2. Segment is continuous (no gaps)
    3. Segment is long enough for practical use

    Args:
        segment: The centerline segment to validate
        constraints: List of obstacles
        street_width: Required street width
        boundary: The lot boundary

    Returns:
        Dict with validation results and adjusted street geometry
    """
    half_width = street_width / 2

    # Check clearance at sample points along the segment
    valid_points = []
    issues = []

    for point in segment.points:
        # Check clearance on both sides perpendicular to direction
        dir_x, dir_y = point.direction

        # Perpendicular directions (left and right of centerline)
        perp_x, perp_y = -dir_y, dir_x

        # Sample points on each side
        left_x = point.x + perp_x * half_width
        left_y = point.y + perp_y * half_width
        right_x = point.x - perp_x * half_width
        right_y = point.y - perp_y * half_width

        # Check if both sides are clear
        left_clear = True
        right_clear = True

        for constraint in constraints:
            box = constraint.expanded()
            if point_in_box(left_x, left_y, box):
                left_clear = False
            if point_in_box(right_x, right_y, box):
                right_clear = False

        # Also check boundary
        if (left_x < boundary.usable_minX or left_x > boundary.usable_maxX or
                left_y < boundary.usable_minY or left_y > boundary.usable_maxY):
            left_clear = False
        if (right_x < boundary.usable_minX or right_x > boundary.usable_maxX or
                right_y < boundary.usable_minY or right_y > boundary.usable_maxY):
            right_clear = False

        if left_clear and right_clear:
            valid_points.append(point)
        else:
            issues.append({
                "point": (point.x, point.y),
                "left_blocked": not left_clear,
                "right_blocked": not right_clear
            })

    # Segment is valid if enough points are valid
    validity_ratio = len(valid_points) / \
        len(segment.points) if segment.points else 0
    is_valid = validity_ratio >= 0.8 and len(valid_points) >= 5

    return {
        "is_valid": is_valid,
        "valid_points": valid_points,
        "validity_ratio": validity_ratio,
        "issues": issues,
        "street_width": street_width,
        "orientation": segment.orientation
    }


def centerline_to_streets(validated_segments: List[Dict],
                          street_id_start: int = 1) -> List['Street']:
    """
    Convert validated centerline segments into Street objects.

    Args:
        validated_segments: List of validation results from validate_street_corridor
        street_id_start: Starting ID for street numbering

    Returns:
        List of Street objects ready for stall placement
    """
    streets = []
    street_id = street_id_start

    for validation in validated_segments:
        if not validation["is_valid"]:
            continue

        points = validation["valid_points"]
        if len(points) < 2:
            continue

        # Get start and end points - ensure proper ordering
        is_horizontal = validation["orientation"] == "horizontal"

        if is_horizontal:
            # Sort by X to ensure x1 < x2
            sorted_points = sorted(points, key=lambda p: p.x)
            start = sorted_points[0]
            end = sorted_points[-1]

            # Use average Y for a straight horizontal line, snapped to grid
            avg_y = snap_to_grid(sum(p.y for p in points) / len(points))

            # Ensure x1 < x2, snapped to grid
            x1 = snap_to_grid(min(start.x, end.x))
            x2 = snap_to_grid(max(start.x, end.x))

            street = Street(
                x1=x1,
                y1=avg_y,
                x2=x2,
                y2=avg_y,
                width=validation["street_width"],
                is_horizontal=True,
                id=street_id
            )
        elif validation["orientation"] == "vertical":
            # Sort by Y to ensure y1 < y2
            sorted_points = sorted(points, key=lambda p: p.y)
            start = sorted_points[0]
            end = sorted_points[-1]

            # Use average X for a straight vertical line, snapped to grid
            avg_x = snap_to_grid(sum(p.x for p in points) / len(points))

            # Ensure y1 < y2, snapped to grid
            y1 = snap_to_grid(min(start.y, end.y))
            y2 = snap_to_grid(max(start.y, end.y))

            street = Street(
                x1=avg_x,
                y1=y1,
                x2=avg_x,
                y2=y2,
                width=validation["street_width"],
                is_horizontal=False,
                id=street_id
            )
        else:
            # Diagonal - use actual coordinates, snapped to grid
            start = points[0]
            end = points[-1]
            dx = abs(end.x - start.x)
            dy = abs(end.y - start.y)
            is_horizontal = dx > dy
            street = Street(
                x1=snap_to_grid(start.x),
                y1=snap_to_grid(start.y),
                x2=snap_to_grid(end.x),
                y2=snap_to_grid(end.y),
                width=validation["street_width"],
                is_horizontal=is_horizontal,
                id=street_id
            )

        streets.append(street)
        street_id += 1

    return streets


def clip_streets_around_constraints(streets: List['Street'],
                                    constraints: List['Constraint'],
                                    buffer: float = 2.0) -> List['Street']:
    """
    Clip streets to avoid overlapping with constraints.

    For each street, check if it overlaps any constraint and split/trim
    the street to avoid the obstacle.

    Args:
        streets: List of Street objects
        constraints: List of Constraint objects (obstacles)
        buffer: Extra buffer distance around constraints

    Returns:
        List of Street objects that don't overlap constraints
    """
    clipped_streets = []
    street_id = 1

    for street in streets:
        street_box = street.get_box()
        hw = street.width / 2

        # Collect all constraints that this street overlaps
        overlapping = []
        for c in constraints:
            c_box = c.expanded()
            # Add buffer to constraint box
            c_minX = c_box["minX"] - buffer
            c_maxX = c_box["maxX"] + buffer
            c_minY = c_box["minY"] - buffer
            c_maxY = c_box["maxY"] + buffer

            # Check overlap
            if not (street_box["maxX"] < c_minX or street_box["minX"] > c_maxX or
                    street_box["maxY"] < c_minY or street_box["minY"] > c_maxY):
                overlapping.append({
                    "minX": c_minX, "maxX": c_maxX,
                    "minY": c_minY, "maxY": c_maxY
                })

        if not overlapping:
            # No overlap, keep street as-is
            clipped_streets.append(Street(
                x1=street.x1, y1=street.y1, x2=street.x2, y2=street.y2,
                width=street.width, is_horizontal=street.is_horizontal, id=street_id
            ))
            street_id += 1
        else:
            # Need to split/clip the street around obstacles
            if street.is_horizontal:
                # Horizontal street - split along X axis
                segments = _clip_horizontal_street(
                    street, overlapping, hw, buffer)
            else:
                # Vertical street - split along Y axis
                segments = _clip_vertical_street(
                    street, overlapping, hw, buffer)

            # Create new streets from valid segments
            for seg in segments:
                if seg["length"] >= 10.0:  # Minimum useful street length
                    clipped_streets.append(Street(
                        x1=seg["x1"], y1=seg["y1"], x2=seg["x2"], y2=seg["y2"],
                        width=street.width, is_horizontal=street.is_horizontal, id=street_id
                    ))
                    street_id += 1

    return clipped_streets


def _clip_horizontal_street(street: 'Street', obstacles: List[Dict],
                            half_width: float, buffer: float) -> List[Dict]:
    """Clip a horizontal street around obstacles, returning valid segments."""
    y = street.y1
    x_start = min(street.x1, street.x2)
    x_end = max(street.x1, street.x2)

    # Collect all X-ranges blocked by obstacles that intersect this street's Y corridor
    blocked_ranges = []
    for obs in obstacles:
        # Check if obstacle's Y range overlaps with street's Y corridor
        street_minY = y - half_width
        street_maxY = y + half_width
        if obs["maxY"] >= street_minY and obs["minY"] <= street_maxY:
            blocked_ranges.append((obs["minX"], obs["maxX"]))

    # Merge overlapping blocked ranges
    blocked_ranges.sort()
    merged = []
    for r in blocked_ranges:
        if merged and r[0] <= merged[-1][1] + buffer:
            merged[-1] = (merged[-1][0], max(merged[-1][1], r[1]))
        else:
            merged.append(r)

    # Find clear segments between blocked ranges
    segments = []
    current_x = x_start

    for block_start, block_end in merged:
        if block_start > current_x:
            # Clear segment before this block
            segments.append({
                "x1": current_x, "y1": y, "x2": block_start, "y2": y,
                "length": block_start - current_x
            })
        current_x = max(current_x, block_end)

    # Final segment after last block
    if current_x < x_end:
        segments.append({
            "x1": current_x, "y1": y, "x2": x_end, "y2": y,
            "length": x_end - current_x
        })

    return segments


def _clip_vertical_street(street: 'Street', obstacles: List[Dict],
                          half_width: float, buffer: float) -> List[Dict]:
    """Clip a vertical street around obstacles, returning valid segments."""
    x = street.x1
    y_start = min(street.y1, street.y2)
    y_end = max(street.y1, street.y2)

    # Collect all Y-ranges blocked by obstacles that intersect this street's X corridor
    blocked_ranges = []
    for obs in obstacles:
        # Check if obstacle's X range overlaps with street's X corridor
        street_minX = x - half_width
        street_maxX = x + half_width
        if obs["maxX"] >= street_minX and obs["minX"] <= street_maxX:
            blocked_ranges.append((obs["minY"], obs["maxY"]))

    # Merge overlapping blocked ranges
    blocked_ranges.sort()
    merged = []
    for r in blocked_ranges:
        if merged and r[0] <= merged[-1][1] + buffer:
            merged[-1] = (merged[-1][0], max(merged[-1][1], r[1]))
        else:
            merged.append(r)

    # Find clear segments between blocked ranges
    segments = []
    current_y = y_start

    for block_start, block_end in merged:
        if block_start > current_y:
            # Clear segment before this block
            segments.append({
                "x1": x, "y1": current_y, "x2": x, "y2": block_start,
                "length": block_start - current_y
            })
        current_y = max(current_y, block_end)

    # Final segment after last block
    if current_y < y_end:
        segments.append({
            "x1": x, "y1": current_y, "x2": x, "y2": y_end,
            "length": y_end - current_y
        })

    return segments


def _check_connectivity_internal(h_segments: List[Tuple], v_segments: List[Tuple]) -> Dict:
    """
    Internal connectivity check using Union-Find.
    Same as check_connectivity but defined earlier for use in centerline code.
    """
    all_segments = [('H', s) for s in h_segments] + [('V', s)
                                                     for s in v_segments]
    n = len(all_segments)

    if n == 0:
        return {"connected": False, "zones": 0}

    parent = list(range(n))

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    # Check all pairs for intersection
    for i in range(n):
        for j in range(i + 1, n):
            t1, s1 = all_segments[i]
            t2, s2 = all_segments[j]

            if t1 == 'H' and t2 == 'V':
                hy, hx1, hx2 = s1
                vx, vy1, vy2 = s2
                if segments_intersect(hy, hx1, hx2, vx, vy1, vy2):
                    union(i, j)
            elif t1 == 'V' and t2 == 'H':
                vx, vy1, vy2 = s1
                hy, hx1, hx2 = s2
                if segments_intersect(hy, hx1, hx2, vx, vy1, vy2):
                    union(i, j)
            elif t1 == t2 == 'H':
                y1, x1a, x1b = s1
                y2, x2a, x2b = s2
                # Connect if same Y and adjacent X
                if abs(y1 - y2) < 3 and (abs(x1b - x2a) < 3 or abs(x2b - x1a) < 3):
                    union(i, j)
            elif t1 == t2 == 'V':
                x1, y1a, y1b = s1
                x2, y2a, y2b = s2
                # Connect if same X and adjacent Y
                if abs(x1 - x2) < 3 and (abs(y1b - y2a) < 3 or abs(y2b - y1a) < 3):
                    union(i, j)

    roots = set(find(i) for i in range(n))
    num_zones = len(roots)

    return {
        "connected": num_zones <= 1,
        "zones": num_zones,
        "segments_count": n
    }


def add_street_connectors(streets: List['Street'],
                          boundary: BoundaryAnalysis,
                          constraints: List['Constraint'],
                          street_width: float,
                          verbose: bool = False) -> List['Street']:
    """
    Add connector streets to ensure all streets are connected.

    This function finds disconnected street zones and adds
    vertical/horizontal connectors to link them together.
    """
    def log(msg):
        if verbose:
            print(msg)

    if len(streets) <= 1:
        return streets

    # Extract segments for connectivity check
    h_segments = []
    v_segments = []
    for s in streets:
        if s.is_horizontal:
            h_segments.append((s.y1, s.x1, s.x2))
        else:
            v_segments.append((s.x1, s.y1, s.y2))

    # Check current connectivity - use internal function reference
    connectivity = _check_connectivity_internal(h_segments, v_segments)

    if connectivity["connected"]:
        return streets

    log(
        f"  [CONNECTOR] Streets not connected ({connectivity['zones']} zones), adding connectors...")

    # Find pairs of horizontal streets that need connecting
    new_streets = list(streets)
    street_id = max(s.id for s in streets) + 1
    half_width = street_width / 2

    # Get expanded constraint boxes
    expanded_constraints = [c.expanded() for c in constraints]

    def is_connector_clear(minX, maxX, minY, maxY):
        """Check if a rectangular connector path is clear of obstacles."""
        connector_box = {"minX": minX, "maxX": maxX,
                         "minY": minY, "maxY": maxY}
        return all(not boxes_overlap(connector_box, exp) for exp in expanded_constraints)

    def try_add_vertical_connector(x, y1, y2, desc=""):
        """Try to add a vertical connector at x from y1 to y2."""
        nonlocal street_id
        if is_connector_clear(x - half_width, x + half_width, min(y1, y2), max(y1, y2)):
            new_streets.append(Street(
                x1=x, y1=min(y1, y2), x2=x, y2=max(y1, y2),
                width=street_width, is_horizontal=False, id=street_id
            ))
            log(
                f"    Added vertical connector at X={x:.0f} from Y={min(y1,y2):.0f} to Y={max(y1,y2):.0f} {desc}")
            street_id += 1
            return True
        return False

    def try_add_horizontal_connector(y, x1, x2, desc=""):
        """Try to add a horizontal connector at y from x1 to x2."""
        nonlocal street_id
        if is_connector_clear(min(x1, x2), max(x1, x2), y - half_width, y + half_width):
            new_streets.append(Street(
                x1=min(x1, x2), y1=y, x2=max(x1, x2), y2=y,
                width=street_width, is_horizontal=True, id=street_id
            ))
            log(
                f"    Added horizontal connector at Y={y:.0f} from X={min(x1,x2):.0f} to X={max(x1,x2):.0f} {desc}")
            street_id += 1
            return True
        return False

    # Strategy 1: Connect horizontal streets with vertical connectors
    h_streets = [s for s in streets if s.is_horizontal]
    h_streets.sort(key=lambda s: s.y1)

    for i, s1 in enumerate(h_streets):
        for s2 in h_streets[i+1:]:
            # Find X overlap
            overlap_start = max(s1.x1, s2.x1)
            overlap_end = min(s1.x2, s2.x2)

            if overlap_end - overlap_start < street_width:
                continue

            y_start = min(s1.y1, s2.y1)
            y_end = max(s1.y1, s2.y1)

            # Try multiple X positions across the overlap
            num_tries = max(3, int((overlap_end - overlap_start) / 20))
            for j in range(num_tries):
                test_x = overlap_start + \
                    (overlap_end - overlap_start) * (j + 1) / (num_tries + 1)
                if try_add_vertical_connector(test_x, y_start, y_end):
                    break

    # Strategy 2: Connect vertical streets with horizontal connectors
    v_streets = [s for s in streets if not s.is_horizontal]
    v_streets.sort(key=lambda s: s.x1)

    for i, s1 in enumerate(v_streets):
        for s2 in v_streets[i+1:]:
            # Find Y overlap
            overlap_start = max(s1.y1, s2.y1)
            overlap_end = min(s1.y2, s2.y2)

            if overlap_end - overlap_start < street_width:
                continue

            x_start = min(s1.x1, s2.x1)
            x_end = max(s1.x1, s2.x1)

            # Try multiple Y positions across the overlap
            num_tries = max(3, int((overlap_end - overlap_start) / 20))
            for j in range(num_tries):
                test_y = overlap_start + \
                    (overlap_end - overlap_start) * (j + 1) / (num_tries + 1)
                if try_add_horizontal_connector(test_y, x_start, x_end):
                    break

    # Strategy 3: Connect horizontal to vertical streets at intersection points
    for h_street in h_streets:
        for v_street in v_streets:
            # Check if they already intersect
            if (h_street.x1 <= v_street.x1 <= h_street.x2 and
                    v_street.y1 <= h_street.y1 <= v_street.y2):
                continue  # Already connected

            # Check if we can extend one to connect to the other
            # Try extending vertical street to horizontal
            if h_street.x1 <= v_street.x1 <= h_street.x2:
                # V street X is within H street range
                if v_street.y2 < h_street.y1:
                    # V street is below H street, extend upward
                    try_add_vertical_connector(
                        v_street.x1, v_street.y2, h_street.y1, "(extend V up)")
                elif v_street.y1 > h_street.y1:
                    # V street is above H street, extend downward
                    try_add_vertical_connector(
                        v_street.x1, h_street.y1, v_street.y1, "(extend V down)")

            # Try extending horizontal street to vertical
            if v_street.y1 <= h_street.y1 <= v_street.y2:
                # H street Y is within V street range
                if h_street.x2 < v_street.x1:
                    # H street is left of V street, extend right
                    try_add_horizontal_connector(
                        h_street.y1, h_street.x2, v_street.x1, "(extend H right)")
                elif h_street.x1 > v_street.x1:
                    # H street is right of V street, extend left
                    try_add_horizontal_connector(
                        h_street.y1, v_street.x1, h_street.x1, "(extend H left)")

    return new_streets


def detect_streets_from_centerlines(boundary: BoundaryAnalysis,
                                    constraints: List['Constraint'],
                                    street_width: float = 24.0,
                                    min_street_length: float = 30.0,
                                    resolution: float = 2.0,
                                    verbose: bool = False) -> Tuple[List['Street'], Dict]:
    """
    Main function: Detect valid street corridors using centerline analysis.

    This is the NEW approach for user-uploaded drawings:
    1. Compute distance field from all obstacles
    2. Extract medial axis (centerlines of free space)
    3. Validate each segment has clearance >= half_street_width on both sides
    4. Convert valid segments to streets

    Args:
        boundary: The lot boundary
        constraints: List of obstacles from user drawing
        street_width: Required street width (typically 24ft for two-way)
        min_street_length: Minimum length for a valid street
        resolution: Grid resolution for analysis (smaller = more accurate)
        verbose: Print debug information

    Returns:
        Tuple of (streets, analysis_info)
    """
    def log(msg):
        if verbose:
            print(msg)

    half_width = street_width / 2

    log(
        f"  [CENTERLINE] Computing distance field (resolution={resolution}ft)...")

    # Step 1: Compute distance field
    dist_field = DistanceField(boundary, constraints, resolution)

    log(f"  [CENTERLINE] Grid size: {dist_field.width}x{dist_field.height}")

    # Step 2: Extract medial axis
    log(
        f"  [CENTERLINE] Extracting medial axis (min_clearance={half_width}ft)...")
    centerline_points = extract_medial_axis(dist_field, half_width)

    log(f"  [CENTERLINE] Found {len(centerline_points)} centerline points")

    # Step 3: Connect points into segments
    log(f"  [CENTERLINE] Tracing segments...")
    segments = trace_centerline_segments(
        centerline_points, half_width, min_street_length
    )

    log(f"  [CENTERLINE] Found {len(segments)} potential street corridors")

    # Step 4: Validate each segment
    log(f"  [CENTERLINE] Validating corridors...")
    validated = []
    for seg in segments:
        validation = validate_street_corridor(
            seg, constraints, street_width, boundary)
        validated.append(validation)
        if validation["is_valid"]:
            log(f"    [OK] {seg.orientation} segment: {seg.length:.0f}ft, "
                f"clearance={seg.min_clearance:.1f}ft")
        else:
            log(f"    [--] {seg.orientation} segment: {seg.length:.0f}ft INVALID "
                f"(ratio={validation['validity_ratio']:.2f})")

    # Step 5: Convert to streets
    streets = centerline_to_streets(validated)
    log(f"  [CENTERLINE] Generated {len(streets)} raw streets from centerlines")

    # Step 5b: Clip streets to avoid overlapping constraints
    streets = clip_streets_around_constraints(streets, constraints, buffer=2.0)
    log(
        f"  [CENTERLINE] After clipping around obstacles: {len(streets)} streets")

    # Step 5c: Apply strict spacing rules - deduplicate and enforce 60' spacing
    h_segments = [(s.y1, s.x1, s.x2) for s in streets if s.is_horizontal]
    v_segments = [(s.x1, s.y1, s.y2) for s in streets if not s.is_horizontal]
    streets, h_segments, v_segments = deduplicate_streets(
        streets, h_segments, v_segments)
    log(
        f"  [CENTERLINE] After strict spacing deduplication: {len(streets)} streets")

    # Step 6: Add connectors to ensure connectivity
    streets = add_street_connectors(
        streets, boundary, constraints, street_width, verbose)

    log(
        f"  [CENTERLINE] Total streets after adding connectors: {len(streets)}")

    analysis = {
        "centerline_points": len(centerline_points),
        "segments_found": len(segments),
        "segments_valid": sum(1 for v in validated if v["is_valid"]),
        "streets_generated": len(streets),
        "grid_resolution": resolution
    }

    return streets, analysis


# =============================================================================
# STEP 1: EVALUATE BOUNDARY
# =============================================================================

def evaluate_boundary(boundary: Dict[str, float], setback: float = 5.0) -> BoundaryAnalysis:
    """
    Analyze the input boundary.
    - Calculate total area and perimeter
    - Determine usable area after setbacks
    - Identify potential entry/exit points
    """
    minX = boundary["minX"]
    maxX = boundary["maxX"]
    minY = boundary["minY"]
    maxY = boundary["maxY"]

    width = maxX - minX
    height = maxY - minY
    area = width * height
    perimeter = 2 * (width + height)

    # Apply setbacks for usable area
    usable_minX = minX + setback
    usable_maxX = maxX - setback
    usable_minY = minY + setback
    usable_maxY = maxY - setback
    usable_area = (usable_maxX - usable_minX) * (usable_maxY - usable_minY)

    # Default entry/exit points at midpoints of edges
    # In real use, these would be specified or detected
    entry_points = [
        # Left edge center
        {"x": minX, "y": (minY + maxY) / 2, "edge": "west"},
    ]
    exit_points = [
        # Right edge center
        {"x": maxX, "y": (minY + maxY) / 2, "edge": "east"},
    ]

    return BoundaryAnalysis(
        minX=minX, maxX=maxX, minY=minY, maxY=maxY,
        area=area, perimeter=perimeter,
        usable_minX=usable_minX, usable_maxX=usable_maxX,
        usable_minY=usable_minY, usable_maxY=usable_maxY,
        usable_area=usable_area,
        entry_points=entry_points, exit_points=exit_points
    )


# =============================================================================
# STEP 2: IDENTIFY AND CLASSIFY CONSTRAINTS
# =============================================================================

def classify_constraints(raw_constraints: List[Dict]) -> List[Constraint]:
    """
    Convert raw constraint dictionaries to Constraint objects.
    Classify based on size and position.
    """
    constraints = []
    for c in raw_constraints:
        width = c["maxX"] - c["minX"]
        height = c["maxY"] - c["minY"]
        area = width * height

        # Classification heuristics
        if area < 25:  # Small obstacle (< 5x5 ft) - likely column or utility
            ctype = ConstraintType.UTILITY
            buffer = 1.5
        elif area > 400:  # Large obstacle (> 20x20 ft) - likely room/building
            ctype = ConstraintType.IMMOVABLE
            buffer = 3.0
        else:  # Medium - could be anything
            ctype = ConstraintType.IMMOVABLE
            buffer = 2.0

        constraints.append(Constraint(
            minX=c["minX"], maxX=c["maxX"],
            minY=c["minY"], maxY=c["maxY"],
            type=ctype, buffer=buffer
        ))

    return constraints


# =============================================================================
# STRICT SPACING RULES (NEW)
# =============================================================================
# These constants enforce clean, non-overlapping street layouts:

# The 60-Foot Rule: Parallel street centerlines MUST be exactly 60 feet apart
STREET_SPACING = 60.0  # No exceptions - this is stall_length*2 + aisle_width

# The 30-Foot Offset: First street centerline from boundary wall
# (18' stall + 12' half-aisle = 30')
FIRST_STREET_OFFSET = 30.0

# Merge Threshold: Lines within this distance get merged into one
MERGE_THRESHOLD = 5.0

# Minimum spacing: Any line closer than this to another parallel line is deleted
MIN_PARALLEL_SPACING = 50.0

# Grid Snap: All coordinates snap to this grid size (prevents microscopic overlaps)
GRID_SNAP = 1.0


def snap_to_grid(value: float, grid_size: float = GRID_SNAP) -> float:
    """Snap a value to the nearest grid point."""
    return round(value / grid_size) * grid_size


def snap_point(x: float, y: float, grid_size: float = GRID_SNAP) -> Tuple[float, float]:
    """Snap a point to the nearest grid intersection."""
    return (snap_to_grid(x, grid_size), snap_to_grid(y, grid_size))


def merge_close_positions(positions: List[float], threshold: float = MERGE_THRESHOLD) -> List[float]:
    """
    Merge positions that are within threshold of each other.
    Returns a list of unique positions where close ones are averaged/merged.
    """
    if not positions:
        return []

    positions = sorted(positions)
    merged = []
    current_group = [positions[0]]

    for pos in positions[1:]:
        if pos - current_group[-1] <= threshold:
            # Close enough to merge
            current_group.append(pos)
        else:
            # Far enough - finalize current group and start new one
            merged.append(sum(current_group) / len(current_group))
            current_group = [pos]

    # Don't forget the last group
    if current_group:
        merged.append(sum(current_group) / len(current_group))

    return [snap_to_grid(p) for p in merged]


def filter_parallel_lines(positions: List[float], min_spacing: float = MIN_PARALLEL_SPACING) -> List[float]:
    """
    Remove lines that are too close to other parallel lines.
    Keeps the first line and removes any subsequent line within min_spacing.
    """
    if not positions:
        return []

    positions = sorted(positions)
    filtered = [positions[0]]

    for pos in positions[1:]:
        # Check if this position is far enough from all kept positions
        if all(abs(pos - kept) >= min_spacing for kept in filtered):
            filtered.append(pos)

    return filtered


def calculate_strict_street_positions(
    boundary: BoundaryAnalysis,
    constraints: List[Constraint],
    stall_length: float = 18.0,
    aisle_width: float = 24.0,
    direction: str = "horizontal"
) -> List[float]:
    """
    Calculate street centerline positions using strict spacing rules.

    Rules enforced:
    1. First street at exactly FIRST_STREET_OFFSET (30') from boundary
    2. Subsequent streets at exactly STREET_SPACING (60') intervals
    3. Any positions within MERGE_THRESHOLD (5') are merged
    4. Lines closer than MIN_PARALLEL_SPACING (50') to another are deleted
    5. All coordinates snapped to GRID_SNAP (1') grid
    """
    half_aisle = aisle_width / 2

    if direction == "horizontal":
        # Calculate Y positions for horizontal streets
        min_pos = boundary.usable_minY
        max_pos = boundary.usable_maxY
    else:
        # Calculate X positions for vertical streets
        min_pos = boundary.usable_minX
        max_pos = boundary.usable_maxX

    # First street at exactly 30' from the starting edge
    first_street = snap_to_grid(min_pos + FIRST_STREET_OFFSET)

    # Generate positions at exactly 60' intervals
    positions = []
    current_pos = first_street

    while current_pos <= max_pos - FIRST_STREET_OFFSET:
        positions.append(current_pos)
        current_pos += STREET_SPACING

    # Snap all positions to grid
    positions = [snap_to_grid(p) for p in positions]

    # Merge any positions that are within 5' of each other
    positions = merge_close_positions(positions, MERGE_THRESHOLD)

    # Filter out positions that are too close (< 50') to another
    positions = filter_parallel_lines(positions, MIN_PARALLEL_SPACING)

    return positions


# =============================================================================
# STEP 3: FIND CLEAR ZONES (Work Around Constraints)
# =============================================================================

def find_clear_bands(boundary: BoundaryAnalysis,
                     constraints: List[Constraint],
                     band_height: float,
                     direction: str = "horizontal") -> List[Tuple[float, float, float, float]]:
    """
    Find clear horizontal or vertical bands for streets.
    Returns list of (position, start, end, clearance).
    """
    clear_bands = []

    # Get expanded constraint boxes
    expanded = [c.expanded() for c in constraints]

    if direction == "horizontal":
        # Scan Y positions
        y = boundary.usable_minY + band_height / 2
        step = 5.0  # Scan resolution

        while y <= boundary.usable_maxY - band_height / 2:
            # Check if this Y position is clear
            is_clear = True
            for exp in expanded:
                if exp["minY"] <= y <= exp["maxY"]:
                    is_clear = False
                    break

            if is_clear:
                # Find clear X extent at this Y
                x_start = boundary.usable_minX
                x_end = boundary.usable_maxX

                for exp in expanded:
                    if exp["minY"] - band_height/2 <= y <= exp["maxY"] + band_height/2:
                        # This constraint affects this band
                        # For now, we'll segment the band
                        pass

                # Calculate clearance (distance to nearest constraint)
                min_clearance = float('inf')
                for exp in expanded:
                    dist_above = exp["minY"] - y
                    dist_below = y - exp["maxY"]
                    if dist_above > 0:
                        min_clearance = min(min_clearance, dist_above)
                    if dist_below > 0:
                        min_clearance = min(min_clearance, dist_below)

                if min_clearance == float('inf'):
                    min_clearance = min(y - boundary.usable_minY,
                                        boundary.usable_maxY - y)

                clear_bands.append((y, x_start, x_end, min_clearance))

            y += step

    return clear_bands


def scan_clear_segments(pos: float, is_horizontal: bool,
                        boundary: BoundaryAnalysis,
                        constraints: List[Constraint],
                        street_width: float) -> List[Tuple[float, float]]:
    """
    Scan for clear street segments at a given position.
    For horizontal: pos = Y position, returns list of (x1, x2) segments
    For vertical: pos = X position, returns list of (y1, y2) segments
    """
    half_width = street_width / 2
    expanded = [c.expanded() for c in constraints]

    segments = []

    if is_horizontal:
        # pos is the Y coordinate of the horizontal street
        x = boundary.usable_minX
        seg_start = None

        while x <= boundary.usable_maxX:
            # Check if street box at this position is clear
            box = {"minX": x, "maxX": min(x + 2, boundary.usable_maxX),
                   "minY": pos - half_width, "maxY": pos + half_width}

            is_clear = all(not boxes_overlap(box, exp) for exp in expanded)

            if is_clear and seg_start is None:
                seg_start = x
            elif not is_clear and seg_start is not None:
                if x - seg_start >= street_width:
                    segments.append((seg_start, x))
                seg_start = None

            x += 2

        if seg_start is not None and boundary.usable_maxX - seg_start >= street_width:
            segments.append((seg_start, boundary.usable_maxX))

    else:  # Vertical
        # pos is the X coordinate of the vertical street
        y = boundary.usable_minY
        seg_start = None

        while y <= boundary.usable_maxY:
            # FIX: Use 'pos' for X coordinates, not 'y'
            box = {"minX": pos - half_width, "maxX": pos + half_width,
                   "minY": y, "maxY": min(y + 2, boundary.usable_maxY)}

            is_clear = all(not boxes_overlap(box, exp) for exp in expanded)

            if is_clear and seg_start is None:
                seg_start = y
            elif not is_clear and seg_start is not None:
                if y - seg_start >= street_width:
                    segments.append((seg_start, y))
                seg_start = None

            y += 2

        if seg_start is not None and boundary.usable_maxY - seg_start >= street_width:
            segments.append((seg_start, boundary.usable_maxY))

    return segments


# =============================================================================
# STEP 4 & 5: BUILD CONNECTED STREET NETWORK
# =============================================================================

def find_best_vertical_positions(boundary: BoundaryAnalysis,
                                 constraints: List[Constraint],
                                 aisle_width: float,
                                 h_segments: List[Tuple]) -> List[float]:
    """
    Find the best X positions for vertical connector streets.
    Only place verticals at the EDGES to connect horizontal streets,
    minimizing stall space consumption.
    """
    half_width = aisle_width / 2

    # Try edge positions first - these are most efficient
    left_edge = boundary.usable_minX + half_width
    right_edge = boundary.usable_maxX - half_width

    v_positions = []

    # Check if edges can span the full height (connect all H streets)
    left_segs = scan_clear_segments(
        left_edge, False, boundary, constraints, aisle_width)
    right_segs = scan_clear_segments(
        right_edge, False, boundary, constraints, aisle_width)

    # We want at least one full-height vertical on each side
    lot_height = boundary.usable_maxY - boundary.usable_minY
    min_useful_span = lot_height * 0.7  # At least 70% of lot height

    # Check left edge
    left_total = sum(y2 - y1 for y1, y2 in left_segs)
    if left_total >= min_useful_span:
        v_positions.append(left_edge)

    # Check right edge
    right_total = sum(y2 - y1 for y1, y2 in right_segs)
    if right_total >= min_useful_span:
        v_positions.append(right_edge)

    # If edges aren't sufficient, find ONE good middle position
    if len(v_positions) < 2:
        # Scan for best alternate position
        best_x = None
        best_score = 0

        x = boundary.usable_minX + half_width + 30  # Start 30ft from edge
        while x <= boundary.usable_maxX - half_width - 30:
            segs = scan_clear_segments(
                x, False, boundary, constraints, aisle_width)
            total = sum(y2 - y1 for y1, y2 in segs)

            if total > best_score:
                best_score = total
                best_x = x

            x += 10

        if best_x and best_score >= min_useful_span:
            v_positions.append(best_x)

    return sorted(v_positions) if v_positions else [left_edge, right_edge]


def build_street_network(boundary: BoundaryAnalysis,
                         constraints: List[Constraint],
                         stall_length: float = 18.0,
                         aisle_width: float = 24.0,
                         verbose: bool = False) -> Tuple[List[Street], Dict]:
    """
    Build a connected street network using STRICT SPACING RULES:

    1. The 60-Foot Rule: Parallel streets EXACTLY 60' apart
    2. The 30-Foot Offset: First street 30' from boundary (18' stall + 12' half-aisle)
    3. Merge Vertices: Lines within 5' merged into one
    4. Snap to Grid: All coordinates on 1' grid
    5. Min Spacing: Delete any line < 50' from another parallel line
    """
    def log(msg):
        if verbose:
            print(msg)

    half_aisle = aisle_width / 2

    log(f"  [STRICT RULES] Applying 60-foot rule, 30-foot offset, 1-foot grid snap")

    # Use strict spacing rules to calculate horizontal street Y positions
    h_positions = calculate_strict_street_positions(
        boundary, constraints, stall_length, aisle_width, direction="horizontal"
    )

    log(
        f"  [STRICT] Calculated H positions (30' offset, 60' spacing): {[f'{y:.0f}' for y in h_positions]}")

    # Build horizontal streets first
    streets = []
    h_segments = []  # (y, x1, x2)
    v_segments = []  # (x, y1, y2)
    street_id = 1

    for y in h_positions:
        # Snap Y to grid
        y = snap_to_grid(y)
        segs = scan_clear_segments(y, True, boundary, constraints, aisle_width)
        for x1, x2 in segs:
            # Snap segment endpoints to grid
            x1 = snap_to_grid(x1)
            x2 = snap_to_grid(x2)
            streets.append(Street(x1, y, x2, y, aisle_width, True, street_id))
            h_segments.append((y, x1, x2))
            street_id += 1

    # Find optimal vertical street positions using strict rules
    v_positions = find_best_vertical_positions(
        boundary, constraints, aisle_width, h_segments)

    # Apply strict spacing rules to vertical positions
    v_positions = merge_close_positions(v_positions, MERGE_THRESHOLD)
    v_positions = filter_parallel_lines(v_positions, MIN_PARALLEL_SPACING)
    v_positions = [snap_to_grid(x) for x in v_positions]

    log(f"  [STRICT] H positions: {[f'{y:.0f}' for y in h_positions]}")
    log(
        f"  [STRICT] V positions (merged, filtered, snapped): {[f'{x:.0f}' for x in v_positions]}")

    for x in v_positions:
        segs = scan_clear_segments(
            x, False, boundary, constraints, aisle_width)
        for y1, y2 in segs:
            # Snap segment endpoints to grid
            y1 = snap_to_grid(y1)
            y2 = snap_to_grid(y2)
            streets.append(Street(x, y1, x, y2, aisle_width, False, street_id))
            v_segments.append((x, y1, y2))
            street_id += 1

    # Check initial connectivity
    connectivity = check_connectivity(h_segments, v_segments)

    # If not connected, try to add more vertical connectors (also with strict rules)
    if not connectivity["connected"] and connectivity["zones"] > 1:
        log(f"  [STRICT] Not connected ({connectivity['zones']} zones), adding connectors...")

        # Find gaps between horizontal segments and add verticals there
        for i, (y1, x1a, x1b) in enumerate(h_segments):
            for j, (y2, x2a, x2b) in enumerate(h_segments):
                if i >= j:
                    continue

                # Find overlapping X range
                overlap_start = max(x1a, x2a)
                overlap_end = min(x1b, x2b)

                if overlap_end - overlap_start >= aisle_width:
                    # There's overlap, check if we need a connector
                    mid_x = snap_to_grid((overlap_start + overlap_end) / 2)

                    # Check if there's already a vertical within MIN_PARALLEL_SPACING
                    has_vertical = any(
                        abs(vx - mid_x) < MIN_PARALLEL_SPACING for vx, _, _ in v_segments)

                    if not has_vertical:
                        # Try to add a vertical connector
                        segs = scan_clear_segments(
                            mid_x, False, boundary, constraints, aisle_width)
                        for vy1, vy2 in segs:
                            vy1 = snap_to_grid(vy1)
                            vy2 = snap_to_grid(vy2)
                            # Check if this connects the two horizontal streets
                            if vy1 <= min(y1, y2) and vy2 >= max(y1, y2):
                                streets.append(
                                    Street(mid_x, vy1, mid_x, vy2, aisle_width, False, street_id))
                                v_segments.append((mid_x, vy1, vy2))
                                street_id += 1
                                log(
                                    f"  [STRICT] Added connector at X={mid_x:.0f}")
                                break

        # Recheck connectivity
        connectivity = check_connectivity(h_segments, v_segments)

    # Final deduplication pass: remove any duplicate/overlapping streets
    streets, h_segments, v_segments = deduplicate_streets(
        streets, h_segments, v_segments)

    return streets, {
        "h_segments": h_segments,
        "v_segments": v_segments,
        "connectivity": connectivity
    }


def deduplicate_streets(streets: List[Street],
                        h_segments: List[Tuple],
                        v_segments: List[Tuple]) -> Tuple[List[Street], List[Tuple], List[Tuple]]:
    """
    Remove duplicate or near-duplicate streets that could cause overlapping lines.
    Uses MERGE_THRESHOLD to detect duplicates.
    """
    # Deduplicate horizontal segments
    unique_h = []
    for y, x1, x2 in sorted(h_segments, key=lambda s: (s[0], s[1])):
        is_duplicate = False
        for uy, ux1, ux2 in unique_h:
            # Same Y position (within threshold) and overlapping X range
            if abs(y - uy) < MERGE_THRESHOLD:
                # Check if X ranges overlap significantly
                overlap = min(x2, ux2) - max(x1, ux1)
                if overlap > 0:
                    is_duplicate = True
                    break
        if not is_duplicate:
            unique_h.append((y, x1, x2))

    # Deduplicate vertical segments
    unique_v = []
    for x, y1, y2 in sorted(v_segments, key=lambda s: (s[0], s[1])):
        is_duplicate = False
        for ux, uy1, uy2 in unique_v:
            # Same X position (within threshold) and overlapping Y range
            if abs(x - ux) < MERGE_THRESHOLD:
                # Check if Y ranges overlap significantly
                overlap = min(y2, uy2) - max(y1, uy1)
                if overlap > 0:
                    is_duplicate = True
                    break
        if not is_duplicate:
            unique_v.append((x, y1, y2))

    # Rebuild streets list from unique segments
    new_streets = []
    street_id = 1

    for y, x1, x2 in unique_h:
        new_streets.append(
            Street(x1, y, x2, y, streets[0].width if streets else 24.0, True, street_id))
        street_id += 1

    for x, y1, y2 in unique_v:
        new_streets.append(
            Street(x, y1, x, y2, streets[0].width if streets else 24.0, False, street_id))
        street_id += 1

    return new_streets, unique_h, unique_v


def check_connectivity(h_segments: List[Tuple], v_segments: List[Tuple]) -> Dict:
    """
    Check if all street segments are connected using Union-Find.
    """
    all_segments = [('H', s) for s in h_segments] + [('V', s)
                                                     for s in v_segments]
    n = len(all_segments)

    if n == 0:
        return {"connected": False, "zones": 0}

    parent = list(range(n))

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    # Check all pairs for intersection
    for i in range(n):
        for j in range(i + 1, n):
            t1, s1 = all_segments[i]
            t2, s2 = all_segments[j]

            if t1 == 'H' and t2 == 'V':
                hy, hx1, hx2 = s1
                vx, vy1, vy2 = s2
                if segments_intersect(hy, hx1, hx2, vx, vy1, vy2):
                    union(i, j)
            elif t1 == 'V' and t2 == 'H':
                vx, vy1, vy2 = s1
                hy, hx1, hx2 = s2
                if segments_intersect(hy, hx1, hx2, vx, vy1, vy2):
                    union(i, j)
            elif t1 == t2 == 'H':
                # Two horizontal segments connect if they share an endpoint
                y1, x1a, x1b = s1
                y2, x2a, x2b = s2
                if abs(y1 - y2) < 1 and (abs(x1b - x2a) < 1 or abs(x2b - x1a) < 1):
                    union(i, j)
            elif t1 == t2 == 'V':
                x1, y1a, y1b = s1
                x2, y2a, y2b = s2
                if abs(x1 - x2) < 1 and (abs(y1b - y2a) < 1 or abs(y2b - y1a) < 1):
                    union(i, j)

    roots = set(find(i) for i in range(n))
    num_zones = len(roots)

    return {
        "connected": num_zones <= 1,
        "zones": num_zones,
        "segments_count": n
    }


# =============================================================================
# STEP 6: OPTIMIZE CIRCULATION
# =============================================================================

def optimize_circulation(streets: List[Street],
                         boundary: BoundaryAnalysis) -> Dict:
    """
    Analyze and optimize circulation:
    - Check for dead-ends
    - Verify turning radius clearance
    - Suggest one-way flow if beneficial
    """
    analysis = {
        "dead_ends": [],
        "intersections": [],
        "flow_recommendation": "two-way",  # Default
        "turning_clearance": True
    }

    # Find all street endpoints
    endpoints = []
    for s in streets:
        endpoints.append((s.x1, s.y1, s))
        endpoints.append((s.x2, s.y2, s))

    # Check each endpoint for connections
    for x, y, street in endpoints:
        connected = False
        for other in streets:
            if other.id == street.id:
                continue
            # Check if this endpoint connects to another street
            box = other.get_box()
            if point_in_box(x, y, box):
                connected = True
                break

        if not connected:
            # Check if it's at boundary edge (entry/exit point)
            at_boundary = (abs(x - boundary.usable_minX) < 1 or
                           abs(x - boundary.usable_maxX) < 1 or
                           abs(y - boundary.usable_minY) < 1 or
                           abs(y - boundary.usable_maxY) < 1)
            if not at_boundary:
                analysis["dead_ends"].append({"x": x, "y": y})

    return analysis


# =============================================================================
# STEP 7: MAXIMIZE STALLS
# =============================================================================

def maximize_stalls(streets: List[Street],
                    street_info: Dict,
                    boundary: BoundaryAnalysis,
                    constraints: List[Constraint],
                    stall_width: float = 9.0,
                    stall_length: float = 18.0,
                    aisle_width: float = 24.0,
                    try_angled: bool = False) -> List[Stall]:
    """
    Iteratively place stalls to maximize count while respecting constraints.
    Supports both perpendicular (90°) and angled (45°, 60°) parking.
    """
    half_aisle = aisle_width / 2
    expanded_constraints = [c.expanded() for c in constraints]
    street_boxes = [s.get_box() for s in streets]

    h_segments = street_info["h_segments"]
    v_segments = street_info["v_segments"]

    stalls = []
    placed_boxes = []
    stall_id = 1

    def is_valid_placement(box: Dict) -> bool:
        """Check if stall placement is valid."""
        # Check boundary
        if (box["minX"] < boundary.usable_minX or
            box["maxX"] > boundary.usable_maxX or
            box["minY"] < boundary.usable_minY or
                box["maxY"] > boundary.usable_maxY):
            return False

        # Check constraints
        for exp in expanded_constraints:
            if boxes_overlap(box, exp):
                return False

        # Check streets
        for sb in street_boxes:
            if boxes_overlap(box, sb):
                return False

        # Check other stalls
        for pb in placed_boxes:
            if boxes_overlap(box, pb):
                return False

        return True

    def try_place_stall(cx: float, cy: float, angle: float,
                        width: float, length: float) -> bool:
        """Attempt to place a stall at given position."""
        nonlocal stall_id

        stall = Stall(stall_id, cx, cy, width, length, angle)
        box = stall.get_box()

        if is_valid_placement(box):
            stalls.append(stall)
            placed_boxes.append(box)
            stall_id += 1
            return True
        return False

    # Strategy 1: Place perpendicular stalls along horizontal streets
    for y, x1, x2 in h_segments:
        # North side of street
        stall_y = y + half_aisle + stall_length / 2
        if stall_y + stall_length / 2 <= boundary.usable_maxY:
            x = x1 + stall_width / 2
            while x + stall_width / 2 <= x2:
                try_place_stall(x, stall_y, 0, stall_width, stall_length)
                x += stall_width

        # South side of street
        stall_y = y - half_aisle - stall_length / 2
        if stall_y - stall_length / 2 >= boundary.usable_minY:
            x = x1 + stall_width / 2
            while x + stall_width / 2 <= x2:
                try_place_stall(x, stall_y, 0, stall_width, stall_length)
                x += stall_width

    # Strategy 2: Place perpendicular stalls along vertical streets
    for x, y1, y2 in v_segments:
        # East side of street
        stall_x = x + half_aisle + stall_length / 2
        if stall_x + stall_length / 2 <= boundary.usable_maxX:
            y = y1 + stall_width / 2
            while y + stall_width / 2 <= y2:
                try_place_stall(stall_x, y, 90, stall_width, stall_length)
                y += stall_width

        # West side of street
        stall_x = x - half_aisle - stall_length / 2
        if stall_x - stall_length / 2 >= boundary.usable_minX:
            y = y1 + stall_width / 2
            while y + stall_width / 2 <= y2:
                try_place_stall(stall_x, y, 90, stall_width, stall_length)
                y += stall_width

    # Strategy 3: Try angled parking if enabled (can fit more stalls)
    if try_angled:
        # Angled parking calculations
        angle = 45
        rad = math.radians(angle)

        # Effective dimensions for angled stalls
        angled_depth = stall_width * \
            math.sin(rad) + stall_length * math.cos(rad)
        angled_spacing = stall_width / math.cos(rad)

        # Try filling gaps with angled stalls
        # (Implementation would go here for Phase 2)

    return stalls


# =============================================================================
# MAIN LAYOUT GENERATOR
# =============================================================================

def generate_smart_layout(
    boundary: Dict[str, float],
    constraints: List[Dict[str, float]],
    stall_width: float = 9.0,
    stall_length: float = 18.0,
    aisle_width: float = 24.0,
    setback: float = 5.0,
    buffer: float = 2.0,
    verbose: bool = False,
    use_centerline_detection: bool = False,
    is_user_drawing: bool = False
) -> Dict[str, Any]:
    """
    Main entry point: Generate optimized parking layout.

    Implements the Parking Design Equation:
    Parking_Layout = f(Boundary, Constraints, Circulation_Optimization, Stall_Maximization)

    Args:
        boundary: Dict with minX, maxX, minY, maxY
        constraints: List of obstacle bounding boxes
        stall_width: Parking stall width (default 9ft)
        stall_length: Parking stall length (default 18ft)
        aisle_width: Drive aisle width (default 24ft for two-way)
        setback: Edge setback distance (default 5ft)
        buffer: Obstacle buffer distance (default 2ft)
        verbose: Print debug information
        use_centerline_detection: Use new centerline-based street detection
        is_user_drawing: True if processing user-uploaded drawing (auto-enables centerline)
    """

    def log(msg):
        if verbose:
            print(msg)

    # Auto-enable centerline detection for user drawings with obstacles
    if is_user_drawing and len(constraints) > 0:
        use_centerline_detection = True

    log(f"\n{'='*60}")
    log("SMART PARKING DESIGN SYSTEM v10")
    log(f"{'='*60}")

    if use_centerline_detection:
        log("  Mode: CENTERLINE-BASED DETECTION (for user drawings)")
    else:
        log("  Mode: GRID-BASED LAYOUT (standard)")

    # STEP 1: Evaluate Boundary
    log("\n[STEP 1] Evaluating boundary...")
    boundary_analysis = evaluate_boundary(boundary, setback)
    log(f"  Total area: {boundary_analysis.area:,.0f} sq ft")
    log(f"  Usable area: {boundary_analysis.usable_area:,.0f} sq ft")
    log(f"  Dimensions: {boundary_analysis.maxX - boundary_analysis.minX:.0f} x "
        f"{boundary_analysis.maxY - boundary_analysis.minY:.0f} ft")

    # STEP 2: Identify and classify constraints
    log(f"\n[STEP 2] Classifying {len(constraints)} constraints...")
    classified_constraints = classify_constraints(constraints)
    for c in classified_constraints:
        log(f"  - {c.type.value}: {c.width:.0f}x{c.height:.0f} ft at "
            f"({c.center[0]:.0f}, {c.center[1]:.0f})")

    # STEP 3 & 4 & 5: Build street network
    if use_centerline_detection:
        # NEW: Use centerline-based detection for user drawings
        log(f"\n[STEP 3-5] Detecting streets using CENTERLINE analysis...")
        streets, centerline_info = detect_streets_from_centerlines(
            boundary_analysis, classified_constraints,
            aisle_width, min_street_length=30.0,
            resolution=2.0, verbose=verbose
        )

        # Convert centerline streets to h_segments/v_segments format for stall placement
        h_segments = []
        v_segments = []
        for s in streets:
            if s.is_horizontal:
                h_segments.append((s.y1, s.x1, s.x2))
            else:
                v_segments.append((s.x1, s.y1, s.y2))

        street_info = {
            "h_segments": h_segments,
            "v_segments": v_segments,
            "connectivity": check_connectivity(h_segments, v_segments),
            "centerline_analysis": centerline_info
        }

        # If centerline detection didn't find enough streets, fall back to grid
        if len(streets) < 1:
            log(f"  [FALLBACK] Centerline detection found no streets, using grid method...")
            streets, street_info = build_street_network(
                boundary_analysis, classified_constraints, stall_length, aisle_width, verbose
            )
    else:
        # Standard grid-based approach
        log(f"\n[STEP 3] Analyzing clear zones around constraints...")
        log(f"\n[STEP 4-5] Building connected street network...")
        streets, street_info = build_street_network(
            boundary_analysis, classified_constraints, stall_length, aisle_width, verbose
        )

    connectivity = street_info["connectivity"]
    log(f"  Streets created: {len(streets)}")
    log(f"  H segments: {len(street_info['h_segments'])}")
    log(f"  V segments: {len(street_info['v_segments'])}")
    log(f"  Connected: {connectivity['connected']} (zones: {connectivity['zones']})")

    # STEP 6: Optimize circulation
    log(f"\n[STEP 6] Optimizing circulation...")
    circulation = optimize_circulation(streets, boundary_analysis)
    log(f"  Dead-ends found: {len(circulation['dead_ends'])}")
    log(f"  Flow recommendation: {circulation['flow_recommendation']}")

    # STEP 7: Maximize stalls
    log(f"\n[STEP 7] Maximizing stall placement...")
    stalls = maximize_stalls(
        streets, street_info, boundary_analysis, classified_constraints,
        stall_width, stall_length, aisle_width
    )
    log(f"  Stalls placed: {len(stalls)}")

    # Calculate efficiency metrics
    stall_area = len(stalls) * stall_width * stall_length
    efficiency = stall_area / \
        boundary_analysis.usable_area if boundary_analysis.usable_area > 0 else 0
    stalls_per_1000sqft = len(stalls) / (boundary_analysis.area / 1000)

    log(f"\n{'='*60}")
    log("RESULTS SUMMARY")
    log(f"{'='*60}")
    log(f"  Total stalls: {len(stalls)}")
    log(f"  Stalls per 1,000 sq ft: {stalls_per_1000sqft:.1f}")
    log(f"  Space efficiency: {efficiency*100:.1f}%")
    log(f"  All streets connected: {connectivity['connected']}")
    log(f"{'='*60}\n")

    result = {
        "streets": [s.to_dict() for s in streets],
        "stalls": [s.to_dict() for s in stalls],
        "connected": connectivity["connected"],
        "zones": connectivity["zones"],
        "stats": {
            "lot_area": boundary_analysis.area,
            "usable_area": boundary_analysis.usable_area,
            "stall_count": len(stalls),
            "street_count": len(streets),
            "zone_count": connectivity["zones"],
            "efficiency": efficiency,
            "stalls_per_1000sqft": stalls_per_1000sqft,
            "dead_ends": len(circulation["dead_ends"])
        },
        "analysis": {
            "boundary": {
                "total_area": boundary_analysis.area,
                "usable_area": boundary_analysis.usable_area,
                "perimeter": boundary_analysis.perimeter
            },
            "constraints": [
                {"type": c.type.value, "center": c.center,
                 "size": (c.width, c.height)} for c in classified_constraints
            ],
            "circulation": circulation,
            "method": "centerline" if use_centerline_detection else "grid"
        }
    }

    # Add centerline analysis if used
    if use_centerline_detection and "centerline_analysis" in street_info:
        result["analysis"]["centerline"] = street_info["centerline_analysis"]

    return result


def generate_layout_from_drawing(
    boundary: Dict[str, float],
    obstacles: List[Dict[str, float]],
    street_width: float = 24.0,
    stall_width: float = 9.0,
    stall_length: float = 18.0,
    setback: float = 5.0,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Specialized entry point for user-uploaded drawings.

    This function:
    1. Identifies obstacles from the drawing
    2. Computes continuous centerlines in the free space around obstacles
    3. Measures distance from centerline to obstacles on both sides
    4. Only draws streets where:
       - Distance to obstacle >= half_street_width on BOTH sides
       - Centerline continuity is maintained
    5. Places parking stalls along valid streets

    Args:
        boundary: The lot boundary {minX, maxX, minY, maxY}
        obstacles: List of obstacle bounding boxes from drawing analysis
        street_width: Required street width (default 24ft for two-way)
        stall_width: Parking stall width (default 9ft)
        stall_length: Parking stall length (default 18ft)
        setback: Edge setback distance (default 5ft)
        verbose: Print debug information

    Returns:
        Complete layout with streets, stalls, and analysis
    """
    return generate_smart_layout(
        boundary=boundary,
        constraints=obstacles,
        stall_width=stall_width,
        stall_length=stall_length,
        aisle_width=street_width,
        setback=setback,
        buffer=2.0,
        verbose=verbose,
        use_centerline_detection=True,
        is_user_drawing=True
    )


# =============================================================================
# TEST CASES
# =============================================================================

if __name__ == "__main__":
    # Test case: 200x150 ft lot (30,000 sq ft) - close to 10,000 sq ft example
    boundary = {"minX": 0, "maxX": 200, "minY": 0, "maxY": 150}

    print("\n" + "="*70)
    print("TEST 1: Empty lot (no constraints) - GRID method")
    print("="*70)
    result = generate_smart_layout(boundary, [], verbose=True)

    print("\n" + "="*70)
    print("TEST 2: 4 columns + 1 room - GRID method")
    print("="*70)
    # 4 columns (3x3 ft each) + 1 room (20x15 ft)
    constraints = [
        # Columns (structural pillars)
        {"minX": 48.5, "maxX": 51.5, "minY": 48.5, "maxY": 51.5},   # Column 1
        {"minX": 98.5, "maxX": 101.5, "minY": 48.5, "maxY": 51.5},  # Column 2
        {"minX": 148.5, "maxX": 151.5, "minY": 48.5, "maxY": 51.5},  # Column 3
        {"minX": 98.5, "maxX": 101.5, "minY": 98.5, "maxY": 101.5},  # Column 4
        # Room (small building/office)
        {"minX": 160, "maxX": 180, "minY": 110, "maxY": 125},       # Room
    ]
    result = generate_smart_layout(boundary, constraints, verbose=True)

    print("\n" + "="*70)
    print("TEST 3: Complex obstacles - CENTERLINE method (user drawing simulation)")
    print("="*70)
    # Simulating user-uploaded drawing with irregular obstacles
    complex_obstacles = [
        # Large L-shaped building (represented as two boxes)
        {"minX": 10, "maxX": 50, "minY": 10, "maxY": 40},  # L-base
        {"minX": 10, "maxX": 25, "minY": 40, "maxY": 70},  # L-upright
        # Central core / elevator
        {"minX": 90, "maxX": 110, "minY": 60, "maxY": 90},
        # Right side structure
        {"minX": 160, "maxX": 190, "minY": 20, "maxY": 50},
        # Top obstruction
        {"minX": 80, "maxX": 120, "minY": 120, "maxY": 140},
    ]

    # Use the new centerline-based approach
    result = generate_layout_from_drawing(
        boundary=boundary,
        obstacles=complex_obstacles,
        street_width=24.0,
        verbose=True
    )

    print(f"\nCenterline method results:")
    print(f"  Streets: {len(result['streets'])}")
    print(f"  Stalls: {len(result['stalls'])}")
    print(f"  Method: {result['analysis'].get('method', 'unknown')}")
    if 'centerline' in result['analysis']:
        cl = result['analysis']['centerline']
        print(f"  Centerline points: {cl['centerline_points']}")
        print(f"  Segments found: {cl['segments_found']}")
        print(f"  Valid segments: {cl['segments_valid']}")

    print("\n" + "="*70)
    print("TEST 4: Same complex obstacles - Comparing GRID vs CENTERLINE")
    print("="*70)

    print("\n--- Grid method ---")
    grid_result = generate_smart_layout(
        boundary, complex_obstacles,
        use_centerline_detection=False, verbose=True
    )

    print("\n--- Centerline method ---")
    centerline_result = generate_smart_layout(
        boundary, complex_obstacles,
        use_centerline_detection=True, verbose=True
    )

    print("\n" + "="*70)
    print("COMPARISON SUMMARY")
    print("="*70)
    print(
        f"  Grid method:       {len(grid_result['stalls'])} stalls, {len(grid_result['streets'])} streets")
    print(
        f"  Centerline method: {len(centerline_result['stalls'])} stalls, {len(centerline_result['streets'])} streets")
