"""
Parking Optimizer Module

Optimizes parking layouts by testing multiple configurations and finding
the best solution based on configurable objectives.

Key responsibilities:
1. Try multiple parking angles (0°, 45°, 60°, 90°)
2. Test different bay configurations (single vs double loaded)
3. Respect exclusion zones and setbacks
4. Maximize stall count or other objectives
5. Return ranked list of best configurations

Optimization strategies:
- Exhaustive: Try all angle combinations
- Greedy: Start with best angle for longest edge, refine
- Genetic: Evolve configurations (future enhancement)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from enum import Enum
import time

from sitefit.core.geometry import Point, Line, Polygon, Rectangle
from sitefit.core.operations import inset, subtract_all
from sitefit.parking.stall import Stall, StallType, required_ada_stalls
from sitefit.parking.drive_aisle import DriveAisle, AisleType
from sitefit.parking.bay import ParkingBay
from sitefit.parking.layout_generator import (
    ParkingLayoutGenerator, LayoutConfig, LayoutResult, Exclusion,
    generate_parking_layout
)
from sitefit.parking.circulation import (
    CirculationGenerator, CirculationNetwork, generate_circulation
)


class OptimizationObjective(Enum):
    """What to optimize for."""
    MAX_STALLS = "max_stalls"           # Maximum parking stalls
    MAX_EFFICIENCY = "max_efficiency"   # Best stalls per 1000 SF
    MIN_CIRCULATION = "min_circulation"  # Minimize circulation area
    BALANCED = "balanced"               # Balance stalls and efficiency


class OptimizationStrategy(Enum):
    """How to search for optimal solution."""
    EXHAUSTIVE = "exhaustive"   # Try all combinations
    GREEDY = "greedy"           # Quick heuristic-based
    ADAPTIVE = "adaptive"       # Start greedy, refine best


@dataclass
class OptimizationConfig:
    """
    Configuration for parking optimization.

    Attributes:
        objective: What to optimize for
        strategy: Search strategy
        angles_to_try: List of parking angles to test
        test_single_loaded: Whether to test single-loaded bays
        test_compact_stalls: Whether to test compact stall configurations
        setback: Site boundary setback
        min_stalls: Minimum required stalls (constraint)
        max_iterations: Maximum optimization iterations
        time_limit_seconds: Maximum optimization time
    """
    objective: OptimizationObjective = OptimizationObjective.MAX_STALLS
    strategy: OptimizationStrategy = OptimizationStrategy.EXHAUSTIVE
    angles_to_try: List[float] = field(default_factory=lambda: [0, 45, 60, 90])
    test_single_loaded: bool = False
    test_compact_stalls: bool = False
    setback: float = 0.0
    min_stalls: int = 0
    max_iterations: int = 100
    time_limit_seconds: float = 30.0


@dataclass
class OptimizationResult:
    """
    Result of a single optimization trial.

    Attributes:
        layout: The parking layout result
        circulation: The circulation network
        score: Optimization score (higher is better)
        angle: Parking angle used
        stall_type: Type of stalls
        double_loaded: Whether double-loaded bays were used
        meets_constraints: Whether all constraints are satisfied
        ada_compliant: Whether ADA requirements are met
    """
    layout: LayoutResult
    circulation: Optional[CirculationNetwork]
    score: float
    angle: float
    stall_type: str
    double_loaded: bool
    meets_constraints: bool
    ada_compliant: bool

    @property
    def total_stalls(self) -> int:
        """Total parking stalls."""
        return self.layout.total_stalls

    @property
    def efficiency(self) -> float:
        """Stalls per 1000 SF."""
        return self.layout.efficiency

    @property
    def site_area(self) -> float:
        """Total site area."""
        return self.layout.site_area

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_stalls": self.total_stalls,
            "score": round(self.score, 3),
            "angle": self.angle,
            "stall_type": self.stall_type,
            "double_loaded": self.double_loaded,
            "efficiency": round(self.efficiency, 2),
            "site_area": round(self.site_area, 1),
            "meets_constraints": self.meets_constraints,
            "ada_compliant": self.ada_compliant,
            "layout": self.layout.to_dict(),
            "circulation": self.circulation.to_dict() if self.circulation else None
        }


@dataclass
class OptimizationSummary:
    """
    Summary of optimization run.

    Attributes:
        best_result: The best configuration found
        all_results: All tested configurations
        iterations: Number of iterations performed
        elapsed_time: Time taken in seconds
        site_area: Site area
        excluded_area: Area of exclusions
    """
    best_result: Optional[OptimizationResult]
    all_results: List[OptimizationResult]
    iterations: int
    elapsed_time: float
    site_area: float
    excluded_area: float

    @property
    def results_by_angle(self) -> Dict[float, OptimizationResult]:
        """Get best result for each angle."""
        by_angle = {}
        for r in self.all_results:
            if r.angle not in by_angle or r.score > by_angle[r.angle].score:
                by_angle[r.angle] = r
        return by_angle

    @property
    def best_angle(self) -> Optional[float]:
        """Get the best performing angle."""
        if self.best_result:
            return self.best_result.angle
        return None

    @property
    def max_stalls(self) -> int:
        """Maximum stalls achieved."""
        if self.best_result:
            return self.best_result.total_stalls
        return 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "best_angle": self.best_angle,
            "max_stalls": self.max_stalls,
            "iterations": self.iterations,
            "elapsed_time": round(self.elapsed_time, 3),
            "site_area": round(self.site_area, 1),
            "excluded_area": round(self.excluded_area, 1),
            "best_result": self.best_result.to_dict() if self.best_result else None,
            "results_count": len(self.all_results),
            "results_by_angle": {
                str(k): v.to_dict()
                for k, v in self.results_by_angle.items()
            }
        }


class ParkingOptimizer:
    """
    Optimizes parking layouts for a site.

    Usage:
        >>> site = Polygon([...])
        >>> optimizer = ParkingOptimizer(site)
        >>> summary = optimizer.optimize()
        >>> print(f"Best: {summary.max_stalls} stalls at {summary.best_angle}°")

        >>> # With exclusions
        >>> obstacles = [Exclusion(polygon=..., exclusion_type="column")]
        >>> optimizer = ParkingOptimizer(site, exclusions=obstacles)
        >>> summary = optimizer.optimize()
    """

    def __init__(
        self,
        site: Polygon,
        exclusions: List[Exclusion] = None,
        config: OptimizationConfig = None
    ):
        """
        Initialize the parking optimizer.

        Args:
            site: Site boundary polygon
            exclusions: List of exclusion zones
            config: Optimization configuration
        """
        self.site = site
        self.exclusions = exclusions or []
        self.config = config or OptimizationConfig()

        # Calculate site metrics
        self.site_area = site.area
        self.excluded_area = sum(e.polygon.area for e in self.exclusions)

        # Results storage
        self.results: List[OptimizationResult] = []
        self.iterations = 0
        self.start_time = 0

    def optimize(self) -> OptimizationSummary:
        """
        Run the optimization and return the best configuration.

        Returns:
            OptimizationSummary with best result and all tested configurations
        """
        self.results = []
        self.iterations = 0
        self.start_time = time.time()

        if self.config.strategy == OptimizationStrategy.EXHAUSTIVE:
            self._optimize_exhaustive()
        elif self.config.strategy == OptimizationStrategy.GREEDY:
            self._optimize_greedy()
        else:  # ADAPTIVE
            self._optimize_adaptive()

        elapsed = time.time() - self.start_time

        # Find best result
        best = None
        if self.results:
            # Filter to those meeting constraints
            valid = [r for r in self.results if r.meets_constraints]
            if valid:
                best = max(valid, key=lambda r: r.score)
            else:
                best = max(self.results, key=lambda r: r.score)

        return OptimizationSummary(
            best_result=best,
            all_results=self.results,
            iterations=self.iterations,
            elapsed_time=elapsed,
            site_area=self.site_area,
            excluded_area=self.excluded_area
        )

    def _optimize_exhaustive(self):
        """Try all configured combinations."""
        stall_types = ["standard"]
        if self.config.test_compact_stalls:
            stall_types.append("compact")

        load_types = [True]  # Double-loaded
        if self.config.test_single_loaded:
            load_types.append(False)

        for angle in self.config.angles_to_try:
            for stall_type in stall_types:
                for double_loaded in load_types:
                    if self._check_limits():
                        break

                    result = self._evaluate_configuration(
                        angle=angle,
                        stall_type=stall_type,
                        double_loaded=double_loaded
                    )

                    if result:
                        self.results.append(result)

                    self.iterations += 1

    def _optimize_greedy(self):
        """Quick optimization using heuristics."""
        # Start with the best angle for the site shape
        best_angle = self._estimate_best_angle()

        # Clamp to valid range
        best_angle = max(0, min(90, best_angle))

        # Try best angle first
        result = self._evaluate_configuration(
            angle=best_angle,
            stall_type="standard",
            double_loaded=True
        )
        if result:
            self.results.append(result)
        self.iterations += 1

        # Try adjacent angles (only valid 0-90 range)
        for delta in [15, -15, 30, -30]:
            angle = best_angle + delta
            # Clamp to valid range 0-90
            if angle < 0 or angle > 90:
                continue
            if angle in self.config.angles_to_try or delta in [-15, 15]:
                if self._check_limits():
                    break

                result = self._evaluate_configuration(
                    angle=angle,
                    stall_type="standard",
                    double_loaded=True
                )
                if result:
                    self.results.append(result)
                self.iterations += 1

    def _optimize_adaptive(self):
        """Start greedy, then refine around best."""
        # First pass: greedy
        self._optimize_greedy()

        if not self.results:
            return

        # Find current best
        current_best = max(self.results, key=lambda r: r.score)
        best_angle = current_best.angle

        # Refine around best angle
        for delta in [-10, -5, 5, 10]:
            angle = best_angle + delta
            if 0 <= angle <= 90 and not self._check_limits():
                result = self._evaluate_configuration(
                    angle=angle,
                    stall_type="standard",
                    double_loaded=True
                )
                if result:
                    self.results.append(result)
                self.iterations += 1

        # Try compact stalls if enabled
        if self.config.test_compact_stalls and not self._check_limits():
            result = self._evaluate_configuration(
                angle=best_angle,
                stall_type="compact",
                double_loaded=True
            )
            if result:
                self.results.append(result)
            self.iterations += 1

    def _evaluate_configuration(
        self,
        angle: float,
        stall_type: str,
        double_loaded: bool
    ) -> Optional[OptimizationResult]:
        """
        Evaluate a single configuration.

        Args:
            angle: Parking angle
            stall_type: "standard" or "compact"
            double_loaded: Whether to use double-loaded bays

        Returns:
            OptimizationResult or None if configuration fails
        """
        # Validate angle range
        if angle < 0 or angle > 90:
            return None

        # Get stall configuration
        try:
            if stall_type == "compact":
                stall = Stall.compact(angle=angle)
            else:
                stall = Stall.standard(angle=angle)
        except ValueError:
            return None

        # Get aisle configuration
        if angle == 90:
            aisle = DriveAisle.two_way()
        else:
            aisle = DriveAisle.one_way(parking_angle=angle)

        # Create layout config
        layout_config = LayoutConfig(
            stall=stall,
            aisle=aisle,
            double_loaded=double_loaded,
            setback=self.config.setback,
            angles_to_try=[angle]
        )

        # Generate layout
        try:
            generator = ParkingLayoutGenerator(
                self.site,
                self.exclusions,
                layout_config
            )
            layout = generator.generate_at_angle(angle)
        except Exception:
            return None

        if layout.total_stalls == 0:
            return None

        # Generate circulation (optional, may fail)
        circulation = None
        try:
            circulation = generate_circulation(self.site, layout)
        except Exception:
            pass

        # Check constraints
        meets_constraints = self._check_constraints(layout)
        ada_compliant = self._check_ada_compliance(layout)

        # Calculate score
        score = self._calculate_score(layout, circulation)

        return OptimizationResult(
            layout=layout,
            circulation=circulation,
            score=score,
            angle=angle,
            stall_type=stall_type,
            double_loaded=double_loaded,
            meets_constraints=meets_constraints,
            ada_compliant=ada_compliant
        )

    def _calculate_score(
        self,
        layout: LayoutResult,
        circulation: Optional[CirculationNetwork]
    ) -> float:
        """
        Calculate optimization score for a layout.

        Higher score is better.
        """
        if self.config.objective == OptimizationObjective.MAX_STALLS:
            return float(layout.total_stalls)

        elif self.config.objective == OptimizationObjective.MAX_EFFICIENCY:
            return layout.efficiency

        elif self.config.objective == OptimizationObjective.MIN_CIRCULATION:
            if circulation:
                # Lower circulation area is better
                circ_ratio = circulation.total_lane_area / layout.site_area
                return 100.0 * (1.0 - circ_ratio)
            return float(layout.total_stalls)

        else:  # BALANCED
            # Combine stall count and efficiency
            stall_score = layout.total_stalls
            efficiency_score = layout.efficiency * 10  # Scale up
            return stall_score * 0.6 + efficiency_score * 0.4

    def _check_constraints(self, layout: LayoutResult) -> bool:
        """Check if layout meets all constraints."""
        # Minimum stalls
        if layout.total_stalls < self.config.min_stalls:
            return False

        return True

    def _check_ada_compliance(self, layout: LayoutResult) -> bool:
        """
        Check if layout has space for required ADA stalls.

        Note: Actual ADA stall placement is done separately.
        This just verifies we have enough stalls to swap some for ADA.
        """
        if layout.total_stalls == 0:
            return True

        reg_ada, van_ada = required_ada_stalls(layout.total_stalls)
        total_ada = reg_ada + van_ada

        # Need at least as many stalls as ADA requires
        return layout.total_stalls >= total_ada

    def _estimate_best_angle(self) -> float:
        """Estimate the best parking angle based on site shape."""
        longest_edge = self.site.longest_edge()  # Call method

        if longest_edge is None:
            return 90  # Default to perpendicular

        # Get angle of longest edge
        edge_angle = longest_edge.angle

        # Parking is typically perpendicular to longest edge
        # or aligned with it (for angled parking)
        # Normalize to 0-90 range
        if edge_angle < 0:
            edge_angle += 180
        if edge_angle > 90:
            edge_angle -= 90

        # Find closest configured angle
        best = 90
        min_diff = 90
        for angle in self.config.angles_to_try:
            diff = abs(angle - edge_angle)
            if diff < min_diff:
                min_diff = diff
                best = angle

        return best

    def _check_limits(self) -> bool:
        """Check if optimization limits have been reached."""
        if self.iterations >= self.config.max_iterations:
            return True

        if time.time() - self.start_time >= self.config.time_limit_seconds:
            return True

        return False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def optimize_parking(
    site: Polygon,
    exclusions: List[Polygon] = None,
    objective: str = "max_stalls",
    angles: List[float] = None,
    min_stalls: int = 0
) -> OptimizationSummary:
    """
    Optimize parking layout for a site.

    This is the main entry point for simple optimization.

    Args:
        site: Site boundary polygon
        exclusions: List of exclusion polygons
        objective: "max_stalls", "max_efficiency", "min_circulation", "balanced"
        angles: List of angles to try (default: [0, 45, 60, 90])
        min_stalls: Minimum required stalls

    Returns:
        OptimizationSummary with best result

    Examples:
        >>> site = Polygon([Point(0,0), Point(200,0), Point(200,150), Point(0,150)])
        >>> summary = optimize_parking(site)
        >>> print(f"Best: {summary.max_stalls} stalls")
    """
    # Convert exclusion polygons to Exclusion objects
    excl_objects = []
    if exclusions:
        excl_objects = [Exclusion(polygon=p) for p in exclusions]

    # Parse objective
    obj_map = {
        "max_stalls": OptimizationObjective.MAX_STALLS,
        "max_efficiency": OptimizationObjective.MAX_EFFICIENCY,
        "min_circulation": OptimizationObjective.MIN_CIRCULATION,
        "balanced": OptimizationObjective.BALANCED
    }
    obj = obj_map.get(objective, OptimizationObjective.MAX_STALLS)

    # Create config
    config = OptimizationConfig(
        objective=obj,
        angles_to_try=angles or [0, 45, 60, 90],
        min_stalls=min_stalls
    )

    # Run optimization
    optimizer = ParkingOptimizer(site, excl_objects, config)
    return optimizer.optimize()


def quick_optimize(site: Polygon) -> OptimizationResult:
    """
    Quick parking optimization using greedy strategy.

    Args:
        site: Site boundary polygon

    Returns:
        Best OptimizationResult found
    """
    config = OptimizationConfig(
        strategy=OptimizationStrategy.GREEDY,
        angles_to_try=[0, 45, 60, 90]
    )

    optimizer = ParkingOptimizer(site, config=config)
    summary = optimizer.optimize()

    return summary.best_result


def compare_angles(
    site: Polygon,
    angles: List[float] = None
) -> Dict[float, int]:
    """
    Compare stall counts at different angles.

    Args:
        site: Site boundary polygon
        angles: List of angles to compare

    Returns:
        Dictionary mapping angle to stall count
    """
    angles = angles or [0, 30, 45, 60, 90]

    config = OptimizationConfig(
        strategy=OptimizationStrategy.EXHAUSTIVE,
        angles_to_try=angles
    )

    optimizer = ParkingOptimizer(site, config=config)
    summary = optimizer.optimize()

    return {r.angle: r.total_stalls for r in summary.all_results}


def optimize_with_building(
    site: Polygon,
    building_footprint: Polygon,
    min_stalls: int = 0
) -> OptimizationSummary:
    """
    Optimize parking around a building footprint.

    Args:
        site: Site boundary polygon
        building_footprint: Building footprint to exclude
        min_stalls: Minimum required parking stalls

    Returns:
        OptimizationSummary
    """
    exclusion = Exclusion(
        polygon=building_footprint,
        exclusion_type="building",
        buffer=5.0  # 5' clearance around building
    )

    config = OptimizationConfig(
        objective=OptimizationObjective.MAX_STALLS,
        min_stalls=min_stalls
    )

    optimizer = ParkingOptimizer(site, [exclusion], config)
    return optimizer.optimize()


def find_minimum_site_for_stalls(
    target_stalls: int,
    site_ratio: float = 1.5,
    stall_type: str = "standard"
) -> Tuple[float, float]:
    """
    Estimate minimum site dimensions for a target stall count.

    Args:
        target_stalls: Target number of stalls
        site_ratio: Width to length ratio
        stall_type: "standard" or "compact"

    Returns:
        Tuple of (width, length) in feet
    """
    # Typical efficiency: ~3.5 stalls per 1000 SF for standard
    # Compact: ~4.0 stalls per 1000 SF
    efficiency = 4.0 if stall_type == "compact" else 3.5

    # Required area
    required_sf = (target_stalls / efficiency) * 1000

    # Solve for dimensions given ratio
    # area = width * length
    # length = width * ratio
    # area = width * width * ratio
    # width = sqrt(area / ratio)
    width = math.sqrt(required_sf / site_ratio)
    length = width * site_ratio

    return (round(width, 0), round(length, 0))
