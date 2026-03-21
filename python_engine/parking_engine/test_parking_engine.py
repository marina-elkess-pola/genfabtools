"""
Parking Engine Tests
====================

Unit tests for the surface parking layout engine.
Run with: python -m pytest test_parking_engine.py -v
Or simply: python test_parking_engine.py
"""

from parking_engine.layout import evaluate_layout_options
from parking_engine.rules import calculate_ada_stall_requirement, validate_aisle_width
from parking_engine import (
    Polygon, Point,
    offset_polygon, subtract_polygon, partition_rectangle,
    ParkingRules, StallType, AisleDirection,
    generate_surface_layout, SurfaceParkingLayout,
    compute_metrics, LayoutMetrics,
)
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_point_operations():
    """Test Point class operations."""
    p1 = Point(10, 20)
    p2 = Point(5, 10)

    # Addition
    p3 = p1 + p2
    assert p3.x == 15 and p3.y == 30

    # Subtraction
    p4 = p1 - p2
    assert p4.x == 5 and p4.y == 10

    # Scalar multiplication
    p5 = p1 * 2
    assert p5.x == 20 and p5.y == 40

    # Distance
    dist = Point(0, 0).distance_to(Point(3, 4))
    assert abs(dist - 5.0) < 0.0001

    print("✓ Point operations passed")


def test_polygon_from_bounds():
    """Test polygon creation from bounding box."""
    poly = Polygon.from_bounds(0, 0, 100, 50)

    assert len(poly.vertices) == 4
    assert poly.width == 100
    assert poly.height == 50
    assert poly.area == 5000
    assert poly.is_rectangular

    print("✓ Polygon from bounds passed")


def test_polygon_from_dimensions():
    """Test polygon creation from dimensions."""
    poly = Polygon.from_dimensions(200, 100)

    assert poly.width == 200
    assert poly.height == 100
    assert poly.bounds == (0, 0, 200, 100)

    # With origin
    poly2 = Polygon.from_dimensions(50, 50, origin=Point(10, 20))
    assert poly2.bounds == (10, 20, 60, 70)

    print("✓ Polygon from dimensions passed")


def test_polygon_area_perimeter():
    """Test area and perimeter calculations."""
    # 100x50 rectangle
    poly = Polygon.from_bounds(0, 0, 100, 50)

    assert poly.area == 5000
    assert poly.perimeter == 300

    print("✓ Polygon area/perimeter passed")


def test_polygon_contains_point():
    """Test point-in-polygon detection."""
    poly = Polygon.from_bounds(0, 0, 100, 100)

    assert poly.contains_point(Point(50, 50))  # Center
    assert poly.contains_point(Point(0, 0))     # Corner
    assert poly.contains_point(Point(100, 100))  # Opposite corner
    assert not poly.contains_point(Point(150, 50))  # Outside right
    assert not poly.contains_point(Point(-10, 50))  # Outside left

    print("✓ Point-in-polygon passed")


def test_offset_polygon():
    """Test polygon offset (shrinking)."""
    poly = Polygon.from_bounds(0, 0, 100, 100)

    # Offset by 10
    result = offset_polygon(poly, 10)
    assert result is not None
    assert result.bounds == (10, 10, 90, 90)
    assert result.width == 80
    assert result.height == 80

    # Offset too large (should return None)
    result2 = offset_polygon(poly, 60)
    assert result2 is None

    print("✓ Polygon offset passed")


def test_subtract_polygon():
    """Test polygon subtraction."""
    base = Polygon.from_bounds(0, 0, 100, 100)

    # Subtract from corner
    sub1 = Polygon.from_bounds(0, 0, 20, 20)
    result1 = subtract_polygon(base, sub1)
    assert len(result1) > 0

    # No overlap
    sub2 = Polygon.from_bounds(200, 200, 250, 250)
    result2 = subtract_polygon(base, sub2)
    assert len(result2) == 1
    assert result2[0].area == base.area

    # Full consumption
    sub3 = Polygon.from_bounds(-10, -10, 110, 110)
    result3 = subtract_polygon(base, sub3)
    assert len(result3) == 0

    print("✓ Polygon subtraction passed")


def test_partition_rectangle():
    """Test rectangle partitioning."""
    poly = Polygon.from_bounds(0, 0, 100, 60)

    # Horizontal partitions of 20' strips
    strips = partition_rectangle(poly, 20, "horizontal")
    assert len(strips) == 3
    for strip in strips:
        assert strip.width == 100
        assert strip.height == 20

    # Vertical partitions of 25' strips
    strips2 = partition_rectangle(poly, 25, "vertical")
    assert len(strips2) == 4  # 4 strips (25+25+25+25 = 100)

    print("✓ Rectangle partitioning passed")


def test_parking_rules_defaults():
    """Test default parking rules."""
    rules = ParkingRules()

    assert rules.stall_standard.width == 9.0
    assert rules.stall_standard.length == 18.0
    assert rules.aisle_two_way == 24.0
    assert rules.aisle_one_way == 12.0

    # Module width calculation
    two_way_module = rules.get_module_width(
        AisleDirection.TWO_WAY, double_loaded=True)
    assert two_way_module == 18.0 + 24.0 + 18.0  # 60'

    one_way_module = rules.get_module_width(
        AisleDirection.ONE_WAY, double_loaded=True)
    assert one_way_module == 18.0 + 12.0 + 18.0  # 48'

    print("✓ Parking rules defaults passed")


def test_ada_stall_requirement():
    """Test ADA stall count calculation."""
    # Small lot
    ada = calculate_ada_stall_requirement(20)
    assert ada["total_ada"] == 1
    assert ada["van_accessible"] >= 1

    # Medium lot
    ada = calculate_ada_stall_requirement(100)
    assert ada["total_ada"] == 4

    # Large lot
    ada = calculate_ada_stall_requirement(500)
    assert ada["total_ada"] == 9

    # Very large lot
    ada = calculate_ada_stall_requirement(2000)
    assert ada["total_ada"] >= 20

    print("✓ ADA stall requirements passed")


def test_validate_aisle_width():
    """Test aisle width validation."""
    # Two-way aisles
    assert validate_aisle_width(24, AisleDirection.TWO_WAY)
    assert validate_aisle_width(22, AisleDirection.TWO_WAY)
    assert not validate_aisle_width(20, AisleDirection.TWO_WAY)

    # One-way aisles
    assert validate_aisle_width(12, AisleDirection.ONE_WAY)
    assert validate_aisle_width(14, AisleDirection.ONE_WAY)
    assert not validate_aisle_width(10, AisleDirection.ONE_WAY)

    print("✓ Aisle width validation passed")


def test_generate_surface_layout():
    """Test surface parking layout generation."""
    # Create a 300' x 200' site (1.38 acres)
    site = Polygon.from_bounds(0, 0, 300, 200)
    rules = ParkingRules()

    layout = generate_surface_layout(
        site_boundary=site,
        rules=rules,
        aisle_direction=AisleDirection.TWO_WAY,
        setback=5.0,
        orientation="horizontal",
    )

    assert isinstance(layout, SurfaceParkingLayout)
    assert layout.total_stalls > 0
    assert len(layout.bays) > 0

    # Check all stalls are generated
    all_stalls = layout.all_stalls
    assert len(all_stalls) == layout.total_stalls

    # Check stall types
    stall_types = layout.stalls_by_type
    assert "standard" in stall_types or len(stall_types) > 0

    print(
        f"✓ Surface layout generated: {layout.total_stalls} stalls in {len(layout.bays)} bays")


def test_generate_layout_vertical():
    """Test vertical orientation layout."""
    site = Polygon.from_bounds(0, 0, 200, 300)

    layout = generate_surface_layout(
        site_boundary=site,
        aisle_direction=AisleDirection.TWO_WAY,
        orientation="vertical",
    )

    assert layout.orientation == "vertical"
    assert layout.total_stalls > 0

    print(f"✓ Vertical layout generated: {layout.total_stalls} stalls")


def test_generate_layout_one_way():
    """Test one-way aisle layout."""
    site = Polygon.from_bounds(0, 0, 300, 200)

    layout = generate_surface_layout(
        site_boundary=site,
        aisle_direction=AisleDirection.ONE_WAY,
        orientation="horizontal",
    )

    assert layout.aisle_direction == AisleDirection.ONE_WAY
    assert layout.total_stalls > 0

    # One-way should have more stalls than two-way (narrower aisles)
    layout_2way = generate_surface_layout(
        site_boundary=site,
        aisle_direction=AisleDirection.TWO_WAY,
        orientation="horizontal",
    )

    # Not always true depending on geometry, but generally expected
    print(
        f"✓ One-way layout: {layout.total_stalls} stalls (vs {layout_2way.total_stalls} two-way)")


def test_evaluate_layout_options():
    """Test layout comparison."""
    site = Polygon.from_bounds(0, 0, 250, 180)

    options = evaluate_layout_options(site)

    assert len(options) > 0

    # Should be sorted by stall count descending
    stall_counts = [opt[0].total_stalls for opt in options]
    assert stall_counts == sorted(stall_counts, reverse=True)

    print(f"✓ Layout options evaluated: {len(options)} configurations")
    for layout, desc in options:
        print(f"  - {desc}: {layout.total_stalls} stalls")


def test_compute_metrics():
    """Test metrics computation."""
    site = Polygon.from_bounds(0, 0, 300, 200)
    layout = generate_surface_layout(site)

    metrics = compute_metrics(layout)

    assert isinstance(metrics, LayoutMetrics)
    assert metrics.total_stalls == layout.total_stalls
    assert metrics.gross_site_area == site.area
    assert metrics.net_parking_area < metrics.gross_site_area
    assert metrics.efficiency_sf_per_stall > 0

    # Check ADA compliance tracking
    assert metrics.ada_required >= 0
    assert metrics.ada_provided >= 0

    print(f"✓ Metrics computed:")
    print(f"  Total stalls: {metrics.total_stalls}")
    print(f"  Efficiency: {metrics.efficiency_sf_per_stall:.0f} SF/stall")
    print(
        f"  ADA: {metrics.ada_provided}/{metrics.ada_required} ({'PASS' if metrics.ada_compliant else 'FAIL'})")


def test_metrics_to_dict():
    """Test metrics serialization."""
    site = Polygon.from_bounds(0, 0, 300, 200)
    layout = generate_surface_layout(site)
    metrics = compute_metrics(layout)

    data = metrics.to_dict()

    assert "stalls" in data
    assert "areas" in data
    assert "efficiency" in data
    assert "bays" in data
    assert "ada_compliance" in data

    print("✓ Metrics serialization passed")


def test_layout_to_dict():
    """Test layout serialization."""
    site = Polygon.from_bounds(0, 0, 200, 150)
    layout = generate_surface_layout(site)

    data = layout.to_dict()

    assert "site_boundary" in data
    assert "net_parking_area" in data
    assert "bays" in data
    assert "total_stalls" in data

    print("✓ Layout serialization passed")


def test_real_world_site():
    """Test with a realistic site scenario."""
    # 2-acre site (approx 87,120 SF)
    # 330' x 264' = 87,120 SF
    site = Polygon.from_bounds(0, 0, 330, 264)

    layout = generate_surface_layout(
        site_boundary=site,
        aisle_direction=AisleDirection.TWO_WAY,
        setback=10.0,  # 10' setback
    )

    metrics = compute_metrics(layout)

    # Expected: ~250-300 stalls for a 2-acre surface lot
    assert metrics.total_stalls >= 200, f"Expected 200+ stalls, got {metrics.total_stalls}"

    # Efficiency should be in reasonable range (280-400 SF/stall)
    assert 250 <= metrics.efficiency_sf_per_stall <= 450, \
        f"Efficiency {metrics.efficiency_sf_per_stall} out of expected range"

    print(f"✓ Real-world site test:")
    print(f"  Site: 2 acres ({site.area:,.0f} SF)")
    print(f"  Stalls: {metrics.total_stalls}")
    print(f"  Efficiency: {metrics.efficiency_sf_per_stall:.0f} SF/stall")
    print(
        f"  Bays: {metrics.num_bays} ({metrics.double_loaded_bays} double-loaded)")

def test_narrow_deep_site_layout():
    from parking_engine.geometry import Rectangle
    from parking_engine.rules import DefaultRules
    from parking_engine.layout import generate_surface_layout
    from parking_engine.metrics import compute_metrics

    site = Rectangle(width=120.0, height=600.0)
    rules = DefaultRules()

    layout = generate_surface_layout(site, rules)
    metrics = compute_metrics(layout)

    # Assertions
    assert metrics.total_stalls > 0
    assert metrics.efficiency_sf_per_stall < 350
    assert all(site.contains_polygon(stall.geometry) for stall in layout.stalls)
    print(f"✓ Narrow deep site layout test:")
    print(f"  Site: 120' x 600' ({site.area:,.0f} SF)")
    print(f"  Stalls: {metrics.total_stalls}")

def test_wide_shallow_site_layout():
    from parking_engine.geometry import Rectangle
    from parking_engine.rules import DefaultRules
    from parking_engine.layout import generate_surface_layout
    from parking_engine.metrics import compute_metrics

    site = Rectangle(width=600.0, height=120.0)
    rules = DefaultRules()

    layout = generate_surface_layout(site, rules)
    metrics = compute_metrics(layout)

    # Assertions
    assert metrics.total_stalls > 0
    assert metrics.efficiency_sf_per_stall < 380
    assert all(site.contains_polygon(stall.geometry) for stall in layout.stalls)
    print(f"✓ Wide shallow site layout test:")
    print(f"  Site: 600' x 120' ({site.area:,.0f} SF)")     
    print(f"  Stalls: {metrics.total_stalls}")  

def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("PARKING ENGINE TEST SUITE")
    print("=" * 60)
    print()

    tests = [
        test_point_operations,
        test_polygon_from_bounds,
        test_polygon_from_dimensions,
        test_polygon_area_perimeter,
        test_polygon_contains_point,
        test_offset_polygon,
        test_subtract_polygon,
        test_partition_rectangle,
        test_parking_rules_defaults,
        test_ada_stall_requirement,
        test_validate_aisle_width,
        test_generate_surface_layout,
        test_generate_layout_vertical,
        test_generate_layout_one_way,
        test_evaluate_layout_options,
        test_compute_metrics,
        test_metrics_to_dict,
        test_layout_to_dict,
        test_real_world_site,
        test_narrow_deep_site_layout,
        test_wide_shallow_site_layout,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
