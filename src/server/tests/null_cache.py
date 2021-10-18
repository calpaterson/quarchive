from typing import Optional

from pyappcache.cache import Cache


class NullCache(Cache):
    """A "null" version of a pyappcache cache, which never has a cache hit."""

    def get_raw(self, key_str: str) -> Optional[bytes]:
        return None

    def set_raw(self, key_str: str, value_bytes: bytes, ttl_seconds: int) -> None:
        return None

    def invalidate_raw(self, key_str: str) -> None:
        return None

    def clear(self) -> None:
        return None
