import sqlite3

import database


def test_create_database_and_report_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_NAME", tmp_path / "test.db")
    database.create_database()

    report_id = database.add_report(
        location="Test Road",
        category="Poor Lighting",
        severity=2,
        description="A street light is not working.",
        latitude=10.91,
        longitude=78.72,
        author="Tester",
    )
    reports = database.get_reports()
    assert len(reports) == 1
    assert reports[0].id == report_id
    assert reports[0].author == "Tester"
    assert reports[0].status == "Reported"
    assert reports[0].location_status == "verified"

    database.update_report_location(report_id, "Updated Road", 10.92, 78.73, "place-123", "osm")
    updated = database.get_reports()[0]
    assert updated.location == "Updated Road"
    assert updated.location_status == "verified"
    assert updated.place_id == "place-123"

    database.update_report_status(report_id, "Confirmed")
    assert database.get_reports()[0].status == "Confirmed"
    database.update_report_status(report_id, "Resolved")
    assert database.get_reports() == []
    assert database.get_reports(include_inactive=True)[0].status == "Resolved"


def test_old_database_is_migrated_without_losing_reports(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE community_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            category TEXT NOT NULL,
            severity INTEGER NOT NULL,
            description TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    connection.execute(
        "INSERT INTO community_reports (location, category, severity, description, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("Old Road", "Traffic", 1, "Old record", "2026-10-01 12:30"),
    )
    connection.commit()
    connection.close()

    monkeypatch.setattr(database, "DATABASE_NAME", db_path)
    database.create_database()
    rows = database.get_reports()
    assert len(rows) == 1
    assert rows[0].location == "Old Road"
    assert rows[0].author == "Community member"
    assert rows[0].status == "Reported"
    assert rows[0].location_status == "unverified"


def test_demo_records_are_excluded_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_NAME", tmp_path / "demo.db")
    database.create_database()
    database.add_demo_reports()
    assert database.get_reports() == []
    assert len(database.get_reports(include_demo=True, include_inactive=True)) == 2


def test_profile_preferences_and_saved_journeys(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_NAME", tmp_path / "profile.db")
    database.create_database()
    database.save_profile("Test User", "Central Area", {"share_display_name": False})
    profile = database.get_profile()
    assert profile["display_name"] == "Test User"
    assert profile["home_area"] == "Central Area"
    assert profile["preferences"]["share_display_name"] is False

    journey_id = database.save_journey(
        "Home to Station", "Home", "Station",
        (10.0, 78.0), (10.1, 78.1), 12.5, 25.0,
    )
    journeys = database.get_saved_journeys()
    assert len(journeys) == 1
    assert journeys[0]["id"] == journey_id
    assert journeys[0]["distance_km"] == 12.5
