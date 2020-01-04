import math
from lxml import etree
from lxml.cssselect import CSSSelector

import pytest

from .conftest import make_bookmark, working_cred_headers
from .utils import sync_bookmarks

pytestmark = pytest.mark.web


def test_sign_in_success(client):
    sign_in_form_response = client.get("/sign-in")
    assert sign_in_form_response.status_code == 200

    sign_in_response = client.post(
        "/sign-in",
        data={"username": "cal@calpaterson.com", "password": "test_password"},
    )
    assert sign_in_response.status_code == 303
    assert sign_in_response.headers["Location"] == "http://localhost/"

    index_response = client.get("/")
    assert index_response.status_code == 200


def test_sign_in_failure(client):
    sign_in_response = client.post(
        "/sign-in",
        data={"username": "cal@calpaterson.com", "password": "wrong_password"},
    )
    assert sign_in_response.status_code == 400


def test_unsigned_in_index(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sign-in")


def test_index(signed_in_client):
    bm = make_bookmark()

    sync_bookmarks(signed_in_client, [bm])

    response = signed_in_client.get("/")
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    (bookmark,) = CSSSelector("div.bookmark")(root)
    assert bookmark is not None


def test_index_paging(app, signed_in_client):
    page_size = app.config["PAGE_SIZE"]

    bms = [
        make_bookmark(url="http://example.com/%s" % i)
        for i in range(math.floor(page_size * 2.5))
    ]

    sync_bookmarks(signed_in_client, bms)

    signed_in_client.post(
        "/sync",
        json={"bookmarks": [bm.to_json() for bm in bms]},
        headers=working_cred_headers,
    )

    response_pg1 = signed_in_client.get("/")
    assert response_pg1.status_code == 200

    html_parser = etree.HTMLParser()
    root_pg1 = etree.fromstring(response_pg1.get_data(), html_parser)
    bookmarks_pg1 = CSSSelector("div.bookmark")(root_pg1)
    assert len(bookmarks_pg1) == page_size

    response_pg3 = signed_in_client.get("/?page=3")
    assert response_pg1.status_code == 200

    root_pg3 = etree.fromstring(response_pg3.get_data(), html_parser)
    bookmarks_pg3 = CSSSelector("div.bookmark")(root_pg3)
    assert len(bookmarks_pg3) == math.floor(0.5 * page_size)
