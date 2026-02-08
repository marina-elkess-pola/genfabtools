"""
Structured Parking Engine Tests
===============================

Unit tests for the structured parking skeleton.
Validates architecture correctness without stall placement.

Run with: python -m parking_engine.test_structured
"""

from parking_engine.structured_metrics import (
    compute_structured_metrics,
    StructuredMetrics,
    estimate_structured_capacity,
)
from parking_engine.structured import (
    generate_structured_parking_skeleton,
    StructuredParkingLayout,
    ParkingLevel,
    Ramp,
    VerticalCore,
    RampType,
    CoreType,
    generate_floor_plate,
    stack_levels,
    compute_structure_height,
    generate_ramp_footprint,
    generate_core_footprint,
)
from parking_engine import Polygon, Point, ParkingRules
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_generate_floor_plate():
    """Test single floor plate generation."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    level = generate_floor_plate(
        footprint=footprint,
        level_index=0,
        elevation=0.0,
        is_roof=False,
    )

    assert isinstance(level, ParkingLevel)
    assert level.level_index == 0
    assert level.elevation == 0.0
    assert level.is_roof is False
    assert level.is_ground is True  # level_index == 0 means ground
    assert level.gross_area == 300 * 180
    assert level.net_area == level.gross_area  # No subtraction in skeleton

    # Test non-ground level
    level_2 = generate_floor_plate(
        footprint=footprint,
        level_index=2,
        elevation=21.0,
        is_roof=False,
    )
    assert level_2.is_ground is False

    print("✓ Floor plate generation passed")


def test_floor_plate_with_reservations():
    """Test floor plate with ramp and core reservations."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)
    ramp_res = [Polygon.from_bounds(240, 164, 300, 180)]  # 60x16 = 960 SF
    core_res = [Polygon.from_bounds(140, 77.5, 160, 102.5)]  # 20x25 = 500 SF

    level = generate_floor_plate(
        footprint=footprint,
        level_index=2,
        elevation=21.0,
        ramp_reservations=ramp_res,
        core_reservations=core_res,
    )

    assert len(level.ramp_reservations) == 1
    assert len(level.core_reservations) == 1
    assert level.reserved_area == 960 + 500

    print("✓ Floor plate with reservations passed")


def test_stack_levels():
    """Test vertical stacking of floor plates."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    levels = stack_levels(
        footprint=footprint,
        level_count=4,
        floor_to_floor_height=10.5,
    )

    assert len(levels) == 4

    # Check elevations
    assert levels[0].elevation == 0.0
    assert levels[1].elevation == 10.5
    assert levels[2].elevation == 21.0
    assert levels[3].elevation == 31.5

    # Check ground and roof flags
    assert levels[0].is_ground is True
    assert levels[0].is_roof is False
    assert levels[3].is_ground is False
    assert levels[3].is_roof is True

    # Middle levels
    assert levels[1].is_ground is False
    assert levels[1].is_roof is False

    print("✓ Level stacking passed")


def test_compute_structure_height():
    """Test structure height calculation."""
    # 4 levels at 10.5' each = 42'
    height = compute_structure_height(4, 10.5)
    assert height == 42.0

    # 3 levels at 11' each = 33'
    height = compute_structure_height(3, 11.0)
    assert height == 33.0

    # Edge case: 0 levels
    height = compute_structure_height(0, 10.5)
    assert height == 0.0

    print("✓ Structure height calculation passed")


def test_generate_ramp_footprint():
    """Test ramp footprint generation at various locations."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    # Northeast corner
    ramp_ne = generate_ramp_footprint(
        footprint, RampType.SINGLE_HELIX, "northeast", 16, 60)
    min_x, min_y, max_x, max_y = ramp_ne.bounds
    assert max_x == 300  # At right edge
    assert max_y == 180  # At top edge
    assert ramp_ne.width == 60
    assert ramp_ne.height == 16

    # Southwest corner
    ramp_sw = generate_ramp_footprint(
        footprint, RampType.SINGLE_HELIX, "southwest", 16, 60)
    min_x, min_y, max_x, max_y = ramp_sw.bounds
    assert min_x == 0  # At left edge
    assert min_y == 0  # At bottom edge

    print("✓ Ramp footprint generation passed")


def test_generate_core_footprint():
    """Test core footprint generation at various locations."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    # Center
    core_center = generate_core_footprint(
        footprint, CoreType.STAIR_ELEVATOR, "center", 20, 25)
    min_x, min_y, max_x, max_y = core_center.bounds
    # Should be centered
    assert abs((min_x + max_x) / 2 - 150) < 0.01
    assert abs((min_y + max_y) / 2 - 90) < 0.01

    # North
    core_north = generate_core_footprint(
        footprint, CoreType.STAIR_ELEVATOR, "north", 20, 25)
    _, _, _, max_y = core_north.bounds
    assert max_y == 180  # At top edge

    print("✓ Core footprint generation passed")


def test_generate_structured_skeleton_basic():
    """Test basic structured parking skeleton generation."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=4,
        floor_to_floor_height=10.5,
    )

    assert isinstance(layout, StructuredParkingLayout)
    assert layout.level_count == 4
    assert layout.floor_to_floor_height == 10.5
    assert layout.total_height == 4 * 10.5

    print("✓ Basic skeleton generation passed")


def test_structured_skeleton_levels():
    """Test level properties in skeleton."""
    footprint = Polygon.from_bounds(0, 0, 250, 150)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=3,
        floor_to_floor_height=11.0,
    )

    # Check level count
    assert len(layout.levels) == 3

    # Check each level
    for i, level in enumerate(layout.levels):
        assert level.level_index == i
        assert level.elevation == i * 11.0
        assert level.gross_area == 250 * 150

    # Ground and roof flags
    assert layout.levels[0].is_ground is True
    assert layout.levels[-1].is_roof is True

    print("✓ Skeleton level properties passed")


def test_structured_skeleton_ramps():
    """Test ramp generation in skeleton."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=4,
        floor_to_floor_height=10.5,
    )

    # Should have 3 ramps (connecting 4 levels)
    assert len(layout.ramps) == 3

    # Check ramp connectivity
    assert layout.ramps[0].from_level == 0
    assert layout.ramps[0].to_level == 1
    assert layout.ramps[1].from_level == 1
    assert layout.ramps[1].to_level == 2
    assert layout.ramps[2].from_level == 2
    assert layout.ramps[2].to_level == 3

    print("✓ Skeleton ramp generation passed")


def test_structured_skeleton_cores():
    """Test core generation in skeleton."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=4,
        floor_to_floor_height=10.5,
    )

    # Should have 1 core (default)
    assert len(layout.cores) == 1
    assert layout.cores[0].core_type == CoreType.STAIR_ELEVATOR
    assert layout.cores[0].area > 0

    print("✓ Skeleton core generation passed")


def test_structured_skeleton_custom_config():
    """Test skeleton with custom ramp and core configuration."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=5,
        floor_to_floor_height=10.0,
        ramp_config={
            "type": "double_helix",
            "location": "southwest",
            "width": 20,
            "length": 70,
        },
        core_config={
            "type": "stair_multi_elevator",
            "location": "north",
            "width": 25,
            "depth": 30,
        },
    )

    assert layout.level_count == 5
    assert layout.ramps[0].ramp_type == RampType.DOUBLE_HELIX
    assert layout.cores[0].core_type == CoreType.STAIR_MULTI_ELEVATOR

    print("✓ Custom configuration passed")


def test_structured_skeleton_no_stalls():
    """Verify that skeleton contains no stalls."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=4,
        floor_to_floor_height=10.5,
    )

    # No stall-related attributes should exist
    for level in layout.levels:
        assert not hasattr(level, 'stalls')
        assert not hasattr(level, 'bays')

    print("✓ No stalls present in skeleton (correct)")


def test_structured_skeleton_validation():
    """Test input validation."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    # Invalid level count
    try:
        generate_structured_parking_skeleton(footprint, level_count=0)
        assert False, "Should raise ValueError for level_count=0"
    except ValueError:
        pass

    # Invalid floor-to-floor height
    try:
        generate_structured_parking_skeleton(
            footprint, level_count=3, floor_to_floor_height=5.0)
        assert False, "Should raise ValueError for floor_to_floor_height < 8"
    except ValueError:
        pass

    print("✓ Input validation passed")


def test_structured_skeleton_serialization():
    """Test skeleton serialization to dict."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=3,
        floor_to_floor_height=10.5,
    )

    data = layout.to_dict()

    assert "level_count" in data
    assert "levels" in data
    assert "ramps" in data
    assert "cores" in data
    assert "total_height_ft" in data
    assert data["level_count"] == 3
    assert len(data["levels"]) == 3

    print("✓ Skeleton serialization passed")


def test_compute_structured_metrics():
    """Test structured metrics computation."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)

    layout = generate_structured_parking_skeleton(
        footprint=footprint,
        level_count=4,
        floor_to_floor_height=10.5,
    )

    metrics = compute_structured_metrics(layout)

    assert isinstance(metrics, StructuredMetrics)
    assert metrics.level_count == 4
    assert metrics.floor_to_floor_height == 10.5
    assert metrics.total_height == 42.0
    assert metrics.footprint_area == 300 * 180
    assert metrics.total_gross_area == 300 * 180 * 4

    # Placeholder stall estimates should exist but be marked as estimates
    assert metrics.estimated_total_stalls > 0
    assert metrics.estimated_stalls_per_level > 0

    print(f"✓ Structured metrics computed:")
    print(f"  Levels: {metrics.level_count}")
    print(f"  Total gross: {metrics.total_gross_area:,.0f} SF")
    print(
        f"  Estimated stalls: {metrics.estimated_total_stalls} (placeholder)")


def test_structured_metrics_serialization():
    """Test metrics serialization."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)
    layout = generate_structured_parking_skeleton(footprint, 4, 10.5)
    metrics = compute_structured_metrics(layout)

    data = metrics.to_dict()

    assert "structure" in data
    assert "areas" in data
    assert "efficiency" in data
    assert "levels" in data
    assert "stall_estimates" in data
    assert "note" in data["stall_estimates"]

    print("✓ Metrics serialization passed")


def test_estimate_structured_capacity():
    """Test quick capacity estimation."""
    estimate = estimate_structured_capacity(
        footprint_area_sf=54000,  # 300 x 180
        level_count=4,
        efficiency_sf_per_stall=325,
    )

    assert "capacity_low" in estimate
    assert "capacity_mid" in estimate
    assert "capacity_high" in estimate
    assert estimate["level_count"] == 4
    assert estimate["footprint_sf"] == 54000
    assert estimate["capacity_mid"] > 0

    # Mid should be between low and high
    assert estimate["capacity_low"] < estimate["capacity_mid"] < estimate["capacity_high"]

    print(f"✓ Capacity estimate: {estimate['capacity_mid']} stalls (mid)")


def test_level_get():
    """Test getting level by index."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)
    layout = generate_structured_parking_skeleton(footprint, 4, 10.5)

    level_0 = layout.get_level(0)
    level_2 = layout.get_level(2)
    level_99 = layout.get_level(99)

    assert level_0 is not None
    assert level_0.level_index == 0
    assert level_2 is not None
    assert level_2.level_index == 2
    assert level_99 is None

    print("✓ Level get by index passed")


def test_areas_consistency():
    """Test that areas are internally consistent."""
    footprint = Polygon.from_bounds(0, 0, 300, 180)
    layout = generate_structured_parking_skeleton(footprint, 4, 10.5)

    # Total gross should equal footprint * levels
    expected_total_gross = footprint.area * layout.level_count
    assert layout.total_gross_area == expected_total_gross

    # Each level gross should equal footprint
    for level in layout.levels:
        assert level.gross_area == footprint.area

    print("✓ Area consistency passed")


def run_all_tests():
    """Run all structured parking tests."""
    print("=" * 60)
    print("STRUCTURED PARKING SKELETON TEST SUITE")
    print("=" * 60)
    print()

    tests = [
        test_generate_floor_plate,
        test_floor_plate_with_reservations,
        test_stack_levels,
        test_compute_structure_height,
        test_generate_ramp_footprint,
        test_generate_core_footprint,
        test_generate_structured_skeleton_basic,
        test_structured_skeleton_levels,
        test_structured_skeleton_ramps,
        test_structured_skeleton_cores,
        test_structured_skeleton_custom_config,
        test_structured_skeleton_no_stalls,
        test_structured_skeleton_validation,
        test_structured_skeleton_serialization,
        test_compute_structured_metrics,
        test_structured_metrics_serialization,
        test_estimate_structured_capacity,
        test_level_get,
        test_areas_consistency,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
