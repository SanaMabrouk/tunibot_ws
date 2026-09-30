# TuniBot Backend (FastAPI)

REST API between the React UI and the Mission Manager node. It talks to ROS 2 only through
rosbridge, using the topics frozen in `PLAN.md` section 4.

## Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows  (Linux/WSL: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env           # optional, every setting has a default
```

## Run

**Fake mode** — no ROS needed. An in-memory robot runs the PLAN.md 6.1 state machine
(one transition every `FAKE_STEP_SECONDS`, battery return below 30%).

```bash
set FAKE_ROS=true              # PowerShell: $env:FAKE_ROS="true"
uvicorn main:app --reload
```

**ROS mode** — start rosbridge first (in WSL / on the ROS machine):

```bash
source /opt/ros/humble/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

then `uvicorn main:app --reload`. The API starts even when rosbridge is down and keeps
reconnecting in the background; `/health` shows the connection state.

Swagger UI: http://localhost:8000/docs

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/delivery` | `{"order_id": "ORD-001", "destination": "room_a"}` → publishes `/delivery_request`. `order_id` is optional (generated as `ORD-001`, `ORD-002`, …). Unknown destination → `422`, rosbridge down → `503`. |
| GET | `/robot/status` | Latest `/robot_status`: `state`, `battery`, `current_order`, plus `last_update` (null until the first message) and `connected`. |
| GET | `/destinations` | Valid destination names, for the UI dropdown. |
| GET | `/health` | `{"api": "ok", "rosbridge": "connected"\|"disconnected", "mode": "ros"\|"fake"}` |

```bash
curl -X POST localhost:8000/delivery -H "Content-Type: application/json" -d "{\"destination\": \"room_a\"}"
curl localhost:8000/robot/status
```

## Destinations

Read from `src/mission_manager/config/destinations.yaml` (owned by Person 1; top-level keys
are the names). Until that file exists, the backend uses `dock`, `kitchen`, `room_a`, `room_b`
and logs a warning. Restart the backend after the file changes.

## Configuration

| Env var | Default |
|---|---|
| `ROSBRIDGE_HOST` / `ROSBRIDGE_PORT` | `localhost` / `9090` |
| `FAKE_ROS` | `false` |
| `FAKE_STEP_SECONDS` | `2` |
| `DESTINATIONS_FILE` | `../src/mission_manager/config/destinations.yaml` |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` |

## Tests

```bash
pytest
```

Tests use fake links only; no ROS or rosbridge needed.

## Checking against real ROS (PLAN.md day 2)

```bash
# WSL, while the backend runs in ROS mode
ros2 topic echo /delivery_request std_msgs/msg/String
ros2 topic pub --once /robot_status std_msgs/msg/String "{data: '{\"state\": \"NAVIGATING\", \"battery\": 85.0, \"current_order\": \"ORD-001\"}'}"
```
