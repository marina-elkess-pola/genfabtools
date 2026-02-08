"""
Tests for optimizer module.
"""

from sitefit.optimizer.solver import (
    OptimizationObjective,
    ConstraintType,
    Constraint,
    SolverConfig,
    OptimizationResult,
    find_optimal_configuration,
    find_pareto_optimal,
    solve_with_constraints,
    get_optimization_summary,
    create_solver_for_residential,
    create_balanced_solver,
)
from sitefit.optimizer.generator import (
    VariationType,
    VariationParameter,
    GeneratorConfig,
    GenerationResult,
    generate_configurations,
    generate_building_variations,
    get_quick_generation_config,
    get_comprehensive_generation_config,
)
import pytest
from sitefit.core.geometry import Point, Polygon, Rectangle
from sitefit.optimizer.configuration import (
    ElementType,
    SiteElement,
    ParkingElement,
    BuildingElement,
    OpenSpaceElement,
    ConfigurationResult,
    SiteConfiguration,
    create_configuration,
    create_parking_element,
    create_building_element,
    create_open_space_element,
    validate_configuration,
    configuration_to_dict,
    get_configuration_summary,
    compare_configurations,
)
from sitefit.optimizer.scorer import (
    ScoringWeights,
    ScoringMetrics,
    ConfigurationScore,
    FinancialAssumptions,
    score_configuration,
    rank_configurations,
    get_default_weights,
    get_unit_focused_weights,
    get_efficiency_focused_weights,
    get_profit_focused_weights,
    get_compliance_focused_weights,
    calculate_metrics,
    get_score_breakdown,
    compare_scores,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def simple_site():
    """Create a simple rectangular site."""
    return Rectangle(Point(0, 0), 300, 200).to_polygon()  # 60,000 SF


@pytest.fixture
def small_site():
    """Create a smaller site."""
    return Rectangle(Point(0, 0), 100, 100).to_polygon()  # 10,000 SF


@pytest.fixture
def building_footprint():
    """Create a building footprint."""
    return Rectangle(Point(50, 50), 100, 80).to_polygon()  # 8,000 SF


@pytest.fixture
def parking_footprint():
    """Create a parking footprint."""
    return Rectangle(Point(160, 20), 130, 160).to_polygon()  # 20,800 SF


# =============================================================================
# TEST ELEMENT TYPES
# =============================================================================

class TestElementType:
    """Tests for ElementType enum."""

    def test_parking_types(self):
        """Test parking type values."""
        assert ElementType.PARKING_SURFACE.value == "parking_surface"
        assert ElementType.PARKING_STRUCTURE.value == "parking_structure"
        assert ElementType.PARKING_UNDERGROUND.value == "parking_underground"

    def test_building_types(self):
        """Test building type values."""
        assert ElementType.BUILDING_RESIDENTIAL.value == "building_residential"
        assert ElementType.BUILDING_COMMERCIAL.value == "building_commercial"
        assert ElementType.BUILDING_MIXED_USE.value == "building_mixed_use"

    def test_other_types(self):
        """Test other element types."""
        assert ElementType.OPEN_SPACE.value == "open_space"
        assert ElementType.AMENITY.value == "amenity"
        assert ElementType.CIRCULATION.value == "circulation"


# =============================================================================
# TEST SITE ELEMENT
# =============================================================================

class TestSiteElement:
    """Tests for SiteElement base class."""

    def test_create_element(self, building_footprint):
        """Test creating a site element."""
        element = SiteElement(
            id="elem1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint,
            name="Building 1"
        )

        assert element.id == "elem1"
        assert element.element_type == ElementType.BUILDING_RESIDENTIAL
        assert element.name == "Building 1"

    def test_element_area(self, building_footprint):
        """Test element area calculation."""
        element = SiteElement(
            id="elem1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint
        )

        assert element.area == pytest.approx(8000, rel=0.01)

    def test_element_centroid(self, building_footprint):
        """Test element centroid."""
        element = SiteElement(
            id="elem1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint
        )

        centroid = element.centroid
        assert centroid.x == pytest.approx(100, rel=0.01)
        assert centroid.y == pytest.approx(90, rel=0.01)

    def test_element_to_dict(self, building_footprint):
        """Test element serialization."""
        element = SiteElement(
            id="elem1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint,
            name="Building 1",
            metadata={"type": "apartment"}
        )

        data = element.to_dict()
        assert data["id"] == "elem1"
        assert data["element_type"] == "building_residential"
        assert data["name"] == "Building 1"
        assert "footprint_area" in data


# =============================================================================
# TEST PARKING ELEMENT
# =============================================================================

class TestParkingElement:
    """Tests for ParkingElement."""

    def test_create_parking_element(self, parking_footprint):
        """Test creating parking element."""
        parking = ParkingElement(
            id="parking1",
            element_type=ElementType.PARKING_SURFACE,
            footprint=parking_footprint,
            stall_count=60,
            levels=1
        )

        assert parking.stall_count == 60
        assert parking.levels == 1
        assert parking.total_spaces == 60

    def test_parking_multiple_levels(self, parking_footprint):
        """Test parking with multiple levels."""
        parking = ParkingElement(
            id="parking1",
            element_type=ElementType.PARKING_STRUCTURE,
            footprint=parking_footprint,
            stall_count=60,
            levels=3
        )

        assert parking.stall_count == 60
        assert parking.levels == 3
        assert parking.total_spaces == 180

    def test_parking_efficiency(self, parking_footprint):
        """Test parking efficiency calculation."""
        parking = ParkingElement(
            id="parking1",
            element_type=ElementType.PARKING_SURFACE,
            footprint=parking_footprint,
            stall_count=60,
            levels=1
        )

        # 60 stalls / 20,800 SF * 1000 = ~2.88 stalls per 1000 SF
        assert parking.parking_efficiency > 0

    def test_parking_to_dict(self, parking_footprint):
        """Test parking serialization."""
        parking = ParkingElement(
            id="parking1",
            element_type=ElementType.PARKING_SURFACE,
            footprint=parking_footprint,
            stall_count=60,
            levels=2,
            stall_angle=90.0
        )

        data = parking.to_dict()
        assert data["stall_count"] == 60
        assert data["levels"] == 2
        assert data["total_spaces"] == 120
        assert data["stall_angle"] == 90.0

    def test_create_parking_element_function(self, parking_footprint):
        """Test create_parking_element helper."""
        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=50,
            levels=2,
            name="Main Parking"
        )

        assert parking.stall_count == 50
        assert parking.levels == 2
        assert parking.name == "Main Parking"
        assert parking.id.startswith("parking_")


# =============================================================================
# TEST BUILDING ELEMENT
# =============================================================================

class TestBuildingElement:
    """Tests for BuildingElement."""

    def test_create_building_element(self, building_footprint):
        """Test creating building element."""
        building = BuildingElement(
            id="building1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint,
            floors=5,
            floor_height=10.0
        )

        assert building.floors == 5
        assert building.floor_height == 10.0
        assert building.total_height == 50.0

    def test_building_gross_area(self, building_footprint):
        """Test building gross area calculation."""
        building = BuildingElement(
            id="building1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint,
            floors=5
        )

        # 8,000 SF footprint * 5 floors = 40,000 SF
        assert building.gross_area == pytest.approx(40000, rel=0.01)

    def test_building_far_calculation(self, building_footprint):
        """Test building FAR calculation."""
        site_area = 60000
        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            site_area=site_area
        )

        # 40,000 SF / 60,000 SF = 0.667 FAR
        assert building.far == pytest.approx(0.667, rel=0.01)

    def test_building_lot_coverage(self, building_footprint):
        """Test building lot coverage."""
        site_area = 60000
        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            site_area=site_area
        )

        # 8,000 SF / 60,000 SF = 0.133
        assert building.lot_coverage == pytest.approx(0.133, rel=0.01)

    def test_building_to_dict(self, building_footprint):
        """Test building serialization."""
        building = BuildingElement(
            id="building1",
            element_type=ElementType.BUILDING_RESIDENTIAL,
            footprint=building_footprint,
            floors=5,
            floor_height=10.0,
            total_units=40
        )

        data = building.to_dict()
        assert data["floors"] == 5
        assert data["floor_height"] == 10.0
        assert data["total_height"] == 50.0
        assert data["total_units"] == 40


# =============================================================================
# TEST OPEN SPACE ELEMENT
# =============================================================================

class TestOpenSpaceElement:
    """Tests for OpenSpaceElement."""

    def test_create_open_space(self, small_site):
        """Test creating open space element."""
        open_space = OpenSpaceElement(
            id="open1",
            element_type=ElementType.OPEN_SPACE,
            footprint=small_site,
            landscape_type="courtyard",
            is_public=True
        )

        assert open_space.landscape_type == "courtyard"
        assert open_space.is_public is True

    def test_open_space_amenities(self, small_site):
        """Test open space with amenities."""
        open_space = OpenSpaceElement(
            id="open1",
            element_type=ElementType.OPEN_SPACE,
            footprint=small_site,
            amenities=["pool", "bbq", "playground"]
        )

        assert len(open_space.amenities) == 3
        assert "pool" in open_space.amenities

    def test_open_space_to_dict(self, small_site):
        """Test open space serialization."""
        open_space = create_open_space_element(
            footprint=small_site,
            landscape_type="plaza",
            is_public=True,
            amenities=["fountain", "seating"]
        )

        data = open_space.to_dict()
        assert data["landscape_type"] == "plaza"
        assert data["is_public"] is True
        assert "fountain" in data["amenities"]


# =============================================================================
# TEST CONFIGURATION RESULT
# =============================================================================

class TestConfigurationResult:
    """Tests for ConfigurationResult."""

    def test_default_result(self):
        """Test default result values."""
        result = ConfigurationResult()

        assert result.site_area == 0.0
        assert result.total_units == 0
        assert result.total_parking_spaces == 0
        assert result.zoning_compliant is True

    def test_result_with_values(self):
        """Test result with values."""
        result = ConfigurationResult(
            site_area=60000,
            total_gross_area=120000,
            total_units=100,
            total_parking_spaces=150
        )

        assert result.site_area == 60000
        assert result.total_units == 100
        assert result.total_parking_spaces == 150

    def test_result_to_dict(self):
        """Test result serialization."""
        result = ConfigurationResult(
            site_area=60000,
            buildable_area=50000,
            total_gross_area=120000,
            total_units=100,
            total_parking_spaces=150,
            far=2.0
        )

        data = result.to_dict()
        assert "site_metrics" in data
        assert "building_metrics" in data
        assert "parking_metrics" in data
        assert "efficiency_metrics" in data
        assert "compliance" in data


# =============================================================================
# TEST SITE CONFIGURATION
# =============================================================================

class TestSiteConfiguration:
    """Tests for SiteConfiguration."""

    def test_create_configuration(self, simple_site):
        """Test creating a configuration."""
        config = SiteConfiguration(
            id="config1",
            name="Test Configuration",
            site_boundary=simple_site
        )

        assert config.id == "config1"
        assert config.name == "Test Configuration"
        assert config.site_area == pytest.approx(60000, rel=0.01)

    def test_configuration_buildable_area(self, simple_site, small_site):
        """Test configuration with buildable boundary."""
        config = SiteConfiguration(
            id="config1",
            name="Test",
            site_boundary=simple_site,
            buildable_boundary=small_site
        )

        assert config.site_area == pytest.approx(60000, rel=0.01)
        assert config.buildable_area == pytest.approx(10000, rel=0.01)

    def test_add_elements(self, simple_site, building_footprint, parking_footprint):
        """Test adding elements to configuration."""
        config = SiteConfiguration(
            id="config1",
            name="Test",
            site_boundary=simple_site
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=60
        )

        config.add_element(building)
        config.add_element(parking)

        assert len(config.elements) == 2
        assert len(config.buildings) == 1
        assert len(config.parking_areas) == 1

    def test_remove_element(self, simple_site, building_footprint):
        """Test removing elements."""
        config = SiteConfiguration(
            id="config1",
            name="Test",
            site_boundary=simple_site
        )

        building = create_building_element(
            id="building_1",
            footprint=building_footprint,
            floors=5
        )

        config.add_element(building)
        assert len(config.elements) == 1

        config.remove_element("building_1")
        assert len(config.elements) == 0

    def test_get_element(self, simple_site, building_footprint):
        """Test getting element by ID."""
        config = SiteConfiguration(
            id="config1",
            name="Test",
            site_boundary=simple_site
        )

        building = create_building_element(
            id="building_1",
            footprint=building_footprint,
            floors=5
        )

        config.add_element(building)

        found = config.get_element("building_1")
        assert found is not None
        assert found.id == "building_1"

        not_found = config.get_element("nonexistent")
        assert not_found is None

    def test_calculate_results(self, simple_site, building_footprint, parking_footprint):
        """Test calculating configuration results."""
        config = SiteConfiguration(
            id="config1",
            name="Test",
            site_boundary=simple_site
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40,
            site_area=simple_site.area
        )

        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=60
        )

        config.add_element(building)
        config.add_element(parking)

        result = config.calculate_results()

        assert result.total_units == 40
        assert result.total_parking_spaces == 60
        assert result.site_area == pytest.approx(60000, rel=0.01)

    def test_parking_compliance(self, simple_site, building_footprint, parking_footprint):
        """Test parking compliance check."""
        config = SiteConfiguration(
            id="config1",
            name="Test",
            site_boundary=simple_site
        )

        # 40 units * 1.5 ratio = 60 required
        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        # Only 50 spaces (10 short)
        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=50
        )

        config.add_element(building)
        config.add_element(parking)

        result = config.calculate_results()

        assert result.parking_compliant is False
        assert result.parking_surplus == -10

    def test_configuration_to_dict(self, simple_site):
        """Test configuration serialization."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Test Config",
            parking_angle=60.0
        )

        data = config.to_dict()

        assert data["name"] == "Test Config"
        assert data["parking_angle"] == 60.0
        assert "site_area" in data


# =============================================================================
# TEST CONFIGURATION FUNCTIONS
# =============================================================================

class TestConfigurationFunctions:
    """Tests for configuration helper functions."""

    def test_create_configuration_function(self, simple_site):
        """Test create_configuration helper."""
        config = create_configuration(
            site_boundary=simple_site,
            name="My Config",
            parking_angle=45.0,
            building_coverage=0.4
        )

        assert config.name == "My Config"
        assert config.parking_angle == 45.0
        assert config.building_coverage == 0.4
        assert config.id is not None

    def test_validate_configuration(self, simple_site, building_footprint):
        """Test configuration validation."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Test"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        parking = create_parking_element(
            footprint=Rectangle(Point(160, 20), 100, 100).to_polygon(),
            stall_count=60
        )

        config.add_element(building)
        config.add_element(parking)

        is_valid, issues = validate_configuration(config)

        assert isinstance(is_valid, bool)
        assert isinstance(issues, list)

    def test_get_configuration_summary(self, simple_site, building_footprint):
        """Test configuration summary."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Summary Test"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        config.add_element(building)

        summary = get_configuration_summary(config)

        assert summary["name"] == "Summary Test"
        assert summary["total_units"] == 40
        assert summary["building_count"] == 1
        assert "site_area_sf" in summary
        assert "site_area_acres" in summary

    def test_compare_configurations(self, simple_site, building_footprint, parking_footprint):
        """Test comparing configurations."""
        config1 = create_configuration(
            site_boundary=simple_site,
            name="Config A",
            id="config_a"
        )

        config2 = create_configuration(
            site_boundary=simple_site,
            name="Config B",
            id="config_b"
        )

        # Config A: 40 units
        building1 = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )
        config1.add_element(building1)

        # Config B: 60 units
        building2 = create_building_element(
            footprint=building_footprint,
            floors=7,
            total_units=60
        )
        config2.add_element(building2)

        comparison = compare_configurations([config1, config2])

        assert comparison["total_count"] == 2
        assert comparison["best_by_units"] == "config_b"
        assert len(comparison["configurations"]) == 2

    def test_configuration_to_dict_function(self, simple_site):
        """Test configuration_to_dict helper."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Dict Test"
        )

        data = configuration_to_dict(config)

        assert data["name"] == "Dict Test"
        assert isinstance(data, dict)


# =============================================================================
# TEST ZONING INTEGRATION
# =============================================================================

class TestZoningIntegration:
    """Tests for zoning integration."""

    def test_configuration_with_zoning(self, simple_site, building_footprint):
        """Test configuration with zoning constraints."""
        from sitefit.constraints.zoning import ZoningDistrict

        zoning = ZoningDistrict(
            name="R-4",
            max_height_ft=50,
            max_far=2.0,
            max_lot_coverage=0.5,
            parking_ratio=1.5
        )

        config = create_configuration(
            site_boundary=simple_site,
            name="Zoned Config",
            zoning=zoning
        )

        # Building exceeds height limit (60 ft > 50 ft)
        building = create_building_element(
            footprint=building_footprint,
            floors=6,  # 60 ft
            total_units=50
        )

        config.add_element(building)
        result = config.calculate_results()

        assert result.height_compliant is False
        assert any("Height" in issue for issue in result.compliance_issues)

    def test_far_compliance(self, simple_site, building_footprint):
        """Test FAR compliance checking."""
        from sitefit.constraints.zoning import ZoningDistrict

        zoning = ZoningDistrict(
            name="R-4",
            max_height_ft=100,
            max_far=0.5,  # Low FAR limit
            max_lot_coverage=0.8,
            parking_ratio=1.0
        )

        config = create_configuration(
            site_boundary=simple_site,
            name="FAR Test",
            zoning=zoning
        )

        # 8000 SF * 5 floors = 40,000 SF
        # Site = 60,000 SF
        # FAR = 0.67 > 0.5 limit
        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        config.add_element(building)
        result = config.calculate_results()

        assert result.zoning_compliant is False
        assert any("FAR" in issue for issue in result.compliance_issues)


# =============================================================================
# TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_configuration(self, simple_site):
        """Test configuration with no elements."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Empty"
        )

        result = config.calculate_results()

        assert result.total_units == 0
        assert result.total_parking_spaces == 0
        assert result.far == 0

    def test_parking_only_configuration(self, simple_site, parking_footprint):
        """Test configuration with only parking."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Parking Only"
        )

        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=100
        )

        config.add_element(parking)

        is_valid, issues = validate_configuration(config)

        assert "no buildings" in str(issues).lower()

    def test_underground_parking_overlap(self, simple_site, building_footprint):
        """Test underground parking can overlap with building."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Underground Parking"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5
        )

        # Underground parking with same footprint as building
        underground = ParkingElement(
            id="parking_ug",
            element_type=ElementType.PARKING_UNDERGROUND,
            footprint=building_footprint,
            stall_count=30,
            levels=1
        )

        config.add_element(building)
        config.add_element(underground)

        # Should not report overlap for underground parking
        is_valid, issues = validate_configuration(config)
        overlap_issues = [i for i in issues if "overlap" in i.lower()]

        assert len(overlap_issues) == 0


# =============================================================================
# TEST SCORING WEIGHTS
# =============================================================================

class TestScoringWeights:
    """Tests for ScoringWeights."""

    def test_default_weights(self):
        """Test default weights sum to 1."""
        weights = ScoringWeights()
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)

    def test_weights_auto_normalize(self):
        """Test weights auto-normalize if not summing to 1."""
        weights = ScoringWeights(
            unit_count=0.5,
            unit_density=0.5,
            parking_efficiency=0.5,
            parking_surplus=0.5,
            site_coverage=0.5,
            far=0.5,
            building_efficiency=0.5,
            compliance=0.5,
            revenue_potential=0.5,
            profit_margin=0.5,
            open_space_ratio=0.5,
        )

        # Should auto-normalize
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)

    def test_weights_to_dict(self):
        """Test weights serialization."""
        weights = get_default_weights()
        data = weights.to_dict()

        assert "unit_count" in data
        assert "compliance" in data
        assert sum(data.values()) == pytest.approx(1.0, rel=0.01)


class TestWeightPresets:
    """Tests for weight preset functions."""

    def test_default_weights(self):
        """Test default weights."""
        weights = get_default_weights()
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)

    def test_unit_focused_weights(self):
        """Test unit-focused weights emphasize units."""
        weights = get_unit_focused_weights()
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)
        assert weights.unit_count >= 0.3  # High unit weight

    def test_efficiency_focused_weights(self):
        """Test efficiency-focused weights."""
        weights = get_efficiency_focused_weights()
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)
        assert weights.building_efficiency >= 0.10

    def test_profit_focused_weights(self):
        """Test profit-focused weights."""
        weights = get_profit_focused_weights()
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)
        assert weights.revenue_potential >= 0.15

    def test_compliance_focused_weights(self):
        """Test compliance-focused weights."""
        weights = get_compliance_focused_weights()
        assert weights.total_weight == pytest.approx(1.0, rel=0.01)
        assert weights.compliance >= 0.25


# =============================================================================
# TEST FINANCIAL ASSUMPTIONS
# =============================================================================

class TestFinancialAssumptions:
    """Tests for FinancialAssumptions."""

    def test_default_assumptions(self):
        """Test default financial assumptions."""
        financial = FinancialAssumptions()

        assert financial.rent_1br > 0
        assert financial.cost_residential_psf > 0
        assert financial.cap_rate > 0

    def test_assumptions_to_dict(self):
        """Test financial assumptions serialization."""
        financial = FinancialAssumptions()
        data = financial.to_dict()

        assert "rent_1br" in data
        assert "cost_residential_psf" in data
        assert "cap_rate" in data


# =============================================================================
# TEST SCORING METRICS
# =============================================================================

class TestScoringMetrics:
    """Tests for ScoringMetrics."""

    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = ScoringMetrics()

        assert metrics.total_units == 0
        assert metrics.is_compliant is True

    def test_metrics_with_values(self):
        """Test metrics with values."""
        metrics = ScoringMetrics(
            total_units=100,
            units_per_acre=50.0,
            far=2.0,
            is_compliant=False
        )

        assert metrics.total_units == 100
        assert metrics.units_per_acre == 50.0
        assert metrics.is_compliant is False

    def test_metrics_to_dict(self):
        """Test metrics serialization."""
        metrics = ScoringMetrics(
            total_units=100,
            annual_revenue=2000000
        )

        data = metrics.to_dict()

        assert "units" in data
        assert "parking" in data
        assert "financial" in data


# =============================================================================
# TEST CONFIGURATION SCORE
# =============================================================================

class TestConfigurationScore:
    """Tests for ConfigurationScore."""

    def test_score_creation(self):
        """Test creating a configuration score."""
        metrics = ScoringMetrics(total_units=100)
        score = ConfigurationScore(
            configuration_id="test1",
            configuration_name="Test Config",
            metrics=metrics,
            total_score=75.0
        )

        assert score.configuration_id == "test1"
        assert score.total_score == 75.0

    def test_score_to_dict(self):
        """Test score serialization."""
        metrics = ScoringMetrics(total_units=100)
        score = ConfigurationScore(
            configuration_id="test1",
            configuration_name="Test Config",
            metrics=metrics,
            total_score=75.0,
            rank=1
        )

        data = score.to_dict()

        assert data["configuration_id"] == "test1"
        assert data["total_score"] == 75.0
        assert data["rank"] == 1
        assert "component_scores" in data


# =============================================================================
# TEST CALCULATE METRICS
# =============================================================================

class TestCalculateMetrics:
    """Tests for calculate_metrics function."""

    def test_calculate_basic_metrics(self, simple_site, building_footprint, parking_footprint):
        """Test calculating basic metrics."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Metrics Test"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=60
        )

        config.add_element(building)
        config.add_element(parking)

        metrics = calculate_metrics(config)

        assert metrics.total_units == 40
        assert metrics.total_parking == 60
        assert metrics.site_area == pytest.approx(60000, rel=0.01)

    def test_calculate_density(self, simple_site, building_footprint):
        """Test density calculation."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Density Test"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        config.add_element(building)

        metrics = calculate_metrics(config)

        # 40 units / (60,000 SF / 43,560 SF/acre) = ~29 units/acre
        assert metrics.units_per_acre == pytest.approx(29, rel=0.1)

    def test_calculate_financials(self, simple_site, building_footprint):
        """Test financial calculations."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Financial Test"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        config.add_element(building)

        financial = FinancialAssumptions()
        metrics = calculate_metrics(config, financial)

        # Should have revenue and costs
        assert metrics.annual_revenue > 0
        assert metrics.construction_cost > 0
        assert metrics.project_value > 0


# =============================================================================
# TEST SCORE CONFIGURATION
# =============================================================================

class TestScoreConfiguration:
    """Tests for score_configuration function."""

    def test_score_simple_config(self, simple_site, building_footprint, parking_footprint):
        """Test scoring a simple configuration."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Score Test"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        parking = create_parking_element(
            footprint=parking_footprint,
            stall_count=60
        )

        config.add_element(building)
        config.add_element(parking)

        score = score_configuration(config)

        assert score.configuration_id == config.id
        assert score.total_score >= 0
        assert score.total_score <= 100

    def test_score_with_custom_weights(self, simple_site, building_footprint):
        """Test scoring with custom weights."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Custom Weights"
        )

        building = create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        )

        config.add_element(building)

        # Unit-focused weights
        unit_weights = get_unit_focused_weights()
        score1 = score_configuration(config, weights=unit_weights)

        # Efficiency-focused weights
        eff_weights = get_efficiency_focused_weights()
        score2 = score_configuration(config, weights=eff_weights)

        # Scores should differ based on weights
        assert score1.total_score != score2.total_score or \
            score1.unit_count_score >= score2.unit_count_score

    def test_score_compliance_impact(self, simple_site, building_footprint):
        """Test that compliance affects score."""
        from sitefit.constraints.zoning import ZoningDistrict

        zoning = ZoningDistrict(
            name="R-4",
            max_height_ft=30,  # Low height limit
            max_far=2.0,
            max_lot_coverage=0.5,
            parking_ratio=1.5
        )

        config = create_configuration(
            site_boundary=simple_site,
            name="Compliance Test",
            zoning=zoning
        )

        # Building exceeds height limit
        building = create_building_element(
            footprint=building_footprint,
            floors=5,  # 50 ft > 30 ft limit
            total_units=40
        )

        config.add_element(building)

        score = score_configuration(config)

        # Compliance score should be reduced
        assert score.compliance_score < 100
        assert not score.metrics.is_compliant


# =============================================================================
# TEST RANK CONFIGURATIONS
# =============================================================================

class TestRankConfigurations:
    """Tests for rank_configurations function."""

    def test_rank_multiple_configs(self, simple_site, building_footprint, parking_footprint):
        """Test ranking multiple configurations."""
        configs = []

        # Config 1: 40 units, 60 parking
        config1 = create_configuration(
            site_boundary=simple_site,
            name="Config A",
            id="config_a"
        )
        config1.add_element(create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        ))
        config1.add_element(create_parking_element(
            footprint=parking_footprint,
            stall_count=60
        ))
        configs.append(config1)

        # Config 2: 60 units, 90 parking (higher density)
        config2 = create_configuration(
            site_boundary=simple_site,
            name="Config B",
            id="config_b"
        )
        config2.add_element(create_building_element(
            footprint=building_footprint,
            floors=7,
            total_units=60
        ))
        config2.add_element(create_parking_element(
            footprint=parking_footprint,
            stall_count=90
        ))
        configs.append(config2)

        scores = rank_configurations(configs)

        assert len(scores) == 2
        assert scores[0].rank == 1
        assert scores[1].rank == 2
        assert scores[0].total_score >= scores[1].total_score

    def test_rank_assigns_positions(self, simple_site, building_footprint):
        """Test that ranking assigns correct positions."""
        configs = []

        for i in range(3):
            config = create_configuration(
                site_boundary=simple_site,
                name=f"Config {i}",
                id=f"config_{i}"
            )
            config.add_element(create_building_element(
                footprint=building_footprint,
                floors=3 + i,  # Different heights
                total_units=20 + i * 10  # Different unit counts
            ))
            configs.append(config)

        scores = rank_configurations(configs)

        ranks = [s.rank for s in scores]
        assert sorted(ranks) == [1, 2, 3]


# =============================================================================
# TEST SCORE BREAKDOWN
# =============================================================================

class TestScoreBreakdown:
    """Tests for get_score_breakdown function."""

    def test_breakdown_structure(self, simple_site, building_footprint):
        """Test breakdown returns expected structure."""
        config = create_configuration(
            site_boundary=simple_site,
            name="Breakdown Test"
        )

        config.add_element(create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        ))

        score = score_configuration(config)
        breakdown = get_score_breakdown(score)

        assert "summary" in breakdown
        assert "scores" in breakdown
        assert "financial" in breakdown
        assert breakdown["summary"]["id"] == config.id


# =============================================================================
# TEST COMPARE SCORES
# =============================================================================

class TestCompareScores:
    """Tests for compare_scores function."""

    def test_compare_multiple_scores(self, simple_site, building_footprint, parking_footprint):
        """Test comparing multiple scores."""
        configs = []

        for i in range(3):
            config = create_configuration(
                site_boundary=simple_site,
                name=f"Config {i}",
                id=f"config_{i}"
            )
            config.add_element(create_building_element(
                footprint=building_footprint,
                floors=3 + i,
                total_units=20 + i * 10
            ))
            config.add_element(create_parking_element(
                footprint=parking_footprint,
                stall_count=30 + i * 15
            ))
            configs.append(config)

        scores = rank_configurations(configs)
        comparison = compare_scores(scores)

        assert comparison["summary"]["count"] == 3
        assert "rankings" in comparison
        assert "best_by_category" in comparison

    def test_compare_empty_scores(self):
        """Test comparing empty score list."""
        comparison = compare_scores([])
        assert "error" in comparison


# =============================================================================
# TEST GENERATOR MODULE
# =============================================================================


class TestVariationParameter:
    """Tests for VariationParameter."""

    def test_create_parameter(self):
        """Test creating a variation parameter."""
        param = VariationParameter(
            name="coverage",
            variation_type=VariationType.BUILDING_COVERAGE,
            min_value=0.2,
            max_value=0.5,
            step=0.1
        )

        assert param.name == "coverage"
        assert param.min_value == 0.2
        assert param.max_value == 0.5

    def test_get_values(self):
        """Test getting parameter values."""
        param = VariationParameter(
            name="floors",
            variation_type=VariationType.BUILDING_HEIGHT,
            min_value=3,
            max_value=6,
            step=1
        )

        values = param.get_values()
        assert values == [3, 4, 5, 6]

    def test_value_count(self):
        """Test value count property."""
        param = VariationParameter(
            name="angle",
            variation_type=VariationType.PARKING_ANGLE,
            min_value=0,
            max_value=90,
            step=30
        )

        assert param.value_count == 4  # 0, 30, 60, 90

    def test_to_dict(self):
        """Test parameter serialization."""
        param = VariationParameter(
            name="test",
            variation_type=VariationType.BUILDING_COVERAGE,
            min_value=0.3,
            max_value=0.5,
            step=0.1
        )

        data = param.to_dict()
        assert "name" in data
        assert "values" in data


class TestGeneratorConfig:
    """Tests for GeneratorConfig."""

    def test_default_config(self):
        """Test default generator config."""
        config = GeneratorConfig()

        assert len(config.parking_angles) > 0
        assert config.min_coverage < config.max_coverage
        assert config.min_floors < config.max_floors

    def test_coverage_values(self):
        """Test coverage value generation."""
        config = GeneratorConfig(
            min_coverage=0.2,
            max_coverage=0.4,
            coverage_step=0.1
        )

        values = config.coverage_values
        assert 0.2 in values
        assert 0.3 in values
        assert 0.4 in values

    def test_floor_values(self):
        """Test floor value generation."""
        config = GeneratorConfig(
            min_floors=3,
            max_floors=6,
            floor_step=1
        )

        values = config.floor_values
        assert values == [3, 4, 5, 6]

    def test_total_combinations(self):
        """Test total combinations calculation."""
        config = GeneratorConfig(
            parking_angles=[45, 90],
            parking_locations=["surface"],
            min_coverage=0.3,
            max_coverage=0.4,
            coverage_step=0.1,
            min_floors=4,
            max_floors=5,
            floor_step=1,
            building_positions=["center"]
        )

        # 2 angles * 1 location * 2 coverages * 2 floors * 1 position = 8
        assert config.total_combinations == 8

    def test_to_dict(self):
        """Test config serialization."""
        config = GeneratorConfig()
        data = config.to_dict()

        assert "parking_angles" in data
        assert "total_combinations" in data


class TestGenerateConfigurations:
    """Tests for generate_configurations function."""

    def test_generate_basic(self, simple_site):
        """Test basic configuration generation."""
        config = GeneratorConfig(
            parking_angles=[90],
            parking_locations=["surface"],
            min_coverage=0.3,
            max_coverage=0.3,
            coverage_step=0.1,
            min_floors=4,
            max_floors=4,
            floor_step=1,
            building_positions=["center"],
            max_configurations=10
        )

        result = generate_configurations(simple_site, config)

        assert isinstance(result, GenerationResult)
        assert result.total_generated >= 1
        assert result.generation_time_ms > 0

    def test_generate_multiple(self, simple_site):
        """Test generating multiple configurations."""
        config = GeneratorConfig(
            parking_angles=[45, 90],
            min_coverage=0.3,
            max_coverage=0.4,
            coverage_step=0.1,
            min_floors=3,
            max_floors=4,
            floor_step=1,
            max_configurations=20
        )

        result = generate_configurations(simple_site, config)

        assert result.total_generated > 1

    def test_max_configurations_limit(self, simple_site):
        """Test max configurations limit."""
        config = GeneratorConfig(
            max_configurations=5
        )

        result = generate_configurations(simple_site, config)

        assert result.total_generated <= 5

    def test_result_to_dict(self, simple_site):
        """Test result serialization."""
        config = GeneratorConfig(max_configurations=3)
        result = generate_configurations(simple_site, config)

        data = result.to_dict()
        assert "total_generated" in data
        assert "generation_time_ms" in data


class TestGenerateBuildingVariations:
    """Tests for generate_building_variations function."""

    def test_generate_buildings(self, simple_site):
        """Test building variation generation."""
        configs = generate_building_variations(
            site_boundary=simple_site,
            coverages=[0.3, 0.4],
            floors=[4, 5]
        )

        assert len(configs) > 0
        assert all(len(c.buildings) > 0 for c in configs)

    def test_different_floors(self, simple_site):
        """Test different floor counts."""
        configs = generate_building_variations(
            site_boundary=simple_site,
            coverages=[0.4],
            floors=[3, 5, 7]
        )

        # Should have 3 configurations
        assert len(configs) >= 3


class TestGeneratorPresets:
    """Tests for generator preset configurations."""

    def test_quick_generation_config(self):
        """Test quick generation preset."""
        config = get_quick_generation_config()

        assert config.max_configurations <= 50
        assert len(config.parking_angles) <= 3

    def test_comprehensive_generation_config(self):
        """Test comprehensive generation preset."""
        config = get_comprehensive_generation_config()

        assert config.max_configurations >= 100
        assert len(config.parking_angles) >= 4


# =============================================================================
# TEST SOLVER MODULE
# =============================================================================


class TestConstraint:
    """Tests for Constraint class."""

    def test_create_constraint(self):
        """Test creating a constraint."""
        constraint = Constraint(
            constraint_type=ConstraintType.MIN_UNITS,
            value=50
        )

        assert constraint.constraint_type == ConstraintType.MIN_UNITS
        assert constraint.value == 50

    def test_constraint_to_dict(self):
        """Test constraint serialization."""
        constraint = Constraint(
            constraint_type=ConstraintType.MAX_HEIGHT,
            value=100,
            weight=1.5
        )

        data = constraint.to_dict()
        assert data["type"] == "max_height"
        assert data["value"] == 100


class TestSolverConfig:
    """Tests for SolverConfig."""

    def test_default_config(self):
        """Test default solver config."""
        config = SolverConfig()

        assert config.objective == OptimizationObjective.MAXIMIZE_SCORE
        assert config.max_iterations > 0
        assert config.time_limit_seconds > 0

    def test_add_constraint(self):
        """Test adding constraints."""
        config = SolverConfig()
        config.add_constraint(ConstraintType.MIN_UNITS, 100)
        config.add_constraint(ConstraintType.MAX_HEIGHT, 80)

        assert len(config.constraints) == 2

    def test_to_dict(self):
        """Test config serialization."""
        config = SolverConfig()
        config.add_constraint(ConstraintType.MIN_UNITS, 50)

        data = config.to_dict()
        assert "objective" in data
        assert "constraints" in data


class TestFindOptimalConfiguration:
    """Tests for find_optimal_configuration function."""

    def test_find_optimal_basic(self, simple_site, building_footprint, parking_footprint):
        """Test finding optimal from list."""
        configs = []

        for i in range(3):
            config = create_configuration(
                site_boundary=simple_site,
                name=f"Config {i}",
                id=f"config_{i}"
            )
            config.add_element(create_building_element(
                footprint=building_footprint,
                floors=3 + i,
                total_units=20 + i * 10
            ))
            config.add_element(create_parking_element(
                footprint=parking_footprint,
                stall_count=30 + i * 15
            ))
            configs.append(config)

        result = find_optimal_configuration(configs)

        assert result.best_configuration is not None
        assert result.configurations_evaluated == 3

    def test_find_optimal_with_constraints(self, simple_site, building_footprint, parking_footprint):
        """Test optimization with constraints."""
        configs = []

        for i in range(3):
            config = create_configuration(
                site_boundary=simple_site,
                name=f"Config {i}",
                id=f"config_{i}"
            )
            config.add_element(create_building_element(
                footprint=building_footprint,
                floors=3 + i,
                total_units=20 + i * 10
            ))
            configs.append(config)

        solver = SolverConfig()
        solver.add_constraint(ConstraintType.MIN_UNITS, 25)

        result = find_optimal_configuration(configs, solver)

        # Should find configs with >= 25 units
        if result.best_configuration:
            result.best_configuration.calculate_results()
            assert result.best_configuration.result.total_units >= 25

    def test_empty_configurations(self):
        """Test with empty configuration list."""
        result = find_optimal_configuration([])

        assert result.best_configuration is None
        assert result.configurations_evaluated == 0


class TestFindParetoOptimal:
    """Tests for find_pareto_optimal function."""

    def test_find_pareto(self, simple_site, building_footprint, parking_footprint):
        """Test finding Pareto optimal solutions."""
        configs = []

        for i in range(4):
            config = create_configuration(
                site_boundary=simple_site,
                name=f"Config {i}",
                id=f"config_{i}"
            )
            config.add_element(create_building_element(
                footprint=building_footprint,
                floors=3 + i,
                total_units=20 + i * 5
            ))
            config.add_element(create_parking_element(
                footprint=parking_footprint,
                stall_count=40 - i * 5  # Inverse relationship
            ))
            configs.append(config)

        result = find_pareto_optimal(configs)

        assert result.configurations_evaluated == 4
        assert len(result.pareto_front) > 0


class TestSolverPresets:
    """Tests for solver preset configurations."""

    def test_residential_solver(self):
        """Test residential solver preset."""
        config = create_solver_for_residential(min_units=100)

        assert config.objective == OptimizationObjective.MAXIMIZE_UNITS
        assert len(config.constraints) > 0

    def test_balanced_solver(self):
        """Test balanced solver preset."""
        config = create_balanced_solver()

        assert config.objective == OptimizationObjective.BALANCE


class TestOptimizationResult:
    """Tests for OptimizationResult."""

    def test_result_to_dict(self, simple_site, building_footprint):
        """Test result serialization."""
        configs = [
            create_configuration(
                site_boundary=simple_site,
                name="Test",
                id="test1"
            )
        ]
        configs[0].add_element(create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        ))

        result = find_optimal_configuration(configs)
        data = result.to_dict()

        assert "best_configuration" in data
        assert "statistics" in data


class TestOptimizationSummary:
    """Tests for get_optimization_summary function."""

    def test_get_summary(self, simple_site, building_footprint):
        """Test getting optimization summary."""
        configs = [
            create_configuration(
                site_boundary=simple_site,
                name="Test",
                id="test1"
            )
        ]
        configs[0].add_element(create_building_element(
            footprint=building_footprint,
            floors=5,
            total_units=40
        ))

        result = find_optimal_configuration(configs)
        summary = get_optimization_summary(result)

        assert summary["success"] is True
        assert "best" in summary
        assert "statistics" in summary
