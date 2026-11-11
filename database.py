"""SQLite persistence for SafeRoute.

The desktop application uses a local SQLite database by default. A shared
community feed is provided separately through community_api.py; local SQLite
files are not automatically shared between different installations.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
except ImportError:
    pass

from models import Incident

BASE_DIR = Path(__file__).resolve().parent
_configured_database_path = os.getenv("SAFEROUTE_DB_PATH", "").strip()
DATABASE_NAME = Path(_configured_database_path).expanduser() if _configured_database_path else BASE_DIR / "saferoute.db"
VALID_REPORT_STATUSES = {"Reported", "Under Review", "Confirmed", "Resolved", "Dismissed"}


@contextmanager
def get_connection():
    DATABASE_NAME.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_NAME), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_database() -> None:
    """Create current tables and safely migrate older SafeRoute databases."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS community_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                category TEXT NOT NULL,
                severity INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 3),
                description TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                location_status TEXT NOT NULL DEFAULT 'unverified',
                place_id TEXT,
                location_provider TEXT,
                author TEXT NOT NULL DEFAULT 'Community member',
                status TEXT NOT NULL DEFAULT 'Reported',
                is_demo INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'local',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        report_columns = {row["name"] for row in connection.execute("PRAGMA table_info(community_reports)")}
        migrations = {
            "latitude": "REAL",
            "longitude": "REAL",
            "location_status": "TEXT NOT NULL DEFAULT 'unverified'",
            "place_id": "TEXT",
            "location_provider": "TEXT",
            "author": "TEXT NOT NULL DEFAULT 'Community member'",
            "status": "TEXT NOT NULL DEFAULT 'Reported'",
            "is_demo": "INTEGER NOT NULL DEFAULT 0",
            "source": "TEXT NOT NULL DEFAULT 'local'",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in report_columns:
                connection.execute(f"ALTER TABLE community_reports ADD COLUMN {column} {definition}")

        connection.execute("""
            UPDATE community_reports
            SET location_status = CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 'verified' ELSE COALESCE(location_status, 'unverified') END,
                created_at = COALESCE(created_at, timestamp),
                updated_at = COALESCE(updated_at, timestamp)
        """)
        # Preserve legacy seed rows but mark the two known tutorial examples as demo data.
        connection.execute("""
            UPDATE community_reports SET is_demo = 1
            WHERE location LIKE 'Segment %'
              AND description IN (
                'Street lights are not working properly',
                'Construction work near the road'
              )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_reports_timestamp ON community_reports(timestamp)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_reports_status_demo ON community_reports(status, is_demo)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_reports_coordinates ON community_reports(latitude, longitude)")

        connection.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                display_name TEXT NOT NULL DEFAULT 'SafeRoute user',
                home_area TEXT NOT NULL DEFAULT '',
                preferences_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            INSERT OR IGNORE INTO user_profile (id, display_name, home_area, preferences_json, updated_at)
            VALUES (1, 'SafeRoute user', '', '{}', ?)
        """, (_utc_now(),))
        connection.execute("""
            CREATE TABLE IF NOT EXISTS saved_journeys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_name TEXT NOT NULL,
                destination_name TEXT NOT NULL,
                start_latitude REAL,
                start_longitude REAL,
                destination_latitude REAL,
                destination_longitude REAL,
                distance_km REAL,
                duration_min REAL,
                created_at TEXT NOT NULL
            )
        """)


def add_report(
    location: str,
    category: str,
    severity: int,
    description: str,
    timestamp: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    author: str = "Community member",
    status: str = "Reported",
    is_demo: bool = False,
    source: str = "local",
    place_id: Optional[str] = None,
    location_provider: Optional[str] = None,
    location_status: Optional[str] = None,
) -> int:
    location = str(location).strip()
    category = str(category).strip()
    description = str(description).strip()
    author = str(author).strip() or "Community member"
    severity = int(severity)
    if not location or not category:
        raise ValueError("Location and category are required.")
    if severity not in (1, 2, 3):
        raise ValueError("Severity must be 1, 2, or 3.")
    if len(description) > 2000:
        raise ValueError("Description must be 2,000 characters or fewer.")
    if (latitude is None) != (longitude is None):
        raise ValueError("Latitude and longitude must be supplied together.")
    if latitude is not None and not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        raise ValueError("Coordinates are outside valid latitude/longitude ranges.")
    location_status = location_status or ("verified" if latitude is not None else "unverified")
    if location_status not in {"verified", "unverified"}:
        raise ValueError("Invalid location verification status.")
    if location_status == "verified" and latitude is None:
        raise ValueError("A verified location must include coordinates.")
    if status not in VALID_REPORT_STATUSES:
        raise ValueError("Invalid report status.")
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
    now = _utc_now()
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO community_reports
            (location, category, severity, description, timestamp, latitude, longitude,
             location_status, place_id, location_provider, author, status, is_demo, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            location, category, severity, description, timestamp, latitude, longitude,
            location_status, place_id, location_provider, author, status, int(is_demo), source, now, now,
        ))
        return int(cursor.lastrowid)


def _row_to_incident(row: sqlite3.Row) -> Incident:
    return Incident(
        id=row["id"],
        location=row["location"],
        category=row["category"],
        severity=int(row["severity"]),
        description=row["description"] or "",
        timestamp=row["timestamp"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        location_status=row["location_status"] or "unverified",
        place_id=row["place_id"],
        location_provider=row["location_provider"],
        author=row["author"] or "Community member",
        status=row["status"] or "Reported",
        is_demo=bool(row["is_demo"]),
    )


def get_reports(include_demo: bool = False, include_inactive: bool = False) -> list[Incident]:
    clauses = []
    params: list[Any] = []
    if not include_demo:
        clauses.append("is_demo = 0")
    if not include_inactive:
        clauses.append("status NOT IN ('Resolved', 'Dismissed')")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM community_reports" + where + " ORDER BY timestamp DESC, id DESC",
            params,
        ).fetchall()
    return [_row_to_incident(row) for row in rows]


def get_report_by_id(report_id: int) -> Optional[Incident]:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM community_reports WHERE id = ?", (int(report_id),)).fetchone()
    return _row_to_incident(row) if row else None


def update_report_status(report_id: int, status: str) -> None:
    if status not in VALID_REPORT_STATUSES:
        raise ValueError("Invalid report status.")
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE community_reports SET status = ?, updated_at = ? WHERE id = ? AND is_demo = 0",
            (status, _utc_now(), int(report_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError("Report not found or is demo data.")


def update_report_location(
    report_id: int, location: str, latitude: float, longitude: float,
    place_id: Optional[str] = None, location_provider: Optional[str] = None,
) -> None:
    location = str(location).strip()
    latitude, longitude = float(latitude), float(longitude)
    if not location:
        raise ValueError("A place name or location description is required.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates are outside valid latitude/longitude ranges.")
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE community_reports SET location = ?, latitude = ?, longitude = ?, "
            "location_status = 'verified', place_id = ?, location_provider = ?, updated_at = ? "
            "WHERE id = ? AND is_demo = 0",
            (location, latitude, longitude, place_id, location_provider or "manual", _utc_now(), int(report_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError("Report not found or is demo data.")


def add_demo_reports() -> None:
    """Insert clearly labelled demonstration rows; never called automatically by the app."""
    examples = [
        ("Demo location A", "Poor Lighting", 2, "DEMO ONLY: example report about an unlit street.", "2026-09-02 20:00"),
        ("Demo location B", "Construction", 2, "DEMO ONLY: example report about road construction.", "2026-09-02 20:30"),
    ]
    with get_connection() as connection:
        for location, category, severity, description, timestamp in examples:
            connection.execute("""
                INSERT INTO community_reports
                (location, category, severity, description, timestamp, author, status, is_demo, source, created_at, updated_at)
                SELECT ?, ?, ?, ?, ?, 'SafeRoute demo', 'Reported', 1, 'demo', ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM community_reports WHERE is_demo = 1 AND location = ? AND description = ?
                )
            """, (location, category, severity, description, timestamp, _utc_now(), _utc_now(), location, description))


def get_profile() -> dict[str, Any]:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if not row:
        return {"display_name": "SafeRoute user", "home_area": "", "preferences": {}}
    try:
        preferences = json.loads(row["preferences_json"] or "{}")
    except json.JSONDecodeError:
        preferences = {}
    return {
        "display_name": row["display_name"],
        "home_area": row["home_area"],
        "preferences": preferences if isinstance(preferences, dict) else {},
        "updated_at": row["updated_at"],
    }


def save_profile(display_name: str, home_area: str = "", preferences: Optional[dict] = None) -> None:
    display_name = str(display_name).strip()
    home_area = str(home_area).strip()
    if not display_name or len(display_name) > 80:
        raise ValueError("Display name must contain 1–80 characters.")
    if len(home_area) > 160:
        raise ValueError("Home area must be 160 characters or fewer.")
    preferences = preferences or {}
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO user_profile (id, display_name, home_area, preferences_json, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                home_area = excluded.home_area,
                preferences_json = excluded.preferences_json,
                updated_at = excluded.updated_at
        """, (display_name, home_area, json.dumps(preferences), _utc_now()))


def save_journey(
    name: str,
    start_name: str,
    destination_name: str,
    start_coordinates: Optional[tuple] = None,
    destination_coordinates: Optional[tuple] = None,
    distance_km: Optional[float] = None,
    duration_min: Optional[float] = None,
) -> int:
    if not str(name).strip() or not str(start_name).strip() or not str(destination_name).strip():
        raise ValueError("Journey name, start and destination are required.")
    start_coordinates = start_coordinates or (None, None)
    destination_coordinates = destination_coordinates or (None, None)
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO saved_journeys
            (name, start_name, destination_name, start_latitude, start_longitude,
             destination_latitude, destination_longitude, distance_km, duration_min, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(name).strip()[:100], str(start_name).strip(), str(destination_name).strip(),
            start_coordinates[0], start_coordinates[1], destination_coordinates[0], destination_coordinates[1],
            distance_km, duration_min, _utc_now(),
        ))
        return int(cursor.lastrowid)


def get_saved_journeys() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM saved_journeys ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def delete_saved_journey(journey_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM saved_journeys WHERE id = ?", (int(journey_id),))


def count_reports_by_author(author: str) -> int:
    with get_connection() as connection:
        return int(connection.execute(
            "SELECT COUNT(*) FROM community_reports WHERE author = ? AND is_demo = 0",
            (author,),
        ).fetchone()[0])
