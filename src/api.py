"""HTTP layer. Thin — translates between JSON and the service/store.

The clock is injected rather than imported, so tests can freeze time.
"""
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException

from src.models import (
    Device,
    DeviceCreate,
    DeviceOut,
    HeartbeatIn,
    SummaryOut,
)
from src.service import compute_status, summarize
from src.store import DeviceStore, DeviceAlreadyExists, DeviceNotFound


# Callable so tests can swap in a controllable clock.
Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _to_out(d: Device, now: datetime) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        name=d.name,
        status=compute_status(d.last_heartbeat_received_at, now),
        last_heartbeat=d.last_heartbeat_received_at,
        reported_status=d.last_reported_status,
        cpu_usage=d.last_cpu_usage,
        signal_strength=d.last_signal_strength,
    )


def create_app(store: Optional[DeviceStore] = None, clock: Clock = _default_clock) -> FastAPI:
    """Build the FastAPI app. Store and clock are injected to keep tests
    independent of a global state."""
    store = store or DeviceStore()
    app = FastAPI(title="Device Fleet Monitor", version="1.0.0")

    @app.post("/devices", status_code=201, response_model=DeviceOut)
    def register_device(payload: DeviceCreate) -> DeviceOut:
        try:
            d = store.add(Device(id=payload.id, name=payload.name))
        except DeviceAlreadyExists:
            raise HTTPException(status_code=409, detail=f"device '{payload.id}' already exists")
        return _to_out(d, clock())

    @app.post("/devices/{device_id}/heartbeat", response_model=DeviceOut)
    def heartbeat(device_id: str, payload: HeartbeatIn) -> DeviceOut:
        try:
            # Server receive time drives the ONLINE/OFFLINE rule; the device's
            # own `timestamp` is kept only as reported metadata if present.
            d = store.record_heartbeat(
                device_id,
                received_at=clock(),
                reported_status=payload.status,
                cpu_usage=payload.cpu_usage,
                signal_strength=payload.signal_strength,
            )
        except DeviceNotFound:
            raise HTTPException(status_code=404, detail=f"device '{device_id}' not registered")
        return _to_out(d, clock())

    @app.get("/devices", response_model=list[DeviceOut])
    def list_devices(status: Optional[str] = None) -> list[DeviceOut]:
        now = clock()
        out = [_to_out(d, now) for d in store.all()]
        if status:
            # Optional filter — makes the simulator demo quick to inspect.
            status_upper = status.upper()
            out = [d for d in out if d.status == status_upper]
        return out

    @app.get("/devices/{device_id}", response_model=DeviceOut)
    def get_device(device_id: str) -> DeviceOut:
        try:
            d = store.get(device_id)
        except DeviceNotFound:
            raise HTTPException(status_code=404, detail=f"device '{device_id}' not registered")
        return _to_out(d, clock())

    @app.get("/summary", response_model=SummaryOut)
    def summary() -> SummaryOut:
        return SummaryOut(**summarize(store.all(), clock()))

    return app
