from datetime import datetime, timedelta
from dataclasses import asdict as dataclass_as_dict

import quartermarker as sut

import pytest

from .conftest import make_bookmark


def test_adding_new_bookmark(client):
    response = client.post("/sync", json={"bookmarks": [make_bookmark().to_json()]},)
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


def test_syncing_bookmark_that_already_exists_with_no_changes(client):
    bm = make_bookmark()
    client.post("/sync", json={"bookmarks": [bm.to_json()]})

    response = client.post("/sync", json={"bookmarks": [bm.to_json()]})
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


def test_syncing_bookmark_that_already_exists_but_has_changed(client):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2", updated=datetime(1970, 1, 1) + timedelta(seconds=1)
    )

    # First put updated bookmark inside
    client.post("/sync", json={"bookmarks": [bm_2.to_json()]})

    # Then send the old version
    response = client.post("/sync", json={"bookmarks": [bm_1.to_json()]})
    assert response.json == {"bookmarks": [bm_2.to_json()]}


def test_syncing_bookmark_that_already_exists_but_is_old(client):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(
        title="Example 2", updated=datetime(1970, 1, 1) + timedelta(seconds=1)
    )

    # First put the bookmark
    client.post("/sync", json={"bookmarks": [bm_1.to_json()]})

    # Then send the new version
    response = client.post("/sync", json={"bookmarks": [bm_2.to_json()]})
    assert response.json == {"bookmarks": []}

    # Then send the old version again - should get new back
    response = client.post("/sync", json={"bookmarks": [bm_1.to_json()]})
    assert response.json == {"bookmarks": [bm_2.to_json()]}
