import math
from typing import List
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy.orm import Session
import flask
from lxml import etree
from lxml.cssselect import CSSSelector
from sqlalchemy import func

import pytest

from .conftest import (
    make_bookmark,
    register_user,
    sign_in_as,
    random_string,
)
from .utils import sync_bookmarks

import quarchive as sut
from quarchive.data.functions import upsert_links
from .utils import get_bookmarks_from_response

pytestmark = pytest.mark.web


def get_bookmark_titles(response) -> List[str]:
    """Returns a list of bookmark titles present in response"""
    return [b["title"] for b in get_bookmarks_from_response(response)]


def test_not_signed_in_my_bookmarks(client):
    response = client.get(flask.url_for("quarchive.my_bookmarks"))
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sign-in")


def test_redirect(signed_in_client, test_user):
    response = signed_in_client.get("/")
    assert response.status_code == 303
    assert response.headers["Location"] == flask.url_for(
        "quarchive.my_bookmarks", _external=True
    )


def test_my_bookmarks(signed_in_client, test_user):
    bm = make_bookmark()

    sync_bookmarks(signed_in_client, test_user, [bm])

    response = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    (bookmark,) = CSSSelector("div.bookmark")(root)
    assert bookmark is not None


def test_my_bookmarks_excludes_deleted_bookmarks(signed_in_client, session, test_user):
    bm = make_bookmark(deleted=True)

    sync_bookmarks(signed_in_client, test_user, [bm])

    response = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    bookmarks = CSSSelector("div.bookmark")(root)
    assert len(bookmarks) == 0


def test_my_bookmarks_excludes_bookmarks_from_others(app, client, session):
    bm1 = make_bookmark(title="Example 1")
    user1 = register_user(session, app, "test_user1" + random_string())
    sync_bookmarks(client, user1, [bm1])

    bm2 = make_bookmark(title="Example 2")
    user2 = register_user(session, app, "test_user1" + random_string())
    sync_bookmarks(client, user2, [bm2])

    sign_in_as(client, user2)
    response = client.get(flask.url_for("quarchive.my_bookmarks"))
    assert response.status_code == 200

    assert get_bookmark_titles(response) == ["Example 2"]


def test_my_bookmarks_paging(app, signed_in_client, session, test_user):
    page_size = app.config["PAGE_SIZE"]

    bms = (
        make_bookmark(url=sut.URL.from_string("http://example.com/%s" % i))
        for i in range(math.floor(page_size * 2.5))
    )

    sync_bookmarks(signed_in_client, test_user, bms)

    response_pg1 = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    assert response_pg1.status_code == 200

    html_parser = etree.HTMLParser()
    root_pg1 = etree.fromstring(response_pg1.get_data(), html_parser)
    bookmarks_pg1 = CSSSelector("div.bookmark")(root_pg1)
    assert len(bookmarks_pg1) == page_size

    response_pg3 = signed_in_client.get(flask.url_for("quarchive.my_bookmarks", page=3))
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
    bm2 = make_bookmark(url=sut.URL.from_string("http://test.com/"), title=title)

    sync_bookmarks(signed_in_client, test_user, [bm1, bm2])

    normal_response = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    assert len(get_bookmark_titles(normal_response)) == 2

    search_response = signed_in_client.get(
        flask.url_for("quarchive.my_bookmarks", q=search_str)
    )
    assert len(get_bookmark_titles(search_response)) == result_count


def make_fulltext_indexed_bookmark(
    session: Session, user: sut.User, bookmark: sut.Bookmark, full_text: str
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


def test_html_injection(app, signed_in_client, test_user):
    """Test to check that html put into bookmarks doesn't get put onto the
    pages unescaped.  Specific test for this because it is easy to regress.

    """
    html_string = "<blockquote>hi!</blockquote>"
    bm = make_bookmark(
        url=sut.URL.from_string("http://example.com/" + html_string),
        title=html_string,
        description=html_string,
    )

    sync_bookmarks(signed_in_client, test_user, [bm])

    response = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)

    selectors = [".bookmark-title", ".bookmark-url > a", ".bookmark-description"]
    for selector in selectors:
        element = CSSSelector(selector)(root)[0]
        assert element.getchildren() == []


def test_user_timezones_are_observed(session, app, client):
    bm1 = make_bookmark(title="Example 1")
    user1 = register_user(
        session, app, "test_user1" + random_string(), timezone="America/Los_Angeles"
    )
    sign_in_as(client, user1)
    sync_bookmarks(client, user1, [bm1])

    response = client.get(flask.url_for("quarchive.my_bookmarks"))
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    selector = CSSSelector(".bookmark-created")
    element = selector(root)[0]
    assert element.text == "4:00 pm"


def test_links_and_backlinks(session, signed_in_client, test_user):
    bm1 = make_bookmark()
    bm1_link1 = make_bookmark()
    bm1_link2 = make_bookmark()
    bm1_link3 = make_bookmark()
    bm1_backlinker1 = make_bookmark()
    bm1_backlinker2 = make_bookmark()
    sync_bookmarks(
        signed_in_client,
        test_user,
        [bm1, bm1_link1, bm1_link2, bm1_link3, bm1_backlinker1, bm1_backlinker2],
    )

    upsert_links(session, bm1.url, {bm1_link1.url, bm1_link2.url, bm1_link3.url})
    upsert_links(session, bm1_backlinker1.url, {bm1.url})
    upsert_links(session, bm1_backlinker2.url, {bm1.url})

    response = signed_in_client.get(flask.url_for("quarchive.my_bookmarks"))
    assert response.status_code == 200
    (bm1_as_shown,) = [
        b
        for b in get_bookmarks_from_response(response)
        if b["url"] == bm1.url.to_string()
    ]
    assert bm1_as_shown["link_count"] == 3
    assert bm1_as_shown["backlink_count"] == 2


def test_individual_bookmark(session, signed_in_client, test_user):
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])

    response = signed_in_client.get(
        flask.url_for(
            "quarchive.view_bookmark",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert response.status_code == 200

    as_shown = get_bookmark_titles(response)
    assert as_shown == [bm.title]
