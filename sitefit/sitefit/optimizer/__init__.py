"""
optimizer - Multi-Configuration Testing & Optimization

This package provides site configuration optimization capabilities:
- configuration.py: Define site configurations combining parking + building
- scorer.py: Score configurations by various metrics  
- generator.py: Generate configuration variations
- solver.py: Find optimal configurations
"""

from .configuration import (
    SiteConfiguration,
    SiteElement,
    ParkingElement,
    BuildingElement,
    OpenSpaceElement,
    ConfigurationResult,
    create_configuration,
    validate_configuration,
    configuration_to_dict,
)

from .scorer import (
    ScoringWeights,
    ScoringMetrics,
    ConfigurationScore,
    score_configuration,
    rank_configurations,
    get_default_weights,
    get_unit_focused_weights,
    get_efficiency_focused_weights,
    get_profit_focused_weights,
)

from .generator import (
    GeneratorConfig,
    VariationParameter,
    generate_configurations,
    generate_parking_variations,
    generate_building_variations,
    generate_mixed_variations,
)

from .solver import (
    OptimizationResult,
    SolverConfig,
    find_optimal_configuration,
    find_pareto_optimal,
    solve_with_constraints,
)

__all__ = [
    # Configuration
    "SiteConfiguration",
    "SiteElement",
    "ParkingElement",
    "BuildingElement",
    "OpenSpaceElement",
    "ConfigurationResult",
    "create_configuration",
    "validate_configuration",
    "configuration_to_dict",
    # Scorer
    "ScoringWeights",
    "ScoringMetrics",
    "ConfigurationScore",
    "score_configuration",
    "rank_configurations",
    "get_default_weights",
    "get_unit_focused_weights",
    "get_efficiency_focused_weights",
    "get_profit_focused_weights",
    # Generator
    "GeneratorConfig",
    "VariationParameter",
    "generate_configurations",
    "generate_parking_variations",
    "generate_building_variations",
    "generate_mixed_variations",
    # Solver
    "OptimizationResult",
    "SolverConfig",
    "find_optimal_configuration",
    "find_pareto_optimal",
    "solve_with_constraints",
]
