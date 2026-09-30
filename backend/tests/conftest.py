import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings  # noqa: E402
from main import create_app  # noqa: E402
from ros_bridge_client import FakeRobot, RosNotConnectedError, StatusStore  # noqa: E402


class RecordingLink:
    """Stands in for rosbridge: records what would be published."""

    mode = "ros"

    def __init__(self, connected=True):
        self.status = StatusStore()
        self.published = []
        self._connected = connected

    @property
    def connected(self):
        return self._connected

    def start(self):
        pass

    def stop(self):
        pass

    def publish_delivery(self, order_id, destination):
        if not self._connected:
            raise RosNotConnectedError("rosbridge not connected")
        self.published.append({"order_id": order_id, "destination": destination})


@pytest.fixture
def settings(tmp_path):
    # Point at a file that doesn't exist so tests use the default destinations.
    return Settings(_env_file=None, destinations_file=tmp_path / "missing.yaml")


@pytest.fixture
def link():
    return RecordingLink()


@pytest.fixture
def client(settings, link):
    with TestClient(create_app(settings, link)) as c:
        yield c


@pytest.fixture
def fake_robot():
    # Huge step interval: tests call step() themselves.
    return FakeRobot(step_seconds=3600)
