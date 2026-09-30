"""TuniBot FastAPI backend: REST in front of Mission Manager (via rosbridge).

Run from backend/:
    uvicorn main:app --reload             # real ROS, needs rosbridge on :9090
    FAKE_ROS=true uvicorn main:app --reload   # no ROS needed
"""

import itertools
import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import Settings
from destinations import load_destinations
from models import (
    DeliveryRequest,
    DeliveryResponse,
    DestinationsResponse,
    HealthResponse,
    RobotStatus,
)
from ros_bridge_client import FakeRobot, RobotLink, RosBridgeClient, RosNotConnectedError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("tunibot.backend")


class OrderIdGenerator:
    """ORD-001, ORD-002, ... for requests that don't send an order_id."""

    def __init__(self):
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            return f"ORD-{next(self._counter):03d}"


def build_link(settings: Settings) -> RobotLink:
    if settings.fake_ros:
        return FakeRobot(step_seconds=settings.fake_step_seconds)
    return RosBridgeClient(
        settings.rosbridge_host, settings.rosbridge_port, settings.rosbridge_connect_timeout
    )


def create_app(settings: Optional[Settings] = None, link: Optional[RobotLink] = None) -> FastAPI:
    settings = settings or Settings()
    link = link or build_link(settings)
    destinations = load_destinations(settings.destinations_file)
    order_ids = OrderIdGenerator()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Mode: %s | destinations: %s", link.mode, destinations)
        link.start()
        yield
        link.stop()

    app = FastAPI(title="TuniBot Backend", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.post("/delivery", response_model=DeliveryResponse)
    def create_delivery(req: DeliveryRequest):
        if req.destination not in destinations:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown destination '{req.destination}'. Valid: {', '.join(destinations)}",
            )
        order_id = req.order_id or order_ids.next()
        try:
            link.publish_delivery(order_id, req.destination)
        except RosNotConnectedError as e:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
        return DeliveryResponse(status="queued", order_id=order_id)

    @app.get("/robot/status", response_model=RobotStatus)
    def robot_status():
        return RobotStatus(**link.status.snapshot(), connected=link.connected)

    @app.get("/destinations", response_model=DestinationsResponse)
    def list_destinations():
        return DestinationsResponse(destinations=destinations)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(
            api="ok",
            rosbridge="connected" if link.connected else "disconnected",
            mode=link.mode,
        )

    return app


app = create_app()
