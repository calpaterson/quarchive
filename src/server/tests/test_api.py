import quartermarker as sut

import pytest


@pytest.fixture()
def app():
    a = sut.app
    a.config["TESTING"] = True
    return a


def test_adding_new_bookmark(client):
    response = client.post("/sync", json={"bookmarks": [{"url": "http://example.com"}]})
    assert response.status_code == 200
    assert response.json == {"bookmarks": []}


@pytest.mark.xfail(reason="not implemented")
def test_syncing_bookmark_that_already_exists_with_no_changes(client):
    assert False
