from typing import Iterable, List, Tuple

from quarchive import Bookmark

from lxml import etree
from lxml.cssselect import CSSSelector

from .conftest import ExtendedUser


def sync_bookmarks(client, user: ExtendedUser, bookmarks: Iterable[Bookmark]):
    response = client.post(
        "/sync",
        json={"bookmarks": [bookmark.to_json() for bookmark in bookmarks]},
        headers={
            "Quarchive-Username": user.username,
            "Quarchive-API-Key": user.api_key.hex(),
        },
    )
    assert response.status_code == 200


def get_bookmarks_from_response(response) -> List[Tuple[str, str]]:
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    # Perhaps there should be a class used in the html for this
    bookmarks = CSSSelector(".bookmark-title")(root)
    return [(e.attrib["href"], e.text) for e in bookmarks]
