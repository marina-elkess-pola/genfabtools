"""
Unit tests for GenFabTools Parking Engine v2 — 60° Geometry Module

Tests validate:
- Fixed dimensions match spec
- Stall creation and rotation
- Row stall placement and counting
- Aisle geometry
- Double-loaded row construction
- Row spacing calculations
"""

import math
import pytest
from sitefit.core.geometry import Point, Line, Polygon
from sitefit.parking_engine.v2.geometry_60 import (
    # Constants
    STALL_WIDTH_60,
    STALL_DEPTH_60,
    AISLE_WIDTH_60,
    ROW_SPACING_60,
    MODULE_DEPTH_60,
    ANGLE_60_DEGREES,
    ANGLE_60_RADIANS,
    STALL_FOOTPRINT_WIDTH_60,
    STALL_FOOTPRINT_DEPTH_60,
    # Classes
    Stall60,
    StallRow60,
    Aisle60,
    DoubleLoadedRow60,
    # Functions
    create_stall_60,
    create_stall_row_60,
    create_aisle_60,
    create_double_loaded_row_60,
    calculate_stalls_per_row,
    calculate_rows_in_depth,
    calculate_row_spacing_60,
    get_geometry_60_constants,
)


# =============================================================================
# CONSTANTS TESTS — Verify spec dimensions
# =============================================================================

class TestConstants:
    """Test that all constants match the MVP specification."""

    def test_stall_width(self):
        """Stall width must be 10.4 ft per spec."""
        assert STALL_WIDTH_60 == 10.4

    def test_stall_depth(self):
        """Stall depth must be 21.0 ft per spec."""
        assert STALL_DEPTH_60 == 21.0

    def test_aisle_width(self):
        """Aisle width must be 14.0 ft per spec (one-way only)."""
        assert AISLE_WIDTH_60 == 14.0

    def test_row_spacing(self):
        """Row-to-row spacing must equal MODULE_DEPTH_60 (~60.77 ft)."""
        assert ROW_SPACING_60 == MODULE_DEPTH_60

    def test_angle_degrees(self):
        """Angle must be 60 degrees."""
        assert ANGLE_60_DEGREES == 60.0

    def test_angle_radians(self):
        """Angle in radians must match 60 degrees."""
        assert abs(ANGLE_60_RADIANS - math.radians(60)) < 1e-10

    def test_footprint_width_positive(self):
        """Footprint width must be positive and reasonable."""
        assert STALL_FOOTPRINT_WIDTH_60 > 0
        # Should be larger than stall width due to angle projection
        assert STALL_FOOTPRINT_WIDTH_60 > STALL_WIDTH_60

    def test_footprint_depth_positive(self):
        """Footprint depth must be positive and reasonable."""
        assert STALL_FOOTPRINT_DEPTH_60 > 0
        # Should be less than perpendicular depth due to angle
        assert STALL_FOOTPRINT_DEPTH_60 < STALL_DEPTH_60 + STALL_WIDTH_60


class TestGetConstants:
    """Test the constants dictionary function."""

    def test_get_geometry_60_constants(self):
        """Constants dict must contain all required keys."""
        constants = get_geometry_60_constants()
        assert constants["stall_width"] == STALL_WIDTH_60
        assert constants["stall_depth"] == STALL_DEPTH_60
        assert constants["aisle_width"] == AISLE_WIDTH_60
        assert constants["row_spacing"] == ROW_SPACING_60
        assert constants["angle_degrees"] == ANGLE_60_DEGREES
        assert constants["footprint_width"] == STALL_FOOTPRINT_WIDTH_60
        assert constants["footprint_depth"] == STALL_FOOTPRINT_DEPTH_60


# =============================================================================
# STALL TESTS
# =============================================================================

class TestStall60Creation:
    """Test individual stall creation and properties."""

    def test_create_stall_at_origin(self):
        """Stall created at origin should have correct anchor."""
        stall = create_stall_60(Point(0, 0), direction=1)
        assert stall.anchor == Point(0, 0)

    def test_create_stall_direction_positive(self):
        """Stall with direction=1 should have +60° angle."""
        stall = create_stall_60(Point(0, 0), direction=1)
        assert stall.angle == 60.0

    def test_create_stall_direction_negative(self):
        """Stall with direction=-1 should have -60° angle."""
        stall = create_stall_60(Point(0, 0), direction=-1)
        assert stall.angle == -60.0

    def test_invalid_direction_rejected(self):
        """Direction must be 1 or -1."""
        with pytest.raises(ValueError):
            create_stall_60(Point(0, 0), direction=0)
        with pytest.raises(ValueError):
            create_stall_60(Point(0, 0), direction=2)

    def test_stall_has_polygon(self):
        """Stall must have a valid polygon."""
        stall = create_stall_60(Point(0, 0), direction=1)
        assert stall.polygon is not None
        assert isinstance(stall.polygon, Polygon)

    def test_stall_polygon_has_four_vertices(self):
        """Stall polygon must have exactly 4 vertices."""
        stall = create_stall_60(Point(0, 0), direction=1)
        assert len(stall.polygon.vertices) == 4

    def test_stall_area_approximately_correct(self):
        """Stall area should equal width × depth."""
        stall = create_stall_60(Point(0, 0), direction=1)
        expected_area = STALL_WIDTH_60 * STALL_DEPTH_60
        assert abs(stall.area - expected_area) < 0.01

    def test_stall_center_method(self):
        """Stall center should be approximately at expected location."""
        stall = create_stall_60(Point(0, 0), direction=1)
        center = stall.center
        assert center.x != 0 or center.y != 0  # Not at origin

    def test_stall_to_dict(self):
        """Stall should serialize to dict correctly."""
        stall = create_stall_60(Point(10, 20), direction=1)
        d = stall.to_dict()
        assert d["anchor"]["x"] == 10
        assert d["anchor"]["y"] == 20
        assert d["angle"] == 60.0
        assert "polygon" in d


class TestStallRotation:
    """Test stall rotation geometry."""

    def test_positive_rotation_moves_corners_counterclockwise(self):
        """Positive 60° rotation should move corners counter-clockwise."""
        stall = create_stall_60(Point(0, 0), direction=1)
        # Check that the second corner (originally at (width, 0)) is rotated
        v1 = stall.polygon.vertices[1]
        # After 60° rotation, x component should be reduced
        assert v1.x < STALL_WIDTH_60
        assert v1.y > 0

    def test_negative_rotation_moves_corners_clockwise(self):
        """Negative 60° rotation should move corners clockwise."""
        stall = create_stall_60(Point(0, 0), direction=-1)
        v1 = stall.polygon.vertices[1]
        assert v1.x < STALL_WIDTH_60
        assert v1.y < 0

    def test_rotated_stall_anchor_unchanged(self):
        """Rotation anchor point should remain at specified position."""
        anchor = Point(50, 100)
        stall = create_stall_60(anchor, direction=1)
        # First vertex should be at anchor
        assert abs(stall.polygon.vertices[0].x - anchor.x) < 0.001
        assert abs(stall.polygon.vertices[0].y - anchor.y) < 0.001


# =============================================================================
# ROW TESTS
# =============================================================================

class TestCalculateStallsPerRow:
    """Test deterministic stall count calculation."""

    def test_zero_length_row(self):
        """Zero length should fit zero stalls."""
        assert calculate_stalls_per_row(0) == 0

    def test_less_than_one_stall(self):
        """Length less than one stall footprint should fit zero."""
        assert calculate_stalls_per_row(STALL_FOOTPRINT_WIDTH_60 - 0.1) == 0

    def test_exactly_one_stall(self):
        """Length exactly one stall footprint should fit one."""
        assert calculate_stalls_per_row(STALL_FOOTPRINT_WIDTH_60) == 1

    def test_two_stalls(self):
        """Length for two stalls should fit exactly two."""
        assert calculate_stalls_per_row(STALL_FOOTPRINT_WIDTH_60 * 2) == 2

    def test_partial_stall_not_counted(self):
        """Partial stall space should be ignored (deterministic)."""
        length = STALL_FOOTPRINT_WIDTH_60 * 2.9
        assert calculate_stalls_per_row(length) == 2

    def test_100ft_row(self):
        """100ft row should fit expected number of stalls."""
        count = calculate_stalls_per_row(100)
        assert count > 0
        assert count == int(100 // STALL_FOOTPRINT_WIDTH_60)


class TestStallRow60:
    """Test row creation and properties."""

    def test_create_empty_row(self):
        """Short aisle should create empty row."""
        edge = Line(Point(0, 0), Point(5, 0))  # 5 ft, too short
        row = create_stall_row_60(edge, direction=1)
        assert row.count == 0
        assert row.stalls == []

    def test_create_row_with_stalls(self):
        """100ft aisle should create row with stalls."""
        edge = Line(Point(0, 0), Point(100, 0))
        row = create_stall_row_60(edge, direction=1)
        expected_count = calculate_stalls_per_row(100)
        assert row.count == expected_count
        assert len(row.stalls) == expected_count

    def test_invalid_direction_rejected(self):
        """Invalid direction should raise error."""
        edge = Line(Point(0, 0), Point(100, 0))
        with pytest.raises(ValueError):
            create_stall_row_60(edge, direction=0)

    def test_row_preserves_aisle_edge(self):
        """Row should preserve the aisle edge."""
        edge = Line(Point(10, 20), Point(110, 20))
        row = create_stall_row_60(edge, direction=1)
        assert row.aisle_edge.start == edge.start
        assert row.aisle_edge.end == edge.end

    def test_row_length(self):
        """Row length should match aisle edge length."""
        edge = Line(Point(0, 0), Point(100, 0))
        row = create_stall_row_60(edge, direction=1)
        assert row.row_length == 100.0

    def test_stalls_placed_along_edge(self):
        """Stalls should be placed along the aisle edge."""
        edge = Line(Point(0, 0), Point(100, 0))
        row = create_stall_row_60(edge, direction=1)

        for i, stall in enumerate(row.stalls):
            expected_x = i * STALL_FOOTPRINT_WIDTH_60
            assert abs(stall.anchor.x - expected_x) < 0.001
            assert abs(stall.anchor.y - 0) < 0.001

    def test_row_to_dict(self):
        """Row should serialize to dict correctly."""
        edge = Line(Point(0, 0), Point(50, 0))
        row = create_stall_row_60(edge, direction=1)
        d = row.to_dict()
        assert "stall_count" in d
        assert "direction" in d
        assert "aisle_edge" in d
        assert "stalls" in d


# =============================================================================
# AISLE TESTS
# =============================================================================

class TestAisle60:
    """Test aisle geometry."""

    def test_create_aisle(self):
        """Aisle should be created with correct parameters."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        assert aisle.width == AISLE_WIDTH_60
        assert aisle.length == 100.0

    def test_aisle_has_polygon(self):
        """Aisle should have a valid polygon."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        assert aisle.polygon is not None
        assert isinstance(aisle.polygon, Polygon)

    def test_aisle_polygon_has_four_vertices(self):
        """Aisle polygon should be a rectangle (4 vertices)."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        assert len(aisle.polygon.vertices) == 4

    def test_aisle_area(self):
        """Aisle area should be length × width."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        expected_area = 100 * AISLE_WIDTH_60
        assert abs(aisle.polygon.area - expected_area) < 0.01

    def test_aisle_left_edge(self):
        """Left edge should be offset from centerline."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        left = aisle.left_edge
        # For horizontal aisle, left edge should be above
        assert left.start.y == AISLE_WIDTH_60 / 2
        assert left.end.y == AISLE_WIDTH_60 / 2

    def test_aisle_right_edge(self):
        """Right edge should be offset from centerline."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        right = aisle.right_edge
        # For horizontal aisle, right edge should be below
        assert right.start.y == -AISLE_WIDTH_60 / 2
        assert right.end.y == -AISLE_WIDTH_60 / 2

    def test_aisle_to_dict(self):
        """Aisle should serialize to dict correctly."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        d = aisle.to_dict()
        assert "centerline" in d
        assert "width" in d
        assert "polygon" in d
        assert d["width"] == AISLE_WIDTH_60


# =============================================================================
# DOUBLE-LOADED ROW TESTS
# =============================================================================

class TestDoubleLoadedRow60:
    """Test double-loaded row construction."""

    def test_create_double_loaded_row(self):
        """Double-loaded row should have aisle and two stall rows."""
        row = create_double_loaded_row_60(Point(0, 0), Point(100, 0))
        assert row.aisle is not None
        assert row.left_row is not None
        assert row.right_row is not None

    def test_total_stalls(self):
        """Total stalls should be sum of both rows."""
        row = create_double_loaded_row_60(Point(0, 0), Point(100, 0))
        expected = row.left_row.count + row.right_row.count
        assert row.total_stalls == expected

    def test_both_rows_have_stalls(self):
        """Both rows should have stalls for sufficient length."""
        row = create_double_loaded_row_60(Point(0, 0), Point(100, 0))
        assert row.left_row.count > 0
        assert row.right_row.count > 0

    def test_total_width(self):
        """Total width should include stalls on both sides plus aisle."""
        row = create_double_loaded_row_60(Point(0, 0), Point(100, 0))
        expected = STALL_FOOTPRINT_DEPTH_60 + AISLE_WIDTH_60 + STALL_FOOTPRINT_DEPTH_60
        assert abs(row.total_width - expected) < 0.01

    def test_row_to_dict(self):
        """Double-loaded row should serialize to dict correctly."""
        row = create_double_loaded_row_60(Point(0, 0), Point(100, 0))
        d = row.to_dict()
        assert "aisle" in d
        assert "left_row" in d
        assert "right_row" in d
        assert "total_stalls" in d


# =============================================================================
# ROW SPACING TESTS
# =============================================================================

class TestRowSpacing:
    """Test row spacing calculations."""

    def test_calculate_row_spacing(self):
        """Row spacing function should return MODULE_DEPTH_60."""
        assert calculate_row_spacing_60() == ROW_SPACING_60
        assert calculate_row_spacing_60() == MODULE_DEPTH_60

    def test_rows_in_zero_depth(self):
        """Zero depth should fit zero rows."""
        assert calculate_rows_in_depth(0) == 0

    def test_rows_in_less_than_one_row(self):
        """Depth less than row spacing should fit zero rows."""
        assert calculate_rows_in_depth(ROW_SPACING_60 - 1) == 0

    def test_rows_in_exactly_one_row(self):
        """Depth exactly one row spacing should fit one row."""
        assert calculate_rows_in_depth(ROW_SPACING_60) == 1

    def test_rows_in_two_rows(self):
        """Depth for two rows should fit two."""
        assert calculate_rows_in_depth(ROW_SPACING_60 * 2) == 2

    def test_rows_in_partial_not_counted(self):
        """Partial row depth should be ignored (deterministic)."""
        assert calculate_rows_in_depth(ROW_SPACING_60 * 2.5) == 2

    def test_rows_in_200ft(self):
        """200ft depth should fit expected rows."""
        rows = calculate_rows_in_depth(200)
        assert rows == int(200 // ROW_SPACING_60)


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

class TestDeterminism:
    """Test that all operations are deterministic."""

    def test_stall_creation_deterministic(self):
        """Same inputs should produce identical stalls."""
        stall1 = create_stall_60(Point(10, 20), direction=1)
        stall2 = create_stall_60(Point(10, 20), direction=1)
        assert stall1.anchor == stall2.anchor
        assert stall1.angle == stall2.angle
        # Compare polygon vertices
        for v1, v2 in zip(stall1.polygon.vertices, stall2.polygon.vertices):
            assert abs(v1.x - v2.x) < 1e-10
            assert abs(v1.y - v2.y) < 1e-10

    def test_row_creation_deterministic(self):
        """Same inputs should produce identical rows."""
        edge = Line(Point(0, 0), Point(100, 0))
        row1 = create_stall_row_60(edge, direction=1)
        row2 = create_stall_row_60(edge, direction=1)
        assert row1.count == row2.count
        for s1, s2 in zip(row1.stalls, row2.stalls):
            assert s1.anchor == s2.anchor

    def test_aisle_creation_deterministic(self):
        """Same inputs should produce identical aisles."""
        aisle1 = create_aisle_60(Point(0, 0), Point(100, 0))
        aisle2 = create_aisle_60(Point(0, 0), Point(100, 0))
        assert aisle1.width == aisle2.width
        assert aisle1.length == aisle2.length


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for complete workflow."""

    def test_stalls_fit_beside_aisle(self):
        """Stalls placed on aisle edges should not overlap aisle."""
        aisle = create_aisle_60(Point(0, 0), Point(100, 0))
        left_row = create_stall_row_60(aisle.left_edge, direction=1)
        right_row = create_stall_row_60(aisle.right_edge, direction=-1)

        # All stall anchors should be on aisle edges
        for stall in left_row.stalls:
            assert abs(stall.anchor.y - AISLE_WIDTH_60 / 2) < 0.001

        for stall in right_row.stalls:
            assert abs(stall.anchor.y - (-AISLE_WIDTH_60 / 2)) < 0.001

    def test_double_loaded_matches_spec_dimensions(self):
        """Double-loaded row width should be consistent with geometry."""
        row = create_double_loaded_row_60(Point(0, 0), Point(100, 0))
        # Total width = 2 × stall_footprint_depth + aisle_width
        # This is the actual geometric footprint, not the row spacing
        expected_width = STALL_FOOTPRINT_DEPTH_60 * 2 + AISLE_WIDTH_60
        assert abs(row.total_width - expected_width) < 0.01

    def test_realistic_lot_stall_count(self):
        """A realistic lot should produce reasonable stall counts."""
        # 200ft × 150ft lot
        # With 56ft row spacing, should fit about 2-3 rows
        rows_count = calculate_rows_in_depth(150)
        stalls_per_100ft = calculate_stalls_per_row(100)

        # Quick estimate: 2 rows × 2 sides × stalls per side
        min_expected = rows_count * 2 * stalls_per_100ft // 2
        max_expected = (rows_count + 1) * 2 * stalls_per_100ft

        # Just verify we're in a reasonable range
        assert rows_count >= 2
        assert stalls_per_100ft >= 5
