import json
from datetime import datetime
from urllib.parse import quote_plus, urlencode, parse_qs
from typing import Optional, List, Iterator, Mapping
from logging import getLogger


from quarchive.value_objects import (
    URL,
    Discussion,
    DiscussionSource,
    Request,
    Response,
    HTTPVerb,
)

log = getLogger(__name__)

ALGOLIA_BASE_URL = URL.from_string("https://hn.algolia.com/api/v1/search")


def get_hn_api_url(original_url: URL) -> URL:
    quoted = quote_plus(original_url.to_string())
    relative = f"?query={quoted}&restrictSearchableAttributes=url"
    return ALGOLIA_BASE_URL.follow(relative)


def extract_hn_discussions(response_body: Mapping) -> Iterator[Discussion]:
    # FIXME: Check the url matches what we expect - to avoid putting irrelevant
    # stuff in the db
    log.debug("hn search api returned: %s", response_body)
    for hit in response_body["hits"]:
        yield Discussion(
            comment_count=hit.get("num_comments", 0),
            created_at=datetime.utcfromtimestamp(hit["created_at_i"]),
            external_id=hit["objectID"],
            title=hit.get("title", ""),
            url=URL.from_string(hit["url"], coerce_canonicalisation=True),
            source=DiscussionSource.HN,
        )


def hn_turn_page(url: URL, response_body: Mapping) -> Optional[Request]:
    final_page = response_body["nbPages"] - 1
    current_page = response_body["page"]
    if current_page < final_page:
        q_dict = parse_qs(url.query)
        q_dict["page"] = current_page + 1
        new_url = url.follow("?" + urlencode(q_dict, doseq=True))
        return Request(verb=HTTPVerb.GET, url=new_url)
    return None
