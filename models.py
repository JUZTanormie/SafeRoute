"""Domain models used by SafeRoute."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Incident:
    location: str
    category: str
    severity: int
    description: str
    timestamp: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    id: Optional[int] = None
    author: str = "Community member"
    status: str = "Reported"
    is_demo: bool = False
    location_status: str = "unverified"
    place_id: Optional[str] = None
    location_provider: Optional[str] = None
    matched_segment: Optional[str] = None
    matched_distance_km: Optional[float] = None
    match_method: Optional[str] = None


@dataclass
class Route:
    name: str
    distance: float
    estimated_time: float
    segments: list
    route_points: Optional[list] = None
    start_coordinates: Optional[tuple] = None
    destination_coordinates: Optional[tuple] = None

    def __post_init__(self):
        if self.route_points is None:
            self.route_points = []
