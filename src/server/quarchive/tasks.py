import cgi
import contextlib
import gzip
import logging
import mimetypes
import shutil
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from os import environ
from typing import BinaryIO, FrozenSet, List, Optional, Union, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import boto3
import lxml
import lxml.html
import magic
import requests
from botocore.utils import fix_s3_host
from celery import Celery
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, scoped_session, sessionmaker

import missive
from missive.adapters.rabbitmq import RabbitMQAdapter

from .data.functions import upsert_url
from .data.models import CrawlRequest, CrawlResponse, FullText, SQLABookmark, SQLAUrl
from .value_objects import URL

log = logging.getLogger(__name__)

celery_app = Celery("quarchive")

processor: missive.Processor[missive.JSONMessage] = missive.Processor()


@processor.handle_for([lambda m: m.get_json()["event_type"] == "test"])
def test_message(message, ctx):
    log.info("test message recieved")
    ctx.ack(message)


@lru_cache(1)
def get_session_cls() -> Session:
    url: str = environ["QM_SQL_URL"]
    engine = create_engine(url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    log.info("using engine: %s", engine)
    return Session


REQUESTS_TIMEOUT = 30


@lru_cache(1)
def get_client() -> requests.Session:
    return requests.Session()


@lru_cache(1)
def get_s3():
    session = boto3.Session(
        aws_access_key_id=environ["QM_AWS_ACCESS_KEY"],
        aws_secret_access_key=environ["QM_AWS_SECRET_ACCESS_KEY"],
        region_name=environ["QM_AWS_REGION_NAME"],
    )

    # This is a magic value to facilitate testing
    resource_kwargs = {}
    if environ["QM_AWS_S3_ENDPOINT_URL"] != "UNSET":
        resource_kwargs["endpoint_url"] = environ["QM_AWS_S3_ENDPOINT_URL"]

    resource = session.resource("s3", **resource_kwargs)
    resource.meta.client.meta.events.unregister("before-sign.s3", fix_s3_host)
    log.info("constructed s3 resource")
    return resource


@lru_cache(1)
def get_response_body_bucket():
    bucket = get_s3().Bucket(environ["QM_RESPONSE_BODY_BUCKET_NAME"])
    log.info("constructed response body bucket")
    return bucket


@celery_app.task
def celery_ok():
    log.info("ok")


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # FIXME: add periodic tasks here
    pass


def enqueue_crawls_for_uncrawled_urls():
    with contextlib.closing(get_session_cls()) as sesh:
        rs = (
            sesh.query(
                SQLAUrl.scheme,
                SQLAUrl.netloc,
                SQLAUrl.path,
                SQLAUrl.query,
                SQLAUrl.fragment,
            )
            .join(SQLABookmark)
            .outerjoin(CrawlRequest, SQLAUrl.url_uuid == CrawlRequest.url_uuid)
            .filter(CrawlRequest.crawl_uuid.is_(None))
        )
        uncrawled_urls = (urlunsplit(tup) for tup in rs)
    index = 0
    for index, uncrawled_url in enumerate(uncrawled_urls, start=1):
        log.info("enqueuing %s for crawl", uncrawled_url)
        ensure_crawled.delay(uncrawled_url)
    log.info("enqueued %d urls", index)


def enqueue_fulltext_indexing():
    with contextlib.closing(get_session_cls()) as sesh:
        rs = (
            sesh.query(CrawlResponse.crawl_uuid)
            .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
            .filter(FullText.crawl_uuid.is_(None))
        )
        for index, (crawl_uuid,) in enumerate(rs, start=1):
            log.info("enqueuing %s for crawl", crawl_uuid)
            ensure_fulltext.delay(crawl_uuid)
    log.info("enqueued %d items", index)


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


def upload_file(bucket, filelike: BinaryIO, filename: str) -> None:
    """Upload a fileobj into the bucket (compressed)"""
    with tempfile.TemporaryFile(mode="w+b") as temp_file:
        gzip_fileobj = gzip.GzipFile(mode="w+b", fileobj=temp_file)
        shutil.copyfileobj(filelike, gzip_fileobj)
        gzip_fileobj.close()
        temp_file.seek(0)
        bucket.upload_fileobj(temp_file, Key=filename)


def download_file(bucket, filename: str) -> gzip.GzipFile:
    """Download a fileobj from a bucket (decompressed)"""
    temp_file = tempfile.TemporaryFile(mode="w+b")
    bucket.download_fileobj(filename, temp_file)
    temp_file.seek(0)
    gzip_fileobj = gzip.GzipFile(mode="r+b", fileobj=temp_file)
    return gzip_fileobj


@lru_cache(1)
def known_content_types() -> FrozenSet[str]:
    mimetypes.init()
    return frozenset(mimetypes.types_map.values())


@celery_app.task
def ensure_crawled(url: str) -> None:
    """Crawl a url only if it has never been crawled before.

    For use from celery beat"""
    scheme, netloc, path, query, fragment = urlsplit(url)
    with contextlib.closing(get_session_cls()) as sesh:
        is_crawled: bool = sesh.query(
            sesh.query(CrawlRequest)
            .join(SQLAUrl)
            .filter(
                SQLAUrl.scheme == scheme,
                SQLAUrl.netloc == netloc,
                SQLAUrl.path == path,
                SQLAUrl.query == query,
                SQLAUrl.fragment == fragment,
            )
            .exists()
        ).scalar()
        if not is_crawled:
            crawl_uuid = uuid4()
            crawl_url(sesh, crawl_uuid, url)


def infer_content_type(fileobj: Union[BinaryIO, gzip.GzipFile]) -> str:
    """Use libmagic to infer the content type of a file from the first 2k."""
    content_type = magic.from_buffer(fileobj.read(2048), mime=True)
    fileobj.seek(0)
    return content_type


@celery_app.task
def ensure_fulltext(crawl_uuid: UUID) -> None:
    """Populate full text table for crawl"""
    with contextlib.closing(get_session_cls()) as sesh:
        content_type_header: Optional[str]
        body_uuid, content_type_header, sqla_url_obj, inserted = (
            sesh.query(
                CrawlResponse.body_uuid,
                CrawlResponse.headers["content-type"],
                SQLAUrl,
                FullText.inserted,
            )
            .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
            .join(CrawlRequest, CrawlResponse.crawl_uuid == CrawlRequest.crawl_uuid)
            .join(SQLAUrl, CrawlRequest.url_uuid == SQLAUrl.url_uuid)
            .filter(CrawlResponse.crawl_uuid == crawl_uuid)
            .one()
        )

        url = sqla_url_obj.to_url()

        if inserted is not None:
            log.info(
                "%s (%s) already indexed - not indexing again",
                url.to_string(),
                crawl_uuid,
            )
            return

        bucket = get_response_body_bucket()
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
                fileobj = download_file(bucket, str(body_uuid))
                content_type = infer_content_type(fileobj)
                log.info(
                    "inferred %s for %s (instead of %s)",
                    content_type,
                    url.to_string(),
                    old_content_type,
                )
        else:
            # No Content-Type, so infer it
            fileobj = download_file(bucket, str(body_uuid))
            content_type = infer_content_type(fileobj)
            log.info(
                "inferred %s for %s (none provided)", content_type, url.to_string()
            )

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
            fileobj = download_file(bucket, str(body_uuid))

        # FIXME: charset should be handed to extract_full_text_from_html
        text = extract_full_text_from_html(fileobj)

        fulltext_obj = FullText(
            url_uuid=sqla_url_obj.url_uuid,
            crawl_uuid=crawl_uuid,
            inserted=datetime.utcnow().replace(tzinfo=timezone.utc),
            full_text=text,
            tsvector=func.to_tsvector(text),
        )
        sesh.add(fulltext_obj)
        sesh.commit()
        log.info("indexed %s (%s)", url.to_string(), crawl_uuid)


def crawl_url(session: Session, crawl_uuid: UUID, url: str) -> None:
    client = get_client()
    bucket = get_response_body_bucket()
    url_uuid = upsert_url(session, url)
    crawl_request = CrawlRequest(
        crawl_uuid=crawl_uuid,
        url_uuid=url_uuid,
        requested=datetime.utcnow().replace(tzinfo=timezone.utc),
        got_response=False,
    )
    session.add(crawl_request)

    try:
        response = client.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
    except requests.exceptions.RequestException as e:
        log.warning("unable to request %s - %s", url, e)
        session.commit()
        return
    log.info("crawled %s", url)

    crawl_request.got_response = True

    body_uuid = uuid4()
    # Typeshed type looks wrong, proposed a fix in
    # https://github.com/python/typeshed/pull/3610
    headers = cast(requests.structures.CaseInsensitiveDict, response.headers)
    session.add(
        CrawlResponse(
            crawl_uuid=crawl_uuid,
            body_uuid=body_uuid,
            headers=dict(headers.lower_items()),
            status_code=response.status_code,
        )
    )

    # Otherwise we'll get the raw stream (often gzipped) rather than the
    # raw payload (usually html bytes)
    response.raw.decode_content = True

    upload_file(bucket, response.raw, str(body_uuid))

    session.commit()
