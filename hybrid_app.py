"""SafeRoute hybrid desktop launcher: FastAPI local bridge + pywebview UI."""
from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn

import map_service
from database import (
    create_database, get_profile, save_profile, save_journey,
    get_saved_journeys, delete_saved_journey, count_reports_by_author,
)
from community_service import community_service
from models import Route
from safety_engine import SafetyAnalyzer
from report_ai import ReportIntelligence
from risk_model import SafetyRiskModel
from journey_briefing import JourneyBriefingEngine
from route_intelligence import RouteIntelligence
from location_intelligence import location_intelligence

BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
SETTINGS_FILE = BASE / "settings.json"
GOOGLE_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

create_database()
report_ai = ReportIntelligence()
risk_model = SafetyRiskModel()
briefing_engine = JourneyBriefingEngine()
route_intelligence = RouteIntelligence()


def read_settings():
    defaults = {
        "provider": map_service.MAP_PROVIDER,
        "custom_geocoding_url": "",
        "custom_routing_url": "",
        "custom_tile_url": "",
        "map_style": "roadmap",
        "view_mode": "basic",
        "motion": True,
    }
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            defaults.update({k: v for k, v in saved.items() if k in defaults})
    except (OSError, json.JSONDecodeError):
        pass
    return defaults


def write_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


settings = read_settings()
try:
    map_service.configure_provider(
        settings["provider"], settings.get("custom_geocoding_url", ""),
        settings.get("custom_routing_url", "")
    )
except Exception:
    settings["provider"] = "osm"
    map_service.configure_provider("osm")

app = FastAPI(title="SafeRoute Desktop Bridge", docs_url=None, redoc_url=None)


class ProviderSettings(BaseModel):
    provider: str = "osm"
    custom_geocoding_url: str = ""
    custom_routing_url: str = ""
    custom_tile_url: str = ""
    map_style: str = "roadmap"
    view_mode: str = "basic"
    motion: bool = True


class JourneyRequest(BaseModel):
    origin: str = Field(min_length=2, max_length=180)
    destination: str = Field(min_length=2, max_length=180)
    departure: str = "Now"


class ReportRequest(BaseModel):
    location: str = Field(min_length=2, max_length=180)
    category: str = "Other"
    severity: int = Field(default=2, ge=1, le=3)
    description: str = Field(min_length=5, max_length=1200)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    place_id: Optional[str] = Field(default=None, max_length=180)
    location_provider: Optional[str] = Field(default=None, max_length=32)


class LocationResolutionRequest(BaseModel):
    location: str = Field(min_length=2, max_length=240)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    place_id: Optional[str] = Field(default=None, max_length=180)
    location_provider: Optional[str] = Field(default="manual", max_length=32)


class ProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    home_area: str = Field(default="", max_length=160)
    preferences: dict = {}


def incident_json(item):
    return {
        "id": item.id, "location": item.location, "category": item.category,
        "severity": item.severity, "description": item.description,
        "timestamp": item.timestamp, "latitude": item.latitude,
        "longitude": item.longitude, "author": item.author,
        "status": item.status, "is_demo": item.is_demo,
        "location_status": item.location_status, "place_id": item.place_id,
        "location_provider": item.location_provider,
        "matched_segment": item.matched_segment,
        "matched_distance_km": item.matched_distance_km,
        "match_method": item.match_method,
    }


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/assets/{asset}")
def assets(asset: str):
    path = (WEB / asset).resolve()
    if WEB.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(path)


@app.get("/api/bootstrap")
def bootstrap():
    profile = get_profile()
    reports = community_service.get_reports(include_demo=False, include_inactive=False)
    saved = get_saved_journeys()
    return {
        "settings": {**settings, "google_key_available": bool(GOOGLE_KEY)},
        "profile": profile,
        "reports": [incident_json(r) for r in reports[:30]],
        "saved_journeys": saved[:12],
        "report_count": len(reports),
        "shared_community": community_service.is_shared,
    }


@app.get("/api/settings")
def get_settings():
    return {**settings, "google_key_available": bool(GOOGLE_KEY)}


@app.get("/api/map-key")
def map_key():
    if map_service.MAP_PROVIDER != "google" or not GOOGLE_KEY:
        return {"key": ""}
    return {"key": GOOGLE_KEY}


@app.put("/api/settings")
def update_settings(payload: ProviderSettings):
    global settings
    candidate = payload.model_dump()
    try:
        map_service.configure_provider(
            candidate["provider"], candidate["custom_geocoding_url"],
            candidate["custom_routing_url"]
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))
    settings = candidate
    write_settings(settings)
    return {**settings, "google_key_available": bool(GOOGLE_KEY)}


@app.get("/api/search")
def search(q: str):
    if len(q.strip()) < 2:
        return []
    try:
        return map_service.search_location_candidates(q, limit=6)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/location-search")
def location_search(q: str, context: Optional[str] = None):
    query = str(q or "").strip()
    if len(query) < 2:
        return []
    try:
        return map_service.search_location_candidates(query, context=context, limit=6)
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.post("/api/journey")
def plan_journey(payload: JourneyRequest):
    try:
        start = map_service.geocode_location(payload.origin)
        end = map_service.geocode_location(payload.destination)
        departure_dt = None
        journey_time = datetime.now().strftime("%I:%M %p")
        if payload.departure and payload.departure != "Now":
            if payload.departure in {"morning", "afternoon", "evening", "night"}:
                hour_map = {"morning": 8, "afternoon": 14, "evening": 18, "night": 22}
                departure_dt = datetime.now().replace(hour=hour_map[payload.departure], minute=0, second=0, microsecond=0)
            else:
                departure_dt = datetime.fromisoformat(payload.departure)
            journey_time = departure_dt.strftime("%I:%M %p")
        route_data = map_service.get_route(start, end, departure_dt)
        route = Route(
            name=f"{payload.origin} to {payload.destination}",
            distance=route_data["distance_km"],
            estimated_time=route_data["duration_min"],
            segments=route_data["segments"],
            route_points=route_data["route_points"],
            start_coordinates=(start["latitude"], start["longitude"]),
            destination_coordinates=(end["latitude"], end["longitude"]),
        )
        reports = community_service.get_reports(include_demo=False, include_inactive=False)
        hour = (departure_dt or datetime.now()).hour
        analyzer = SafetyAnalyzer(reports, journey_hour=hour)
        relevant = analyzer.find_relevant_reports(route)
        score = min(10.0, analyzer.calculate_score(relevant))
        assessment = analyzer.get_assessment(score)
        confidence = analyzer.get_confidence(relevant)
        location_coverage = location_intelligence.coverage(reports, relevant)
        ml = risk_model.explain_route_risk(relevant, hour)
        intelligence = route_intelligence.analyze(relevant, analyzer)
        briefing = briefing_engine.generate(
            relevant, score, assessment, confidence, ml["risk"], ml["factors"],
            journey_time, "Night" if hour < 5 or hour >= 21 else "Evening" if hour >= 16 else "Daytime",
            route_data["distance_km"], route_data["duration_min"]
        )
        result = {
            "origin": start, "destination": end,
            "distance_km": route_data["distance_km"],
            "duration_min": route_data["duration_min"],
            "route_points": route_data["route_points"],
            "provider": route_data.get("provider", map_service.MAP_PROVIDER),
            "traffic_aware": route_data.get("traffic_aware", False),
            "alternatives": route_data.get("alternatives", []),
            "score": score, "assessment": assessment, "confidence": confidence,
            "ml_risk": ml["risk"], "ml_factors": ml["factors"],
            "briefing": briefing, "hotspots": intelligence.get("hotspots", []),
            "reports": [incident_json(r) for r in relevant],
            "report_count": len(relevant),
            "location_coverage": location_coverage,
        }
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/reports")
def list_reports():
    try:
        reports = community_service.get_reports(include_demo=False, include_inactive=False)
        return [incident_json(r) for r in reports]
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/report-suggestion")
def report_suggestion(description: str):
    if len(description.strip()) < 5:
        return {"category": "Other", "confidence": 0.0, "severity": 1}
    suggestion = report_ai.predict_category(description)
    suggestion["severity"] = report_ai.suggest_severity(description)
    return suggestion


@app.post("/api/reports")
def submit_report(payload: ReportRequest):
    try:
        if payload.latitude is None or payload.longitude is None:
            raise HTTPException(400, "Confirm the observation location from the suggestions or place a pin on the map before submitting.")
        profile = get_profile()
        preferences = profile.get("preferences", {})
        author = profile.get("display_name", "Community member") if preferences.get("share_display_name", True) else "Anonymous contributor"
        report_id = community_service.submit_report(
            payload.location, payload.category, payload.severity,
            payload.description, payload.latitude, payload.longitude, author,
            payload.place_id, payload.location_provider
        )
        return {"success": True, "id": report_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.patch("/api/reports/{report_id}/location")
def verify_report_location(report_id: int, payload: LocationResolutionRequest):
    try:
        community_service.update_report_location(
            report_id, payload.location, payload.latitude, payload.longitude,
            payload.place_id, payload.location_provider,
        )
        return {"success": True, "id": report_id, "location_status": "verified"}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/profile")
def profile():
    data = get_profile()
    data["contributions"] = count_reports_by_author(data.get("display_name", ""))
    data["saved_journeys"] = get_saved_journeys()
    return data


@app.put("/api/profile")
def update_profile(payload: ProfileRequest):
    save_profile(payload.display_name, payload.home_area, payload.preferences)
    return profile()


@app.post("/api/journeys/save")
def save_current_journey(payload: dict):
    try:
        journey_id = save_journey(
            payload.get("name") or f"{payload.get('origin', 'Journey')} → {payload.get('destination', '')}",
            payload["origin"], payload["destination"],
            tuple(payload["start_coordinates"]), tuple(payload["destination_coordinates"]),
            payload.get("distance_km"), payload.get("duration_min")
        )
        return {"success": True, "id": journey_id}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/journeys/{journey_id}")
def remove_journey(journey_id: int):
    delete_saved_journey(journey_id)
    return {"success": True}


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning", access_log=False)


def main():
    server = threading.Thread(target=run_server, daemon=True)
    server.start()
    for _ in range(50):
        try:
            import requests
            if requests.get("http://127.0.0.1:8765/api/settings", timeout=0.3).ok:
                break
        except Exception:
            time.sleep(0.1)
    try:
        import webview
        webview.create_window(
            "SafeRoute | Journey Intelligence", "http://127.0.0.1:8765",
            width=1500, height=940, min_size=(1120, 720), background_color="#0b1018"
        )
        webview.start()
    except ImportError:
        print("pywebview is not installed. Opening SafeRoute in your default browser.")
        webbrowser.open("http://127.0.0.1:8765")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
