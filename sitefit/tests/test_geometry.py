"""
Tests for core/geometry.py

Run with: python -m pytest tests/test_geometry.py -v
"""

import math
import pytest
from sitefit.core.geometry import (
    Point, Line, Polygon, Rectangle,
    distance, angle_between, bounding_box
)


class TestPoint:
    """Tests for Point class."""

    def test_creation(self):
        p = Point(10, 20)
        assert p.x == 10.0
        assert p.y == 20.0

    def test_distance_to(self):
        p1 = Point(0, 0)
        p2 = Point(3, 4)
        assert p1.distance_to(p2) == 5.0

    def test_midpoint(self):
        p1 = Point(0, 0)
        p2 = Point(10, 10)
        mid = p1.midpoint_to(p2)
        assert mid.x == 5.0
        assert mid.y == 5.0

    def test_translate(self):
        p = Point(10, 20)
        p2 = p.translate(5, -5)
        assert p2.x == 15.0
        assert p2.y == 15.0
        # Original unchanged (immutable)
        assert p.x == 10.0

    def test_rotate_90_degrees(self):
        p = Point(10, 0)
        p2 = p.rotate(90, Point(0, 0))
        assert abs(p2.x) < 0.0001  # Should be ~0
        assert abs(p2.y - 10) < 0.0001  # Should be 10

    def test_from_dict(self):
        p = Point.from_dict({'x': 5, 'y': 10})
        assert p.x == 5.0
        assert p.y == 10.0

    def test_to_dict(self):
        p = Point(5, 10)
        d = p.to_dict()
        assert d == {'x': 5.0, 'y': 10.0}

    def test_immutable(self):
        p = Point(10, 20)
        with pytest.raises(Exception):
            p.x = 30


class TestLine:
    """Tests for Line class."""

    def test_length_horizontal(self):
        line = Line(Point(0, 0), Point(10, 0))
        assert line.length == 10.0

    def test_length_diagonal(self):
        line = Line(Point(0, 0), Point(3, 4))
        assert line.length == 5.0

    def test_midpoint(self):
        line = Line(Point(0, 0), Point(10, 0))
        assert line.midpoint.x == 5.0
        assert line.midpoint.y == 0.0

    def test_angle_horizontal(self):
        line = Line(Point(0, 0), Point(10, 0))
        assert line.angle == 0.0

    def test_angle_vertical(self):
        line = Line(Point(0, 0), Point(0, 10))
        assert line.angle == 90.0

    def test_angle_diagonal(self):
        line = Line(Point(0, 0), Point(10, 10))
        assert line.angle == 45.0

    def test_direction(self):
        line = Line(Point(0, 0), Point(10, 0))
        dx, dy = line.direction
        assert dx == 1.0
        assert dy == 0.0

    def test_normal(self):
        line = Line(Point(0, 0), Point(10, 0))
        nx, ny = line.normal
        assert nx == 0.0
        assert ny == 1.0

    def test_offset(self):
        line = Line(Point(0, 0), Point(10, 0))
        offset_line = line.offset(5)
        assert offset_line.start.y == 5.0
        assert offset_line.end.y == 5.0

    def test_point_at(self):
        line = Line(Point(0, 0), Point(10, 0))
        p = line.point_at(0.5)
        assert p.x == 5.0
        assert p.y == 0.0

    def test_subdivide(self):
        line = Line(Point(0, 0), Point(10, 0))
        points = line.subdivide(5)
        assert len(points) == 6
        assert points[0].x == 0.0
        assert points[5].x == 10.0

    def test_extend(self):
        line = Line(Point(0, 0), Point(10, 0))
        extended = line.extend(5, 5)
        assert extended.start.x == -5.0
        assert extended.end.x == 15.0


class TestPolygon:
    """Tests for Polygon class."""

    def test_rectangle_area(self):
        # 100 x 50 rectangle = 5000 sq ft
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 50), (0, 50)
        ])
        assert poly.area == 5000.0

    def test_rectangle_perimeter(self):
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 50), (0, 50)
        ])
        assert poly.perimeter == 300.0

    def test_centroid(self):
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 50), (0, 50)
        ])
        c = poly.centroid
        assert c.x == 50.0
        assert c.y == 25.0

    def test_bounds(self):
        poly = Polygon.from_tuples([
            (10, 20), (110, 20), (110, 70), (10, 70)
        ])
        min_x, min_y, max_x, max_y = poly.bounds
        assert min_x == 10.0
        assert min_y == 20.0
        assert max_x == 110.0
        assert max_y == 70.0

    def test_edges(self):
        poly = Polygon.from_tuples([
            (0, 0), (10, 0), (10, 10), (0, 10)
        ])
        edges = poly.edges
        assert len(edges) == 4
        assert edges[0].length == 10.0

    def test_longest_edge(self):
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 50), (0, 50)
        ])
        longest = poly.longest_edge()
        assert longest.length == 100.0

    def test_contains_point(self):
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 50), (0, 50)
        ])
        assert poly.contains_point(Point(50, 25))
        assert not poly.contains_point(Point(150, 25))

    def test_translate(self):
        poly = Polygon.from_tuples([
            (0, 0), (10, 0), (10, 10), (0, 10)
        ])
        moved = poly.translate(5, 5)
        assert moved.vertices[0].x == 5.0
        assert moved.vertices[0].y == 5.0

    def test_from_dicts(self):
        poly = Polygon.from_dicts([
            {'x': 0, 'y': 0},
            {'x': 10, 'y': 0},
            {'x': 10, 'y': 10},
            {'x': 0, 'y': 10}
        ])
        assert poly.area == 100.0

    def test_l_shaped(self):
        # L-shaped polygon
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 30),
            (50, 30), (50, 60), (0, 60)
        ])
        # Area = 100*30 + 50*30 = 3000 + 1500 = 4500
        assert poly.area == 4500.0

    def test_triangle_area(self):
        poly = Polygon.from_tuples([
            (0, 0), (10, 0), (5, 10)
        ])
        # Triangle area = 0.5 * base * height = 0.5 * 10 * 10 = 50
        assert poly.area == 50.0


class TestRectangle:
    """Tests for Rectangle class."""

    def test_area(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        assert rect.area == 5000.0

    def test_perimeter(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        assert rect.perimeter == 300.0

    def test_center(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        assert rect.center.x == 50.0
        assert rect.center.y == 25.0

    def test_corners(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        corners = rect.corners
        assert len(corners) == 4
        assert corners[0] == Point(0, 0)
        assert corners[1] == Point(100, 0)
        assert corners[2] == Point(100, 50)
        assert corners[3] == Point(0, 50)

    def test_contains_point(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        assert rect.contains_point(Point(50, 25))
        assert not rect.contains_point(Point(150, 25))

    def test_inset(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        inset = rect.inset(10)
        assert inset.width == 80.0
        assert inset.height == 30.0
        assert inset.origin.x == 10.0
        assert inset.origin.y == 10.0

    def test_inset_too_large(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        with pytest.raises(ValueError):
            rect.inset(30)  # Would make height negative

    def test_expand(self):
        rect = Rectangle(Point(10, 10), 100, 50)
        expanded = rect.expand(5)
        assert expanded.width == 110.0
        assert expanded.height == 60.0
        assert expanded.origin.x == 5.0
        assert expanded.origin.y == 5.0

    def test_to_polygon(self):
        rect = Rectangle(Point(0, 0), 100, 50)
        poly = rect.to_polygon()
        assert poly.area == 5000.0

    def test_from_bounds(self):
        rect = Rectangle.from_bounds(10, 20, 110, 70)
        assert rect.origin.x == 10.0
        assert rect.origin.y == 20.0
        assert rect.width == 100.0
        assert rect.height == 50.0

    def test_from_center(self):
        rect = Rectangle.from_center(Point(50, 25), 100, 50)
        assert rect.origin.x == 0.0
        assert rect.origin.y == 0.0

    def test_intersects(self):
        rect1 = Rectangle(Point(0, 0), 100, 50)
        rect2 = Rectangle(Point(50, 25), 100, 50)
        rect3 = Rectangle(Point(200, 0), 100, 50)

        assert rect1.intersects(rect2)
        assert not rect1.intersects(rect3)


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_distance(self):
        p1 = Point(0, 0)
        p2 = Point(3, 4)
        assert distance(p1, p2) == 5.0

    def test_angle_between_90(self):
        p1 = Point(0, 0)
        p2 = Point(5, 0)
        p3 = Point(5, 5)
        angle = angle_between(p1, p2, p3)
        assert abs(angle - 90.0) < 0.0001

    def test_bounding_box(self):
        points = [Point(0, 0), Point(10, 5), Point(5, 10)]
        bbox = bounding_box(points)
        assert bbox.min_x == 0.0
        assert bbox.max_x == 10.0
        assert bbox.min_y == 0.0
        assert bbox.max_y == 10.0


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple classes."""

    def test_parking_lot_dimensions(self):
        """
        A typical parking lot: 200' x 150' = 30,000 SF
        After 10' setbacks: 180' x 130' = 23,400 SF usable
        """
        site = Rectangle(Point(0, 0), 200, 150)
        assert site.area == 30000.0

        buildable = site.inset(10)
        assert buildable.width == 180.0
        assert buildable.height == 130.0
        assert buildable.area == 23400.0

    def test_line_grid(self):
        """Generate a grid of parallel lines."""
        rect = Rectangle(Point(0, 0), 100, 60)

        # Horizontal lines every 20 feet
        lines = []
        for y in range(0, 61, 20):
            lines.append(Line(Point(0, y), Point(100, y)))

        assert len(lines) == 4
        assert lines[0].length == 100.0

    def test_polygon_from_complex_shape(self):
        """Test L-shaped building footprint."""
        # L-shape: main wing 100x40, side wing 40x30
        poly = Polygon.from_tuples([
            (0, 0), (100, 0), (100, 40), (40, 40), (40, 70), (0, 70)
        ])
        # Area = 100*40 + 40*30 = 4000 + 1200 = 5200
        assert poly.area == 5200.0

        # Check centroid is within polygon
        assert poly.contains_point(poly.centroid)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
