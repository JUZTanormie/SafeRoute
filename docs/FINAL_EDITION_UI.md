# SafeRoute Final Edition — Hybrid UI

## Architecture

- Python remains responsible for routing, geocoding, community persistence, NLP, the experimental Random Forest indicator, rule-based safety scoring, briefing and hotspot analysis.
- `hybrid_app.py` exposes a loopback-only FastAPI bridge on `127.0.0.1:8765`.
- `web/` contains the responsive dark desktop interface.
- `pywebview` embeds the local web interface in a native desktop window. If pywebview is unavailable, the launcher opens the same local interface in the default browser.
- The previous Tkinter UI is preserved in `legacy_main.py` as a fallback/reference.

## Map providers

Settings supports:

1. **OpenStreetMap** — Nominatim-compatible geocoding, OSRM routing and OSM raster tiles.
2. **Google Maps Platform** — Google Places/Routes through the Python service and Google Maps JavaScript API for the interactive browser map.
3. **Custom / Local** — Nominatim-compatible geocoding endpoint, OSRM-compatible routing endpoint, and an optional `{z}/{x}/{y}` raster tile template. This supports self-hosted services and compatible custom providers.

Custom geocoding endpoint should accept Nominatim-style search requests and return Nominatim-style JSON. Custom routing endpoint should use the OSRM route URL pattern and return OSRM-compatible GeoJSON responses. Custom tile URL must be a standard XYZ template. Respect each provider's terms, attribution and rate limits.

Google roadmap/satellite/terrain/hybrid map styles are exposed when the Google Maps JavaScript API is enabled. The tilt control requests a 45-degree perspective in Satellite/Hybrid where Google supports it; it is not a photorealistic 3D city renderer. A dedicated Google 3D Maps integration would require the separate Maps 3D API/library and additional implementation. OSM/custom map tilt is not advertised as available unless the selected tile/rendering service supports it.

## Google key security

- Keep `GOOGLE_MAPS_API_KEY` in the private `.env` file only.
- Use separate Google credentials for server and browser use. `GOOGLE_MAPS_API_KEY` is the server key used by Places/Routes requests; restrict it to the required APIs and an appropriate server-side application restriction. `GOOGLE_MAPS_BROWSER_API_KEY` is delivered to the local loopback UI only when Google is selected; restrict it to `http://127.0.0.1:8765/*` and `http://localhost:8765/*` and the Maps JavaScript API. Do not reuse a browser-referrer-restricted key for server-side REST calls.
- Never commit `.env`, credentials, or database files. Review `.gitignore` before publishing.

## Run

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python main.py
```

The local bridge binds only to `127.0.0.1`; it is not a public server. Community sharing remains dependent on a separately hosted/configured SafeRoute community API as documented in README.md.

## Limitations and verification

- Live route calculation and map tiles require network access and compatible provider configuration.
- Google map styles require Maps JavaScript API enablement and a correctly restricted key.
- Custom services must implement the documented compatible request/response formats.
- OSM public services are best-effort and do not provide live traffic. Self-host or use a contracted provider for dependable production use.
- The Random Forest indicator is experimental and based on prototype training data. It is not a validated real-world safety prediction.
- SafeRoute presents community context and cannot guarantee route safety.
