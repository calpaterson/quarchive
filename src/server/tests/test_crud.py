import flask
from uuid import UUID
from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from quarchive import SQLABookmark

from .conftest import make_bookmark
from .utils import sync_bookmarks

pytestmark = pytest.mark.web


@freeze_time("2018-01-03")
@pytest.mark.parametrize("unread", [True, False])
def test_creating_a_bookmark(signed_in_client, session, unread):
    form_data = dict(
        url="http://example.com", title="Example", description="Example description"
    )
    if unread:
        form_data["unread"] = "on"
    response = signed_in_client.post(
        flask.url_for("quarchive.create_bookmark",), data=form_data
    )
    assert response.status_code == 303

    bookmark = session.query(SQLABookmark).one()
    assert response.headers["Location"].endswith(
        flask.url_for("quarchive.edit_bookmark", url_uuid=bookmark.url_uuid)
    )
    assert bookmark.title == form_data["title"]
    assert bookmark.description == form_data["description"]
    assert bookmark.unread == unread
    assert (
        bookmark.created
        == bookmark.updated
        == datetime(2018, 1, 3, tzinfo=timezone.utc)
    )


@pytest.mark.parametrize(
    "field, form_value, expected",
    [
        ("deleted", "on", True),
        ("unread", "on", True),
        ("title", "Something else", "Something else"),
        ("description", "A desc", "A desc"),
    ],
)
def test_editing_a_bookmark(signed_in_client, session, field, form_value, expected):
    bm = make_bookmark()

    sync_bookmarks(signed_in_client, [bm])

    (url_uuid,) = session.query(SQLABookmark.url_uuid).one()

    response = signed_in_client.post(
        flask.url_for(
            "quarchive.edit_bookmark", url_uuid=url_uuid, redirect_to="/test_location",
        ),
        data={field: form_value},
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "http://localhost/test_location"

    bookmark_obj = session.query(SQLABookmark).one()
    assert getattr(bookmark_obj, field) == expected


def test_editing_a_bookmark_that_doesnt_exist(signed_in_client):
    response = signed_in_client.post(
        flask.url_for(
            "quarchive.edit_bookmark",
            url_uuid=UUID("f" * 32),
            redirect_to="/test_location",
        ),
        data={"deleted": "on"},
    )
    assert response.status_code == 404
