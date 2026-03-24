import time
import unittest

from core.cache import ExpiringStore


class ExpiringStoreTests(unittest.TestCase):
    def test_set_and_get_value(self):
        store = ExpiringStore(ttl=60)
        store.set("key", "value")

        self.assertEqual(store.get("key"), "value")
        self.assertTrue(store.contains("key"))

    def test_expired_value_is_removed(self):
        store = ExpiringStore(ttl=0)
        store.set("key", "value")

        time.sleep(0.01)

        self.assertIsNone(store.get("key"))
        self.assertFalse(store.contains("key"))

    def test_pop_returns_default_for_missing_or_expired_value(self):
        store = ExpiringStore(ttl=0)
        store.set("key", "value")

        time.sleep(0.01)

        self.assertEqual(store.pop("key", "fallback"), "fallback")

    def test_negative_ttl_is_rejected(self):
        with self.assertRaises(ValueError):
            ExpiringStore(ttl=-1)


if __name__ == "__main__":
    unittest.main()
