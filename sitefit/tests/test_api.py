"""
tests/test_api.py - API Tests

Comprehensive tests for the SiteFit REST API.
"""

from sitefit.api.app import app
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add sitefit to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# TEST CLIENT
# =============================================================================

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


# =============================================================================
# HEALTH TESTS
# =============================================================================

class TestHealth:
    """Tests for health and root endpoints."""

    def test_root(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SiteFit API"
        assert "version" in data
        assert data["status"] == "running"

    def test_health(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data


# =============================================================================
# PARKING TESTS
# =============================================================================

class TestParking:
    """Tests for parking endpoints."""

    def test_create_parking_layout(self, client):
        """Test parking layout generation."""
        response = client.post("/parking/layout", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 200, "y": 0},
                    {"x": 200, "y": 150},
                    {"x": 0, "y": 150}
                ]
            },
            "stall_angle": 90,
            "stall_type": "standard"
        })
        if response.status_code != 200:
            print("ERROR:", response.json())
        assert response.status_code == 200
        data = response.json()
        assert "total_stalls" in data
        assert "stall_angle" in data
        assert data["stall_angle"] == 90
        assert data["site_area"] == 30000  # 200 x 150

    def test_optimize_parking(self, client):
        """Test parking optimization."""
        response = client.post("/parking/optimize", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 200, "y": 0},
                    {"x": 200, "y": 150},
                    {"x": 0, "y": 150}
                ]
            },
            "angles_to_try": [45, 60, 90]
        })
        assert response.status_code == 200
        data = response.json()
        assert "best_angle" in data
        assert "best_stall_count" in data
        assert "results_by_angle" in data
        assert "optimization_time_ms" in data

    def test_stall_dimensions(self, client):
        """Test stall dimensions endpoint."""
        response = client.get("/parking/stall-dimensions")
        assert response.status_code == 200
        data = response.json()
        assert "standard" in data
        assert "compact" in data
        assert "accessible" in data
        assert data["standard"]["width"] == 9.0
        assert data["standard"]["length"] == 18.0

    def test_efficiency_estimate(self, client):
        """Test parking efficiency estimate."""
        response = client.get(
            "/parking/efficiency-estimate?area_sf=30000&stall_angle=90")
        assert response.status_code == 200
        data = response.json()
        assert "estimated_stalls" in data
        assert "sf_per_stall" in data
        assert data["area_sf"] == 30000


# =============================================================================
# BUILDING TESTS
# =============================================================================

class TestBuilding:
    """Tests for building endpoints."""

    def test_create_massing(self, client):
        """Test building massing generation."""
        response = client.post("/building/massing", json={
            "footprint": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 80},
                    {"x": 0, "y": 80}
                ]
            },
            "floor_count": 5,
            "floor_height": 10.0,
            "floor_type": "residential"
        })
        if response.status_code != 200:
            print("ERROR:", response.json())
        assert response.status_code == 200
        data = response.json()
        assert data["floor_count"] == 5
        # Ground floor is taller (15') + 4 typical floors (4 x 10' = 40') = 55'
        assert data["total_height"] == 55.0
        assert "total_gross_area" in data
        assert "total_net_area" in data
        assert "estimated_units" in data

    def test_unit_mix(self, client):
        """Test unit mix calculation."""
        response = client.post(
            "/building/unit-mix?building_area_sf=50000",
            json={
                "studios": 10,
                "one_br": 40,
                "two_br": 30,
                "three_br": 10
            }
        )
        if response.status_code != 200:
            print("ERROR:", response.json())
        assert response.status_code == 200
        data = response.json()
        assert "total_units" in data
        assert data["total_units"] > 0
        assert "average_unit_size" in data

    def test_floor_types(self, client):
        """Test floor types endpoint."""
        response = client.get("/building/floor-types")
        assert response.status_code == 200
        data = response.json()
        assert "residential" in data
        assert "commercial" in data
        assert "retail" in data
        assert data["residential"]["efficiency"] == 0.85

    def test_efficiency_standards(self, client):
        """Test building efficiency standards."""
        response = client.get("/building/efficiency-standards")
        assert response.status_code == 200
        data = response.json()
        assert "multifamily_garden" in data
        assert "multifamily_highrise" in data


# =============================================================================
# FEASIBILITY TESTS
# =============================================================================

class TestFeasibility:
    """Tests for feasibility endpoints."""

    def test_analyze_site(self, client):
        """Test site feasibility analysis."""
        response = client.post("/feasibility/analyze", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 300, "y": 0},
                    {"x": 300, "y": 200},
                    {"x": 0, "y": 200}
                ]
            },
            "parking_ratio": 1.5,
            "building_coverage": 0.4,
            "floor_count": 5
        })
        assert response.status_code == 200
        data = response.json()
        assert data["site_area"] == 60000  # 300 x 200
        assert "buildable_area" in data
        assert "estimated_units" in data
        assert "required_parking" in data
        assert "provided_parking" in data
        assert "is_compliant" in data
        assert "far" in data

    def test_analyze_with_zoning(self, client):
        """Test feasibility with zoning constraints."""
        response = client.post("/feasibility/analyze", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 200, "y": 0},
                    {"x": 200, "y": 150},
                    {"x": 0, "y": 150}
                ]
            },
            "zoning": {
                "name": "R-4",
                "max_height_ft": 45,
                "max_far": 2.0,
                "max_lot_coverage": 0.5
            },
            "floor_count": 10
        })
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        # With 10 floors at 10' each = 100' height, should exceed 45' limit
        assert "compliance_issues" in data

    def test_optimize_site(self, client):
        """Test site optimization."""
        response = client.post("/feasibility/optimize", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 300, "y": 0},
                    {"x": 300, "y": 200},
                    {"x": 0, "y": 200}
                ]
            },
            "coverage_range": [0.3, 0.5],
            "floor_range": [4, 8],
            "max_configurations": 20
        })
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert "best_configuration" in data
        assert "top_configurations" in data
        assert data["configurations_evaluated"] > 0
        assert data["optimization_time_seconds"] >= 0

    def test_quick_estimate(self, client):
        """Test quick estimate endpoint."""
        response = client.get(
            "/feasibility/quick-estimate"
            "?site_area_sf=60000&floors=5&coverage=0.4&parking_ratio=1.5"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["inputs"]["site_area_sf"] == 60000
        assert "building" in data
        assert "units" in data
        assert "parking" in data
        assert "feasibility" in data


# =============================================================================
# EXPORT TESTS
# =============================================================================

class TestExport:
    """Tests for export endpoints."""

    def test_export_json(self, client):
        """Test JSON export."""
        response = client.post("/export/json", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 80},
                    {"x": 0, "y": 80}
                ]
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "json"
        assert "site" in data

    def test_export_geojson(self, client):
        """Test GeoJSON export."""
        response = client.post("/export/geojson", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 80},
                    {"x": 0, "y": 80}
                ]
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert len(data["features"]) >= 1

    def test_export_dxf(self, client):
        """Test DXF export."""
        response = client.post("/export/dxf", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 80},
                    {"x": 0, "y": 80}
                ]
            }
        })
        assert response.status_code == 200
        assert "LWPOLYLINE" in response.text
        assert "EOF" in response.text

    def test_export_svg(self, client):
        """Test SVG export."""
        response = client.post("/export/svg", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 80},
                    {"x": 0, "y": 80}
                ]
            }
        })
        assert response.status_code == 200
        assert "image/svg+xml" in response.headers["content-type"]
        assert "<svg" in response.text
        assert "<polygon" in response.text

    def test_export_formats(self, client):
        """Test export formats endpoint."""
        response = client.get("/export/formats")
        assert response.status_code == 200
        data = response.json()
        assert "json" in data
        assert "geojson" in data
        assert "dxf" in data
        assert "svg" in data


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_boundary(self, client):
        """Test handling of invalid boundary."""
        response = client.post("/parking/layout", json={
            "site_boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 0, "y": 0},
                    {"x": 0, "y": 0}
                ]
            }
        })
        # Should handle gracefully
        assert response.status_code in [400, 500]

    def test_invalid_area_estimate(self, client):
        """Test invalid area for estimate."""
        response = client.get("/parking/efficiency-estimate?area_sf=-1000")
        assert response.status_code == 400

    def test_invalid_floors(self, client):
        """Test invalid floor count."""
        response = client.get(
            "/feasibility/quick-estimate?site_area_sf=10000&floors=100")
        assert response.status_code == 400
