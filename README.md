# TuniBot — Hotel Delivery Robot (Phase 1 MVP)

TuniBot is a delivery robot for a hotel. A staff member picks a room in a web page, the robot
collects the item at reception, takes the elevator if needed, delivers it, and returns to its
dock. This repository holds **Pair B's part**: everything above navigation — the mission logic,
the REST API and the web UI. Navigation, SLAM and simulation (Nav2) belong to Pair A.

- [How it works](#how-it-works)
- [Repository layout](#repository-layout)
- [Installation](#installation)
- [Running the project](#running-the-project)
- [Using the dispatch UI](#using-the-dispatch-ui)
- [REST API reference](#rest-api-reference)
- [ROS 2 interface](#ros-2-interface)
- [Mission flow and states](#mission-flow-and-states)
- [Destinations](#destinations)
- [How each part is built](#how-each-part-is-built)
- [Configuration](#configuration)
- [Testing](#testing)
- [Development workflow](#development-workflow)
- [Known gaps](#known-gaps)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
 Hotel staff
     │  browser
     ▼
┌──────────────────┐   REST (JSON)    ┌──────────────────┐  WebSocket   ┌────────────┐
│  React UI        │ ───────────────▶ │  FastAPI backend │ ───────────▶ │ rosbridge  │
│  frontend/ :5173 │ ◀─────────────── │  backend/  :8000 │ ◀─────────── │   :9090    │
└──────────────────┘  polls status    └──────────────────┘              └─────┬──────┘
                                                                              │ ROS 2 topics
                                                                              ▼
                                                                   ┌─────────────────────┐
                                                                   │  Mission Manager    │
                                                                   │  (ROS 2 node)       │
                                                                   │  queue, states,     │
                                                                   │  destinations       │
                                                                   └──────────┬──────────┘
                                                                              │ (Phase 1: simulated
                                                                              ▼  timers; later Nav2)
                                                                        Robot / Pair A
```

| Part | What it does | Tech | Runs on |
|---|---|---|---|
| **UI** (`frontend/`) | Form to send a delivery, live robot state, battery and activity log | React 19, Vite, Tailwind CSS 4 | Windows or Linux (Node.js) |
| **Backend** (`backend/`) | Validates orders, forwards them to ROS, serves the latest robot status | Python, FastAPI, roslibpy | Windows or Linux (Python) |
| **Mission Manager** (`src/mission_manager/`) | Decides what the robot does next: order queue, pickup → floor change → delivery → return | ROS 2 Humble, rclpy | Linux / WSL |
| **rosbridge** | Translates between the backend's WebSocket and ROS 2 topics | `rosbridge_suite` | Linux / WSL |

The UI and the backend never import ROS: they talk to it only through rosbridge. That keeps
web development independent from the robot, and lets the backend run with a **fake robot**
when ROS isn't available.

---

## Repository layout

```
tunibot_ws/
├── README.md                     ← this file
├── PLAN.md                       Pair B plan, interface contract, day-by-day acceptance tests
├── maps/arena_map.yaml           Map metadata (the .pgm image is not versioned)
├── src/
│   └── mission_manager/          ROS 2 package (ament_python) — built by colcon
│       ├── config/destinations.yaml     Named places with floor + coordinates
│       ├── mission_manager/
│       │   ├── mission_manager_node.py  The node: subscriptions, timer, state transitions
│       │   ├── state_machine.py         MissionState enum
│       │   ├── delivery_queue.py        FIFO order queue
│       │   └── destination_resolver.py  Name → {floor, x, y, yaw}, rejects unknown names
│       ├── package.xml, setup.py, setup.cfg
│       └── test/                        ament lint tests
├── backend/                      FastAPI service — not built by colcon
│   ├── main.py                   App factory and REST endpoints
│   ├── ros_bridge_client.py      rosbridge client, status store, fake robot
│   ├── config.py                 Settings from environment / .env
│   ├── destinations.py           Reads destination names from destinations.yaml
│   ├── models.py                 Request / response schemas
│   ├── tests/                    pytest suite (no ROS needed)
│   ├── requirements.txt, .env.example, README.md
└── frontend/                     React app — not built by colcon
    ├── src/App.jsx               The whole dispatch UI
    ├── src/main.jsx, index.css
    ├── vite.config.js, package.json
```

`backend/` and `frontend/` are deliberately outside `src/`: `colcon build` only scans `src/`.

---

## Installation

### Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.10+ | Backend |
| Node.js + npm | 20+ | Frontend |
| WSL 2 with Ubuntu 22.04 (on Windows) | — | ROS 2 |
| ROS 2 Humble | — | Mission Manager, rosbridge |

You can develop the UI and backend **without ROS at all** (see fake mode below).

### 1. Clone

```bash
git clone https://github.com/SanaMabrouk/tunibot_ws.git
cd tunibot_ws
```

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate                  # Windows   (Linux/WSL: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                 # optional  (Linux/WSL: cp .env.example .env)
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. ROS 2 side (in WSL / Ubuntu 22.04)

```bash
# rosbridge + YAML support for the destination resolver
sudo apt install ros-humble-rosbridge-suite python3-yaml

# Build the Mission Manager package (from the repo root inside WSL)
cd ~/path/to/tunibot_ws        # or /mnt/c/Users/<you>/Documents/tunibot_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

---

## Running the project

### Option A — UI + backend with a fake robot (no ROS)

Fastest way to demo or work on the UI. The backend simulates the robot itself.

```bash
# Terminal 1 — backend (PowerShell, from backend/)
$env:FAKE_ROS="true"; .\venv\Scripts\uvicorn main:app --reload
```
```bash
# Terminal 2 — frontend (from frontend/)
npm run dev
```

Open **http://localhost:5173**. API docs are at **http://localhost:8000/docs**.

### Option B — full stack with ROS 2

Start the pieces in this order. ROS terminals are in WSL, the rest can be Windows.

```bash
# WSL terminal 1 — rosbridge
source /opt/ros/humble/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```
```bash
# WSL terminal 2 — Mission Manager (run from the package source folder, see Known gaps)
source /opt/ros/humble/setup.bash
cd src/mission_manager
python3 -m mission_manager.mission_manager_node
```
```bash
# Windows terminal 3 — backend in ROS mode (from backend/)
$env:FAKE_ROS="false"; .\venv\Scripts\uvicorn main:app --reload
```
```bash
# Windows terminal 4 — frontend (from frontend/)
npm run dev
```

WSL 2 forwards ports to Windows, so the backend reaches rosbridge at `localhost:9090`.
Check **http://localhost:8000/health** — it should say `"mode": "ros"` and `"rosbridge": "connected"`.

---

## Using the dispatch UI

1. Open http://localhost:5173. The dot top-right shows **Connected** when the backend answers.
2. **Robot state** shows the current state, the active order and the battery bar (red under 30%).
3. In **New delivery**, pick a room and click **Send delivery**. The UI generates an order ID
   (`ORD-` + 4 digits) and posts it to the backend.
4. **Activity** lists the last 8 state changes with their time.

The UI refreshes the robot status every 1.5 seconds.

---

## REST API reference

Base URL: `http://localhost:8000`. Interactive docs (Swagger): `/docs`.

### `POST /delivery` — send a delivery

```json
{ "order_id": "ORD-001", "destination": "room_101" }
```

- `order_id` is optional; the backend generates `ORD-001`, `ORD-002`, … when it's missing.
- `destination` must be a name from `destinations.yaml`.

| Response | When |
|---|---|
| `200 {"status": "queued", "order_id": "ORD-001"}` | Published to `/delivery_request` |
| `422` with the list of valid names | Unknown destination, or empty `order_id` |
| `503` | rosbridge is not connected (nothing was sent) |

### `GET /robot/status` — latest robot status

```json
{
  "state": "NAVIGATING",
  "battery": 100.0,
  "current_order": "ORD-001",
  "last_update": "2026-10-01T09:30:12.123Z",
  "connected": true
}
```

Before the first status message arrives: `state` is `"UNKNOWN"` and the other fields are `null`.
`connected` tells whether the backend currently reaches rosbridge.

### `GET /destinations` — valid destination names

```json
{ "destinations": ["reception", "dock", "elevator_rdc", "elevator_etage1", "room_101", "..."] }
```

### `GET /health` — service check

```json
{ "api": "ok", "rosbridge": "connected", "mode": "ros" }
```

`mode` is `"fake"` when `FAKE_ROS=true`.

### Examples

```bash
# PowerShell
Invoke-RestMethod -Method Post http://localhost:8000/delivery -ContentType "application/json" -Body '{"destination":"room_101"}'
Invoke-RestMethod http://localhost:8000/robot/status
```
```bash
# bash / WSL
curl -X POST localhost:8000/delivery -H "Content-Type: application/json" -d '{"destination":"room_101"}'
curl localhost:8000/robot/status
```

---

## ROS 2 interface

Plain `std_msgs/String` messages carrying JSON (PLAN.md §4). Changing these requires agreement
from both Pair B developers.

| Topic | Type | Payload | Publisher → Subscriber |
|---|---|---|---|
| `/delivery_request` | `std_msgs/String` | `{"order_id": "ORD-001", "destination": "room_101"}` | Backend → Mission Manager |
| `/robot_status` | `std_msgs/String` | `{"state": "NAVIGATING", "battery": 100.0, "current_order": "ORD-001", "floor": 1}` | Mission Manager → Backend |

Mission Manager publishes `/robot_status` once per second. The `floor` field is extra
information; the backend currently ignores it.

---

## Mission flow and states

For each order the robot goes to **reception** to pick up the item, changes floor through the
elevator if the room is on another floor, delivers, then takes the next order or goes back to
its dock.

```
IDLE ──order──▶ QUEUED ──▶ NAVIGATING (to reception) ──▶ PICKING_UP
                                                            │
                         ┌── room on another floor ─────────┤
                         ▼                                  │ same floor
                   CHANGING_FLOOR ──▶ NAVIGATING (to room) ◀┘
                                            │
                                            ▼
                                       DELIVERING ──more orders──▶ NAVIGATING (to reception)
                                            │ queue empty
                                            ▼
                         RETURNING ──▶ DOCKING ──▶ DOCKED ──▶ IDLE (or QUEUED if orders waiting)
```

| State | Meaning |
|---|---|
| `IDLE` | At the dock, nothing to do |
| `QUEUED` | Orders are waiting; the next one is being dispatched |
| `NAVIGATING` | Driving — to reception, or to the room after pickup |
| `PICKING_UP` | Collecting the item at reception |
| `CHANGING_FLOOR` | Taking the elevator to the destination floor |
| `DELIVERING` | Handing over the item at the room |
| `RETURNING` | Heading back to the dock |
| `DOCKING` / `DOCKED` | Parking / parked on the charger (floor resets to 0) |
| `UNKNOWN` | Shown by the backend before any status has been received |

In Phase 1 the Mission Manager **simulates** movement with timers (for example 5 s navigating,
2 s picking up, 4 s changing floor). Phase 1 step 4 replaces these with real Nav2
`NavigateToPose` goals from Pair A.

---

## Destinations

Defined once in `src/mission_manager/config/destinations.yaml` (owned by the Mission Manager
developer). Both the Mission Manager and the backend read this file.

| Name | Floor | x | y | Notes |
|---|---|---|---|---|
| `reception` | 0 | -5.0 | 3.0 | Pickup point for every order |
| `dock` | 0 | 0.0 | 0.0 | Charging dock |
| `elevator_rdc` | 0 | 8.0 | 0.0 | Elevator, ground floor |
| `elevator_etage1` | 1 | 0.0 | 0.0 | Elevator, 1st floor |
| `room_101` … `room_106` | 1 | -8.0 … 2.0 | -14.0 / -18.0 | Guest rooms |

To add a place: add it to `destinations.yaml`, restart the Mission Manager and the backend,
and add it to `DESTINATIONS` in `frontend/src/App.jsx`.

---

## How each part is built

### Backend (`backend/`)

- **`main.py`** builds the app with `create_app(settings, link)`. Endpoints only depend on a
  *robot link* object, so tests can pass a fake one.
- **`ros_bridge_client.py`** has two interchangeable links:
  - `RosBridgeClient` connects to rosbridge with roslibpy **in a background thread**, so the API
    starts even when ROS is down. roslibpy retries automatically and re-subscribes after a
    reconnect. Publishing while disconnected raises an error that the API turns into `503`.
  - `FakeRobot` (`FAKE_ROS=true`) runs a simplified state machine in a thread: one transition
    every `FAKE_STEP_SECONDS`, battery drains while working and forces a return below 30%.
- **`StatusStore`** holds the latest `/robot_status`. It's protected by a lock (ROS callbacks run
  on another thread) and ignores malformed messages, keeping the last good status.
- **`destinations.py`** reads the names from `destinations.yaml`; if the file is missing or
  invalid it falls back to the PLAN.md defaults and logs a warning.
- **`config.py`** loads settings from environment variables or `backend/.env` (pydantic-settings).
- CORS allows the Vite dev server (`http://localhost:5173`) to call the API.

### Frontend (`frontend/`)

- Single component **`App.jsx`**, styled with Tailwind utility classes.
- Polls `GET /robot/status` every 1.5 s; a failed request switches the header to **Offline**.
- Keeps an activity log of the last 8 state changes (client side only).
- Sends `POST /delivery` with a random `ORD-####` order ID. The submit button is disabled for
  1 s after sending to avoid double orders.

### Mission Manager (`src/mission_manager/`)

- **`MissionManagerNode`** subscribes to `/delivery_request`, publishes `/robot_status`, and runs
  a **1-second timer** (`tick`) that advances the state machine.
- Incoming orders are parsed, validated with the destination resolver (unknown names are
  logged and dropped), then added to the FIFO **`DeliveryQueue`**.
- Each state lasts a fixed number of ticks (`FAKE_DURATION`); `advance()` picks the next state
  based on the current order, its destination floor and the current floor.

---

## Configuration

Backend settings (environment variables or `backend/.env`):

| Variable | Default | Description |
|---|---|---|
| `ROSBRIDGE_HOST` | `localhost` | rosbridge host |
| `ROSBRIDGE_PORT` | `9090` | rosbridge port |
| `FAKE_ROS` | `false` | `true` = simulate the robot, no ROS needed |
| `FAKE_STEP_SECONDS` | `2` | Fake robot: seconds per state transition |
| `DESTINATIONS_FILE` | `../src/mission_manager/config/destinations.yaml` | Destination list |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Origins allowed to call the API |

Frontend: the API address is the `API` constant at the top of `frontend/src/App.jsx`
(`http://localhost:8000`).

In PowerShell, `$env:FAKE_ROS="true"` stays set for the rest of that window — set it back to
`"false"` explicitly for ROS mode.

---

## Testing

### Backend — automated (no ROS)

```bash
cd backend
.\venv\Scripts\python -m pytest -v
```

17 tests: endpoints, destination validation, `503` when rosbridge is down, status parsing,
fake robot state machine.

### Frontend — lint

```bash
cd frontend
npm run lint
```

### Mission Manager — ament lint tests (WSL)

```bash
colcon test --packages-select mission_manager && colcon test-result --verbose
```

### End-to-end checks against ROS (PLAN.md §7)

```bash
# Watch what the backend sends
ros2 topic echo /delivery_request std_msgs/msg/String

# Watch what Mission Manager reports
ros2 topic echo /robot_status std_msgs/msg/String

# Send an order without the UI
ros2 topic pub --once /delivery_request std_msgs/msg/String "{data: '{\"order_id\": \"ORD-001\", \"destination\": \"room_101\"}'}"
```

A full run: send a delivery from the UI and watch the state go through
`QUEUED → NAVIGATING → PICKING_UP → CHANGING_FLOOR → NAVIGATING → DELIVERING → RETURNING → DOCKING → DOCKED → IDLE`.

---

## Development workflow

- Work on feature branches: `feature/mission-manager`, `feature/backend-ui`, `feature/frontend`.
- No direct commits to `main`. Merge through a pull request reviewed by the other developer,
  after that day's acceptance test passes (PLAN.md §7).
- `destinations.yaml` is owned by the Mission Manager developer; others request changes.
- The topic contract (PLAN.md §4) changes only with both developers' agreement, in the same PR
  that updates PLAN.md.
- Never commit `venv/`, `node_modules/`, `build/`, `install/`, `log/` or `.env`.

---

## Known gaps

Phase 1 items not finished yet, or worth fixing before the demo:

| Area | Gap |
|---|---|
| Mission Manager | No `console_scripts` entry in `setup.py`, so `ros2 run mission_manager …` doesn't work yet; run it with `python3 -m` from `src/mission_manager/` |
| Mission Manager | `destinations.yaml` isn't installed by `setup.py`; the resolver reads it from the source tree |
| Mission Manager | Battery simulator not implemented: battery is always reported as `100.0`, so the low-battery return never triggers |
| Mission Manager | Navigation is simulated with timers; real Nav2 `NavigateToPose` calls are the Day 4 sync point with Pair A |
| Frontend | Destination list is hard-coded instead of loaded from `GET /destinations` |
| Frontend | `422` / `503` responses from `POST /delivery` aren't shown to the user |
| Frontend | `PICKING_UP` and `CHANGING_FLOOR` have no colour in the state display |
| Backend | The fake robot (`FAKE_ROS=true`) follows the original PLAN.md states and doesn't simulate `PICKING_UP` / `CHANGING_FLOOR` |
| Backend | `/robot/status` doesn't expose the `floor` field yet |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `.\venv\Scripts\uvicorn` is not recognized | Run it from the `backend/` folder |
| `Address already in use` on port 8000 | Another backend is running; stop it or add `--port 8001` (and update `API` in `App.jsx`) |
| `/health` shows `"rosbridge": "disconnected"` | Start rosbridge in WSL; the backend reconnects by itself within seconds |
| UI header shows **Offline** | Backend not running, or running on another port |
| UI stays on `UNKNOWN` in ROS mode | Mission Manager isn't running, so nothing publishes `/robot_status` |
| Delivery sent but nothing happens | Check the Mission Manager log: unknown destinations are rejected there; `ros2 topic echo /delivery_request std_msgs/msg/String` shows whether the order reached ROS |
| `ros2 topic echo` says it can't determine the type | Pass the type explicitly: `std_msgs/msg/String` |
| WSL can't be reached on `localhost:9090` | Run `wsl --shutdown` in Windows and start the WSL terminals again |
