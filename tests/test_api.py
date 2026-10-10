"""End-to-end API tests through FastAPI's TestClient.

The clock is a mutable callable so we can jump forward past 30s without any
real sleep.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.store import DeviceStore


class FakeClock:
    """Minimal mutable clock — call `advance(seconds)` to move time forward."""
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def client(clock: FakeClock) -> TestClient:
    return TestClient(create_app(store=DeviceStore(), clock=clock))


def test_register_device(client: TestClient):
    r = client.post("/devices", json={"id": "d1", "name": "Lab 1"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "d1"
    # No heartbeat yet → OFFLINE out of the gate.
    assert body["status"] == "OFFLINE"
    assert body["last_heartbeat"] is None


def test_duplicate_registration_returns_409(client: TestClient):
    client.post("/devices", json={"id": "d1", "name": "Lab 1"})
    r = client.post("/devices", json={"id": "d1", "name": "Dup"})
    assert r.status_code == 409


def test_heartbeat_for_unknown_device_returns_404(client: TestClient):
    r = client.post("/devices/ghost/heartbeat", json={"status": "OK"})
    assert r.status_code == 404


def test_get_unknown_device_returns_404(client: TestClient):
    r = client.get("/devices/ghost")
    assert r.status_code == 404


def test_malformed_payload_returns_422(client: TestClient):
    # Missing required `name`.
    r = client.post("/devices", json={"id": "d1"})
    assert r.status_code == 422


def test_heartbeat_flips_device_online(client: TestClient, clock: FakeClock):
    client.post("/devices", json={"id": "d1", "name": "Lab 1"})
    r = client.post("/devices/d1/heartbeat", json={"status": "OK", "cpu_usage": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ONLINE"
    assert body["reported_status"] == "OK"
    assert body["cpu_usage"] == 42


def test_device_goes_offline_after_30s(client: TestClient, clock: FakeClock):
    client.post("/devices", json={"id": "d1", "name": "Lab 1"})
    client.post("/devices/d1/heartbeat", json={"status": "OK"})

    # Right at the boundary — still ONLINE.
    clock.advance(30)
    assert client.get("/devices/d1").json()["status"] == "ONLINE"

    # One second later — OFFLINE.
    clock.advance(1)
    assert client.get("/devices/d1").json()["status"] == "OFFLINE"


def test_summary_counts(client: TestClient, clock: FakeClock):
    for i in range(1, 4):
        client.post("/devices", json={"id": f"d{i}", "name": f"Lab {i}"})
    client.post("/devices/d1/heartbeat", json={"status": "OK"})
    client.post("/devices/d2/heartbeat", json={"status": "OK"})

    # d3 never heartbeated.
    assert client.get("/summary").json() == {"total": 3, "online": 2, "offline": 1}

    # Age d1 and d2 past the timeout.
    clock.advance(31)
    assert client.get("/summary").json() == {"total": 3, "online": 0, "offline": 3}


def test_status_filter(client: TestClient, clock: FakeClock):
    client.post("/devices", json={"id": "d1", "name": "Lab 1"})
    client.post("/devices", json={"id": "d2", "name": "Lab 2"})
    client.post("/devices/d1/heartbeat", json={"status": "OK"})

    online = client.get("/devices?status=ONLINE").json()
    assert [d["id"] for d in online] == ["d1"]

    offline = client.get("/devices?status=OFFLINE").json()
    assert [d["id"] for d in offline] == ["d2"]

def test_health_endpoint(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "time" in body