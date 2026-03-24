import threading
import unittest

from core.task_runner import BackgroundTaskRunner


class BackgroundTaskRunnerTests(unittest.TestCase):
    def test_executes_submitted_task(self):
        runner = BackgroundTaskRunner(max_workers=1, max_queue_size=0)
        try:
            future = runner.submit("simple", lambda: "ok")
            self.assertIsNotNone(future)
            self.assertEqual(future.result(timeout=1), "ok")
        finally:
            runner.shutdown()

    def test_rejects_task_when_capacity_is_full(self):
        started = threading.Event()
        release = threading.Event()

        def slow_task():
            started.set()
            release.wait(timeout=1)
            return "done"

        runner = BackgroundTaskRunner(max_workers=1, max_queue_size=0)
        try:
            first_future = runner.submit("slow", slow_task)
            self.assertIsNotNone(first_future)
            self.assertTrue(started.wait(timeout=1))

            second_future = runner.submit("overflow", lambda: "should_not_run")
            self.assertIsNone(second_future)
        finally:
            release.set()
            runner.shutdown()

    def test_rejects_task_after_shutdown_instead_of_raising(self):
        runner = BackgroundTaskRunner(max_workers=1, max_queue_size=0)
        runner.shutdown()

        self.assertIsNone(runner.submit("late", lambda: "should_not_run"))

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            BackgroundTaskRunner(max_workers=0)

        with self.assertRaises(ValueError):
            BackgroundTaskRunner(max_workers=1, max_queue_size=-1)


if __name__ == "__main__":
    unittest.main()
