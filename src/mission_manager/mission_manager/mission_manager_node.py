import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from mission_manager.delivery_queue import DeliveryQueue
from mission_manager.state_machine import MissionState
from mission_manager.destination_resolver import resolve

FAKE_DURATION = {
    MissionState.NAVIGATING: 5,
    MissionState.PICKING_UP: 2,
    MissionState.CHANGING_FLOOR: 4,
    MissionState.DELIVERING: 3,
    MissionState.RETURNING: 5,
    MissionState.DOCKING: 2,
    MissionState.DOCKED: 1,
}

PICKUP_POINT = 'reception'


class MissionManagerNode(Node):
    def __init__(self):
        super().__init__('mission_manager')
        self.state = MissionState.IDLE
        self.queue = DeliveryQueue()
        self.current_order = None
        self.current_floor = 0
        self.ticks_in_state = 0
        self.pending_final_destination = None

        self.create_subscription(
            String, '/delivery_request', self.on_delivery_request, 10)
        self.status_pub = self.create_publisher(String, '/robot_status', 10)
        self.create_timer(1.0, self.tick)

        self.get_logger().info('Mission Manager started, state=IDLE (at dock)')

    def set_state(self, new_state):
        self.get_logger().info(f'{self.state.value} -> {new_state.value}')
        self.state = new_state
        self.ticks_in_state = 0

    def on_delivery_request(self, msg):
        try:
            data = json.loads(msg.data)
            order_id = data['order_id']
            destination = data['destination']
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.get_logger().error(f'Invalid request ignored: {msg.data} ({e})')
            return

        try:
            resolve(destination)
        except ValueError as e:
            self.get_logger().error(f'Rejected: {e}')
            return

        self.queue.add(order_id, destination)
        self.get_logger().info(
            f'Queued {order_id} -> {destination} (queue size {self.queue.size()})')

        if self.state == MissionState.IDLE:
            self.set_state(MissionState.QUEUED)

    def go_to_pickup(self):
        """Head from wherever we are to reception, to collect the next order."""
        self.get_logger().info('Heading to reception for pickup')
        self.set_state(MissionState.NAVIGATING)

    def dispatch_next_order(self):
        order = self.queue.next()
        if order is None:
            self.set_state(MissionState.IDLE)
            return
        self.current_order = order
        self.go_to_pickup()

    def advance(self):
        s = self.state
        if s == MissionState.NAVIGATING:
            if self.current_order and not self.pending_final_destination:
                # just arrived at reception -> pick up the order
                self.pending_final_destination = self.current_order['destination']
                self.set_state(MissionState.PICKING_UP)
            elif self.pending_final_destination and \
                    resolve(self.pending_final_destination)['floor'] != self.current_floor:
                self.set_state(MissionState.CHANGING_FLOOR)
            else:
                self.set_state(MissionState.DELIVERING)

        elif s == MissionState.PICKING_UP:
            dest = resolve(self.pending_final_destination)
            self.set_state(MissionState.CHANGING_FLOOR
                            if dest['floor'] != self.current_floor
                            else MissionState.NAVIGATING)

        elif s == MissionState.CHANGING_FLOOR:
            dest = resolve(self.pending_final_destination)
            self.current_floor = dest['floor']
            self.get_logger().info(f'Now on floor {self.current_floor}')
            self.set_state(MissionState.NAVIGATING)

        elif s == MissionState.DELIVERING:
            self.current_order = None
            self.pending_final_destination = None
            if not self.queue.is_empty():
                self.dispatch_next_order()
            else:
                self.set_state(MissionState.RETURNING)

        elif s == MissionState.RETURNING:
            self.set_state(MissionState.DOCKING)
        elif s == MissionState.DOCKING:
            self.set_state(MissionState.DOCKED)
        elif s == MissionState.DOCKED:
            self.current_floor = 0
            self.set_state(MissionState.QUEUED
                            if not self.queue.is_empty()
                            else MissionState.IDLE)

    def tick(self):
        self.ticks_in_state += 1
        if self.state == MissionState.QUEUED:
            self.dispatch_next_order()
        elif (self.state in FAKE_DURATION
              and self.ticks_in_state >= FAKE_DURATION[self.state]):
            self.advance()
        self.publish_status()

    def publish_status(self):
        payload = {
            'state': self.state.value,
            'battery': 100.0,
            'current_order': (self.current_order['order_id']
                              if self.current_order else None),
            'floor': self.current_floor,
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MissionManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
