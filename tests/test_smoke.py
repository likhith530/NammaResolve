from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_create_and_read_complaint():
    with TestClient(app) as client:
        create_response = client.post(
            "/api/complaints",
            json={
                "category": "garbage",
                "description": "Garbage has not been collected for three days.",
                "area": "Kalyan Nagar",
                "landmark": "Near 5th Main Road",
            },
        )
        assert create_response.status_code == 201
        complaint = create_response.json()
        assert complaint["complaint_id"].startswith("NM-")
        assert complaint["status"] == "RECEIVED"

        read_response = client.get(f"/api/complaints/{complaint['complaint_id']}")
        assert read_response.status_code == 200
        assert read_response.json()["complaint_id"] == complaint["complaint_id"]
