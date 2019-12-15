import math
from lxml import etree
from lxml.cssselect import CSSSelector

from .conftest import make_bookmark


def test_index(client):
    bm = make_bookmark()

    client.post("/sync", json={"bookmarks": [bm.to_json()]})

    response = client.get("/")
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    (bookmark,) = CSSSelector("p.bookmark")(root)
    assert bookmark is not None


def test_index_paging(app, client):
    page_size = app.config["PAGE_SIZE"]

    bms = [
        make_bookmark(url="http://example.com/%s" % i)
        for i in range(math.floor(page_size * 2.5))
    ]

    client.post("/sync", json={"bookmarks": [bm.to_json() for bm in bms]})

    response_pg1 = client.get("/")
    assert response_pg1.status_code == 200

    html_parser = etree.HTMLParser()
    root_pg1 = etree.fromstring(response_pg1.get_data(), html_parser)
    bookmarks_pg1 = CSSSelector("p.bookmark")(root_pg1)
    assert len(bookmarks_pg1) == page_size

    response_pg3 = client.get("/?page=3")
    assert response_pg1.status_code == 200

    root_pg3 = etree.fromstring(response_pg3.get_data(), html_parser)
    bookmarks_pg3 = CSSSelector("p.bookmark")(root_pg3)
    assert len(bookmarks_pg3) == math.floor(0.5 * page_size)
