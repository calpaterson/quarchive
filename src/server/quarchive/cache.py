from uuid import UUID

import pylibmc
from pyappcache.keys import Key
from pyappcache.memcache import MemcacheCache
from pyappcache.cache import Cache

from quarchive.value_objects import User

_cache = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        client = pylibmc.Client(["127.0.0.1"])
        _cache = MemcacheCache(client)
        _cache.prefix = "/quarchive/"
    return _cache