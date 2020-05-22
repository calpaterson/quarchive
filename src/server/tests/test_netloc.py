from datetime import datetime, timezone

import flask
from lxml import etree
from lxml.cssselect import CSSSelector

from .conftest import make_bookmark
from .utils import sync_bookmarks, get_bookmarks_from_response


def test_user_netloc_page(signed_in_client, test_user):
    epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    bm1 = make_bookmark(
        url="http://pokemon.com/",
        title="Pokemon",
        tag_triples=frozenset([("pokemon", epoch_start, False)]),
    )
    bm2 = make_bookmark(
        url="http://digimon.com/",
        title="Digimon",
        tag_triples=frozenset([("digimon", epoch_start, False)]),
    )

    sync_bookmarks(signed_in_client, test_user, [bm1, bm2])

    response = signed_in_client.get(
        flask.url_for(
            "quarchive.user_netloc", username=test_user.username, netloc="pokemon.com"
        )
    )
    assert response.status_code == 200

    present = get_bookmarks_from_response(response)
    assert present == [("http://pokemon.com/", "Pokemon")]
