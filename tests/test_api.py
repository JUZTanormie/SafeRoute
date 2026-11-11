import os

from fastapi.testclient import TestClient

import community_api
import database


def test_shared_api_auth_report_submission_and_moderation(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_NAME", tmp_path / "api-test.db")
    monkeypatch.setenv("SAFEROUTE_API_TOKEN", "client-test-token")
    monkeypatch.setenv("SAFEROUTE_ADMIN_TOKEN", "admin-test-token")

    with TestClient(community_api.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/reports").status_code == 401

        client_headers = {"Authorization": "Bearer client-test-token"}
        payload = {
            "location": "Test Area",
            "category": "Traffic",
            "severity": 2,
            "description": "Traffic observed near the junction.",
            "latitude": 10.9,
            "longitude": 78.7,
            "author": "API Tester",
        }
        created = client.post("/reports", json=payload, headers=client_headers)
        assert created.status_code == 201
        report_id = created.json()["id"]

        listing = client.get("/reports", headers=client_headers)
        assert listing.status_code == 200
        assert len(listing.json()) == 1
        assert listing.json()[0]["status"] == "Reported"

        # The client token cannot moderate report status.
        denied = client.patch(
            f"/reports/{report_id}/status",
            json={"status": "Confirmed"},
            headers=client_headers,
        )
        assert denied.status_code == 403

        admin_headers = {"Authorization": "Bearer admin-test-token"}
        approved = client.patch(
            f"/reports/{report_id}/status",
            json={"status": "Confirmed"},
            headers=admin_headers,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "Confirmed"
