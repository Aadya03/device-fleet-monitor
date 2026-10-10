"""Device simulator.

Spawns N threads that each register and then heartbeat at a fixed interval.
`--kill-at device-03:15` stops device-03 after 15s so you can watch it flip to
OFFLINE in `GET /devices` without doing any manual choreography.

Usage:
    python simulator/simulator.py                       # 5 devices, 5s interval
    python simulator/simulator.py --kill-at device-03:15
"""
import argparse
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import requests


def parse_kill_at(spec: Optional[str]) -> Dict[str, float]:
    """`'device-03:15,device-04:40'` → {'device-03': 15.0, 'device-04': 40.0}"""
    if not spec:
        return {}
    out: Dict[str, float] = {}
    for part in spec.split(","):
        name, _, when = part.partition(":")
        out[name.strip()] = float(when)
    return out


class SimulatedDevice(threading.Thread):
    def __init__(self, device_id: str, name: str, base_url: str,
                 interval: float, stop_after: Optional[float]):
        super().__init__(daemon=True)
        self.device_id = device_id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.interval = interval
        self.stop_after = stop_after
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        # Register. 409 on restart is fine — someone registered us already.
        try:
            r = requests.post(
                f"{self.base_url}/devices",
                json={"id": self.device_id, "name": self.name},
                timeout=5,
            )
            if r.status_code not in (201, 409):
                print(f"[{self.device_id}] register failed: {r.status_code} {r.text}")
                return
        except requests.RequestException as e:
            print(f"[{self.device_id}] cannot reach server: {e}")
            return

        started = time.monotonic()
        while not self._stop.is_set():
            if self.stop_after and (time.monotonic() - started) >= self.stop_after:
                print(f"[{self.device_id}] stopping (--kill-at)")
                return
            try:
                requests.post(
                    f"{self.base_url}/devices/{self.device_id}/heartbeat",
                    json={
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "OK",
                        "cpu_usage": round(random.uniform(5, 85), 1),
                        "signal_strength": random.randint(-90, -40),
                    },
                    timeout=5,
                )
            except requests.RequestException as e:
                print(f"[{self.device_id}] heartbeat failed: {e}")
            # Sleep in small chunks so Ctrl-C is responsive.
            self._stop.wait(self.interval)


def main() -> None:
    p = argparse.ArgumentParser(description="Simulate heartbeats from N devices.")
    p.add_argument("--url", default="http://localhost:8000", help="server base URL")
    p.add_argument("--devices", type=int, default=5, help="number of devices")
    p.add_argument("--interval", type=float, default=5.0, help="heartbeat interval (s)")
    p.add_argument(
        "--kill-at",
        help="stop specific devices after N seconds, e.g. 'device-03:15,device-04:40'",
    )
    args = p.parse_args()

    kill_at = parse_kill_at(args.kill_at)

    devices = []
    for i in range(1, args.devices + 1):
        device_id = f"device-{i:02d}"
        devices.append(
            SimulatedDevice(
                device_id=device_id,
                name=f"Lab Device {i:02d}",
                base_url=args.url,
                interval=args.interval,
                stop_after=kill_at.get(device_id),
            )
        )

    # Clean shutdown on Ctrl-C.
    def shutdown(*_):
        print("\nstopping all devices...")
        for d in devices:
            d.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    print(f"starting {len(devices)} devices → {args.url} (every {args.interval}s)")
    if kill_at:
        print(f"scheduled stops: {kill_at}")
    for d in devices:
        d.start()
    for d in devices:
        d.join()


if __name__ == "__main__":
    main()
