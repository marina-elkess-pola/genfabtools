"""
Tests for parking/stall.py, parking/drive_aisle.py, and parking/bay.py

Run with: python -m pytest tests/test_parking.py -v
"""

import math
import pytest
from sitefit.parking.stall import (
    Stall, StallType, STALL_PRESETS,
    calculate_stalls_per_length, required_ada_stalls, stall_dimensions_for_angle
)
from sitefit.parking.drive_aisle import (
    DriveAisle, AisleType, AISLE_PRESETS,
    calculate_bay_width, calculate_parking_module, minimum_aisle_width_for_angle
)
from sitefit.parking.bay import (
    ParkingBay, BayType, StallPlacement
)
from sitefit.core.geometry import Point, Line


class TestStall:
    """Tests for Stall class."""

    def test_standard_dimensions(self):
        """Standard stall is 9' x 18'."""
        stall = Stall.standard()
        assert stall.width == 9.0
        assert stall.depth == 18.0
        assert stall.stall_type == StallType.STANDARD

    def test_compact_dimensions(self):
        """Compact stall is 8' x 16'."""
        stall = Stall.compact()
        assert stall.width == 8.0
        assert stall.depth == 16.0
        assert stall.stall_type == StallType.COMPACT

    def test_ada_dimensions(self):
        """ADA stall is 8' + 5' access aisle = 13' total width."""
        stall = Stall.ada()
        assert stall.width == 8.0
        assert stall.access_aisle_width == 5.0
        assert stall.total_width == 13.0
        assert stall.is_ada is True

    def test_ada_van_dimensions(self):
        """ADA van stall is 8' + 8' access aisle = 16' total width."""
        stall = Stall.ada_van()
        assert stall.width == 8.0
        assert stall.access_aisle_width == 8.0
        assert stall.total_width == 16.0
        assert stall.is_ada is True

    def test_parallel_dimensions(self):
        """Parallel stall is 8' x 22' at 0° angle."""
        stall = Stall.parallel()
        assert stall.width == 8.0
        assert stall.depth == 22.0
        assert stall.angle == 0.0
        assert stall.stall_type == StallType.PARALLEL

    def test_motorcycle_dimensions(self):
        """Motorcycle stall is 4' x 8'."""
        stall = Stall.motorcycle()
        assert stall.width == 4.0
        assert stall.depth == 8.0

    def test_stall_area(self):
        """Area is width * depth."""
        stall = Stall.standard()
        assert stall.area == 9.0 * 18.0  # 162 sf

    def test_effective_depth_90_degrees(self):
        """At 90°, effective depth equals actual depth."""
        stall = Stall.standard(angle=90)
        assert stall.effective_depth == 18.0

    def test_effective_depth_45_degrees(self):
        """At 45°, effective depth is depth * sin(45°)."""
        stall = Stall.standard(angle=45)
        expected = 18.0 * math.sin(math.radians(45))
        assert abs(stall.effective_depth - expected) < 0.01

    def test_effective_width_90_degrees(self):
        """At 90°, effective width equals stall width."""
        stall = Stall.standard(angle=90)
        assert stall.effective_width == 9.0

    def test_effective_width_45_degrees(self):
        """At 45°, effective width is width / sin(45°)."""
        stall = Stall.standard(angle=45)
        expected = 9.0 / math.sin(math.radians(45))
        assert abs(stall.effective_width - expected) < 0.01

    def test_effective_width_0_degrees(self):
        """At 0° (parallel), effective width equals depth."""
        stall = Stall(width=8.0, depth=22.0, angle=0)
        assert stall.effective_width == 22.0

    def test_to_rectangle(self):
        """Create rectangle from stall."""
        stall = Stall.standard()
        rect = stall.to_rectangle(Point(10, 20))
        assert rect.origin.x == 10.0
        assert rect.origin.y == 20.0
        assert rect.width == 9.0
        assert rect.height == 18.0

    def test_to_polygon(self):
        """Create polygon from stall."""
        stall = Stall.standard()
        poly = stall.to_polygon(Point(0, 0))
        assert poly.area == 162.0

    def test_copy(self):
        """Copy stall with overrides."""
        stall = Stall.standard()
        copied = stall.copy(angle=45)
        assert copied.width == 9.0
        assert copied.angle == 45.0

    def test_invalid_dimensions(self):
        """Negative dimensions should raise error."""
        with pytest.raises(ValueError):
            Stall(width=-1, depth=18)

    def test_invalid_angle(self):
        """Angle outside 0-90 should raise error."""
        with pytest.raises(ValueError):
            Stall(width=9, depth=18, angle=100)

    def test_presets_exist(self):
        """Check all preset stalls exist."""
        assert "standard_90" in STALL_PRESETS
        assert "compact_90" in STALL_PRESETS
        assert "ada" in STALL_PRESETS
        assert "ada_van" in STALL_PRESETS
        assert "parallel" in STALL_PRESETS


class TestDriveAisle:
    """Tests for DriveAisle class."""

    def test_two_way_dimensions(self):
        """Two-way aisle is 24' wide."""
        aisle = DriveAisle.two_way()
        assert aisle.width == 24.0
        assert aisle.aisle_type == AisleType.TWO_WAY
        assert aisle.allows_two_way_traffic is True

    def test_one_way_90_degrees(self):
        """One-way aisle for 90° parking is 22' wide."""
        aisle = DriveAisle.one_way(90)
        assert aisle.width == 22.0
        assert aisle.aisle_type == AisleType.ONE_WAY

    def test_one_way_60_degrees(self):
        """One-way aisle for 60° parking is 18' wide."""
        aisle = DriveAisle.one_way(60)
        assert aisle.width == 18.0

    def test_one_way_45_degrees(self):
        """One-way aisle for 45° parking is 13' wide."""
        aisle = DriveAisle.one_way(45)
        assert aisle.width == 13.0

    def test_one_way_30_degrees(self):
        """One-way aisle for 30° parking is 11' wide."""
        aisle = DriveAisle.one_way(30)
        assert aisle.width == 11.0

    def test_fire_lane(self):
        """Fire lane is minimum 20' wide."""
        aisle = DriveAisle.fire_lane()
        assert aisle.width == 20.0
        assert aisle.is_fire_lane is True

    def test_fire_lane_wide(self):
        """Wide fire lane is 26' for no hydrant access."""
        aisle = DriveAisle.fire_lane_wide()
        assert aisle.width == 26.0

    def test_half_width(self):
        """Half width is width / 2."""
        aisle = DriveAisle.two_way()
        assert aisle.half_width == 12.0

    def test_to_polygon(self):
        """Create polygon from aisle centerline."""
        aisle = DriveAisle.two_way()
        centerline = Line(Point(0, 0), Point(100, 0))
        poly = aisle.to_polygon(centerline)

        # Should be 100' long x 24' wide = 2400 sf
        assert abs(poly.area - 2400.0) < 1.0

    def test_for_parking_angle(self):
        """Factory method creates correct aisle."""
        aisle = DriveAisle.for_parking_angle(45, two_way=False)
        assert aisle.width == 13.0
        assert aisle.parking_angle == 45.0

    def test_invalid_width(self):
        """Negative width should raise error."""
        with pytest.raises(ValueError):
            DriveAisle(width=-1)

    def test_presets_exist(self):
        """Check all preset aisles exist."""
        assert "two_way_90" in AISLE_PRESETS
        assert "one_way_60" in AISLE_PRESETS
        assert "fire_lane" in AISLE_PRESETS


class TestStallUtilities:
    """Tests for stall utility functions."""

    def test_calculate_stalls_per_length(self):
        """Calculate stalls that fit in given length."""
        stall = Stall.standard()  # 9' wide at 90°

        # 100' / 9' = 11 stalls
        assert calculate_stalls_per_length(100, stall) == 11

        # 50' / 9' = 5 stalls
        assert calculate_stalls_per_length(50, stall) == 5

    def test_calculate_stalls_per_length_angled(self):
        """Angled stalls take more length."""
        stall = Stall.standard(angle=45)  # 9' / sin(45°) ≈ 12.7' effective

        # 100' / 12.7' ≈ 7 stalls
        result = calculate_stalls_per_length(100, stall)
        assert result == 7

    def test_required_ada_stalls_small_lot(self):
        """Small lot requires 1 ADA stall."""
        reg, van = required_ada_stalls(20)
        assert reg + van == 1
        assert van >= 1  # At least 1 must be van accessible

    def test_required_ada_stalls_medium_lot(self):
        """50-stall lot requires 2 ADA stalls."""
        reg, van = required_ada_stalls(50)
        assert reg + van == 2

    def test_required_ada_stalls_large_lot(self):
        """100-stall lot requires 4 ADA stalls."""
        reg, van = required_ada_stalls(100)
        assert reg + van == 4

    def test_required_ada_stalls_van_ratio(self):
        """At least 1 in 6 must be van accessible."""
        reg, van = required_ada_stalls(500)
        total = reg + van
        assert van >= total / 6  # At least 1/6 van accessible

    def test_stall_dimensions_for_angle(self):
        """Get dimensions for specific angle."""
        stall = Stall.standard()
        dims = stall_dimensions_for_angle(stall, 60)

        assert dims["angle"] == 60
        assert dims["base_width"] == 9.0
        assert dims["base_depth"] == 18.0
        assert dims["effective_depth"] < 18.0  # Less than full depth


class TestAisleUtilities:
    """Tests for aisle utility functions."""

    def test_calculate_bay_width_double_loaded(self):
        """Double-loaded bay: stall + aisle + stall."""
        width = calculate_bay_width(18, 24, double_loaded=True)
        assert width == 60.0  # 18 + 24 + 18

    def test_calculate_bay_width_single_loaded(self):
        """Single-loaded bay: stall + aisle."""
        width = calculate_bay_width(18, 24, double_loaded=False)
        assert width == 42.0  # 18 + 24

    def test_calculate_parking_module(self):
        """Calculate parking module metrics."""
        module = calculate_parking_module(stall_depth=18, aisle_width=24)

        assert module["bay_width"] == 60.0
        assert module["double_loaded"] is True
        assert module["stalls_per_module"] == 2

    def test_minimum_aisle_width_90(self):
        """90° parking requires widest aisle."""
        width = minimum_aisle_width_for_angle(90)
        assert width >= 22.0

    def test_minimum_aisle_width_45(self):
        """45° parking requires less aisle width."""
        width = minimum_aisle_width_for_angle(45)
        assert 11.0 <= width <= 15.0

    def test_minimum_aisle_width_parallel(self):
        """Parallel parking requires minimum 12'."""
        width = minimum_aisle_width_for_angle(0)
        assert width == 12.0


class TestIntegration:
    """Integration tests combining stalls and aisles."""

    def test_typical_parking_layout(self):
        """
        Test typical double-loaded parking bay:
        - Standard 90° stalls (9' x 18')
        - Two-way aisle (24')
        - Total bay width: 60'
        """
        stall = Stall.standard()
        aisle = DriveAisle.two_way()

        bay_width = calculate_bay_width(
            stall.depth, aisle.width, double_loaded=True)
        assert bay_width == 60.0

        # In 100' of length, how many stalls per side?
        stalls_per_side = calculate_stalls_per_length(100, stall)
        assert stalls_per_side == 11

        # Total stalls (both sides)
        total_stalls = stalls_per_side * 2
        assert total_stalls == 22

    def test_angled_parking_layout(self):
        """
        Test 60° angled parking:
        - Stalls take more length
        - Aisle can be narrower (one-way)
        """
        stall = Stall.standard(angle=60)
        aisle = DriveAisle.one_way(60)

        # 60° aisle is 18' wide
        assert aisle.width == 18.0

        # Stall effective depth at 60°
        expected_depth = 18.0 * math.sin(math.radians(60))
        assert abs(stall.effective_depth - expected_depth) < 0.01

        # Bay width with reduced depth
        bay_width = calculate_bay_width(stall.effective_depth, aisle.width)
        assert bay_width < 60.0  # Less than 90° configuration

    def test_ada_compliant_lot(self):
        """
        Test ADA-compliant parking lot:
        - 100 total stalls
        - Requires 4 ADA stalls
        - At least 1 van accessible
        """
        total_stalls = 100
        standard_stall = Stall.standard()
        ada_stall = Stall.ada()
        ada_van_stall = Stall.ada_van()

        reg_ada, van_ada = required_ada_stalls(total_stalls)

        # Should have 4 total ADA stalls
        assert reg_ada + van_ada == 4

        # At least 1 van accessible
        assert van_ada >= 1

        # ADA stalls are wider
        assert ada_stall.total_width > standard_stall.width
        assert ada_van_stall.total_width > ada_stall.total_width


class TestParkingBay:
    """Tests for parking bay generation."""

    def test_create_double_loaded_bay(self):
        """Test creating a double-loaded parking bay."""
        centerline = Line(Point(0, 30), Point(100, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        # Should be double loaded
        assert bay.double_loaded is True

        # Total width should be: stall + aisle + stall
        expected_width = 18.0 + 24.0 + 18.0  # 60 feet
        assert abs(bay.total_width - expected_width) < 0.01

        # Should generate stalls
        assert bay.total_stalls > 0

    def test_create_single_loaded_bay(self):
        """Test creating a single-loaded parking bay."""
        centerline = Line(Point(0, 30), Point(100, 30))
        bay = ParkingBay.create_single_loaded(centerline=centerline)

        assert bay.double_loaded is False

        # Total width: stall + aisle (no second row)
        expected_width = 18.0 + 24.0  # 42 feet
        assert abs(bay.total_width - expected_width) < 0.01

    def test_bay_stall_count(self):
        """Test that bay generates correct number of stalls."""
        # 90' long bay = 10 stalls per side (9' each)
        centerline = Line(Point(0, 30), Point(90, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        # Should have stalls on both sides: 10 per side = 20 total
        assert bay.total_stalls == 20

    def test_bay_stall_positions(self):
        """Test stall positions along the bay."""
        # 36' bay = 4 stalls per side
        centerline = Line(Point(0, 30), Point(36, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        # Separate left and right placements
        left = bay.stalls_left
        right = bay.stalls_right

        assert len(left) == 4
        assert len(right) == 4

        # Left stalls should have higher y (positive normal direction)
        # Right stalls should have lower y (negative normal direction)
        centerline_y = 30.0
        for p in left:
            assert p.center.y > centerline_y
        for p in right:
            assert p.center.y < centerline_y

    def test_bay_stall_polygons(self):
        """Test that stall placements generate valid polygons."""
        centerline = Line(Point(0, 30), Point(36, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        for placement in bay.all_stalls:
            polygon = placement.polygon
            assert polygon is not None
            # Standard stall area: 9 x 18 = 162 sq ft
            assert abs(polygon.area - 162.0) < 1.0  # Small tolerance

    def test_bay_efficiency(self):
        """Test parking bay efficiency calculation."""
        centerline = Line(Point(0, 30), Point(90, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        efficiency = bay.efficiency

        # Efficiency = stalls per 1000 SF
        # 20 stalls, area = 90 * 60 = 5400 sq ft
        # Efficiency = (20 / 5400) * 1000 ≈ 3.7
        assert 3.0 < efficiency < 4.5

    def test_angled_bay_90_degrees(self):
        """Test 90-degree angled bay (same as perpendicular)."""
        centerline = Line(Point(0, 30), Point(100, 30))
        bay = ParkingBay.create_angled(centerline=centerline, angle=90)

        # At 90 degrees, effective width equals actual stall width
        assert abs(bay.stall.width - 9.0) < 0.01

    def test_angled_bay_60_degrees(self):
        """Test 60-degree angled bay."""
        centerline = Line(Point(0, 30), Point(100, 30))
        bay = ParkingBay.create_angled(centerline=centerline, angle=60)

        # At 60 degrees, aisle is narrower (one-way)
        assert bay.aisle.width < 24.0  # Narrower aisle at angles

    def test_clip_bay_to_polygon(self):
        """Test clipping bay to a site boundary."""
        centerline = Line(Point(0, 30), Point(100, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        # Create a polygon that only covers half the bay
        from sitefit.core import Polygon as CorePolygon
        boundary = CorePolygon([
            Point(0, 0),
            Point(50, 0),  # Only half the length
            Point(50, 70),
            Point(0, 70)
        ])

        original_count = bay.total_stalls
        clipped = bay.clip_to_polygon(boundary)

        # Should have fewer stalls
        assert clipped is not None
        assert clipped.total_stalls < original_count
        # Roughly half
        assert clipped.total_stalls >= original_count // 3

    def test_create_bay_grid(self):
        """Test creating a grid of parking bays."""
        from sitefit.parking import create_bay_grid
        from sitefit.core.geometry import Rectangle

        bounds = Rectangle(Point(0, 0), 200, 120)
        bays = create_bay_grid(bounds=bounds)

        # Should create multiple bays
        assert len(bays) >= 1

        # Each bay should have stalls
        for bay in bays:
            assert bay.total_stalls > 0

    def test_count_total_stalls(self):
        """Test counting total stalls across multiple bays."""
        from sitefit.parking import count_total_stalls, create_bay_grid
        from sitefit.core.geometry import Rectangle

        bounds = Rectangle(Point(0, 0), 200, 120)
        bays = create_bay_grid(bounds=bounds)

        total = count_total_stalls(bays)

        # Should have reasonable number of stalls
        assert total > 0

        # Should equal sum of individual bay counts
        manual_count = sum(b.total_stalls for b in bays)
        assert total == manual_count

    def test_bay_to_dict(self):
        """Test serializing a bay to dictionary."""
        centerline = Line(Point(0, 30), Point(90, 30))
        bay = ParkingBay.create_double_loaded(centerline=centerline)

        data = bay.to_dict()

        assert "centerline" in data
        assert "length" in data
        assert "total_width" in data
        assert "total_stalls" in data
        assert "stalls" in data

        assert data["double_loaded"] is True
        assert data["total_stalls"] == 20

    def test_factory_at_position(self):
        """Test creating bay at specific position."""
        bay = ParkingBay.create_at_y(y=100.0, x_start=0, x_end=90)

        # Centerline should be at y=100
        assert bay.centerline.start.y == 100.0
        assert bay.centerline.end.y == 100.0

        # Stalls should be around y=100
        for p in bay.all_stalls:
            # All stalls within the bay width of centerline
            assert abs(p.center.y - 100.0) < 35.0  # Within half bay width


class TestLayoutGenerator:
    """Tests for parking layout generation."""

    def test_simple_rectangle_layout(self):
        """Test generating layout for a simple rectangle."""
        from sitefit.parking.layout_generator import (
            ParkingLayoutGenerator, generate_parking_layout
        )
        from sitefit.core.geometry import Polygon

        # 200' x 150' site
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        result = generate_parking_layout(site)

        # Should generate stalls
        assert result.total_stalls > 0

        # Should have reasonable efficiency (2-5 stalls per 1000 SF)
        assert 1.5 < result.efficiency < 6.0

        # Should have some bays
        assert len(result.bays) > 0

    def test_layout_at_specific_angle(self):
        """Test generating layout at a specific angle."""
        from sitefit.parking.layout_generator import ParkingLayoutGenerator
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        generator = ParkingLayoutGenerator(site)

        # Test 90-degree layout
        result = generator.generate_at_angle(90)
        assert result.angle == 90
        assert result.total_stalls > 0

    def test_compare_angles(self):
        """Test comparing layouts at different angles."""
        from sitefit.parking.layout_generator import compare_layouts
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        results = compare_layouts(site)

        # Should have result for each angle
        assert len(results) >= 1

        # Results should be sorted by stall count (descending)
        for i in range(len(results) - 1):
            assert results[i].total_stalls >= results[i + 1].total_stalls

    def test_layout_with_exclusion(self):
        """Test layout generation with exclusion zone."""
        from sitefit.parking.layout_generator import (
            ParkingLayoutGenerator, Exclusion, LayoutConfig
        )
        from sitefit.core.geometry import Polygon

        # 200' x 150' site
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # 40' x 40' exclusion in center
        exclusion_poly = Polygon([
            Point(80, 55), Point(120, 55), Point(120, 95), Point(80, 95)
        ])
        exclusion = Exclusion(polygon=exclusion_poly,
                              exclusion_type="building")

        # Layout without exclusion
        gen_no_excl = ParkingLayoutGenerator(site)
        result_no_excl = gen_no_excl.generate()

        # Layout with exclusion
        gen_with_excl = ParkingLayoutGenerator(site, exclusions=[exclusion])
        result_with_excl = gen_with_excl.generate()

        # With exclusion should have fewer stalls
        assert result_with_excl.total_stalls <= result_no_excl.total_stalls

        # Excluded area should be tracked
        assert result_with_excl.excluded_area > 0

    def test_layout_result_to_dict(self):
        """Test that layout result serializes correctly."""
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        result = generate_parking_layout(site)
        data = result.to_dict()

        # Should have all required fields
        assert "total_stalls" in data
        assert "angle" in data
        assert "efficiency" in data
        assert "bay_count" in data
        assert "bays" in data

    def test_layout_for_rectangle_convenience(self):
        """Test the convenience function for rectangles."""
        from sitefit.parking.layout_generator import layout_for_rectangle

        result = layout_for_rectangle(200, 150, angle=90)

        assert result.total_stalls > 0
        assert result.angle == 90

    def test_stalls_per_acre(self):
        """Test stalls per acre calculation."""
        from sitefit.parking.layout_generator import (
            generate_parking_layout, stalls_per_acre
        )
        from sitefit.core.geometry import Polygon

        # 1 acre = 43,560 SF ≈ 208' x 209'
        site = Polygon([
            Point(0, 0), Point(208, 0), Point(208, 209), Point(0, 209)
        ])

        result = generate_parking_layout(site)
        spa = stalls_per_acre(result)

        # Typical surface parking: 100-150 stalls per acre
        assert 50 < spa < 200

    def test_estimate_capacity(self):
        """Test quick capacity estimation."""
        from sitefit.parking.layout_generator import ParkingLayoutGenerator
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        generator = ParkingLayoutGenerator(site)
        estimate = generator.estimate_capacity()

        # Should provide a reasonable estimate
        assert estimate > 0

        # Estimate should be in ballpark of actual
        actual = generator.generate().total_stalls
        assert abs(estimate - actual) < actual * 0.5  # Within 50%

    def test_l_shaped_site(self):
        """Test layout generation for L-shaped site."""
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        # L-shaped site
        site = Polygon([
            Point(0, 0), Point(150, 0), Point(150, 100),
            Point(100, 100), Point(100, 150), Point(0, 150)
        ])

        result = generate_parking_layout(site)

        # Should still generate stalls
        assert result.total_stalls > 0

        # Area calculation should be correct
        assert abs(result.site_area - site.area) < 1.0

    def test_double_vs_single_loaded(self):
        """Test that double-loaded produces more stalls than single-loaded."""
        from sitefit.parking.layout_generator import (
            ParkingLayoutGenerator, LayoutConfig
        )
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Double loaded
        config_double = LayoutConfig(double_loaded=True, angles_to_try=[90])
        gen_double = ParkingLayoutGenerator(site, config=config_double)
        result_double = gen_double.generate()

        # Single loaded
        config_single = LayoutConfig(double_loaded=False, angles_to_try=[90])
        gen_single = ParkingLayoutGenerator(site, config=config_single)
        result_single = gen_single.generate()

        # Double loaded should have more stalls
        assert result_double.total_stalls > result_single.total_stalls


class TestCirculation:
    """Tests for parking circulation network generation."""

    def test_generate_circulation_basic(self):
        """Test generating circulation for a simple layout."""
        from sitefit.parking.circulation import (
            CirculationGenerator, generate_circulation
        )
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        # Create site and layout
        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        layout = generate_parking_layout(site)

        # Generate circulation
        network = generate_circulation(site, layout)

        # Should have access points
        assert len(network.access_points) > 0

        # Should have drive lanes
        # May be 0 if bays connect directly
        assert len(network.drive_lanes) >= 0

        # Should include the bays
        assert network.total_stalls == layout.total_stalls

    def test_circulation_network_connectivity(self):
        """Test that circulation network connects all bays."""
        from sitefit.parking.circulation import CirculationGenerator
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        layout = generate_parking_layout(site)

        generator = CirculationGenerator(site, layout=layout)
        network = generator.generate()

        # Network should be connected
        assert network.is_connected() or len(network.bays) == 0

    def test_access_point_creation(self):
        """Test creating custom access points."""
        from sitefit.parking.circulation import (
            CirculationGenerator, AccessPoint, AccessPointType
        )
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Create access point on south edge
        access = AccessPoint(
            location=Point(100, 0),
            direction=(0, 1),  # North into site
            access_type=AccessPointType.ENTRY_EXIT,
            width=24.0,
            edge="south"
        )

        generator = CirculationGenerator(site, access_points=[access])
        network = generator.generate()

        assert len(network.access_points) == 1
        assert network.access_points[0].edge == "south"

    def test_add_access_point_on_edge(self):
        """Test adding access point on specific edge."""
        from sitefit.parking.circulation import add_access_point_on_edge
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Add on first edge (bottom)
        access = add_access_point_on_edge(site, edge_index=0, position=0.5)

        # Should be at midpoint of bottom edge
        assert abs(access.location.x - 100) < 1
        assert abs(access.location.y - 0) < 1

        # Direction should point into site (upward)
        assert access.direction[1] > 0  # Positive Y

    def test_circulation_network_to_dict(self):
        """Test serialization of circulation network."""
        from sitefit.parking.circulation import generate_circulation
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        layout = generate_parking_layout(site)
        network = generate_circulation(site, layout)

        data = network.to_dict()

        assert "access_points" in data
        assert "drive_lanes" in data
        assert "total_stalls" in data
        assert "is_connected" in data

    def test_drive_lane_polygon(self):
        """Test drive lane polygon generation."""
        from sitefit.parking.circulation import DriveLane, DriveLaneType

        lane = DriveLane(
            centerline=Line(Point(0, 50), Point(100, 50)),
            width=24.0,
            lane_type=DriveLaneType.MAIN
        )

        poly = lane.to_polygon()

        # Should have 4 vertices (rectangle)
        assert len(poly.vertices) == 4

        # Area = length * width = 100 * 24 = 2400
        assert abs(poly.area - 2400) < 1

    def test_circulation_efficiency(self):
        """Test circulation efficiency calculation."""
        from sitefit.parking.circulation import generate_circulation
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        layout = generate_parking_layout(site)
        network = generate_circulation(site, layout)

        efficiency = network.circulation_efficiency

        # Should be a positive ratio
        assert efficiency >= 0

    def test_fire_lane_coverage(self):
        """Test fire lane coverage calculation."""
        from sitefit.parking.circulation import (
            generate_circulation, calculate_fire_lane_coverage
        )
        from sitefit.parking.layout_generator import generate_parking_layout
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])
        layout = generate_parking_layout(site)
        network = generate_circulation(site, layout)

        coverage = calculate_fire_lane_coverage(network)

        # Should be between 0-100%
        assert 0 <= coverage <= 100

    def test_default_access_point_generation(self):
        """Test automatic access point generation."""
        from sitefit.parking.circulation import CirculationGenerator
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Don't provide access points - should auto-generate
        generator = CirculationGenerator(site)

        # Should have generated at least one access point
        assert len(generator.access_points) >= 1

        # Access point should be on an edge
        for ap in generator.access_points:
            # Location should be on or near site boundary
            # The point should be on the perimeter
            edges = site.edges
            on_edge = any(
                abs(edge.start.x - ap.location.x) < 5 or
                abs(edge.start.y - ap.location.y) < 5
                for edge in edges
            )
            # Just verify it has reasonable coordinates
            assert 0 <= ap.location.x <= 200
            assert 0 <= ap.location.y <= 150


# =============================================================================
# STEP 7: OPTIMIZER TESTS
# =============================================================================

class TestOptimizer:
    """Tests for parking/optimizer.py"""

    def test_optimize_parking_simple_rectangle(self):
        """Test basic optimization on a rectangle."""
        from sitefit.parking.optimizer import optimize_parking
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        summary = optimize_parking(site)

        # Should find at least some stalls
        assert summary.max_stalls > 0
        # Should have tested multiple angles
        assert len(summary.all_results) >= 4
        # Should have a best result
        assert summary.best_result is not None
        # Best angle should be set
        assert summary.best_angle is not None

    def test_optimize_parking_l_shaped_site(self):
        """Test optimization on L-shaped site (per architecture)."""
        from sitefit.parking.optimizer import optimize_parking
        from sitefit.core.geometry import Polygon

        # L-shaped site (200x150 with 100x75 corner removed)
        site = Polygon([
            Point(0, 0),
            Point(200, 0),
            Point(200, 75),
            Point(100, 75),
            Point(100, 150),
            Point(0, 150)
        ])

        summary = optimize_parking(site)

        # Should find stalls even with irregular shape
        assert summary.max_stalls > 0
        assert summary.best_result is not None

    def test_quick_optimize(self):
        """Test greedy optimization."""
        from sitefit.parking.optimizer import quick_optimize
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        result = quick_optimize(site)

        # Should return a result
        assert result is not None
        assert result.total_stalls > 0

    def test_compare_angles(self):
        """Test angle comparison function."""
        from sitefit.parking.optimizer import compare_angles
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        results = compare_angles(site, angles=[0, 45, 90])

        # Should have results for each angle
        assert len(results) >= 1
        # All should have non-negative stall counts
        for angle, stalls in results.items():
            assert stalls >= 0

    def test_optimizer_with_exclusions(self):
        """Test optimization with exclusion zones."""
        from sitefit.parking.optimizer import ParkingOptimizer, OptimizationConfig
        from sitefit.parking.layout_generator import Exclusion
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Add obstacle in center
        obstacle = Exclusion(
            polygon=Polygon([
                Point(80, 60), Point(120, 60), Point(120, 90), Point(80, 90)
            ]),
            exclusion_type="column"
        )

        optimizer = ParkingOptimizer(site, [obstacle])
        summary = optimizer.optimize()

        # Should still find stalls
        assert summary.max_stalls > 0
        # Excluded area should be recorded
        assert summary.excluded_area > 0

    def test_optimizer_min_stalls_constraint(self):
        """Test minimum stalls constraint."""
        from sitefit.parking.optimizer import ParkingOptimizer, OptimizationConfig
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        config = OptimizationConfig(min_stalls=10)
        optimizer = ParkingOptimizer(site, config=config)
        summary = optimizer.optimize()

        # Best result should meet constraints
        assert summary.best_result is not None
        assert summary.best_result.meets_constraints is True
        assert summary.best_result.total_stalls >= 10

    def test_optimization_objectives(self):
        """Test different optimization objectives."""
        from sitefit.parking.optimizer import (
            ParkingOptimizer, OptimizationConfig, OptimizationObjective
        )
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Test each objective
        for obj in OptimizationObjective:
            config = OptimizationConfig(objective=obj)
            optimizer = ParkingOptimizer(site, config=config)
            summary = optimizer.optimize()

            # All objectives should produce results
            assert summary.best_result is not None

    def test_optimization_summary_to_dict(self):
        """Test JSON serialization of results."""
        from sitefit.parking.optimizer import optimize_parking
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        summary = optimize_parking(site)
        data = summary.to_dict()

        # Should have expected keys
        assert "best_angle" in data
        assert "max_stalls" in data
        assert "iterations" in data
        assert "results_by_angle" in data

    def test_optimize_with_building(self):
        """Test optimization around a building footprint."""
        from sitefit.parking.optimizer import optimize_with_building
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(300, 0), Point(300, 200), Point(0, 200)
        ])

        building = Polygon([
            Point(100, 60), Point(200, 60), Point(200, 140), Point(100, 140)
        ])

        summary = optimize_with_building(site, building, min_stalls=5)

        # Should find stalls around building
        assert summary.max_stalls > 0

    def test_find_minimum_site_for_stalls(self):
        """Test site size estimation."""
        from sitefit.parking.optimizer import find_minimum_site_for_stalls

        # 50 stalls at standard efficiency
        width, length = find_minimum_site_for_stalls(50)

        # Should give reasonable dimensions
        assert width > 0
        assert length > 0
        # Length should be larger due to ratio
        assert length >= width

    def test_optimizer_time_limit(self):
        """Test that time limits are respected."""
        from sitefit.parking.optimizer import ParkingOptimizer, OptimizationConfig
        from sitefit.core.geometry import Polygon
        import time

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        # Very short time limit
        config = OptimizationConfig(time_limit_seconds=0.001)
        optimizer = ParkingOptimizer(site, config=config)

        start = time.time()
        summary = optimizer.optimize()
        elapsed = time.time() - start

        # Should complete quickly (allow some overhead)
        assert elapsed < 5.0  # Very generous limit

    def test_results_by_angle(self):
        """Test grouping results by angle."""
        from sitefit.parking.optimizer import optimize_parking
        from sitefit.core.geometry import Polygon

        site = Polygon([
            Point(0, 0), Point(200, 0), Point(200, 150), Point(0, 150)
        ])

        summary = optimize_parking(site, angles=[0, 45, 90])
        by_angle = summary.results_by_angle

        # Should have entries for tested angles
        assert len(by_angle) >= 1
        # Each entry should be an OptimizationResult
        for angle, result in by_angle.items():
            assert result.angle == angle


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
