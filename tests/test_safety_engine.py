from models import Incident, Route
from safety_engine import SafetyAnalyzer


def test_distance_and_route_segment_matching():
    analyzer = SafetyAnalyzer([])
    route = Route(
        "Test route", 2.0, 5.0,
        [{"id": 1, "name": "Segment 1", "points": [(10.0, 78.0), (10.01, 78.01)]}],
        [(10.0, 78.0), (10.01, 78.01)],
    )
    report = Incident("Test Road", "Poor Lighting", 2, "Light out", "2026-10-01 18:00", 10.0001, 78.0001)
    match = analyzer.find_closest_segment(report, route)
    assert match is not None
    assert match[0]["name"] == "Segment 1"
    assert match[1] < 0.1
