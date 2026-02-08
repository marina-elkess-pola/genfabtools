"""
Tests for core/operations.py

Run with: python -m pytest tests/test_operations.py -v
"""

import math
import pytest
from sitefit.core.geometry import Point, Line, Polygon, Rectangle
from sitefit.core.operations import (
    # Boolean operations
    union, intersection, difference, subtract_all, symmetric_difference,
    # Buffer operations
    buffer, inset, offset, inset_square,
    # Line clipping
    clip_line_to_polygon, clip_lines_to_polygon, extend_line_to_polygon,
    # Parallel lines
    generate_parallel_lines, generate_grid_lines,
    # Spatial relationships
    polygons_intersect, polygon_contains, point_in_polygon, line_intersects_polygon,
    # Area calculations
    total_area, intersection_area, coverage_ratio,
    # Utilities
    convex_hull, split_polygon_with_line, simplify
)


class TestBooleanOperations:
    """Tests for polygon boolean operations."""

    def test_union_overlapping(self):
        """Two overlapping rectangles should merge."""
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(5, 0), (15, 0), (15, 10), (5, 10)])

        result = union([p1, p2])
        assert len(result) == 1
        assert result[0].area == 150.0  # 15*10 = 150

    def test_union_separate(self):
        """Two separate rectangles should stay separate."""
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(20, 0), (30, 0), (30, 10), (20, 10)])

        result = union([p1, p2])
        assert len(result) == 2
        assert total_area(result) == 200.0

    def test_union_empty(self):
        """Union of empty list should be empty."""
        result = union([])
        assert result == []

    def test_intersection_overlapping(self):
        """Intersection of overlapping squares."""
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(5, 5), (15, 5), (15, 15), (5, 15)])

        result = intersection(p1, p2)
        assert len(result) == 1
        assert result[0].area == 25.0  # 5x5 overlap

    def test_intersection_no_overlap(self):
        """No intersection returns empty list."""
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(20, 0), (30, 0), (30, 10), (20, 10)])

        result = intersection(p1, p2)
        assert len(result) == 0

    def test_difference_hole(self):
        """Cut a hole in a rectangle."""
        outer = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        hole = Polygon.from_tuples([(40, 40), (60, 40), (60, 60), (40, 60)])

        result = difference(outer, hole)
        assert len(result) == 1
        assert result[0].area == 10000 - 400  # 9600

    def test_subtract_all_multiple_holes(self):
        """Subtract multiple obstacles from site."""
        site = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        obstacles = [
            Polygon.from_tuples(
                [(10, 10), (20, 10), (20, 20), (10, 20)]),  # 100 sf
            Polygon.from_tuples(
                [(80, 80), (90, 80), (90, 90), (80, 90)])   # 100 sf
        ]

        result = subtract_all(site, obstacles)
        assert result[0].area == 9800.0

    def test_subtract_all_no_holes(self):
        """Subtracting empty list returns original."""
        site = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        result = subtract_all(site, [])
        assert len(result) == 1
        assert result[0].area == 10000.0


class TestBufferOperations:
    """Tests for buffer/inset/offset operations."""

    def test_buffer_expand(self):
        """Positive buffer expands polygon."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        result = buffer(rect, 10)

        assert len(result) == 1
        # Area should be larger (corners are rounded)
        assert result[0].area > 5000

    def test_buffer_shrink(self):
        """Negative buffer shrinks polygon."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        result = buffer(rect, -10)

        assert len(result) == 1
        # 80 x 30 = 2400, but corners are rounded so slightly less
        assert 2300 < result[0].area < 2500

    def test_inset(self):
        """Inset convenience function."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        result = inset(rect, 10)

        assert len(result) == 1
        min_x, min_y, max_x, max_y = result[0].bounds
        # Should be roughly 80 x 30
        assert abs((max_x - min_x) - 80) < 1
        assert abs((max_y - min_y) - 30) < 1

    def test_inset_square_corners(self):
        """Inset with square corners."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        result = inset_square(rect, 10)

        assert len(result) == 1
        # Should be exactly 80 x 30 with square corners
        assert abs(result[0].area - 2400) < 1

    def test_inset_too_large(self):
        """Inset larger than polygon returns empty."""
        rect = Polygon.from_tuples([(0, 0), (20, 0), (20, 20), (0, 20)])
        result = inset(rect, 15)  # Would create negative dimensions
        assert len(result) == 0

    def test_offset(self):
        """Offset convenience function."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        result = offset(rect, 10)

        assert len(result) == 1
        assert result[0].area > 5000


class TestLineClipping:
    """Tests for line clipping operations."""

    def test_clip_line_through_polygon(self):
        """Clip line that passes through polygon."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        line = Line(Point(-10, 25), Point(110, 25))

        result = clip_line_to_polygon(line, rect)
        assert len(result) == 1
        assert abs(result[0].start.x) < 0.01
        assert abs(result[0].end.x - 100) < 0.01

    def test_clip_line_partial(self):
        """Line starting inside polygon."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        line = Line(Point(50, 25), Point(150, 25))

        result = clip_line_to_polygon(line, rect)
        assert len(result) == 1
        assert abs(result[0].start.x - 50) < 0.01
        assert abs(result[0].end.x - 100) < 0.01

    def test_clip_line_outside(self):
        """Line completely outside polygon."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        line = Line(Point(-50, 100), Point(150, 100))

        result = clip_line_to_polygon(line, rect)
        assert len(result) == 0

    def test_clip_multiple_lines(self):
        """Clip multiple lines."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        lines = [
            Line(Point(-10, 10), Point(110, 10)),
            Line(Point(-10, 25), Point(110, 25)),
            Line(Point(-10, 40), Point(110, 40)),
        ]

        result = clip_lines_to_polygon(lines, rect)
        assert len(result) == 3

    def test_extend_line_to_polygon(self):
        """Extend short line to polygon boundary."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        line = Line(Point(40, 25), Point(60, 25))  # Short line in middle

        result = extend_line_to_polygon(line, rect)
        assert result is not None
        assert abs(result.start.x) < 0.01
        assert abs(result.end.x - 100) < 0.01


class TestParallelLines:
    """Tests for parallel line generation."""

    def test_horizontal_lines(self):
        """Generate horizontal lines."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 60), (0, 60)])
        lines = generate_parallel_lines(rect, spacing=20, angle=0)

        # Should have lines at y=20, y=40 (edges are at 0 and 60)
        # With center-based generation, we get lines at center offsets
        assert len(lines) >= 2

        # All lines should span full width
        for line in lines:
            assert abs(line.start.x) < 1 or abs(line.start.x - 100) < 1

    def test_vertical_lines(self):
        """Generate vertical lines."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 60), (0, 60)])
        lines = generate_parallel_lines(rect, spacing=25, angle=90)

        # Should have vertical lines
        assert len(lines) >= 3

    def test_angled_lines(self):
        """Generate 45-degree lines."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        lines = generate_parallel_lines(rect, spacing=20, angle=45)

        assert len(lines) > 0
        # Check angle is approximately 45 degrees
        for line in lines:
            angle = line.angle
            assert abs(angle - 45) < 1 or abs(angle - 225) < 1

    def test_grid_lines(self):
        """Generate grid of lines."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        h_lines, v_lines = generate_grid_lines(
            rect, x_spacing=25, y_spacing=20)

        assert len(h_lines) >= 1
        assert len(v_lines) >= 3

    def test_l_shaped_clipping(self):
        """Lines should clip properly to L-shaped polygon."""
        l_shape = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 30),
            (50, 30), (50, 60), (0, 60)
        ])

        lines = generate_parallel_lines(l_shape, spacing=15, angle=0)

        # Some lines should be shorter (in the notched area)
        lengths = [line.length for line in lines]
        assert min(lengths) < max(lengths)


class TestSpatialRelationships:
    """Tests for spatial relationship functions."""

    def test_polygons_intersect_true(self):
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(5, 5), (15, 5), (15, 15), (5, 15)])
        assert polygons_intersect(p1, p2) is True

    def test_polygons_intersect_false(self):
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(20, 0), (30, 0), (30, 10), (20, 10)])
        assert polygons_intersect(p1, p2) is False

    def test_polygon_contains(self):
        outer = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        inner = Polygon.from_tuples([(20, 20), (80, 20), (80, 80), (20, 80)])

        assert polygon_contains(outer, inner) is True
        assert polygon_contains(inner, outer) is False

    def test_point_in_polygon(self):
        poly = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])

        assert point_in_polygon(Point(50, 50), poly) is True
        assert point_in_polygon(Point(150, 50), poly) is False

    def test_line_intersects_polygon(self):
        poly = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])

        line_through = Line(Point(-10, 50), Point(110, 50))
        line_outside = Line(Point(150, 0), Point(150, 100))

        assert line_intersects_polygon(line_through, poly) is True
        assert line_intersects_polygon(line_outside, poly) is False


class TestAreaCalculations:
    """Tests for area calculation functions."""

    def test_total_area(self):
        polygons = [
            Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)]),  # 100
            Polygon.from_tuples([(20, 0), (30, 0), (30, 20), (20, 20)])  # 200
        ]
        assert total_area(polygons) == 300.0

    def test_intersection_area(self):
        p1 = Polygon.from_tuples([(0, 0), (10, 0), (10, 10), (0, 10)])
        p2 = Polygon.from_tuples([(5, 5), (15, 5), (15, 15), (5, 15)])

        assert intersection_area(p1, p2) == 25.0

    def test_coverage_ratio(self):
        site = Polygon.from_tuples([(0, 0), (100, 0), (100, 100), (0, 100)])
        buildings = [
            Polygon.from_tuples(
                [(10, 10), (50, 10), (50, 50), (10, 50)])  # 1600 sf
        ]

        ratio = coverage_ratio(buildings, site)
        assert abs(ratio - 0.16) < 0.001


class TestUtilities:
    """Tests for utility functions."""

    def test_convex_hull(self):
        """Convex hull of L-shape should be larger."""
        l_shape = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 30),
            (50, 30), (50, 60), (0, 60)
        ])

        hull = convex_hull(l_shape)
        assert hull.area > l_shape.area

    def test_simplify(self):
        """Simplify should reduce vertex count."""
        # Create polygon with many points
        poly = Polygon.from_tuples([
            (0, 0), (10, 0.1), (20, 0), (30, 0.1), (40, 0),
            (50, 0.1), (60, 0), (70, 0.1), (80, 0), (90, 0.1), (100, 0),
            (100, 50), (0, 50)
        ])

        simplified = simplify(poly, tolerance=1)
        assert len(simplified.vertices) < len(poly.vertices)

    def test_split_polygon(self):
        """Split a rectangle in half."""
        rect = Polygon.from_tuples([(0, 0), (100, 0), (100, 50), (0, 50)])
        line = Line(Point(50, -10), Point(50, 60))

        result = split_polygon_with_line(rect, line)
        assert len(result) == 2
        # Each half should be about 2500 sf
        for part in result:
            assert 2400 < part.area < 2600


class TestIntegration:
    """Integration tests combining operations."""

    def test_parking_lot_preparation(self):
        """
        Simulate preparing a site for parking:
        1. Start with site boundary
        2. Apply setback (inset)
        3. Subtract obstacles
        4. Generate drive aisle lines
        """
        # 1. Site boundary: 200' x 150'
        site = Polygon.from_tuples([
            (0, 0), (200, 0), (200, 150), (0, 150)
        ])
        assert site.area == 30000.0

        # 2. Apply 10' setback
        setback_area = inset_square(site, 10)
        assert len(setback_area) == 1
        # 180 x 130 = 23400
        assert abs(setback_area[0].area - 23400) < 10

        # 3. Subtract obstacles (building, ramp)
        obstacles = [
            # Building: 60x40
            Polygon.from_tuples([(20, 20), (80, 20), (80, 60), (20, 60)]),
            Polygon.from_tuples(
                [(150, 100), (170, 100), (170, 130), (150, 130)])  # Ramp: 20x30
        ]
        usable = subtract_all(setback_area[0], obstacles)
        expected_area = 23400 - (60*40) - (20*30)  # 23400 - 2400 - 600 = 20400
        assert abs(total_area(usable) - expected_area) < 10

        # 4. Generate drive aisle lines at 60' spacing (typical double-loaded bay)
        if usable:
            lines = generate_parallel_lines(usable[0], spacing=60, angle=0)
            assert len(lines) >= 1

    def test_site_with_l_shape(self):
        """Test operations on L-shaped site."""
        l_site = Polygon.from_tuples([
            (0, 0), (150, 0), (150, 60),
            (80, 60), (80, 120), (0, 120)
        ])

        # Apply setback
        setback = inset_square(l_site, 5)
        assert len(setback) >= 1

        # Generate parking lines
        lines = generate_parallel_lines(setback[0], spacing=30, angle=0)
        assert len(lines) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
