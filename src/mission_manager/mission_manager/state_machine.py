from enum import Enum


class MissionState(Enum):
    IDLE = "IDLE"
    QUEUED = "QUEUED"
    NAVIGATING = "NAVIGATING"
    DELIVERING = "DELIVERING"
    RETURNING = "RETURNING"
    DOCKING = "DOCKING"
    DOCKED = "DOCKED"
