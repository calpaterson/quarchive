from datetime import datetime

import flask

from quarchive.value_objects import URL

from .conftest import make_bookmark
from .utils import sync_bookmarks


def test_archives(signed_in_client, test_user):
    url = URL.from_string("http://example.com/")
    bm = make_bookmark(url=url, created=datetime(2018, 1, 3))
    sync_bookmarks(signed_in_client, test_user, [bm])

    archive_response = signed_in_client.get(
        flask.url_for(
            "quarchive.bookmark_archives",
            url_uuid=url.url_uuid,
            username=test_user.username,
        )
    )

    assert archive_response.status_code == 200


def test_archives_doesnt_exist(signed_in_client, test_user):
    archive_response = signed_in_client.get(
        flask.url_for(
            "quarchive.bookmark_archives",
            url_uuid="f" * 32,
            username=test_user.username,
        )
    )

    assert archive_response.status_code == 404
