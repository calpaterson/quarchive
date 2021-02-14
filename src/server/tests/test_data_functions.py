from datetime import datetime, timezone
from uuid import uuid4

from quarchive.data.functions import (
    most_recent_successful_bookmark_crawls,
    set_bookmark,
    user_tags,
)
from quarchive.value_objects import URL
from quarchive.data.models import CrawlRequest, CrawlResponse, SQLAUrl
from .conftest import random_string, make_bookmark


def test_most_recent_successful_crawls(session, test_user):
    # Crawl 1 is an old crawl of url 1 (should not be present)
    # Crawl 2 is a more recent crawl of url 1
    # Crawl 3 is a crawl of url 3 that didn't get a response
    # Crawl 4 is a crawl that of url 4 returned a non-2xx status code
    # Only crawl 2 should be present

    url_1 = SQLAUrl.from_url(URL.from_string(f"http://example.com/{random_string()}"))
    bm_1 = make_bookmark(url=url_1.to_url())
    set_bookmark(session, test_user.user_uuid, bm_1)
    crawl_req_1 = CrawlRequest(  # type: ignore
        crawl_uuid=uuid4(),
        requested=datetime(2018, 1, 3),
        got_response=True,
        url_uuid=url_1.url_uuid,
        response_obj=CrawlResponse(body_uuid=uuid4(), headers={}, status_code=200),
    )
    crawl_req_2 = CrawlRequest(  # type: ignore
        crawl_uuid=uuid4(),
        requested=datetime(2018, 1, 4),
        got_response=True,
        url_uuid=url_1.url_uuid,
        response_obj=CrawlResponse(body_uuid=uuid4(), headers={}, status_code=200),
    )
    url_3 = SQLAUrl.from_url(URL.from_string(f"http://example.com/{random_string()}"))
    bm_3 = make_bookmark(url=url_3.to_url())
    set_bookmark(session, test_user.user_uuid, bm_3)
    crawl_req_3 = CrawlRequest(
        crawl_uuid=uuid4(),
        requested=datetime(2018, 1, 3),
        got_response=False,
        url_uuid=url_3.url_uuid,
    )
    url_4 = SQLAUrl.from_url(URL.from_string(f"http://example.com/{random_string()}"))
    bm_4 = make_bookmark(url=url_3.to_url())
    set_bookmark(session, test_user.user_uuid, bm_4)
    crawl_req_4 = CrawlRequest(  # type: ignore
        crawl_uuid=uuid4(),
        requested=datetime(2018, 1, 3),
        got_response=False,
        url_uuid=url_3.url_uuid,
        response_obj=CrawlResponse(body_uuid=uuid4(), headers={}, status_code=404),
    )
    session.add_all([crawl_req_1, crawl_req_2, crawl_req_3, crawl_req_4])
    session.commit()

    rv = set(most_recent_successful_bookmark_crawls(session))
    assert crawl_req_1.crawl_uuid not in rv
    assert crawl_req_2.crawl_uuid in rv
    assert crawl_req_3.crawl_uuid not in rv
    assert crawl_req_3.crawl_uuid not in rv


def test_user_tags(session, test_user):
    epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    bm_1 = make_bookmark(
        tag_triples=frozenset([("a", epoch_start, False), ("b", epoch_start, False)])
    )
    bm_2 = make_bookmark(
        tag_triples=frozenset([("b", epoch_start, False), ("c", epoch_start, True)])
    )
    set_bookmark(session, test_user.user_uuid, bm_1)
    set_bookmark(session, test_user.user_uuid, bm_2)

    expected = set(["a", "b"])
    assert set(user_tags(session, test_user)) == expected
