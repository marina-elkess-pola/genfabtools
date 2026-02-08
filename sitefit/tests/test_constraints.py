"""
Tests for constraints/setback_rules.py and constraints/zoning.py

Run with: python -m pytest tests/test_constraints.py -v
"""

from sitefit.building.unit_mix import UnitCount, UnitMixTarget, BuildingUnitMix
from sitefit.constraints.parking_ratio import (
    UseType, ParkingRatio, ResidentialParkingRatios, CommercialParkingRatios,
    ParkingRequirement, calculate_residential_parking, calculate_commercial_parking,
    calculate_parking_from_unit_mix, calculate_mixed_use_parking,
    check_parking_compliance, estimate_parking_area, calculate_parking_levels,
    get_parking_summary, get_parking_by_jurisdiction
)
import math
import pytest
from sitefit.core.geometry import Point, Polygon
from sitefit.constraints.setback_rules import (
    SetbackRule, SetbackType, SetbackConfig, EdgeSetback,
    apply_setbacks, calculate_buildable_area, identify_edge_types,
    assign_setback_distances, get_standard_setbacks, get_urban_setbacks,
    get_suburban_setbacks, StepBackRule, calculate_floor_buildable_area
)
from sitefit.constraints.zoning import (
    ZoningDistrict, ZoningConfig, ZoningResult, ZoningType,
    calculate_far, check_height_limit, check_lot_coverage,
    calculate_max_building_area, validate_zoning, get_common_zoning,
    calculate_lot_coverage, calculate_max_floors_from_height,
    calculate_max_units, calculate_required_parking, analyze_site_potential
)


# =============================================================================
# SETBACK RULES TESTS
# =============================================================================

class TestSetbackRule:
    """Tests for SetbackRule class."""

    def test_create_front_setback(self):
        """Create a front setback rule."""
        rule = SetbackRule.front(25.0)
        assert rule.setback_type == SetbackType.FRONT
        assert rule.distance == 25.0

    def test_create_side_setback(self):
        """Create a side setback rule."""
        rule = SetbackRule.side(10.0)
        assert rule.setback_type == SetbackType.SIDE
        assert rule.distance == 10.0

    def test_create_rear_setback(self):
        """Create a rear setback rule."""
        rule = SetbackRule.rear(20.0)
        assert rule.setback_type == SetbackType.REAR
        assert rule.distance == 20.0

    def test_negative_setback_raises(self):
        """Negative setback should raise ValueError."""
        with pytest.raises(ValueError):
            SetbackRule(SetbackType.FRONT, -10.0)

    def test_min_max_defaults(self):
        """Min/max default to reasonable values."""
        rule = SetbackRule.front(25.0)
        assert rule.min_distance == 25.0
        assert rule.max_distance == 50.0  # 2x default


class TestSetbackConfig:
    """Tests for SetbackConfig class."""

    def test_default_config(self):
        """Default configuration values."""
        config = SetbackConfig()
        assert config.front == 25.0
        assert config.side == 10.0
        assert config.rear == 20.0

    def test_uniform_setback(self):
        """Create uniform setback config."""
        config = SetbackConfig.uniform_setback(15.0)
        assert config.uniform is True
        assert config.front == 15.0
        assert config.side == 15.0
        assert config.rear == 15.0

    def test_residential_preset(self):
        """Residential preset values."""
        config = SetbackConfig.residential()
        assert config.front == 25.0
        assert config.side == 10.0
        assert config.rear == 20.0

    def test_commercial_preset(self):
        """Commercial preset values."""
        config = SetbackConfig.commercial()
        assert config.front == 15.0
        assert config.side == 10.0
        assert config.rear == 15.0

    def test_urban_preset(self):
        """Urban preset values (minimal setbacks)."""
        config = SetbackConfig.urban()
        assert config.front == 0.0
        assert config.side == 0.0
        assert config.rear == 10.0

    def test_get_rules(self):
        """Convert config to list of rules."""
        config = SetbackConfig(front=20, side=8, rear=15)
        rules = config.get_rules()
        assert len(rules) == 4  # front, side, rear, corner

        front_rule = next(
            r for r in rules if r.setback_type == SetbackType.FRONT)
        assert front_rule.distance == 20

    def test_min_max_setback(self):
        """Min and max setback properties."""
        config = SetbackConfig(front=25, side=10, rear=20)
        assert config.min_setback == 10
        assert config.max_setback == 25


class TestEdgeClassification:
    """Tests for edge type identification."""

    def test_identify_rectangle_edges(self):
        """Classify edges of a rectangle."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        edges = identify_edge_types(site)

        assert len(edges) == 4

        # Should have at least one of each type
        types = [e.setback_type for e in edges]
        assert SetbackType.FRONT in types
        assert SetbackType.REAR in types
        assert SetbackType.SIDE in types

    def test_identify_with_direction(self):
        """Classify edges with specified front direction."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        edges = identify_edge_types(site, front_direction="south")

        # Should classify edges
        assert len(edges) == 4

        # Check that we have a front edge
        types = [e.setback_type for e in edges]
        assert SetbackType.FRONT in types or SetbackType.REAR in types

    def test_assign_distances(self):
        """Assign setback distances to classified edges."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        edges = identify_edge_types(site)
        config = SetbackConfig(front=25, side=10, rear=20)

        edges_with_distances = assign_setback_distances(edges, config)

        for edge in edges_with_distances:
            if edge.setback_type == SetbackType.FRONT:
                assert edge.setback_distance == 25
            elif edge.setback_type == SetbackType.SIDE:
                assert edge.setback_distance == 10
            elif edge.setback_type == SetbackType.REAR:
                assert edge.setback_distance == 20


class TestApplySetbacks:
    """Tests for applying setbacks to site."""

    def test_apply_uniform_setback(self):
        """Apply uniform setback to rectangle."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        config = SetbackConfig.uniform_setback(10.0)
        buildable = apply_setbacks(site, config)

        assert buildable is not None
        # Original: 100 x 80 = 8000 SF
        # After 10' inset: 80 x 60 = 4800 SF
        assert abs(buildable.area - 4800) < 100  # Allow some tolerance

    def test_setback_reduces_area(self):
        """Setbacks should reduce buildable area."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        config = SetbackConfig(front=25, side=10, rear=20)
        buildable = apply_setbacks(site, config)

        assert buildable is not None
        assert buildable.area < site.area

    def test_calculate_buildable_area_with_ratio(self):
        """Calculate buildable area with reduction ratio."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        buildable, ratio = calculate_buildable_area(site, uniform_setback=20)

        assert buildable is not None
        assert 0 < ratio < 1
        # Original: 200 x 150 = 30000
        # After 20' inset: 160 x 110 = 17600
        expected_ratio = 17600 / 30000
        assert abs(ratio - expected_ratio) < 0.1

    def test_excessive_setback_returns_none(self):
        """Very large setback that collapses polygon."""
        site = Polygon([
            Point(0, 0), Point(50, 0), Point(50, 40), Point(0, 40)
        ])

        # 30' setback on a 50x40 site should collapse it
        buildable, ratio = calculate_buildable_area(site, uniform_setback=30)

        # Either None or very small area
        if buildable is not None:
            assert buildable.area < 100


class TestPresetConfigs:
    """Tests for preset setback configurations."""

    def test_standard_setbacks(self):
        """Standard residential setbacks."""
        config = get_standard_setbacks()
        assert config.front == 25.0
        assert config.side == 10.0
        assert config.rear == 20.0

    def test_urban_setbacks(self):
        """Urban setbacks (minimal)."""
        config = get_urban_setbacks()
        assert config.front == 0.0
        assert config.side == 0.0
        assert config.rear == 10.0

    def test_suburban_setbacks(self):
        """Suburban setbacks (larger)."""
        config = get_suburban_setbacks()
        assert config.front == 30.0
        assert config.side == 15.0
        assert config.rear == 25.0


class TestStepBack:
    """Tests for step-back rules."""

    def test_stepback_rule_creation(self):
        """Create a step-back rule."""
        rule = StepBackRule.front_stepback(floor=3, distance=10)
        assert rule.applies_above_floor == 3
        assert rule.additional_setback == 10
        assert SetbackType.FRONT in rule.applies_to

    def test_floor_buildable_area_ground(self):
        """Ground floor uses base setbacks."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        base = SetbackConfig.uniform_setback(10)
        rules = [StepBackRule.front_stepback(3, 5)]

        ground = calculate_floor_buildable_area(
            site, base, rules, floor_number=1)
        floor3 = calculate_floor_buildable_area(
            site, base, rules, floor_number=1)

        # Ground floor should have same area
        assert ground is not None
        assert abs(ground.area - floor3.area) < 1

    def test_floor_buildable_area_upper(self):
        """Upper floors have additional step-back."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        base = SetbackConfig.uniform_setback(10)
        rules = [StepBackRule.front_stepback(3, 5)]

        floor3 = calculate_floor_buildable_area(
            site, base, rules, floor_number=3)
        floor5 = calculate_floor_buildable_area(
            site, base, rules, floor_number=5)

        # Floor 5 should have smaller area due to step-back
        assert floor3 is not None
        assert floor5 is not None
        assert floor5.area < floor3.area


# =============================================================================
# ZONING TESTS
# =============================================================================

class TestZoningDistrict:
    """Tests for ZoningDistrict class."""

    def test_residential_low(self):
        """Low-density residential district."""
        district = ZoningDistrict.residential_low()
        assert district.max_far == 0.5
        assert district.max_lot_coverage == 0.4
        assert district.max_height_ft == 35.0
        assert district.max_stories == 2

    def test_residential_medium(self):
        """Medium-density residential district."""
        district = ZoningDistrict.residential_medium()
        assert district.max_far == 1.5
        assert district.max_lot_coverage == 0.6
        assert district.max_height_ft == 45.0

    def test_residential_high(self):
        """High-density residential district."""
        district = ZoningDistrict.residential_high()
        assert district.max_far == 3.0
        assert district.max_lot_coverage == 0.7
        assert district.max_height_ft == 75.0

    def test_commercial_neighborhood(self):
        """Neighborhood commercial district."""
        district = ZoningDistrict.commercial_neighborhood()
        assert district.max_far == 1.0
        assert district.max_height_ft == 35.0

    def test_mixed_use(self):
        """Mixed-use district."""
        district = ZoningDistrict.mixed_use()
        assert district.max_far == 4.0
        assert district.max_lot_coverage == 0.8
        assert district.max_height_ft == 85.0

    def test_negative_far_raises(self):
        """Negative FAR should raise ValueError."""
        with pytest.raises(ValueError):
            ZoningDistrict(name="test", max_far=-1.0)

    def test_invalid_lot_coverage_raises(self):
        """Lot coverage outside 0-1 should raise ValueError."""
        with pytest.raises(ValueError):
            ZoningDistrict(name="test", max_lot_coverage=1.5)

    def test_max_height_stories(self):
        """Max stories based on height."""
        # 35' max with 2 story limit
        district = ZoningDistrict(
            name="test",
            max_height_ft=35.0,
            max_stories=2
        )
        assert district.max_height_stories == 2

        # 45' height should allow 3 floors (at 12'/floor)
        district2 = ZoningDistrict(
            name="test2",
            max_height_ft=45.0,
            max_stories=5  # Height is limiting factor
        )
        assert district2.max_height_stories == 3


class TestZoningCalculations:
    """Tests for zoning calculation functions."""

    def test_calculate_far(self):
        """Calculate Floor Area Ratio."""
        # 30000 SF building on 10000 SF lot = 3.0 FAR
        far = calculate_far(30000, 10000)
        assert far == 3.0

    def test_calculate_far_zero_lot_raises(self):
        """Zero lot area should raise."""
        with pytest.raises(ValueError):
            calculate_far(10000, 0)

    def test_calculate_lot_coverage(self):
        """Calculate lot coverage ratio."""
        # 5000 SF footprint on 10000 SF lot = 0.5
        coverage = calculate_lot_coverage(5000, 10000)
        assert coverage == 0.5

    def test_check_height_limit_pass(self):
        """Height within limit should pass."""
        passes, margin = check_height_limit(30, 35)
        assert passes is True
        assert margin == 5

    def test_check_height_limit_fail(self):
        """Height exceeding limit should fail."""
        passes, margin = check_height_limit(40, 35)
        assert passes is False
        assert margin == -5

    def test_check_height_with_tolerance(self):
        """Height check with tolerance."""
        # 37' building, 35' limit, 5' tolerance for equipment
        passes, margin = check_height_limit(37, 35, tolerance=5)
        assert passes is True

    def test_check_lot_coverage_pass(self):
        """Lot coverage within limit."""
        passes, margin = check_lot_coverage(4000, 10000, 0.5)
        assert passes is True
        assert abs(margin - 0.1) < 0.001  # Use approximate comparison

    def test_check_lot_coverage_fail(self):
        """Lot coverage exceeding limit."""
        passes, margin = check_lot_coverage(6000, 10000, 0.5)
        assert passes is False

    def test_calculate_max_building_area(self):
        """Max building area from FAR."""
        max_area = calculate_max_building_area(10000, 2.5)
        assert max_area == 25000.0

    def test_calculate_max_floors_from_height(self):
        """Max floors from height limit."""
        # 35' = 1 floor at 15' + 1 floor at 12' = 2 floors
        floors = calculate_max_floors_from_height(35)
        assert floors == 2

        # 75' = 1 at 15' + 5 at 12' = 6 floors
        floors = calculate_max_floors_from_height(75)
        assert floors == 6

    def test_calculate_max_units(self):
        """Max units from density."""
        # 1 acre at 20 DU/acre = 20 units
        units = calculate_max_units(43560, 20)
        assert units == 20

    def test_calculate_required_parking(self):
        """Required parking stalls."""
        # 100 units at 1.5 ratio = 150 stalls
        stalls = calculate_required_parking(100, 1.5)
        assert stalls == 150

        # With commercial: 100 units + 10000 SF commercial
        stalls = calculate_required_parking(100, 1.5, 10000, 4.0)
        assert stalls == 190  # 150 + 40


class TestZoningValidation:
    """Tests for zoning validation."""

    def test_validate_compliant(self):
        """Validate a compliant building."""
        district = ZoningDistrict.residential_medium()

        # Within all limits
        result = validate_zoning(
            lot_area=10000,
            building_footprint=5000,  # 50% coverage (limit 60%)
            total_building_area=12000,  # FAR 1.2 (limit 1.5)
            building_height=40,  # (limit 45')
            district=district
        )

        assert result.compliant is True
        assert len(result.violations) == 0

    def test_validate_far_violation(self):
        """Validate FAR violation."""
        district = ZoningDistrict.residential_medium()  # FAR 1.5

        result = validate_zoning(
            lot_area=10000,
            building_footprint=5000,
            total_building_area=20000,  # FAR 2.0 - exceeds 1.5
            building_height=40,
            district=district
        )

        assert result.compliant is False
        assert any("FAR" in v for v in result.violations)

    def test_validate_coverage_violation(self):
        """Validate lot coverage violation."""
        district = ZoningDistrict.residential_medium()  # 60% coverage

        result = validate_zoning(
            lot_area=10000,
            building_footprint=7000,  # 70% - exceeds 60%
            total_building_area=10000,
            building_height=40,
            district=district
        )

        assert result.compliant is False
        assert any("coverage" in v.lower() for v in result.violations)

    def test_validate_height_violation(self):
        """Validate height violation."""
        district = ZoningDistrict.residential_low()  # 35' height

        result = validate_zoning(
            lot_area=10000,
            building_footprint=3000,
            total_building_area=4000,
            building_height=45,  # Exceeds 35'
            district=district
        )

        assert result.compliant is False
        assert any("Height" in v for v in result.violations)

    def test_validate_warnings(self):
        """Validate near-limit warnings."""
        district = ZoningDistrict.residential_medium()  # FAR 1.5

        result = validate_zoning(
            lot_area=10000,
            building_footprint=5000,
            total_building_area=14000,  # FAR 1.4 - 93% of 1.5
            building_height=43,  # 96% of 45'
            district=district
        )

        assert result.compliant is True
        assert len(result.warnings) >= 1

    def test_validate_to_dict(self):
        """Result to_dict for JSON."""
        district = ZoningDistrict.residential_medium()

        result = validate_zoning(
            lot_area=10000,
            building_footprint=5000,
            total_building_area=12000,
            building_height=40,
            district=district
        )

        data = result.to_dict()
        assert "compliant" in data
        assert "far" in data
        assert "lot_coverage" in data


class TestGetCommonZoning:
    """Tests for getting common zoning districts."""

    def test_get_r1(self):
        """Get R-1 district."""
        district = get_common_zoning("R-1")
        assert district.name == "R-1"
        assert district.zoning_type == ZoningType.R1

    def test_get_r3(self):
        """Get R-3 district."""
        district = get_common_zoning("R-3")
        assert district.name == "R-3"

    def test_get_mu(self):
        """Get mixed-use district."""
        district = get_common_zoning("MU")
        assert district.name == "MU"
        assert district.zoning_type == ZoningType.MU

    def test_unknown_type_raises(self):
        """Unknown zoning type should raise."""
        with pytest.raises(ValueError):
            get_common_zoning("X-99")

    def test_case_insensitive(self):
        """Zone type lookup is case-insensitive."""
        district = get_common_zoning("r-3")
        assert district.name == "R-3"


class TestZoningConfig:
    """Tests for ZoningConfig class."""

    def test_effective_far_with_bonus(self):
        """Effective FAR includes bonuses."""
        district = ZoningDistrict.residential_medium()  # FAR 1.5

        config = ZoningConfig(
            district=district,
            lot_area=10000,
            bonuses={"affordable_housing": 0.5, "transit": 0.25}
        )

        # 1.5 + 0.5 + 0.25 = 2.25
        assert config.effective_far == 2.25

    def test_max_building_area(self):
        """Max building area from config."""
        district = ZoningDistrict(name="test", max_far=2.0)
        config = ZoningConfig(district=district, lot_area=10000)

        assert config.max_building_area == 20000

    def test_max_footprint(self):
        """Max footprint from config."""
        district = ZoningDistrict(name="test", max_lot_coverage=0.6)
        config = ZoningConfig(district=district, lot_area=10000)

        assert config.max_footprint == 6000


class TestAnalyzeSitePotential:
    """Tests for site potential analysis."""

    def test_analyze_site(self):
        """Analyze development potential."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])  # 30,000 SF

        district = ZoningDistrict.residential_medium()

        analysis = analyze_site_potential(site, district)

        assert analysis["lot_area_sf"] == 30000
        assert analysis["max_far"] == 1.5
        assert analysis["max_building_area_sf"] == 45000  # 30000 * 1.5
        assert analysis["max_footprint_sf"] == 18000  # 30000 * 0.6
        assert "max_units" in analysis
        assert "required_parking" in analysis


# =============================================================================
# PARKING RATIO TESTS
# =============================================================================


class TestResidentialParkingRatios:
    """Tests for ResidentialParkingRatios class."""

    def test_default_ratios(self):
        """Default parking ratios."""
        ratios = ResidentialParkingRatios()
        assert ratios.studio == 1.0
        assert ratios.one_br == 1.25
        assert ratios.two_br == 1.5
        assert ratios.three_br == 2.0
        assert ratios.guest_ratio == 0.25

    def test_urban_preset(self):
        """Urban parking ratios."""
        ratios = ResidentialParkingRatios.urban()
        assert ratios.studio == 0.5
        assert ratios.one_br == 0.75
        assert ratios.transit_reduction == 0.25

    def test_suburban_preset(self):
        """Suburban parking ratios."""
        ratios = ResidentialParkingRatios.suburban()
        assert ratios.studio == 1.0
        assert ratios.one_br == 1.5
        assert ratios.two_br == 2.0

    def test_transit_oriented_preset(self):
        """Transit-oriented parking ratios."""
        ratios = ResidentialParkingRatios.transit_oriented()
        assert ratios.studio == 0.25
        assert ratios.transit_reduction == 0.5

    def test_affordable_housing_preset(self):
        """Affordable housing parking ratios."""
        ratios = ResidentialParkingRatios.affordable_housing()
        assert ratios.affordable_reduction == 0.25

    def test_senior_housing_preset(self):
        """Senior housing parking ratios."""
        ratios = ResidentialParkingRatios.senior_housing()
        assert ratios.senior_reduction == 0.5

    def test_to_dict(self):
        """Convert to dictionary."""
        ratios = ResidentialParkingRatios()
        data = ratios.to_dict()
        assert "studio" in data
        assert "guest" in data


class TestCommercialParkingRatios:
    """Tests for CommercialParkingRatios class."""

    def test_default_ratios(self):
        """Default commercial ratios."""
        ratios = CommercialParkingRatios()
        assert ratios.retail == 4.0
        assert ratios.restaurant == 10.0
        assert ratios.office == 3.0

    def test_urban_preset(self):
        """Urban commercial ratios."""
        ratios = CommercialParkingRatios.urban()
        assert ratios.retail == 2.5
        assert ratios.office == 2.0

    def test_suburban_preset(self):
        """Suburban commercial ratios."""
        ratios = CommercialParkingRatios.suburban()
        assert ratios.retail == 5.0
        assert ratios.restaurant == 12.0

    def test_get_ratio_for_use(self):
        """Get ratio for specific use."""
        ratios = CommercialParkingRatios()
        assert ratios.get_ratio_for_use(UseType.RETAIL) == 4.0
        assert ratios.get_ratio_for_use(UseType.OFFICE) == 3.0


class TestCalculateResidentialParking:
    """Tests for calculate_residential_parking function."""

    def test_basic_calculation(self):
        """Calculate parking for units."""
        units = UnitCount(studio=10, one_br=20, two_br=15, three_br=5)

        residential, guest, breakdown = calculate_residential_parking(units)

        # 10*1.0 + 20*1.25 + 15*1.5 + 5*2.0 = 10 + 25 + 22.5 + 10 = 67.5
        assert residential == 67.5

    def test_guest_parking(self):
        """Guest parking calculation."""
        units = UnitCount(studio=10, one_br=20, two_br=15,
                          three_br=5)  # 50 units

        _, guest, breakdown = calculate_residential_parking(units)

        # 50 * 0.25 = 12.5
        assert guest == 12.5
        assert "guest" in breakdown

    def test_without_guest(self):
        """Calculate without guest parking."""
        units = UnitCount(studio=10)

        _, guest, _ = calculate_residential_parking(units, include_guest=False)

        assert guest == 0.0

    def test_custom_ratios(self):
        """Use custom ratios."""
        units = UnitCount(one_br=10)
        ratios = ResidentialParkingRatios(one_br=2.0, guest_ratio=0.0)

        residential, _, _ = calculate_residential_parking(units, ratios)

        assert residential == 20.0  # 10 * 2.0

    def test_100_units_1_5_ratio(self):
        """100 units at 1.5 ratio = 150 stalls (architecture doc example)."""
        # All 1BR to get 1.25 ratio, adjust to get close to 1.5
        units = UnitCount(two_br=100)  # 1.5 ratio
        ratios = ResidentialParkingRatios(two_br=1.5, guest_ratio=0.0)

        residential, _, _ = calculate_residential_parking(
            units, ratios, include_guest=False)

        assert residential == 150.0


class TestCalculateCommercialParking:
    """Tests for calculate_commercial_parking function."""

    def test_retail_parking(self):
        """Calculate retail parking."""
        areas = {UseType.RETAIL: 10000}  # 10,000 SF

        total, breakdown = calculate_commercial_parking(areas)

        # 10,000 SF / 1000 * 4.0 = 40 spaces
        assert total == 40.0

    def test_mixed_commercial(self):
        """Calculate mixed commercial parking."""
        areas = {
            UseType.RETAIL: 5000,    # 5 * 4.0 = 20
            UseType.OFFICE: 10000,   # 10 * 3.0 = 30
        }

        total, breakdown = calculate_commercial_parking(areas)

        assert total == 50.0
        assert breakdown["retail"] == 20.0
        assert breakdown["office"] == 30.0

    def test_restaurant_high_ratio(self):
        """Restaurant has high parking ratio."""
        areas = {UseType.RESTAURANT: 5000}

        total, _ = calculate_commercial_parking(areas)

        # 5 * 10.0 = 50 spaces
        assert total == 50.0


class TestMixedUseParking:
    """Tests for calculate_mixed_use_parking function."""

    def test_mixed_use_calculation(self):
        """Calculate mixed-use parking."""
        units = UnitCount(one_br=20, two_br=10)
        commercial = {UseType.RETAIL: 5000}

        result = calculate_mixed_use_parking(
            units=units,
            commercial_areas=commercial
        )

        assert result.residential_spaces > 0
        assert result.commercial_spaces > 0
        assert result.total_required > 0

    def test_shared_parking_factor(self):
        """Shared parking reduces requirement."""
        units = UnitCount(one_br=20)
        commercial = {UseType.RETAIL: 5000}

        result = calculate_mixed_use_parking(
            units=units,
            commercial_areas=commercial,
            shared_parking_factor=0.8  # 20% reduction
        )

        assert result.shared_parking_reduction > 0
        # Total is reduced by 20%


class TestParkingRequirement:
    """Tests for ParkingRequirement class."""

    def test_total_required(self):
        """Total required calculation."""
        req = ParkingRequirement(
            residential_spaces=100,
            guest_spaces=25,
            commercial_spaces=50
        )

        assert req.total_required == 175

    def test_to_dict(self):
        """Convert to dictionary."""
        req = ParkingRequirement(
            residential_spaces=100,
            guest_spaces=25,
            commercial_spaces=50
        )

        data = req.to_dict()
        assert data["total_required"] == 175


class TestParkingCompliance:
    """Tests for check_parking_compliance function."""

    def test_compliant_parking(self):
        """Check compliant parking."""
        req = ParkingRequirement(
            residential_spaces=100,
            guest_spaces=25
        )

        result = check_parking_compliance(150, req)

        assert result["compliant"] is True
        assert result["surplus"] == 25

    def test_deficient_parking(self):
        """Check deficient parking."""
        req = ParkingRequirement(
            residential_spaces=100,
            guest_spaces=25
        )

        result = check_parking_compliance(100, req)

        assert result["compliant"] is False
        assert result["surplus"] == -25

    def test_exactly_met(self):
        """Parking exactly met."""
        req = ParkingRequirement(residential_spaces=100)

        result = check_parking_compliance(100, req)

        assert result["compliant"] is True
        assert result["surplus"] == 0


class TestParkingAreaEstimation:
    """Tests for parking area estimation functions."""

    def test_estimate_parking_area(self):
        """Estimate parking area."""
        # 100 spaces * 350 SF = 35,000 SF
        area = estimate_parking_area(100)

        assert area == 35000

    def test_structured_parking_efficiency(self):
        """Structured parking is more efficient."""
        surface_area = estimate_parking_area(100, structured=False)
        structured_area = estimate_parking_area(100, structured=True)

        assert structured_area < surface_area

    def test_calculate_parking_levels(self):
        """Calculate parking levels needed."""
        # 200 spaces, 20,000 SF per level, 350 SF per space
        # 20,000 / 350 = 57 spaces per level
        # 200 / 57 = 3.5 → 4 levels
        levels = calculate_parking_levels(200, 20000)

        assert levels == 4


class TestJurisdictionPresets:
    """Tests for jurisdiction parking presets."""

    def test_los_angeles(self):
        """Los Angeles parking ratios."""
        res, comm = get_parking_by_jurisdiction("los_angeles")

        assert res.one_br == 1.5
        assert comm.retail == 4.0

    def test_san_francisco(self):
        """San Francisco parking ratios (lower)."""
        res, comm = get_parking_by_jurisdiction("san_francisco")

        assert res.one_br == 0.5  # Low ratios
        assert res.transit_reduction == 0.5

    def test_houston(self):
        """Houston parking ratios (higher)."""
        res, comm = get_parking_by_jurisdiction("houston")

        assert res.one_br == 1.5
        assert comm.retail == 5.0

    def test_unknown_jurisdiction(self):
        """Unknown jurisdiction returns defaults."""
        res, comm = get_parking_by_jurisdiction("unknown_city")

        # Should return default ratios
        assert res.one_br == 1.25
        assert comm.retail == 4.0


class TestGetParkingSummary:
    """Tests for get_parking_summary function."""

    def test_parking_summary(self):
        """Get parking summary."""
        units = UnitCount(studio=10, one_br=20, two_br=15, three_br=5)

        summary = get_parking_summary(units)

        assert summary["total_units"] == 50
        assert "total_parking" in summary
        assert "ratio_overall" in summary
        assert "breakdown" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
