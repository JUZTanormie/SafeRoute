"""Geographical matching and coverage analysis for community observations.

Coordinates are treated as the source of truth for route matching. Text labels
are not geocoded heuristically by the safety scorer. The sole text fallback is
an explicit legacy segment label such as ``Segment 2`` used by old demo data.
"""
from __future__ import annotations

import os
from math import cos, radians, sqrt
from typing import Any, Iterable, Optional

EARTH_KM_PER_DEG_LAT = 110.574
EARTH_KM_PER_DEG_LON = 111.320


def _point_to_segment_distance_km(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    """Approximate short-distance point-to-segment distance in a local tangent plane."""
    lat, lon = float(point[0]), float(point[1])
    mean_lat = radians((float(start[0]) + float(end[0]) + lat) / 3.0)
    lon_scale = EARTH_KM_PER_DEG_LON * max(0.01, abs(cos(mean_lat)))

    ax = (float(start[1]) - lon) * lon_scale
    ay = (float(start[0]) - lat) * EARTH_KM_PER_DEG_LAT
    bx = (float(end[1]) - lon) * lon_scale
    by = (float(end[0]) - lat) * EARTH_KM_PER_DEG_LAT

    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-12:
        return sqrt(ax * ax + ay * ay)

    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / length_squared))
    nearest_x, nearest_y = ax + t * dx, ay + t * dy
    return sqrt(nearest_x * nearest_x + nearest_y * nearest_y)


class LocationIntelligence:
    """Match observations to route geometry and report data-coverage quality."""

    def __init__(self, match_radius_km: Optional[float] = None):
        configured = match_radius_km
        if configured is None:
            try:
                configured = float(os.getenv("SAFEROUTE_OBSERVATION_MATCH_RADIUS_KM", "0.30"))
            except ValueError:
                configured = 0.30
        self.match_radius_km = max(0.05, min(float(configured), 2.0))

    @staticmethod
    def _segment_points(segment: dict[str, Any]) -> list[tuple[float, float]]:
        points = []
        for item in segment.get("points") or []:
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return points

    def closest_segment(self, latitude: float, longitude: float, segments: Iterable[dict[str, Any]]) -> Optional[tuple[dict[str, Any], float]]:
        observation = (float(latitude), float(longitude))
        best_segment: Optional[dict[str, Any]] = None
        best_distance = float("inf")

        for segment in segments:
            points = self._segment_points(segment)
            if not points:
                continue
            if len(points) == 1:
                distance = _point_to_segment_distance_km(observation, points[0], points[0])
                best_distance = min(best_distance, distance)
                if best_distance == distance:
                    best_segment = segment
                continue
            for index in range(len(points) - 1):
                distance = _point_to_segment_distance_km(observation, points[index], points[index + 1])
                if distance < best_distance:
                    best_distance = distance
                    best_segment = segment

        if best_segment is None or best_distance > self.match_radius_km:
            return None
        return best_segment, round(best_distance, 4)

    def match_observations(self, reports: list[Any], route: Any) -> list[Any]:
        matched: list[Any] = []
        segments = route.segments or []
        for report in reports:
            report.matched_segment = None
            report.matched_distance_km = None
            report.match_method = None
            has_coordinates = report.latitude is not None and report.longitude is not None

            if has_coordinates:
                match = self.closest_segment(report.latitude, report.longitude, segments)
                if match:
                    report.matched_segment = match[0].get("name", "Route segment")
                    report.matched_distance_km = match[1]
                    report.match_method = "coordinates"
                    matched.append(report)
                # A geotagged observation outside the corridor must not be pulled
                # onto the route merely because its text resembles a segment label.
                continue

            # Preserve only the explicit legacy demo convention. Arbitrary text
            # such as a landmark or street name is never treated as coordinates.
            legacy_location = str(getattr(report, "location", "")).strip().casefold()
            for segment in segments:
                segment_name = str(segment.get("name", "")).strip()
                if segment_name and legacy_location == segment_name.casefold():
                    report.matched_segment = segment_name
                    report.matched_distance_km = 0.0
                    report.match_method = "legacy_segment_label"
                    matched.append(report)
                    break
        return matched

    def coverage(self, reports: list[Any], matched_reports: list[Any]) -> dict[str, Any]:
        total = len(reports)
        geotagged = sum(r.latitude is not None and r.longitude is not None for r in reports)
        matched = len(matched_reports)
        matched_geotagged = sum(getattr(r, "match_method", None) == "coordinates" for r in matched_reports)
        legacy_matched = sum(getattr(r, "match_method", None) == "legacy_segment_label" for r in matched_reports)
        return {
            "total_observations": total,
            "geotagged_observations": geotagged,
            "matched_observations": matched,
            "matched_geotagged_observations": matched_geotagged,
            "legacy_segment_matches": legacy_matched,
            "unverified_locations": total - geotagged,
            "unmatched_geotagged_observations": max(0, geotagged - matched_geotagged),
            "match_radius_m": int(round(self.match_radius_km * 1000)),
        }


location_intelligence = LocationIntelligence()
