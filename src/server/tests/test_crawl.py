from datetime import datetime, timezone
from os import environ
import gzip

import requests
import responses
from freezegun import freeze_time
import pytest

from quarchive import file_storage
from quarchive.data.functions import upsert_url
from quarchive.data.models import CrawlRequest as SQLACrawlRequest, CrawlResponse
from quarchive.value_objects import URL, Request, HTTPVerb
from quarchive import crawler
from .conftest import random_string

pytestmark = pytest.mark.crawler


@freeze_time("2018-01-03")
@pytest.mark.parametrize("status_code", [200, 404, 500])
def test_crawl_when_response_is_recieved(
    session, http_client, status_code, mock_s3, requests_mock
):
    url = URL.from_string("http://example.com/" + random_string())
    upsert_url(session, url)

    requests_mock.add(
        responses.GET, url.to_string(), body=b"hello", status=status_code, stream=True
    )

    crawl_request = Request(verb=HTTPVerb.GET, url=url)
    crawl_uuid = crawler.crawl_url(session, http_client, crawl_request)

    request = session.query(SQLACrawlRequest).get(crawl_uuid)
    response = session.query(CrawlResponse).get(crawl_uuid)

    assert request.requested == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert request.got_response
    assert response.status_code == status_code
    assert response.crawl_uuid == crawl_uuid
    assert response.headers == {"content-type": "text/plain"}

    s3_obj = (
        file_storage.get_s3()
        .Object(environ["QM_RESPONSE_BODY_BUCKET_NAME"], str(response.body_uuid))
        .get()
    )
    response_body = s3_obj["Body"].read()
    assert response_body == gzip.compress(b"hello")


def test_crawl_when_no_response(session, http_client, requests_mock):
    url = URL.from_string("http://example.com/" + random_string())
    upsert_url(session, url)

    requests_mock.add(
        responses.GET,
        url.to_string(),
        body=requests.exceptions.ConnectTimeout("connect timeout"),
    )

    crawl_uuid = crawler.crawl_url(
        session, http_client, Request(verb=HTTPVerb.GET, url=url)
    )

    request = session.query(SQLACrawlRequest).get(crawl_uuid)
    response = session.query(CrawlResponse).get(crawl_uuid)
    assert request is not None
    assert response is None
