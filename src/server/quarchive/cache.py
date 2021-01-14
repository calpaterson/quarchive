import pylibmc
from pyappcache.memcache import MemcacheCache
from pyappcache.cache import Cache

_cache = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        client = pylibmc.Client(["127.0.0.1"], binary=True)
        _cache = MemcacheCache(client)
        _cache.prefix = "/quarchive/"
    return _cache
