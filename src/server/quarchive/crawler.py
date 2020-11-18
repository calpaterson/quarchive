from os import environ
import io
from logging import getLogger
from uuid import uuid4, UUID
from typing import Tuple, BinaryIO, cast
import hashlib
from tempfile import TemporaryFile

from sqlalchemy.orm import Session
import requests

from quarchive import file_storage
from quarchive.messaging.message_lib import CrawlRequested
from quarchive.messaging.publication import publish_message
from quarchive.value_objects import URL
from quarchive.data.functions import (
    is_crawled,
    create_crawl_request,
    mark_crawl_request_with_response,
    add_crawl_response,
    get_uncrawled_urls,
)

log = getLogger(__name__)


REQUESTS_TIMEOUT = 30


def ensure_url_is_crawled(
    session: Session, http_client: requests.Session, url: URL
) -> None:
    if is_crawled(session, url):
        log.info("%s already crawled")
    else:
        crawl_url(session, http_client, url)


def crawl_url(session: Session, http_client: requests.Session, url: URL) -> UUID:
    crawl_uuid = uuid4()
    bucket = file_storage.get_response_body_bucket()
    create_crawl_request(session, crawl_uuid, url)

    try:
        response = http_client.get(
            url.to_string(), stream=True, timeout=REQUESTS_TIMEOUT
        )
    except requests.exceptions.RequestException as e:
        log.warning("unable to request %s - %s", url, e)
        return crawl_uuid

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
    response.close()
    log.info("crawled %s", url)
    return crawl_uuid


class CrawlException(Exception):
    pass


def crawl_icon(
    session: Session, http_client: requests.Session, icon_url: URL
) -> Tuple[hashlib.blake2b, BinaryIO]:
    # FIXME: Lots of duplicated code here
    """Crawl an icon, returning a hash and the bytes themselves"""
    crawl_uuid = uuid4()
    create_crawl_request(session, crawl_uuid, icon_url)

    try:
        response = requests.get(
            icon_url.to_string(), stream=True, timeout=REQUESTS_TIMEOUT
        )
    except requests.exceptions.RequestException as e:
        log.warning("unable to request %s - %s", icon_url, e)
        raise CrawlException()
    log.info("crawled %s", icon_url)

    mark_crawl_request_with_response(session, crawl_uuid)

    body_uuid = uuid4()

    lowered_headers = dict(response.headers.lower_items())
    add_crawl_response(
        session, crawl_uuid, body_uuid, lowered_headers, response.status_code
    )

    # Otherwise we'll get the raw stream (often gzipped) rather than the
    # raw payload (usually html bytes)
    response.raw.decode_content = True

    temp_filelike = cast(BinaryIO, TemporaryFile())
    hashobj = hashlib.blake2b()

    while True:
        buff = response.raw.read(io.DEFAULT_BUFFER_SIZE)
        if not buff:
            break
        temp_filelike.write(buff)
        hashobj.update(buff)

    temp_filelike.seek(0)
    bucket = file_storage.get_response_body_bucket()
    file_storage.upload_file(bucket, temp_filelike, str(body_uuid))

    temp_filelike.seek(0)
    return hashobj, temp_filelike


def request_crawls_for_uncrawled_urls(session):
    index = 0
    for index, url in enumerate(get_uncrawled_urls(session), start=1):
        publish_message(
            CrawlRequested(url.url_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
        )
        log.info("requested crawl: %s", url.to_string())
    log.info("requested %d crawls", index + 1)
