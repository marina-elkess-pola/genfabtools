"""
Tests for building/floor_plate.py and building/setbacks.py

Run with: python -m pytest tests/test_building.py -v
"""

from sitefit.building.unit_mix import (
    UnitType, UnitSpec, UnitMixTarget, UnitCount,
    FloorUnitMix, BuildingUnitMix,
    calculate_units_for_area, calculate_floor_unit_mix,
    calculate_building_unit_mix, get_default_unit_specs,
    estimate_units_from_area, calculate_avg_unit_size,
    calculate_required_parking_from_units, get_unit_mix_summary,
    optimize_unit_mix_for_target_count
)
from sitefit.building.massing import (
    MassingType, StepBack, MassingConfig, BuildingMass,
    generate_massing, generate_bar_massing, generate_podium_tower_massing,
    generate_stepped_massing, generate_massing_from_zoning,
    generate_massing_to_target, calculate_far_utilization,
    estimate_additional_floors, compare_massings, get_massing_summary
)
import math
import pytest
from sitefit.core.geometry import Point, Polygon
from sitefit.building.floor_plate import (
    FloorPlate, FloorType, FloorConfig,
    create_floor_plate, create_floor_plates, create_uniform_floor_plates,
    calculate_gross_area, calculate_net_area, calculate_efficiency,
    calculate_total_height, calculate_floor_area_by_type, get_floor_summary,
    check_floor_depth, estimate_units_per_floor
)
from sitefit.building.setbacks import (
    BuildableArea, BuildableAreaResult, BuildingTypology,
    calculate_buildable_envelope, apply_building_setbacks,
    get_buildable_area_for_floor, calculate_step_backs,
    calculate_max_building_area, estimate_floor_count,
    check_building_envelope_compliance
)
from sitefit.constraints.setback_rules import SetbackConfig, StepBackRule
from sitefit.constraints.zoning import ZoningDistrict


# =============================================================================
# FLOOR CONFIG TESTS
# =============================================================================

class TestFloorConfig:
    """Tests for FloorConfig class."""

    def test_default_config(self):
        """Default configuration values."""
        config = FloorConfig()
        assert config.floor_to_floor_height == 10.0
        assert config.ground_floor_height == 15.0
        assert config.efficiency == 0.85

    def test_residential_preset(self):
        """Residential configuration preset."""
        config = FloorConfig.residential()
        assert config.floor_to_floor_height == 10.0
        assert config.efficiency == 0.85

    def test_office_preset(self):
        """Office configuration preset."""
        config = FloorConfig.office()
        assert config.floor_to_floor_height == 13.0
        assert config.efficiency == 0.80

    def test_retail_preset(self):
        """Retail configuration preset."""
        config = FloorConfig.retail()
        assert config.floor_to_floor_height == 15.0
        assert config.efficiency == 0.90

    def test_hotel_preset(self):
        """Hotel configuration preset."""
        config = FloorConfig.hotel()
        assert config.floor_to_floor_height == 11.0
        assert config.efficiency == 0.80

    def test_net_ratio(self):
        """Net ratio calculation."""
        config = FloorConfig(core_area_ratio=0.08, corridor_ratio=0.07)
        assert abs(config.net_ratio - 0.85) < 0.001


# =============================================================================
# FLOOR PLATE TESTS
# =============================================================================

class TestFloorPlate:
    """Tests for FloorPlate class."""

    def test_create_from_polygon(self):
        """Create floor plate from polygon."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floor = FloorPlate.from_polygon(polygon, floor_number=1)

        assert floor.floor_number == 1
        assert floor.floor_type == FloorType.GROUND
        assert floor.gross_area == 8000.0

    def test_create_from_rectangle(self):
        """Create rectangular floor plate."""
        floor = FloorPlate.from_rectangle(100, 80, floor_number=2)

        assert floor.width == 100.0
        assert floor.depth == 80.0
        assert floor.gross_area == 8000.0
        assert floor.floor_type == FloorType.TYPICAL

    def test_gross_area(self):
        """Gross area calculation."""
        floor = FloorPlate.from_rectangle(100, 80)
        assert floor.gross_area == 8000.0

    def test_net_area(self):
        """Net area with efficiency."""
        config = FloorConfig(efficiency=0.85)
        floor = FloorPlate.from_rectangle(100, 80, config=config)

        assert floor.net_area == 8000.0 * 0.85

    def test_core_area(self):
        """Core area calculation."""
        config = FloorConfig(core_area_ratio=0.08)
        floor = FloorPlate.from_rectangle(100, 80, config=config)

        assert floor.core_area == 8000.0 * 0.08

    def test_corridor_area(self):
        """Corridor area calculation."""
        config = FloorConfig(corridor_ratio=0.07)
        floor = FloorPlate.from_rectangle(100, 80, config=config)

        assert floor.corridor_area == 8000.0 * 0.07

    def test_perimeter(self):
        """Perimeter calculation."""
        floor = FloorPlate.from_rectangle(100, 80)
        assert floor.perimeter == 360.0  # 2*(100+80)

    def test_elevation_ground(self):
        """Ground floor elevation is 0."""
        floor = FloorPlate.from_rectangle(100, 80, floor_number=1)
        assert floor.elevation == 0.0

    def test_elevation_upper(self):
        """Upper floor elevation calculation."""
        config = FloorConfig(ground_floor_height=15, floor_to_floor_height=10)
        floor = FloorPlate.from_rectangle(
            100, 80, floor_number=3, config=config)

        # Floor 3: ground (15') + floor 2 (10') = 25'
        assert floor.elevation == 25.0

    def test_is_ground_floor(self):
        """Ground floor detection."""
        floor1 = FloorPlate.from_rectangle(100, 80, floor_number=1)
        floor2 = FloorPlate.from_rectangle(100, 80, floor_number=2)

        assert floor1.is_ground_floor is True
        assert floor2.is_ground_floor is False

    def test_floor_number_validation(self):
        """Floor number must be >= 1."""
        with pytest.raises(ValueError):
            FloorPlate.from_rectangle(100, 80, floor_number=0)

    def test_floor_height_validation(self):
        """Floor height must be positive."""
        polygon = Polygon([Point(0, 0), Point(100, 0),
                          Point(100, 80), Point(0, 80)])
        with pytest.raises(ValueError):
            FloorPlate(polygon, floor_number=1, floor_height=-10)

    def test_to_dict(self):
        """Convert to dictionary."""
        floor = FloorPlate.from_rectangle(100, 80, floor_number=1)
        data = floor.to_dict()

        assert "floor_number" in data
        assert "gross_area" in data
        assert "net_area" in data
        assert "efficiency" in data
        assert data["floor_number"] == 1
        assert data["gross_area"] == 8000.0

    def test_get_usable_polygon(self):
        """Get usable area polygon."""
        floor = FloorPlate.from_rectangle(100, 80, floor_number=1)
        usable = floor.get_usable_polygon()

        assert usable is not None
        assert usable.area < floor.gross_area


# =============================================================================
# FLOOR PLATE CREATION TESTS
# =============================================================================

class TestFloorPlateCreation:
    """Tests for floor plate creation functions."""

    def test_create_floor_plate(self):
        """Create single floor plate."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floor = create_floor_plate(polygon, floor_number=2)

        assert floor.floor_number == 2
        assert floor.gross_area == 8000.0

    def test_create_floor_plates(self):
        """Create multiple floor plates."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floors = create_floor_plates([polygon, polygon, polygon])

        assert len(floors) == 3
        assert floors[0].floor_number == 1
        assert floors[1].floor_number == 2
        assert floors[2].floor_number == 3
        assert floors[0].floor_type == FloorType.GROUND
        assert floors[1].floor_type == FloorType.TYPICAL

    def test_create_uniform_floor_plates(self):
        """Create uniform floor plates."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floors = create_uniform_floor_plates(polygon, num_floors=5)

        assert len(floors) == 5
        for i, floor in enumerate(floors):
            assert floor.floor_number == i + 1
            assert floor.gross_area == 8000.0


# =============================================================================
# AREA CALCULATION TESTS
# =============================================================================

class TestAreaCalculations:
    """Tests for area calculation functions."""

    def test_calculate_gross_area(self):
        """Total gross floor area."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floors = create_uniform_floor_plates(polygon, num_floors=5)

        total = calculate_gross_area(floors)
        assert total == 8000.0 * 5

    def test_calculate_net_area(self):
        """Total net floor area."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = FloorConfig(efficiency=0.85)
        floors = create_uniform_floor_plates(
            polygon, num_floors=5, config=config)

        total = calculate_net_area(floors)
        assert total == 8000.0 * 5 * 0.85

    def test_calculate_efficiency(self):
        """Overall efficiency."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = FloorConfig(efficiency=0.85)
        floors = create_uniform_floor_plates(
            polygon, num_floors=5, config=config)

        eff = calculate_efficiency(floors)
        assert abs(eff - 0.85) < 0.001

    def test_calculate_total_height(self):
        """Total building height."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = FloorConfig(floor_to_floor_height=10, ground_floor_height=15)
        floors = create_uniform_floor_plates(
            polygon, num_floors=5, config=config)

        # Floor 1: 15', Floors 2-5: 10' each = 15 + 40 = 55'
        height = calculate_total_height(floors)
        # Actually each floor stores its own height
        # Ground: 15, typical (4): 10 each = 55
        assert height == 55.0

    def test_calculate_floor_area_by_type(self):
        """Area breakdown by floor type."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floors = create_uniform_floor_plates(polygon, num_floors=5)

        by_type = calculate_floor_area_by_type(floors)

        assert FloorType.GROUND in by_type
        assert FloorType.TYPICAL in by_type
        assert by_type[FloorType.GROUND] == 8000.0
        assert by_type[FloorType.TYPICAL] == 8000.0 * 4

    def test_get_floor_summary(self):
        """Floor summary statistics."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        floors = create_uniform_floor_plates(polygon, num_floors=5)

        summary = get_floor_summary(floors)

        assert summary["num_floors"] == 5
        assert summary["total_gross_sf"] == 40000
        assert "efficiency" in summary
        assert "avg_floor_area" in summary


# =============================================================================
# FLOOR ANALYSIS TESTS
# =============================================================================

class TestFloorAnalysis:
    """Tests for floor plate analysis functions."""

    def test_check_floor_depth_pass(self):
        """Floor depth within limits."""
        floor = FloorPlate.from_rectangle(100, 60)

        passes, depth = check_floor_depth(floor, max_depth=40)

        assert passes is True
        assert depth == 30.0  # 60/2

    def test_check_floor_depth_fail(self):
        """Floor depth exceeds limits."""
        floor = FloorPlate.from_rectangle(100, 100)

        passes, depth = check_floor_depth(floor, max_depth=40)

        assert passes is False
        assert depth == 50.0  # 100/2

    def test_estimate_units_per_floor(self):
        """Estimate unit count."""
        floor = FloorPlate.from_rectangle(100, 80)  # 8000 SF

        # 8000 * 0.85 / 850 = 8 units
        units = estimate_units_per_floor(floor, avg_unit_size=850)

        assert units == 8


# =============================================================================
# BUILDABLE AREA TESTS
# =============================================================================

class TestBuildableArea:
    """Tests for BuildableArea class."""

    def test_buildable_area_creation(self):
        """Create buildable area."""
        polygon = Polygon([
            Point(0, 0), Point(80, 0), Point(80, 60), Point(0, 60)
        ])
        buildable = BuildableArea(polygon, floor_range=(1, 5))

        assert buildable.area == 4800.0
        assert buildable.min_floor == 1
        assert buildable.max_floor == 5

    def test_applies_to_floor(self):
        """Check floor applicability."""
        polygon = Polygon([
            Point(0, 0), Point(80, 0), Point(80, 60), Point(0, 60)
        ])
        buildable = BuildableArea(polygon, floor_range=(3, 6))

        assert buildable.applies_to_floor(3) is True
        assert buildable.applies_to_floor(5) is True
        assert buildable.applies_to_floor(2) is False
        assert buildable.applies_to_floor(7) is False

    def test_to_dict(self):
        """Convert to dictionary."""
        polygon = Polygon([
            Point(0, 0), Point(80, 0), Point(80, 60), Point(0, 60)
        ])
        buildable = BuildableArea(polygon, floor_range=(1, 5))
        data = buildable.to_dict()

        assert "area_sf" in data
        assert "floor_range" in data


# =============================================================================
# BUILDABLE ENVELOPE TESTS
# =============================================================================

class TestBuildableEnvelope:
    """Tests for buildable envelope calculation."""

    def test_calculate_buildable_envelope(self):
        """Calculate buildable envelope."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig(front=25, side=10, rear=20)

        result = calculate_buildable_envelope(site, setbacks)

        assert result.site_area == 30000.0
        assert result.ground_buildable_area < result.site_area
        assert result.coverage_ratio < 1.0

    def test_envelope_with_zoning(self):
        """Envelope with zoning limits."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig(front=25, side=10, rear=20)
        zoning = ZoningDistrict.residential_medium()

        result = calculate_buildable_envelope(site, setbacks, zoning)

        assert result.max_height == 45.0
        assert result.max_floors == 4

    def test_get_buildable_for_floor(self):
        """Get buildable for specific floor."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()

        result = calculate_buildable_envelope(site, setbacks)

        floor1 = result.get_buildable_for_floor(1)
        floor5 = result.get_buildable_for_floor(5)

        assert floor1 is not None
        assert floor5 is not None

    def test_envelope_to_dict(self):
        """Convert envelope to dictionary."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        result = calculate_buildable_envelope(site)

        data = result.to_dict()

        assert "site_area" in data
        assert "ground_buildable_area" in data
        assert "coverage_ratio" in data


# =============================================================================
# BUILDING SETBACK TESTS
# =============================================================================

class TestBuildingSetbacks:
    """Tests for building setback functions."""

    def test_apply_building_setbacks(self):
        """Apply setbacks to site."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        buildable = apply_building_setbacks(site, front=20, side=10, rear=15)

        assert buildable is not None
        assert buildable.area < site.area

    def test_apply_uniform_setbacks(self):
        """Apply uniform setbacks."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        buildable = apply_building_setbacks(site, front=10, uniform=True)

        assert buildable is not None
        # 100x80 - 10 all around = 80x60 = 4800
        assert abs(buildable.area - 4800) < 100

    def test_get_buildable_area_for_floor(self):
        """Get buildable for specific floor."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()

        floor1 = get_buildable_area_for_floor(site, 1, setbacks)
        floor5 = get_buildable_area_for_floor(site, 5, setbacks)

        assert floor1 is not None
        assert floor5 is not None

    def test_calculate_step_backs(self):
        """Calculate step-back polygons."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()

        polygons = calculate_step_backs(
            site, setbacks,
            step_back_floors=[3, 6],
            step_back_distances=[10, 15]
        )

        assert len(polygons) >= 1
        # Each step-back should be smaller
        for i in range(1, len(polygons)):
            assert polygons[i].area < polygons[i-1].area


# =============================================================================
# MAX BUILDING AREA TESTS
# =============================================================================

class TestMaxBuildingArea:
    """Tests for max building area calculation."""

    def test_calculate_max_building_area(self):
        """Calculate max building area."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()
        zoning = ZoningDistrict.residential_medium()

        result = calculate_max_building_area(site, setbacks, zoning)

        assert "site_area" in result
        assert "buildable_area" in result
        assert "max_floors" in result
        assert "max_building_area" in result
        assert result["max_building_area"] > 0

    def test_estimate_floor_count(self):
        """Estimate floor count."""
        floors = estimate_floor_count(
            total_building_area=40000,
            floor_plate_area=8000
        )

        assert floors == 5

    def test_estimate_floor_count_with_limit(self):
        """Floor count limited by max."""
        floors = estimate_floor_count(
            total_building_area=40000,
            floor_plate_area=8000,
            max_floors=3
        )

        assert floors == 3


# =============================================================================
# ENVELOPE COMPLIANCE TESTS
# =============================================================================

class TestEnvelopeCompliance:
    """Tests for envelope compliance checking."""

    def test_compliant_building(self):
        """Check compliant building."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()
        zoning = ZoningDistrict.residential_medium()

        # Small building within limits
        building = Polygon([
            Point(30, 30), Point(170, 30), Point(170, 120), Point(30, 120)
        ])

        result = check_building_envelope_compliance(
            site, building, building_height=40,
            setbacks=setbacks, zoning=zoning
        )

        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    def test_height_violation(self):
        """Check height violation."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()
        zoning = ZoningDistrict.residential_medium()  # 45' limit

        building = Polygon([
            Point(30, 30), Point(170, 30), Point(170, 120), Point(30, 120)
        ])

        result = check_building_envelope_compliance(
            site, building, building_height=60,  # Exceeds 45'
            setbacks=setbacks, zoning=zoning
        )

        assert result["compliant"] is False
        assert any("height" in v.lower() for v in result["violations"])

    def test_coverage_violation(self):
        """Check lot coverage violation."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)
        ])  # 10,000 SF
        setbacks = SetbackConfig(front=5, side=5, rear=5)
        zoning = ZoningDistrict.residential_low()  # 40% coverage

        # Building covers 80% of site
        building = Polygon([
            Point(10, 10), Point(90, 10), Point(90, 100), Point(10, 100)
        ])  # 7200 SF = 72%

        result = check_building_envelope_compliance(
            site, building, building_height=30,
            setbacks=setbacks, zoning=zoning
        )

        assert result["compliant"] is False
        assert any("coverage" in v.lower() for v in result["violations"])


# =============================================================================
# MASSING IMPORTS AND TESTS
# =============================================================================


class TestMassingConfig:
    """Tests for MassingConfig class."""

    def test_default_config(self):
        """Default massing configuration."""
        config = MassingConfig()
        assert config.massing_type == MassingType.BAR
        assert config.podium_floors == 0
        assert config.tower_floor_plate_ratio == 0.6

    def test_residential_tower_preset(self):
        """Residential tower preset."""
        config = MassingConfig.residential_tower()
        assert config.massing_type == MassingType.TOWER
        assert config.max_floors == 20

    def test_residential_podium_preset(self):
        """Residential podium preset."""
        config = MassingConfig.residential_podium(podium_floors=5)
        assert config.massing_type == MassingType.PODIUM_TOWER
        assert config.podium_floors == 5

    def test_office_building_preset(self):
        """Office building preset."""
        config = MassingConfig.office_building()
        assert config.massing_type == MassingType.SLAB
        assert config.floor_config.floor_to_floor_height == 13.0

    def test_mixed_use_preset(self):
        """Mixed-use preset."""
        config = MassingConfig.mixed_use(retail_floors=2)
        assert config.massing_type == MassingType.PODIUM_TOWER
        assert config.podium_floors == 2


class TestStepBack:
    """Tests for StepBack class."""

    def test_step_back_creation(self):
        """Create step-back."""
        step_back = StepBack(floor_number=6, inset_distance=10)
        assert step_back.floor_number == 6
        assert step_back.inset_distance == 10
        assert 'all' in step_back.edges

    def test_step_back_with_edges(self):
        """Create step-back with specific edges."""
        step_back = StepBack(
            floor_number=4, inset_distance=8, edges=['front', 'side'])
        assert 'front' in step_back.edges
        assert 'side' in step_back.edges


class TestBuildingMass:
    """Tests for BuildingMass class."""

    def test_generate_bar_massing(self):
        """Generate simple bar massing."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        assert massing.num_floors == 5
        assert massing.gross_floor_area == 8000.0 * 5  # 40,000 SF

    def test_massing_properties(self):
        """Test building mass properties."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        assert massing.building_footprint == 8000.0
        assert massing.lot_coverage == 1.0  # Building = site
        assert massing.floor_area_ratio == 5.0
        assert massing.efficiency > 0

    def test_massing_with_separate_site(self):
        """Test FAR calculation with larger site."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])  # 30,000 SF site

        buildable = Polygon([
            Point(20, 20), Point(180, 20), Point(180, 130), Point(20, 130)
        ])  # ~17,600 SF buildable

        massing = generate_bar_massing(
            buildable, num_floors=5,
            config=MassingConfig(),
            site_polygon=site
        )

        assert massing.site_area == 30000.0
        assert massing.building_footprint < massing.site_area
        assert massing.floor_area_ratio < 5.0

    def test_get_floor(self):
        """Get specific floor by number."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        floor3 = massing.get_floor(3)
        assert floor3 is not None
        assert floor3.floor_number == 3

        floor10 = massing.get_floor(10)
        assert floor10 is None

    def test_get_floors_by_type(self):
        """Get floors by type."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        ground_floors = massing.get_floors_by_type(FloorType.GROUND)
        typical_floors = massing.get_floors_by_type(FloorType.TYPICAL)

        assert len(ground_floors) == 1
        assert len(typical_floors) == 4

    def test_total_height(self):
        """Total building height calculation."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = MassingConfig(
            floor_config=FloorConfig(
                ground_floor_height=15, floor_to_floor_height=10)
        )

        massing = generate_bar_massing(polygon, num_floors=5, config=config)

        # Ground: 15' + 4 typical: 10' each = 55'
        assert massing.total_height == 55.0

    def test_to_dict(self):
        """Convert massing to dictionary."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=3, config=MassingConfig())
        data = massing.to_dict()

        assert "num_floors" in data
        assert "gross_floor_area_sf" in data
        assert "floor_area_ratio" in data
        assert "floors" in data
        assert len(data["floors"]) == 3


class TestPodiumTowerMassing:
    """Tests for podium-tower massing."""

    def test_generate_podium_tower(self):
        """Generate podium with tower."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = MassingConfig(
            massing_type=MassingType.PODIUM_TOWER,
            podium_floors=3,
            tower_setback=15
        )

        massing = generate_podium_tower_massing(
            polygon, num_floors=10, config=config
        )

        assert massing.num_floors == 10

        # Podium floors should have full footprint
        floor1 = massing.get_floor(1)
        floor3 = massing.get_floor(3)
        assert floor1.gross_area == floor3.gross_area

        # Tower floors should be smaller
        floor5 = massing.get_floor(5)
        assert floor5.gross_area < floor1.gross_area

    def test_podium_floor_types(self):
        """Verify floor types for podium-tower."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = MassingConfig(
            massing_type=MassingType.PODIUM_TOWER,
            podium_floors=3
        )

        massing = generate_podium_tower_massing(
            polygon, num_floors=6, config=config
        )

        # Floor 1 is ground, 2-3 are podium, 4-6 are typical
        assert massing.get_floor(1).floor_type == FloorType.GROUND
        assert massing.get_floor(2).floor_type == FloorType.PODIUM
        assert massing.get_floor(3).floor_type == FloorType.PODIUM
        assert massing.get_floor(4).floor_type == FloorType.TYPICAL


class TestSteppedMassing:
    """Tests for stepped massing with step-backs."""

    def test_generate_stepped_massing(self):
        """Generate massing with step-backs."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        step_backs = [
            StepBack(floor_number=4, inset_distance=10),
            StepBack(floor_number=7, inset_distance=10),
        ]

        massing = generate_stepped_massing(
            polygon, num_floors=10,
            step_backs=step_backs,
            config=MassingConfig()
        )

        assert massing.num_floors == 10

        # Floors should get smaller at step-backs
        floor1 = massing.get_floor(1)
        floor4 = massing.get_floor(4)
        floor7 = massing.get_floor(7)

        assert floor4.gross_area < floor1.gross_area
        assert floor7.gross_area < floor4.gross_area

    def test_step_back_via_config(self):
        """Generate massing using step_backs in config."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = MassingConfig(
            step_backs=[StepBack(floor_number=3, inset_distance=8)]
        )

        massing = generate_massing(polygon, num_floors=5, config=config)

        floor2 = massing.get_floor(2)
        floor3 = massing.get_floor(3)

        assert floor3.gross_area < floor2.gross_area


class TestGenerateMassing:
    """Tests for main generate_massing function."""

    def test_generate_bar_default(self):
        """Default generates bar massing."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_massing(polygon, num_floors=5)

        assert massing.num_floors == 5
        assert massing.config.massing_type == MassingType.BAR

    def test_generate_podium_tower_type(self):
        """Generate podium-tower via type."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        config = MassingConfig(
            massing_type=MassingType.PODIUM_TOWER,
            podium_floors=2
        )

        massing = generate_massing(polygon, num_floors=6, config=config)

        # Tower floors are smaller
        floor1 = massing.get_floor(1)
        floor4 = massing.get_floor(4)
        assert floor4.gross_area < floor1.gross_area


class TestMassingFromZoning:
    """Tests for zoning-constrained massing."""

    def test_massing_from_zoning(self):
        """Generate massing respecting zoning."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()
        zoning = ZoningDistrict.residential_medium()  # FAR 2.0, 45' height

        massing = generate_massing_from_zoning(site, setbacks, zoning)

        # Should respect height limit
        assert massing.total_height <= 45.0

        # Should respect FAR
        assert massing.floor_area_ratio <= 2.0

    def test_massing_far_limited(self):
        """Massing is FAR-limited."""
        site = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)
        ])  # 10,000 SF
        setbacks = SetbackConfig(front=5, side=5, rear=5)
        zoning = ZoningDistrict(
            name="test", max_far=1.0, max_height_ft=100,
            max_lot_coverage=0.9, parking_ratio=1.0
        )

        massing = generate_massing_from_zoning(site, setbacks, zoning)

        # FAR 1.0 means max GFA = site area
        assert massing.gross_floor_area <= 10000.0

    def test_massing_to_target(self):
        """Generate massing to target GFA."""
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        setbacks = SetbackConfig.residential()

        massing = generate_massing_to_target(
            site, setbacks, target_gfa=80000
        )

        # Should get close to target (within one floor)
        buildable = massing.floors[0].gross_area
        assert massing.gross_floor_area >= 80000 - buildable


class TestFARUtilization:
    """Tests for FAR utilization calculation."""

    def test_calculate_far_utilization(self):
        """Calculate FAR utilization."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        utilized, percentage = calculate_far_utilization(massing, max_far=10.0)

        assert utilized == 5.0  # FAR = 5.0
        assert percentage == 50.0  # 50% of max FAR 10

    def test_estimate_additional_floors(self):
        """Estimate additional floors possible."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=3, config=MassingConfig())

        additional = estimate_additional_floors(massing, max_far=5.0)

        # Currently at FAR 3.0, can add 2 more floors to reach FAR 5.0
        assert additional == 2


class TestMassingComparison:
    """Tests for massing comparison functions."""

    def test_compare_massings(self):
        """Compare multiple massing options."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing1 = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())
        massing2 = generate_bar_massing(
            polygon, num_floors=8, config=MassingConfig())

        comparison = compare_massings([massing1, massing2])

        assert len(comparison) == 2
        assert comparison[0]["num_floors"] == 5
        assert comparison[1]["num_floors"] == 8
        assert comparison[1]["gfa_sf"] > comparison[0]["gfa_sf"]

    def test_get_massing_summary(self):
        """Get comprehensive massing summary."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])

        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        summary = get_massing_summary(massing)

        assert "overview" in summary
        assert "areas" in summary
        assert "ratios" in summary
        assert "floor_types" in summary
        assert "floor_details" in summary


# =============================================================================
# UNIT MIX IMPORTS AND TESTS
# =============================================================================


class TestUnitSpec:
    """Tests for UnitSpec class."""

    def test_studio_preset(self):
        """Studio unit preset."""
        spec = UnitSpec.studio()
        assert spec.unit_type == UnitType.STUDIO
        assert spec.avg_size_sf == 500
        assert spec.bedrooms == 0
        assert spec.parking_spaces == 0.75

    def test_one_bedroom_preset(self):
        """1BR unit preset."""
        spec = UnitSpec.one_bedroom()
        assert spec.unit_type == UnitType.ONE_BEDROOM
        assert spec.avg_size_sf == 700
        assert spec.bedrooms == 1

    def test_two_bedroom_preset(self):
        """2BR unit preset."""
        spec = UnitSpec.two_bedroom()
        assert spec.unit_type == UnitType.TWO_BEDROOM
        assert spec.avg_size_sf == 1000
        assert spec.bedrooms == 2
        assert spec.parking_spaces == 1.5

    def test_three_bedroom_preset(self):
        """3BR unit preset."""
        spec = UnitSpec.three_bedroom()
        assert spec.unit_type == UnitType.THREE_BEDROOM
        assert spec.avg_size_sf == 1300
        assert spec.bedrooms == 3

    def test_custom_size(self):
        """Custom unit size."""
        spec = UnitSpec.one_bedroom(avg_size=800)
        assert spec.avg_size_sf == 800

    def test_min_max_size_defaults(self):
        """Min/max size defaults from avg."""
        spec = UnitSpec.studio(avg_size=500)
        assert spec.min_size_sf == 400  # 80%
        assert spec.max_size_sf == 600  # 120%

    def test_to_dict(self):
        """Convert to dictionary."""
        spec = UnitSpec.one_bedroom()
        data = spec.to_dict()
        assert "unit_type" in data
        assert "avg_size_sf" in data
        assert data["bedrooms"] == 1


class TestUnitMixTarget:
    """Tests for UnitMixTarget class."""

    def test_default_mix(self):
        """Default unit mix."""
        mix = UnitMixTarget()
        assert mix.studio_pct == 0.15
        assert mix.one_br_pct == 0.40
        assert mix.two_br_pct == 0.35
        assert mix.three_br_pct == 0.10

    def test_urban_rental_preset(self):
        """Urban rental preset."""
        mix = UnitMixTarget.urban_rental()
        assert mix.studio_pct == 0.20
        assert mix.one_br_pct == 0.45

    def test_suburban_rental_preset(self):
        """Suburban rental preset."""
        mix = UnitMixTarget.suburban_rental()
        assert mix.two_br_pct == 0.45
        assert mix.three_br_pct == 0.20

    def test_condo_preset(self):
        """Condo preset."""
        mix = UnitMixTarget.condo()
        assert mix.two_br_pct == 0.50

    def test_normalization(self):
        """Mix is normalized to 100%."""
        mix = UnitMixTarget(
            studio_pct=0.5, one_br_pct=0.5,
            two_br_pct=0.5, three_br_pct=0.5
        )
        total = mix.studio_pct + mix.one_br_pct + mix.two_br_pct + mix.three_br_pct
        assert abs(total - 1.0) < 0.01

    def test_get_percentages(self):
        """Get percentages by type."""
        mix = UnitMixTarget()
        pcts = mix.get_percentages()
        assert UnitType.STUDIO in pcts
        assert UnitType.ONE_BEDROOM in pcts

    def test_to_dict(self):
        """Convert to dictionary."""
        mix = UnitMixTarget()
        data = mix.to_dict()
        assert "studio" in data
        assert "1br" in data


class TestUnitCount:
    """Tests for UnitCount class."""

    def test_default_zero(self):
        """Default counts are zero."""
        count = UnitCount()
        assert count.total == 0

    def test_total(self):
        """Total unit count."""
        count = UnitCount(studio=5, one_br=10, two_br=8, three_br=2)
        assert count.total == 25

    def test_total_bedrooms(self):
        """Total bedroom count."""
        count = UnitCount(studio=5, one_br=10, two_br=8, three_br=2)
        # 0*5 + 1*10 + 2*8 + 3*2 = 0 + 10 + 16 + 6 = 32
        assert count.total_bedrooms == 32

    def test_add_unit(self):
        """Add units by type."""
        count = UnitCount()
        count.add(UnitType.STUDIO, 3)
        count.add(UnitType.ONE_BEDROOM, 5)
        assert count.studio == 3
        assert count.one_br == 5

    def test_get_by_type(self):
        """Get count by type."""
        count = UnitCount(two_br=10)
        assert count.get_by_type(UnitType.TWO_BEDROOM) == 10

    def test_add_counts(self):
        """Add two UnitCounts."""
        count1 = UnitCount(studio=5, one_br=10)
        count2 = UnitCount(studio=3, two_br=8)
        total = count1 + count2
        assert total.studio == 8
        assert total.one_br == 10
        assert total.two_br == 8

    def test_to_dict(self):
        """Convert to dictionary."""
        count = UnitCount(studio=5, one_br=10)
        data = count.to_dict()
        assert data["total"] == 15
        assert data["studio"] == 5


class TestCalculateUnitsForArea:
    """Tests for calculate_units_for_area function."""

    def test_basic_calculation(self):
        """Basic unit calculation."""
        # 10,000 SF with default mix
        units, leftover = calculate_units_for_area(10000, UnitMixTarget())

        assert units.total > 0
        assert leftover >= 0

    def test_zero_area(self):
        """Zero area returns zero units."""
        units, leftover = calculate_units_for_area(0, UnitMixTarget())
        assert units.total == 0

    def test_small_area(self):
        """Very small area may return zero units."""
        units, leftover = calculate_units_for_area(100, UnitMixTarget())
        assert units.total == 0
        assert leftover == 100

    def test_respects_mix(self):
        """Unit distribution respects target mix."""
        # 50,000 SF should give enough units for a good distribution
        units, _ = calculate_units_for_area(50000, UnitMixTarget())

        # Should have some of each type
        assert units.studio > 0
        assert units.one_br > 0
        assert units.two_br > 0


class TestFloorUnitMix:
    """Tests for FloorUnitMix class."""

    def test_floor_unit_mix_creation(self):
        """Create floor unit mix."""
        units = UnitCount(studio=2, one_br=5, two_br=3)
        floor_mix = FloorUnitMix(
            floor_number=1,
            floor_area_sf=8000,
            net_area_sf=6800,
            units=units
        )

        assert floor_mix.unit_count == 10
        assert floor_mix.floor_number == 1

    def test_avg_unit_size(self):
        """Average unit size calculation."""
        units = UnitCount(studio=2, one_br=5, two_br=3)
        floor_mix = FloorUnitMix(
            floor_number=1,
            floor_area_sf=8000,
            net_area_sf=6800,
            units=units
        )

        assert floor_mix.avg_unit_size == 680  # 6800 / 10

    def test_to_dict(self):
        """Convert to dictionary."""
        units = UnitCount(studio=2, one_br=5)
        floor_mix = FloorUnitMix(
            floor_number=1,
            floor_area_sf=8000,
            net_area_sf=6800,
            units=units
        )
        data = floor_mix.to_dict()
        assert "unit_count" in data
        assert "units" in data


class TestCalculateFloorUnitMix:
    """Tests for calculate_floor_unit_mix function."""

    def test_typical_floor(self):
        """Calculate units for typical floor."""
        floor = FloorPlate.from_rectangle(100, 80, floor_number=2)

        floor_mix = calculate_floor_unit_mix(floor, UnitMixTarget())

        assert floor_mix.unit_count > 0
        assert floor_mix.floor_number == 2

    def test_custom_mix(self):
        """Calculate units with custom mix."""
        floor = FloorPlate.from_rectangle(100, 80, floor_number=2)
        mix = UnitMixTarget.suburban_rental()  # More 2BR/3BR

        floor_mix = calculate_floor_unit_mix(floor, mix)

        assert floor_mix.unit_count > 0


class TestCalculateBuildingUnitMix:
    """Tests for calculate_building_unit_mix function."""

    def test_building_unit_mix(self):
        """Calculate units for entire building."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        building_mix = calculate_building_unit_mix(massing)

        assert building_mix.unit_count > 0
        assert len(building_mix.floors) == 5

    def test_total_units(self):
        """Total units across building."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        building_mix = calculate_building_unit_mix(massing)

        # Sum of floor units should equal total
        floor_sum = sum(f.unit_count for f in building_mix.floors)
        assert building_mix.unit_count == floor_sum

    def test_parking_requirement(self):
        """Calculate parking requirement."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())

        building_mix = calculate_building_unit_mix(massing)

        # Should require some parking
        assert building_mix.get_parking_requirement() > 0

    def test_actual_mix(self):
        """Get actual unit mix percentages."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        massing = generate_bar_massing(
            polygon, num_floors=10, config=MassingConfig())

        building_mix = calculate_building_unit_mix(massing)
        actual_mix = building_mix.get_actual_mix()

        # Percentages should sum to ~1.0
        total_pct = sum(actual_mix.values())
        assert abs(total_pct - 1.0) < 0.01

    def test_to_dict(self):
        """Convert to dictionary."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        massing = generate_bar_massing(
            polygon, num_floors=3, config=MassingConfig())

        building_mix = calculate_building_unit_mix(massing)
        data = building_mix.to_dict()

        assert "unit_count" in data
        assert "units_by_type" in data
        assert "parking_requirement" in data


class TestHelperFunctions:
    """Tests for unit mix helper functions."""

    def test_estimate_units_from_area(self):
        """Estimate units from total area."""
        # 40,000 SF * 0.85 efficiency / 800 avg = 42.5 → 42 units
        units = estimate_units_from_area(40000, avg_unit_size=800)
        assert units == 42

    def test_calculate_avg_unit_size(self):
        """Calculate weighted average unit size."""
        mix = UnitMixTarget()
        specs = get_default_unit_specs()

        avg_size = calculate_avg_unit_size(mix, specs)

        # Should be between studio (500) and 3BR (1300)
        assert 500 < avg_size < 1300

    def test_calculate_required_parking(self):
        """Calculate required parking from units."""
        units = UnitCount(studio=10, one_br=20, two_br=10, three_br=5)

        parking = calculate_required_parking_from_units(units)

        # 10*0.75 + 20*1.0 + 10*1.5 + 5*2.0 = 7.5 + 20 + 15 + 10 = 52.5
        assert parking == 52.5

    def test_optimize_unit_mix_for_target(self):
        """Optimize mix for target unit count."""
        net_area = 50000
        target_units = 80  # Need ~625 SF avg

        mix, units = optimize_unit_mix_for_target_count(net_area, target_units)

        # Should get close to target
        assert abs(units.total - target_units) < 10

    def test_get_unit_mix_summary(self):
        """Get unit mix summary."""
        polygon = Polygon([
            Point(0, 0), Point(100, 0), Point(100, 80), Point(0, 80)
        ])
        massing = generate_bar_massing(
            polygon, num_floors=5, config=MassingConfig())
        building_mix = calculate_building_unit_mix(massing)

        summary = get_unit_mix_summary(building_mix)

        assert "summary" in summary
        assert "units_by_type" in summary
        assert "mix_percentages" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
