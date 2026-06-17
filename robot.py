"""MedicalRobot: an autonomous agent with its own thread and task queue."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

from medical_task import MedicalTask

logger = logging.getLogger("medbot.robot")

# Sentinel enqueued to wake a blocked worker so it can exit cleanly.
_STOP = object()


@dataclass
class RobotStats:
    """Per-robot run results, used to show how work was balanced."""

    processed: int = 0      # tasks actually carried out
    abandoned: int = 0      # queued tasks dropped by an immediate stop
    busy_seconds: float = 0.0  # cumulative simulated processing time


class MedicalRobot:
    """A robot agent that processes medical tasks one at a time on its own thread.

    The task queue is a ``queue.Queue`` (already thread-safe), so the dispatcher
    can submit tasks concurrently while the robot consumes them. The worker
    thread is the only writer of ``stats``, so the values can be read safely by
    the main thread once :meth:`join` has returned.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.stats = RobotStats()
        self._queue: "queue.Queue" = queue.Queue()
        self._stopping = threading.Event()
        self._drain = True  # whether a pending stop should finish queued tasks
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        logger.info("%s 启动", self.name)
        self._thread.start()

    def submit(self, task: MedicalTask) -> None:
        """Thread-safe enqueue of a task."""
        self._queue.put(task)

    def queue_depth(self) -> int:
        """Advisory load hint (Queue.qsize is approximate under concurrency)."""
        return self._queue.qsize()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    break
                if self._stopping.is_set() and not self._drain:
                    # Immediate stop: abandon work still sitting in the queue.
                    self.stats.abandoned += 1
                    continue
                self._process(item)
            finally:
                self._queue.task_done()
        logger.info(
            "%s 已停止 (处理 %d / 放弃 %d)",
            self.name,
            self.stats.processed,
            self.stats.abandoned,
        )

    def _process(self, task: MedicalTask) -> None:
        logger.info("%s ▶ 开始处理 %s", self.name, task.describe())
        time.sleep(task.duration)  # simulate real medical work
        self.stats.processed += 1
        self.stats.busy_seconds += task.duration
        logger.info("%s ✔ 完成 %s", self.name, task.describe())

    def stop(self, drain: bool = True) -> None:
        """Request a graceful stop.

        With ``drain=True`` (default) the robot finishes already-queued tasks
        first. With ``drain=False`` it abandons pending tasks and stops after the
        task currently in progress. Either way the sentinel guarantees a blocked,
        idle robot unblocks and exits promptly.
        """
        self._drain = drain
        self._stopping.set()
        self._queue.put(_STOP)

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout)
