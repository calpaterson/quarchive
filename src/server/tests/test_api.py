import quartermarker as sut

import pytest


@pytest.fixture()
def app():
    a = sut.app
    a.config["TESTING"] = True
    return a


def test_adding_new_bookmark(client):
    response = client.post(
        "/sync",
        json={
            "bookmarks": [
                {"url": "http://example.com", "title": "Example", "timestamp": 0}
            ]
        },
    )
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


def test_syncing_bookmark_that_already_exists_with_no_changes(client):
    bm = {"url": "http://example.com", "title": "Example", "timestamp": 0}
    client.post("/sync", json={"bookmarks": [bm]})

    response = client.post("/sync", json={"bookmarks": [bm]})
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}
