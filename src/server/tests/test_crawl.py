from uuid import UUID
from unittest import mock
from datetime import datetime, timezone
from os import environ
import gzip
from urllib.parse import urlsplit

import requests
import responses
import moto
from freezegun import freeze_time
import pytest

import quarchive as sut

pytestmark = pytest.mark.crawler


@pytest.fixture(scope="session", autouse=True)
def lower_requests_timeout():
    with mock.patch.object(sut, "REQUESTS_TIMEOUT", 0.1):
        yield


@responses.activate
@freeze_time("2018-01-03")
@pytest.mark.parametrize("status_code", [200, 404, 500])
def test_crawl_when_response_is_recieved(session, status_code, mock_s3):
    url = "http://example.com"

    responses.add(responses.GET, url, body=b"hello", status=status_code, stream=True)

    crawl_uuid = UUID("f" * 32)
    sut.crawl_url(crawl_uuid, url)

    request, response = session.query(sut.CrawlRequest, sut.CrawlResponse).one()

    assert request.requested == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert request.got_response
    assert response.status_code == status_code
    assert response.crawl_uuid == crawl_uuid
    assert response.headers == {"content-type": "text/plain"}

    s3_obj = (
        sut.get_s3()
        .Object(environ["QM_RESPONSE_BODY_BUCKET_NAME"], str(response.body_uuid))
        .get()
    )
    response_body = s3_obj["Body"].read()
    assert response_body == gzip.compress(b"hello")


@responses.activate
def test_crawl_when_no_response(session):
    url = "http://example.com"
    responses.add(
        responses.GET, url, body=requests.exceptions.ConnectTimeout("connect timeout")
    )

    crawl_uuid = UUID("f" * 32)
    sut.crawl_url(crawl_uuid, url)

    request = session.query(sut.CrawlRequest).one()
    response = session.query(sut.CrawlResponse).first()
    assert request is not None
    assert response is None


@responses.activate
def test_crawl_url_if_uncrawled(session, mock_s3):
    url = "http://example.com"

    responses.add(responses.GET, url, body=b"hello", stream=True)

    sut.crawl_url_if_uncrawled(url)

    # Effectively assert that there's only one
    pairs = session.query(sut.CrawlRequest, sut.CrawlResponse).all()
    assert len(pairs) == 1

    sut.crawl_url_if_uncrawled(url)

    # Assert again
    pairs = session.query(sut.CrawlRequest, sut.CrawlResponse).all()
    assert len(pairs) == 1


@responses.activate
def test_enqueue_of_uncrawled(session, eager_celery, mock_s3):
    url = "http://example.com"
    s, n, p, q, f = urlsplit(url)
    session.add(
        sut.SQLAUrl(
            url_uuid=UUID("f" * 32), scheme=s, netloc=n, path=p, query=q, fragment=f
        )
    )
    session.commit()

    responses.add(responses.GET, url, body=b"hello", stream=True)
    sut.enqueue_crawls_for_uncrawled_urls()

    pairs = session.query(sut.CrawlRequest, sut.CrawlRequest).all()
    assert len(pairs) == 1
