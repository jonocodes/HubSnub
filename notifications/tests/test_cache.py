from django.test import TestCase

from notifications import cache


class TestCache(TestCase):
    def setUp(self):
        cache.clear()

    def test_put_and_get(self):
        cache.put("myorg/repo:42", "thread-123")
        self.assertEqual(cache.get("myorg/repo:42"), "thread-123")

    def test_get_missing_key(self):
        self.assertIsNone(cache.get("nonexistent"))

    def test_size(self):
        self.assertEqual(cache.size(), 0)
        cache.put("key1", "val1")
        cache.put("key2", "val2")
        self.assertEqual(cache.size(), 2)

    def test_clear(self):
        cache.put("key1", "val1")
        cache.clear()
        self.assertEqual(cache.size(), 0)
        self.assertIsNone(cache.get("key1"))

    def test_eviction_at_max_size(self):
        # Use a smaller max for testing
        original_max = cache.MAX_CACHE_SIZE
        try:
            cache.MAX_CACHE_SIZE = 3
            cache.put("key1", "val1")
            cache.put("key2", "val2")
            cache.put("key3", "val3")
            cache.put("key4", "val4")  # should evict key1
            self.assertIsNone(cache.get("key1"))
            self.assertEqual(cache.get("key4"), "val4")
            self.assertEqual(cache.size(), 3)
        finally:
            cache.MAX_CACHE_SIZE = original_max

    def test_lru_ordering(self):
        original_max = cache.MAX_CACHE_SIZE
        try:
            cache.MAX_CACHE_SIZE = 3
            cache.put("key1", "val1")
            cache.put("key2", "val2")
            cache.put("key3", "val3")
            # Access key1 to make it recently used
            cache.get("key1")
            cache.put("key4", "val4")  # should evict key2 (least recently used)
            self.assertIsNone(cache.get("key2"))
            self.assertEqual(cache.get("key1"), "val1")
        finally:
            cache.MAX_CACHE_SIZE = original_max
