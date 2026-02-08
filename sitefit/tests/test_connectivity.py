"""
Unit tests for GenFabTools Parking Engine v2 — Connectivity Check Module

Tests validate:
- Fully connected layout returns true
- Disconnected aisle clusters return false
- Deterministic behavior
- O(n) / O(n log n) performance
"""

import pytest
import time
from sitefit.core.geometry import Point, Line
from sitefit.parking_engine.v2.geometry_60 import Aisle60, create_aisle_60
from sitefit.parking_engine.v2.connectivity import (
    # Constants
    ENDPOINT_TOLERANCE,
    INTERSECTION_TOLERANCE,
    # Classes
    UnionFind,
    ConnectivityResult,
    # Functions
    check_circulation_connected,
    check_circulation_connectivity,
    get_connected_components,
    count_connected_components,
    _points_are_close,
    _aisles_share_endpoint,
    _aisles_are_connected,
    _get_aisle_endpoints,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

def create_horizontal_aisle(y: float, x_start: float = 0, x_end: float = 100) -> Aisle60:
    """Create a horizontal aisle at given y coordinate."""
    return create_aisle_60(Point(x_start, y), Point(x_end, y))


def create_vertical_aisle(x: float, y_start: float = 0, y_end: float = 100) -> Aisle60:
    """Create a vertical aisle at given x coordinate."""
    return create_aisle_60(Point(x, y_start), Point(x, y_end))


def create_point_tuple(x1: float, y1: float, x2: float, y2: float) -> tuple:
    """Create a (Point, Point) tuple representing an aisle."""
    return (Point(x1, y1), Point(x2, y2))


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Test that constants are reasonable."""

    def test_endpoint_tolerance_positive(self):
        """Endpoint tolerance should be positive."""
        assert ENDPOINT_TOLERANCE > 0

    def test_intersection_tolerance_positive(self):
        """Intersection tolerance should be positive."""
        assert INTERSECTION_TOLERANCE > 0

    def test_endpoint_tolerance_reasonable(self):
        """Endpoint tolerance should be less than a foot."""
        assert ENDPOINT_TOLERANCE <= 1.0


# =============================================================================
# UNION-FIND TESTS
# =============================================================================

class TestUnionFind:
    """Test Union-Find data structure."""

    def test_initial_state(self):
        """Each element starts as its own component."""
        uf = UnionFind(5)
        assert uf.get_component_count() == 5
        assert not uf.is_connected()

    def test_single_element(self):
        """Single element is trivially connected."""
        uf = UnionFind(1)
        assert uf.get_component_count() == 1
        assert uf.is_connected()

    def test_union_reduces_components(self):
        """Union should reduce component count."""
        uf = UnionFind(3)
        assert uf.union(0, 1)
        assert uf.get_component_count() == 2

    def test_union_same_set_returns_false(self):
        """Union of same set returns False."""
        uf = UnionFind(3)
        uf.union(0, 1)
        assert not uf.union(0, 1)  # Already same set

    def test_transitive_connection(self):
        """A-B and B-C implies A-C connected."""
        uf = UnionFind(3)
        uf.union(0, 1)
        uf.union(1, 2)
        assert uf.find(0) == uf.find(2)

    def test_full_connectivity(self):
        """All elements connected means is_connected = True."""
        uf = UnionFind(4)
        uf.union(0, 1)
        uf.union(2, 3)
        assert not uf.is_connected()
        uf.union(1, 2)
        assert uf.is_connected()


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Test helper functions."""

    def test_points_are_close_same_point(self):
        """Same point should be close."""
        p = Point(10, 20)
        assert _points_are_close(p, p)

    def test_points_are_close_within_tolerance(self):
        """Points within tolerance are close."""
        p1 = Point(0, 0)
        p2 = Point(0.4, 0)
        assert _points_are_close(p1, p2, tolerance=0.5)

    def test_points_are_close_outside_tolerance(self):
        """Points outside tolerance are not close."""
        p1 = Point(0, 0)
        p2 = Point(1, 0)
        assert not _points_are_close(p1, p2, tolerance=0.5)

    def test_get_endpoints_from_aisle60(self):
        """Should extract endpoints from Aisle60."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        start, end = _get_aisle_endpoints(aisle)
        assert start.x == 0 and start.y == 0
        assert end.x == 100 and end.y == 0

    def test_get_endpoints_from_tuple(self):
        """Should extract endpoints from tuple."""
        aisle = (Point(10, 20), Point(30, 40))
        start, end = _get_aisle_endpoints(aisle)
        assert start.x == 10 and start.y == 20
        assert end.x == 30 and end.y == 40

    def test_aisles_share_endpoint_start_start(self):
        """Aisles sharing start points are connected."""
        a = (Point(0, 0), Point(100, 0))
        b = (Point(0, 0), Point(0, 100))
        assert _aisles_share_endpoint(a, b)

    def test_aisles_share_endpoint_end_start(self):
        """Aisles where end meets start are connected."""
        a = (Point(0, 0), Point(50, 0))
        b = (Point(50, 0), Point(100, 0))
        assert _aisles_share_endpoint(a, b)

    def test_aisles_no_shared_endpoint(self):
        """Parallel aisles don't share endpoints."""
        a = (Point(0, 0), Point(100, 0))
        b = (Point(0, 50), Point(100, 50))
        assert not _aisles_share_endpoint(a, b)


# =============================================================================
# BASIC CONNECTIVITY TESTS
# =============================================================================

class TestBasicConnectivity:
    """Test basic connectivity scenarios."""

    def test_empty_list_is_connected(self):
        """Empty aisle list is trivially connected."""
        assert check_circulation_connected([])

    def test_single_aisle_is_connected(self):
        """Single aisle is trivially connected."""
        aisle = create_point_tuple(0, 0, 100, 0)
        assert check_circulation_connected([aisle])

    def test_two_connected_aisles(self):
        """Two aisles sharing an endpoint are connected."""
        a1 = create_point_tuple(0, 0, 50, 0)
        a2 = create_point_tuple(50, 0, 100, 0)
        assert check_circulation_connected([a1, a2])

    def test_two_disconnected_aisles(self):
        """Two parallel aisles are disconnected."""
        a1 = create_point_tuple(0, 0, 100, 0)
        a2 = create_point_tuple(0, 50, 100, 50)
        assert not check_circulation_connected([a1, a2])

    def test_t_junction_connected(self):
        """T-junction is connected."""
        horizontal = create_point_tuple(0, 0, 100, 0)
        vertical = create_point_tuple(50, 0, 50, 100)
        assert check_circulation_connected([horizontal, vertical])

    def test_cross_intersection_connected(self):
        """Two crossing aisles are connected."""
        horizontal = create_point_tuple(0, 50, 100, 50)
        vertical = create_point_tuple(50, 0, 50, 100)
        assert check_circulation_connected([horizontal, vertical])


# =============================================================================
# COMPLEX CONNECTIVITY TESTS
# =============================================================================

class TestComplexConnectivity:
    """Test complex connectivity scenarios."""

    def test_chain_of_aisles_connected(self):
        """Chain of connected aisles forms single component."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 100, 0),
            create_point_tuple(100, 0, 150, 0),
            create_point_tuple(150, 0, 200, 0),
        ]
        assert check_circulation_connected(aisles)

    def test_grid_connected(self):
        """Grid of aisles is connected."""
        aisles = [
            # Horizontal
            create_point_tuple(0, 0, 100, 0),
            create_point_tuple(0, 50, 100, 50),
            # Vertical
            create_point_tuple(0, 0, 0, 50),
            create_point_tuple(50, 0, 50, 50),
            create_point_tuple(100, 0, 100, 50),
        ]
        assert check_circulation_connected(aisles)

    def test_two_separate_clusters_disconnected(self):
        """Two separate clusters are disconnected."""
        # Cluster 1
        cluster1 = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 50, 50),
        ]
        # Cluster 2 (far away)
        cluster2 = [
            create_point_tuple(200, 0, 250, 0),
            create_point_tuple(250, 0, 250, 50),
        ]
        assert not check_circulation_connected(cluster1 + cluster2)

    def test_loop_connected(self):
        """Loop/circuit is connected."""
        aisles = [
            create_point_tuple(0, 0, 100, 0),    # Bottom
            create_point_tuple(100, 0, 100, 100),  # Right
            create_point_tuple(0, 100, 100, 100),  # Top
            create_point_tuple(0, 0, 0, 100),    # Left
        ]
        assert check_circulation_connected(aisles)

    def test_star_topology_connected(self):
        """Star topology (all meeting at center) is connected."""
        center = Point(50, 50)
        aisles = [
            create_point_tuple(50, 50, 100, 50),  # Right
            create_point_tuple(50, 50, 0, 50),    # Left
            create_point_tuple(50, 50, 50, 100),  # Up
            create_point_tuple(50, 50, 50, 0),    # Down
        ]
        assert check_circulation_connected(aisles)


# =============================================================================
# AISLE60 INTEGRATION TESTS
# =============================================================================

class TestAisle60Integration:
    """Test with actual Aisle60 objects."""

    def test_aisle60_connected(self):
        """Aisle60 objects connected via shared endpoint."""
        a1 = create_aisle_60(Point(0, 0), Point(50, 0))
        a2 = create_aisle_60(Point(50, 0), Point(100, 0))
        assert check_circulation_connected([a1, a2])

    def test_aisle60_disconnected(self):
        """Parallel Aisle60 objects are disconnected."""
        a1 = create_aisle_60(Point(0, 0), Point(100, 0))
        a2 = create_aisle_60(Point(0, 100), Point(100, 100))
        assert not check_circulation_connected([a1, a2])

    def test_mixed_aisle_types(self):
        """Can mix Aisle60 and tuples."""
        a1 = create_aisle_60(Point(0, 0), Point(50, 0))
        a2 = create_point_tuple(50, 0, 100, 0)
        assert check_circulation_connected([a1, a2])


# =============================================================================
# TOLERANCE TESTS
# =============================================================================

class TestTolerance:
    """Test endpoint tolerance handling."""

    def test_near_miss_within_tolerance(self):
        """Points just within tolerance are connected."""
        a1 = create_point_tuple(0, 0, 50, 0)
        a2 = create_point_tuple(50.3, 0, 100, 0)  # 0.3 ft gap
        assert check_circulation_connected([a1, a2], tolerance=0.5)

    def test_near_miss_outside_tolerance(self):
        """Points just outside tolerance are not connected."""
        a1 = create_point_tuple(0, 0, 50, 0)
        a2 = create_point_tuple(51, 0, 100, 0)  # 1 ft gap
        assert not check_circulation_connected([a1, a2], tolerance=0.5)

    def test_custom_tolerance(self):
        """Can use custom tolerance."""
        a1 = create_point_tuple(0, 0, 50, 0)
        a2 = create_point_tuple(52, 0, 100, 0)  # 2 ft gap
        assert not check_circulation_connected([a1, a2], tolerance=0.5)
        assert check_circulation_connected([a1, a2], tolerance=2.5)


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

class TestDeterminism:
    """Test deterministic behavior."""

    def test_same_input_same_output(self):
        """Same input produces same output."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 100, 0),
            create_point_tuple(100, 0, 100, 50),
        ]

        results = [check_circulation_connected(aisles) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_order_independent(self):
        """Result is independent of input order."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 100, 0),
            create_point_tuple(100, 0, 100, 50),
        ]

        import random
        for _ in range(5):
            shuffled = aisles.copy()
            random.shuffle(shuffled)
            assert check_circulation_connected(
                shuffled) == check_circulation_connected(aisles)

    def test_connected_stability(self):
        """Connected result is stable across multiple calls."""
        aisles = [
            create_point_tuple(0, 0, 100, 0),
            create_point_tuple(50, 0, 50, 100),
        ]

        assert all(check_circulation_connected(aisles) for _ in range(100))

    def test_disconnected_stability(self):
        """Disconnected result is stable across multiple calls."""
        aisles = [
            create_point_tuple(0, 0, 100, 0),
            create_point_tuple(0, 200, 100, 200),
        ]

        assert all(not check_circulation_connected(aisles) for _ in range(100))


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Test O(n) / O(n log n) performance."""

    def test_linear_chain_performance(self):
        """Linear chain of n aisles should complete quickly."""
        # Create chain of 1000 connected aisles
        n = 1000
        aisles = []
        for i in range(n):
            aisles.append(create_point_tuple(i * 10, 0, (i + 1) * 10, 0))

        start = time.time()
        result = check_circulation_connected(aisles)
        elapsed = time.time() - start

        assert result is True
        # Should complete in under 2 seconds on any reasonable hardware
        assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s for {n} aisles"

    def test_grid_performance(self):
        """Grid of n×n aisles should complete quickly."""
        # Create 20×20 grid (400 horizontal + 400 vertical = 800 aisles)
        n = 20
        aisles = []

        # Horizontal aisles
        for row in range(n):
            for col in range(n - 1):
                x1 = col * 10
                x2 = (col + 1) * 10
                y = row * 10
                aisles.append(create_point_tuple(x1, y, x2, y))

        # Vertical aisles
        for row in range(n - 1):
            for col in range(n):
                x = col * 10
                y1 = row * 10
                y2 = (row + 1) * 10
                aisles.append(create_point_tuple(x, y1, x, y2))

        start = time.time()
        result = check_circulation_connected(aisles)
        elapsed = time.time() - start

        assert result is True
        # Should complete in under 2 seconds
        assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s for {len(aisles)} aisles"


# =============================================================================
# CONNECTIVITY RESULT TESTS
# =============================================================================

class TestConnectivityResult:
    """Test ConnectivityResult and full diagnostics."""

    def test_result_connected(self):
        """Connected result has correct fields."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 100, 0),
        ]
        result = check_circulation_connectivity(aisles)

        assert result.is_connected is True
        assert result.aisle_count == 2
        assert result.component_count == 1

    def test_result_disconnected(self):
        """Disconnected result has correct component count."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(100, 0, 150, 0),  # Gap
        ]
        result = check_circulation_connectivity(aisles)

        assert result.is_connected is False
        assert result.aisle_count == 2
        assert result.component_count == 2

    def test_result_to_dict(self):
        """Result should serialize to dict."""
        aisles = [create_point_tuple(0, 0, 100, 0)]
        result = check_circulation_connectivity(aisles)
        d = result.to_dict()

        assert "is_connected" in d
        assert "aisle_count" in d
        assert "component_count" in d

    def test_empty_result(self):
        """Empty input produces valid result."""
        result = check_circulation_connectivity([])
        assert result.is_connected is True
        assert result.aisle_count == 0
        assert result.component_count == 0


# =============================================================================
# COMPONENT ANALYSIS TESTS
# =============================================================================

class TestComponentAnalysis:
    """Test component counting and grouping."""

    def test_count_single_component(self):
        """Single connected network has count 1."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 100, 0),
        ]
        assert count_connected_components(aisles) == 1

    def test_count_multiple_components(self):
        """Two clusters have count 2."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(100, 0, 150, 0),
        ]
        assert count_connected_components(aisles) == 2

    def test_get_components_single(self):
        """Get components for single network."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),
            create_point_tuple(50, 0, 100, 0),
        ]
        components = get_connected_components(aisles)

        assert len(components) == 1
        assert len(components[0]) == 2

    def test_get_components_multiple(self):
        """Get components for multiple networks."""
        aisles = [
            create_point_tuple(0, 0, 50, 0),     # Component 1
            create_point_tuple(100, 0, 150, 0),  # Component 2
            create_point_tuple(50, 0, 50, 50),   # Connects to component 1
        ]
        components = get_connected_components(aisles)

        assert len(components) == 2
        # Find the larger component (should have 2 aisles)
        sizes = sorted([len(c) for c in components], reverse=True)
        assert sizes == [2, 1]
