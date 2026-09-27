# TuniBot — CSTAM-TUNIBOT Phase 1 MVP
## Pair B Development Plan — Mission Manager · Backend · UI

**Repo:** `tunibot_ws` (shared, GitHub)
**Team:** Pair B (2 people) — Pair A owns Robot/Simulation/SLAM/Nav2 separately
**Deadline:** Phase 1 MVP ~October 1
**Scope:** This document governs Pair B's work only. See `Pair_A_Deliverables.pdf` for the cross-team interface contract.

---

## 1. System context

Pair B builds everything **above** navigation: the logic that decides *what* the robot should do next, and the interfaces that let a human request a delivery and see status.

```
USER
  │
  ▼
React UI  ──REST──▶  FastAPI  ──rosbridge (WebSocket)──▶  ROS 2
                                                              │
                                                              ▼
                                                    MISSION MANAGER
                                              (state machine, queue,
                                               destination resolver,
                                               battery simulator)
                                                              │
                                                              ▼
                                          NavigateToPose (Pair A's Nav2)
```

Mission Manager is a **ROS 2 node**. FastAPI and React are **standalone** — they don't get compiled by `colcon`, they run as ordinary Python/Node processes and talk to ROS 2 only through `rosbridge`.

---

## 2. Repository structure

```
tunibot_ws/
├── .gitignore
├── README.md
├── PLAN.md                          ← this file
├── Pair_A_Deliverables.pdf
├── src/
│   └── mission_manager/             ← ROS 2 package (ament_python)
│       ├── mission_manager/
│       │   ├── __init__.py
│       │   ├── state_machine.py
│       │   ├── destination_resolver.py
│       │   ├── delivery_queue.py
│       │   ├── battery_simulator.py
│       │   └── mission_manager_node.py
│       ├── config/
│       │   └── destinations.yaml
│       ├── package.xml
│       ├── setup.py
│       └── setup.cfg
├── backend/                          ← standalone FastAPI service
│   ├── main.py
│   ├── ros_bridge_client.py
│   ├── requirements.txt
│   └── venv/                         (gitignored)
└── frontend/                         ← standalone React app
    ├── src/
    │   ├── App.jsx
    │   └── components/
    │       ├── DeliveryForm.jsx
    │       └── StatusView.jsx
    ├── package.json
    └── node_modules/                 (gitignored)
```

`backend/` and `frontend/` sit outside `src/` deliberately — `colcon build` only scans `src/` for ROS 2 packages, and keeping web code out of that tree avoids build errors and confusion.

---

## 3. Ownership split

| Person | Owns | Environment needed |
|---|---|---|
| **Person 1** | `src/mission_manager/` (state machine, queue, resolver, battery) | ROS 2 Humble (already installed) |
| **Person 2** | `backend/` (FastAPI) + `frontend/` (React) | Python 3.10+, Node.js; `rosbridge` running on Person 1's or a shared ROS 2 machine for integration testing |

Whoever isn't sure which to take: Person 1 role suits prior ROS 2/Linux debugging experience from the SLAM/AMCL session; Person 2 role suits prior React/Next.js experience. Either assignment works as long as the split stays clean — no shared files edited by both people.

---

## 4. Interface contract (frozen — changes require both people's agreement)

| Topic | Type | Payload (JSON string) | Publisher | Subscriber |
|---|---|---|---|---|
| `/delivery_request` | `std_msgs/String` | `{"order_id": "ORD-001", "destination": "room_a"}` | FastAPI | Mission Manager |
| `/robot_status` | `std_msgs/String` | `{"state": "NAVIGATING", "battery": 85.0, "current_order": "ORD-001"}` | Mission Manager | FastAPI |
| `/battery` | `std_msgs/Float32` | raw percentage (0–100) | Battery Simulator (inside Mission Manager node) | Mission Manager (internal) |

Custom `.msg` interfaces are intentionally **not** used for Phase 1 — plain `String` + JSON is faster to iterate on and avoids interface-package rebuilds every time a field changes. Revisit for Phase 2 if needed.

**Destination names** (must match exactly between `destinations.yaml` and the UI's dropdown): `dock`, `kitchen`, `room_a`, `room_b` (extend as Pair A's hotel world grows — coordinate values come from Pair A, see `Pair_A_Deliverables.pdf`).

---

## 5. Git workflow

```bash
# One-time setup (repo owner)
mkdir -p tunibot_ws/src && cd tunibot_ws
git init
git add . && git commit -m "Initial repo structure"
git remote add origin https://github.com/<username>/tunibot_ws.git
git branch -M main
git push -u origin main
```

**Branching rule:**
```bash
git checkout -b feature/mission-manager      # Person 1
git checkout -b feature/backend-ui           # Person 2
```

- No direct commits to `main`.
- Merge to `main` only after that day's acceptance test (Section 7) passes.
- Pull requests reviewed by the other person before merge — even a 2-minute glance catches interface mismatches early (e.g. a typo in a topic name).
- `destinations.yaml` is owned by Person 1; Person 2 requests changes rather than editing it directly, to avoid silent merge conflicts on a file both sides depend on.

**`.gitignore`:**
```
build/
install/
log/
__pycache__/
*.pyc
venv/
node_modules/
.env
*.pgm
```

---

## 6. Component specifications

### 6.1 Mission Manager — State Machine

```python
from enum import Enum

class MissionState(Enum):
    IDLE = "IDLE"
    QUEUED = "QUEUED"
    NAVIGATING = "NAVIGATING"
    DELIVERING = "DELIVERING"
    RETURNING = "RETURNING"
    DOCKING = "DOCKING"
    DOCKED = "DOCKED"
```

Transitions:
```
IDLE       → QUEUED      (delivery request received)
QUEUED     → NAVIGATING  (queue has item, goal dispatched)
NAVIGATING → DELIVERING  (goal reached)
DELIVERING → NAVIGATING  (more items queued)
DELIVERING → RETURNING   (queue empty)
RETURNING  → DOCKING     (near dock)
DOCKING    → DOCKED      (dock confirmed)
DOCKED     → IDLE        (ready for next request)

-- battery override, any state except DOCKED/DOCKING --
*          → RETURNING   (battery < 30%)
```

### 6.2 Destination Resolver

```yaml
# config/destinations.yaml
dock:    { x: 0.0, y: 0.0, yaw: 0.0 }
kitchen: { x: 0.0, y: 0.0, yaw: 0.0 }   # placeholder — Pair A to confirm
room_a:  { x: 0.0, y: 0.0, yaw: 0.0 }   # placeholder — Pair A to confirm
room_b:  { x: 0.0, y: 0.0, yaw: 0.0 }   # placeholder — Pair A to confirm
```
Resolver raises a clear error on an unknown destination name (Phase 1 robustness requirement).

### 6.3 Delivery Queue

Plain FIFO list — no priority logic needed for Phase 1:
```python
class DeliveryQueue:
    def __init__(self):
        self._queue = []
    def add(self, order_id, destination):
        self._queue.append({"order_id": order_id, "destination": destination})
    def next(self):
        return self._queue.pop(0) if self._queue else None
    def is_empty(self):
        return len(self._queue) == 0
```

### 6.4 Battery Simulator

```python
class BatterySimulator:
    def __init__(self, drain_rate=0.05):
        self.level = 100.0
        self.drain_rate = drain_rate
    def tick(self):
        self.level = max(0.0, self.level - self.drain_rate)
        return self.level
```
Driven by a 1-second ROS 2 timer inside the Mission Manager node.

### 6.5 FastAPI Backend

```python
from fastapi import FastAPI
from pydantic import BaseModel
import roslibpy

app = FastAPI()
ros_client = roslibpy.Ros(host='localhost', port=9090)
ros_client.run()

delivery_pub = roslibpy.Topic(ros_client, '/delivery_request', 'std_msgs/String')
status_sub = roslibpy.Topic(ros_client, '/robot_status', 'std_msgs/String')

latest_status = {"state": "UNKNOWN", "battery": None, "current_order": None}
def on_status(msg):
    global latest_status
    latest_status = msg  # parse JSON here
status_sub.subscribe(on_status)

class DeliveryRequest(BaseModel):
    order_id: str
    destination: str

@app.post("/delivery")
async def create_delivery(req: DeliveryRequest):
    delivery_pub.publish(roslibpy.Message({'data': req.json()}))
    return {"status": "queued", "order_id": req.order_id}

@app.get("/robot/status")
async def robot_status():
    return latest_status
```

Dependencies: `pip install fastapi uvicorn roslibpy`
Requires `rosbridge_suite` running: `ros2 launch rosbridge_server rosbridge_websocket_launch.xml`

### 6.6 React UI

Two components only for Phase 1:
- **DeliveryForm** — destination dropdown + submit → `POST /delivery`
- **StatusView** — polls `GET /robot/status` every 1–2s, displays state + battery

No routing, no auth, no styling framework required — function over form.

---

## 7. Day-by-day plan with acceptance tests

| Day | Mission Manager (Person 1) | Backend + UI (Person 2) | Acceptance test |
|---|---|---|---|
| **1** | `ros2 pkg create mission_manager`; state machine with fake timers replacing real navigation | FastAPI skeleton, hardcoded fake responses, no ROS yet | MM: node runs, `/robot_status` cycles through states after a fake `/delivery_request`. Backend: `curl` to both endpoints returns valid JSON. |
| **2** | Wire Destination Resolver + Delivery Queue; real `/delivery_request` subscription | Install `rosbridge_suite`; connect FastAPI via `roslibpy`; `POST /delivery` publishes for real | MM: `ros2 topic pub` a real request, queue processes it correctly. Backend: message appears on `ros2 topic echo /delivery_request` when hitting the API. |
| **3** | Add Battery Simulator; wire battery-triggered `RETURNING` override | Build React UI; wire to FastAPI | MM: forcing battery below 30% (test hook) triggers `RETURNING` regardless of current state. UI: clicking submit produces a visible FastAPI log entry. |
| **4** | Swap fake timers for real `NavigateToPose` calls to Pair A's Nav2 (sync point) | Full loop test: UI → API → MM → (real or fake nav) → UI | One full order flows end-to-end with no manual intervention, observable in the UI's status view. |

---

## 8. Definition of done (Pair B, Phase 1)

- [ ] Mission Manager runs as a ROS 2 node with no crashes, correct state transitions
- [ ] Delivery Queue processes multiple orders in FIFO order
- [ ] Destination Resolver rejects unknown names cleanly
- [ ] Battery Simulator drains and triggers `RETURNING` at threshold
- [ ] FastAPI exposes `/delivery` and `/robot/status`, connected to ROS 2 via `rosbridge`
- [ ] React UI lets a user submit a delivery and see live status
- [ ] One full end-to-end run recorded for the demo video, no manual topic publishing needed
- [ ] Code merged to `main`, README updated, `destinations.yaml` filled with Pair A's real coordinates

---

*This plan is a living document — update it in the same PR as any interface or scope change, so both people and Pair A stay synced against one source of truth.*
