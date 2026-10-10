"""Boundary tests for the 30-second ONLINE/OFFLINE rule.

We inject a fake clock so these tests run in milliseconds instead of waiting
for real wall time.
"""
from datetime import datetime, timedelta, timezone

from src.models import Device
from src.service import compute_status, summarize, TIMEOUT_SECONDS


NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_no_heartbeat_is_offline():
    assert compute_status(None, NOW) == "OFFLINE"


def test_recent_heartbeat_is_online():
    last = NOW - timedelta(seconds=10)
    assert compute_status(last, NOW) == "ONLINE"


def test_exactly_at_boundary_is_online():
    # Spec: "within the last 30 seconds" is inclusive.
    last = NOW - timedelta(seconds=TIMEOUT_SECONDS)
    assert compute_status(last, NOW) == "ONLINE"


def test_just_past_boundary_is_offline():
    last = NOW - timedelta(seconds=TIMEOUT_SECONDS + 1)
    assert compute_status(last, NOW) == "OFFLINE"


def test_summarize_counts_correctly():
    devices = [
        Device(id="a", name="A", last_heartbeat_received_at=NOW),
        Device(id="b", name="B", last_heartbeat_received_at=NOW - timedelta(seconds=5)),
        Device(id="c", name="C", last_heartbeat_received_at=NOW - timedelta(seconds=60)),
        Device(id="d", name="D", last_heartbeat_received_at=None),
    ]
    summary = summarize(devices, NOW)
    assert summary == {"total": 4, "online": 2, "offline": 2}
