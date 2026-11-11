from models import Incident, Route
from safety_engine import SafetyAnalyzer
from location_intelligence import LocationIntelligence


def build_route():
    points = [(10.0, 78.0), (10.0, 78.01)]
    return Route(
        "Polyline test", 1.1, 4.0,
        [{"id": 1, "name": "Segment 1", "points": points}],
        points,
    )


def test_observation_matches_polyline_between_vertices():
    # Both route vertices are over 500 m away, but the observation is about 55 m
    # from the line between them. Vertex-only distance matching misses this.
    report = Incident(
        location="Main Road", category="Poor Lighting", severity=2,
        description="Streetlight is out", timestamp="2026-11-10 20:00",
        latitude=10.0005, longitude=78.005,
    )
    analyzer = SafetyAnalyzer([report])
    match = analyzer.find_closest_segment(report, build_route())
    assert match is not None
    assert match[0]["name"] == "Segment 1"
    assert 0.04 < match[1] < 0.07


def test_unlocated_free_text_is_not_assigned_to_a_route():
    report = Incident(
        location="Near central bus stand", category="Traffic", severity=2,
        description="Heavy traffic", timestamp="2026-11-10 18:00",
    )
    assert SafetyAnalyzer([report]).find_relevant_reports(build_route()) == []


def test_far_away_coordinates_are_not_overridden_by_segment_text():
    report = Incident(
        location="Segment 1", category="Road Hazard", severity=3,
        description="Unrelated far away report", timestamp="2026-11-10 18:00",
        latitude=10.02, longitude=78.005,
    )
    assert SafetyAnalyzer([report]).find_relevant_reports(build_route()) == []


def test_legacy_explicit_segment_label_remains_compatible():
    report = Incident(
        location="Segment 1", category="Construction", severity=1,
        description="Legacy sample", timestamp="2026-11-10 18:00",
    )
    relevant = SafetyAnalyzer([report]).find_relevant_reports(build_route())
    assert relevant == [report]
    assert report.match_method == "legacy_segment_label"


def test_location_coverage_is_explicit():
    reports = [
        Incident("A", "Traffic", 1, "Located", "2026-11-10 18:00", 10.0005, 78.005),
        Incident("B", "Traffic", 1, "No coordinates", "2026-11-10 18:00"),
    ]
    relevant = SafetyAnalyzer(reports).find_relevant_reports(build_route())
    coverage = LocationIntelligence().coverage(reports, relevant)
    assert coverage["total_observations"] == 2
    assert coverage["geotagged_observations"] == 1
    assert coverage["matched_geotagged_observations"] == 1
    assert coverage["unverified_locations"] == 1
