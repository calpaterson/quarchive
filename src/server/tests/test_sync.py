from datetime import datetime, timedelta, timezone
from dataclasses import asdict as dataclass_as_dict

import quarchive as sut

import pytest

from .conftest import make_bookmark, working_cred_headers


def test_no_credentials(client):
    response = client.post("/sync", json={"bookmarks": []},)
    assert response.status_code == 400


def test_wrong_credentials(client):
    response = client.post(
        "/sync",
        json={"bookmarks": []},
        headers={"X-QM-API-Username": "calpaterson", "X-QM-API-Key": "toblerone"},
    )
    assert response.status_code == 400


@pytest.mark.sync
def test_adding_new_bookmark(client):
    response = client.post(
        "/sync",
        json={"bookmarks": [make_bookmark().to_json()]},
        headers=working_cred_headers,
    )
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_with_no_changes(client):
    bm = make_bookmark()
    client.post(
        "/sync", json={"bookmarks": [bm.to_json()]}, headers=working_cred_headers
    )

    response = client.post(
        "/sync", json={"bookmarks": [bm.to_json()]}, headers=working_cred_headers
    )
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_but_has_changed(client):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2",
        updated=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
    )

    # First put updated bookmark inside
    client.post(
        "/sync", json={"bookmarks": [bm_2.to_json()]}, headers=working_cred_headers
    )

    # Then send the old version
    response = client.post(
        "/sync", json={"bookmarks": [bm_1.to_json()]}, headers=working_cred_headers
    )
    assert response.json == {"bookmarks": [bm_2.to_json()]}


@pytest.mark.sync
def test_syncing_bookmark_that_already_exists_but_is_old(client):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2",
        updated=datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1),
    )

    # First put the bookmark
    client.post(
        "/sync", json={"bookmarks": [bm_1.to_json()]}, headers=working_cred_headers
    )

    # Then send the new version
    response = client.post(
        "/sync", json={"bookmarks": [bm_2.to_json()]}, headers=working_cred_headers
    )
    assert response.json == {"bookmarks": []}

    # Then send the old version again - should get new back
    response = client.post(
        "/sync", json={"bookmarks": [bm_1.to_json()]}, headers=working_cred_headers
    )
    assert response.json == {"bookmarks": [bm_2.to_json()]}


@pytest.mark.full_sync
def test_full_sync_gets_all(client):
    bm_1 = make_bookmark()

    # First, sync the bookmark
    client.post(
        "/sync", json={"bookmarks": [bm_1.to_json()]}, headers=working_cred_headers
    )

    # Then resync giving nothing
    full_sync_response = client.post(
        "/sync?full=true", headers=working_cred_headers, json={"bookmarks": []}
    )
    assert full_sync_response.json == {"bookmarks": [bm_1.to_json()]}
