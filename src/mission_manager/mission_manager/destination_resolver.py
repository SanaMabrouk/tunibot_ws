import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config' / 'destinations.yaml'

with open(_CONFIG_PATH, encoding='utf-8') as f:
    _DESTINATIONS = yaml.safe_load(f)


def resolve(name):
    if name not in _DESTINATIONS:
        raise ValueError(f'Unknown destination: {name}')
    return _DESTINATIONS[name]
