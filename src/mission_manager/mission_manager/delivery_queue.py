from collections import deque


class DeliveryQueue:
    """FIFO queue of accepted delivery orders."""

    def __init__(self):
        self._orders = deque()

    def add(self, order_id, destination):
        self._orders.append(
            {'order_id': order_id, 'destination': destination})

    def next(self):
        """Remove and return the oldest order, or None if empty."""
        return self._orders.popleft() if self._orders else None

    def is_empty(self):
        return len(self._orders) == 0

    def size(self):
        return len(self._orders)
