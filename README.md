# Device Fleet Monitor

A small HTTP service that tracks heartbeats from a fleet of devices and reports
which ones are currently online.

---

## What it does

- Devices register with the service, then POST a heartbeat on a regular interval.
- The service reports a device as **ONLINE** if its last heartbeat arrived
  within the last 30 seconds, otherwise **OFFLINE**.
- Status is computed on every read, so it is always correct — no background
  worker is needed to flip devices offline.
- A simulator script spins up 5 fake devices to make the behaviour easy to see.

---

## Design

```
                        ┌─────────────────┐
HTTP ──► FastAPI (api.py) ──► service.py ──► DeviceStore (store.py)
                        └── compute_status ──┘        │
                                                      │
                                          dict + threading.Lock
```

Three thin layers:

- **`store.py`** — in-memory dict of devices, protected by one `threading.Lock`.
  Writes (register, heartbeat) and iterations (list, summary) take the lock;
  single-key reads also take it for simplicity.
- **`service.py`** — pure functions. `compute_status(last_heartbeat, now)` is
  the whole timeout rule. No I/O, no clock lookups — the clock is passed in.
- **`api.py`** — FastAPI routes. They validate input through Pydantic, call
  the store, and run the response through `compute_status` using the injected
  clock.

### Why these choices

| Decision | Reason |
|---|---|
| Lazy status computation | No background sweeper means no race conditions and no timers to shut down. A `GET /devices` 31s after the last heartbeat always sees OFFLINE, even if nobody polled in between. |
| Server receive time, not device timestamp | A device with a wrong clock cannot force a false ONLINE. The device's `timestamp` is accepted and stored as metadata only. |
| `last_reported_status` separate from connectivity `status` | The spec example mixes `"status": "OK"` (device-reported) with `"status": "ONLINE"` (connectivity). They are different things — a device reporting `"ERROR"` is still ONLINE if it keeps heartbeating. |
| Injectable `Clock` | Tests advance time without `sleep()`. The full suite runs in under a second. |
| Single `threading.Lock` | 5 devices means zero contention; one lock is simpler than per-device locks. |

---

## Prerequisites

- Python 3.10 or newer
- `pip`

---

## Build

```bash
git clone https://github.com/aadya03/device-fleet-monitor.git
cd device-fleet-monitor
python -m venv .venv
source .venv/bin/activate         # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Run the application

```bash
python -m uvicorn src.main:app --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

---

## Run the simulator

In a second terminal, with the server already running:

```bash
# default: 5 devices, heartbeat every 5s
python simulator/simulator.py

# stop device-03 after 15s to see it flip to OFFLINE
python simulator/simulator.py --kill-at device-03:15

# different fleet / interval
python simulator/simulator.py --devices 10 --interval 2 --url http://localhost:8000
```

To watch the flip:

```bash
python simulator/simulator.py --kill-at device-03:15 &
# wait ~45s, then:
curl -s localhost:8000/summary
curl -s localhost:8000/devices | python -m json.tool
```

---

## Run the tests

```bash
python -m pytest -q
```

The full suite runs in well under a second — all time-based tests use a
controllable clock, no `sleep` calls.

---

## Example API requests

```bash
# Register a device
curl -X POST localhost:8000/devices \
  -H 'content-type: application/json' \
  -d '{"id":"device-01","name":"Lab Device 01"}'

# Send a heartbeat
curl -X POST localhost:8000/devices/device-01/heartbeat \
  -H 'content-type: application/json' \
  -d '{"timestamp":"2026-10-10T12:30:00Z","status":"OK","cpu_usage":42,"signal_strength":-71}'

# List all devices
curl localhost:8000/devices

# Filter by status
curl 'localhost:8000/devices?status=OFFLINE'

# Get one device
curl localhost:8000/devices/device-01

# Fleet summary
curl localhost:8000/summary
```

### Error responses

| Scenario | Status |
|---|---|
| Register an id that already exists | `409 Conflict` |
| Heartbeat for an unknown device | `404 Not Found` |
| Get an unknown device | `404 Not Found` |
| Malformed JSON / missing required field | `422 Unprocessable Entity` |

---

## Assumptions

- The 30-second window is **inclusive**: a device whose last heartbeat was
  received exactly 30s ago is still ONLINE. 31s is OFFLINE. The spec reads
  "within the last 30 seconds" vs. "more than 30 seconds".
- The device-supplied `timestamp` in a heartbeat is informational only — the
  server records its own receive time and uses that for the timeout rule.
- The heartbeat's `status` field is the device's self-reported health. It is
  surfaced in responses as `reported_status`, distinct from the connectivity
  `status` (`ONLINE`/`OFFLINE`).
- All timestamps are UTC and timezone-aware.
- Device IDs are opaque strings (1–64 characters). Names are 1–128 characters.

---

## Known limitations

- **No persistence.** State is in memory; a restart loses all devices and
  heartbeats. A persistent store would mean a schema plus startup/shutdown
  logic that was out of scope for 3 hours.
- **No authentication.** Anyone who can reach the port can register devices
  and send heartbeats on behalf of any id.
- **No pagination on `GET /devices`.** Fine for small fleets; would need
  cursoring for thousands of devices.
- **Single process.** A multi-worker deployment would need shared state
  (Redis or a database).
- **Lock granularity.** One lock around the whole store. For a very large
  fleet, sharding by id hash would reduce contention — but for 10, 100, or
  1,000 devices it is strictly simpler and shows no measurable overhead.

---

## What I would improve with one more day

- **SQLite persistence** behind the same `DeviceStore` interface, so a restart
  does not drop state.
- **Structured logging** on every heartbeat and on each ONLINE → OFFLINE
  transition. The transition is interesting; the heartbeat is noisy.
- **A tiny HTML dashboard** at `/` auto-refreshing `/summary` and `/devices`
  every 2s. Useful for the live demo.
- **Prometheus-style `/metrics`** (gauge for online count, histogram for
  heartbeat age) so this plugs into existing monitoring.
- **Docker + docker-compose** so a reviewer runs `docker compose up` and
  gets the server + simulator together.
- **`PATCH /devices/{id}`** to rename a device without re-registering.

---

## AI Usage

- **Tool used:** mix of claude and chatgpt.
- **What I used it for:**
  - Talking through the design before I started coding - mainly whether to
    recompute status on every read or run a background sweeper, and where
    the clock should live so the timeout tests wouldn't need to sleep.
  - A second opinion on my error handling (what should return 404 vs. 409
    vs. 422) and whether a `Repository` interface in front of the store
    was worth the extra file.
  - Catching that `self._stop = threading.Event()` in the simulator would
    collide with `threading.Thread`'s own `_stop` method. I'd have hit
    that on the live demo and had no idea what was wrong.
- **One suggestion I rejected:** it initially put the 30-second timeout
  check as a method on the `Device` class (`device.is_online(now)`). I
  moved it out into a standalone `compute_status(last_heartbeat, now)`
  in `service.py`, the rule isn't about a single device, it's a
  business rule, and keeping it as a pure function made the boundary
  tests dead simple to write.
- **One suggestion I adopted:** keeping the device's self-reported
  `status` ("OK") separate from the derived connectivity status
  ("ONLINE"/"OFFLINE"). The brief's example mashes both into one field
  and I would've shipped it that way without thinking.
- **What I personally verified before submitting:**
  - Ran the test suite from a clean venv on my own machine. 20 passed in
    under a second.
  - Started the server, ran `simulator.py --kill-at device-03:15`, waited
    ~40 seconds and confirmed `GET /summary` returned
    `{"total":5,"online":4,"offline":1}` with device-03 as the offline one.
  - Walked through the README setup commands in a fresh terminal.