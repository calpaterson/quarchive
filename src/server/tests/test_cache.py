from quarchive.cache import get_cache
from quarchive.data.functions import UserUUIDToUserKey


def test_caching_user(test_user):
    cache = get_cache()
    key = UserUUIDToUserKey(test_user.user_uuid)

    cache.set(key, test_user)

    assert cache.get(key) == test_user
