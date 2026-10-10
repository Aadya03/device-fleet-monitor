"""Store tests: happy paths, error cases, and a small concurrency check."""
from datetime import datetime, timezone
from threading import Thread

import pytest

from src.models import Device
from src.store import DeviceStore, DeviceAlreadyExists, DeviceNotFound


def test_add_and_get():
    store = DeviceStore()
    store.add(Device(id="d1", name="One"))
    assert store.get("d1").name == "One"


def test_duplicate_id_raises():
    store = DeviceStore()
    store.add(Device(id="d1", name="One"))
    with pytest.raises(DeviceAlreadyExists):
        store.add(Device(id="d1", name="Dup"))


def test_get_unknown_raises():
    store = DeviceStore()
    with pytest.raises(DeviceNotFound):
        store.get("nope")


def test_heartbeat_unknown_raises():
    store = DeviceStore()
    with pytest.raises(DeviceNotFound):
        store.record_heartbeat("nope", datetime.now(timezone.utc))


def test_heartbeat_updates_fields():
    store = DeviceStore()
    store.add(Device(id="d1", name="One"))
    ts = datetime(2026, 10, 10, tzinfo=timezone.utc)
    store.record_heartbeat("d1", ts, reported_status="OK", cpu_usage=42)
    d = store.get("d1")
    assert d.last_heartbeat_received_at == ts
    assert d.last_reported_status == "OK"
    assert d.last_cpu_usage == 42


def test_concurrent_registers_do_not_corrupt_dict():
    # Lots of threads register distinct ids at once. If the lock is wrong we
    # see lost writes or a corrupt dict iteration.
    store = DeviceStore()

    def register(i):
        store.add(Device(id=f"d{i}", name=f"N{i}"))

    threads = [Thread(target=register, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(store.all()) == 50
