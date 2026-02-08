"""
optimizer/solver.py - Configuration Optimization Solver

Finds optimal configurations based on scoring criteria:
- Single objective optimization (maximize score)
- Pareto optimal solutions (multi-objective)
- Constraint satisfaction

Depends on:
- configuration.py
- scorer.py
- generator.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple, Callable, TYPE_CHECKING
import time

if TYPE_CHECKING:
    from sitefit.optimizer.configuration import SiteConfiguration
    from sitefit.optimizer.scorer import (
        ScoringWeights,
        ConfigurationScore,
        ScoringMetrics,
    )


class OptimizationObjective(Enum):
    """Optimization objectives."""
    MAXIMIZE_SCORE = "maximize_score"
    MAXIMIZE_UNITS = "maximize_units"
    MAXIMIZE_PROFIT = "maximize_profit"
    MAXIMIZE_EFFICIENCY = "maximize_efficiency"
    MINIMIZE_PARKING = "minimize_parking"
    BALANCE = "balance"


class ConstraintType(Enum):
    """Types of constraints."""
    MIN_UNITS = "min_units"
    MAX_UNITS = "max_units"
    MIN_PARKING = "min_parking"
    MAX_PARKING = "max_parking"
    MIN_HEIGHT = "min_height"
    MAX_HEIGHT = "max_height"
    MIN_COVERAGE = "min_coverage"
    MAX_COVERAGE = "max_coverage"
    MIN_FAR = "min_far"
    MAX_FAR = "max_far"
    REQUIRE_COMPLIANCE = "require_compliance"


@dataclass
class Constraint:
    """
    A constraint for optimization.
    """
    constraint_type: ConstraintType
    value: Any
    weight: float = 1.0  # How much to penalize violations

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type.value,
            "value": self.value,
            "weight": self.weight,
        }


@dataclass
class SolverConfig:
    """
    Configuration for the solver.
    """
    # Objectives
    objective: OptimizationObjective = OptimizationObjective.MAXIMIZE_SCORE

    # Constraints
    constraints: List[Constraint] = field(default_factory=list)

    # Search parameters
    max_iterations: int = 1000
    time_limit_seconds: float = 30.0
    early_stop_threshold: float = 0.01  # Stop if improvement < this

    # Result selection
    top_n: int = 10

    # Options
    include_non_compliant: bool = False
    allow_partial_solutions: bool = True

    def add_constraint(
        self,
        constraint_type: ConstraintType,
        value: Any,
        weight: float = 1.0
    ) -> None:
        """Add a constraint."""
        self.constraints.append(Constraint(constraint_type, value, weight))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "objective": self.objective.value,
            "constraints": [c.to_dict() for c in self.constraints],
            "max_iterations": self.max_iterations,
            "time_limit_seconds": self.time_limit_seconds,
            "top_n": self.top_n,
        }


@dataclass
class OptimizationResult:
    """
    Result from optimization.
    """
    best_configuration: Optional[SiteConfiguration] = None
    best_score: Optional[ConfigurationScore] = None
    top_configurations: List[Tuple[SiteConfiguration, ConfigurationScore]] = field(
        default_factory=list
    )
    pareto_front: List[Tuple[SiteConfiguration, ConfigurationScore]] = field(
        default_factory=list
    )

    # Statistics
    configurations_evaluated: int = 0
    configurations_valid: int = 0
    iterations: int = 0
    time_elapsed_seconds: float = 0.0

    # Metadata
    objective: Optional[str] = None
    constraints_satisfied: bool = True
    constraint_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "best_configuration": self.best_configuration.to_dict() if self.best_configuration else None,
            "best_score": self.best_score.to_dict() if self.best_score else None,
            "top_count": len(self.top_configurations),
            "pareto_count": len(self.pareto_front),
            "statistics": {
                "evaluated": self.configurations_evaluated,
                "valid": self.configurations_valid,
                "iterations": self.iterations,
                "time_seconds": round(self.time_elapsed_seconds, 2),
            },
            "constraints_satisfied": self.constraints_satisfied,
            "constraint_violations": self.constraint_violations,
        }


# =============================================================================
# OPTIMIZATION FUNCTIONS
# =============================================================================

def find_optimal_configuration(
    configurations: List[SiteConfiguration],
    solver_config: Optional[SolverConfig] = None,
    weights: Optional[ScoringWeights] = None,
) -> OptimizationResult:
    """
    Find the optimal configuration from a list.

    Args:
        configurations: List of configurations to evaluate
        solver_config: Solver configuration
        weights: Scoring weights

    Returns:
        OptimizationResult with best configuration
    """
    from sitefit.optimizer.scorer import score_configuration, rank_configurations

    start_time = time.time()

    if solver_config is None:
        solver_config = SolverConfig()

    result = OptimizationResult(
        objective=solver_config.objective.value,
    )

    if not configurations:
        return result

    # Score all configurations
    scores = rank_configurations(configurations, weights)
    result.configurations_evaluated = len(configurations)

    # Filter by constraints
    valid_configs = []
    for config, score in zip(configurations, scores):
        if config.id != score.configuration_id:
            # Find matching score
            for s in scores:
                if s.configuration_id == config.id:
                    score = s
                    break

        is_valid, violations = _check_constraints(
            config, score, solver_config.constraints)

        if is_valid or solver_config.include_non_compliant:
            valid_configs.append((config, score, is_valid, violations))
        else:
            result.constraint_violations.extend(
                [f"{config.name}: {v}" for v in violations]
            )

    result.configurations_valid = sum(1 for _, _, v, _ in valid_configs if v)

    if not valid_configs:
        result.constraints_satisfied = False
        result.time_elapsed_seconds = time.time() - start_time
        return result

    # Sort by objective
    sorted_configs = _sort_by_objective(valid_configs, solver_config.objective)

    # Select best
    best_config, best_score, _, _ = sorted_configs[0]
    result.best_configuration = best_config
    result.best_score = best_score

    # Get top N
    result.top_configurations = [
        (config, score) for config, score, _, _ in sorted_configs[:solver_config.top_n]
    ]

    result.iterations = 1
    result.time_elapsed_seconds = time.time() - start_time

    return result


def find_pareto_optimal(
    configurations: List[SiteConfiguration],
    objectives: Optional[List[str]] = None,
    weights: Optional[ScoringWeights] = None,
) -> OptimizationResult:
    """
    Find Pareto optimal configurations (multi-objective).

    Args:
        configurations: List of configurations
        objectives: List of objectives to optimize
        weights: Scoring weights

    Returns:
        OptimizationResult with Pareto front
    """
    from sitefit.optimizer.scorer import score_configuration, calculate_metrics

    start_time = time.time()

    if objectives is None:
        objectives = ["units", "parking", "efficiency", "profit"]

    result = OptimizationResult(
        objective="pareto_optimal",
    )

    if not configurations:
        return result

    # Score all configurations
    scored = []
    for config in configurations:
        score = score_configuration(config, weights)
        metrics = score.metrics

        # Extract objective values
        obj_values = _get_objective_values(metrics, objectives)
        scored.append((config, score, obj_values))

    result.configurations_evaluated = len(configurations)

    # Find Pareto front
    pareto_front = _compute_pareto_front(scored, objectives)

    result.pareto_front = [(config, score)
                           for config, score, _ in pareto_front]
    result.configurations_valid = len(pareto_front)

    if pareto_front:
        # Best is first in Pareto front (arbitrary but consistent)
        result.best_configuration = pareto_front[0][0]
        result.best_score = pareto_front[0][1]
        result.top_configurations = result.pareto_front[:10]

    result.time_elapsed_seconds = time.time() - start_time

    return result


def solve_with_constraints(
    configurations: List[SiteConfiguration],
    constraints: List[Constraint],
    weights: Optional[ScoringWeights] = None,
    max_iterations: int = 100,
) -> OptimizationResult:
    """
    Find best configuration satisfying all constraints.

    Args:
        configurations: List of configurations
        constraints: List of constraints to satisfy
        weights: Scoring weights
        max_iterations: Maximum iterations

    Returns:
        OptimizationResult
    """
    solver_config = SolverConfig(
        constraints=constraints,
        max_iterations=max_iterations,
        include_non_compliant=False,
    )

    return find_optimal_configuration(configurations, solver_config, weights)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _check_constraints(
    config: SiteConfiguration,
    score: ConfigurationScore,
    constraints: List[Constraint]
) -> Tuple[bool, List[str]]:
    """Check if configuration satisfies all constraints."""
    violations = []
    metrics = score.metrics

    # Ensure results are calculated
    if config.result is None:
        config.calculate_results()

    for constraint in constraints:
        ct = constraint.constraint_type
        value = constraint.value

        if ct == ConstraintType.MIN_UNITS:
            if metrics.total_units < value:
                violations.append(f"Units {metrics.total_units} < min {value}")

        elif ct == ConstraintType.MAX_UNITS:
            if metrics.total_units > value:
                violations.append(f"Units {metrics.total_units} > max {value}")

        elif ct == ConstraintType.MIN_PARKING:
            if metrics.total_parking < value:
                violations.append(
                    f"Parking {metrics.total_parking} < min {value}")

        elif ct == ConstraintType.MAX_PARKING:
            if metrics.total_parking > value:
                violations.append(
                    f"Parking {metrics.total_parking} > max {value}")

        elif ct == ConstraintType.MIN_HEIGHT:
            if metrics.max_height < value:
                violations.append(f"Height {metrics.max_height} < min {value}")

        elif ct == ConstraintType.MAX_HEIGHT:
            if metrics.max_height > value:
                violations.append(f"Height {metrics.max_height} > max {value}")

        elif ct == ConstraintType.MIN_COVERAGE:
            if metrics.site_coverage < value:
                violations.append(
                    f"Coverage {metrics.site_coverage:.2f} < min {value}")

        elif ct == ConstraintType.MAX_COVERAGE:
            if metrics.site_coverage > value:
                violations.append(
                    f"Coverage {metrics.site_coverage:.2f} > max {value}")

        elif ct == ConstraintType.MIN_FAR:
            if metrics.far < value:
                violations.append(f"FAR {metrics.far:.2f} < min {value}")

        elif ct == ConstraintType.MAX_FAR:
            if metrics.far > value:
                violations.append(f"FAR {metrics.far:.2f} > max {value}")

        elif ct == ConstraintType.REQUIRE_COMPLIANCE:
            if value and not metrics.is_compliant:
                violations.append(
                    f"Non-compliant: {metrics.compliance_issues}")

    return len(violations) == 0, violations


def _sort_by_objective(
    configs: List[Tuple[SiteConfiguration, ConfigurationScore, bool, List[str]]],
    objective: OptimizationObjective
) -> List[Tuple[SiteConfiguration, ConfigurationScore, bool, List[str]]]:
    """Sort configurations by objective."""
    if objective == OptimizationObjective.MAXIMIZE_SCORE:
        return sorted(configs, key=lambda x: x[1].total_score, reverse=True)

    elif objective == OptimizationObjective.MAXIMIZE_UNITS:
        return sorted(configs, key=lambda x: x[1].metrics.total_units, reverse=True)

    elif objective == OptimizationObjective.MAXIMIZE_PROFIT:
        return sorted(configs, key=lambda x: x[1].metrics.profit_margin, reverse=True)

    elif objective == OptimizationObjective.MAXIMIZE_EFFICIENCY:
        return sorted(configs, key=lambda x: x[1].building_efficiency_score, reverse=True)

    elif objective == OptimizationObjective.MINIMIZE_PARKING:
        # Minimize parking surplus while staying compliant
        return sorted(configs, key=lambda x: abs(x[1].metrics.parking_surplus))

    elif objective == OptimizationObjective.BALANCE:
        # Balance units and efficiency
        return sorted(
            configs,
            key=lambda x: x[1].unit_count_score * 0.5 +
            x[1].building_efficiency_score * 0.5,
            reverse=True
        )

    return configs


def _get_objective_values(
    metrics: ScoringMetrics,
    objectives: List[str]
) -> Dict[str, float]:
    """Get objective values from metrics."""
    values = {}

    for obj in objectives:
        if obj == "units":
            values[obj] = float(metrics.total_units)
        elif obj == "parking":
            values[obj] = float(metrics.total_parking)
        elif obj == "efficiency":
            values[obj] = metrics.building_efficiency
        elif obj == "profit":
            values[obj] = metrics.profit_margin
        elif obj == "far":
            values[obj] = metrics.far
        elif obj == "coverage":
            values[obj] = metrics.site_coverage
        elif obj == "revenue":
            values[obj] = metrics.annual_revenue

    return values


def _compute_pareto_front(
    scored: List[Tuple[SiteConfiguration, ConfigurationScore, Dict[str, float]]],
    objectives: List[str]
) -> List[Tuple[SiteConfiguration, ConfigurationScore, Dict[str, float]]]:
    """Compute Pareto front from scored configurations."""
    pareto = []

    for i, (config1, score1, vals1) in enumerate(scored):
        is_dominated = False

        for j, (config2, score2, vals2) in enumerate(scored):
            if i == j:
                continue

            # Check if config2 dominates config1
            if _dominates(vals2, vals1, objectives):
                is_dominated = True
                break

        if not is_dominated:
            pareto.append((config1, score1, vals1))

    return pareto


def _dominates(vals1: Dict[str, float], vals2: Dict[str, float], objectives: List[str]) -> bool:
    """Check if vals1 dominates vals2 (better or equal in all, strictly better in at least one)."""
    at_least_one_better = False

    for obj in objectives:
        v1 = vals1.get(obj, 0)
        v2 = vals2.get(obj, 0)

        if v1 < v2:  # Assuming maximization
            return False
        if v1 > v2:
            at_least_one_better = True

    return at_least_one_better


# =============================================================================
# OPTIMIZATION UTILITIES
# =============================================================================

def get_optimization_summary(result: OptimizationResult) -> Dict[str, Any]:
    """
    Get a summary of optimization results.

    Args:
        result: Optimization result

    Returns:
        Summary dictionary
    """
    summary = {
        "success": result.best_configuration is not None,
        "objective": result.objective,
        "statistics": {
            "evaluated": result.configurations_evaluated,
            "valid": result.configurations_valid,
            "time_seconds": round(result.time_elapsed_seconds, 2),
        },
        "constraints_satisfied": result.constraints_satisfied,
    }

    if result.best_configuration:
        summary["best"] = {
            "id": result.best_configuration.id,
            "name": result.best_configuration.name,
            "score": round(result.best_score.total_score, 1) if result.best_score else 0,
            "units": result.best_score.metrics.total_units if result.best_score else 0,
            "parking": result.best_score.metrics.total_parking if result.best_score else 0,
        }

    summary["top_count"] = len(result.top_configurations)
    summary["pareto_count"] = len(result.pareto_front)

    return summary


def compare_optimization_results(
    results: List[OptimizationResult]
) -> Dict[str, Any]:
    """
    Compare multiple optimization results.

    Args:
        results: List of optimization results

    Returns:
        Comparison summary
    """
    valid_results = [r for r in results if r.best_configuration is not None]

    if not valid_results:
        return {"error": "No valid results to compare"}

    # Find best overall
    best = max(
        valid_results,
        key=lambda r: r.best_score.total_score if r.best_score else 0
    )

    # Find best by units
    most_units = max(
        valid_results,
        key=lambda r: r.best_score.metrics.total_units if r.best_score else 0
    )

    # Find fastest
    fastest = min(valid_results, key=lambda r: r.time_elapsed_seconds)

    return {
        "count": len(results),
        "valid_count": len(valid_results),
        "best_overall": {
            "objective": best.objective,
            "score": round(best.best_score.total_score, 1) if best.best_score else 0,
            "units": best.best_score.metrics.total_units if best.best_score else 0,
        },
        "most_units": {
            "objective": most_units.objective,
            "units": most_units.best_score.metrics.total_units if most_units.best_score else 0,
        },
        "fastest": {
            "objective": fastest.objective,
            "time_seconds": round(fastest.time_elapsed_seconds, 2),
        },
    }


def create_solver_for_residential(
    min_units: int = 50,
    max_height: float = 100.0,
    require_compliance: bool = True,
) -> SolverConfig:
    """
    Create a solver config optimized for residential development.

    Args:
        min_units: Minimum unit count
        max_height: Maximum building height
        require_compliance: Require zoning compliance

    Returns:
        SolverConfig for residential optimization
    """
    config = SolverConfig(
        objective=OptimizationObjective.MAXIMIZE_UNITS,
        max_iterations=500,
        time_limit_seconds=60.0,
        top_n=10,
    )

    config.add_constraint(ConstraintType.MIN_UNITS, min_units)
    config.add_constraint(ConstraintType.MAX_HEIGHT, max_height)

    if require_compliance:
        config.add_constraint(ConstraintType.REQUIRE_COMPLIANCE, True)

    return config


def create_solver_for_commercial(
    min_parking: int = 100,
    max_coverage: float = 0.6,
) -> SolverConfig:
    """
    Create a solver config optimized for commercial development.

    Args:
        min_parking: Minimum parking spaces
        max_coverage: Maximum site coverage

    Returns:
        SolverConfig for commercial optimization
    """
    config = SolverConfig(
        objective=OptimizationObjective.MAXIMIZE_EFFICIENCY,
        max_iterations=200,
        time_limit_seconds=30.0,
        top_n=5,
    )

    config.add_constraint(ConstraintType.MIN_PARKING, min_parking)
    config.add_constraint(ConstraintType.MAX_COVERAGE, max_coverage)

    return config


def create_balanced_solver() -> SolverConfig:
    """
    Create a solver config for balanced optimization.

    Returns:
        SolverConfig with balanced objectives
    """
    return SolverConfig(
        objective=OptimizationObjective.BALANCE,
        max_iterations=300,
        time_limit_seconds=45.0,
        top_n=10,
        include_non_compliant=False,
    )
