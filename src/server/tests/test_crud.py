from urllib.parse import urlsplit
from uuid import UUID
from datetime import datetime, timezone

import flask
import pytest
from freezegun import freeze_time

import quarchive as sut

from .conftest import make_bookmark, random_string
from .utils import sync_bookmarks

pytestmark = pytest.mark.web


def test_create_bookmark_form(signed_in_client):
    response = signed_in_client.get(flask.url_for("quarchive.create_bookmark_form"))
    assert response.status_code == 200


@freeze_time("2018-01-03")
@pytest.mark.parametrize("unread", [True, False])
def test_creating_a_bookmark(test_user, signed_in_client, session, unread):
    url = "http://example.com/" + random_string()
    form_data = dict(url=url, title="Example", description="Example description")
    if unread:
        form_data["unread"] = "on"
    response = signed_in_client.post(
        flask.url_for("quarchive.create_bookmark",), data=form_data
    )
    assert response.status_code == 303

    bookmark = sut.get_bookmark_by_url(session, test_user.user_uuid, url)
    assert bookmark is not None

    assert response.headers["Location"].endswith(
        flask.url_for(
            "quarchive.edit_bookmark", url_uuid=str(sut.create_url_uuid(bookmark.url))
        )
    )
    assert bookmark.title == form_data["title"]
    assert bookmark.description == form_data["description"]
    assert bookmark.unread == unread
    assert (
        bookmark.created
        == bookmark.updated
        == datetime(2018, 1, 3, tzinfo=timezone.utc)
    )


@freeze_time("2018-01-03")
def test_edit_bookmark_form(signed_in_client, session, test_user):
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])

    url_uuid = sut.create_url_uuid(bm.url)

    response = signed_in_client.get(
        flask.url_for("quarchive.edit_bookmark", url_uuid=url_uuid)
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "field, start_value, form_value, expected",
    [
        ("deleted", False, "on", True),
        ("deleted", True, None, False),
        ("unread", False, "on", True),
        ("unread", True, None, False),
        ("title", "example", "Something else", "Something else"),
        ("description", "example desc", "A desc", "A desc"),
    ],
)
def test_editing_a_bookmark(
    signed_in_client, session, test_user, field, start_value, form_value, expected
):
    bm_args = {field: start_value}
    bm = make_bookmark(**bm_args)

    sync_bookmarks(signed_in_client, test_user, [bm])

    url_uuid = sut.create_url_uuid(bm.url)
    form_data = {
        "title": bm.title,
        "description": bm.description,
        # "unread": False and "deleted": False are by default
    }
    if form_value is not None:
        form_data[field] = form_value

    response = signed_in_client.post(
        flask.url_for(
            "quarchive.edit_bookmark", url_uuid=url_uuid, redirect_to="/test_location",
        ),
        data=form_data,
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "http://localhost/test_location"

    bookmark_obj = sut.get_bookmark_by_url(session, test_user.user_uuid, bm.url)
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
