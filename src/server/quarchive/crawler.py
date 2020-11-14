from os import environ
from logging import getLogger
from uuid import uuid4, UUID
from functools import lru_cache
from typing import BinaryIO, Union, FrozenSet
import gzip
import mimetypes
import cgi

import magic
from sqlalchemy.orm import Session
import requests

from quarchive import file_storage
from quarchive.html_metadata import extract_metadata_from_html
from quarchive.messaging.message_lib import CrawlRequested, IndexRequested
from quarchive.messaging.publication import publish_message
from quarchive.value_objects import URL
from quarchive.data.functions import (
    get_crawl_metadata,
    is_crawled,
    create_crawl_request,
    mark_crawl_request_with_response,
    add_crawl_response,
    get_uncrawled_urls,
    get_unindexed_urls,
    upsert_metadata,
    record_index_error,
)

log = getLogger(__name__)

## BEGIN temporary hacks until missive has proper processor state


@lru_cache(1)
def get_client() -> requests.Session:
    return requests.Session()


_session = None


## END temporary hacks

REQUESTS_TIMEOUT = 30


def ensure_url_is_crawled(session: Session, url: URL):
    if is_crawled(session, url):
        log.info("%s already crawled")
        return
    else:
        crawl_uuid = uuid4()
        crawl_url(session, crawl_uuid, url)


def crawl_url(session: Session, crawl_uuid: UUID, url: URL) -> None:
    client = get_client()
    bucket = file_storage.get_response_body_bucket()
    create_crawl_request(session, crawl_uuid, url)

    try:
        response = client.get(url.to_string(), stream=True, timeout=REQUESTS_TIMEOUT)
    except requests.exceptions.RequestException as e:
        log.warning("unable to request %s - %s", url, e)
        return

    mark_crawl_request_with_response(session, crawl_uuid)

    body_uuid = uuid4()

    lowered_headers = dict(response.headers.lower_items())
    add_crawl_response(
        session, crawl_uuid, body_uuid, lowered_headers, response.status_code
    )

    # Otherwise we'll get the raw stream (often gzipped) rather than the
    # raw payload (usually html bytes)
    response.raw.decode_content = True

    file_storage.upload_file(bucket, response.raw, str(body_uuid))
    log.info("crawled %s", url)


def request_crawls_for_uncrawled_urls(session):
    index = 0
    for index, url in enumerate(get_uncrawled_urls(session), start=1):
        publish_message(
            CrawlRequested(url.url_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
        )
        log.info("requested crawl: %s", url.to_string())
    log.info("requested %d crawls", index + 1)
