"""Community data service with local SQLite or a shared authenticated API.

Set SAFEROUTE_API_URL and SAFEROUTE_API_TOKEN in .env to use a shared server.
When SAFEROUTE_API_URL is empty, the client uses this computer's SQLite file.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)
except ImportError:
    pass

from database import add_report, get_reports as get_local_reports
from models import Incident

API_URL = os.getenv("SAFEROUTE_API_URL", "").strip().rstrip("/")
API_TOKEN = os.getenv("SAFEROUTE_API_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("SAFEROUTE_ADMIN_TOKEN", "").strip()
API_TIMEOUT = float(os.getenv("SAFEROUTE_API_TIMEOUT", "12"))


class CommunityService:
    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None):
        self.api_url = (API_URL if api_url is None else api_url).strip().rstrip("/")
        self.api_token = API_TOKEN if api_token is None else api_token.strip()

    @property
    def is_shared(self) -> bool:
        return bool(self.api_url)

    def _headers(self) -> dict[str, str]:
        if self.is_shared and not self.api_token:
            raise RuntimeError(
                "A shared SafeRoute API URL is configured, but SAFEROUTE_API_TOKEN is missing. "
                "Set the same access token on the API server and desktop client."
            )
        return {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}

    def _request(self, method: str, path: str, **kwargs):
        if not self.is_shared:
            raise RuntimeError("Shared API is not configured.")
        url = urljoin(self.api_url + "/", path.lstrip("/"))
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                timeout=API_TIMEOUT,
                **kwargs,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        except requests.RequestException as error:
            detail = ""
            if getattr(error, "response", None) is not None:
                detail = f" (HTTP {error.response.status_code}: {error.response.text[:250]})"
            raise RuntimeError(
                f"SafeRoute shared community service is unavailable: {error}{detail}. "
                "The app did not silently save a local copy, because that would split the feed."
            ) from error

    @staticmethod
    def _to_incident(item: dict[str, Any]) -> Incident:
        return Incident(
            id=item.get("id"),
            location=item.get("location", "Unknown location"),
            category=item.get("category", "Other"),
            severity=int(item.get("severity", 1)),
            description=item.get("description", ""),
            timestamp=item.get("timestamp", ""),
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            author=item.get("author", "Community member"),
            status=item.get("status", "Reported"),
            is_demo=bool(item.get("is_demo", False)),
            location_status=item.get("location_status", "verified" if item.get("latitude") is not None and item.get("longitude") is not None else "unverified"),
            place_id=item.get("place_id"),
            location_provider=item.get("location_provider"),
        )

    def get_reports(self, include_demo: bool = False, include_inactive: bool = False) -> list[Incident]:
        if not self.is_shared:
            return get_local_reports(include_demo=include_demo, include_inactive=include_inactive)
        data = self._request(
            "GET", "/reports",
            params={"include_demo": str(bool(include_demo)).lower(), "include_inactive": str(bool(include_inactive)).lower()},
        )
        return [self._to_incident(item) for item in (data or [])]

    def submit_report(
        self,
        location: str,
        category: str,
        severity: int,
        description: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        author: str = "Community member",
        place_id: Optional[str] = None,
        location_provider: Optional[str] = None,
    ) -> Optional[int]:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        payload = {
            "location": str(location).strip(),
            "category": str(category).strip(),
            "severity": int(severity),
            "description": str(description).strip(),
            "timestamp": timestamp,
            "latitude": latitude,
            "longitude": longitude,
            "author": str(author).strip() or "Community member",
            "place_id": place_id,
            "location_provider": location_provider or ("manual" if latitude is not None else None),
        }
        if self.is_shared:
            result = self._request("POST", "/reports", json=payload)
            return int(result["id"]) if result and result.get("id") else None
        return add_report(**payload)

    def update_status(self, report_id: int, status: str) -> None:
        if not self.is_shared:
            from database import update_report_status
            update_report_status(report_id, status)
            return
        if not ADMIN_TOKEN:
            raise RuntimeError("SAFEROUTE_ADMIN_TOKEN is required for moderation changes.")
        url = urljoin(self.api_url + "/", f"reports/{int(report_id)}/status")
        try:
            response = requests.patch(
                url, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                json={"status": status}, timeout=API_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(f"Could not update community report status: {error}") from error

    def update_report_location(
        self, report_id: int, location: str, latitude: float, longitude: float,
        place_id: Optional[str] = None, location_provider: Optional[str] = None,
    ) -> None:
        if not self.is_shared:
            from database import update_report_location
            update_report_location(report_id, location, latitude, longitude, place_id, location_provider)
            return
        if not ADMIN_TOKEN:
            raise RuntimeError("SAFEROUTE_ADMIN_TOKEN is required to verify an existing shared observation location.")
        url = urljoin(self.api_url + "/", f"reports/{int(report_id)}/location")
        try:
            response = requests.patch(
                url, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                json={"location": location, "latitude": latitude, "longitude": longitude,
                      "place_id": place_id, "location_provider": location_provider or "manual"},
                timeout=API_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(f"Could not verify community report location: {error}") from error

    def filter_near_location(self, reports: list[Incident], center: tuple[float, float], radius_km: float = 5.0) -> list[Incident]:
        """Return geotagged observations within radius_km of a chosen home-area point."""
        from math import asin, cos, radians, sin, sqrt

        def distance_km(point):
            lat1, lon1 = center
            lat2, lon2 = point
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return 6371.0 * 2 * asin(sqrt(min(1.0, value)))

        result = []
        for report in reports:
            if report.latitude is None or report.longitude is None:
                continue
            distance = distance_km((report.latitude, report.longitude))
            if distance <= radius_km:
                report.matched_distance_km = distance
                result.append(report)
        return result

    def filter_along_route(self, reports: list[Incident], route_points: list[tuple], radius_km: float = 0.75) -> list[Incident]:
        """Return geotagged reports within radius_km of any route point."""
        if not route_points:
            return []

        def haversine(a, b):
            from math import asin, cos, radians, sin, sqrt
            lat1, lon1 = a
            lat2, lon2 = b
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return 6371.0 * 2 * asin(sqrt(min(1.0, value)))

        filtered = []
        # Sample long routes to keep filtering responsive while preserving spatial coverage.
        stride = max(1, len(route_points) // 250)
        sampled_points = route_points[::stride]
        if sampled_points[-1] != route_points[-1]:
            sampled_points.append(route_points[-1])
        for report in reports:
            if report.latitude is None or report.longitude is None:
                continue
            distance = min(
                haversine((report.latitude, report.longitude), point)
                for point in sampled_points
            )
            if distance <= radius_km:
                report.matched_distance_km = distance
                filtered.append(report)
        return filtered


community_service = CommunityService()
