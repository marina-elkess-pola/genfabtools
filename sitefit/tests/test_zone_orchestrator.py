"""
Unit tests for GenFabTools Parking Engine v2 — Zone Orchestrator

Tests validate:
- Deterministic zone ordering
- No stalls cross zone boundaries
- v1 behavior unchanged when zones are absent
- Zone-specific stall counts
- 90° and 60° zone handling
"""

import pytest
from sitefit.core.geometry import Point, Polygon
from sitefit.parking.layout_generator import LayoutConfig
from sitefit.parking.stall import Stall
from sitefit.parking.drive_aisle import DriveAisle
from sitefit.parking_engine.v2.zones import (
    Zone,
    ZoneType,
    AngleConfig,
    create_default_zone,
    sort_zones_for_processing,
)
from sitefit.parking_engine.v2.zone_orchestrator import (
    ZoneLayoutResult,
    OrchestratedLayoutResult,
    ZoneOrchestrator,
    orchestrate_layout,
    get_zone_order,
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


def create_zone_a() -> Zone:
    """Create zone A (left half of site)."""
    return Zone(
        name="Zone A",
        zone_type=ZoneType.GENERAL,
        polygon=create_simple_polygon(0, 0, 100, 150),
        id="zone-a",
        angle_config=AngleConfig.DEGREES_90,
    )


def create_zone_b() -> Zone:
    """Create zone B (right half of site)."""
    return Zone(
        name="Zone B",
        zone_type=ZoneType.GENERAL,
        polygon=create_simple_polygon(100, 0, 200, 150),
        id="zone-b",
        angle_config=AngleConfig.DEGREES_90,
    )


def create_zone_60() -> Zone:
    """Create a zone with 60° parking."""
    return Zone(
        name="Zone 60",
        zone_type=ZoneType.GENERAL,
        polygon=create_simple_polygon(0, 0, 150, 100),
        id="zone-60",
        angle_config=AngleConfig.DEGREES_60,
    )


# =============================================================================
# ZONE LAYOUT RESULT TESTS
# =============================================================================

class TestZoneLayoutResult:
    """Test ZoneLayoutResult dataclass."""

    def test_create_result(self):
        """Result should be creatable with minimal attributes."""
        result = ZoneLayoutResult(
            zone_id="test",
            zone_name="Test Zone",
            zone_type=ZoneType.GENERAL,
            angle_config=AngleConfig.DEGREES_90,
            stall_count=10,
        )
        assert result.zone_id == "test"
        assert result.stall_count == 10

    def test_to_dict(self):
        """Result should serialize to dict."""
        result = ZoneLayoutResult(
            zone_id="test",
            zone_name="Test Zone",
            zone_type=ZoneType.GENERAL,
            angle_config=AngleConfig.DEGREES_90,
            stall_count=10,
            area=1000.0,
        )
        d = result.to_dict()
        assert d["zone_id"] == "test"
        assert d["stall_count"] == 10
        assert d["angle_config"] == "90_DEGREES"


# =============================================================================
# ORCHESTRATED LAYOUT RESULT TESTS
# =============================================================================

class TestOrchestratedLayoutResult:
    """Test OrchestratedLayoutResult dataclass."""

    def test_stalls_by_zone(self):
        """Should return stall counts keyed by zone ID."""
        result = OrchestratedLayoutResult(
            zone_results=[
                ZoneLayoutResult("zone-a", "A", ZoneType.GENERAL,
                                 AngleConfig.DEGREES_90, 50),
                ZoneLayoutResult("zone-b", "B", ZoneType.GENERAL,
                                 AngleConfig.DEGREES_90, 30),
            ],
            total_stalls=80,
            total_area=2000.0,
            zones_processed=2,
        )
        assert result.stalls_by_zone == {"zone-a": 50, "zone-b": 30}

    def test_to_dict(self):
        """Result should serialize to dict."""
        result = OrchestratedLayoutResult(
            zone_results=[],
            total_stalls=0,
            total_area=0,
            zones_processed=0,
        )
        d = result.to_dict()
        assert "total_stalls" in d
        assert "zone_results" in d


# =============================================================================
# DETERMINISTIC ZONE ORDER TESTS
# =============================================================================

class TestDeterministicZoneOrder:
    """Test that zones are processed in deterministic order."""

    def test_get_zone_order_alphabetical(self):
        """Zones should be ordered alphabetically by ID."""
        zones = [
            Zone(name="C", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(200, 0, 300, 100), id="zone-c"),
            Zone(name="A", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(0, 0, 100, 100), id="zone-a"),
            Zone(name="B", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(100, 0, 200, 100), id="zone-b"),
        ]
        order = get_zone_order(zones)
        assert order == ["zone-a", "zone-b", "zone-c"]

    def test_get_zone_order_stable(self):
        """Same zones should always produce same order."""
        zones = [
            Zone(name="2", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(100, 0, 200, 100), id="z2"),
            Zone(name="1", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(0, 0, 100, 100), id="z1"),
            Zone(name="3", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(200, 0, 300, 100), id="z3"),
        ]
        order1 = get_zone_order(zones)
        order2 = get_zone_order(zones)
        order3 = get_zone_order(list(reversed(zones)))
        assert order1 == order2 == order3

    def test_orchestrator_processes_in_order(self):
        """Orchestrator should process zones in deterministic order."""
        site = create_simple_polygon(0, 0, 300, 100)
        zones = [
            Zone(name="C", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(200, 0, 300, 100), id="zone-c"),
            Zone(name="A", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(0, 0, 100, 100), id="zone-a"),
            Zone(name="B", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(100, 0, 200, 100), id="zone-b"),
        ]

        result = orchestrate_layout(site, zones)

        # Results should be in alphabetical order by zone ID
        result_ids = [r.zone_id for r in result.zone_results]
        assert result_ids == ["zone-a", "zone-b", "zone-c"]

    def test_repeated_runs_identical(self):
        """Multiple runs with same input should produce identical results."""
        site = create_test_site()
        zones = [create_zone_b(), create_zone_a()]

        result1 = orchestrate_layout(site, zones)
        result2 = orchestrate_layout(site, zones)

        assert result1.total_stalls == result2.total_stalls
        assert len(result1.zone_results) == len(result2.zone_results)

        for r1, r2 in zip(result1.zone_results, result2.zone_results):
            assert r1.zone_id == r2.zone_id
            assert r1.stall_count == r2.stall_count


# =============================================================================
# V1 BEHAVIOR UNCHANGED TESTS
# =============================================================================

class TestV1BehaviorUnchanged:
    """Test that v1 behavior is unchanged when zones are absent."""

    def test_no_zones_creates_default(self):
        """When no zones provided, should create default zone."""
        site = create_test_site()

        orchestrator = ZoneOrchestrator(site, zones=None)

        assert len(orchestrator.zones) == 1
        assert orchestrator.zones[0].id == "default-zone"
        assert orchestrator.zones[0].angle_config == AngleConfig.DEGREES_90

    def test_empty_zones_creates_default(self):
        """When empty zones list provided, should create default zone."""
        site = create_test_site()

        orchestrator = ZoneOrchestrator(site, zones=[])

        assert len(orchestrator.zones) == 1
        assert orchestrator.zones[0].id == "default-zone"

    def test_default_zone_covers_site(self):
        """Default zone should cover entire site."""
        site = create_test_site()

        orchestrator = ZoneOrchestrator(site, zones=None)

        default_zone = orchestrator.zones[0]
        assert abs(default_zone.area - site.area) < 0.01

    def test_single_default_zone_uses_v1(self):
        """Single default zone should use v1 engine (90°)."""
        site = create_test_site()

        result = orchestrate_layout(site, zones=None)

        assert result.zones_processed == 1
        assert result.zone_results[0].angle_config == AngleConfig.DEGREES_90
        # Should have bays (from v1), not stalls_60
        assert len(result.zone_results[0].bays) >= 0
        assert len(result.zone_results[0].stalls_60) == 0

    def test_default_zone_produces_stalls(self):
        """Default zone for reasonable site should produce stalls."""
        site = create_test_site()  # 200x150 = 30,000 sq ft

        result = orchestrate_layout(site, zones=None)

        # A 200x150 site should fit some stalls
        assert result.total_stalls > 0


# =============================================================================
# ZONE BOUNDARY TESTS
# =============================================================================

class TestZoneBoundaries:
    """Test that stalls don't cross zone boundaries."""

    def test_bays_within_zone_90(self):
        """90° bays should be within their zone."""
        site = create_test_site()
        zone_a = create_zone_a()  # Left half: 0-100
        zone_b = create_zone_b()  # Right half: 100-200

        result = orchestrate_layout(site, [zone_a, zone_b])

        zone_a_result = next(
            r for r in result.zone_results if r.zone_id == "zone-a")
        zone_b_result = next(
            r for r in result.zone_results if r.zone_id == "zone-b")

        zone_a_shapely = zone_a.polygon.to_shapely()
        zone_b_shapely = zone_b.polygon.to_shapely()

        # All zone A bays should have centers in zone A
        for bay in zone_a_result.bays:
            center = bay.bay_polygon.centroid.to_shapely()
            assert zone_a_shapely.contains(center), "Bay center outside zone A"

        # All zone B bays should have centers in zone B
        for bay in zone_b_result.bays:
            center = bay.bay_polygon.centroid.to_shapely()
            assert zone_b_shapely.contains(center), "Bay center outside zone B"

    def test_stalls_60_within_zone(self):
        """60° stalls should be within their zone."""
        site = create_simple_polygon(0, 0, 150, 100)
        zone = create_zone_60()

        result = orchestrate_layout(site, [zone])

        zone_result = result.zone_results[0]
        zone_shapely = zone.polygon.to_shapely()

        for stall in zone_result.stalls_60:
            stall_shapely = stall.polygon.to_shapely()
            assert zone_shapely.contains(stall_shapely), \
                f"Stall at {stall.anchor} extends outside zone"

    def test_60_stalls_no_overlap(self):
        """60° stalls must not overlap each other."""
        site = create_simple_polygon(0, 0, 200, 200)
        zone = Zone(
            name="Large 60 Zone",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 200, 200),
            id="zone-60-large",
            angle_config=AngleConfig.DEGREES_60,
        )

        result = orchestrate_layout(site, [zone])
        zone_result = result.zone_results[0]
        stalls = zone_result.stalls_60

        # Check all pairs for intersection
        for i, stall_a in enumerate(stalls):
            poly_a = stall_a.polygon.to_shapely()
            for j, stall_b in enumerate(stalls):
                if i >= j:
                    continue
                poly_b = stall_b.polygon.to_shapely()
                # Small tolerance for touching edges
                intersection = poly_a.intersection(poly_b)
                assert intersection.area < 0.1, \
                    f"Stalls {i} and {j} overlap by {intersection.area:.2f} sq ft"

    def test_60_stalls_no_aisle_intersection(self):
        """60° stalls must not intersect their aisles."""
        site = create_simple_polygon(0, 0, 200, 200)
        zone = Zone(
            name="Large 60 Zone",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 200, 200),
            id="zone-60-large",
            angle_config=AngleConfig.DEGREES_60,
        )

        result = orchestrate_layout(site, [zone])
        zone_result = result.zone_results[0]
        stalls = zone_result.stalls_60
        aisles = zone_result.aisles_60

        # Check each stall against each aisle
        for stall in stalls:
            stall_poly = stall.polygon.to_shapely()
            for aisle in aisles:
                aisle_poly = aisle.polygon.to_shapely()
                intersection = stall_poly.intersection(aisle_poly)
                assert intersection.area < 0.1, \
                    f"Stall at {stall.anchor} intersects aisle by {intersection.area:.2f} sq ft"

    def test_no_stall_overlap_between_zones(self):
        """Stalls from different zones should not overlap."""
        site = create_simple_polygon(0, 0, 200, 100)
        zone_a = Zone(
            name="Zone A",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 100, 100),
            id="zone-a",
            angle_config=AngleConfig.DEGREES_90,
        )
        zone_b = Zone(
            name="Zone B",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(100, 0, 200, 100),
            id="zone-b",
            angle_config=AngleConfig.DEGREES_90,
        )

        result = orchestrate_layout(site, [zone_a, zone_b])

        zone_a_result = next(
            r for r in result.zone_results if r.zone_id == "zone-a")
        zone_b_result = next(
            r for r in result.zone_results if r.zone_id == "zone-b")

        # Check that bay centers from zone A are not in zone B and vice versa
        zone_a_shapely = zone_a.polygon.to_shapely()
        zone_b_shapely = zone_b.polygon.to_shapely()

        for bay in zone_a_result.bays:
            center = bay.bay_polygon.centroid.to_shapely()
            assert not zone_b_shapely.contains(center), \
                "Zone A bay center is in zone B"

        for bay in zone_b_result.bays:
            center = bay.bay_polygon.centroid.to_shapely()
            assert not zone_a_shapely.contains(center), \
                "Zone B bay center is in zone A"


# =============================================================================
# ZONE TYPE HANDLING TESTS
# =============================================================================

class TestZoneTypeHandling:
    """Test handling of different zone types."""

    def test_general_zone(self):
        """GENERAL zone should be processed normally."""
        site = create_simple_polygon(0, 0, 100, 100)
        zone = Zone(
            name="General",
            zone_type=ZoneType.GENERAL,
            polygon=site,
            id="general",
            angle_config=AngleConfig.DEGREES_90,
        )

        result = orchestrate_layout(site, [zone])

        assert result.zone_results[0].zone_type == ZoneType.GENERAL

    def test_reserved_zone(self):
        """RESERVED zone should be processed normally."""
        site = create_simple_polygon(0, 0, 100, 100)
        zone = Zone(
            name="Reserved",
            zone_type=ZoneType.RESERVED,
            polygon=site,
            id="reserved",
            angle_config=AngleConfig.DEGREES_90,
        )

        result = orchestrate_layout(site, [zone])

        assert result.zone_results[0].zone_type == ZoneType.RESERVED


# =============================================================================
# ANGLE CONFIG HANDLING TESTS
# =============================================================================

class TestAngleConfigHandling:
    """Test handling of different angle configurations."""

    def test_90_degree_uses_v1(self):
        """90° zones should use v1 engine."""
        site = create_simple_polygon(0, 0, 100, 100)
        zone = Zone(
            name="Zone 90",
            zone_type=ZoneType.GENERAL,
            polygon=site,
            id="zone-90",
            angle_config=AngleConfig.DEGREES_90,
        )

        result = orchestrate_layout(site, [zone])

        assert result.zone_results[0].angle_config == AngleConfig.DEGREES_90
        # Should have bays (from v1), not stalls_60
        assert len(result.zone_results[0].stalls_60) == 0

    def test_60_degree_uses_v2(self):
        """60° zones should use v2 geometry."""
        site = create_simple_polygon(0, 0, 150, 100)
        zone = Zone(
            name="Zone 60",
            zone_type=ZoneType.GENERAL,
            polygon=site,
            id="zone-60",
            angle_config=AngleConfig.DEGREES_60,
        )

        result = orchestrate_layout(site, [zone])

        assert result.zone_results[0].angle_config == AngleConfig.DEGREES_60
        # Should have stalls_60 (from v2), not bays
        assert len(result.zone_results[0].bays) == 0

    def test_mixed_angles(self):
        """Site can have zones with different angles."""
        site = create_simple_polygon(0, 0, 250, 100)
        zone_90 = Zone(
            name="Zone 90",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 100, 100),
            id="zone-90",
            angle_config=AngleConfig.DEGREES_90,
        )
        zone_60 = Zone(
            name="Zone 60",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(100, 0, 250, 100),
            id="zone-60",
            angle_config=AngleConfig.DEGREES_60,
        )

        result = orchestrate_layout(site, [zone_90, zone_60])

        result_90 = next(
            r for r in result.zone_results if r.zone_id == "zone-90")
        result_60 = next(
            r for r in result.zone_results if r.zone_id == "zone-60")

        assert result_90.angle_config == AngleConfig.DEGREES_90
        assert result_60.angle_config == AngleConfig.DEGREES_60


# =============================================================================
# STALL COUNT TRACKING TESTS
# =============================================================================

class TestStallCountTracking:
    """Test that stall counts are tracked correctly."""

    def test_total_stalls_sum_of_zones(self):
        """Total stalls should equal sum of zone stalls."""
        site = create_test_site()
        zones = [create_zone_a(), create_zone_b()]

        result = orchestrate_layout(site, zones)

        zone_total = sum(r.stall_count for r in result.zone_results)
        assert result.total_stalls == zone_total

    def test_stalls_by_zone_correct(self):
        """Stalls by zone should match individual zone counts."""
        site = create_test_site()
        zones = [create_zone_a(), create_zone_b()]

        result = orchestrate_layout(site, zones)

        for zone_result in result.zone_results:
            assert result.stalls_by_zone[zone_result.zone_id] == zone_result.stall_count

    def test_zones_processed_count(self):
        """zones_processed should equal number of zones."""
        site = create_simple_polygon(0, 0, 300, 100)
        zones = [
            Zone(name="1", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(0, 0, 100, 100), id="z1"),
            Zone(name="2", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(100, 0, 200, 100), id="z2"),
            Zone(name="3", zone_type=ZoneType.GENERAL,
                 polygon=create_simple_polygon(200, 0, 300, 100), id="z3"),
        ]

        result = orchestrate_layout(site, zones)

        assert result.zones_processed == 3


# =============================================================================
# VALIDATION ERROR TESTS
# =============================================================================

class TestValidationErrors:
    """Test validation error handling."""

    def test_overlapping_zones_detected(self):
        """Overlapping zones should produce validation errors."""
        site = create_test_site()
        zone_a = Zone(
            name="A",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 120, 100),  # Overlaps with B
            id="zone-a",
        )
        zone_b = Zone(
            name="B",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(100, 0, 200, 100),  # Overlaps with A
            id="zone-b",
        )

        orchestrator = ZoneOrchestrator(site, [zone_a, zone_b])

        assert len(orchestrator.validation_errors) > 0
        assert any("overlap" in err.lower()
                   for err in orchestrator.validation_errors)

    def test_duplicate_ids_detected(self):
        """Duplicate zone IDs should produce validation errors."""
        site = create_simple_polygon(0, 0, 200, 100)
        zone_a = Zone(
            name="A",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 100, 100),
            id="same-id",
        )
        zone_b = Zone(
            name="B",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(100, 0, 200, 100),
            id="same-id",
        )

        orchestrator = ZoneOrchestrator(site, [zone_a, zone_b])

        assert len(orchestrator.validation_errors) > 0
        assert any("duplicate" in err.lower()
                   for err in orchestrator.validation_errors)

    def test_validation_errors_in_result(self):
        """Validation errors should be included in result."""
        site = create_simple_polygon(0, 0, 200, 100)
        zone_a = Zone(
            name="A",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(0, 0, 100, 100),
            id="same-id",
        )
        zone_b = Zone(
            name="B",
            zone_type=ZoneType.GENERAL,
            polygon=create_simple_polygon(100, 0, 200, 100),
            id="same-id",
        )

        result = orchestrate_layout(site, [zone_a, zone_b])

        assert len(result.validation_errors) > 0


# =============================================================================
# SMALL ZONE TESTS
# =============================================================================

class TestSmallZones:
    """Test handling of zones too small for parking."""

    def test_small_zone_no_stalls(self):
        """Very small zone should produce zero stalls."""
        site = create_simple_polygon(0, 0, 10, 10)  # 100 sq ft, too small
        zone = Zone(
            name="Tiny",
            zone_type=ZoneType.GENERAL,
            polygon=site,
            id="tiny",
            angle_config=AngleConfig.DEGREES_90,
        )

        result = orchestrate_layout(site, [zone])

        assert result.zone_results[0].stall_count == 0

    def test_small_60_zone_no_stalls(self):
        """Very small 60° zone should produce zero stalls."""
        site = create_simple_polygon(0, 0, 30, 30)  # Too small for 60° row
        zone = Zone(
            name="Tiny 60",
            zone_type=ZoneType.GENERAL,
            polygon=site,
            id="tiny-60",
            angle_config=AngleConfig.DEGREES_60,
        )

        result = orchestrate_layout(site, [zone])

        assert result.zone_results[0].stall_count == 0


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Test JSON serialization of results."""

    def test_result_to_dict_complete(self):
        """Result should serialize with all required fields."""
        site = create_test_site()

        result = orchestrate_layout(site, zones=None)
        d = result.to_dict()

        assert "total_stalls" in d
        assert "total_area" in d
        assert "zones_processed" in d
        assert "zone_results" in d
        assert "stalls_by_zone" in d

    def test_zone_result_serialization(self):
        """Zone results should serialize correctly."""
        site = create_test_site()

        result = orchestrate_layout(site, zones=None)

        for zone_result in result.zone_results:
            d = zone_result.to_dict()
            assert "zone_id" in d
            assert "zone_name" in d
            assert "zone_type" in d
            assert "angle_config" in d
            assert "stall_count" in d
