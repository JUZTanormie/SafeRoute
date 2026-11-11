PRAGMA foreign_keys = ON;

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
);

CREATE INDEX IF NOT EXISTS idx_reports_timestamp ON community_reports(timestamp);
CREATE INDEX IF NOT EXISTS idx_reports_status_demo ON community_reports(status, is_demo);
CREATE INDEX IF NOT EXISTS idx_reports_coordinates ON community_reports(latitude, longitude);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    display_name TEXT NOT NULL DEFAULT 'SafeRoute user',
    home_area TEXT NOT NULL DEFAULT '',
    preferences_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

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
);
