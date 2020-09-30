from os import environ
from logging import getLogger
from uuid import uuid4, UUID
from functools import lru_cache

import boto3
from sqlalchemy.orm import Session
import requests
from botocore.utils import fix_s3_host

from quarchive.tasks import upload_file
from quarchive.value_objects import URL
from quarchive.data.functions import (
    get_session_cls,
    is_crawled,
    upsert_url,
    create_crawl_request,
    mark_crawl_request_with_response,
    add_crawl_response,
)

log = getLogger(__name__)

## BEGIN temporary hacks until missive has proper processor state


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


_session = None


def get_session_hack() -> Session:
    global _session
    if _session is None:
        _session = get_session_cls()
    return _session


@lru_cache(1)
def get_response_body_bucket():
    bucket = get_s3().Bucket(environ["QM_RESPONSE_BODY_BUCKET_NAME"])
    log.info("constructed response body bucket")
    return bucket


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
    bucket = get_response_body_bucket()
    create_crawl_request(session, crawl_uuid, url)

    try:
        response = client.get(url.to_string(), stream=True, timeout=REQUESTS_TIMEOUT)
    except requests.exceptions.RequestException as e:
        log.warning("unable to request %s - %s", url, e)
        return
    log.info("crawled %s", url)

    mark_crawl_request_with_response(session, crawl_uuid)

    body_uuid = uuid4()
    # Typeshed type looks wrong, proposed a fix in
    # https://github.com/python/typeshed/pull/3610
    from typing import cast

    headers = cast(requests.structures.CaseInsensitiveDict, response.headers)

    lowered_headers = dict(headers.lower_items())
    add_crawl_response(
        session, crawl_uuid, body_uuid, lowered_headers, response.status_code
    )

    # Otherwise we'll get the raw stream (often gzipped) rather than the
    # raw payload (usually html bytes)
    response.raw.decode_content = True

    upload_file(bucket, response.raw, str(body_uuid))
