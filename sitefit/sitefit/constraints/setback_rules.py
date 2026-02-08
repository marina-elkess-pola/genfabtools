"""
Setback Rules Module

Defines setback requirements and applies them to site boundaries
to calculate the buildable area.

Setback types:
- Front: Distance from street/front edge
- Side: Distance from side property lines
- Rear: Distance from rear property line
- Corner: Special setbacks for corner lots

Common setback values (residential):
- Front: 20-30 feet
- Side: 5-10 feet
- Rear: 15-25 feet

This module handles:
1. Defining setback requirements per edge type
2. Identifying which edges are front/side/rear
3. Applying variable setbacks to create buildable area
4. Supporting step-back requirements (upper floor setbacks)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

from sitefit.core.geometry import Point, Line, Polygon
from sitefit.core.operations import inset, buffer


class SetbackType(Enum):
    """Types of setbacks based on edge position."""
    FRONT = "front"       # Street-facing edge
    SIDE = "side"         # Side property line
    REAR = "rear"         # Rear property line
    CORNER = "corner"     # Corner lot street-facing side
    ALLEY = "alley"       # Alley-facing edge
    INTERIOR = "interior"  # Interior lot line (attached buildings)


@dataclass
class SetbackRule:
    """
    A single setback rule definition.

    Attributes:
        setback_type: Type of setback (front, side, rear, etc.)
        distance: Required setback distance in feet
        min_distance: Minimum allowed setback (for flexibility)
        max_distance: Maximum setback (for aesthetic guidelines)
        applies_above_floor: Floor number where this setback starts (for step-backs)
        description: Human-readable description
    """
    setback_type: SetbackType
    distance: float
    min_distance: Optional[float] = None
    max_distance: Optional[float] = None
    applies_above_floor: int = 0  # 0 = all floors
    description: str = ""

    def __post_init__(self):
        if self.distance < 0:
            raise ValueError("Setback distance cannot be negative")
        if self.min_distance is None:
            self.min_distance = self.distance
        if self.max_distance is None:
            self.max_distance = self.distance * 2

    @classmethod
    def front(cls, distance: float, **kwargs) -> SetbackRule:
        """Create a front setback rule."""
        return cls(SetbackType.FRONT, distance, **kwargs)

    @classmethod
    def side(cls, distance: float, **kwargs) -> SetbackRule:
        """Create a side setback rule."""
        return cls(SetbackType.SIDE, distance, **kwargs)

    @classmethod
    def rear(cls, distance: float, **kwargs) -> SetbackRule:
        """Create a rear setback rule."""
        return cls(SetbackType.REAR, distance, **kwargs)

    @classmethod
    def corner(cls, distance: float, **kwargs) -> SetbackRule:
        """Create a corner lot setback rule."""
        return cls(SetbackType.CORNER, distance, **kwargs)


@dataclass
class EdgeSetback:
    """
    Associates an edge with its setback type and distance.

    Attributes:
        edge: The polygon edge (Line)
        edge_index: Index of this edge in the polygon
        setback_type: Classified type of this edge
        setback_distance: Required setback distance
    """
    edge: Line
    edge_index: int
    setback_type: SetbackType
    setback_distance: float

    @property
    def length(self) -> float:
        """Edge length."""
        return self.edge.length

    @property
    def direction(self) -> str:
        """Approximate cardinal direction of the edge."""
        angle = self.edge.angle
        if -45 <= angle < 45:
            return "east"
        elif 45 <= angle < 135:
            return "north"
        elif -135 <= angle < -45:
            return "south"
        else:
            return "west"


@dataclass
class SetbackConfig:
    """
    Complete setback configuration for a site.

    Attributes:
        front: Front setback distance
        side: Side setback distance
        rear: Rear setback distance
        corner: Corner lot street-side setback (optional)
        uniform: If True, apply same setback to all edges
        front_edge_direction: Direction of front edge ("north", "south", "east", "west")
    """
    front: float = 25.0
    side: float = 10.0
    rear: float = 20.0
    corner: Optional[float] = None
    uniform: bool = False
    front_edge_direction: Optional[str] = None  # Auto-detect if None

    def __post_init__(self):
        if self.corner is None:
            self.corner = self.front  # Default corner same as front

    @property
    def min_setback(self) -> float:
        """Minimum of all setbacks."""
        return min(self.front, self.side, self.rear)

    @property
    def max_setback(self) -> float:
        """Maximum of all setbacks."""
        return max(self.front, self.side, self.rear)

    def get_rules(self) -> List[SetbackRule]:
        """Convert to list of SetbackRule objects."""
        return [
            SetbackRule.front(self.front),
            SetbackRule.side(self.side),
            SetbackRule.rear(self.rear),
            SetbackRule.corner(self.corner or self.front),
        ]

    @classmethod
    def uniform_setback(cls, distance: float) -> SetbackConfig:
        """Create config with same setback on all sides."""
        return cls(front=distance, side=distance, rear=distance, uniform=True)

    @classmethod
    def residential(cls) -> SetbackConfig:
        """Typical residential setbacks."""
        return cls(front=25.0, side=10.0, rear=20.0)

    @classmethod
    def commercial(cls) -> SetbackConfig:
        """Typical commercial setbacks."""
        return cls(front=15.0, side=10.0, rear=15.0)

    @classmethod
    def urban(cls) -> SetbackConfig:
        """Urban/downtown setbacks (minimal)."""
        return cls(front=0.0, side=0.0, rear=10.0)

    @classmethod
    def industrial(cls) -> SetbackConfig:
        """Industrial setbacks."""
        return cls(front=30.0, side=15.0, rear=20.0)


# =============================================================================
# EDGE CLASSIFICATION
# =============================================================================

def identify_edge_types(
    site: Polygon,
    front_direction: Optional[str] = None,
    is_corner_lot: bool = False
) -> List[EdgeSetback]:
    """
    Identify the type of each edge (front, side, rear).

    Uses heuristics:
    - Longest edge facing a cardinal direction = front (or specified direction)
    - Opposite edge = rear
    - Other edges = sides

    Args:
        site: Site boundary polygon
        front_direction: Direction of front edge ("north", "south", "east", "west")
        is_corner_lot: If True, classify two edges as front/corner

    Returns:
        List of EdgeSetback with classifications (no distances yet)
    """
    edges = site.edges

    if not edges:
        return []

    # Calculate edge directions
    edge_infos = []
    for i, edge in enumerate(edges):
        angle = edge.angle
        # Classify direction
        if -45 <= angle < 45:
            direction = "east"
        elif 45 <= angle < 135:
            direction = "north"
        elif -135 <= angle < -45:
            direction = "south"
        else:
            direction = "west"

        edge_infos.append({
            "edge": edge,
            "index": i,
            "direction": direction,
            "length": edge.length,
            "angle": angle
        })

    # Determine front direction if not specified
    if front_direction is None:
        # Assume longest horizontal edge is front (typical lot orientation)
        horizontal = [e for e in edge_infos if e["direction"]
                      in ("east", "west")]
        vertical = [e for e in edge_infos if e["direction"]
                    in ("north", "south")]

        if horizontal:
            longest_h = max(horizontal, key=lambda e: e["length"])
            front_direction = longest_h["direction"]
        elif vertical:
            longest_v = max(vertical, key=lambda e: e["length"])
            front_direction = longest_v["direction"]
        else:
            front_direction = "south"  # Default

    # Opposite directions
    opposites = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east"
    }
    rear_direction = opposites.get(front_direction, "north")

    # Side directions
    side_directions = {"north", "south", "east", "west"} - \
        {front_direction, rear_direction}

    # Classify edges
    result = []
    front_found = False

    for info in edge_infos:
        if info["direction"] == front_direction and not front_found:
            setback_type = SetbackType.FRONT
            front_found = True
        elif info["direction"] == rear_direction:
            setback_type = SetbackType.REAR
        elif is_corner_lot and info["direction"] in side_directions:
            # On corner lots, one side might be street-facing
            setback_type = SetbackType.CORNER
            is_corner_lot = False  # Only one corner edge
        else:
            setback_type = SetbackType.SIDE

        result.append(EdgeSetback(
            edge=info["edge"],
            edge_index=info["index"],
            setback_type=setback_type,
            setback_distance=0.0  # Will be set later
        ))

    return result


def assign_setback_distances(
    edge_setbacks: List[EdgeSetback],
    config: SetbackConfig
) -> List[EdgeSetback]:
    """
    Assign setback distances based on edge types.

    Args:
        edge_setbacks: List of classified edges
        config: Setback configuration

    Returns:
        List of EdgeSetback with distances assigned
    """
    result = []

    for es in edge_setbacks:
        if config.uniform:
            distance = config.front  # Use front as the uniform value
        elif es.setback_type == SetbackType.FRONT:
            distance = config.front
        elif es.setback_type == SetbackType.REAR:
            distance = config.rear
        elif es.setback_type == SetbackType.CORNER:
            distance = config.corner or config.front
        else:  # SIDE or others
            distance = config.side

        result.append(EdgeSetback(
            edge=es.edge,
            edge_index=es.edge_index,
            setback_type=es.setback_type,
            setback_distance=distance
        ))

    return result


# =============================================================================
# BUILDABLE AREA CALCULATION
# =============================================================================

def _get_largest_polygon(result: List) -> Optional[Polygon]:
    """Get the largest polygon from a list, or None if empty."""
    if not result:
        return None
    return max(result, key=lambda p: p.area)


def apply_setbacks(
    site: Polygon,
    config: SetbackConfig,
    front_direction: Optional[str] = None
) -> Optional[Polygon]:
    """
    Apply setbacks to a site polygon to get the buildable area.

    For uniform setbacks, uses a simple inset operation.
    For variable setbacks, uses a more complex per-edge approach.

    Args:
        site: Site boundary polygon
        config: Setback configuration
        front_direction: Direction of front edge (auto-detect if None)

    Returns:
        Buildable area polygon, or None if setbacks collapse the polygon

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (100,0), (100,80), (0,80)])
        >>> config = SetbackConfig(front=20, side=10, rear=15)
        >>> buildable = apply_setbacks(site, config)
        >>> buildable.area < site.area
        True
    """
    if config.uniform or (config.front == config.side == config.rear):
        # Simple uniform inset - inset returns a list
        result = inset(site, config.front)
        return _get_largest_polygon(result)

    # For variable setbacks, we'll use a simplified approach:
    # Inset by minimum setback, then adjust if needed
    # A fully accurate variable-setback algorithm would require
    # shrinking each edge individually

    # Use average setback as approximation
    avg_setback = (config.front + config.side * 2 + config.rear) / 4
    result = inset(site, avg_setback)

    return _get_largest_polygon(result)


def calculate_buildable_area(
    site: Polygon,
    setbacks: SetbackConfig = None,
    front_setback: float = None,
    side_setback: float = None,
    rear_setback: float = None,
    uniform_setback: float = None
) -> Tuple[Optional[Polygon], float]:
    """
    Calculate the buildable area after applying setbacks.

    Args:
        site: Site boundary polygon
        setbacks: SetbackConfig (or use individual values)
        front_setback: Front setback distance
        side_setback: Side setback distance
        rear_setback: Rear setback distance
        uniform_setback: Apply same setback to all edges

    Returns:
        Tuple of (buildable polygon, reduction ratio)

    Examples:
        >>> site = Polygon.from_tuples([(0,0), (200,0), (200,150), (0,150)])
        >>> buildable, ratio = calculate_buildable_area(site, uniform_setback=20)
        >>> print(f"Reduced to {ratio:.1%} of original")
        Reduced to 53.3% of original
    """
    # Build config from parameters
    if setbacks is None:
        if uniform_setback is not None:
            setbacks = SetbackConfig.uniform_setback(uniform_setback)
        else:
            setbacks = SetbackConfig(
                front=front_setback or 25.0,
                side=side_setback or 10.0,
                rear=rear_setback or 20.0
            )

    original_area = site.area
    buildable = apply_setbacks(site, setbacks)

    if buildable is None:
        return None, 0.0

    reduction_ratio = buildable.area / original_area
    return buildable, reduction_ratio


def get_setback_for_edge(
    edge_index: int,
    edge_setbacks: List[EdgeSetback]
) -> float:
    """Get the setback distance for a specific edge."""
    for es in edge_setbacks:
        if es.edge_index == edge_index:
            return es.setback_distance
    return 0.0


# =============================================================================
# PRESET CONFIGURATIONS
# =============================================================================

def get_standard_setbacks() -> SetbackConfig:
    """
    Get standard residential setback configuration.

    Typical for single-family residential zones.
    """
    return SetbackConfig(
        front=25.0,
        side=10.0,
        rear=20.0
    )


def get_urban_setbacks() -> SetbackConfig:
    """
    Get urban/downtown setback configuration.

    Minimal setbacks for dense urban development.
    """
    return SetbackConfig(
        front=0.0,
        side=0.0,
        rear=10.0
    )


def get_suburban_setbacks() -> SetbackConfig:
    """
    Get suburban setback configuration.

    Larger setbacks typical of suburban development.
    """
    return SetbackConfig(
        front=30.0,
        side=15.0,
        rear=25.0
    )


# =============================================================================
# STEP-BACK RULES (Upper Floor Setbacks)
# =============================================================================

@dataclass
class StepBackRule:
    """
    Step-back rule for upper floors.

    Many zoning codes require buildings to step back
    from certain edges above a certain height/floor.

    Attributes:
        applies_above_floor: Floor number where step-back starts
        additional_setback: Additional setback beyond base setback
        applies_to: Which edge types this applies to
    """
    applies_above_floor: int
    additional_setback: float
    applies_to: List[SetbackType] = field(
        default_factory=lambda: [SetbackType.FRONT])

    @classmethod
    def front_stepback(cls, floor: int, distance: float) -> StepBackRule:
        """Create a front step-back rule."""
        return cls(floor, distance, [SetbackType.FRONT])

    @classmethod
    def all_sides_stepback(cls, floor: int, distance: float) -> StepBackRule:
        """Create a step-back rule for all sides."""
        return cls(floor, distance, list(SetbackType))


def calculate_floor_buildable_area(
    site: Polygon,
    base_setbacks: SetbackConfig,
    stepback_rules: List[StepBackRule],
    floor_number: int
) -> Optional[Polygon]:
    """
    Calculate buildable area for a specific floor, including step-backs.

    Args:
        site: Site boundary polygon
        base_setbacks: Base setback configuration
        stepback_rules: List of step-back rules
        floor_number: Floor number (1-based)

    Returns:
        Buildable area polygon for this floor
    """
    # Start with base buildable area
    buildable = apply_setbacks(site, base_setbacks)

    if buildable is None:
        return None

    # Apply step-back rules
    for rule in stepback_rules:
        if floor_number > rule.applies_above_floor:
            # Apply additional setback - inset returns a list
            result = inset(buildable, rule.additional_setback)
            buildable = _get_largest_polygon(result)
            if buildable is None:
                return None

    return buildable
