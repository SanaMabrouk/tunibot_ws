"""Link between the API and the robot.

RosBridgeClient talks to Mission Manager through rosbridge (roslibpy).
FakeRobot is an in-memory stand-in used with FAKE_ROS=true and in tests.
Both expose the same interface, so main.py doesn't care which one it has.

Topics (PLAN.md section 4, frozen):
  /delivery_request  std_msgs/String  {"order_id": "ORD-001", "destination": "room_a"}  (we publish)
  /robot_status      std_msgs/String  {"state": "NAVIGATING", "battery": 85.0, "current_order": "ORD-001"}  (we subscribe)
"""

import json
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Protocol

import roslibpy
from roslibpy.core import RosTimeoutError

logger = logging.getLogger(__name__)

DELIVERY_REQUEST_TOPIC = "/delivery_request"
ROBOT_STATUS_TOPIC = "/robot_status"
STRING_MSG_TYPE = "std_msgs/String"


class RosNotConnectedError(Exception):
    """Raised when publishing while rosbridge is unreachable."""


class StatusStore:
    """Latest /robot_status, safe to update from the ROS callback thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = "UNKNOWN"
        self._battery: Optional[float] = None
        self._current_order: Optional[str] = None
        self._last_update: Optional[datetime] = None

    def update_from_json(self, raw: str) -> bool:
        """Parse a /robot_status payload. Malformed payloads are logged and ignored."""
        try:
            data = json.loads(raw)
            state = data["state"]
            battery = data.get("battery")
            current_order = data.get("current_order")
            if not isinstance(state, str):
                raise ValueError("state must be a string")
            if battery is not None:
                battery = float(battery)
            if current_order is not None and not isinstance(current_order, str):
                raise ValueError("current_order must be a string or null")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as e:
            logger.warning("Ignoring malformed %s payload %r: %s", ROBOT_STATUS_TOPIC, raw, e)
            return False

        with self._lock:
            self._state = state
            self._battery = battery
            self._current_order = current_order
            self._last_update = datetime.now(timezone.utc)
        return True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "battery": self._battery,
                "current_order": self._current_order,
                "last_update": self._last_update,
            }


class RobotLink(Protocol):
    mode: str
    status: StatusStore

    @property
    def connected(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def publish_delivery(self, order_id: str, destination: str) -> None: ...


class RosBridgeClient:
    """Connects to rosbridge; roslibpy keeps retrying and re-subscribes after reconnects."""

    mode = "ros"

    def __init__(self, host: str, port: int, connect_timeout: float = 5.0):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.status = StatusStore()
        self._ros: Optional[roslibpy.Ros] = None
        self._delivery_pub: Optional[roslibpy.Topic] = None

    @property
    def connected(self) -> bool:
        return self._ros is not None and self._ros.is_connected

    def start(self) -> None:
        self._ros = roslibpy.Ros(host=self.host, port=self.port)
        self._delivery_pub = roslibpy.Topic(self._ros, DELIVERY_REQUEST_TOPIC, STRING_MSG_TYPE)
        status_sub = roslibpy.Topic(self._ros, ROBOT_STATUS_TOPIC, STRING_MSG_TYPE)
        status_sub.subscribe(self._on_status)

        # Connect in the background so the API starts even when rosbridge is down.
        threading.Thread(target=self._connect, name="rosbridge-connect", daemon=True).start()

    def _connect(self) -> None:
        try:
            self._ros.run(timeout=self.connect_timeout)
            logger.info("Connected to rosbridge at %s:%s", self.host, self.port)
        except RosTimeoutError:
            logger.warning(
                "rosbridge not reachable at %s:%s, retrying in the background", self.host, self.port
            )

    def _on_status(self, msg: dict) -> None:
        self.status.update_from_json(msg.get("data", ""))

    def stop(self) -> None:
        if self._ros is None:
            return
        try:
            self._ros.terminate()
        except Exception:  # shutting down anyway
            logger.exception("Error while closing rosbridge connection")

    def publish_delivery(self, order_id: str, destination: str) -> None:
        if not self.connected:
            raise RosNotConnectedError(f"rosbridge not connected at {self.host}:{self.port}")
        payload = json.dumps({"order_id": order_id, "destination": destination})
        self._delivery_pub.publish(roslibpy.Message({"data": payload}))
        logger.info("Published %s %s", DELIVERY_REQUEST_TOPIC, payload)


class FakeRobot:
    """Simulates Mission Manager (PLAN.md section 6.1) so the API and UI work without ROS.

    Every step advances the state machine one transition and drains the battery.
    Status goes through StatusStore.update_from_json, the same path as real ROS messages.
    """

    mode = "fake"

    BATTERY_DRAIN_PER_STEP = 3.0
    LOW_BATTERY_THRESHOLD = 30.0

    def __init__(self, step_seconds: float = 2.0):
        self.step_seconds = step_seconds
        self.status = StatusStore()
        self._lock = threading.Lock()
        self._queue: deque[dict] = deque()
        self._state = "IDLE"
        self._battery = 100.0
        self._current_order: Optional[str] = None
        self._current_item: Optional[dict] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._publish_status()

    @property
    def connected(self) -> bool:
        return True

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="fake-robot", daemon=True)
        self._thread.start()
        logger.info("FAKE_ROS enabled: simulating Mission Manager, one step every %ss", self.step_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.step_seconds + 1)

    def _run(self) -> None:
        while not self._stop.wait(self.step_seconds):
            self.step()

    def publish_delivery(self, order_id: str, destination: str) -> None:
        with self._lock:
            self._queue.append({"order_id": order_id, "destination": destination})
            if self._state == "IDLE":
                self._state = "QUEUED"
            self._publish_status()
        logger.info("Fake %s %s -> %s", DELIVERY_REQUEST_TOPIC, order_id, destination)

    def step(self) -> None:
        """Advance one transition. Public so tests can drive it without sleeping."""
        with self._lock:
            if self._state == "DOCKED":
                self._battery = 100.0
            elif self._state != "IDLE":  # idle means parked at the dock
                self._battery = max(0.0, self._battery - self.BATTERY_DRAIN_PER_STEP)

            low_battery = self._battery < self.LOW_BATTERY_THRESHOLD
            if low_battery and self._state not in ("DOCKED", "DOCKING", "RETURNING"):
                # Battery override: put the unfinished order back so it isn't lost.
                if self._current_order is not None and self._state == "NAVIGATING":
                    self._queue.appendleft(self._current_item)
                self._current_order = None
                self._state = "RETURNING"
            else:
                self._advance()
            self._publish_status()

    def _advance(self) -> None:
        s = self._state
        if s == "IDLE":
            if self._queue:
                self._state = "QUEUED"
        elif s == "QUEUED":
            self._start_next_order()
        elif s == "NAVIGATING":
            self._state = "DELIVERING"
        elif s == "DELIVERING":
            if self._queue:
                self._start_next_order()
            else:
                self._current_order = None
                self._state = "RETURNING"
        elif s == "RETURNING":
            self._state = "DOCKING"
        elif s == "DOCKING":
            self._state = "DOCKED"
        elif s == "DOCKED":
            self._state = "IDLE"

    def _start_next_order(self) -> None:
        self._current_item = self._queue.popleft()
        self._current_order = self._current_item["order_id"]
        self._state = "NAVIGATING"

    def _publish_status(self) -> None:
        self.status.update_from_json(
            json.dumps(
                {"state": self._state, "battery": self._battery, "current_order": self._current_order}
            )
        )
