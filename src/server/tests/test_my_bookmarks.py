import math
from typing import List
from uuid import uuid4
from datetime import datetime, timezone

import flask
from lxml import etree
from lxml.cssselect import CSSSelector
from sqlalchemy import func

import pytest

from .conftest import make_bookmark, User, register_user, sign_in_as, random_string
from .utils import sync_bookmarks

import quarchive as sut

pytestmark = pytest.mark.web


def get_bookmark_titles(response) -> List[str]:
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    # Perhaps there should be a class used in the html for this
    bookmarks = CSSSelector("div.bookmark>p:nth-child(1)>a:nth-child(1)")(root)
    return [b.text for b in bookmarks]


def test_not_signed_in_my_bookmarks(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sign-in")


def test_my_bookmarks(signed_in_client, test_user):
    bm = make_bookmark()

    sync_bookmarks(signed_in_client, test_user, [bm])

    response = signed_in_client.get("/")
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    (bookmark,) = CSSSelector("div.bookmark")(root)
    assert bookmark is not None


def test_my_bookmarks_excludes_deleted_bookmarks(signed_in_client, session, test_user):
    bm = make_bookmark(deleted=True)

    sync_bookmarks(signed_in_client, test_user, [bm])

    response = signed_in_client.get("/")
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    bookmarks = CSSSelector("div.bookmark")(root)
    assert len(bookmarks) == 0


def test_my_bookmarks_excludes_bookmarks_from_others(client, session):
    bm1 = make_bookmark(title="Example 1")
    user1 = register_user(session, client, "test_user1" + random_string())
    sync_bookmarks(client, user1, [bm1])

    bm2 = make_bookmark(title="Example 2")
    user2 = register_user(session, client, "test_user1" + random_string())
    sync_bookmarks(client, user2, [bm2])

    sign_in_as(client, user2)
    response = client.get("/")
    assert response.status_code == 200

    assert get_bookmark_titles(response) == ["Example 2"]


def test_my_bookmarks_paging(app, signed_in_client, session, test_user):
    page_size = app.config["PAGE_SIZE"]

    bms = (
        make_bookmark(url="http://example.com/%s" % i)
        for i in range(math.floor(page_size * 2.5))
    )

    sync_bookmarks(signed_in_client, test_user, bms)

    signed_in_client.post(
        "/sync",
        json={"bookmarks": [bm.to_json() for bm in bms]},
        headers={
            "X-QM-API-Username": test_user.username,
            "X-QM-API-Key": test_user.api_key.hex(),
        },
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


@pytest.mark.parametrize(
    "title,search_str,result_count",
    [("Test", "test", 1), ("Star wars", "star", 1), ("Star wars", "star trek", 0),],
)
def test_my_bookmarks_search(
    app, signed_in_client, session, test_user, title, search_str, result_count
):
    bm1 = make_bookmark()
    bm2 = make_bookmark(url="http://test.com", title=title)

    sync_bookmarks(signed_in_client, test_user, [bm1, bm2])

    normal_response = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    assert len(get_bookmark_titles(normal_response)) == 2

    search_response = signed_in_client.get(
        flask.url_for("quarchive.my_bookmarks", q=search_str)
    )
    assert len(get_bookmark_titles(search_response)) == result_count


def make_fulltext_indexed_bookmark(
    session: sut.Session, user: User, bookmark: sut.Bookmark, full_text: str
):
    # FIXME: this really shows the need for a library of common db functions
    url_uuid = sut.set_bookmark(session, user.user_uuid, bookmark)
    crawl_uuid = uuid4()
    body_uuid = uuid4()

    crawl_req = sut.CrawlRequest(
        crawl_uuid=crawl_uuid,
        url_uuid=url_uuid,
        requested=datetime(2018, 1, 3),
        got_response=True,
    )
    crawl_resp = sut.CrawlResponse(
        crawl_uuid=crawl_uuid,
        headers={"content-type": "text/html"},
        body_uuid=body_uuid,
        status_code=200,
    )
    fulltext_obj = sut.FullText(
        url_uuid=url_uuid,
        crawl_uuid=crawl_uuid,
        inserted=datetime.utcnow().replace(tzinfo=timezone.utc),
        full_text=full_text,
        tsvector=func.to_tsvector(full_text),
    )
    session.add_all([crawl_req, crawl_resp, fulltext_obj])


def test_full_text_search(app, signed_in_client, session, test_user):
    star_wars_bm = make_bookmark(title="star wars")
    star_trek_bm = make_bookmark(title="star trek")

    make_fulltext_indexed_bookmark(
        session, test_user, star_wars_bm, "wookies live on planet kashyyyk"
    )
    make_fulltext_indexed_bookmark(
        session, test_user, star_trek_bm, "red shirts usually perish"
    )
    session.commit()

    search_response = signed_in_client.get(
        flask.url_for("quarchive.my_bookmarks", q="wookies")
    )
    returned_bookmarks = get_bookmark_titles(search_response)
    assert returned_bookmarks == ["star wars"]


def test_full_text_search_with_quotes(app, signed_in_client, test_user):
    search_term = '"roger kimball"'

    search_response = signed_in_client.get(
        flask.url_for("quarchive.my_bookmarks", q=search_term)
    )

    html_parser = etree.HTMLParser()
    root = etree.fromstring(search_response.get_data(), html_parser)
    selector = CSSSelector("#search-box")
    (element,) = selector(root)
    assert element.attrib["value"] == search_term
