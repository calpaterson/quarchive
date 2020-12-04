from os import path
from uuid import uuid4, UUID
from datetime import datetime, timezone
from typing import Tuple, Optional
from unittest import mock

import pytest
from sqlalchemy import func
from freezegun import freeze_time

from quarchive import file_storage, indexing
from quarchive.data.models import (
    SQLAUrl,
    CrawlRequest,
    CrawlResponse,
    FullText,
    IndexingError,
)
from quarchive.value_objects import URL

from .conftest import test_data_path, random_string


def make_crawl_with_response(
    session, url: Optional[URL] = None
) -> Tuple[SQLAUrl, CrawlRequest, CrawlResponse]:
    # FIXME: This should probably return a CrawlMetadata
    if url is None:
        url = URL.from_string("http://example.com/" + random_string())
        url_obj = SQLAUrl.from_url(url)
    else:
        url_obj = session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url.url_uuid).one()
    crawl_uuid = uuid4()
    body_uuid = uuid4()
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
    with open(
        path.join(test_data_path, "webpage-with-full-metadata.html"), "rb"
    ) as html_f:
        file_storage.upload_file(bucket, html_f, str(body_uuid))


@freeze_time("2018-01-03")
def test_indexing_for_fresh(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)

    indexing.index(session, crawl_req.crawl_uuid)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 10
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

    indexing.index(session, crawl_req.crawl_uuid)

    fulltext_count = (
        session.query(FullText).filter(FullText.url_uuid == sqla_url.url_uuid).count()
    )
    assert fulltext_count == 1

    error_count = (
        session.query(IndexingError)
        .filter(IndexingError.crawl_uuid == crawl_req.crawl_uuid)
        .count()
    )
    assert error_count == 0


def test_indexing_non_html(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    crawl_resp.headers["content-type"] = "application/pdf"  # type: ignore

    indexing.index(session, crawl_req.crawl_uuid)

    fulltext_count = (
        session.query(FullText)
        .filter(FullText.crawl_uuid == crawl_req.crawl_uuid)
        .count()
    )
    assert fulltext_count == 0


@freeze_time("2018-01-03")
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no content type"),
        pytest.param({"content-type": "nonsense"}, id="nonsense"),
    ],
)
def test_indexing_with_content_type_problems(session, mock_s3, headers):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    crawl_resp.headers = headers

    indexing.index(session, crawl_req.crawl_uuid)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 10
    assert len(fulltext_obj.full_text) > 0


def test_index_throws_an_error(session, mock_s3):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    session.commit()

    # First time, error thrown and recorded
    with mock.patch.object(indexing, "extract_metadata_from_html") as mock_gmd:
        mock_gmd.side_effect = RuntimeError
        indexing.index(session, crawl_req.crawl_uuid)

    error_count = (
        session.query(IndexingError)
        .filter(IndexingError.crawl_uuid == crawl_req.crawl_uuid)
        .count()
    )
    assert error_count == 1

    # Second time, it's skipped
    indexing.index(session, crawl_req.crawl_uuid)
    assert error_count == 1


@pytest.mark.skip(reason="buggy, indexing way too much")
@freeze_time("2018-01-03")
def test_enqueue_fulltext_indexing(session, mock_s3, bg_worker):
    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(session)
    session.commit()

    indexing.request_indexes_for_unindexed_urls(session)

    fulltext_obj = session.query(FullText).get(sqla_url.url_uuid)
    assert fulltext_obj.url_uuid == sqla_url.url_uuid
    assert fulltext_obj.crawl_uuid == crawl_req.crawl_uuid
    assert fulltext_obj.inserted == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert len(fulltext_obj.tsvector.split(" ")) == 10
    assert len(fulltext_obj.full_text) > 0
