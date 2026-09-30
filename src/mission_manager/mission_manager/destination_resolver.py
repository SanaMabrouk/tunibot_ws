DESTINATIONS = {
    'dock':    {'x': 0.0, 'y': 0.0, 'yaw': 0.0},
    'kitchen': {'x': 0.0, 'y': 0.0, 'yaw': 0.0},
    'room_a':  {'x': 0.0, 'y': 0.0, 'yaw': 0.0},
    'room_b':  {'x': 0.0, 'y': 0.0, 'yaw': 0.0},
}


def resolve(name):
    if name not in DESTINATIONS:
        raise ValueError(f'Unknown destination: {name}')
    return DESTINATIONS[name]
