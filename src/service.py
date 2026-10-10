"""Business rules — kept as pure functions so they can be tested without
spinning up HTTP or touching a store.
"""
from datetime import datetime
from typing import Iterable, Optional

from src.models import Device


# A device is considered ONLINE if its last heartbeat arrived within this
# many seconds. The boundary is inclusive: age == 30s is still ONLINE.
TIMEOUT_SECONDS = 30


def compute_status(last_heartbeat: Optional[datetime], now: datetime) -> str:
    """Decide ONLINE/OFFLINE from the age of the last heartbeat.

    `last_heartbeat` is the time the server *received* the heartbeat (not the
    device's own clock), so a mis-set device clock cannot force a false ONLINE.
    """
    if last_heartbeat is None:
        return "OFFLINE"
    age = (now - last_heartbeat).total_seconds()
    return "ONLINE" if age <= TIMEOUT_SECONDS else "OFFLINE"


def summarize(devices: Iterable[Device], now: datetime) -> dict:
    """Count how many devices are online vs offline right now."""
    online = 0
    total = 0
    for d in devices:
        total += 1
        if compute_status(d.last_heartbeat_received_at, now) == "ONLINE":
            online += 1
    return {"total": total, "online": online, "offline": total - online}
