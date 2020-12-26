from datetime import datetime, timezone

import flask
from lxml import etree
from lxml.cssselect import CSSSelector

from quarchive.value_objects import URL

from .conftest import make_bookmark
from .utils import sync_bookmarks, get_bookmarks_from_response


def test_user_tags_page(signed_in_client, test_user):
    epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    bm1 = make_bookmark(
        url=URL.from_string("http://example.com/pokemon"),
        title="Pokemon",
        tag_triples=frozenset([("pokemon", epoch_start, False)]),
    )
    bm2 = make_bookmark(
        url=URL.from_string("http://example.com/digimon"),
        title="Digimon",
        tag_triples=frozenset([("digimon", epoch_start, False)]),
    )

    sync_bookmarks(signed_in_client, test_user, [bm1, bm2])

    response = signed_in_client.get(
        flask.url_for("quarchive.user_tag", username=test_user.username, tag="pokemon")
    )
    assert response.status_code == 200

    (present,) = get_bookmarks_from_response(response)
    assert present["url"] == "http://example.com/pokemon"
    assert present["title"] == "Pokemon"


def test_tags_page(signed_in_client, test_user):
    # FIXME: include deleted, etc
    epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    bm1 = make_bookmark(
        url=URL.from_string("http://example.com/pokemon"),
        title="Pokemon",
        tag_triples=frozenset([("pokemon", epoch_start, False)]),
    )
    bm2 = make_bookmark(
        url=URL.from_string("http://example.com/digimon"),
        title="Digimon",
        tag_triples=frozenset([("digimon", epoch_start, False)]),
    )

    sync_bookmarks(signed_in_client, test_user, [bm1, bm2])

    response = signed_in_client.get(
        flask.url_for("quarchive.user_tags", username=test_user.username)
    )
    assert response.status_code == 200

    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    tags = set([e.text for e in CSSSelector(".tag-link")(root)])

    assert {"pokemon", "digimon"} == tags
