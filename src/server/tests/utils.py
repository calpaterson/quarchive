from typing import Iterable, Any, Dict, List, Mapping
import re

from quarchive import Bookmark

from lxml import etree
from lxml.cssselect import CSSSelector

from .conftest import ExtendedUser, random_url, random_numeric_id


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


def get_bookmarks_from_response(response) -> List[Dict[str, Any]]:
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)

    backlinks_selector = CSSSelector(".bookmark-backlink-count")
    links_selector = CSSSelector(".bookmark-link-count")
    title_selector = CSSSelector(".bookmark-title")

    bookmark_elems = CSSSelector(".bookmark")(root)

    rv = []
    for bookmark_elem in bookmark_elems:
        as_shown_dict = {}
        (title_elem,) = title_selector(bookmark_elem)
        as_shown_dict["url"] = title_elem.attrib["href"]
        as_shown_dict["title"] = title_elem.text
        as_shown_dict["link_count"] = _get_count(links_selector(bookmark_elem))
        as_shown_dict["backlink_count"] = _get_count(backlinks_selector(bookmark_elem))
        rv.append(as_shown_dict)

    return rv


def _get_count(elems):
    """Pull out \\d from a selector's return value (list of 1 elem)"""
    regex = re.compile(r"(\d+) .*")
    if len(elems) == 0:
        return 0
    elif len(elems) > 1:
        raise RuntimeError("wrongly used")
    else:
        match_obj = regex.match(elems[0].text)
        count = int(match_obj.groups()[0])  # type: ignore
        return count


def make_algolia_hit(**kwargs) -> Mapping:
    rv = {
        "created_at": "2018-01-03T09:00:00.000Z",
        "created_at_i": 1514970000,
        "num_comments": 1,
        "objectID": random_numeric_id(),
        "title": "Example",
        "url": random_url().to_string(),
    }
    rv.update(kwargs)
    return rv


def make_algolia_resp(**kwargs) -> Mapping:
    url_str = random_url().to_string()
    rv = {
        "exhaustiveNbHits": True,
        "hits": [make_algolia_hit(url=url_str)],
        "hitsPerPage": 20,
        "nbHits": 1,
        "nbPages": 1,
        "page": 0,
        "query": url_str,
    }
    rv.update(kwargs)
    return rv
