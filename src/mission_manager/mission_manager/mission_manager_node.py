import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from mission_manager.state_machine import MissionState


class MissionManagerNode(Node):
    def __init__(self):
        super().__init__('mission_manager')
        self.state = MissionState.IDLE

        self.create_subscription(
            String, '/delivery_request', self.on_delivery_request, 10)
        self.status_pub = self.create_publisher(String, '/robot_status', 10)
        self.create_timer(1.0, self.publish_status)

        self.get_logger().info('Mission Manager started, state=IDLE')

    def on_delivery_request(self, msg):
        self.get_logger().info(f'Received request: {msg.data}')

    def publish_status(self):
        payload = {
            'state': self.state.value,
            'battery': 100.0,
            'current_order': None,
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
