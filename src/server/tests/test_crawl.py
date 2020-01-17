from uuid import UUID
from datetime import datetime, timezone
from os import environ
import gzip

import responses
import moto
from freezegun import freeze_time
import pytest

import quarchive as sut

pytestmark = pytest.mark.crawler


@pytest.fixture(scope="function")
def mock_s3():
    with moto.mock_s3():
        sut.get_s3().create_bucket(Bucket=environ["QM_RESPONSE_BODY_BUCKET_NAME"])
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
