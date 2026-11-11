import math
import os
import re
import time
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus

import requests


# ============================================================
# PROVIDER CONFIGURATION
# ============================================================

GOOGLE_PLACES_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
GOOGLE_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places"
GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

USER_AGENT = "SafeRoute/1.0 (college-project route safety application)"
GOOGLE_TIMEOUT = 30
OSM_TIMEOUT = 30
NOMINATIM_MIN_INTERVAL = 1.1


# Optional local .env loading; credentials are never read from a Python source file.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
except ImportError:
    pass

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
_requested_provider = os.getenv("SAFEROUTE_MAP_PROVIDER", "osm").strip().lower()
MAP_PROVIDER = _requested_provider if _requested_provider in {"google", "osm", "custom"} else "osm"
OSRM_URL = os.getenv("SAFEROUTE_OSRM_URL", OSRM_URL).strip().rstrip("/")
_DEFAULT_NOMINATIM_URL = NOMINATIM_URL
_DEFAULT_OSRM_URL = OSRM_URL


def configure_provider(provider: str, geocoding_url: str = "", routing_url: str = "") -> dict:
    """Switch map providers at runtime. Custom endpoints must be Nominatim- and OSRM-compatible."""
    global MAP_PROVIDER, NOMINATIM_URL, OSRM_URL, _cache
    provider = str(provider or "osm").strip().lower()
    if provider not in {"osm", "google", "custom"}:
        raise ValueError("Provider must be osm, google, or custom.")
    if provider == "google":
        _require_google_key()
    if provider == "custom":
        geocoding_url = str(geocoding_url or "").strip().rstrip("/")
        routing_url = str(routing_url or "").strip().rstrip("/")
        if not geocoding_url.startswith(("https://", "http://")):
            raise ValueError("Custom geocoding URL must start with http:// or https://")
        if not routing_url.startswith(("https://", "http://")):
            raise ValueError("Custom routing URL must start with http:// or https://")
        NOMINATIM_URL = geocoding_url
        OSRM_URL = routing_url
    else:
        NOMINATIM_URL = _DEFAULT_NOMINATIM_URL
        OSRM_URL = _DEFAULT_OSRM_URL
    MAP_PROVIDER = provider
    _cache.clear()
    return {"provider": MAP_PROVIDER}




_last_nominatim_request = 0.0
_nominatim_lock = threading.Lock()
_cache: Dict[Any, Any] = {}


# ============================================================
# COMMON HELPERS
# ============================================================


def _require_google_key() -> None:
    """Reject missing/template credentials without exposing the configured key."""
    key = str(GOOGLE_MAPS_API_KEY or "").strip()
    invalid_placeholders = {
        "",
        "PASTE_YOUR_GOOGLE_MAPS_API_KEY_HERE",
        "YOUR_GOOGLE_MAPS_API_KEY",
    }
    if key in invalid_placeholders:
        raise RuntimeError(
            "Google Maps is selected, but GOOGLE_MAPS_API_KEY is not configured. "
            "Add it to your private .env file; never commit the key to GitHub."
        )



def _google_headers(field_mask: Optional[str] = None) -> Dict[str, str]:
    _require_google_key()
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
    }
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask
    return headers


def _google_error(response: requests.Response, fallback: str = "request failed") -> str:
    try:
        payload = response.json()
        error = payload.get("error", {})
        message = error.get("message")
        status = error.get("status")
        if message and status:
            return f"{status}: {message}"
        if message:
            return str(message)
    except (ValueError, TypeError):
        pass
    return response.text[:500] or fallback


def new_session_token() -> str:
    return str(uuid.uuid4())


def _normalize_location(location: str) -> str:
    replacements = {
        "trichy": "tiruchirappalli",
        "tiruchy": "tiruchirappalli",
    }
    value = " ".join(str(location).strip().split())
    lowered = value.lower()
    for old, new in replacements.items():
        lowered = lowered.replace(old, new)
    return lowered if lowered != value.lower() else value


def build_search_queries(location: str, context: Optional[str] = None) -> List[str]:
    location = " ".join(str(location).strip().split())
    normalized = _normalize_location(location)
    context = " ".join(str(context or "").strip().split())

    queries: List[str] = []

    def add(value: str) -> None:
        value = " ".join(value.split())
        if value and value not in queries:
            queries.append(value)

    add(location)
    add(normalized)
    if context:
        add(f"{location}, {context}")
        add(f"{normalized}, {context}")
    add(f"{location}, Tamil Nadu, India")
    add(f"{normalized}, Tamil Nadu, India")
    add(f"{location}, India")
    return queries


# ============================================================
# GOOGLE PLACE PARSING
# ============================================================


def _google_place_to_candidate(place: Dict[str, Any]) -> Dict[str, Any]:
    location = place.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None or longitude is None:
        raise ValueError("Google place did not contain coordinates")

    display_name_data = place.get("displayName") or {}
    display_name = display_name_data.get("text") or "Unknown location"
    formatted_address = place.get("formattedAddress") or ""
    types = place.get("types") or []
    primary_type = place.get("primaryType") or (types[0] if types else "Location")

    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "display_name": display_name,
        "formatted_address": formatted_address,
        "category": primary_type,
        "types": types,
        "place_id": place.get("id"),
        "google_place_id": place.get("id"),
        "rating": place.get("rating"),
        "google_maps_uri": place.get("googleMapsUri"),
        "provider": "google",
    }


def _google_prediction_to_candidate(prediction: Dict[str, Any]) -> Dict[str, Any]:
    place = prediction.get("placePrediction") or {}
    text_obj = place.get("text") or {}
    structured = place.get("structuredFormat") or {}

    main_text = (structured.get("mainText") or {}).get("text")
    secondary_text = (structured.get("secondaryText") or {}).get("text")
    display_name = main_text or text_obj.get("text") or "Google location"

    return {
        "display_name": display_name,
        "prediction_text": text_obj.get("text") or display_name,
        "secondary_text": secondary_text or "",
        "place_id": place.get("placeId"),
        "google_place_id": place.get("placeId"),
        "provider": "google",
    }


# ============================================================
# GOOGLE AUTOCOMPLETE (NEW)
# ============================================================


def autocomplete_location_candidates(
    input_text: str,
    session_token: Optional[str] = None,
    location_bias: Optional[Sequence[float]] = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    text_value = " ".join(str(input_text).strip().split())
    if len(text_value) < 2:
        return []

    if MAP_PROVIDER == "osm":
        return _osm_search(text_value, limit=limit)

    _require_google_key()
    token = session_token or new_session_token()

    body: Dict[str, Any] = {
        "input": text_value,
        "sessionToken": token,
        "includedRegionCodes": ["in"],
        "languageCode": "en",
        "includeQueryPredictions": False,
    }

    if location_bias:
        if len(location_bias) != 3:
            raise ValueError("location_bias must be (latitude, longitude, radius_meters)")

        # Google Places Autocomplete circle radius is limited to 50,000 m.
        # Clamp larger caller values instead of sending an invalid request.
        radius_meters = max(1.0, min(float(location_bias[2]), 50_000.0))

        body["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": float(location_bias[0]),
                    "longitude": float(location_bias[1]),
                },
                "radius": radius_meters,
            }
        }

    response = requests.post(
        GOOGLE_PLACES_AUTOCOMPLETE_URL,
        json=body,
        headers=_google_headers(),
        timeout=GOOGLE_TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(
            f"Google Autocomplete failed: {_google_error(response)}"
        )

    suggestions = response.json().get("suggestions") or []
    results: List[Dict[str, Any]] = []
    seen = set()

    for suggestion in suggestions:
        candidate = _google_prediction_to_candidate(suggestion)
        key = candidate.get("place_id") or candidate.get("display_name")
        if key in seen:
            continue
        seen.add(key)
        results.append(candidate)
        if len(results) >= limit:
            break

    return results


# ============================================================
# GOOGLE PLACE DETAILS (NEW)
# ============================================================


def get_place_details(
    place_id: str,
    session_token: Optional[str] = None,
) -> Dict[str, Any]:
    _require_google_key()

    clean_id = str(place_id or "").strip()
    if clean_id.startswith("places/"):
        clean_id = clean_id.split("/", 1)[1]
    if not clean_id:
        raise RuntimeError("Google place selection has no Place ID")

    url = f"{GOOGLE_PLACE_DETAILS_URL}/{quote_plus(clean_id)}"
    params: Dict[str, str] = {}
    if session_token:
        params["sessionToken"] = session_token

    field_mask = (
        "id,displayName,formattedAddress,location,primaryType,types,rating,googleMapsUri"
    )

    response = requests.get(
        url,
        params=params,
        headers=_google_headers(field_mask),
        timeout=GOOGLE_TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(
            f"Google Place Details failed: {_google_error(response)}"
        )

    return _google_place_to_candidate(response.json())


# ============================================================
# GOOGLE TEXT SEARCH (NEW)
# ============================================================


def _google_text_search(
    query: str,
    context: Optional[str] = None,
    limit: int = 6,
    route_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> List[Dict[str, Any]]:
    _require_google_key()

    text_query = " ".join(str(query).strip().split())
    if context:
        clean_context = " ".join(str(context).strip().split())
        if clean_context and clean_context.lower() not in text_query.lower():
            text_query = f"{text_query}, {clean_context}"

    body: Dict[str, Any] = {
        "textQuery": text_query,
        "languageCode": "en",
        "regionCode": "IN",
        "maxResultCount": max(1, min(int(limit), 20)),
    }

    if route_bounds:
        min_lat, min_lon, max_lat, max_lon = route_bounds
        body["locationBias"] = {
            "rectangle": {
                "low": {"latitude": float(min_lat), "longitude": float(min_lon)},
                "high": {"latitude": float(max_lat), "longitude": float(max_lon)},
            }
        }

    field_mask = (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.primaryType,places.types,places.rating,places.googleMapsUri"
    )

    response = requests.post(
        GOOGLE_PLACES_SEARCH_URL,
        json=body,
        headers=_google_headers(field_mask),
        timeout=GOOGLE_TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(
            f"Google Text Search failed: {_google_error(response)}"
        )

    results: List[Dict[str, Any]] = []
    seen = set()
    for place in response.json().get("places") or []:
        try:
            candidate = _google_place_to_candidate(place)
        except (KeyError, TypeError, ValueError):
            continue

        key = (
            round(candidate["latitude"], 6),
            round(candidate["longitude"], 6),
            candidate["display_name"],
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(candidate)

        if len(results) >= limit:
            break

    return results


def search_location_candidates(
    location: str,
    context: Optional[str] = None,
    limit: int = 6,
    route_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> List[Dict[str, Any]]:
    if not str(location).strip():
        return []

    cache_key = (
        MAP_PROVIDER,
        "search",
        str(location).strip().lower(),
        str(context or "").strip().lower(),
        str(route_bounds),
        int(limit),
    )
    if cache_key in _cache:
        return list(_cache[cache_key])

    if MAP_PROVIDER == "google":
        results = _google_text_search(
            location,
            context=context,
            limit=limit,
            route_bounds=route_bounds,
        )
    else:
        results = _osm_search(
            location,
            context=context,
            limit=limit,
            route_bounds=route_bounds,
        )

    _cache[cache_key] = list(results)
    return results


def geocode_location(
    location: str,
    context: Optional[str] = None,
    route_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> Dict[str, Any]:
    results = search_location_candidates(
        location,
        context=context,
        limit=1,
        route_bounds=route_bounds,
    )
    if not results:
        raise RuntimeError(f"Location not found: {location}")
    return results[0]


# ============================================================
# OSM ROLLBACK SEARCH
# ============================================================


def _wait_for_nominatim() -> None:
    """Serialize public Nominatim requests and stay within its usage policy."""
    global _last_nominatim_request
    with _nominatim_lock:
        elapsed = time.monotonic() - _last_nominatim_request
        if elapsed < NOMINATIM_MIN_INTERVAL:
            time.sleep(NOMINATIM_MIN_INTERVAL - elapsed)
        _last_nominatim_request = time.monotonic()


def _osm_result_to_candidate(result: Dict[str, Any]) -> Dict[str, Any]:
    address = result.get("address", {})
    parts: List[str] = []
    for key in ("suburb", "neighbourhood", "city_district", "town", "city", "state"):
        value = address.get(key)
        if value and value not in parts:
            parts.append(value)

    return {
        "latitude": float(result["lat"]),
        "longitude": float(result["lon"]),
        "display_name": result.get("display_name", "Unknown location"),
        "category": result.get("type") or result.get("class") or "Location",
        "area": ", ".join(parts),
        "place_id": result.get("place_id"),
        "provider": "osm",
    }


def _osm_search(
    location: str,
    context: Optional[str] = None,
    limit: int = 6,
    route_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> List[Dict[str, Any]]:
    queries = build_search_queries(location, context)
    last_error: Optional[Exception] = None

    for query_index, query in enumerate(queries):
        params: Dict[str, Any] = {
            "q": query,
            "format": "jsonv2",
            "limit": int(limit),
            "addressdetails": 1,
            "countrycodes": "in",
        }

        if route_bounds is not None:
            params["viewbox"] = (
                f"{route_bounds[1]},{route_bounds[2]},"
                f"{route_bounds[3]},{route_bounds[0]}"
            )
            params["bounded"] = 1 if query_index == 0 else 0

        try:
            _wait_for_nominatim()
            contact_email = os.getenv("SAFEROUTE_CONTACT_EMAIL", "").strip()
            user_agent = USER_AGENT + (f"; contact: {contact_email}" if contact_email else "")
            response = requests.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": user_agent},
                timeout=15,
            )
            response.raise_for_status()
            results = response.json()
            if not results:
                continue

            candidates = []
            seen = set()
            for result in results:
                try:
                    candidate = _osm_result_to_candidate(result)
                except (KeyError, TypeError, ValueError):
                    continue
                key = (
                    round(candidate["latitude"], 6),
                    round(candidate["longitude"], 6),
                    candidate["display_name"],
                )
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    break

            if candidates:
                return candidates
        except requests.RequestException as error:
            last_error = error

    if last_error is not None:
        raise RuntimeError(f"Location search service error: {last_error}")
    return []


# ============================================================
# ROUTE SEGMENTATION
# ============================================================


def build_route_segments(route_points: Sequence[Tuple[float, float]], segment_count: int = 8) -> List[Dict[str, Any]]:
    if not route_points:
        return []

    actual_count = min(segment_count, len(route_points))
    points_per_segment = len(route_points) / actual_count
    segments: List[Dict[str, Any]] = []

    for index in range(actual_count):
        start_index = int(round(index * points_per_segment))
        end_index = int(round((index + 1) * points_per_segment))
        start_index = min(start_index, len(route_points) - 1)
        end_index = min(max(end_index, start_index + 1), len(route_points))
        segment_points = list(route_points[start_index:end_index])
        if not segment_points:
            continue
        segments.append({
            "id": index + 1,
            "name": f"Segment {index + 1}",
            "points": segment_points,
            "midpoint": segment_points[len(segment_points) // 2],
        })

    return segments


# ============================================================
# GOOGLE POLYLINE + DURATION
# ============================================================


def _decode_google_polyline(encoded: str) -> List[Tuple[float, float]]:
    coordinates: List[Tuple[float, float]] = []
    index = 0
    latitude = 0
    longitude = 0

    while index < len(encoded):
        result = 0
        shift = 0
        while True:
            if index >= len(encoded):
                raise ValueError("Invalid Google encoded polyline")
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        delta = -(result >> 1) if result & 1 else result >> 1
        latitude += delta

        result = 0
        shift = 0
        while True:
            if index >= len(encoded):
                raise ValueError("Invalid Google encoded polyline")
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        delta = -(result >> 1) if result & 1 else result >> 1
        longitude += delta

        coordinates.append((latitude / 1e5, longitude / 1e5))

    return coordinates


def _parse_duration_seconds(duration_text: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)s\s*", duration_text or "")
    if not match:
        raise ValueError(f"Unsupported Google route duration: {duration_text}")
    return float(match.group(1))


# ============================================================
# GOOGLE ROUTES API
# ============================================================


def _google_route(
    start_location: Dict[str, Any],
    destination: Dict[str, Any],
    departure_datetime: Optional[Any] = None,
) -> Dict[str, Any]:
    _require_google_key()

    body: Dict[str, Any] = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": float(start_location["latitude"]),
                    "longitude": float(start_location["longitude"]),
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": float(destination["latitude"]),
                    "longitude": float(destination["longitude"]),
                }
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "polylineQuality": "HIGH_QUALITY",
        "polylineEncoding": "ENCODED_POLYLINE",
        "languageCode": "en-US",
        "units": "METRIC",
    }

    if departure_datetime is not None:
        body["departureTime"] = departure_datetime.isoformat(timespec="seconds")

    field_mask = (
        "routes.duration,routes.staticDuration,routes.distanceMeters,"
        "routes.polyline.encodedPolyline"
    )

    response = requests.post(
        GOOGLE_ROUTES_URL,
        json=body,
        headers=_google_headers(field_mask),
        timeout=GOOGLE_TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"Google Routes API failed: {_google_error(response)}")

    routes = response.json().get("routes") or []
    if not routes:
        raise RuntimeError("Google Routes API returned no routes")

    parsed_routes: List[Dict[str, Any]] = []
    for index, route in enumerate(routes[:3]):
        encoded = (route.get("polyline") or {}).get("encodedPolyline")
        if not encoded:
            continue

        points = _decode_google_polyline(encoded)
        if len(points) < 2:
            continue

        duration_seconds = _parse_duration_seconds(route.get("duration", ""))
        static_duration_seconds = _parse_duration_seconds(
            route.get("staticDuration", route.get("duration", ""))
        )
        distance_meters = float(route.get("distanceMeters", 0.0))

        parsed_routes.append({
            "distance_km": round(distance_meters / 1000, 2),
            "duration_min": round(duration_seconds / 60, 1),
            "static_duration_min": round(static_duration_seconds / 60, 1),
            "route_points": points,
            "encoded_polyline": encoded,
            "segments": build_route_segments(points),
            "label": "Recommended" if index == 0 else "Alternative",
        })

    if not parsed_routes:
        raise RuntimeError("Google Routes API returned no usable route geometry")

    primary = parsed_routes[0]
    return {
        **primary,
        "start": start_location,
        "destination": destination,
        "alternatives": parsed_routes[1:],
        "provider": "google",
        "traffic_aware": True,
    }


def _osm_route(start_location: Dict[str, Any], destination: Dict[str, Any]) -> Dict[str, Any]:
    coordinates = (
        f'{start_location["longitude"]},{start_location["latitude"]};'
        f'{destination["longitude"]},{destination["latitude"]}'
    )

    response = requests.get(
        f"{OSRM_URL}/{coordinates}",
        params={"overview": "full", "geometries": "geojson", "steps": "false"},
        headers={"User-Agent": USER_AGENT},
        timeout=OSM_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError("OSRM could not calculate a route")

    route = data["routes"][0]
    points = [
        (float(coord[1]), float(coord[0]))
        for coord in route["geometry"]["coordinates"]
    ]

    return {
        "distance_km": round(route["distance"] / 1000, 2),
        "duration_min": round(route["duration"] / 60, 1),
        "route_points": points,
        "segments": build_route_segments(points),
        "start": start_location,
        "destination": destination,
        "alternatives": [],
        "provider": "osm",
        "traffic_aware": False,
    }


def get_route(
    start_location: Dict[str, Any],
    destination: Dict[str, Any],
    departure_datetime: Optional[Any] = None,
) -> Dict[str, Any]:
    if MAP_PROVIDER == "google":
        return _google_route(start_location, destination, departure_datetime)
    return _osm_route(start_location, destination)


# ============================================================
# GOOGLE SEARCH ALONG ROUTE — SAFETY ASSISTANCE
# ============================================================


def search_places_along_route(
    route_data: Dict[str, Any],
    text_query: str,
    max_result_count: int = 3,
) -> List[Dict[str, Any]]:
    _require_google_key()

    encoded_polyline = route_data.get("encoded_polyline")
    if not encoded_polyline:
        return []

    body = {
        "textQuery": text_query,
        "languageCode": "en",
        "regionCode": "IN",
        "maxResultCount": max(1, min(int(max_result_count), 20)),
        "searchAlongRouteParameters": {
            "polyline": {"encodedPolyline": encoded_polyline}
        },
    }

    field_mask = (
        "places.id,places.displayName,places.formattedAddress,places.location,"
        "places.primaryType,places.types,places.rating,places.googleMapsUri"
    )

    response = requests.post(
        GOOGLE_PLACES_SEARCH_URL,
        json=body,
        headers=_google_headers(field_mask),
        timeout=GOOGLE_TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(
            f"Google route recommendation search failed: {_google_error(response)}"
        )

    results: List[Dict[str, Any]] = []
    for place in response.json().get("places") or []:
        try:
            results.append(_google_place_to_candidate(place))
        except (KeyError, TypeError, ValueError):
            continue
        if len(results) >= max_result_count:
            break
    return results


def get_route_recommendations(route_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    if MAP_PROVIDER != "google":
        return {"Hospital": [], "Police station": [], "Pharmacy": []}

    output: Dict[str, List[Dict[str, Any]]] = {}
    for category, query in (
        ("Hospital", "hospital"),
        ("Police station", "police station"),
        ("Pharmacy", "pharmacy"),
    ):
        try:
            output[category] = search_places_along_route(
                route_data,
                query,
                max_result_count=3,
            )
        except Exception:
            output[category] = []
    return output


# ============================================================
# GOOGLE STATIC MAPS
# ============================================================


def _viewport_for_points(
    route_points: Sequence[Tuple[float, float]],
) -> Tuple[int, float, float]:
    if not route_points:
        return 12, 0.0, 0.0

    min_lat = min(point[0] for point in route_points)
    max_lat = max(point[0] for point in route_points)
    min_lon = min(point[1] for point in route_points)
    max_lon = max(point[1] for point in route_points)

    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    span = max(max_lat - min_lat, max_lon - min_lon)

    if span > 10:
        zoom = 5
    elif span > 5:
        zoom = 6
    elif span > 2.5:
        zoom = 7
    elif span > 1.2:
        zoom = 8
    elif span > 0.6:
        zoom = 9
    elif span > 0.3:
        zoom = 10
    elif span > 0.15:
        zoom = 11
    elif span > 0.075:
        zoom = 12
    elif span > 0.035:
        zoom = 13
    else:
        zoom = 14

    return zoom, center_lat, center_lon


def fetch_google_static_map(
    route_data: Dict[str, Any],
    width: int = 760,
    height: int = 500,
    center: Optional[Tuple[float, float]] = None,
    zoom: Optional[int] = None,
) -> bytes:
    _require_google_key()

    route_points = route_data.get("route_points") or []
    if not route_points:
        raise RuntimeError("No route geometry is available for the Google map")

    if center is None or zoom is None:
        computed_zoom, computed_lat, computed_lon = _viewport_for_points(route_points)
        if center is None:
            center = (computed_lat, computed_lon)
        if zoom is None:
            zoom = computed_zoom

    encoded = route_data.get("encoded_polyline")
    if not encoded:
        raise RuntimeError("Google route did not include an encoded polyline")

    width = max(320, min(int(width), 640))
    height = max(180, min(int(height), 640))
    zoom = max(1, min(int(zoom), 20))

    path = f"weight:6|color:0x22d3ee|enc:{encoded}"
    params = [
        ("size", f"{width}x{height}"),
        ("scale", "2"),
        ("maptype", "roadmap"),
        ("center", f"{center[0]},{center[1]}"),
        ("zoom", str(zoom)),
        ("markers", f"color:green|label:S|{route_data['start']['latitude']},{route_data['start']['longitude']}"),
        ("markers", f"color:red|label:D|{route_data['destination']['latitude']},{route_data['destination']['longitude']}"),
        ("path", path),
        ("key", GOOGLE_MAPS_API_KEY),
    ]

    response = requests.get(
        GOOGLE_STATIC_MAP_URL,
        params=params,
        timeout=GOOGLE_TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(
            f"Google Maps Static API failed: {_google_error(response)}"
        )

    content_type = response.headers.get("content-type", "")
    if "image" not in content_type.lower():
        raise RuntimeError("Google Maps Static API returned a non-image response")

    return response.content


def google_maps_directions_url(
    start_location: Dict[str, Any],
    destination: Dict[str, Any],
) -> str:
    origin = f"{start_location['latitude']},{start_location['longitude']}"
    destination_text = f"{destination['latitude']},{destination['longitude']}"
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(origin)}"
        f"&destination={quote_plus(destination_text)}"
        "&travelmode=driving"
    )
