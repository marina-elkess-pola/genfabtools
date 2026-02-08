"""
Unit Tests for CAD/BIM Constraint Integration
=============================================

Tests for Phase 5: CAD/BIM constraint subsystem.

Test Categories:
    - Models: ConstraintType, ImportedConstraint, ConstraintSet
    - Classifiers: Layer and category classification
    - Validators: Geometry validation
    - Normalizers: Unit conversion and coordinate alignment
    - Integration: Surface and structured layout constraint application
    - Regression: No CAD/BIM input → unchanged results
"""

from parking_engine.structured import generate_structured_parking_skeleton
from parking_engine.layout import generate_surface_layout
from parking_engine.rules import ParkingRules, AisleDirection
from parking_engine.geometry import Polygon, Point
import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConstraintType(unittest.TestCase):
    """Tests for ConstraintType enum."""

    def test_from_string_known_types(self):
        """Test parsing known constraint types."""
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(ConstraintType.from_string(
            "column"), ConstraintType.COLUMN)
        self.assertEqual(ConstraintType.from_string(
            "COLUMN"), ConstraintType.COLUMN)
        self.assertEqual(ConstraintType.from_string(
            "columns"), ConstraintType.COLUMN)
        self.assertEqual(ConstraintType.from_string(
            "structural_column"), ConstraintType.COLUMN)

        self.assertEqual(ConstraintType.from_string(
            "core"), ConstraintType.CORE)
        self.assertEqual(ConstraintType.from_string(
            "stair"), ConstraintType.CORE)
        self.assertEqual(ConstraintType.from_string(
            "elevator"), ConstraintType.CORE)

        self.assertEqual(ConstraintType.from_string(
            "wall"), ConstraintType.WALL)
        self.assertEqual(ConstraintType.from_string(
            "mep"), ConstraintType.MEP_ROOM)
        self.assertEqual(ConstraintType.from_string(
            "shaft"), ConstraintType.SHAFT)
        self.assertEqual(ConstraintType.from_string(
            "void"), ConstraintType.VOID)

    def test_from_string_unknown(self):
        """Test unknown types default to UNKNOWN."""
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(ConstraintType.from_string(
            "random"), ConstraintType.UNKNOWN)
        self.assertEqual(ConstraintType.from_string(""),
                         ConstraintType.UNKNOWN)
        self.assertEqual(ConstraintType.from_string(
            "foobar"), ConstraintType.UNKNOWN)

    def test_to_string(self):
        """Test constraint type to string conversion."""
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(ConstraintType.COLUMN.to_string(), "column")
        self.assertEqual(ConstraintType.UNKNOWN.to_string(), "unknown")


class TestImportedConstraint(unittest.TestCase):
    """Tests for ImportedConstraint dataclass."""

    def test_basic_constraint(self):
        """Test creating a basic constraint."""
        from parking_engine.cad_constraints.models import ImportedConstraint, ConstraintType

        geometry = Polygon.from_bounds(0, 0, 2, 2)
        constraint = ImportedConstraint(
            geometry=geometry,
            constraint_type=ConstraintType.COLUMN,
            source_format="dxf",
            source_layer_or_category="S-COLS",
            source_id="col_1",
            confidence=0.95,
        )

        self.assertEqual(constraint.area, 4.0)
        self.assertEqual(constraint.constraint_type, ConstraintType.COLUMN)
        self.assertTrue(constraint.is_high_confidence)
        self.assertFalse(constraint.is_unknown)

    def test_invalid_confidence(self):
        """Test that invalid confidence raises error."""
        from parking_engine.cad_constraints.models import ImportedConstraint, ConstraintType

        geometry = Polygon.from_bounds(0, 0, 2, 2)
        with self.assertRaises(ValueError):
            ImportedConstraint(
                geometry=geometry,
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="layer",
                confidence=1.5,  # Invalid
            )

    def test_invalid_source_format(self):
        """Test that invalid source format raises error."""
        from parking_engine.cad_constraints.models import ImportedConstraint, ConstraintType

        geometry = Polygon.from_bounds(0, 0, 2, 2)
        with self.assertRaises(ValueError):
            ImportedConstraint(
                geometry=geometry,
                constraint_type=ConstraintType.COLUMN,
                source_format="ifc",  # Not supported
                source_layer_or_category="layer",
            )

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from parking_engine.cad_constraints.models import ImportedConstraint, ConstraintType

        geometry = Polygon.from_bounds(0, 0, 2, 2)
        constraint = ImportedConstraint(
            geometry=geometry,
            constraint_type=ConstraintType.COLUMN,
            source_format="dxf",
            source_layer_or_category="layer",
        )

        d = constraint.to_dict()
        self.assertEqual(d["constraint_type"], "column")
        self.assertEqual(d["source_format"], "dxf")
        self.assertIn("area_sf", d)


class TestConstraintSet(unittest.TestCase):
    """Tests for ConstraintSet."""

    def test_empty_set(self):
        """Test empty constraint set."""
        from parking_engine.cad_constraints.models import ConstraintSet

        cs = ConstraintSet()
        self.assertEqual(cs.count, 0)
        self.assertEqual(cs.total_area, 0.0)
        self.assertEqual(cs.unknown_count, 0)

    def test_set_with_constraints(self):
        """Test constraint set with multiple constraints."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )

        constraints = [
            ImportedConstraint(
                geometry=Polygon.from_bounds(0, 0, 2, 2),
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="cols",
            ),
            ImportedConstraint(
                geometry=Polygon.from_bounds(10, 10, 20, 20),
                constraint_type=ConstraintType.CORE,
                source_format="dxf",
                source_layer_or_category="cores",
            ),
        ]

        cs = ConstraintSet(constraints=constraints)
        self.assertEqual(cs.count, 2)
        self.assertEqual(cs.total_area, 4.0 + 100.0)
        self.assertEqual(cs.unknown_count, 0)

    def test_filter_by_type(self):
        """Test filtering constraints by type."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )

        constraints = [
            ImportedConstraint(
                geometry=Polygon.from_bounds(0, 0, 2, 2),
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="cols",
            ),
            ImportedConstraint(
                geometry=Polygon.from_bounds(10, 10, 20, 20),
                constraint_type=ConstraintType.CORE,
                source_format="dxf",
                source_layer_or_category="cores",
            ),
        ]

        cs = ConstraintSet(constraints=constraints)
        columns = cs.filter_by_type(ConstraintType.COLUMN)

        self.assertEqual(columns.count, 1)
        self.assertEqual(
            columns.constraints[0].constraint_type, ConstraintType.COLUMN)


class TestLayerClassifier(unittest.TestCase):
    """Tests for layer-based classification."""

    def test_classify_column_layers(self):
        """Test classification of column layers."""
        from parking_engine.cad_constraints.classifiers import classify_by_layer
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(classify_by_layer("S-COLS"), ConstraintType.COLUMN)
        self.assertEqual(classify_by_layer(
            "structural_columns"), ConstraintType.COLUMN)
        self.assertEqual(classify_by_layer("A-COLS"), ConstraintType.COLUMN)
        self.assertEqual(classify_by_layer(
            "COLUMN-GRID"), ConstraintType.COLUMN)

    def test_classify_core_layers(self):
        """Test classification of core layers."""
        from parking_engine.cad_constraints.classifiers import classify_by_layer
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(classify_by_layer("stair_core"), ConstraintType.CORE)
        self.assertEqual(classify_by_layer("ELEVATOR"), ConstraintType.CORE)
        self.assertEqual(classify_by_layer("A-CORE"), ConstraintType.CORE)

    def test_classify_wall_layers(self):
        """Test classification of wall layers."""
        from parking_engine.cad_constraints.classifiers import classify_by_layer
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(classify_by_layer("A-WALL"), ConstraintType.WALL)
        self.assertEqual(classify_by_layer("walls"), ConstraintType.WALL)

    def test_classify_unknown(self):
        """Test unknown layers default to UNKNOWN."""
        from parking_engine.cad_constraints.classifiers import classify_by_layer
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(classify_by_layer(
            "random_layer"), ConstraintType.UNKNOWN)
        self.assertEqual(classify_by_layer("0"), ConstraintType.UNKNOWN)


class TestCategoryClassifier(unittest.TestCase):
    """Tests for Revit category-based classification."""

    def test_classify_revit_categories(self):
        """Test classification of Revit categories."""
        from parking_engine.cad_constraints.classifiers import classify_by_category
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(
            classify_by_category("OST_StructuralColumns"),
            ConstraintType.COLUMN
        )
        self.assertEqual(classify_by_category(
            "OST_Walls"), ConstraintType.WALL)
        self.assertEqual(classify_by_category(
            "OST_Shafts"), ConstraintType.SHAFT)

    def test_classify_room_by_name(self):
        """Test room classification by name."""
        from parking_engine.cad_constraints.classifiers import classify_by_room_name
        from parking_engine.cad_constraints.models import ConstraintType

        self.assertEqual(
            classify_by_room_name("Mechanical Room"),
            ConstraintType.MEP_ROOM
        )
        self.assertEqual(
            classify_by_room_name("Electrical Closet"),
            ConstraintType.MEP_ROOM
        )
        self.assertEqual(classify_by_room_name("Stair 1"), ConstraintType.CORE)
        self.assertEqual(classify_by_room_name(
            "Office"), ConstraintType.UNKNOWN)


class TestGeometryValidation(unittest.TestCase):
    """Tests for geometry validation."""

    def test_valid_rectangle(self):
        """Test validation of valid rectangle."""
        from parking_engine.cad_constraints.validators import validate_polygon

        polygon = Polygon.from_bounds(0, 0, 10, 10)
        result = validate_polygon(polygon)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(result.vertex_count, 4)
        self.assertEqual(result.area, 100.0)

    def test_too_few_vertices(self):
        """Test validation rejects too few vertices."""
        from parking_engine.cad_constraints.validators import validate_polygon

        polygon = Polygon([Point(0, 0), Point(1, 1)])  # Only 2 vertices
        result = validate_polygon(polygon)

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(e.error_type.name == "TOO_FEW_VERTICES" for e in result.errors))

    def test_area_too_small(self):
        """Test validation rejects tiny polygons."""
        from parking_engine.cad_constraints.validators import validate_polygon

        # 0.01 x 0.01 = 0.0001 SF (below minimum)
        polygon = Polygon.from_bounds(0, 0, 0.01, 0.01)
        result = validate_polygon(polygon)

        self.assertFalse(result.is_valid)
        self.assertTrue(
            any(e.error_type.name == "AREA_TOO_SMALL" for e in result.errors))

    def test_convexity_detection(self):
        """Test convexity detection."""
        from parking_engine.cad_constraints.validators import validate_polygon

        # Convex rectangle
        rect = Polygon.from_bounds(0, 0, 10, 10)
        result = validate_polygon(rect)
        self.assertTrue(result.is_convex)


class TestUnitNormalization(unittest.TestCase):
    """Tests for unit normalization."""

    def test_feet_to_feet(self):
        """Test feet to feet (no conversion)."""
        from parking_engine.cad_constraints.normalizer import (
            normalize_geometry, UnitSystem
        )

        polygon = Polygon.from_bounds(0, 0, 100, 100)
        normalized = normalize_geometry(polygon, source_units=UnitSystem.FEET)

        self.assertEqual(normalized.bounds, polygon.bounds)

    def test_inches_to_feet(self):
        """Test inches to feet conversion."""
        from parking_engine.cad_constraints.normalizer import (
            normalize_geometry, UnitSystem
        )

        # 120 inches = 10 feet
        polygon = Polygon.from_bounds(0, 0, 120, 120)
        normalized = normalize_geometry(
            polygon, source_units=UnitSystem.INCHES)

        self.assertAlmostEqual(normalized.width, 10.0, places=1)
        self.assertAlmostEqual(normalized.height, 10.0, places=1)

    def test_meters_to_feet(self):
        """Test meters to feet conversion."""
        from parking_engine.cad_constraints.normalizer import (
            normalize_geometry, UnitSystem
        )

        # 10 meters ≈ 32.8 feet
        polygon = Polygon.from_bounds(0, 0, 10, 10)
        normalized = normalize_geometry(
            polygon, source_units=UnitSystem.METERS)

        self.assertAlmostEqual(normalized.width, 32.8084, places=1)

    def test_origin_translation(self):
        """Test coordinate origin translation."""
        from parking_engine.cad_constraints.normalizer import (
            normalize_geometry, UnitSystem
        )

        polygon = Polygon.from_bounds(100, 100, 200, 200)
        normalized = normalize_geometry(
            polygon,
            source_units=UnitSystem.FEET,
            site_origin=Point(100, 100),
        )

        min_x, min_y, max_x, max_y = normalized.bounds
        self.assertAlmostEqual(min_x, 0.0)
        self.assertAlmostEqual(min_y, 0.0)


class TestDXFColumnConstraintsRemovingStalls(unittest.TestCase):
    """Test that DXF column constraints remove stalls."""

    def test_column_removes_stalls(self):
        """Test that a column constraint removes overlapping stalls."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_surface_layout
        )

        # Create a parking site
        site = Polygon.from_bounds(0, 0, 200, 150)

        # Generate unconstrained layout first
        unconstrained = generate_surface_layout(site, setback=5.0)
        unconstrained_stalls = unconstrained.total_stalls

        # Create column constraints in the middle of the site
        columns = [
            ImportedConstraint(
                geometry=Polygon.from_bounds(95, 70, 105, 80),  # 10x10 column
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="S-COLS",
                source_id="col_1",
            ),
        ]
        constraint_set = ConstraintSet(constraints=columns)

        # Apply constraints
        result = apply_constraints_to_surface_layout(
            site_boundary=site,
            constraints=constraint_set,
            setback=5.0,
        )

        # Verify stalls were lost
        self.assertIsNotNone(result.layout)
        self.assertLess(result.total_stalls, unconstrained_stalls)
        self.assertGreater(result.constraint_impact.total_stalls_lost, 0)


class TestRVTCoresExcludingZones(unittest.TestCase):
    """Test that RVT core constraints exclude parking zones."""

    def test_core_excludes_zone(self):
        """Test that a core constraint excludes a parking zone."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_structured_layout
        )

        # Create a structured parking skeleton
        footprint = Polygon.from_bounds(0, 0, 200, 150)
        skeleton = generate_structured_parking_skeleton(
            footprint=footprint,
            level_count=2,
        )

        # Create a core constraint
        core = ImportedConstraint(
            geometry=Polygon.from_bounds(90, 65, 110, 85),  # 20x20 core
            constraint_type=ConstraintType.CORE,
            source_format="rvt",
            source_layer_or_category="OST_Rooms",
            source_id="stair_core_1",
        )
        constraint_set = ConstraintSet(constraints=[core])

        # Apply constraints
        result = apply_constraints_to_structured_layout(
            structured_layout=skeleton,
            constraints=constraint_set,
        )

        # Verify core was applied
        self.assertIsNotNone(result.layout)
        self.assertGreater(result.constraint_impact.total_area_lost, 0)


class TestUnknownConstraintsDefaultToExclusion(unittest.TestCase):
    """Test that UNKNOWN constraints are treated as exclusions."""

    def test_unknown_constraint_excludes(self):
        """Test that UNKNOWN type constraints still exclude parking."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_surface_layout
        )

        site = Polygon.from_bounds(0, 0, 200, 150)

        # Create an UNKNOWN constraint
        unknown = ImportedConstraint(
            geometry=Polygon.from_bounds(80, 60, 120, 90),
            constraint_type=ConstraintType.UNKNOWN,
            source_format="dxf",
            source_layer_or_category="random_layer",
        )
        constraint_set = ConstraintSet(constraints=[unknown])

        # Get unconstrained baseline
        unconstrained = generate_surface_layout(site, setback=5.0)

        # Apply constraint
        result = apply_constraints_to_surface_layout(
            site_boundary=site,
            constraints=constraint_set,
            setback=5.0,
        )

        # UNKNOWN constraints should still exclude area
        self.assertLess(result.constrained_site_area,
                        result.original_site_area)


class TestRegressionNoConstraints(unittest.TestCase):
    """Test that no CAD/BIM input produces unchanged results."""

    def test_empty_constraints_unchanged(self):
        """Test that empty constraint set produces same layout."""
        from parking_engine.cad_constraints.models import ConstraintSet
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_surface_layout
        )

        site = Polygon.from_bounds(0, 0, 200, 150)

        # Generate unconstrained layout
        unconstrained = generate_surface_layout(site, setback=5.0)

        # Apply empty constraints
        empty_constraints = ConstraintSet()
        result = apply_constraints_to_surface_layout(
            site_boundary=site,
            constraints=empty_constraints,
            setback=5.0,
            compute_unconstrained_baseline=True,
        )

        # Should have same stall count and no stalls lost
        self.assertEqual(result.total_stalls, unconstrained.total_stalls)
        self.assertEqual(result.stalls_removed, 0)

    def test_structured_empty_constraints_unchanged(self):
        """Test that empty constraints don't change structured layout."""
        from parking_engine.cad_constraints.models import ConstraintSet
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_structured_layout
        )
        from parking_engine.structured_layout import generate_structured_parking_layout

        footprint = Polygon.from_bounds(0, 0, 200, 150)
        skeleton = generate_structured_parking_skeleton(
            footprint, level_count=2)

        # Generate unconstrained layout
        unconstrained = generate_structured_parking_layout(skeleton)

        # Apply empty constraints
        empty_constraints = ConstraintSet()
        result = apply_constraints_to_structured_layout(
            structured_layout=skeleton,
            constraints=empty_constraints,
            compute_unconstrained_baseline=False,
        )

        # Should have same stall count
        self.assertEqual(result.total_stalls, unconstrained.total_stalls)


class TestOverlappingConstraints(unittest.TestCase):
    """Test handling of overlapping constraints."""

    def test_overlapping_constraints_handled(self):
        """Test that overlapping constraints are handled correctly."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_surface_layout
        )

        site = Polygon.from_bounds(0, 0, 200, 150)

        # Create overlapping constraints
        constraints = [
            ImportedConstraint(
                geometry=Polygon.from_bounds(90, 65, 110, 85),
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="cols",
                source_id="col_1",
            ),
            ImportedConstraint(
                geometry=Polygon.from_bounds(
                    100, 70, 120, 90),  # Overlaps col_1
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="cols",
                source_id="col_2",
            ),
        ]
        constraint_set = ConstraintSet(constraints=constraints)

        # Should not raise error
        result = apply_constraints_to_surface_layout(
            site_boundary=site,
            constraints=constraint_set,
            setback=5.0,
        )

        self.assertIsNotNone(result)
        self.assertGreater(result.constraint_impact.total_area_lost, 0)


class TestDeterminism(unittest.TestCase):
    """Test that constraint integration is deterministic."""

    def test_constraint_integration_deterministic(self):
        """Test that same inputs produce same outputs."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )
        from parking_engine.cad_constraints.integration import (
            apply_constraints_to_surface_layout
        )

        site = Polygon.from_bounds(0, 0, 200, 150)
        constraint = ImportedConstraint(
            geometry=Polygon.from_bounds(90, 65, 110, 85),
            constraint_type=ConstraintType.COLUMN,
            source_format="dxf",
            source_layer_or_category="cols",
        )
        constraint_set = ConstraintSet(constraints=[constraint])

        # Run twice
        result1 = apply_constraints_to_surface_layout(
            site, constraint_set, setback=5.0)
        result2 = apply_constraints_to_surface_layout(
            site, constraint_set, setback=5.0)

        # Should be identical
        self.assertEqual(result1.total_stalls, result2.total_stalls)
        self.assertEqual(
            result1.constraint_impact.total_stalls_lost,
            result2.constraint_impact.total_stalls_lost,
        )


class TestConstraintSetPolygonExtraction(unittest.TestCase):
    """Test ConstraintSet polygon extraction methods."""

    def test_get_polygons(self):
        """Test getting all polygons from constraint set."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )

        constraints = [
            ImportedConstraint(
                geometry=Polygon.from_bounds(0, 0, 2, 2),
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="cols",
            ),
            ImportedConstraint(
                geometry=Polygon.from_bounds(10, 10, 15, 15),
                constraint_type=ConstraintType.CORE,
                source_format="dxf",
                source_layer_or_category="cores",
            ),
        ]
        cs = ConstraintSet(constraints=constraints)

        polygons = cs.get_polygons()
        self.assertEqual(len(polygons), 2)
        self.assertEqual(polygons[0].area, 4.0)
        self.assertEqual(polygons[1].area, 25.0)

    def test_get_polygons_by_type(self):
        """Test getting polygons for specific type."""
        from parking_engine.cad_constraints.models import (
            ConstraintSet, ImportedConstraint, ConstraintType
        )

        constraints = [
            ImportedConstraint(
                geometry=Polygon.from_bounds(0, 0, 2, 2),
                constraint_type=ConstraintType.COLUMN,
                source_format="dxf",
                source_layer_or_category="cols",
            ),
            ImportedConstraint(
                geometry=Polygon.from_bounds(10, 10, 15, 15),
                constraint_type=ConstraintType.CORE,
                source_format="dxf",
                source_layer_or_category="cores",
            ),
        ]
        cs = ConstraintSet(constraints=constraints)

        column_polygons = cs.get_polygons_by_type(ConstraintType.COLUMN)
        self.assertEqual(len(column_polygons), 1)
        self.assertEqual(column_polygons[0].area, 4.0)


class TestLoaderFromGeometry(unittest.TestCase):
    """Test loading constraints from programmatic geometry."""

    def test_dxf_loader_from_geometry(self):
        """Test DXF loader with geometry data."""
        from parking_engine.cad_constraints.loader import DXFLoader
        from parking_engine.cad_constraints.models import ConstraintType

        loader = DXFLoader()
        elements = [
            {
                "vertices": [
                    {"x": 0, "y": 0},
                    {"x": 2, "y": 0},
                    {"x": 2, "y": 2},
                    {"x": 0, "y": 2},
                ],
                "layer": "S-COLS",
                "id": "col_1",
            },
        ]

        result = loader.load_from_geometry(elements)

        self.assertTrue(result.success)
        self.assertEqual(result.constraint_set.count, 1)
        self.assertEqual(
            result.constraint_set.constraints[0].constraint_type,
            ConstraintType.COLUMN
        )

    def test_rvt_loader_from_geometry(self):
        """Test RVT loader with geometry data."""
        from parking_engine.cad_constraints.loader import RVTLoader
        from parking_engine.cad_constraints.models import ConstraintType

        loader = RVTLoader()
        elements = [
            {
                "footprint": [
                    {"x": 0, "y": 0},
                    {"x": 20, "y": 0},
                    {"x": 20, "y": 20},
                    {"x": 0, "y": 20},
                ],
                "category": "OST_StructuralColumns",
                "element_id": "123456",
            },
        ]

        result = loader.load_from_geometry(elements)

        self.assertTrue(result.success)
        self.assertEqual(result.constraint_set.count, 1)
        self.assertEqual(
            result.constraint_set.constraints[0].constraint_type,
            ConstraintType.COLUMN
        )


class TestIntegrationHelpers(unittest.TestCase):
    """Test integration helper functions."""

    def test_create_constraint_from_polygon(self):
        """Test creating constraint from polygon."""
        from parking_engine.cad_constraints.integration import create_constraint_from_polygon
        from parking_engine.cad_constraints.models import ConstraintType

        polygon = Polygon.from_bounds(0, 0, 5, 5)
        constraint = create_constraint_from_polygon(
            polygon,
            constraint_type=ConstraintType.COLUMN,
            source_format="dxf",
            layer="custom_layer",
        )

        self.assertEqual(constraint.area, 25.0)
        self.assertEqual(constraint.constraint_type, ConstraintType.COLUMN)
        self.assertEqual(constraint.source_layer_or_category, "custom_layer")

    def test_create_constraint_set_from_polygons(self):
        """Test creating constraint set from polygons."""
        from parking_engine.cad_constraints.integration import create_constraint_set_from_polygons
        from parking_engine.cad_constraints.models import ConstraintType

        polygons = [
            Polygon.from_bounds(0, 0, 5, 5),
            Polygon.from_bounds(10, 10, 15, 15),
        ]

        cs = create_constraint_set_from_polygons(
            polygons,
            constraint_type=ConstraintType.WALL,
        )

        self.assertEqual(cs.count, 2)
        for c in cs.constraints:
            self.assertEqual(c.constraint_type, ConstraintType.WALL)


class TestConstraintImpactMetrics(unittest.TestCase):
    """Test constraint impact metric calculations."""

    def test_impact_summary(self):
        """Test impact summary generation."""
        from parking_engine.cad_constraints.models import ConstraintImpact

        impact = ConstraintImpact(
            total_stalls_lost=10,
            total_area_lost=500.0,
            stalls_lost_by_type={"column": 5, "core": 5},
            area_lost_by_type={"column": 200.0, "core": 300.0},
            unconstrained_stalls=100,
            constrained_stalls=90,
            efficiency_delta=0.1,
        )

        summary = impact.summary()
        self.assertIn("10 stalls lost", summary)
        self.assertIn("500", summary)

    def test_impact_to_dict(self):
        """Test impact serialization."""
        from parking_engine.cad_constraints.models import ConstraintImpact

        impact = ConstraintImpact(
            total_stalls_lost=10,
            unconstrained_stalls=100,
            constrained_stalls=90,
            efficiency_delta=0.1,
        )

        d = impact.to_dict()
        self.assertEqual(d["total_stalls_lost"], 10)
        self.assertEqual(d["efficiency_delta_pct"], 10.0)


if __name__ == "__main__":
    unittest.main()
