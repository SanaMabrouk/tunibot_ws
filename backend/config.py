"""Backend settings, read from environment variables or backend/.env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # rosbridge connection (ros2 launch rosbridge_server rosbridge_websocket_launch.xml)
    rosbridge_host: str = "localhost"
    rosbridge_port: int = 9090
    rosbridge_connect_timeout: float = 5.0

    # Run without ROS: an in-memory robot cycles through the mission states.
    fake_ros: bool = False
    fake_step_seconds: float = 2.0

    # Owned by Person 1 (Mission Manager). Falls back to the built-in list if missing.
    destinations_file: Path = REPO_ROOT / "src" / "mission_manager" / "config" / "destinations.yaml"

    # Comma-separated origins allowed to call the API (React dev servers).
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
