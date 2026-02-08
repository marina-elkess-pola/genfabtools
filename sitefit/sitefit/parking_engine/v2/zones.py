"""
GenFabTools Parking Engine v2 — Zone Data Model

Zone Types:
- GENERAL: Standard parking area
- RESERVED: Reserved parking (non-ADA, e.g., employee, visitor, VIP)

Note: ADA is a global regulatory overlay, not a zone type.
ADA stall placement is handled by the v1 engine based on total stall count.

v1 remains frozen. This module is additive only.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import uuid

from sitefit.core.geometry import Point, Polygon
from sitefit.parking_engine.v2.geometry_60 import CirculationMode


class ZoneType(str, Enum):
    """
    Zone types for parking areas.

    GENERAL: Standard parking area (default)
    RESERVED: Reserved parking (non-ADA, e.g., employee, visitor, VIP)

    Note: ADA is NOT a zone type. ADA is a global regulatory requirement
    that applies across all zones based on total stall counts.
    """
    GENERAL = "GENERAL"
    RESERVED = "RESERVED"


class AngleConfig(str, Enum):
    """
    Stall angle configuration.

    90_DEGREES: Perpendicular parking (v1 default)
    60_DEGREES: Angled parking (v2, requires one-way aisles)
    45_DEGREES: Angled parking (v2, requires one-way aisles)
    30_DEGREES: Angled parking (v2, requires one-way aisles)
    """
    DEGREES_90 = "90_DEGREES"
    DEGREES_60 = "60_DEGREES"
    DEGREES_45 = "45_DEGREES"
    DEGREES_30 = "30_DEGREES"


@dataclass
class Setbacks:
    """
    Setback distances from zone edges.

    Setbacks define the required clearance from zone boundaries.
    All stall and module placement must occur inside the setback-adjusted
    buildable area.

    Attributes:
        north: Setback from north edge (positive Y direction)
        south: Setback from south edge (negative Y direction)
        east: Setback from east edge (positive X direction)
        west: Setback from west edge (negative X direction)

    Note: Setbacks are applied relative to the zone's primary axis,
    not global screen coordinates.
    """
    north: float = 0.0
    south: float = 0.0
    east: float = 0.0
    west: float = 0.0

    def __post_init__(self):
        for name, value in [("north", self.north), ("south", self.south),
                            ("east", self.east), ("west", self.west)]:
            if value < 0:
                raise ValueError(f"Setback {name} cannot be negative: {value}")

    @property
    def total_vertical(self) -> float:
        """Total vertical setback (north + south)."""
        return self.north + self.south

    @property
    def total_horizontal(self) -> float:
        """Total horizontal setback (east + west)."""
        return self.east + self.west


@dataclass
class Zone:
    """
    A named parking zone with defined boundaries.

    Zones are non-overlapping polygons that partition the parkable area.
    Each zone can have its own angle configuration, setbacks, and stall targets.

    Attributes:
        id: Unique identifier (UUID)
        name: Human-readable zone name
        zone_type: Type of zone (GENERAL or RESERVED)
        polygon: Zone boundary polygon
        angle_config: Stall angle (90° or 60°)
        setbacks: Setback distances from zone edges
        stall_target_min: Optional minimum stall count target
        stall_target_max: Optional maximum stall count target

    Primary Axis:
        Derived from the zone polygon's oriented bounding box (OBB).
        The primary axis is the direction of the longest edge.
        Aisle circulation direction follows this axis.

    Examples:
        >>> zone = Zone(
        ...     name="Main Lot",
        ...     zone_type=ZoneType.GENERAL,
        ...     polygon=Polygon([Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)])
        ... )
        >>> zone.zone_type
        <ZoneType.GENERAL: 'GENERAL'>
    """
    name: str
    zone_type: ZoneType
    polygon: Polygon
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    angle_config: AngleConfig = AngleConfig.DEGREES_90
    circulation_mode: CirculationMode = CirculationMode.ONE_WAY_FORWARD
    setbacks: Optional[Setbacks] = None
    stall_target_min: Optional[int] = None
    stall_target_max: Optional[int] = None

    def __post_init__(self):
        """Validate zone data after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Zone name cannot be empty")

        if not isinstance(self.zone_type, ZoneType):
            raise ValueError(f"Invalid zone type: {self.zone_type}")

        if not isinstance(self.angle_config, AngleConfig):
            raise ValueError(f"Invalid angle config: {self.angle_config}")

        if self.polygon.area <= 0:
            raise ValueError("Zone polygon must have positive area")

        # Validate stall targets
        if self.stall_target_min is not None and self.stall_target_min < 0:
            raise ValueError("stall_target_min must be non-negative")

        if self.stall_target_max is not None and self.stall_target_max < 0:
            raise ValueError("stall_target_max must be non-negative")

        if (self.stall_target_min is not None and
            self.stall_target_max is not None and
                self.stall_target_min > self.stall_target_max):
            raise ValueError("stall_target_min cannot exceed stall_target_max")

    @property
    def area(self) -> float:
        """Return zone area in square feet."""
        return self.polygon.area

    @property
    def centroid(self) -> Point:
        """Return zone centroid."""
        return self.polygon.centroid

    def contains_point(self, point: Point) -> bool:
        """Check if a point is inside the zone."""
        return self.polygon.contains_point(point)

    def intersects(self, other: Zone) -> bool:
        """Check if this zone intersects another zone."""
        # Use Shapely for intersection check
        return self.polygon.to_shapely().intersects(other.polygon.to_shapely())

    def intersection_area(self, other: Zone) -> float:
        """Return the intersection area with another zone."""
        # Use Shapely for intersection area calculation
        intersection = self.polygon.to_shapely().intersection(other.polygon.to_shapely())
        return intersection.area

    @property
    def primary_axis(self) -> Tuple[float, float]:
        """
        Return the primary axis direction vector (normalized).

        The primary axis is derived from the zone's bounding box:
        - Along the longest edge of the bounding box
        - Determines aisle circulation direction

        Returns:
            (dx, dy) normalized direction vector

        Note: This is topological, not screen-based.
        Rotating the zone rotates the axis consistently.
        """
        min_x, min_y, max_x, max_y = self.polygon.bounds
        width = max_x - min_x
        height = max_y - min_y

        if width >= height:
            # Primary axis along X (horizontal in zone's local frame)
            return (1.0, 0.0)
        else:
            # Primary axis along Y (vertical in zone's local frame)
            return (0.0, 1.0)

    @property
    def secondary_axis(self) -> Tuple[float, float]:
        """
        Return the secondary axis direction vector (perpendicular to primary).

        Returns:
            (dx, dy) normalized direction vector, perpendicular to primary
        """
        px, py = self.primary_axis
        # Rotate 90 degrees counter-clockwise
        return (-py, px)

    @property
    def buildable_bounds(self) -> Tuple[float, float, float, float]:
        """
        Return the buildable area bounds after applying setbacks.

        All stall and module placement must occur within these bounds.

        Returns:
            (min_x, min_y, max_x, max_y) after setback adjustment
        """
        min_x, min_y, max_x, max_y = self.polygon.bounds

        if self.setbacks is None:
            return (min_x, min_y, max_x, max_y)

        # Apply setbacks (west/south reduce min, east/north reduce max)
        buildable_min_x = min_x + self.setbacks.west
        buildable_min_y = min_y + self.setbacks.south
        buildable_max_x = max_x - self.setbacks.east
        buildable_max_y = max_y - self.setbacks.north

        return (buildable_min_x, buildable_min_y, buildable_max_x, buildable_max_y)

    @property
    def buildable_dimensions(self) -> Tuple[float, float]:
        """
        Return the buildable area dimensions after setbacks.

        Returns:
            (width, height) of buildable area
        """
        min_x, min_y, max_x, max_y = self.buildable_bounds
        return (max(0, max_x - min_x), max(0, max_y - min_y))

    def is_buildable(self) -> bool:
        """
        Check if zone has positive buildable area after setbacks.

        Returns:
            True if buildable area has positive dimensions
        """
        width, height = self.buildable_dimensions
        return width > 0 and height > 0


def validate_zones(zones: List[Zone]) -> List[str]:
    """
    Validate a list of zones for use in layout generation.

    Checks:
    - No overlapping zones (zones must be disjoint)
    - All zones have valid polygons
    - Zone IDs are unique

    Args:
        zones: List of zones to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: List[str] = []

    if not zones:
        return errors  # Empty is valid (defaults to single GENERAL zone)

    # Check for duplicate IDs
    ids = [z.id for z in zones]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate zone IDs detected")

    # Check for overlapping zones
    for i, zone_a in enumerate(zones):
        for zone_b in zones[i + 1:]:
            if zone_a.intersects(zone_b):
                # Allow touching (shared edges) but not overlapping
                overlap = zone_a.intersection_area(zone_b)
                if overlap > 0.01:  # Tolerance for floating point
                    errors.append(
                        f"Zones '{zone_a.name}' and '{zone_b.name}' overlap "
                        f"by {overlap:.2f} sq ft"
                    )

    return errors


def sort_zones_for_processing(zones: List[Zone]) -> List[Zone]:
    """
    Sort zones in deterministic order for layout processing.

    Order: alphabetical by zone.id

    This ensures deterministic output for identical input.

    Args:
        zones: List of zones to sort

    Returns:
        Sorted list of zones
    """
    return sorted(zones, key=lambda z: z.id)


def create_default_zone(site_boundary: Polygon) -> Zone:
    """
    Create a default GENERAL zone covering the entire site.

    Used when no zones are specified (backwards compatibility with v1).

    Args:
        site_boundary: Site boundary polygon

    Returns:
        A single GENERAL zone covering the entire site
    """
    return Zone(
        id="default-zone",
        name="Default",
        zone_type=ZoneType.GENERAL,
        polygon=site_boundary,
        angle_config=AngleConfig.DEGREES_90
    )
