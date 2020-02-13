from os import path
import json
from uuid import UUID
import re
from urllib.parse import urlsplit
from datetime import datetime

import quarchive as sut

from .conftest import test_data_path

WORDS_REGEX = re.compile(r"\w+")


def test_simple():
    with open(path.join(test_data_path, "simple-website.html"), "rb") as html_f:
        full_text = sut.extract_full_text(html_f)

    words = set(WORDS_REGEX.findall(full_text))
    assert "Simple" in words
    assert {"This", "is", "a", "basic", "html", "document"} <= words
    assert {"meta", "description"} <= words


def test_calpaterson():
    with open(path.join(test_data_path, "calpaterson.html"), "rb") as html_f:
        full_text = sut.extract_full_text(html_f)

    words = WORDS_REGEX.findall(full_text)
    # pass/fail
    assert len(words) > 0


import pytest


@pytest.mark.xfail(reason="unfinished")
def test_celery_task(session, eager_celery, mock_s3):
    url_str = "http://example.com"
    scheme, netloc, path, query, fragment = urlsplit(url_str)
    crawl_uuid = UUID("f" * 31 + "0")
    url_uuid = UUID("f" * 31 + "1")
    body_uuid = UUID("f" * 31 + "2")

    url_obj = sut.SQLAUrl(
        url_uuid=url_uuid,
        scheme=scheme,
        netloc=netloc,
        path=path,
        query=query,
        fragment=fragment,
    )
    crawl_req = sut.CrawlRequest(
        crawl_uuid=crawl_uuid,
        url_uuid=url_uuid,
        requested=datetime(2018, 1, 3),
        got_response=True,
    )
    crawl_resp = sut.CrawlResponse(
        crawl_uuid=crawl_uuid,
        headers=json.dumps({"Content-Type": "application/html"}),
        body_uuid=body_uuid,
        status_code=200,
    )

    session.add_all([url_obj, crawl_req, crawl_resp])
    session.commit()
    assert False
