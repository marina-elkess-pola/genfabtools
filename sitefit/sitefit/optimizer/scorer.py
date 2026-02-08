"""
optimizer/scorer.py - Configuration Scoring Module

Scores site configurations based on multiple criteria:
- Unit count / density
- Parking efficiency
- Compliance (zoning, parking, height)
- Financial metrics (revenue, costs, profit)
- Site utilization efficiency

Depends on:
- configuration.py
- constraints/* modules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from sitefit.optimizer.configuration import SiteConfiguration


class ScoringCriteria(Enum):
    """Criteria used for scoring configurations."""
    UNIT_COUNT = "unit_count"
    UNIT_DENSITY = "unit_density"
    PARKING_EFFICIENCY = "parking_efficiency"
    PARKING_SURPLUS = "parking_surplus"
    SITE_COVERAGE = "site_coverage"
    FAR = "far"
    BUILDING_EFFICIENCY = "building_efficiency"
    COMPLIANCE = "compliance"
    REVENUE_POTENTIAL = "revenue_potential"
    CONSTRUCTION_COST = "construction_cost"
    PROFIT_MARGIN = "profit_margin"
    OPEN_SPACE_RATIO = "open_space_ratio"


@dataclass
class ScoringWeights:
    """
    Weights for different scoring criteria.

    All weights should sum to 1.0 for normalized scoring.
    """
    unit_count: float = 0.20
    unit_density: float = 0.10
    parking_efficiency: float = 0.10
    parking_surplus: float = 0.05
    site_coverage: float = 0.05
    far: float = 0.10
    building_efficiency: float = 0.10
    compliance: float = 0.15
    revenue_potential: float = 0.05
    profit_margin: float = 0.05
    open_space_ratio: float = 0.05

    def __post_init__(self):
        """Validate weights sum to ~1.0."""
        total = self.total_weight
        if abs(total - 1.0) > 0.01:
            # Normalize weights
            self._normalize()

    @property
    def total_weight(self) -> float:
        """Get sum of all weights."""
        return (
            self.unit_count +
            self.unit_density +
            self.parking_efficiency +
            self.parking_surplus +
            self.site_coverage +
            self.far +
            self.building_efficiency +
            self.compliance +
            self.revenue_potential +
            self.profit_margin +
            self.open_space_ratio
        )

    def _normalize(self):
        """Normalize weights to sum to 1.0."""
        total = self.total_weight
        if total > 0:
            self.unit_count /= total
            self.unit_density /= total
            self.parking_efficiency /= total
            self.parking_surplus /= total
            self.site_coverage /= total
            self.far /= total
            self.building_efficiency /= total
            self.compliance /= total
            self.revenue_potential /= total
            self.profit_margin /= total
            self.open_space_ratio /= total

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "unit_count": round(self.unit_count, 3),
            "unit_density": round(self.unit_density, 3),
            "parking_efficiency": round(self.parking_efficiency, 3),
            "parking_surplus": round(self.parking_surplus, 3),
            "site_coverage": round(self.site_coverage, 3),
            "far": round(self.far, 3),
            "building_efficiency": round(self.building_efficiency, 3),
            "compliance": round(self.compliance, 3),
            "revenue_potential": round(self.revenue_potential, 3),
            "profit_margin": round(self.profit_margin, 3),
            "open_space_ratio": round(self.open_space_ratio, 3),
        }


@dataclass
class FinancialAssumptions:
    """
    Financial assumptions for scoring.

    All monetary values in dollars.
    """
    # Revenue per unit type (annual)
    rent_studio: float = 18000  # $1,500/month
    rent_1br: float = 24000  # $2,000/month
    rent_2br: float = 30000  # $2,500/month
    rent_3br: float = 36000  # $3,000/month

    # Revenue per SF (annual)
    rent_retail_psf: float = 30.0
    rent_office_psf: float = 25.0

    # Construction costs per SF
    cost_residential_psf: float = 250.0
    cost_parking_surface_psf: float = 50.0
    cost_parking_structure_psf: float = 150.0
    cost_parking_underground_psf: float = 200.0

    # Parking revenue (annual per space)
    parking_revenue_surface: float = 600  # $50/month
    parking_revenue_structure: float = 1200  # $100/month

    # Operating expense ratio
    opex_ratio: float = 0.35  # 35% of revenue

    # Cap rate for valuation
    cap_rate: float = 0.05  # 5%

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "rent_studio": self.rent_studio,
            "rent_1br": self.rent_1br,
            "rent_2br": self.rent_2br,
            "rent_3br": self.rent_3br,
            "rent_retail_psf": self.rent_retail_psf,
            "rent_office_psf": self.rent_office_psf,
            "cost_residential_psf": self.cost_residential_psf,
            "cost_parking_surface_psf": self.cost_parking_surface_psf,
            "cost_parking_structure_psf": self.cost_parking_structure_psf,
            "cost_parking_underground_psf": self.cost_parking_underground_psf,
            "opex_ratio": self.opex_ratio,
            "cap_rate": self.cap_rate,
        }


@dataclass
class ScoringMetrics:
    """
    Raw metrics calculated from a configuration.

    These are the base values before normalization and weighting.
    """
    # Unit metrics
    total_units: int = 0
    units_per_acre: float = 0.0
    avg_unit_size: float = 0.0

    # Parking metrics
    total_parking: int = 0
    required_parking: int = 0
    parking_surplus: int = 0
    parking_ratio: float = 0.0
    spaces_per_1000sf: float = 0.0

    # Building metrics
    total_gross_area: float = 0.0
    total_net_area: float = 0.0
    building_efficiency: float = 0.0  # Net / Gross
    floor_count: int = 0
    max_height: float = 0.0

    # Site metrics
    site_area: float = 0.0
    buildable_area: float = 0.0
    built_area: float = 0.0
    site_coverage: float = 0.0  # Built / Site
    far: float = 0.0  # Gross / Site
    open_space_area: float = 0.0
    open_space_ratio: float = 0.0  # Open / Site

    # Compliance
    is_compliant: bool = True
    compliance_issues: List[str] = field(default_factory=list)

    # Financial
    annual_revenue: float = 0.0
    construction_cost: float = 0.0
    net_operating_income: float = 0.0
    project_value: float = 0.0
    profit_margin: float = 0.0  # (Value - Cost) / Cost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "units": {
                "total": self.total_units,
                "per_acre": round(self.units_per_acre, 1),
                "avg_size": round(self.avg_unit_size, 0),
            },
            "parking": {
                "total": self.total_parking,
                "required": self.required_parking,
                "surplus": self.parking_surplus,
                "ratio": round(self.parking_ratio, 2),
                "per_1000sf": round(self.spaces_per_1000sf, 2),
            },
            "building": {
                "gross_area": round(self.total_gross_area, 0),
                "net_area": round(self.total_net_area, 0),
                "efficiency": round(self.building_efficiency, 3),
                "floors": self.floor_count,
                "max_height": round(self.max_height, 0),
            },
            "site": {
                "area": round(self.site_area, 0),
                "buildable_area": round(self.buildable_area, 0),
                "coverage": round(self.site_coverage, 3),
                "far": round(self.far, 2),
                "open_space_ratio": round(self.open_space_ratio, 3),
            },
            "compliance": {
                "is_compliant": self.is_compliant,
                "issues": self.compliance_issues,
            },
            "financial": {
                "annual_revenue": round(self.annual_revenue, 0),
                "construction_cost": round(self.construction_cost, 0),
                "noi": round(self.net_operating_income, 0),
                "value": round(self.project_value, 0),
                "profit_margin": round(self.profit_margin, 3),
            },
        }


@dataclass
class ConfigurationScore:
    """
    Complete score for a configuration.

    Includes raw metrics, normalized scores, and final weighted score.
    """
    configuration_id: str
    configuration_name: str
    metrics: ScoringMetrics

    # Normalized scores (0-100)
    unit_count_score: float = 0.0
    unit_density_score: float = 0.0
    parking_efficiency_score: float = 0.0
    parking_surplus_score: float = 0.0
    site_coverage_score: float = 0.0
    far_score: float = 0.0
    building_efficiency_score: float = 0.0
    compliance_score: float = 0.0
    revenue_score: float = 0.0
    profit_score: float = 0.0
    open_space_score: float = 0.0

    # Final weighted score
    total_score: float = 0.0

    # Ranking
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "configuration_id": self.configuration_id,
            "configuration_name": self.configuration_name,
            "total_score": round(self.total_score, 1),
            "rank": self.rank,
            "component_scores": {
                "unit_count": round(self.unit_count_score, 1),
                "unit_density": round(self.unit_density_score, 1),
                "parking_efficiency": round(self.parking_efficiency_score, 1),
                "parking_surplus": round(self.parking_surplus_score, 1),
                "site_coverage": round(self.site_coverage_score, 1),
                "far": round(self.far_score, 1),
                "building_efficiency": round(self.building_efficiency_score, 1),
                "compliance": round(self.compliance_score, 1),
                "revenue": round(self.revenue_score, 1),
                "profit": round(self.profit_score, 1),
                "open_space": round(self.open_space_score, 1),
            },
            "metrics": self.metrics.to_dict(),
        }


# =============================================================================
# WEIGHT PRESETS
# =============================================================================

def get_default_weights() -> ScoringWeights:
    """
    Get balanced default weights.

    Returns:
        ScoringWeights with balanced distribution
    """
    return ScoringWeights()


def get_unit_focused_weights() -> ScoringWeights:
    """
    Get weights focused on maximizing unit count.

    Returns:
        ScoringWeights emphasizing unit metrics
    """
    return ScoringWeights(
        unit_count=0.35,
        unit_density=0.20,
        parking_efficiency=0.05,
        parking_surplus=0.05,
        site_coverage=0.05,
        far=0.05,
        building_efficiency=0.05,
        compliance=0.10,
        revenue_potential=0.05,
        profit_margin=0.02,
        open_space_ratio=0.03,
    )


def get_efficiency_focused_weights() -> ScoringWeights:
    """
    Get weights focused on site efficiency.

    Returns:
        ScoringWeights emphasizing efficiency metrics
    """
    return ScoringWeights(
        unit_count=0.10,
        unit_density=0.15,
        parking_efficiency=0.15,
        parking_surplus=0.05,
        site_coverage=0.10,
        far=0.15,
        building_efficiency=0.15,
        compliance=0.05,
        revenue_potential=0.03,
        profit_margin=0.02,
        open_space_ratio=0.05,
    )


def get_profit_focused_weights() -> ScoringWeights:
    """
    Get weights focused on financial returns.

    Returns:
        ScoringWeights emphasizing financial metrics
    """
    return ScoringWeights(
        unit_count=0.10,
        unit_density=0.05,
        parking_efficiency=0.05,
        parking_surplus=0.05,
        site_coverage=0.05,
        far=0.10,
        building_efficiency=0.10,
        compliance=0.10,
        revenue_potential=0.20,
        profit_margin=0.15,
        open_space_ratio=0.05,
    )


def get_compliance_focused_weights() -> ScoringWeights:
    """
    Get weights focused on regulatory compliance.

    Returns:
        ScoringWeights emphasizing compliance
    """
    return ScoringWeights(
        unit_count=0.05,
        unit_density=0.05,
        parking_efficiency=0.05,
        parking_surplus=0.15,
        site_coverage=0.10,
        far=0.10,
        building_efficiency=0.05,
        compliance=0.30,
        revenue_potential=0.05,
        profit_margin=0.05,
        open_space_ratio=0.05,
    )


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def calculate_metrics(
    config: SiteConfiguration,
    financial: Optional[FinancialAssumptions] = None
) -> ScoringMetrics:
    """
    Calculate raw metrics for a configuration.

    Args:
        config: Site configuration
        financial: Financial assumptions

    Returns:
        ScoringMetrics with calculated values
    """
    if financial is None:
        financial = FinancialAssumptions()

    # Ensure results are calculated
    if config.result is None:
        config.calculate_results()

    result = config.result
    metrics = ScoringMetrics()

    # Site metrics
    metrics.site_area = config.site_area
    metrics.buildable_area = config.buildable_area

    if result:
        # From configuration result
        metrics.built_area = result.built_area
        metrics.site_coverage = result.site_coverage
        metrics.far = result.far
        metrics.open_space_area = result.open_space_area
        metrics.open_space_ratio = result.open_space_ratio

        # Building metrics
        metrics.total_gross_area = result.total_gross_area
        metrics.total_net_area = result.total_net_area
        metrics.floor_count = result.total_floors
        metrics.max_height = result.max_height

        if metrics.total_gross_area > 0:
            metrics.building_efficiency = metrics.total_net_area / metrics.total_gross_area

        # Unit metrics
        metrics.total_units = result.total_units
        if metrics.site_area > 0:
            metrics.units_per_acre = metrics.total_units / \
                (metrics.site_area / 43560)
        if metrics.total_units > 0 and metrics.total_net_area > 0:
            metrics.avg_unit_size = metrics.total_net_area / metrics.total_units

        # Parking metrics
        metrics.total_parking = result.total_parking_spaces
        metrics.required_parking = result.required_parking_spaces
        metrics.parking_surplus = result.parking_surplus
        if metrics.total_units > 0:
            metrics.parking_ratio = metrics.total_parking / metrics.total_units
        if metrics.total_gross_area > 0:
            metrics.spaces_per_1000sf = (
                metrics.total_parking / metrics.total_gross_area) * 1000

        # Compliance
        metrics.is_compliant = (
            result.zoning_compliant and
            result.parking_compliant and
            result.height_compliant and
            result.setback_compliant
        )
        metrics.compliance_issues = result.compliance_issues.copy()

    # Calculate financials
    _calculate_financials(metrics, config, financial)

    return metrics


def _calculate_financials(
    metrics: ScoringMetrics,
    config: SiteConfiguration,
    financial: FinancialAssumptions
) -> None:
    """Calculate financial metrics."""
    # Revenue from units (simplified - assume all 1BR for now)
    unit_revenue = metrics.total_units * financial.rent_1br

    # Revenue from parking
    parking_revenue = 0.0
    for parking in config.parking_areas:
        from sitefit.optimizer.configuration import ElementType
        if parking.element_type == ElementType.PARKING_SURFACE:
            parking_revenue += parking.total_spaces * financial.parking_revenue_surface
        else:
            parking_revenue += parking.total_spaces * financial.parking_revenue_structure

    # Revenue from commercial (if any)
    commercial_revenue = 0.0
    for building in config.buildings:
        commercial_revenue += building.retail_sf * financial.rent_retail_psf
        commercial_revenue += building.office_sf * financial.rent_office_psf

    metrics.annual_revenue = unit_revenue + parking_revenue + commercial_revenue

    # Construction costs
    building_cost = metrics.total_gross_area * financial.cost_residential_psf

    parking_cost = 0.0
    for parking in config.parking_areas:
        from sitefit.optimizer.configuration import ElementType
        area = parking.footprint.area * parking.levels
        if parking.element_type == ElementType.PARKING_SURFACE:
            parking_cost += area * financial.cost_parking_surface_psf
        elif parking.element_type == ElementType.PARKING_UNDERGROUND:
            parking_cost += area * financial.cost_parking_underground_psf
        else:
            parking_cost += area * financial.cost_parking_structure_psf

    metrics.construction_cost = building_cost + parking_cost

    # NOI and value
    opex = metrics.annual_revenue * financial.opex_ratio
    metrics.net_operating_income = metrics.annual_revenue - opex

    if financial.cap_rate > 0:
        metrics.project_value = metrics.net_operating_income / financial.cap_rate

    # Profit margin
    if metrics.construction_cost > 0:
        metrics.profit_margin = (
            metrics.project_value - metrics.construction_cost) / metrics.construction_cost


def score_configuration(
    config: SiteConfiguration,
    weights: Optional[ScoringWeights] = None,
    financial: Optional[FinancialAssumptions] = None,
    benchmarks: Optional[Dict[str, float]] = None
) -> ConfigurationScore:
    """
    Score a site configuration.

    Args:
        config: Site configuration to score
        weights: Scoring weights
        financial: Financial assumptions
        benchmarks: Benchmark values for normalization

    Returns:
        ConfigurationScore with all scores
    """
    if weights is None:
        weights = get_default_weights()

    if benchmarks is None:
        benchmarks = _get_default_benchmarks()

    # Calculate metrics
    metrics = calculate_metrics(config, financial)

    # Create score object
    score = ConfigurationScore(
        configuration_id=config.id,
        configuration_name=config.name,
        metrics=metrics,
    )

    # Calculate component scores (0-100)
    score.unit_count_score = _score_unit_count(metrics.total_units, benchmarks)
    score.unit_density_score = _score_unit_density(
        metrics.units_per_acre, benchmarks)
    score.parking_efficiency_score = _score_parking_efficiency(
        metrics.spaces_per_1000sf, benchmarks)
    score.parking_surplus_score = _score_parking_surplus(
        metrics.parking_surplus, metrics.required_parking)
    score.site_coverage_score = _score_site_coverage(
        metrics.site_coverage, benchmarks)
    score.far_score = _score_far(metrics.far, benchmarks)
    score.building_efficiency_score = _score_building_efficiency(
        metrics.building_efficiency, benchmarks)
    score.compliance_score = _score_compliance(
        metrics.is_compliant, len(metrics.compliance_issues))
    score.revenue_score = _score_revenue(metrics.annual_revenue, benchmarks)
    score.profit_score = _score_profit(metrics.profit_margin, benchmarks)
    score.open_space_score = _score_open_space(
        metrics.open_space_ratio, benchmarks)

    # Calculate weighted total score
    score.total_score = (
        score.unit_count_score * weights.unit_count +
        score.unit_density_score * weights.unit_density +
        score.parking_efficiency_score * weights.parking_efficiency +
        score.parking_surplus_score * weights.parking_surplus +
        score.site_coverage_score * weights.site_coverage +
        score.far_score * weights.far +
        score.building_efficiency_score * weights.building_efficiency +
        score.compliance_score * weights.compliance +
        score.revenue_score * weights.revenue_potential +
        score.profit_score * weights.profit_margin +
        score.open_space_score * weights.open_space_ratio
    )

    return score


def rank_configurations(
    configs: List[SiteConfiguration],
    weights: Optional[ScoringWeights] = None,
    financial: Optional[FinancialAssumptions] = None
) -> List[ConfigurationScore]:
    """
    Score and rank multiple configurations.

    Args:
        configs: List of configurations
        weights: Scoring weights
        financial: Financial assumptions

    Returns:
        List of ConfigurationScore sorted by total score (highest first)
    """
    # Calculate benchmarks across all configs
    benchmarks = _calculate_benchmarks(configs, financial)

    # Score all configurations
    scores = [
        score_configuration(config, weights, financial, benchmarks)
        for config in configs
    ]

    # Sort by total score (descending)
    scores.sort(key=lambda s: s.total_score, reverse=True)

    # Assign ranks
    for i, score in enumerate(scores):
        score.rank = i + 1

    return scores


# =============================================================================
# SCORING HELPER FUNCTIONS
# =============================================================================

def _get_default_benchmarks() -> Dict[str, float]:
    """Get default benchmark values."""
    return {
        "max_units": 200,
        "max_density": 100,  # units per acre
        "optimal_parking_per_1000sf": 3.0,
        "optimal_coverage": 0.5,
        "max_far": 4.0,
        "optimal_efficiency": 0.85,
        "max_revenue": 5_000_000,
        "optimal_profit_margin": 0.30,
        "optimal_open_space": 0.15,
    }


def _calculate_benchmarks(
    configs: List[SiteConfiguration],
    financial: Optional[FinancialAssumptions] = None
) -> Dict[str, float]:
    """Calculate benchmarks from configuration list."""
    benchmarks = _get_default_benchmarks()

    if not configs:
        return benchmarks

    # Calculate metrics for all
    all_metrics = [calculate_metrics(c, financial) for c in configs]

    # Update benchmarks with actual values
    max_units = max((m.total_units for m in all_metrics), default=100)
    benchmarks["max_units"] = max(max_units, 10)  # Minimum 10 for scaling

    max_density = max((m.units_per_acre for m in all_metrics), default=50)
    benchmarks["max_density"] = max(max_density, 10)

    max_revenue = max(
        (m.annual_revenue for m in all_metrics), default=1_000_000)
    benchmarks["max_revenue"] = max(max_revenue, 100_000)

    max_far = max((m.far for m in all_metrics), default=2.0)
    benchmarks["max_far"] = max(max_far, 0.5)

    return benchmarks


def _score_unit_count(units: int, benchmarks: Dict[str, float]) -> float:
    """Score based on unit count."""
    max_units = benchmarks.get("max_units", 200)
    if max_units <= 0:
        return 0
    return min(100, (units / max_units) * 100)


def _score_unit_density(density: float, benchmarks: Dict[str, float]) -> float:
    """Score based on units per acre."""
    max_density = benchmarks.get("max_density", 100)
    if max_density <= 0:
        return 0
    return min(100, (density / max_density) * 100)


def _score_parking_efficiency(spaces_per_1000sf: float, benchmarks: Dict[str, float]) -> float:
    """Score parking efficiency (closer to optimal is better)."""
    optimal = benchmarks.get("optimal_parking_per_1000sf", 3.0)
    if spaces_per_1000sf <= 0:
        return 50  # Neutral if no data

    # Score decreases as we deviate from optimal
    deviation = abs(spaces_per_1000sf - optimal) / optimal
    return max(0, 100 - deviation * 100)


def _score_parking_surplus(surplus: int, required: int) -> float:
    """Score based on parking surplus/deficit."""
    if required <= 0:
        return 100  # No requirement = full score

    if surplus < 0:
        # Deficit is bad - score decreases with deficit
        deficit_ratio = abs(surplus) / required
        return max(0, 100 - deficit_ratio * 200)  # Penalize heavily
    elif surplus == 0:
        # Exact match
        return 100
    else:
        # Small surplus is good, large surplus wastes space
        surplus_ratio = surplus / required
        if surplus_ratio <= 0.1:  # Up to 10% surplus is perfect
            return 100
        elif surplus_ratio <= 0.25:  # Up to 25% is good
            return 90
        elif surplus_ratio <= 0.5:  # Up to 50% is okay
            return 70
        else:  # More than 50% surplus
            return max(30, 70 - (surplus_ratio - 0.5) * 80)


def _score_site_coverage(coverage: float, benchmarks: Dict[str, float]) -> float:
    """Score based on site coverage."""
    optimal = benchmarks.get("optimal_coverage", 0.5)

    if coverage <= 0:
        return 0

    # Higher coverage is generally better up to optimal
    if coverage <= optimal:
        return (coverage / optimal) * 100
    else:
        # Slightly over optimal is okay
        over = coverage - optimal
        return max(0, 100 - over * 100)


def _score_far(far: float, benchmarks: Dict[str, float]) -> float:
    """Score based on Floor Area Ratio."""
    max_far = benchmarks.get("max_far", 4.0)
    if max_far <= 0:
        return 0

    # Higher FAR is better (more development)
    return min(100, (far / max_far) * 100)


def _score_building_efficiency(efficiency: float, benchmarks: Dict[str, float]) -> float:
    """Score based on building efficiency (net/gross ratio)."""
    optimal = benchmarks.get("optimal_efficiency", 0.85)

    if efficiency <= 0:
        return 0

    # Higher efficiency is better
    return min(100, (efficiency / optimal) * 100)


def _score_compliance(is_compliant: bool, issue_count: int) -> float:
    """Score based on compliance status."""
    if is_compliant:
        return 100

    # Reduce score based on number of issues
    return max(0, 100 - issue_count * 25)


def _score_revenue(revenue: float, benchmarks: Dict[str, float]) -> float:
    """Score based on annual revenue."""
    max_revenue = benchmarks.get("max_revenue", 5_000_000)
    if max_revenue <= 0:
        return 0

    return min(100, (revenue / max_revenue) * 100)


def _score_profit(profit_margin: float, benchmarks: Dict[str, float]) -> float:
    """Score based on profit margin."""
    optimal = benchmarks.get("optimal_profit_margin", 0.30)

    if profit_margin < 0:
        return max(0, 50 + profit_margin * 100)  # Negative margin = low score

    return min(100, (profit_margin / optimal) * 100)


def _score_open_space(ratio: float, benchmarks: Dict[str, float]) -> float:
    """Score based on open space ratio."""
    optimal = benchmarks.get("optimal_open_space", 0.15)

    # Want some open space but not too much
    if ratio < optimal:
        return (ratio / optimal) * 100
    elif ratio <= optimal * 2:
        return 100
    else:
        # Too much open space reduces development
        over = ratio - optimal * 2
        return max(50, 100 - over * 200)


# =============================================================================
# COMPARISON UTILITIES
# =============================================================================

def get_score_breakdown(score: ConfigurationScore) -> Dict[str, Any]:
    """
    Get detailed breakdown of a configuration score.

    Args:
        score: Configuration score

    Returns:
        Detailed breakdown dictionary
    """
    return {
        "summary": {
            "id": score.configuration_id,
            "name": score.configuration_name,
            "total_score": round(score.total_score, 1),
            "rank": score.rank,
        },
        "scores": {
            "unit_count": {
                "score": round(score.unit_count_score, 1),
                "value": score.metrics.total_units,
            },
            "unit_density": {
                "score": round(score.unit_density_score, 1),
                "value": round(score.metrics.units_per_acre, 1),
                "units": "units/acre",
            },
            "parking_efficiency": {
                "score": round(score.parking_efficiency_score, 1),
                "value": round(score.metrics.spaces_per_1000sf, 2),
                "units": "spaces/1000sf",
            },
            "parking_surplus": {
                "score": round(score.parking_surplus_score, 1),
                "value": score.metrics.parking_surplus,
                "units": "spaces",
            },
            "far": {
                "score": round(score.far_score, 1),
                "value": round(score.metrics.far, 2),
            },
            "compliance": {
                "score": round(score.compliance_score, 1),
                "is_compliant": score.metrics.is_compliant,
                "issues": score.metrics.compliance_issues,
            },
        },
        "financial": {
            "revenue": round(score.metrics.annual_revenue, 0),
            "cost": round(score.metrics.construction_cost, 0),
            "noi": round(score.metrics.net_operating_income, 0),
            "value": round(score.metrics.project_value, 0),
            "profit_margin": f"{score.metrics.profit_margin:.1%}",
        },
    }


def compare_scores(scores: List[ConfigurationScore]) -> Dict[str, Any]:
    """
    Compare multiple configuration scores.

    Args:
        scores: List of scores to compare

    Returns:
        Comparison results
    """
    if not scores:
        return {"error": "No scores to compare"}

    # Find best in each category
    best_units = max(scores, key=lambda s: s.metrics.total_units)
    best_efficiency = max(scores, key=lambda s: s.building_efficiency_score)
    best_parking = max(scores, key=lambda s: s.parking_efficiency_score)
    best_profit = max(scores, key=lambda s: s.metrics.profit_margin)

    # Calculate averages
    avg_score = sum(s.total_score for s in scores) / len(scores)
    avg_units = sum(s.metrics.total_units for s in scores) / len(scores)

    return {
        "summary": {
            "count": len(scores),
            "average_score": round(avg_score, 1),
            "average_units": round(avg_units, 0),
            "compliant_count": sum(1 for s in scores if s.metrics.is_compliant),
        },
        "rankings": [
            {
                "rank": s.rank,
                "id": s.configuration_id,
                "name": s.configuration_name,
                "score": round(s.total_score, 1),
                "units": s.metrics.total_units,
                "compliant": s.metrics.is_compliant,
            }
            for s in sorted(scores, key=lambda s: s.rank)
        ],
        "best_by_category": {
            "most_units": {
                "id": best_units.configuration_id,
                "units": best_units.metrics.total_units,
            },
            "best_efficiency": {
                "id": best_efficiency.configuration_id,
                "score": round(best_efficiency.building_efficiency_score, 1),
            },
            "best_parking": {
                "id": best_parking.configuration_id,
                "score": round(best_parking.parking_efficiency_score, 1),
            },
            "best_profit": {
                "id": best_profit.configuration_id,
                "margin": f"{best_profit.metrics.profit_margin:.1%}",
            },
        },
    }
