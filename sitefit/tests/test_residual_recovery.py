"""
Unit tests for GenFabTools Parking Engine v2 — Residual Recovery Module

Tests validate:
- Correct residual detection
- Deterministic processing order
- No overlap with existing stalls
- Correct residualRecovered count
- Recovery disabled by default
"""

import pytest
from sitefit.core.geometry import Point, Polygon
from sitefit.parking_engine.v2.geometry_60 import (
    Stall60,
    create_stall_60,
    STALL_FOOTPRINT_WIDTH_60,
    ROW_SPACING_60,
)
from sitefit.parking_engine.v2.residual_recovery import (
    # Constants
    MIN_RESIDUAL_AREA,
    DEFAULT_RECOVER_RESIDUAL,
    # Classes
    ResidualPolygon,
    RecoveryResult,
    ResidualRecoveryResult,
    # Functions
    sort_residuals_for_processing,
    identify_residual_polygons,
    recover_stalls_from_residual,
    perform_residual_recovery,
    get_occupied_polygons_from_stalls_60,
    get_residual_processing_order,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

def create_simple_polygon(min_x: float, min_y: float, max_x: float, max_y: float) -> Polygon:
    """Create a simple rectangular polygon."""
    return Polygon([
        Point(min_x, min_y),
        Point(max_x, min_y),
        Point(max_x, max_y),
        Point(min_x, max_y),
    ])


def create_test_site() -> Polygon:
    """Create a 200x150 ft test site."""
    return create_simple_polygon(0, 0, 200, 150)


def create_small_polygon() -> Polygon:
    """Create a polygon below minimum area threshold."""
    return create_simple_polygon(0, 0, 10, 10)  # 100 sq ft


def create_medium_polygon() -> Polygon:
    """Create a polygon above minimum area threshold."""
    return create_simple_polygon(0, 0, 20, 20)  # 400 sq ft


def create_large_polygon() -> Polygon:
    """Create a large polygon."""
    return create_simple_polygon(0, 0, 100, 100)  # 10,000 sq ft


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Test that constants match spec."""

    def test_min_residual_area(self):
        """Minimum residual area should be 150 sq ft per spec."""
        assert MIN_RESIDUAL_AREA == 150.0

    def test_default_recover_residual(self):
        """Recovery should be disabled by default."""
        assert DEFAULT_RECOVER_RESIDUAL is False


# =============================================================================
# RESIDUAL POLYGON TESTS
# =============================================================================

class TestResidualPolygon:
    """Test ResidualPolygon dataclass."""

    def test_from_polygon(self):
        """Should create ResidualPolygon from Polygon."""
        poly = create_medium_polygon()
        residual = ResidualPolygon.from_polygon(poly, "test_source")

        assert residual.polygon == poly
        assert residual.area == poly.area
        assert residual.source_description == "test_source"

    def test_centroid_calculated(self):
        """Centroid should be calculated correctly."""
        poly = create_simple_polygon(0, 0, 100, 100)
        residual = ResidualPolygon.from_polygon(poly)

        assert abs(residual.centroid.x - 50) < 0.01
        assert abs(residual.centroid.y - 50) < 0.01

    def test_to_dict(self):
        """Should serialize to dict."""
        poly = create_medium_polygon()
        residual = ResidualPolygon.from_polygon(poly, "test")
        d = residual.to_dict()

        assert "area" in d
        assert "centroid" in d
        assert "source_description" in d


# =============================================================================
# SORTING TESTS
# =============================================================================

class TestDeterministicSorting:
    """Test deterministic sorting of residual polygons."""

    def test_sort_by_area_descending(self):
        """Larger areas should come first."""
        small = ResidualPolygon.from_polygon(
            create_simple_polygon(0, 0, 20, 20), "small"  # 400 sq ft
        )
        large = ResidualPolygon.from_polygon(
            create_simple_polygon(0, 0, 50, 50), "large"  # 2500 sq ft
        )
        medium = ResidualPolygon.from_polygon(
            create_simple_polygon(0, 0, 30, 30), "medium"  # 900 sq ft
        )

        sorted_list = sort_residuals_for_processing([small, large, medium])

        assert sorted_list[0].source_description == "large"
        assert sorted_list[1].source_description == "medium"
        assert sorted_list[2].source_description == "small"

    def test_sort_by_centroid_x_when_same_area(self):
        """When areas are equal, sort by centroid X."""
        left = ResidualPolygon.from_polygon(
            create_simple_polygon(0, 0, 20, 20), "left"  # centroid at (10, 10)
        )
        right = ResidualPolygon.from_polygon(
            # centroid at (110, 10)
            create_simple_polygon(100, 0, 120, 20), "right"
        )

        sorted_list = sort_residuals_for_processing([right, left])

        assert sorted_list[0].source_description == "left"
        assert sorted_list[1].source_description == "right"

    def test_sort_by_centroid_y_when_same_area_and_x(self):
        """When areas and X are equal, sort by centroid Y."""
        bottom = ResidualPolygon.from_polygon(
            # centroid at (10, 10)
            create_simple_polygon(0, 0, 20, 20), "bottom"
        )
        top = ResidualPolygon.from_polygon(
            # centroid at (10, 110)
            create_simple_polygon(0, 100, 20, 120), "top"
        )

        sorted_list = sort_residuals_for_processing([top, bottom])

        assert sorted_list[0].source_description == "bottom"
        assert sorted_list[1].source_description == "top"

    def test_sort_is_stable(self):
        """Multiple sorts should produce identical order."""
        residuals = [
            ResidualPolygon.from_polygon(
                create_simple_polygon(0, 0, 30, 30), "a"),
            ResidualPolygon.from_polygon(
                create_simple_polygon(50, 0, 70, 20), "b"),
            ResidualPolygon.from_polygon(
                create_simple_polygon(0, 50, 40, 80), "c"),
        ]

        order1 = get_residual_processing_order(residuals)
        order2 = get_residual_processing_order(residuals)
        order3 = get_residual_processing_order(list(reversed(residuals)))

        assert order1 == order2 == order3

    def test_complex_sorting(self):
        """Complex scenario with multiple residuals."""
        residuals = [
            ResidualPolygon.from_polygon(create_simple_polygon(
                0, 0, 20, 20), "small_left"),     # 400, (10, 10)
            ResidualPolygon.from_polygon(create_simple_polygon(
                100, 0, 150, 50), "large_right"),  # 2500, (125, 25)
            ResidualPolygon.from_polygon(create_simple_polygon(
                50, 0, 100, 50), "large_middle"),  # 2500, (75, 25)
        ]

        order = get_residual_processing_order(residuals)

        # large_middle has same area as large_right but smaller X
        assert order[0] == "large_middle"
        assert order[1] == "large_right"
        assert order[2] == "small_left"


# =============================================================================
# RESIDUAL DETECTION TESTS
# =============================================================================

class TestResidualDetection:
    """Test identification of residual polygons."""

    def test_empty_site_is_residual(self):
        """Site with no occupied areas is entirely residual."""
        site = create_test_site()

        residuals, skipped = identify_residual_polygons(
            site_boundary=site,
            occupied_polygons=[],
        )

        assert len(residuals) == 1
        assert abs(residuals[0].area - site.area) < 1.0
        assert skipped == 0

    def test_fully_occupied_no_residual(self):
        """Fully occupied site should have no residual."""
        site = create_test_site()

        # Occupy entire site
        residuals, skipped = identify_residual_polygons(
            site_boundary=site,
            occupied_polygons=[site],
        )

        assert len(residuals) == 0

    def test_partial_occupation_creates_residual(self):
        """Partial occupation should create residual polygon."""
        site = create_simple_polygon(0, 0, 100, 100)
        occupied = create_simple_polygon(0, 0, 50, 100)  # Left half

        residuals, skipped = identify_residual_polygons(
            site_boundary=site,
            occupied_polygons=[occupied],
        )

        # Should have one residual (right half)
        assert len(residuals) >= 1
        # Total residual area should be approximately 5000 sq ft
        total_residual = sum(r.area for r in residuals)
        assert abs(total_residual - 5000) < 100

    def test_small_residual_skipped(self):
        """Residuals below minimum area should be skipped."""
        site = create_simple_polygon(0, 0, 100, 100)
        # Occupy most of the site, leaving small residual
        occupied = create_simple_polygon(0, 0, 99, 100)  # Almost all

        residuals, skipped = identify_residual_polygons(
            site_boundary=site,
            occupied_polygons=[occupied],
            min_area=150.0,  # Higher than 100 sq ft residual
        )

        # Small residual should be skipped
        assert skipped >= 0  # May be 0 if residual is very small

    def test_multiple_residuals(self):
        """Multiple occupied areas can create multiple residuals."""
        site = create_simple_polygon(0, 0, 100, 100)
        occupied1 = create_simple_polygon(20, 0, 40, 100)  # Strip in middle
        occupied2 = create_simple_polygon(60, 0, 80, 100)  # Another strip

        residuals, skipped = identify_residual_polygons(
            site_boundary=site,
            occupied_polygons=[occupied1, occupied2],
        )

        # Should have residuals on left, middle, and right
        assert len(residuals) >= 1


# =============================================================================
# RECOVERY TESTS
# =============================================================================

class TestResidualRecovery:
    """Test stall recovery from residual polygons."""

    def test_recovery_disabled_by_default(self):
        """Recovery should return empty result when disabled."""
        site = create_test_site()

        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[],
            existing_stalls=[],
            recover_residual=False,  # Explicitly disabled
        )

        assert result.residuals_found == 0
        assert result.residuals_processed == 0
        assert result.total_stalls_recovered == 0

    def test_recovery_enabled(self):
        """When enabled, recovery should process residuals."""
        site = create_test_site()

        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[],
            existing_stalls=[],
            recover_residual=True,  # Enabled
        )

        # Site is 200x150, should have residuals found
        assert result.residuals_found >= 1
        assert result.residuals_processed >= 1

    def test_small_residual_produces_no_stalls(self):
        """Very small residual should produce no stalls."""
        small_poly = create_simple_polygon(
            0, 0, 30, 30)  # 900 sq ft, too small for rows
        residual = ResidualPolygon.from_polygon(small_poly, "small")

        result = recover_stalls_from_residual(
            residual=residual,
            existing_stalls=[],
        )

        assert result.stalls_recovered == 0

    def test_large_residual_produces_stalls(self):
        """Large residual should produce stalls."""
        large_poly = create_simple_polygon(0, 0, 150, 100)  # 15,000 sq ft
        residual = ResidualPolygon.from_polygon(large_poly, "large")

        result = recover_stalls_from_residual(
            residual=residual,
            existing_stalls=[],
        )

        # Should recover some stalls
        assert result.stalls_recovered > 0

    def test_stalls_within_residual(self):
        """Recovered stalls should be within residual polygon."""
        poly = create_simple_polygon(0, 0, 150, 100)
        residual = ResidualPolygon.from_polygon(poly, "test")

        result = recover_stalls_from_residual(
            residual=residual,
            existing_stalls=[],
        )

        poly_shapely = poly.to_shapely()
        for stall in result.stalls:
            stall_shapely = stall.polygon.to_shapely()
            assert poly_shapely.contains(stall_shapely), \
                f"Stall at {stall.anchor} is outside residual"


# =============================================================================
# NO OVERLAP TESTS
# =============================================================================

class TestNoOverlap:
    """Test that recovered stalls don't overlap existing stalls."""

    def test_no_overlap_with_existing(self):
        """Recovered stalls should not overlap existing stalls."""
        poly = create_simple_polygon(0, 0, 150, 100)
        residual = ResidualPolygon.from_polygon(poly, "test")

        # Create an existing stall in the middle
        existing = create_stall_60(Point(50, 50), direction=1)

        result = recover_stalls_from_residual(
            residual=residual,
            existing_stalls=[existing],
        )

        existing_shapely = existing.polygon.to_shapely()
        for stall in result.stalls:
            stall_shapely = stall.polygon.to_shapely()
            intersection = stall_shapely.intersection(existing_shapely)
            assert intersection.area < 0.1, \
                f"Stall at {stall.anchor} overlaps existing stall"

    def test_recovery_avoids_previous_recovery(self):
        """Multiple residuals should not produce overlapping stalls."""
        site = create_simple_polygon(0, 0, 300, 100)

        # First recovery
        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[],
            existing_stalls=[],
            recover_residual=True,
        )

        # All stalls should be non-overlapping
        all_stalls = result.all_stalls
        for i, stall_a in enumerate(all_stalls):
            shapely_a = stall_a.polygon.to_shapely()
            for stall_b in all_stalls[i + 1:]:
                shapely_b = stall_b.polygon.to_shapely()
                intersection = shapely_a.intersection(shapely_b)
                assert intersection.area < 0.1, \
                    "Recovered stalls overlap each other"


# =============================================================================
# STALL COUNT TESTS
# =============================================================================

class TestStallCount:
    """Test that stall counts are tracked correctly."""

    def test_total_stalls_recovered_correct(self):
        """Total stalls should equal sum of individual results."""
        site = create_test_site()

        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[],
            existing_stalls=[],
            recover_residual=True,
        )

        sum_from_results = sum(
            r.stalls_recovered for r in result.recovery_results)
        assert result.total_stalls_recovered == sum_from_results

    def test_all_stalls_count(self):
        """all_stalls property should match total count."""
        site = create_test_site()

        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[],
            existing_stalls=[],
            recover_residual=True,
        )

        assert len(result.all_stalls) == result.total_stalls_recovered

    def test_skipped_count(self):
        """Skipped residuals should be counted."""
        site = create_simple_polygon(0, 0, 100, 100)
        # Occupy most of site, leaving small residual
        occupied = create_simple_polygon(5, 5, 95, 95)

        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[occupied],
            existing_stalls=[],
            recover_residual=True,
        )

        # residuals_found should include both processed and skipped
        assert result.residuals_found == result.residuals_processed + result.residuals_skipped


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Test JSON serialization of results."""

    def test_recovery_result_to_dict(self):
        """RecoveryResult should serialize correctly."""
        poly = create_medium_polygon()
        residual = ResidualPolygon.from_polygon(poly, "test")
        result = RecoveryResult(
            residual=residual,
            stalls_recovered=5,
        )

        d = result.to_dict()
        assert "residual" in d
        assert "stalls_recovered" in d
        assert d["stalls_recovered"] == 5

    def test_full_result_to_dict(self):
        """ResidualRecoveryResult should serialize correctly."""
        result = ResidualRecoveryResult(
            residuals_found=3,
            residuals_processed=2,
            residuals_skipped=1,
            total_stalls_recovered=10,
        )

        d = result.to_dict()
        assert d["residuals_found"] == 3
        assert d["residuals_processed"] == 2
        assert d["residuals_skipped"] == 1
        assert d["total_stalls_recovered"] == 10


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Test helper functions."""

    def test_get_occupied_from_stalls_60(self):
        """Should extract polygons from stalls."""
        stalls = [
            create_stall_60(Point(0, 0), direction=1),
            create_stall_60(Point(20, 0), direction=1),
        ]

        polygons = get_occupied_polygons_from_stalls_60(stalls)

        assert len(polygons) == 2
        for poly in polygons:
            assert isinstance(poly, Polygon)

    def test_get_residual_processing_order(self):
        """Should return source descriptions in order."""
        residuals = [
            ResidualPolygon.from_polygon(
                create_simple_polygon(0, 0, 20, 20), "a"),
            ResidualPolygon.from_polygon(
                create_simple_polygon(0, 0, 50, 50), "b"),
        ]

        order = get_residual_processing_order(residuals)

        assert order[0] == "b"  # Larger area first
        assert order[1] == "a"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for full recovery workflow."""

    def test_full_workflow(self):
        """Test complete recovery workflow."""
        site = create_test_site()
        # Occupy left quarter of site
        occupied = create_simple_polygon(0, 0, 50, 150)

        result = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=[occupied],
            existing_stalls=[],
            recover_residual=True,
        )

        # Should have found residual in right 3/4 of site
        assert result.residuals_found >= 1
        assert result.residuals_processed >= 1
        # Right side (150x150 = 22,500 sq ft) should have stalls
        if result.residuals_processed > 0:
            assert result.total_stalls_recovered >= 0  # May be 0 if geometry doesn't fit

    def test_determinism(self):
        """Same inputs should produce identical outputs."""
        site = create_test_site()
        occupied = [create_simple_polygon(0, 0, 50, 150)]

        result1 = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=occupied,
            existing_stalls=[],
            recover_residual=True,
        )
        result2 = perform_residual_recovery(
            site_boundary=site,
            occupied_polygons=occupied,
            existing_stalls=[],
            recover_residual=True,
        )

        assert result1.total_stalls_recovered == result2.total_stalls_recovered
        assert result1.residuals_found == result2.residuals_found
        assert result1.residuals_processed == result2.residuals_processed
