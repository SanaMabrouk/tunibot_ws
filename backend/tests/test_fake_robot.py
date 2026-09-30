def run_until(robot, state, max_steps=50):
    for _ in range(max_steps):
        if robot.status.snapshot()["state"] == state:
            return
        robot.step()
    raise AssertionError(f"never reached {state}")


def test_single_order_full_cycle(fake_robot):
    fake_robot.publish_delivery("ORD-001", "room_a")
    seen = [fake_robot.status.snapshot()["state"]]
    for _ in range(7):
        fake_robot.step()
        seen.append(fake_robot.status.snapshot()["state"])
    assert seen == [
        "QUEUED", "NAVIGATING", "DELIVERING", "RETURNING", "DOCKING", "DOCKED", "IDLE", "IDLE",
    ]


def test_orders_are_processed_fifo(fake_robot):
    fake_robot.publish_delivery("ORD-001", "room_a")
    fake_robot.publish_delivery("ORD-002", "room_b")
    fake_robot.step()
    assert fake_robot.status.snapshot()["current_order"] == "ORD-001"
    fake_robot.step()  # DELIVERING
    fake_robot.step()  # next order
    snap = fake_robot.status.snapshot()
    assert (snap["state"], snap["current_order"]) == ("NAVIGATING", "ORD-002")


def test_low_battery_forces_return_and_keeps_order(fake_robot):
    fake_robot._battery = 31.0
    fake_robot.publish_delivery("ORD-001", "kitchen")
    fake_robot.step()  # battery 28 < 30: override before the order starts
    snap = fake_robot.status.snapshot()
    assert snap["state"] == "RETURNING"
    assert snap["current_order"] is None
    run_until(fake_robot, "DOCKED")
    fake_robot.step()  # charged
    assert fake_robot.status.snapshot()["battery"] == 100.0
    run_until(fake_robot, "NAVIGATING")
    assert fake_robot.status.snapshot()["current_order"] == "ORD-001"


def test_battery_drains_only_while_working(fake_robot):
    fake_robot.step()  # idle at dock
    assert fake_robot.status.snapshot()["battery"] == 100.0
    fake_robot.publish_delivery("ORD-001", "room_a")
    fake_robot.step()
    fake_robot.step()
    assert fake_robot.status.snapshot()["battery"] == 94.0
