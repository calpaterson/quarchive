from os import path
from uuid import uuid4, UUID
import re
from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import func
from freezegun import freeze_time

from quarchive import file_storage, crawler
from quarchive.data.models import SQLAUrl, CrawlRequest, CrawlResponse, FullText
from quarchive.value_objects import URL

from .conftest import test_data_path, random_string

WORDS_REGEX = re.compile(r"\w+")


def make_crawl_with_response(session) -> Tuple[SQLAUrl, CrawlRequest, CrawlResponse]:
    url = URL.from_string("http://example.com/" + random_string())
    crawl_uuid = uuid4()
    body_uuid = uuid4()
    url_obj = SQLAUrl.from_url(url)
    crawl_req = CrawlRequest(
        crawl_uuid=crawl_uuid,
        url_uuid=url.url_uuid,
        requested=datetime(2018, 1, 3),
        got_response=True,
    )
    crawl_resp = CrawlResponse(
        crawl_uuid=crawl_uuid,
        headers={"content-type": "text/html"},
        body_uuid=body_uuid,
        status_code=200,
    )
    session.add_all([url_obj, crawl_req, crawl_resp])

    put_simple_website_into_bucket(crawl_resp.body_uuid)

    return (url_obj, crawl_req, crawl_resp)


def put_simple_website_into_bucket(body_uuid: UUID):
    bucket = file_storage.get_response_body_bucket()
    with open(path.join(test_data_path, "simple-website.html"), "rb") as html_f:
        file_storage.upload_file(bucket, html_f, str(body_uuid))


def test_simple():
    with open(path.join(test_data_path, "simple-website.html"), "rb") as html_f:
        full_text = crawler.extract_full_text_from_html(html_f)

    words = set(WORDS_REGEX.findall(full_text))
    assert "Simple" in words
    assert {"This", "is", "a", "basic", "html", "document"} <= words
    assert {"meta", "description"} <= words


def test_calpaterson():
    with open(path.join(test_data_path, "calpaterson.html"), "rb") as html_f:
        full_text = crawler.extract_full_text_from_html(html_f)

    words = WORDS_REGEX.findall(full_text)
    # pass/fail
    assert len(words) > 0


@freeze_time("2018-01-03")
def test_indexing_for_fresh(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    session.commit()

    crawler.ensure_fulltext(session, crawl_req.crawl_uuid)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 6
    assert len(fulltext_obj.full_text) > 0


def test_indexing_idempotent(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    fulltext = FullText(
        url_uuid=sqla_url.url_uuid,
        crawl_uuid=crawl_req.crawl_uuid,
        inserted=datetime(2018, 1, 3, tzinfo=timezone.utc),
        full_text="hello world",
        tsvector=func.to_tsvector("hello world"),
    )

    session.add(fulltext)
    session.commit()

    crawler.ensure_fulltext(session, crawl_req.crawl_uuid)

    fulltext_count = (
        session.query(FullText).filter(FullText.url_uuid == sqla_url.url_uuid).count()
    )
    assert fulltext_count == 1


def test_indexing_non_html(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    crawl_resp.headers["content-type"] = "application/pdf"  # type: ignore
    session.commit()

    crawler.ensure_fulltext(session, crawl_req.crawl_uuid)

    fulltext_count = (
        session.query(FullText)
        .filter(FullText.crawl_uuid == crawl_req.crawl_uuid)
        .count()
    )
    assert fulltext_count == 0


@freeze_time("2018-01-03")
def test_indexing_nonsense_content_type(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    crawl_resp.headers["content-type"] = "nonsense"  # type: ignore
    session.commit()

    crawler.ensure_fulltext(session, crawl_req.crawl_uuid)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 6
    assert len(fulltext_obj.full_text) > 0


@freeze_time("2018-01-03")
def test_indexing_absent_content_type(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    crawl_resp.headers = {}
    session.commit()

    crawler.ensure_fulltext(session, crawl_req.crawl_uuid)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 6
    assert len(fulltext_obj.full_text) > 0


@freeze_time("2018-01-03")
def test_enqueue_fulltext_indexing(session, mock_s3, patched_publish_message):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    session.commit()

    crawler.request_indexes_for_unindexed_urls(session)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 6
    assert len(fulltext_obj.full_text) > 0
