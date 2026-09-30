"""Valid delivery destinations, read from Mission Manager's destinations.yaml."""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# PLAN.md section 4. Used until Person 1 commits config/destinations.yaml.
DEFAULT_DESTINATIONS = ["dock", "kitchen", "room_a", "room_b"]


def load_destinations(path: Path) -> list[str]:
    """Return the destination names (top-level keys) from destinations.yaml."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("%s not found, using default destinations %s", path, DEFAULT_DESTINATIONS)
        return list(DEFAULT_DESTINATIONS)
    except yaml.YAMLError as e:
        logger.error("Could not parse %s (%s), using default destinations", path, e)
        return list(DEFAULT_DESTINATIONS)

    if not isinstance(data, dict) or not data:
        logger.error("%s has no destinations, using default destinations", path)
        return list(DEFAULT_DESTINATIONS)

    return [str(name) for name in data]
