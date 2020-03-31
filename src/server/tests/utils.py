from typing import Iterable

from quarchive import Bookmark

from .conftest import User


def sync_bookmarks(client, user: User, bookmarks: Iterable[Bookmark]):
    response = client.post(
        "/sync",
        json={"bookmarks": [bookmark.to_json() for bookmark in bookmarks]},
        headers={
            "X-QM-API-Username": user.username,
            "X-QM-API-Key": user.api_key.hex(),
        },
    )
    assert response.status_code == 200
