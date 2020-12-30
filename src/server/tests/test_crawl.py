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

    request = Request(verb=HTTPVerb.GET, url=url)
    response = crawler.crawl(session, http_client, request)

    sql_request = session.query(SQLACrawlRequest).get(response.crawl_uuid)
    sql_response = session.query(CrawlResponse).get(response.crawl_uuid)

    assert sql_request.requested == datetime(2018, 1, 3, tzinfo=timezone.utc)
    assert sql_request.got_response
    assert sql_response.status_code == status_code
    assert sql_response.crawl_uuid == sql_response.crawl_uuid
    assert sql_response.headers == {"content-type": "text/plain"}

    s3_obj = (
        file_storage.get_s3()
        .Object(environ["QM_RESPONSE_BODY_BUCKET_NAME"], str(sql_response.body_uuid))
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

    response = crawler.crawl(session, http_client, Request(verb=HTTPVerb.GET, url=url))

    sql_request = session.query(SQLACrawlRequest).get(response.crawl_uuid)
    sql_response = session.query(CrawlResponse).get(response.crawl_uuid)
    assert sql_request is not None
    assert sql_response is None
