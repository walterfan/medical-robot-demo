"""TaskDispatcher: load-aware round-robin assignment of tasks to robots."""

from __future__ import annotations

import logging
import time
from typing import List

from medical_task import MedicalTask
from robot import MedicalRobot

logger = logging.getLogger("medbot.dispatcher")


class TaskDispatcher:
    """Assigns tasks round-robin, preferring robots below a capacity threshold.

    If every robot's queue is at/above ``capacity``, the dispatcher reports that
    the fleet is busy and waits (backoff + retry) instead of overloading anyone.
    """

    def __init__(
        self,
        robots: List[MedicalRobot],
        capacity: int = 5,
        wait_seconds: float = 0.5,
    ) -> None:
        if not robots:
            raise ValueError("至少需要一个机器人")
        self.robots = robots
        self.capacity = capacity
        self.wait_seconds = wait_seconds
        self._next = 0  # rotating round-robin cursor

    def _pick_under_capacity(self) -> MedicalRobot | None:
        """Return the next round-robin robot with queue depth < capacity."""
        n = len(self.robots)
        for offset in range(n):
            robot = self.robots[(self._next + offset) % n]
            if robot.queue_depth() < self.capacity:
                self._next = (self._next + offset + 1) % n
                return robot
        return None

    def dispatch(self, task: MedicalTask) -> MedicalRobot:
        """Assign one task, waiting if all robots are currently full."""
        while True:
            robot = self._pick_under_capacity()
            if robot is not None:
                robot.submit(task)
                logger.info(
                    "派发 %s → %s (队列深度=%d)",
                    task.describe(),
                    robot.name,
                    robot.queue_depth(),
                )
                return robot
            logger.warning(
                "所有机器人队列已满(容量=%d)，请稍候 %.1fs 后重试...",
                self.capacity,
                self.wait_seconds,
            )
            time.sleep(self.wait_seconds)

    def dispatch_all(self, tasks: List[MedicalTask]) -> None:
        for task in tasks:
            self.dispatch(task)
