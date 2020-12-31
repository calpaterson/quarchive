import json
from datetime import datetime
from urllib.parse import quote_plus
from typing import Optional, List
from logging import getLogger

from sqlalchemy.orm import Session

from quarchive.io import RewindingIO
from quarchive.value_objects import URL, Discussion, DiscussionSource
from quarchive.data.functions import upsert_discussions

log = getLogger(__name__)

ALGOLIA_BASE_URL = URL.from_string("https://hn.algolia.com/api/v1/search")


def get_hn_api_url(original_url: URL) -> URL:
    quoted = quote_plus(original_url.to_string())
    relative = f"?query={quoted}&restrictSearchableAttributes=url"
    return ALGOLIA_BASE_URL.follow(relative)


def upsert_hn_discussions(session: Session, body: RewindingIO) -> None:
    # FIXME: Check the url matches what we expect - to avoid putting irrelevant
    # stuff in the db
    with body as f:
        document = json.load(f)
    log.debug("hn search api returned: %s", document)
    discussions: List[Discussion] = []
    for hit in document["hits"]:
        discussions.append(
            Discussion(
                comment_count=hit.get("num_comments", 0),
                created_at=datetime.utcfromtimestamp(hit["created_at_i"]),
                external_id=hit["objectID"],
                title=hit.get("title", ""),
                url=URL.from_string(hit["url"], coerce_canonicalisation=True),
                source=DiscussionSource.HN,
            )
        )
    upsert_discussions(session, discussions)


def hn_turn_page(hn_api_url: URL) -> Optional[URL]:
    ...
