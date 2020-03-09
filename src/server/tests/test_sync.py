from datetime import datetime, timedelta, timezone
from typing import Sequence
import json
import logging

import quarchive as sut

import pytest

from .conftest import make_bookmark, working_cred_headers


def test_no_credentials(client, session):
    response = client.post("/sync", json={"bookmarks": []},)
    assert response.status_code == 400


def test_wrong_credentials(client, session):
    response = client.post(
        "/sync",
        json={"bookmarks": []},
        headers={"X-QM-API-Username": "calpaterson", "X-QM-API-Key": "toblerone"},
    )
    assert response.status_code == 400


def post_bookmarks(
    client, bookmarks: Sequence[sut.Bookmark], full=False, use_jsonlines=False
):
    if full:
        url = "/sync?full=true"
    else:
        url = "/sync"

    if use_jsonlines:
        kwargs = dict(
            data="\n".join(json.dumps(b.to_json()) for b in bookmarks),
            headers={**working_cred_headers, **{"Content-Type": "application/ndjson"}},
        )
    else:
        kwargs = dict(
            json={"bookmarks": [b.to_json() for b in bookmarks]},
            headers=working_cred_headers,
        )

    return client.post(url, **kwargs)


@pytest.fixture(params=[True, False], ids=["jsonlines", "legacy json"])
def use_jl(request):
    return request.param


def to_jl(bookmarks: Sequence[sut.Bookmark]) -> bytes:
    return "\n".join(json.dumps(b.to_json()) for b in bookmarks).encode("utf-8") + b"\n"


@pytest.mark.sync
def test_adding_new_bookmark(client, session, use_jl):
    response = post_bookmarks(client, [make_bookmark()], use_jsonlines=use_jl)

    assert response.status_code == 200

    if use_jl:
        assert response.data == b""
    else:
        assert response.json == {"bookmarks": []}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_with_no_changes(client, session, use_jl):
    bm = make_bookmark()
    post_bookmarks(client, [bm], use_jsonlines=use_jl)

    response = post_bookmarks(client, [bm], use_jsonlines=use_jl)
    assert response.status_code == 200
    if use_jl:
        assert response.data == b""
    else:
        assert response.json == {"bookmarks": []}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_but_has_changed(client, session, use_jl):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2",
        updated=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
    )

    # First put updated bookmark inside
    post_bookmarks(client, [bm_2], use_jsonlines=use_jl)

    # Then send the old version
    response = post_bookmarks(client, [bm_1], use_jsonlines=use_jl)
    if use_jl:
        assert response.data == to_jl(
            [bm_2]
        )  # json.dumps(bm_2.to_json()).encode("utf-8")
    else:
        assert response.json == {"bookmarks": [bm_2.to_json()]}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_but_is_old(client, session, use_jl):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2",
        updated=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
    )

    # First put the bookmark
    post_bookmarks(client, [bm_1], use_jsonlines=use_jl)

    # Then send the new version
    response = post_bookmarks(client, [bm_2], use_jsonlines=use_jl)
    if use_jl:
        assert response.data == b""
    else:
        assert response.json == {"bookmarks": []}

    # Then send the old version again - should get new back
    response = post_bookmarks(client, [bm_1], use_jsonlines=use_jl)
    if use_jl:
        assert response.data == to_jl(
            [bm_2]
        )  # json.dumps(bm_2.to_json()).encode("utf-8")
    else:
        assert response.json == {"bookmarks": [bm_2.to_json()]}


@pytest.mark.full_sync
def test_multiple_bookmarks(client, session, use_jl):
    bm_1 = make_bookmark(url="http://example/com/1", title="Example 1")
    bm_2 = make_bookmark(url="http://example/com/2", title="Example 2")

    response = post_bookmarks(client, [bm_1, bm_2], use_jsonlines=use_jl, full=True)

    if use_jl:
        assert set(response.data.split(b"\n")) == set(to_jl([bm_1, bm_2]).split(b"\n"))
    else:
        assert bm_1.to_json() in response.json["bookmarks"]
        assert bm_2.to_json() in response.json["bookmarks"]


@pytest.mark.full_sync
def test_full_sync_gets_all(client, session, use_jl):
    bm_1 = make_bookmark()

    # First, sync the bookmark
    post_bookmarks(client, [bm_1], use_jsonlines=use_jl)

    # Then resync giving nothing
    full_sync_response = post_bookmarks(client, [], full=True, use_jsonlines=use_jl)
    if use_jl:
        assert full_sync_response.data == to_jl([bm_1])
    else:
        assert full_sync_response.json == {"bookmarks": [bm_1.to_json()]}


@pytest.mark.full_sync
def test_logging_for_bug_6(client, caplog, session):
    bm_json = make_bookmark().to_json()
    bm_json["updated"] = "+051979-10-24T11:59:23.000Z"

    with caplog.at_level(logging.ERROR) as e:
        with pytest.raises(ValueError):
            client.post(
                "/sync", json={"bookmarks": [bm_json]}, headers=working_cred_headers
            )

        messages = [r.getMessage() for r in caplog.records]

        assert (
            "Got invalid datetime: [+051979-10-24T11:59:23.000Z, 1970-01-01T00:00:00+00:00] for http://example.com"
            in messages
        )
