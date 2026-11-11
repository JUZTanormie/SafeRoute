from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import map_service

if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT))

    import map_service


    print("SafeRoute optional Google Maps diagnostic")
    print("--------------------------------")
    print(f"Provider: {map_service.MAP_PROVIDER}")
    print(
        "API key configured:",
        bool(map_service.GOOGLE_MAPS_API_KEY)
        and "PASTE_YOUR_GOOGLE_MAPS_API_KEY_HERE" not in map_service.GOOGLE_MAPS_API_KEY,
    )

    if map_service.MAP_PROVIDER != "google":
        print("ERROR: Set SAFEROUTE_MAP_PROVIDER=google in your private .env first.")
        print("Do not store API keys in source files.")
        raise SystemExit(1)

    autocomplete_token = map_service.new_session_token()

    try:
        suggestions = map_service.autocomplete_location_candidates(
            "SRMIST Tiruchirappalli",
            session_token=autocomplete_token,
            location_bias=(10.7905, 78.7047, 50000),
            limit=5,
        )
        print(f"Autocomplete: OK ({len(suggestions)} result(s))")
        for item in suggestions[:5]:
            print("  -", item.get("display_name"))
    except Exception as error:
        print("Autocomplete: FAILED")
        print(" ", error)
        raise SystemExit(2)

    try:
        places = map_service.search_location_candidates(
            "SRMIST Tiruchirappalli",
            context="Tamil Nadu, India",
            limit=5,
        )
        destination_candidates = map_service.search_location_candidates(
            "Thanjavur New Bus Stand",
            context="Tamil Nadu, India",
            limit=5,
        )
        print(f"Text Search: OK ({len(places)} + {len(destination_candidates)} result(s))")
    except Exception as error:
        print("Text Search: FAILED")
        print(" ", error)
        raise SystemExit(3)

    if not suggestions:
        print("No Autocomplete suggestion was returned, so Place Details cannot be tested.")
        raise SystemExit(4)

    try:
        prediction = suggestions[0]
        details = map_service.get_place_details(
            prediction["place_id"],
            session_token=autocomplete_token,
        )
        print("Place Details: OK")
        print("  -", details.get("display_name"))
        print("  -", details.get("formatted_address"))
        print(
            "  - coordinates:",
            details.get("latitude"),
            details.get("longitude"),
        )
    except Exception as error:
        print("Place Details: FAILED")
        print(" ", error)
        raise SystemExit(5)

    try:
        start_place = details
        destination_place = destination_candidates[0]
        route = map_service.get_route(
            start_place,
            destination_place,
        )
        print("Routes API: OK")
        print("  - distance:", route["distance_km"], "km")
        print("  - duration:", route["duration_min"], "min")
        print("  - alternatives:", len(route.get("alternatives", [])))
    except Exception as error:
        print("Routes API: FAILED")
        print(" ", error)
        raise SystemExit(6)

    try:
        image_bytes = map_service.fetch_google_static_map(route)
        output = ROOT / "google_route_test.png"
        output.write_bytes(image_bytes)
        print("Maps Static API: OK")
        print("  - saved:", output)
    except Exception as error:
        print("Maps Static API: FAILED")
        print(" ", error)
        raise SystemExit(7)

    try:
        recommendations = map_service.get_route_recommendations(route)
        print("Route recommendations: OK")
        for category, items in recommendations.items():
            print(f"  - {category}: {len(items)}")
    except Exception as error:
        print("Route recommendations: FAILED")
        print(" ", error)
        raise SystemExit(8)

    print("\nALL GOOGLE SERVICES PASSED.")
