import io
import shutil
from logging import getLogger
from uuid import uuid4
from typing import Tuple, cast, Optional, Mapping, IO
import hashlib
from tempfile import TemporaryFile

from sqlalchemy.orm import Session
from requests import exceptions, Session as HTTPClient

from quarchive.io import RewindingIO
from quarchive import file_storage
from quarchive.value_objects import Request, Response
from quarchive.data.functions import (
    create_crawl_request,
    mark_crawl_request_with_response,
    add_crawl_response,
)

log = getLogger(__name__)


REQUESTS_TIMEOUT = 30


def crawl(
    session: Session, http_client: HTTPClient, request: Request, stream=True
) -> Response:
    """Makes a request, records the outcome in the database and returns the
    result for any futher processing.

    """
    crawl_uuid = uuid4()
    bucket = file_storage.get_response_body_bucket()
    create_crawl_request(session, crawl_uuid, request)

    log.info("crawling %s", request.url)
    try:
        response = http_client.request(
            method=request.verb.name,
            url=request.url.to_string(),
            stream=stream,
            timeout=REQUESTS_TIMEOUT,
        )
    except exceptions.RequestException as e:
        log.warning("unable to issue request %s - %s", request, e)
        return Response(crawl_uuid, request)

    log.info("got %d from %s", response.status_code, request.url)

    mark_crawl_request_with_response(session, crawl_uuid)

    body_uuid = uuid4()

    lowered_headers = dict(response.headers.lower_items())
    add_crawl_response(
        session, crawl_uuid, body_uuid, lowered_headers, response.status_code
    )

    # Unfortunately request's (usually very helpful) automatic JSON decoding
    # can't be disabled so we need to check to see if it consumed our buffer
    # and if so, copy into a new buffer
    if response.raw.tell() != 0:
        inner_io: IO[bytes] = io.BytesIO(response.content)
        rwio = RewindingIO(inner_io)
    else:
        # Need to decode, otherwise we'll get the raw stream (often gzipped)
        # rather than the raw payload (usually html bytes)
        response.raw.decode_content = True
        rwio = RewindingIO(TemporaryFile(mode="w+b"))

    with rwio as wind_1:
        shutil.copyfileobj(response.raw, wind_1)
    response.close()

    with rwio as wind_2:
        file_storage.upload_file(bucket, wind_2, str(body_uuid))

    log.info("crawled %s", request)
    return Response(crawl_uuid, request, response.status_code, lowered_headers, rwio)


class CrawlException(Exception):
    pass


def crawl_icon(
    session: Session, http_client: HTTPClient, request: Request
) -> Tuple[hashlib.blake2b, Response]:
    """Crawl an icon, returning a hash and the bytes themselves"""
    response = crawl(session, http_client, request)
    if response.body is None:
        # FIXME: This needs proper error handling
        raise CrawlException("didn't get icon")
    with response.body as wind:
        hashobj = hashlib.blake2b()

        while True:
            buff = wind.read(io.DEFAULT_BUFFER_SIZE)
            if not buff:
                break
            hashobj.update(buff)

    return hashobj, response
