# SafeRoute final major update — implementation notes

## Added and changed

- OSM is now the default map provider; Google Maps remains an opt-in provider using a private environment variable.
- Location lookup on the OSM path is manual-search-only. Public Nominatim calls are rate-spaced and identify the SafeRoute client in the User-Agent.
- The route and report-preview screens now use the interactive `tkintermapview` OSM component when the dependency is installed.
- The data model now includes community author, report moderation status, demo-data marker, source, and created/updated timestamps.
- Existing SQLite databases are migrated in place and retain their existing report rows.
- New local tables store a single-device profile/preferences and saved journeys.
- The Communities page supports category filtering, recent reports, nearby-to-home filtering (5 km), along-current-route filtering (750 m), geotagged submissions, and visible report statuses.
- The Profile page supports a display name, optional home area, optional public display-name sharing, report count, and saved journeys.
- `community_service.py` routes community reads/writes to local SQLite by default or to a configured shared API. API failures are surfaced instead of silently forking the feed.
- `community_api.py` exposes an authenticated FastAPI service. Report creation/listing uses the client token; report status changes use a separate moderator token.
- Added SQL schema and clearly labelled demo seed data, dependency files, `.env.example`, `.gitignore`, tests, and setup documentation.

## Important limitations

- Shared reports are shared only when a real API server is running and every client points to that same server. The delivered project does not include a hosted backend.
- The FastAPI service is a supervised prototype. Do not expose it publicly without HTTPS, stronger user identity/permissions, rate limiting, moderation/abuse controls, backups, and production hosting.
- User profiles and saved journeys remain local to each desktop installation; this is not a multi-user account system.
- The OSM/OSRM public endpoints are best-effort and do not provide live traffic. Use a managed/self-hosted service for production traffic or availability guarantees.
- The `tkintermapview` package is declared in `requirements.txt` but could not be installed in this build environment because outbound package-network access was unavailable. The GUI pages and map-widget call path were smoke-tested with an interface stub; install the requirements and verify live tile loading on the target Windows PC.
- Genuine Tkinter page captures are included for Journey Planner, Communities, Profile, Safety Results empty state, and Advanced Analysis empty state. The target Windows PC still needs populated journey/result captures and a live interactive OSM map screenshot after dependencies and external map services are verified.
- The rule-based safety score remains a heuristic. The Random Forest model remains an experimental prototype trained on prototype/synthetic examples.
