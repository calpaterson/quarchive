from dataclasses import dataclass, asdict as dataclass_as_dict

import quartermarker as sut

import pytest


@pytest.fixture()
def app():
    a = sut.app
    a.config["TESTING"] = True
    return a


@pytest.fixture(autouse=True)
def ensure_clean_tables(app):
    sut.DATA_STORE.clear()


def make_bookmark(**kwargs):
    values = {"url": "http://example.com", "title": "Example", "timestamp": 0}
    values.update(kwargs)
    return sut.Bookmark(**values)


def test_adding_new_bookmark(client):
    response = client.post("/sync", json={"bookmarks": [make_bookmark()]},)
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


def test_syncing_bookmark_that_already_exists_with_no_changes(client):
    bm = make_bookmark()
    client.post("/sync", json={"bookmarks": [bm]})

    response = client.post("/sync", json={"bookmarks": [bm]})
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


def test_syncing_bookmark_that_already_exists_but_has_changed(client):
    bm_1 = make_bookmark()
    bm_2 = make_bookmark(title="Example 2", timestamp=1)

    # First put updated bookmark inside
    client.post("/sync", json={"bookmarks": [bm_2]})

    # Then send the old version
    response = client.post("/sync", json={"bookmarks": [bm_1]})
    assert response.json == {"bookmarks": [dataclass_as_dict(bm_2)]}
