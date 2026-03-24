import unittest

from core.task_registry import UserTaskRegistry


class UserTaskRegistryTests(unittest.TestCase):
    def test_try_start_blocks_duplicate_user_task(self):
        registry = UserTaskRegistry()

        self.assertTrue(registry.try_start(123))
        self.assertFalse(registry.try_start(123))
        self.assertTrue(registry.is_active(123))

    def test_finish_releases_user_task(self):
        registry = UserTaskRegistry()
        registry.try_start(123)

        registry.finish(123)

        self.assertFalse(registry.is_active(123))
        self.assertTrue(registry.try_start(123))


if __name__ == "__main__":
    unittest.main()
