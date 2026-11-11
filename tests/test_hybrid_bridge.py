from fastapi.testclient import TestClient

import database
import hybrid_app
import map_service
from models import Incident


def test_hybrid_ui_and_settings_endpoints():
    client = TestClient(hybrid_app.app)
    assert client.get('/').status_code == 200
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert response.json()['provider'] in {'osm', 'google', 'custom'}


def test_custom_provider_requires_compatible_urls():
    original = map_service.MAP_PROVIDER
    try:
        result = map_service.configure_provider(
            'custom',
            'http://127.0.0.1:8080/search',
            'http://127.0.0.1:5000/route/v1/driving',
        )
        assert result['provider'] == 'custom'
        assert map_service.NOMINATIM_URL.endswith('/search')
        assert map_service.OSRM_URL.endswith('/route/v1/driving')
    finally:
        map_service.configure_provider('osm')


def test_location_search_endpoint_uses_active_provider(monkeypatch):
    expected = [{"latitude": 10.9, "longitude": 78.7, "display_name": "Central Bus Stand", "provider": "osm"}]
    monkeypatch.setattr(map_service, "search_location_candidates", lambda q, context=None, limit=6: expected)
    response = TestClient(hybrid_app.app).get("/api/location-search", params={"q": "Central Bus Stand"})
    assert response.status_code == 200
    assert response.json() == expected


def test_old_observation_location_can_be_resolved_in_desktop_api(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_NAME", tmp_path / "location-resolution.db")
    database.create_database()
    report_id = database.add_report(
        location="Near railway station", category="Poor Lighting", severity=2,
        description="Older report without coordinates", timestamp="2026-11-01 19:00",
    )
    client = TestClient(hybrid_app.app)
    response = client.patch(
        f"/api/reports/{report_id}/location",
        json={"location": "Madurai Railway Junction", "latitude": 9.9195, "longitude": 78.1193,
              "place_id": "test-place", "location_provider": "osm"},
    )
    assert response.status_code == 200
    saved = database.get_reports(include_inactive=True)[0]
    assert saved.location_status == "verified"
    assert saved.latitude == 9.9195
    assert saved.longitude == 78.1193


def test_new_observation_requires_confirmed_coordinates(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_NAME", tmp_path / "new-report-location.db")
    database.create_database()
    client = TestClient(hybrid_app.app)
    payload = {"location": "Central Bus Stand", "category": "Poor Lighting", "severity": 2,
               "description": "Streetlights are not working near the entrance."}
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 400
    payload.update({"latitude": 9.9252, "longitude": 78.1198, "location_provider": "manual"})
    saved = client.post("/api/reports", json=payload)
    assert saved.status_code == 200
    assert database.get_reports()[0].location_status == "verified"


def test_journey_response_exposes_location_coverage(monkeypatch):
    monkeypatch.setattr(map_service, "geocode_location", lambda name: {
        "latitude": 10.0 if name == "Start Place" else 10.0,
        "longitude": 78.0 if name == "Start Place" else 78.01,
        "display_name": name,
    })
    route_points = [(10.0, 78.0), (10.0, 78.01)]
    monkeypatch.setattr(map_service, "get_route", lambda start, end, departure=None: {
        "distance_km": 1.1, "duration_min": 4.0, "route_points": route_points,
        "segments": [{"id": 1, "name": "Segment 1", "points": route_points}],
        "provider": "osm", "traffic_aware": False, "alternatives": [],
    })
    located = Incident("Main Road", "Poor Lighting", 2, "Lamp out", "2026-11-10 20:00", 10.0005, 78.005)
    unlocated = Incident("Near bus stand", "Traffic", 1, "Slow traffic", "2026-11-10 18:00")
    monkeypatch.setattr(hybrid_app.community_service, "get_reports", lambda **kwargs: [located, unlocated])
    response = TestClient(hybrid_app.app).post("/api/journey", json={
        "origin": "Start Place", "destination": "End Place", "departure": "Now"
    })
    assert response.status_code == 200, response.text
    coverage = response.json()["location_coverage"]
    assert coverage["total_observations"] == 2
    assert coverage["geotagged_observations"] == 1
    assert coverage["matched_geotagged_observations"] == 1
    assert coverage["unverified_locations"] == 1
    assert response.json()["report_count"] == 1
