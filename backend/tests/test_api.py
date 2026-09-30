from datetime import datetime

from fastapi.testclient import TestClient

from conftest import RecordingLink
from main import create_app


def test_delivery_publishes_contract_payload(client, link):
    r = client.post("/delivery", json={"order_id": "ORD-001", "destination": "room_a"})
    assert r.status_code == 200
    assert r.json() == {"status": "queued", "order_id": "ORD-001"}
    assert link.published == [{"order_id": "ORD-001", "destination": "room_a"}]


def test_delivery_generates_order_id_when_missing(client, link):
    first = client.post("/delivery", json={"destination": "kitchen"}).json()
    second = client.post("/delivery", json={"destination": "dock"}).json()
    assert first["order_id"] == "ORD-001"
    assert second["order_id"] == "ORD-002"
    assert [p["order_id"] for p in link.published] == ["ORD-001", "ORD-002"]


def test_unknown_destination_is_rejected_and_not_published(client, link):
    r = client.post("/delivery", json={"order_id": "ORD-001", "destination": "roof"})
    assert r.status_code == 422
    assert "roof" in r.json()["detail"]
    assert link.published == []


def test_empty_order_id_is_rejected(client, link):
    r = client.post("/delivery", json={"order_id": "", "destination": "room_a"})
    assert r.status_code == 422
    assert link.published == []


def test_delivery_returns_503_when_rosbridge_down(settings):
    down = RecordingLink(connected=False)
    with TestClient(create_app(settings, down)) as c:
        r = c.post("/delivery", json={"order_id": "ORD-001", "destination": "room_a"})
    assert r.status_code == 503
    assert down.published == []


def test_status_defaults_before_first_message(client):
    body = client.get("/robot/status").json()
    assert body == {
        "state": "UNKNOWN",
        "battery": None,
        "current_order": None,
        "last_update": None,
        "connected": True,
    }


def test_status_reflects_robot_status_topic(client, link):
    link.status.update_from_json('{"state": "NAVIGATING", "battery": 85.0, "current_order": "ORD-001"}')
    body = client.get("/robot/status").json()
    assert body["state"] == "NAVIGATING"
    assert body["battery"] == 85.0
    assert body["current_order"] == "ORD-001"
    assert datetime.fromisoformat(body["last_update"])


def test_destinations_and_health(client):
    assert client.get("/destinations").json() == {
        "destinations": ["dock", "kitchen", "room_a", "room_b"]
    }
    assert client.get("/health").json() == {"api": "ok", "rosbridge": "connected", "mode": "ros"}


def test_health_reports_disconnected(settings):
    with TestClient(create_app(settings, RecordingLink(connected=False))) as c:
        assert c.get("/health").json()["rosbridge"] == "disconnected"


def test_cors_allows_react_dev_server(client):
    r = client.options(
        "/delivery",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
