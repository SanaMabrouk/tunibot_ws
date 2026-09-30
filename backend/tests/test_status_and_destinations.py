from destinations import DEFAULT_DESTINATIONS, load_destinations
from ros_bridge_client import StatusStore


def test_malformed_status_keeps_last_good_value():
    store = StatusStore()
    assert store.update_from_json('{"state": "IDLE", "battery": 90, "current_order": null}')
    for bad in ["not json", "[]", '{"battery": 50}', '{"state": 3}', '{"state": "IDLE", "battery": "x"}']:
        assert not store.update_from_json(bad)
    snap = store.snapshot()
    assert snap["state"] == "IDLE"
    assert snap["battery"] == 90.0


def test_destinations_read_from_yaml(tmp_path):
    f = tmp_path / "destinations.yaml"
    f.write_text("dock: {x: 0.0, y: 0.0, yaw: 0.0}\nlobby: {x: 1.0, y: 2.0, yaw: 0.0}\n")
    assert load_destinations(f) == ["dock", "lobby"]


def test_destinations_fall_back_when_missing_or_invalid(tmp_path):
    assert load_destinations(tmp_path / "nope.yaml") == DEFAULT_DESTINATIONS
    bad = tmp_path / "bad.yaml"
    bad.write_text("dock: [unclosed")
    assert load_destinations(bad) == DEFAULT_DESTINATIONS
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    assert load_destinations(empty) == DEFAULT_DESTINATIONS
