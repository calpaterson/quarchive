import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence
import json
import logging

import quarchive as sut

import pytest

from .conftest import make_bookmark, random_string


def test_check_api_key_user_does_not_exist(client, session):
    username = random_string()
    response = client.post(
        "/api/sync/check-api-key",
        headers={"Quarchive-Username": username, "Quarchive-API-Key": "deadbeef",},
    )
    assert response.status_code == 400
    assert response.json == {"error": "user does not exist"}


def test_check_api_key_no_credentials(client, session):
    response = client.post("/api/sync/check-api-key")
    assert response.status_code == 400
    assert response.json == {"error": "no api credentials"}


def test_check_api_key_wrong_api_key(client, session, test_user):
    response = client.post(
        "/api/sync/check-api-key",
        headers={
            "Quarchive-Username": test_user.username,
            "Quarchive-API-Key": "deadbeef",
        },
    )
    assert response.status_code == 400
    assert response.json == {"error": "bad api key"}  # FIXME: error could be better


def test_check_api_key_right_creds(client, session, test_user):
    response = client.post(
        "/api/sync/check-api-key",
        headers={
            "Quarchive-Username": test_user.username,
            "Quarchive-API-Key": test_user.api_key.hex(),
        },
    )
    assert response.status_code == 200
    assert response.json == {}


def test_no_credentials(client, session):
    response = client.post("/sync", json={"bookmarks": []},)
    assert response.status_code == 400


def test_wrong_credentials(client, session, test_user):
    response = client.post(
        "/sync",
        json={"bookmarks": []},
        headers={
            "Quarchive-Username": test_user.username,
            "Quarchive-API-Key": "deadbeef",
        },
    )
    assert response.status_code == 400


def post_bookmarks(
    client, user, bookmarks: Sequence[sut.Bookmark], full=False, use_jsonlines=False
):
    if full:
        url = "/sync?full=true"
    else:
        url = "/sync"

    if use_jsonlines:
        kwargs = dict(
            data="\n".join(json.dumps(b.to_json()) for b in bookmarks),
            headers={
                "Content-Type": "application/ndjson",
                "Quarchive-Username": user.username,
                "Quarchive-API-Key": user.api_key.hex(),
            },
        )

    else:
        kwargs = dict(
            json={"bookmarks": [b.to_json() for b in bookmarks]},
            headers={
                "Quarchive-Username": user.username,
                "Quarchive-API-Key": user.api_key.hex(),
            },
        )

    return client.post(url, **kwargs)


@pytest.fixture(params=[True, False], ids=["jsonlines", "legacy json"])
def use_jl(request):
    return request.param


def to_jl(bookmarks: Sequence[sut.Bookmark]) -> bytes:
    return "\n".join(json.dumps(b.to_json()) for b in bookmarks).encode("utf-8") + b"\n"


@pytest.mark.sync
def test_adding_new_bookmark(client, session, use_jl, test_user):
    response = post_bookmarks(
        client, test_user, [make_bookmark()], use_jsonlines=use_jl
    )

    assert response.status_code == 200

    if use_jl:
        assert response.data == b""
    else:
        assert response.json == {"bookmarks": []}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_with_no_changes(
    client, session, use_jl, test_user
):
    bm = make_bookmark()
    post_bookmarks(client, test_user, [bm], use_jsonlines=use_jl)

    response = post_bookmarks(client, test_user, [bm], use_jsonlines=use_jl)
    assert response.status_code == 200
    if use_jl:
        assert response.data == b""
    else:
        assert response.json == {"bookmarks": []}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_but_has_changed(
    client, session, use_jl, test_user
):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2",
        updated=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
        url=bm_1.url,
    )

    # First put updated bookmark inside
    post_bookmarks(client, test_user, [bm_2], use_jsonlines=use_jl)

    # Then send the old version
    response = post_bookmarks(client, test_user, [bm_1], use_jsonlines=use_jl)
    if use_jl:
        assert response.data == to_jl([bm_2])
    else:
        assert response.json == {"bookmarks": [bm_2.to_json()]}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_but_is_old(
    client, session, use_jl, test_user
):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2",
        updated=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
        url=bm_1.url,
    )

    # First put the bookmark
    post_bookmarks(client, test_user, [bm_1], use_jsonlines=use_jl)

    # Then send the new version
    response = post_bookmarks(client, test_user, [bm_2], use_jsonlines=use_jl)
    if use_jl:
        assert response.data == b""
    else:
        assert response.json == {"bookmarks": []}

    # Then send the old version again - should get new back
    response = post_bookmarks(client, test_user, [bm_1], use_jsonlines=use_jl)
    if use_jl:
        assert response.data == to_jl([bm_2])
    else:
        assert response.json == {"bookmarks": [bm_2.to_json()]}


@pytest.mark.full_sync
def test_multiple_bookmarks(client, session, use_jl, test_user):
    bm_1 = make_bookmark(
        url=sut.URL.from_string("http://example/com/1"), title="Example 1"
    )
    bm_2 = make_bookmark(
        url=sut.URL.from_string("http://example/com/2"), title="Example 2"
    )

    response = post_bookmarks(
        client, test_user, [bm_1, bm_2], use_jsonlines=use_jl, full=True
    )

    if use_jl:
        assert set(response.data.split(b"\n")) == set(to_jl([bm_1, bm_2]).split(b"\n"))
    else:
        assert bm_1.to_json() in response.json["bookmarks"]
        assert bm_2.to_json() in response.json["bookmarks"]


@pytest.mark.full_sync
def test_full_sync_gets_all(client, session, use_jl, test_user):
    bm_1 = make_bookmark()

    # First, sync the bookmark
    post_bookmarks(client, test_user, [bm_1], use_jsonlines=use_jl)

    # Then resync giving nothing
    full_sync_response = post_bookmarks(
        client, test_user, [], full=True, use_jsonlines=use_jl
    )
    if use_jl:
        assert full_sync_response.data == to_jl([bm_1])
    else:
        assert full_sync_response.json == {"bookmarks": [bm_1.to_json()]}


@pytest.mark.full_sync
def test_logging_for_bug_6(client, caplog, session, test_user):
    bm = make_bookmark()
    bm_json = dict(bm.to_json())
    bm_json["updated"] = "+051979-10-24T11:59:23.000Z"

    with caplog.at_level(logging.ERROR) as e:
        with pytest.raises(ValueError):
            client.post(
                "/sync",
                json={"bookmarks": [bm_json]},
                headers={
                    "Quarchive-Username": test_user.username,
                    "Quarchive-API-Key": test_user.api_key.hex(),
                },
            )

        messages = [r.getMessage() for r in caplog.records]

        expected_message = (
            "Got invalid datetime: [+051979-10-24T11:59:23.000Z,"
            " 1970-01-01T00:00:00+00:00] for %s" % bm.url.to_string()
        )

        assert expected_message in messages


def test_syncing_with_an_extension_that_doesnt_know_about_tags(
    client, session, test_user
):
    """This test checks that syncs from extensions that don't know about tags
    don't clober existing tags."""
    url = sut.URL.from_string("http://example/com/1")
    bm_1 = make_bookmark(url=url, title="Example 1")

    initial_sync = post_bookmarks(client, test_user, [bm_1])
    assert initial_sync.status_code == 200

    bm_1_no_tags = sut.Bookmark(
        url=url,
        title=bm_1.title,
        description=bm_1.description,
        created=bm_1.created,
        updated=bm_1.updated,
        unread=bm_1.unread,
        deleted=bm_1.deleted,
        tag_triples=frozenset(),
    )
    second_sync = post_bookmarks(client, test_user, [bm_1_no_tags])
    assert second_sync.status_code == 200

    end_state = sut.get_bookmark_by_url(session, test_user.user_uuid, url.to_string())
    assert end_state == bm_1


@pytest.mark.parametrize(
    "problem_url", [pytest.param("http://example.com#", id="empty fragment")]
)
def test_syncing_with_urls_without_minimum_canonicalisation(
    client, session, test_user, caplog, problem_url
):
    """The urls without minimum canonicalisation (basically: where urlunsplit
    is not a clean undo of urlsplit) are not accepted"""
    caplog.set_level(logging.ERROR, logger="quarchive.web.blueprint")
    bm_json = dict(make_bookmark().to_json())
    bm_json["url"] = problem_url

    response = client.post(
        "/sync",
        data=json.dumps(bm_json),
        headers={
            "Content-Type": "application/ndjson",
            "Quarchive-Username": test_user.username,
            "Quarchive-API-Key": test_user.api_key.hex(),
        },
    )

    assert response.status_code == 400
    # FIXME: something is pulling other log messages in here.
    assert "bad canonicalised url" in caplog.text
