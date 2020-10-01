from os import environ
from logging import getLogger
from uuid import uuid4, UUID
from functools import lru_cache
from typing import BinaryIO, Union, List, FrozenSet
import gzip
import mimetypes
import cgi

import magic
from sqlalchemy.orm import Session
import requests
import lxml

from quarchive import file_storage
from quarchive.messaging.message_lib import CrawlRequested
from quarchive.messaging.publication import publish_message
from quarchive.value_objects import URL
from quarchive.data.functions import (
    get_crawl_metadata,
    get_session_cls,
    is_crawled,
    create_crawl_request,
    mark_crawl_request_with_response,
    add_crawl_response,
    get_uncrawled_urls,
    add_fulltext,
)

log = getLogger(__name__)

## BEGIN temporary hacks until missive has proper processor state


@lru_cache(1)
def get_client() -> requests.Session:
    return requests.Session()


_session = None


def get_session_hack() -> Session:
    global _session
    if _session is None:
        _session = get_session_cls()
    return _session


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
    log.info("crawled %s", url)

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


def request_crawls_for_uncrawled_urls(session):
    for index, url in enumerate(get_uncrawled_urls(session)):
        publish_message(
            CrawlRequested(url.url_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
        )
        log.info("requested crawl: %s", url.to_string())
    log.info("requested %d crawls", index)


def get_meta_descriptions(root: lxml.html.HtmlElement) -> List[str]:
    meta_description_elements = root.xpath("//meta[@name='description']")
    if len(meta_description_elements) == 0:
        return []
    else:
        return [e.attrib.get("content", "") for e in meta_description_elements]


def extract_full_text_from_html(filelike: Union[BinaryIO, gzip.GzipFile]) -> str:
    # union required as gzip.GzipFile doesn't implement the full API required
    # by BinaryIO - we only need the shared subset
    document = lxml.html.parse(filelike)
    root = document.getroot()
    meta_descs = get_meta_descriptions(root)
    text_content: str = root.text_content()
    return " ".join(meta_descs + [text_content])


@lru_cache(1)
def known_content_types() -> FrozenSet[str]:
    mimetypes.init()
    return frozenset(mimetypes.types_map.values())


def infer_content_type(fileobj: Union[BinaryIO, gzip.GzipFile]) -> str:
    """Use libmagic to infer the content type of a file from the first 2k."""
    content_type = magic.from_buffer(fileobj.read(2048), mime=True)
    fileobj.seek(0)
    return content_type


def ensure_fulltext(session, crawl_uuid) -> None:
    body_uuid, content_type_header, url, inserted = get_crawl_metadata(
        session, crawl_uuid
    )

    if inserted is not None:
        log.info(
            "%s (%s) already indexed - not indexing again", url.to_string(), crawl_uuid,
        )
        return

    bucket = file_storage.get_response_body_bucket()
    # Try to avoid downloading the content unless we need it
    fileobj = None

    # FIXME: Some error modes not handled here, see
    # https://github.com/calpaterson/quarchive/issues/11
    if content_type_header is not None:
        content_type, parameters = cgi.parse_header(content_type_header)
        # charset = parameters.get("charset")

        # If we were given something we don't recognise, infer the content type
        if content_type not in known_content_types():
            old_content_type = content_type
            fileobj = file_storage.download_file(bucket, str(body_uuid))
            content_type = infer_content_type(fileobj)
            log.info(
                "inferred %s for %s (instead of %s)",
                content_type,
                url.to_string(),
                old_content_type,
            )
    else:
        # No Content-Type, so infer it
        fileobj = file_storage.download_file(bucket, str(body_uuid))
        content_type = infer_content_type(fileobj)
        log.info("inferred %s for %s (none provided)", content_type, url.to_string())

    if content_type != "text/html":
        log.info(
            "%s (%s) has wrong content type: %s - skipping",
            url.to_string(),
            crawl_uuid,
            content_type,
        )
        return

    # If we didn't download it before, we should now
    if fileobj is None:
        fileobj = file_storage.download_file(bucket, str(body_uuid))

    # FIXME: charset should be handed to extract_full_text_from_html
    text = extract_full_text_from_html(fileobj)

    add_fulltext(session, url, crawl_uuid, text)
    log.info("indexed %s (%s)", url.to_string(), crawl_uuid)
