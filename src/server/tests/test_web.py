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
