from datetime import datetime

import flask

from quarchive.data.functions import set_bookmark
from quarchive.data.discussion_functions import upsert_discussions
from quarchive.value_objects import Discussion, DiscussionSource

from .conftest import make_bookmark, random_numeric_id


def test_discussions(signed_in_client, test_user, session):
    bm = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm)

    discussions = [
        Discussion(
            external_id=str(random_numeric_id()),
            source=DiscussionSource.HN,
            url=bm.url,
            comment_count=1,
            created_at=datetime(2018, 1, 3),
            title="HN discussion 1",
        )
    ]

    upsert_discussions(session, discussions)

    response = signed_in_client.get(
        flask.url_for(
            "quarchive.discussions",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert response.status_code == 200
