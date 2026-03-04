import collections

MAX_CACHE_SIZE = 1000

# LRU cache mapping "owner/repo:number" → GitHub notification thread ID
_cache = collections.OrderedDict()


def get(key):
    """Get a thread ID from the cache. Moves key to end (most recently used)."""
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def put(key, thread_id):
    """Store a thread ID in the cache, evicting oldest if at capacity."""
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = thread_id
    while len(_cache) > MAX_CACHE_SIZE:
        _cache.popitem(last=False)


def items():
    """Return all cache entries as a list of (key, thread_id) tuples."""
    return list(_cache.items())


def size():
    """Return current cache size."""
    return len(_cache)


def max_size():
    """Return max cache size."""
    return MAX_CACHE_SIZE


def clear():
    """Clear the entire cache."""
    _cache.clear()
