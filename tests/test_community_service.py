from community_service import CommunityService
from models import Incident


def test_along_route_filter_keeps_only_nearby_geotagged_reports():
    service = CommunityService(api_url="", api_token="")
    reports = [
        Incident("Near", "Poor Lighting", 2, "Near report", "2026-10-01 18:00", 10.0, 78.0),
        Incident("Far", "Traffic", 1, "Far report", "2026-10-01 18:00", 11.0, 79.0),
        Incident("No coordinates", "Other", 1, "No point", "2026-10-01 18:00"),
    ]
    result = service.filter_along_route(reports, [(10.0, 78.0), (10.01, 78.01)], radius_km=0.75)
    assert [item.location for item in result] == ["Near"]
    assert result[0].matched_distance_km is not None


def test_near_home_filter_uses_radius_and_skips_missing_coordinates():
    service = CommunityService(api_url="", api_token="")
    reports = [
        Incident("Near", "Traffic", 1, "Near home", "2026-10-01 18:00", 10.0, 78.0),
        Incident("Far", "Other", 1, "Far away", "2026-10-01 18:00", 12.0, 80.0),
        Incident("No point", "Other", 1, "No coordinates", "2026-10-01 18:00"),
    ]
    result = service.filter_near_location(reports, (10.0, 78.0), radius_km=5.0)
    assert [item.location for item in result] == ["Near"]
    assert result[0].matched_distance_km == 0.0
