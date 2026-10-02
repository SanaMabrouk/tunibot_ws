import math


class SimpleNavigator:
    """Open-loop move-to-target: compute bearing+distance ONCE, then
    execute a timed turn followed by a timed drive. No continuous
    feedback during motion -- avoids any possibility of oscillation."""

    def __init__(self, linear_speed=0.3, angular_speed=0.5):
        self.linear_speed = linear_speed
        self.angular_speed = angular_speed

    def plan(self, current_x, current_y, current_yaw, target_x, target_y):
        """Call ONCE when starting a move. Returns (turn_duration_s, drive_duration_s)."""
        dx = target_x - current_x
        dy = target_y - current_y
        distance = math.hypot(dx, dy)

        target_yaw = math.atan2(dy, dx)
        yaw_error = target_yaw - current_yaw
        yaw_error = math.atan2(math.sin(yaw_error), math.cos(yaw_error))

        turn_duration = abs(yaw_error) / self.angular_speed
        drive_duration = distance / self.linear_speed
        turn_direction = 1.0 if yaw_error > 0 else -1.0

        return turn_duration, drive_duration, turn_direction

    def turn_cmd(self, turn_direction):
        return 0.0, self.angular_speed * turn_direction

    def drive_cmd(self):
        return self.linear_speed, 0.0
