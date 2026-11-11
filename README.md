# SafeRoute — Community-Powered Journey Safety
## BY BATCH-6 SAFE ROUTE TEAM
  UNDER THE COURSE OF ADVANCED PROGRAMMING PRACTICE (APP)
## TEAM MEMBERS :
- ANANTA NARAYANAN.V - RA2511003050317
- NIVASH S - RA2511003050316
- BALASUBRAMANIAM S B - RA2511003050313
- SANJAY S - RA2511003050323

SafeRoute is a Python desktop application prototype that combines route planning, community-submitted observations, geographical location intelligence, and explainable journey-risk analysis. It uses a Python backend with an embedded web interface. OpenStreetMap is the default provider; Google Maps Platform and compatible custom/local map services are optional.

> **Important safety limitation:** SafeRoute is an information aid, not a guarantee that a route is safe. Community reports may be incomplete, inaccurate, outdated, or unverified. No matching reports means insufficient information—not proof of safety. The machine-learning risk indicator is experimental and must not be used as a standalone safety decision.

## Features and implemented modules

- **Journey planning:** place search, route retrieval, route geometry and departure-time selection.
- **Map providers:** OpenStreetMap/OSRM by default, optional Google Maps Platform, and configurable Nominatim-/OSRM-compatible geocoding/routing plus XYZ tile endpoints.
- **Map display:** provider switching, roadmap/satellite/terrain/hybrid Google map styles where supported, and map lifecycle/loading recovery.
- **Community observations:** report submission, categories, severity, descriptions, moderation statuses, feed filters and local profile contributions.
- **Location Intelligence:** geocoded observation locations, manual map-pin selection, coordinate persistence, legacy-report location resolution, and route-polyline proximity matching.
- **Safety analysis:** time-aware deterministic concern scoring, route hotspots, report recency/severity/category handling and data-coverage indicators.
- **NLP:** TF-IDF / logistic-regression utilities for report categorisation and similarity support. NLP does not invent geographical coordinates.
- **Experimental ML:** Random Forest route-risk indicator based on prototype training data; supplementary only.
- **Journey briefing:** contextual journey summary and route intelligence.
- **Persistence:** SQLite database with migration support, SQL schema and optional demo seed script.
- **Optional shared community API:** FastAPI service for a shared feed across installations; local-only mode is the default.

## Repository structure

```text
SafeRoute/
├── main.py                      # Desktop application launcher
├── hybrid_app.py                # Local Python/web bridge and API endpoints
├── map_service.py               # OSM, Google and custom map provider services
├── location_intelligence.py     # Geocoding/location and spatial matching helpers
├── database.py                  # SQLite persistence and migrations
├── models.py                    # Data models
├── safety_engine.py             # Explainable safety concern scoring
├── report_ai.py                 # NLP report analysis utilities
├── risk_model.py                # Experimental ML risk indicator
├── route_intelligence.py        # Route-level analysis and hotspots
├── journey_briefing.py          # Journey briefing generation
├── community_service.py         # Community report service
├── community_api.py             # Optional FastAPI shared service
├── route_data.json              # Local route/demo data
├── web/                         # HTML, CSS and JavaScript UI
├── sql/                         # Schema and optional demo seed SQL
├── tests/                       # Automated tests
├── scripts/                     # Diagnostics and helper scripts
├── screenshots/                 # Application screenshots
├── docs/                        # UI and implementation notes
├── requirements.txt
├── requirements-dev.txt
├── .env.example                 # Safe configuration template
└── .gitignore
```

## Requirements

- Windows 10/11, macOS or Linux.
- Python 3.10+ (use a version supported by the installed scientific packages).
- Internet connection for public OSM geocoding/routing and map tiles.
- On Windows, Microsoft Edge WebView2 Runtime is recommended for the embedded desktop window. If `pywebview` cannot initialise, the launcher can fall back to the default browser.

## Installation and run (Windows PowerShell)

```powershell
# Clone the repository
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd SafeRoute

# Create and activate a virtual environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create your private local configuration
Copy-Item .env.example .env

# Launch
python main.py
```

The app creates `saferoute.db` on first launch. Runtime databases and local settings are intentionally excluded from Git. Existing database files can be retained locally; do not upload personal/community data without permission.

## Configuration

### OpenStreetMap (default)

No API key is required. `.env.example` defaults to `SAFEROUTE_MAP_PROVIDER=osm`. Public Nominatim and OSRM services are best-effort demonstration services, not production SLAs. Respect Nominatim usage policy and retain visible OpenStreetMap attribution. For sustained usage, configure self-hosted or managed services.

### Google Maps Platform (optional)

1. Create and restrict the required Google Maps Platform keys in Google Cloud Console.
2. Enable the APIs required by the enabled SafeRoute features and configure billing/quotas as required by Google.
3. Add keys to your **private `.env` file only**:

```dotenv
SAFEROUTE_MAP_PROVIDER=google
GOOGLE_MAPS_API_KEY=your_server_restricted_key
GOOGLE_MAPS_BROWSER_API_KEY=your_browser_restricted_key
```

The browser key should be restricted to the local app origins and Maps JavaScript API; the server key should be restricted to the relevant APIs and appropriate application restrictions. Do not paste keys into source files, screenshots, issues, README files or commits. If a key has ever been committed or publicly shared, revoke it and create a replacement.

### Custom/self-hosted map services

Use the Settings page to configure compatible geocoding, routing and XYZ tile endpoints. Follow the relevant provider's authentication, attribution, rate-limit and licensing requirements.

### Optional shared community API

Local-only SQLite mode is the default; separate installations do **not** automatically share reports. For a supervised demo, configure a trusted FastAPI host and set `SAFEROUTE_API_URL`, `SAFEROUTE_API_TOKEN`, and server-side `SAFEROUTE_ADMIN_TOKEN` in private environment files. See `docs/` and `community_api.py` for endpoint details. Do not expose this student prototype directly to the public internet without HTTPS, proper authentication/authorization, rate limiting, moderation, privacy controls, backups and monitoring.

## Location Intelligence and matching

New community observations should have a confirmed place/coordinate selection. Users can search for a place or drop a map pin. Older reports without coordinates are retained and marked as requiring location confirmation; they are not silently assigned to a route based on ambiguous text. Journey analysis compares geotagged reports to route-segment polylines using point-to-segment distance. The default corridor is 300 metres and can be adjusted with `SAFEROUTE_OBSERVATION_MATCH_RADIUS_KM` (supported range 0.05–2 km). Text/NLP analysis helps understand report content; it does not determine exact coordinates.

## Database and SQL scripts

- `sql/schema.sql` — database schema.
- `sql/seed_demo_data.sql` — optional, clearly labelled demo data.
- `database.py` — SQLite initialisation and migrations.

Demo seed data is optional. Do not use fabricated/demo observations as real incident evidence.

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

The automated suite is designed to run offline and should not require live Google, Nominatim or OSRM calls. Google service diagnostics are separate and may incur Google Maps Platform charges:

```powershell
python scripts/diagnose_google_services.py
```

## Screenshots

See [`screenshots/`](screenshots/) for application captures. Some supplied captures show empty states; they document the UI, not a completed live route analysis. For final academic submission, capture fresh screenshots from the running application showing: (1) journey planner with a calculated route, (2) safety results and data coverage, (3) community report with confirmed map location, (4) advanced analysis/hotspots, and (5) provider/time settings. Ensure no API keys, tokens, private addresses or personal report details are visible.

## Limitations and responsible use

- Safety scores are heuristic outputs based on available reports, not validated crime/safety predictions.
- Community observations are not independently verified by the software. Moderation statuses require human review.
- Experimental ML is trained on prototype data and is not production-validated.
- Map/route services may be unavailable, rate-limited, inaccurate or lack live traffic.
- A route with few or no reports must not be described as safe. Display data coverage and uncertainty alongside every score.
- The prototype is not an emergency service. In an emergency, contact local emergency services.

## Attribution

OpenStreetMap data is © OpenStreetMap contributors and is available under the Open Database License. Retain required attribution. Google Maps Platform services are subject to Google's terms, usage limits and billing policies. Third-party services retain their own licenses and terms.

## Academic project note

This repository contains the source code, database scripts, dependency manifests, screenshots and execution instructions for the SafeRoute academic project. Update this section with your institution, team members, guide, course and final submission details before publishing.

