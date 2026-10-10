"""Domain types and API schemas.

Internal state keeps `last_heartbeat_received_at` (server receive time) because
device clocks can drift. The response field is renamed back to `last_heartbeat`
to match the brief's example.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


@dataclass
class Device:
    id: str
    name: str
    # None until the first heartbeat arrives.
    last_heartbeat_received_at: Optional[datetime] = None
    # Device self-reported health (e.g. "OK", "WARN"). Separate from
    # connectivity status, which is derived from the heartbeat age.
    last_reported_status: Optional[str] = None
    last_cpu_usage: Optional[float] = None
    last_signal_strength: Optional[float] = None




class DeviceCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


class HeartbeatIn(BaseModel):
    # Device-supplied timestamp is accepted but not used for the timeout rule.
    timestamp: Optional[datetime] = None
    status: Optional[str] = None
    cpu_usage: Optional[float] = None
    signal_strength: Optional[float] = None


class DeviceOut(BaseModel):
    id: str
    name: str
    status: str                       # "ONLINE" / "OFFLINE" (connectivity)
    last_heartbeat: Optional[datetime] = None
    reported_status: Optional[str] = None
    cpu_usage: Optional[float] = None
    signal_strength: Optional[float] = None


class SummaryOut(BaseModel):
    total: int
    online: int
    offline: int
