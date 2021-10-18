from uuid import UUID

from pyappcache.keys import BaseKey


class UserBookmarksNamespaceKey(BaseKey):
    """This cache namespace is updated whenever a user changes their bookmarks."""

    def __init__(self, user_uuid: UUID):
        self.user_uuid = user_uuid

    def cache_key_segments(self):
        return [self.user_uuid.hex, "ub"]
