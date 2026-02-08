"""
Unit Tests for Structured Parking Stall Placement
==================================================

Tests for Phase 4: Stall placement in structured parking.
"""

import unittest
from parking_engine.geometry import Polygon, Point, rectangles_overlap
from parking_engine.rules import ParkingRules, AisleDirection
from parking_engine.structured import (
    StructuredParkingLayout,
    ParkingLevel,
    Ramp,
    VerticalCore,
    RampType,
    CoreType,
    generate_structured_parking_skeleton,
    generate_floor_plate,
)
from parking_engine.structured_layout import (
    StructuralBayConfig,
    LevelLayout,
    StructuredLayoutWithStalls,
    StructuredLayoutMetrics,
    compute_net_parkable_geometry,
    validate_stalls_avoid_exclusions,
    generate_level_layout,
    generate_structured_parking_layout,
    compute_structured_layout_metrics,
)
from parking_engine.layout import Stall, StallType


class TestStructuralBayConfig(unittest.TestCase):
    """Tests for structural bay configuration."""

    def test_default_config(self):
        """Default configuration should have sensible values."""
        config = StructuralBayConfig()

        self.assertEqual(config.typical_bay_depth, 60.0)
        self.assertEqual(config.single_bay_depth, 42.0)
        self.assertEqual(config.structural_bay_width, 30.0)

    def test_config_to_dict(self):
        """Config should serialize to dictionary."""
        config = StructuralBayConfig()
        data = config.to_dict()

        self.assertIn("typical_bay_depth_ft", data)
        self.assertIn("structural_bay_width_ft", data)


class TestNetParkableGeometry(unittest.TestCase):
    """Tests for exclusion zone handling."""

    def test_no_exclusions(self):
        """Without exclusions, net equals gross."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        level = generate_floor_plate(
            footprint=footprint,
            level_index=0,
            elevation=0.0,
        )

        net, exclusions = compute_net_parkable_geometry(level)

        self.assertEqual(len(exclusions), 0)
        self.assertAlmostEqual(net.area, footprint.area, places=1)

    def test_with_corner_ramp(self):
        """Corner ramp should reduce parkable area."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        ramp = Polygon.from_bounds(240, 160, 300, 180)  # Northeast corner

        level = generate_floor_plate(
            footprint=footprint,
            level_index=0,
            elevation=0.0,
            ramp_reservations=[ramp],
        )

        net, exclusions = compute_net_parkable_geometry(level)

        self.assertEqual(len(exclusions), 1)
        # Net area should be reduced
        self.assertLess(net.area, footprint.area)

    def test_with_center_core(self):
        """Center core should be excluded."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        core = Polygon.from_bounds(140, 77.5, 160, 102.5)  # Center

        level = generate_floor_plate(
            footprint=footprint,
            level_index=0,
            elevation=0.0,
            core_reservations=[core],
        )

        net, exclusions = compute_net_parkable_geometry(level)

        self.assertEqual(len(exclusions), 1)


class TestStallExclusionValidation(unittest.TestCase):
    """Tests for stall-exclusion overlap detection."""

    def test_stalls_no_overlap(self):
        """Stalls not overlapping exclusions should all be valid."""
        exclusion = Polygon.from_bounds(100, 100, 150, 150)

        stalls = [
            Stall(
                id="s1",
                geometry=Polygon.from_bounds(10, 10, 20, 28),
                stall_type=StallType.STANDARD,
                bay_id="bay_0",
                row="north",
            ),
            Stall(
                id="s2",
                geometry=Polygon.from_bounds(30, 10, 40, 28),
                stall_type=StallType.STANDARD,
                bay_id="bay_0",
                row="north",
            ),
        ]

        valid, invalid, warnings = validate_stalls_avoid_exclusions(
            stalls, [exclusion]
        )

        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 0)

    def test_stalls_with_overlap(self):
        """Stalls overlapping exclusions should be marked invalid."""
        exclusion = Polygon.from_bounds(25, 5, 50, 35)

        stalls = [
            Stall(
                id="s1",
                geometry=Polygon.from_bounds(10, 10, 20, 28),  # Clear
                stall_type=StallType.STANDARD,
                bay_id="bay_0",
                row="north",
            ),
            Stall(
                id="s2",
                geometry=Polygon.from_bounds(30, 10, 40, 28),  # Overlaps
                stall_type=StallType.STANDARD,
                bay_id="bay_0",
                row="north",
            ),
        ]

        valid, invalid, warnings = validate_stalls_avoid_exclusions(
            stalls, [exclusion]
        )

        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0].id, "s2")


class TestLevelLayout(unittest.TestCase):
    """Tests for single-level stall placement."""

    def test_generate_level_layout_basic(self):
        """Should generate stalls on a basic floor plate."""
        footprint = Polygon.from_bounds(0, 0, 200, 150)
        level = generate_floor_plate(
            footprint=footprint,
            level_index=0,
            elevation=0.0,
        )
        rules = ParkingRules()

        layout = generate_level_layout(
            level=level,
            rules=rules,
            aisle_direction=AisleDirection.TWO_WAY,
        )

        self.assertTrue(layout.placement_successful)
        self.assertGreater(layout.stall_count, 0)
        self.assertEqual(layout.level_index, 0)

    def test_generate_level_layout_with_exclusions(self):
        """Should avoid exclusion zones when placing stalls."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        ramp = Polygon.from_bounds(240, 160, 300, 180)
        core = Polygon.from_bounds(140, 77.5, 160, 102.5)

        level = generate_floor_plate(
            footprint=footprint,
            level_index=1,
            elevation=10.5,
            ramp_reservations=[ramp],
            core_reservations=[core],
        )
        rules = ParkingRules()

        layout = generate_level_layout(
            level=level,
            rules=rules,
            aisle_direction=AisleDirection.TWO_WAY,
        )

        # Should still place stalls
        self.assertTrue(layout.placement_successful)
        self.assertGreater(layout.stall_count, 0)

        # No stalls should overlap exclusions
        for stall in layout.all_stalls:
            self.assertFalse(rectangles_overlap(stall.geometry, ramp))
            self.assertFalse(rectangles_overlap(stall.geometry, core))

    def test_level_layout_too_small(self):
        """Very small floor plate should fail gracefully."""
        footprint = Polygon.from_bounds(0, 0, 30, 30)  # 900 SF
        level = generate_floor_plate(
            footprint=footprint,
            level_index=0,
            elevation=0.0,
        )
        rules = ParkingRules()

        layout = generate_level_layout(
            level=level,
            rules=rules,
            aisle_direction=AisleDirection.TWO_WAY,
        )

        self.assertFalse(layout.placement_successful)
        self.assertEqual(layout.stall_count, 0)
        self.assertGreater(len(layout.placement_notes), 0)


class TestStructuredLayoutWithStalls(unittest.TestCase):
    """Tests for complete structured parking with stalls."""

    def test_generate_structured_layout_basic(self):
        """Should generate stalls on all levels."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=4,
            floor_to_floor_height=10.5,
        )

        layout = generate_structured_parking_layout(
            structured_layout=skeleton,
            aisle_direction=AisleDirection.TWO_WAY,
        )

        self.assertIsInstance(layout, StructuredLayoutWithStalls)
        self.assertEqual(layout.level_count, 4)
        self.assertGreater(layout.total_stalls, 0)

        # Each level should have stalls
        for stall_count in layout.stalls_per_level:
            self.assertGreater(stall_count, 0)

    def test_stalls_scale_with_levels(self):
        """Total stalls should scale approximately linearly with levels."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)

        skeleton_2 = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=2,
        )
        layout_2 = generate_structured_parking_layout(skeleton_2)

        skeleton_4 = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=4,
        )
        layout_4 = generate_structured_parking_layout(skeleton_4)

        # 4-level should have approximately 2x the stalls of 2-level
        ratio = layout_4.total_stalls / layout_2.total_stalls
        self.assertGreater(ratio, 1.5)  # At least 1.5x
        self.assertLess(ratio, 2.5)     # At most 2.5x

    def test_no_stalls_overlap_ramps(self):
        """No stalls should overlap ramp areas."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=3,
            ramp_config={"location": "northeast", "width": 20, "length": 70},
        )

        layout = generate_structured_parking_layout(skeleton)

        ramp_footprint = skeleton.ramps[0].footprint

        for level_layout in layout.level_layouts:
            for stall in level_layout.all_stalls:
                self.assertFalse(
                    rectangles_overlap(stall.geometry, ramp_footprint),
                    f"Stall {stall.id} overlaps ramp"
                )

    def test_no_stalls_overlap_cores(self):
        """No stalls should overlap core areas."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=3,
            core_config={"location": "center", "width": 25, "depth": 30},
        )

        layout = generate_structured_parking_layout(skeleton)

        core_footprint = skeleton.cores[0].footprint

        for level_layout in layout.level_layouts:
            for stall in level_layout.all_stalls:
                self.assertFalse(
                    rectangles_overlap(stall.geometry, core_footprint),
                    f"Stall {stall.id} overlaps core"
                )

    def test_layout_to_dict(self):
        """Layout should serialize to dictionary."""
        footprint = Polygon.from_bounds(0, 0, 200, 150)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=2,
        )

        layout = generate_structured_parking_layout(skeleton)
        data = layout.to_dict()

        self.assertIn("skeleton", data)
        self.assertIn("total_stalls", data)
        self.assertIn("stalls_per_level", data)
        self.assertIn("levels", data)

    def test_layout_summary(self):
        """Layout should generate human-readable summary."""
        footprint = Polygon.from_bounds(0, 0, 200, 150)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=2,
        )

        layout = generate_structured_parking_layout(skeleton)
        summary = layout.summary()

        self.assertIn("Structured Parking Layout", summary)
        self.assertIn("Total Stalls", summary)


class TestStructuredLayoutMetrics(unittest.TestCase):
    """Tests for structured layout metrics computation."""

    def test_compute_metrics_basic(self):
        """Should compute comprehensive metrics."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=4,
        )

        layout = generate_structured_parking_layout(skeleton)
        metrics = compute_structured_layout_metrics(layout)

        self.assertIsInstance(metrics, StructuredLayoutMetrics)
        self.assertEqual(metrics.level_count, 4)
        self.assertGreater(metrics.total_stalls, 0)
        self.assertGreater(metrics.overall_efficiency_sf_per_stall, 0)

    def test_metrics_stalls_per_level(self):
        """Metrics should include per-level stall counts."""
        footprint = Polygon.from_bounds(0, 0, 250, 150)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=3,
        )

        layout = generate_structured_parking_layout(skeleton)
        metrics = compute_structured_layout_metrics(layout)

        self.assertEqual(len(metrics.stalls_per_level), 3)
        self.assertEqual(sum(metrics.stalls_per_level), metrics.total_stalls)

    def test_metrics_efficiency(self):
        """Efficiency should be within expected range."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=4,
        )

        layout = generate_structured_parking_layout(skeleton)
        metrics = compute_structured_layout_metrics(layout)

        # Typical structured parking: 280-375 SF/stall
        self.assertGreater(metrics.overall_efficiency_sf_per_stall, 250)
        self.assertLess(metrics.overall_efficiency_sf_per_stall, 400)

    def test_metrics_to_dict(self):
        """Metrics should serialize to dictionary."""
        footprint = Polygon.from_bounds(0, 0, 200, 150)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=2,
        )

        layout = generate_structured_parking_layout(skeleton)
        metrics = compute_structured_layout_metrics(layout)
        data = metrics.to_dict()

        self.assertIn("structure", data)
        self.assertIn("stalls", data)
        self.assertIn("areas", data)
        self.assertIn("efficiency", data)
        self.assertIn("losses", data)


class TestBayAlignment(unittest.TestCase):
    """Tests for bay alignment across levels."""

    def test_consistent_bay_count(self):
        """Each level should have consistent bay count."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=4,
        )

        layout = generate_structured_parking_layout(skeleton)

        bay_counts = [
            ll.bay_count for ll in layout.level_layouts if ll.bay_count > 0]

        # All levels should have same number of bays (within tolerance)
        if len(bay_counts) > 1:
            min_bays = min(bay_counts)
            max_bays = max(bay_counts)
            # Allow 1 bay difference due to floor variations
            self.assertLessEqual(max_bays - min_bays, 1)


class TestOneWayAisles(unittest.TestCase):
    """Tests for one-way aisle configuration."""

    def test_one_way_layout(self):
        """Should support one-way aisle configuration."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=2,
        )

        layout = generate_structured_parking_layout(
            skeleton,
            aisle_direction=AisleDirection.ONE_WAY,
        )

        self.assertIsInstance(layout, StructuredLayoutWithStalls)
        self.assertGreater(layout.total_stalls, 0)
        self.assertEqual(layout.aisle_direction, AisleDirection.ONE_WAY)


class TestDeterminism(unittest.TestCase):
    """Tests for deterministic output."""

    def test_layout_is_deterministic(self):
        """Same inputs should produce same outputs."""
        footprint = Polygon.from_bounds(0, 0, 300, 180)

        skeleton1 = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=3,
        )
        layout1 = generate_structured_parking_layout(skeleton1)

        skeleton2 = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=3,
        )
        layout2 = generate_structured_parking_layout(skeleton2)

        self.assertEqual(layout1.total_stalls, layout2.total_stalls)
        self.assertEqual(layout1.stalls_per_level, layout2.stalls_per_level)


class TestSurfaceParkingUnchanged(unittest.TestCase):
    """Tests to ensure surface parking behavior is unchanged."""

    def test_surface_layout_still_works(self):
        """Surface parking should work independently."""
        from parking_engine.layout import generate_surface_layout

        site = Polygon.from_bounds(0, 0, 200, 150)
        layout = generate_surface_layout(
            site_boundary=site,
            aisle_direction=AisleDirection.TWO_WAY,
        )

        self.assertGreater(layout.total_stalls, 0)

    def test_irregular_layout_still_works(self):
        """Irregular surface parking should work independently."""
        from parking_engine.layout import generate_surface_layout_irregular

        l_shape = Polygon([
            Point(0, 100),
            Point(0, 200),
            Point(200, 200),
            Point(200, 0),
            Point(100, 0),
            Point(100, 100),
        ])

        result = generate_surface_layout_irregular(
            site_boundary=l_shape,
            aisle_direction=AisleDirection.TWO_WAY,
        )

        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
