import json
import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

from mission_manager.delivery_queue import DeliveryQueue
from mission_manager.state_machine import MissionState
from mission_manager.destination_resolver import resolve
from mission_manager.simple_navigator import SimpleNavigator

FAKE_DURATION = {
    MissionState.PICKING_UP: 2,
    MissionState.CHANGING_FLOOR: 4,
    MissionState.DELIVERING: 3,
    MissionState.DOCKING: 2,
    MissionState.DOCKED: 1,
}


def yaw_from_quaternion(z, w):
    return math.atan2(2.0 * w * z, 1.0 - 2.0 * z * z)


class MissionManagerNode(Node):
    def __init__(self):
        super().__init__('mission_manager')
        self.state = MissionState.IDLE
        self.queue = DeliveryQueue()
        self.current_order = None
        self.current_floor = 0
        self.ticks_in_state = 0
        self.pending_final_destination = None
        self.current_nav_target = None

        self.navigator = SimpleNavigator()
        self.current_pose = None

        self.nav_phase = None
        self.nav_phase_elapsed = 0.0
        self.nav_turn_duration = 0.0
        self.nav_drive_duration = 0.0
        self.nav_turn_direction = 1.0

        self.create_subscription(String, '/delivery_request', self.on_delivery_request, 10)
        self.create_subscription(Odometry, '/odom', self.on_odom, 10)

        self.status_pub = self.create_publisher(String, '/robot_status', 10)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.create_timer(0.2, self.tick)

        self.get_logger().info('Mission Manager started, state=IDLE (at dock)')

    def on_odom(self, msg):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        yaw = yaw_from_quaternion(msg.pose.pose.orientation.z, msg.pose.pose.orientation.w)
        self.current_pose = (x, y, yaw)

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
        self.get_logger().info(f'Queued {order_id} -> {destination} (queue size {self.queue.size()})')
        if self.state == MissionState.IDLE:
            self.set_state(MissionState.QUEUED)

    def go_to_pickup(self):
        self.get_logger().info('Heading to reception for pickup (real nav)')
        r = resolve('reception')
        self.current_nav_target = (r['x'], r['y'])
        self.nav_phase = None
        self.set_state(MissionState.NAVIGATING)

    def dispatch_next_order(self):
        order = self.queue.next()
        if order is None:
            self.set_state(MissionState.IDLE)
            return
        self.current_order = order
        self.pending_final_destination = None
        self.go_to_pickup()

    def start_nav_to_destination(self):
        dest = resolve(self.pending_final_destination)
        self.current_nav_target = (dest['x'], dest['y'])
        self.nav_phase = None
        self.get_logger().info(f'Navigating (real) to {self.pending_final_destination}')
        self.set_state(MissionState.NAVIGATING)

    def start_return_to_dock(self):
        dock = resolve('dock')
        self.current_nav_target = (dock['x'], dock['y'])
        self.nav_phase = None
        self.get_logger().info('Returning (real nav) to dock')
        self.set_state(MissionState.RETURNING)

    def run_navigation_step(self):
        if self.current_pose is None or self.current_nav_target is None:
            return False

        if self.nav_phase is None:
            x, y, yaw = self.current_pose
            tx, ty = self.current_nav_target
            turn_s, drive_s, direction = self.navigator.plan(x, y, yaw, tx, ty)
            self.nav_phase = 'turn'
            self.nav_phase_elapsed = 0.0
            self.nav_turn_duration = turn_s
            self.nav_drive_duration = drive_s
            self.nav_turn_direction = direction
            self.get_logger().info(f'NAV PLAN: turn {turn_s:.1f}s (dir={direction:+.0f}), then drive {drive_s:.1f}s')

        cmd = Twist()
        if self.nav_phase == 'turn':
            lin, ang = self.navigator.turn_cmd(self.nav_turn_direction)
            cmd.linear.x, cmd.angular.z = lin, ang
            self.nav_phase_elapsed += 0.2
            if self.nav_phase_elapsed >= self.nav_turn_duration:
                self.nav_phase = 'drive'
                self.nav_phase_elapsed = 0.0
        elif self.nav_phase == 'drive':
            lin, ang = self.navigator.drive_cmd()
            cmd.linear.x, cmd.angular.z = lin, ang
            self.nav_phase_elapsed += 0.2
            if self.nav_phase_elapsed >= self.nav_drive_duration:
                self.cmd_vel_pub.publish(Twist())
                self.nav_phase = None
                return True

        self.cmd_vel_pub.publish(cmd)
        return False

    def advance(self):
        s = self.state
        if s == MissionState.PICKING_UP:
            if self.pending_final_destination:
                dest = resolve(self.pending_final_destination)
                if dest['floor'] != self.current_floor:
                    self.set_state(MissionState.CHANGING_FLOOR)
                else:
                    self.start_nav_to_destination()
            else:
                self.set_state(MissionState.DELIVERING)
        elif s == MissionState.CHANGING_FLOOR:
            dest = resolve(self.pending_final_destination)
            self.current_floor = dest['floor']
            self.get_logger().info(f'Now on floor {self.current_floor}')
            self.start_nav_to_destination()
        elif s == MissionState.DELIVERING:
            self.current_order = None
            self.pending_final_destination = None
            if not self.queue.is_empty():
                self.dispatch_next_order()
            else:
                self.start_return_to_dock()
        elif s == MissionState.DOCKING:
            self.set_state(MissionState.DOCKED)
        elif s == MissionState.DOCKED:
            self.current_floor = 0
            self.set_state(MissionState.QUEUED if not self.queue.is_empty() else MissionState.IDLE)

    def tick(self):
        self.ticks_in_state += 1

        if self.state == MissionState.QUEUED:
            self.dispatch_next_order()
        elif self.state == MissionState.NAVIGATING:
            if self.current_order and not self.pending_final_destination:
                if self.run_navigation_step():
                    self.pending_final_destination = self.current_order['destination']
                    self.set_state(MissionState.PICKING_UP)
            else:
                if self.run_navigation_step():
                    self.set_state(MissionState.DELIVERING)
        elif self.state == MissionState.RETURNING:
            if self.run_navigation_step():
                self.set_state(MissionState.DOCKING)
        elif self.state in FAKE_DURATION and self.ticks_in_state * 0.2 >= FAKE_DURATION[self.state]:
            self.advance()

        self.publish_status()

    def publish_status(self):
        payload = {
            'state': self.state.value,
            'battery': 100.0,
            'current_order': self.current_order['order_id'] if self.current_order else None,
            'floor': self.current_floor,
            'pose': self.current_pose,
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
