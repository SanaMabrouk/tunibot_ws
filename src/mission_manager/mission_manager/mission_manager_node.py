import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from mission_manager.delivery_queue import DeliveryQueue
from mission_manager.state_machine import MissionState


class MissionManagerNode(Node):
    def __init__(self):
        super().__init__('mission_manager')
        self.state = MissionState.IDLE
        self.queue = DeliveryQueue()
        self.current_order = None

        self.create_subscription(
            String, '/delivery_request', self.on_delivery_request, 10)
        self.status_pub = self.create_publisher(String, '/robot_status', 10)
        self.create_timer(1.0, self.tick)

        self.get_logger().info('Mission Manager started, state=IDLE')

    def set_state(self, new_state):
        self.get_logger().info(f'{self.state.value} -> {new_state.value}')
        self.state = new_state

    def on_delivery_request(self, msg):
        try:
            data = json.loads(msg.data)
            order_id = data['order_id']
            destination = data['destination']
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.get_logger().error(
                f'Invalid request ignored: {msg.data} ({e})')
            return

        self.queue.add(order_id, destination)
        self.get_logger().info(
            f'Queued {order_id} -> {destination} '
            f'(queue size {self.queue.size()})')

        if self.state == MissionState.IDLE:
            self.set_state(MissionState.QUEUED)

    def tick(self):
        if self.state == MissionState.QUEUED:
            self.dispatch_next_order()
        self.publish_status()

    def dispatch_next_order(self):
        order = self.queue.next()
        if order is None:
            self.set_state(MissionState.IDLE)
            return
        self.current_order = order
        self.get_logger().info(
            f'Dispatching {order["order_id"]} -> {order["destination"]}')
        self.set_state(MissionState.NAVIGATING)

    def publish_status(self):
        payload = {
            'state': self.state.value,
            'battery': 100.0,
            'current_order': (self.current_order['order_id']
                              if self.current_order else None),
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
