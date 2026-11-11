"""Authenticated FastAPI backend for a shared SafeRoute community feed.

Run locally/LAN for a supervised project demonstration. Do not expose this
prototype directly to the public internet without HTTPS, stronger identity,
rate limiting, moderation/abuse controls, backups and a managed database.
"""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
except ImportError:
    pass

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from database import create_database, get_reports, add_report, update_report_status, update_report_location, get_connection

@asynccontextmanager
async def lifespan(_app):
    create_database()
    yield


app = FastAPI(
    title="SafeRoute Community API",
    version="1.0.0",
    description="Authenticated API for community observations used by SafeRoute clients.",
    lifespan=lifespan,
)
VALID_CATEGORIES = {"Poor Lighting", "Construction", "Blocked Path", "Road Hazard", "Flooding", "Traffic", "Other"}
VALID_STATUSES = {"Reported", "Under Review", "Confirmed", "Resolved", "Dismissed"}


class ReportCreate(BaseModel):
    location: str = Field(min_length=2, max_length=240)
    category: str = Field(min_length=2, max_length=60)
    severity: int = Field(ge=1, le=3)
    description: str = Field(min_length=3, max_length=2000)
    timestamp: Optional[str] = Field(default=None, max_length=32)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    place_id: Optional[str] = Field(default=None, max_length=180)
    location_provider: Optional[str] = Field(default=None, max_length=32)
    author: str = Field(default="Community member", min_length=1, max_length=80)

    @field_validator("category")
    @classmethod
    def category_is_supported(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError("Unsupported report category.")
        return value

    @model_validator(mode="after")
    def coordinates_are_paired(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together.")
        if self.latitude is None or self.longitude is None:
            raise ValueError("A confirmed observation location is required. Select a place or provide map coordinates.")
        return self


class LocationUpdate(BaseModel):
    location: str = Field(min_length=2, max_length=240)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    place_id: Optional[str] = Field(default=None, max_length=180)
    location_provider: Optional[str] = Field(default="manual", max_length=32)


class StatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_is_supported(cls, value: str) -> str:
        if value not in VALID_STATUSES:
            raise ValueError("Unsupported report status.")
        return value


def require_api_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("SAFEROUTE_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is not configured. Set SAFEROUTE_API_TOKEN before starting the API.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    supplied = authorization[7:].strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API token.")


def require_admin_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("SAFEROUTE_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report moderation is not configured on this server.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Moderator bearer token required.")
    supplied = authorization[7:].strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid moderator token.")


@app.get("/health")
def health():
    return {"service": "SafeRoute Community API", "status": "ok"}


@app.get("/reports", dependencies=[Depends(require_api_token)])
def list_reports(include_demo: bool = False, include_inactive: bool = False):
    reports = get_reports(include_demo=include_demo, include_inactive=include_inactive)
    return [
        {
            "id": report.id,
            "location": report.location,
            "category": report.category,
            "severity": report.severity,
            "description": report.description,
            "timestamp": report.timestamp,
            "latitude": report.latitude,
            "longitude": report.longitude,
            "author": report.author,
            "status": report.status,
            "is_demo": report.is_demo,
            "location_status": report.location_status,
            "place_id": report.place_id,
            "location_provider": report.location_provider,
        }
        for report in reports
    ]


@app.post("/reports", status_code=201, dependencies=[Depends(require_api_token)])
def create_report(payload: ReportCreate):
    timestamp = payload.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
    report_id = add_report(
        location=payload.location,
        category=payload.category,
        severity=payload.severity,
        description=payload.description,
        timestamp=timestamp,
        latitude=payload.latitude,
        longitude=payload.longitude,
        author=payload.author,
        place_id=payload.place_id,
        location_provider=payload.location_provider,
        source="shared-api",
    )
    return {"id": report_id, "status": "Reported", "message": "Report received for community review."}


@app.patch("/reports/{report_id}/status", dependencies=[Depends(require_admin_token)])
def set_report_status(report_id: int, payload: StatusUpdate):
    try:
        update_report_status(report_id, payload.status)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"id": report_id, "status": payload.status}


@app.patch("/reports/{report_id}/location", dependencies=[Depends(require_admin_token)])
def set_report_location(report_id: int, payload: LocationUpdate):
    try:
        update_report_location(
            report_id, payload.location, payload.latitude, payload.longitude,
            payload.place_id, payload.location_provider,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"id": report_id, "location_status": "verified"}
