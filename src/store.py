"""In-memory device registry.

A single lock guards the dict. For 5 or 10 devices the contention is nil, and
one lock is simpler to reason about than per-device locks. For a real fleet
of thousands you'd shard by id hash.
"""
from datetime import datetime
from threading import Lock
from typing import List, Optional

from src.models import Device
from copy import copy


class DeviceAlreadyExists(Exception):
    pass


class DeviceNotFound(Exception):
    pass


class DeviceStore:
    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._lock = Lock()

    def add(self, device: Device) -> Device:
        with self._lock:
            if device.id in self._devices:
                raise DeviceAlreadyExists(device.id)
            self._devices[device.id] = device
            return device

    def get(self, device_id: str) -> Device:
        with self._lock:
            if device_id not in self._devices:
                raise DeviceNotFound(device_id)
            return copy(self._devices[device_id])

    def all(self) -> List[Device]:
        with self._lock:
            return [copy(d) for d in self._devices.values()]

    def record_heartbeat(
        self,
        device_id: str,
        received_at: datetime,
        reported_status: Optional[str] = None,
        cpu_usage: Optional[float] = None,
        signal_strength: Optional[float] = None,
    ) -> Device:
        with self._lock:
            if device_id not in self._devices:
                raise DeviceNotFound(device_id)
            d = self._devices[device_id]
            d.last_heartbeat_received_at = received_at
            d.last_reported_status = reported_status
            d.last_cpu_usage = cpu_usage
            d.last_signal_strength = signal_strength
            return d
