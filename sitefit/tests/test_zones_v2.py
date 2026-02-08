"""
GenFabTools Parking Engine v2 — Zone Unit Tests

Tests for Zone data model and API schemas.
"""

import pytest
from pydantic import ValidationError

from sitefit.core.geometry import Point, Polygon
from sitefit.parking_engine.v2.zones import (
    Zone,
    ZoneType,
    AngleConfig,
    validate_zones,
    sort_zones_for_processing,
    create_default_zone,
)
from sitefit.parking_engine.v2.schemas import (
    ZoneTypeSchema,
    AngleConfigSchema,
    ZoneSchema,
    ZoneResultSchema,
    V2RequestExtension,
    V2ResponseExtension,
    PointSchema,
    PolygonSchema,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def simple_polygon():
    """A simple 100x100 square polygon."""
    return Polygon([
        Point(0, 0),
        Point(100, 0),
        Point(100, 100),
        Point(0, 100),
    ])


@pytest.fixture
def small_polygon():
    """A small 50x50 square polygon."""
    return Polygon([
        Point(0, 0),
        Point(50, 0),
        Point(50, 50),
        Point(0, 50),
    ])


@pytest.fixture
def adjacent_polygon():
    """A polygon adjacent to simple_polygon (no overlap)."""
    return Polygon([
        Point(100, 0),
        Point(200, 0),
        Point(200, 100),
        Point(100, 100),
    ])


@pytest.fixture
def overlapping_polygon():
    """A polygon that overlaps with simple_polygon."""
    return Polygon([
        Point(50, 50),
        Point(150, 50),
        Point(150, 150),
        Point(50, 150),
    ])


# =============================================================================
# ZONE TYPE TESTS
# =============================================================================

class TestZoneType:
    """Tests for ZoneType enum."""

    def test_zone_type_values(self):
        """Verify zone type enum values."""
        assert ZoneType.GENERAL.value == "GENERAL"
        assert ZoneType.RESERVED.value == "RESERVED"

    def test_zone_type_count(self):
        """Verify only 2 zone types exist (ADA removed per spec)."""
        assert len(ZoneType) == 2

    def test_zone_type_is_string_enum(self):
        """Verify ZoneType is a string enum."""
        assert ZoneType.GENERAL == "GENERAL"


# =============================================================================
# ANGLE CONFIG TESTS
# =============================================================================

class TestAngleConfig:
    """Tests for AngleConfig enum."""

    def test_angle_config_values(self):
        """Verify angle config enum values."""
        assert AngleConfig.DEGREES_90.value == "90_DEGREES"
        assert AngleConfig.DEGREES_60.value == "60_DEGREES"

    def test_angle_config_count(self):
        """Verify only 2 angle configs exist."""
        assert len(AngleConfig) == 2


# =============================================================================
# ZONE MODEL TESTS
# =============================================================================

class TestZone:
    """Tests for Zone dataclass."""

    def test_zone_creation_minimal(self, simple_polygon):
        """Test zone creation with minimal required fields."""
        zone = Zone(
            name="Test Zone",
            zone_type=ZoneType.GENERAL,
            polygon=simple_polygon,
        )

        assert zone.name == "Test Zone"
        assert zone.zone_type == ZoneType.GENERAL
        assert zone.angle_config == AngleConfig.DEGREES_90
        assert zone.stall_target_min is None
        assert zone.stall_target_max is None
        assert zone.id is not None  # Auto-generated

    def test_zone_creation_full(self, simple_polygon):
        """Test zone creation with all fields."""
        zone = Zone(
            id="custom-id",
            name="Reserved Area",
            zone_type=ZoneType.RESERVED,
            polygon=simple_polygon,
            angle_config=AngleConfig.DEGREES_60,
            stall_target_min=10,
            stall_target_max=20,
        )

        assert zone.id == "custom-id"
        assert zone.name == "Reserved Area"
        assert zone.zone_type == ZoneType.RESERVED
        assert zone.angle_config == AngleConfig.DEGREES_60
        assert zone.stall_target_min == 10
        assert zone.stall_target_max == 20

    def test_zone_empty_name_rejected(self, simple_polygon):
        """Test that empty zone name is rejected."""
        with pytest.raises(ValueError, match="Zone name cannot be empty"):
            Zone(
                name="",
                zone_type=ZoneType.GENERAL,
                polygon=simple_polygon,
            )

    def test_zone_whitespace_name_rejected(self, simple_polygon):
        """Test that whitespace-only zone name is rejected."""
        with pytest.raises(ValueError, match="Zone name cannot be empty"):
            Zone(
                name="   ",
                zone_type=ZoneType.GENERAL,
                polygon=simple_polygon,
            )

    def test_zone_invalid_stall_targets(self, simple_polygon):
        """Test that invalid stall target range is rejected."""
        with pytest.raises(ValueError, match="stall_target_min cannot exceed"):
            Zone(
                name="Test",
                zone_type=ZoneType.GENERAL,
                polygon=simple_polygon,
                stall_target_min=20,
                stall_target_max=10,
            )

    def test_zone_negative_stall_target_min(self, simple_polygon):
        """Test that negative stall_target_min is rejected."""
        with pytest.raises(ValueError, match="stall_target_min must be non-negative"):
            Zone(
                name="Test",
                zone_type=ZoneType.GENERAL,
                polygon=simple_polygon,
                stall_target_min=-1,
            )

    def test_zone_area_property(self, simple_polygon):
        """Test zone area property."""
        zone = Zone(
            name="Test",
            zone_type=ZoneType.GENERAL,
            polygon=simple_polygon,
        )

        assert zone.area == pytest.approx(10000, rel=1e-6)  # 100 * 100

    def test_zone_centroid_property(self, simple_polygon):
        """Test zone centroid property."""
        zone = Zone(
            name="Test",
            zone_type=ZoneType.GENERAL,
            polygon=simple_polygon,
        )

        centroid = zone.centroid
        assert centroid.x == pytest.approx(50, rel=1e-6)
        assert centroid.y == pytest.approx(50, rel=1e-6)

    def test_zone_intersects(self, simple_polygon, overlapping_polygon):
        """Test zone intersection detection."""
        zone_a = Zone(name="A", zone_type=ZoneType.GENERAL,
                      polygon=simple_polygon)
        zone_b = Zone(name="B", zone_type=ZoneType.GENERAL,
                      polygon=overlapping_polygon)

        assert zone_a.intersects(zone_b) is True

    def test_zone_not_intersects(self, simple_polygon, adjacent_polygon):
        """Test zones that don't intersect."""
        zone_a = Zone(name="A", zone_type=ZoneType.GENERAL,
                      polygon=simple_polygon)
        zone_b = Zone(name="B", zone_type=ZoneType.GENERAL,
                      polygon=adjacent_polygon)

        # Adjacent polygons share an edge but don't overlap
        # The intersects check should return True for shared edges
        # but intersection_area should be ~0
        assert zone_a.intersection_area(zone_b) < 1.0


# =============================================================================
# ZONE VALIDATION TESTS
# =============================================================================

class TestValidateZones:
    """Tests for validate_zones function."""

    def test_empty_zones_valid(self):
        """Empty zone list is valid (defaults to single GENERAL zone)."""
        errors = validate_zones([])
        assert errors == []

    def test_single_zone_valid(self, simple_polygon):
        """Single zone is valid."""
        zones = [
            Zone(name="Main", zone_type=ZoneType.GENERAL, polygon=simple_polygon)
        ]
        errors = validate_zones(zones)
        assert errors == []

    def test_adjacent_zones_valid(self, simple_polygon, adjacent_polygon):
        """Adjacent (non-overlapping) zones are valid."""
        zones = [
            Zone(id="a", name="A", zone_type=ZoneType.GENERAL,
                 polygon=simple_polygon),
            Zone(id="b", name="B", zone_type=ZoneType.GENERAL,
                 polygon=adjacent_polygon),
        ]
        errors = validate_zones(zones)
        assert errors == []

    def test_overlapping_zones_invalid(self, simple_polygon, overlapping_polygon):
        """Overlapping zones produce validation error."""
        zones = [
            Zone(id="a", name="A", zone_type=ZoneType.GENERAL,
                 polygon=simple_polygon),
            Zone(id="b", name="B", zone_type=ZoneType.GENERAL,
                 polygon=overlapping_polygon),
        ]
        errors = validate_zones(zones)
        assert len(errors) == 1
        assert "overlap" in errors[0].lower()

    def test_duplicate_ids_invalid(self, simple_polygon, adjacent_polygon):
        """Duplicate zone IDs produce validation error."""
        zones = [
            Zone(id="same-id", name="A", zone_type=ZoneType.GENERAL,
                 polygon=simple_polygon),
            Zone(id="same-id", name="B", zone_type=ZoneType.GENERAL,
                 polygon=adjacent_polygon),
        ]
        errors = validate_zones(zones)
        assert len(errors) == 1
        assert "duplicate" in errors[0].lower()


# =============================================================================
# ZONE SORTING TESTS (DETERMINISM)
# =============================================================================

class TestSortZonesForProcessing:
    """Tests for deterministic zone sorting."""

    def test_sort_by_id_alphabetical(self, simple_polygon, adjacent_polygon):
        """Zones are sorted alphabetically by ID."""
        zone_b = Zone(id="zone-b", name="B",
                      zone_type=ZoneType.GENERAL, polygon=adjacent_polygon)
        zone_a = Zone(id="zone-a", name="A",
                      zone_type=ZoneType.GENERAL, polygon=simple_polygon)

        sorted_zones = sort_zones_for_processing([zone_b, zone_a])

        assert sorted_zones[0].id == "zone-a"
        assert sorted_zones[1].id == "zone-b"

    def test_sort_is_stable(self, simple_polygon, adjacent_polygon):
        """Sorting is deterministic (same input = same output)."""
        zone_a = Zone(id="zone-a", name="A",
                      zone_type=ZoneType.GENERAL, polygon=simple_polygon)
        zone_b = Zone(id="zone-b", name="B",
                      zone_type=ZoneType.GENERAL, polygon=adjacent_polygon)

        # Run multiple times
        for _ in range(10):
            sorted_zones = sort_zones_for_processing([zone_b, zone_a])
            assert sorted_zones[0].id == "zone-a"
            assert sorted_zones[1].id == "zone-b"


# =============================================================================
# DEFAULT ZONE TESTS
# =============================================================================

class TestCreateDefaultZone:
    """Tests for default zone creation."""

    def test_default_zone_is_general(self, simple_polygon):
        """Default zone is GENERAL type."""
        zone = create_default_zone(simple_polygon)
        assert zone.zone_type == ZoneType.GENERAL

    def test_default_zone_is_90_degrees(self, simple_polygon):
        """Default zone uses 90° angle."""
        zone = create_default_zone(simple_polygon)
        assert zone.angle_config == AngleConfig.DEGREES_90

    def test_default_zone_covers_site(self, simple_polygon):
        """Default zone covers entire site boundary."""
        zone = create_default_zone(simple_polygon)
        assert zone.area == simple_polygon.area

    def test_default_zone_has_fixed_id(self, simple_polygon):
        """Default zone has predictable ID for determinism."""
        zone = create_default_zone(simple_polygon)
        assert zone.id == "default-zone"


# =============================================================================
# API SCHEMA TESTS
# =============================================================================

class TestZoneSchema:
    """Tests for ZoneSchema Pydantic model."""

    def test_zone_schema_valid(self):
        """Valid zone schema parses correctly."""
        data = {
            "id": "zone-1",
            "name": "Main Lot",
            "type": "GENERAL",
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 100},
                    {"x": 0, "y": 100},
                ]
            },
            "angleConfig": "90_DEGREES",
        }

        schema = ZoneSchema(**data)
        assert schema.id == "zone-1"
        assert schema.name == "Main Lot"
        assert schema.type == ZoneTypeSchema.GENERAL
        assert schema.angleConfig == AngleConfigSchema.DEGREES_90

    def test_zone_schema_defaults(self):
        """Zone schema uses correct defaults."""
        data = {
            "id": "zone-1",
            "name": "Main Lot",
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 100},
                    {"x": 0, "y": 100},
                ]
            },
        }

        schema = ZoneSchema(**data)
        assert schema.type == ZoneTypeSchema.GENERAL
        assert schema.angleConfig == AngleConfigSchema.DEGREES_90
        assert schema.stallTargetMin is None
        assert schema.stallTargetMax is None

    def test_zone_schema_empty_name_rejected(self):
        """Empty zone name rejected by schema."""
        data = {
            "id": "zone-1",
            "name": "",
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 100},
                    {"x": 0, "y": 100},
                ]
            },
        }

        with pytest.raises(ValidationError):
            ZoneSchema(**data)

    def test_zone_schema_invalid_stall_targets(self):
        """Invalid stall target range rejected by schema."""
        data = {
            "id": "zone-1",
            "name": "Test",
            "polygon": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 100},
                    {"x": 0, "y": 100},
                ]
            },
            "stallTargetMin": 20,
            "stallTargetMax": 10,
        }

        with pytest.raises(ValidationError):
            ZoneSchema(**data)


class TestV2RequestExtension:
    """Tests for V2RequestExtension schema."""

    def test_defaults(self):
        """V2 request extension has correct defaults."""
        ext = V2RequestExtension()

        assert ext.zones is None
        assert ext.allowAngledParking is False
        assert ext.recoverResidual is False  # opt-in only per spec

    def test_with_zones(self):
        """V2 request extension accepts zone list."""
        data = {
            "zones": [
                {
                    "id": "zone-1",
                    "name": "Main",
                    "polygon": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 100, "y": 0},
                            {"x": 100, "y": 100},
                            {"x": 0, "y": 100},
                        ]
                    },
                }
            ],
            "allowAngledParking": True,
            "recoverResidual": True,
        }

        ext = V2RequestExtension(**data)
        assert len(ext.zones) == 1
        assert ext.allowAngledParking is True
        assert ext.recoverResidual is True


class TestV2ResponseExtension:
    """Tests for V2ResponseExtension schema."""

    def test_defaults(self):
        """V2 response extension has correct defaults."""
        ext = V2ResponseExtension()

        assert ext.zones is None
        assert ext.angledStalls == 0
        assert ext.residualRecovered == 0
        assert ext.circulationConnected is True

    def test_with_zones(self):
        """V2 response extension accepts zone results."""
        data = {
            "zones": [
                {
                    "id": "zone-1",
                    "name": "Main",
                    "type": "GENERAL",
                    "stallCount": 120,
                    "angledStalls": 15,
                    "area": 10000.0,
                }
            ],
            "angledStalls": 15,
            "residualRecovered": 8,
            "circulationConnected": True,
        }

        ext = V2ResponseExtension(**data)
        assert len(ext.zones) == 1
        assert ext.zones[0].stallCount == 120
        assert ext.angledStalls == 15
        assert ext.residualRecovered == 8
