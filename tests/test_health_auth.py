from fastapi.testclient import TestClient

from app.main import app
from app.services.bootstrap import init_database


def test_health_and_login_flow():
    init_database()
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] in {"ok", "degraded"}

    denied = client.get("/api/v1/assets/summary")
    assert denied.status_code == 401

    login = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@gridsense.example", "password": "ChangeMeNow!23"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
