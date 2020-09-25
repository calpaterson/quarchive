from uuid import uuid4
import re
from unittest import mock
from datetime import datetime, timezone
from os import environ
import gzip
from urllib.parse import urlsplit

import requests
import responses
from freezegun import freeze_time
import pytest

import quarchive as sut
from .conftest import random_string, make_bookmark

pytestmark = pytest.mark.crawler


@pytest.fixture(scope="session", autouse=True)
def lower_requests_timeout():
    with mock.patch.object(sut, "REQUESTS_TIMEOUT", 0.1):
        yield


@responses.activate
@freeze_time("2018-01-03")
@pytest.mark.parametrize("status_code", [200, 404, 500])
def test_crawl_when_response_is_recieved(session, status_code, mock_s3):
    url = "http://example.com/"

    responses.add(responses.GET, url, body=b"hello", status=status_code, stream=True)

    crawl_uuid = uuid4()
    sut.crawl_url(session, crawl_uuid, url)

    request = session.query(sut.CrawlRequest).get(crawl_uuid)
    response = session.query(sut.CrawlResponse).get(crawl_uuid)

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
    url = "http://example.com/"
    responses.add(
        responses.GET, url, body=requests.exceptions.ConnectTimeout("connect timeout")
    )

    crawl_uuid = uuid4()
    sut.crawl_url(session, crawl_uuid, url)

    request = session.query(sut.CrawlRequest).get(crawl_uuid)
    response = session.query(sut.CrawlResponse).get(crawl_uuid)
    assert request is not None
    assert response is None


@responses.activate
def test_ensure_crawled_only_runs_once(session, mock_s3):
    url = "http://example.com/" + random_string()

    responses.add(responses.GET, url, body=b"hello", stream=True)

    sut.ensure_crawled(url)

    s, n, p, q, f = urlsplit(url)
    resp_query = (
        session.query(sut.CrawlResponse)
        .join(sut.CrawlRequest)
        .join(sut.SQLAUrl)
        .filter(
            sut.SQLAUrl.scheme == s,
            sut.SQLAUrl.netloc == n,
            sut.SQLAUrl.path == p,
            sut.SQLAUrl.query == q,
            sut.SQLAUrl.fragment == f,
        )
    )
    assert resp_query.count() == 1
    sut.ensure_crawled(url)

    # Assert again
    assert resp_query.count() == 1


@responses.activate
def test_enqueue_crawls_for_uncrawled_urls(session, eager_celery, mock_s3, test_user):
    bookmark = make_bookmark()
    sut.set_bookmark(session, test_user.user_uuid, bookmark)
    session.commit()
    url = bookmark.url

    responses.add(
        responses.GET, re.compile(r"http://example.com/.*"), body=b"hello", stream=True
    )
    sut.enqueue_crawls_for_uncrawled_urls()

    resp_query = (
        session.query(sut.CrawlResponse)
        .join(sut.CrawlRequest)
        .join(sut.SQLAUrl)
        .filter(
            sut.SQLAUrl.scheme == url.scheme,
            sut.SQLAUrl.netloc == url.netloc,
            sut.SQLAUrl.path == url.path,
            sut.SQLAUrl.query == url.query,
            sut.SQLAUrl.fragment == url.fragment,
        )
    )
    assert resp_query.count() == 1
