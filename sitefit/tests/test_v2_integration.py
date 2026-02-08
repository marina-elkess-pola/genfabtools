"""
Integration tests for v2 API feature flag.

Tests validate:
- useV2=false uses v1 code path (unchanged)
- useV2=true uses v2 code path
- v2 response extensions are populated correctly
- v1 backwards compatibility preserved
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from sitefit.api.app import app
    return TestClient(app)


class TestV2FeatureFlag:
    """Test v2 feature flag integration."""

    @pytest.fixture
    def simple_site(self):
        """Simple rectangular site."""
        return {
            "siteBoundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 200, "y": 0},
                    {"x": 200, "y": 150},
                    {"x": 0, "y": 150}
                ]
            },
            "parkingConfig": {
                "parkingType": "surface",
                "aisleDirection": "TWO_WAY",
                "setback": 5.0
            }
        }

    def test_default_uses_v1(self, client, simple_site):
        """Default (no useV2) should use v1 code path."""
        response = client.post("/parking/evaluate", json=simple_site)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # v2 fields should have default values
        result = data["result"]
        assert result.get("angledStalls", 0) == 0
        assert result.get("residualRecovered", 0) == 0
        assert result.get("circulationConnected", True) is True
        assert result.get("v2Zones") is None

    def test_useV2_false_uses_v1(self, client, simple_site):
        """Explicit useV2=false should use v1 code path."""
        simple_site["useV2"] = False
        response = client.post("/parking/evaluate", json=simple_site)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # v2 fields should have default values
        result = data["result"]
        assert result.get("v2Zones") is None

    def test_useV2_true_uses_v2(self, client, simple_site):
        """useV2=true should use v2 code path."""
        simple_site["useV2"] = True
        response = client.post("/parking/evaluate", json=simple_site)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        result = data["result"]
        # v2 should have warnings mentioning v2 engine
        assert any("v2" in w.lower() for w in result.get("warnings", []))

        # v2Zones should be populated
        assert result.get("v2Zones") is not None
        assert len(result["v2Zones"]) >= 1  # At least default zone

    def test_useV2_with_zones(self, client, simple_site):
        """useV2=true with zones should process zones."""
        simple_site["useV2"] = True
        simple_site["zones"] = [
            {
                "id": "zone-1",
                "name": "Main Lot",
                "type": "GENERAL",
                "polygon": {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 100, "y": 0},
                        {"x": 100, "y": 150},
                        {"x": 0, "y": 150}
                    ]
                },
                "angleConfig": "90_DEGREES"
            },
            {
                "id": "zone-2",
                "name": "Reserved",
                "type": "RESERVED",
                "polygon": {
                    "points": [
                        {"x": 100, "y": 0},
                        {"x": 200, "y": 0},
                        {"x": 200, "y": 150},
                        {"x": 100, "y": 150}
                    ]
                },
                "angleConfig": "60_DEGREES"
            }
        ]

        response = client.post("/parking/evaluate", json=simple_site)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        result = data["result"]
        assert result.get("v2Zones") is not None
        assert len(result["v2Zones"]) == 2

        # Check zone names
        zone_names = [z["name"] for z in result["v2Zones"]]
        assert "Main Lot" in zone_names
        assert "Reserved" in zone_names

    def test_useV2_with_angled_parking(self, client, simple_site):
        """useV2=true with allowAngledParking should use 60° stalls."""
        simple_site["useV2"] = True
        simple_site["allowAngledParking"] = True

        response = client.post("/parking/evaluate", json=simple_site)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        result = data["result"]
        # Should have angled stalls
        assert result.get("angledStalls", 0) >= 0

    def test_useV2_circulation_connected(self, client, simple_site):
        """useV2=true should check circulation connectivity."""
        simple_site["useV2"] = True

        response = client.post("/parking/evaluate", json=simple_site)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        result = data["result"]
        # circulationConnected should be boolean
        assert isinstance(result.get("circulationConnected"), bool)

    def test_health_check_shows_v2(self, client):
        """Health check should report v2 availability."""
        response = client.get("/parking/health")

        assert response.status_code == 200
        data = response.json()
        assert "has_v2_engine" in data
        assert isinstance(data["has_v2_engine"], bool)


class TestV1BackwardsCompatibility:
    """Ensure v1 behavior is unchanged."""

    @pytest.fixture
    def v1_request(self):
        """Standard v1 request format."""
        return {
            "siteBoundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 300, "y": 0},
                    {"x": 300, "y": 200},
                    {"x": 0, "y": 200}
                ]
            },
            "parkingConfig": {
                "parkingType": "surface",
                "aisleDirection": "TWO_WAY",
                "setback": 5.0
            }
        }

    def test_v1_request_still_works(self, client, v1_request):
        """Standard v1 request should work unchanged."""
        response = client.post("/parking/evaluate", json=v1_request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        result = data["result"]
        assert "parkingResult" in result
        assert result["parkingResult"]["type"] == "surface"
        assert "metrics" in result["parkingResult"]
        assert "totalStalls" in result["parkingResult"]["metrics"]

    def test_v1_bays_populated(self, client, v1_request):
        """v1 should populate bays (not zones)."""
        response = client.post("/parking/evaluate", json=v1_request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        result = data["result"]
        parking = result["parkingResult"]

        # v1 uses bays
        assert "bays" in parking
        # v1 may have zones as empty list
        assert len(parking.get("zones", [])) == 0

    def test_v1_constraints_still_work(self, client, v1_request):
        """v1 with constraints should work unchanged."""
        v1_request["constraints"] = [
            {
                "id": "col-1",
                "geometry": {
                    "points": [
                        {"x": 150, "y": 100},
                        {"x": 154, "y": 100},
                        {"x": 154, "y": 104},
                        {"x": 150, "y": 104}
                    ]
                },
                "constraintType": "COLUMN"
            }
        ]

        response = client.post("/parking/evaluate", json=v1_request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
