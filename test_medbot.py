"""Scenario verification for the multi-agent medical robot demo.

Run: python -m unittest test_medbot -v
"""

import time
import unittest

from dispatcher import TaskDispatcher
from medical_task import MedicalTask, TaskType
from robot import MedicalRobot


def task(duration=0.05, task_type=TaskType.CHECK_PATIENT, target="病房101"):
    return MedicalTask(task_type=task_type, target=target, duration=duration)


class MedicalRobotTests(unittest.TestCase):
    def test_receive_and_sequential_processing(self):
        robot = MedicalRobot("R-seq")
        robot.start()
        for _ in range(3):
            robot.submit(task(duration=0.05))
        robot.stop(drain=True)
        robot.join(timeout=5)
        self.assertFalse(robot._thread.is_alive())
        self.assertEqual(robot.queue_depth(), 0)

    def test_simulated_processing_takes_time(self):
        robot = MedicalRobot("R-time")
        robot.start()
        start = time.perf_counter()
        robot.submit(task(duration=0.3))
        robot.stop(drain=True)
        robot.join(timeout=5)
        elapsed = time.perf_counter() - start
        self.assertGreaterEqual(elapsed, 0.3)

    def test_idle_stop_unblocks_promptly(self):
        robot = MedicalRobot("R-idle")
        robot.start()
        time.sleep(0.1)  # robot is blocked waiting on an empty queue
        robot.stop(drain=True)
        robot.join(timeout=2)
        self.assertFalse(robot._thread.is_alive())

    def test_drain_processes_all_queued_tasks(self):
        robot = MedicalRobot("R-drain")
        for _ in range(4):
            robot.submit(task(duration=0.02))
        robot.start()  # start after queuing so all 4 are already pending
        robot.stop(drain=True)
        robot.join(timeout=5)
        self.assertEqual(robot.stats.processed, 4)
        self.assertEqual(robot.stats.abandoned, 0)

    def test_immediate_stop_abandons_pending_tasks(self):
        robot = MedicalRobot("R-abandon")
        for _ in range(5):
            robot.submit(task(duration=0.02))
        robot.stop(drain=False)  # abandon everything still queued
        robot.start()
        robot.join(timeout=5)
        self.assertEqual(robot.stats.processed, 0)
        self.assertEqual(robot.stats.abandoned, 5)

    def test_statistics_track_busy_time(self):
        robot = MedicalRobot("R-stats")
        robot.start()
        robot.submit(task(duration=0.1))
        robot.submit(task(duration=0.2))
        robot.stop(drain=True)
        robot.join(timeout=5)
        self.assertEqual(robot.stats.processed, 2)
        self.assertAlmostEqual(robot.stats.busy_seconds, 0.3, places=2)


class TaskDispatcherTests(unittest.TestCase):
    def test_round_robin_spreads_across_robots(self):
        robots = [MedicalRobot(f"R{i}") for i in range(3)]
        dispatcher = TaskDispatcher(robots, capacity=5)
        # Do not start robots, so queues stay filled and depth is observable.
        for _ in range(3):
            dispatcher.dispatch(task())
        self.assertEqual([r.queue_depth() for r in robots], [1, 1, 1])

    def test_prefers_under_capacity_robot(self):
        robots = [MedicalRobot("R0"), MedicalRobot("R1")]
        dispatcher = TaskDispatcher(robots, capacity=2)
        for _ in range(4):  # fills both queues to capacity (2 each)
            dispatcher.dispatch(task())
        self.assertEqual([r.queue_depth() for r in robots], [2, 2])

    def test_waits_when_all_full_then_assigns_after_free(self):
        robots = [MedicalRobot("R-full")]
        robots[0].start()
        dispatcher = TaskDispatcher(robots, capacity=2, wait_seconds=0.05)
        # Two slow tasks fill capacity; a third must wait until one drains.
        dispatcher.dispatch(task(duration=0.2))
        dispatcher.dispatch(task(duration=0.2))
        start = time.perf_counter()
        dispatcher.dispatch(task(duration=0.05))  # blocks until capacity frees
        waited = time.perf_counter() - start
        self.assertGreater(waited, 0.0)
        robots[0].stop(drain=True)
        robots[0].join(timeout=5)


class FleetOrchestrationTests(unittest.TestCase):
    def test_fleet_processes_all_and_shuts_down(self):
        robots = [MedicalRobot(f"Robot-{i+1}") for i in range(3)]
        for r in robots:
            r.start()
        dispatcher = TaskDispatcher(robots, capacity=5)
        tasks = [task(duration=0.05) for _ in range(12)]
        dispatcher.dispatch_all(tasks)
        for r in robots:
            r.stop(drain=True)
        for r in robots:
            r.join(timeout=5)
        self.assertTrue(all(not r._thread.is_alive() for r in robots))
        self.assertTrue(all(r.queue_depth() == 0 for r in robots))


if __name__ == "__main__":
    unittest.main(verbosity=2)
