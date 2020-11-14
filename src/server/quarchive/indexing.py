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

from quarchive import file_storage
from quarchive.html_metadata import extract_metadata_from_html
from quarchive.messaging.message_lib import IndexRequested
from quarchive.messaging.publication import publish_message
from quarchive.data.functions import (
    get_crawl_metadata,
    get_unindexed_urls,
    upsert_metadata,
    record_index_error,
)

log = getLogger(__name__)


def request_indexes_for_unindexed_urls(session: Session) -> None:
    index = 0
    for index, (url, crawl_uuid) in enumerate(get_unindexed_urls(session), start=1):
        publish_message(
            IndexRequested(crawl_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
        )
        log.info("requested index: %s", url.to_string())
    log.info("requested %d indexes", index)


@lru_cache(1)
def known_content_types() -> FrozenSet[str]:
    mimetypes.init()
    return frozenset(mimetypes.types_map.values())


def infer_content_type(fileobj: Union[BinaryIO, gzip.GzipFile]) -> str:
    """Use libmagic to infer the content type of a file from the first 2k."""
    content_type = magic.from_buffer(fileobj.read(2048), mime=True)
    fileobj.seek(0)
    return content_type


def index(session: Session, crawl_uuid: UUID) -> None:
    try:
        ensure_fulltext(session, crawl_uuid)
    except file_storage.FileStorageException as e:
        log.error(e.message)
        session.rollback()
        record_index_error(session, crawl_uuid, e.message)
    except Exception as e:
        log.exception("indexing error")
        session.rollback()
        record_index_error(session, crawl_uuid, str(e))


def ensure_fulltext(session: Session, crawl_uuid: UUID) -> None:
    """Use the artefacts from the given crawl uuid for the fulltext index of
    it's url.

    If those artefacts are already being used, this command will exit early.

    If those artefacts are not being used, whatever fulltext is being used will
    be overwritten.

    If there is an error, a fulltext error will be recorded in the database.

    ."""
    crawl_metadata = get_crawl_metadata(session, crawl_uuid)

    if crawl_metadata.fulltext_failed:
        log.info(
            "%s (%s) already failed - not trying again",
            crawl_metadata.url.to_string(),
            crawl_uuid,
        )
        return

    if crawl_metadata.fulltext_inserted is not None:
        log.info(
            "%s (%s) already indexed - not indexing again",
            crawl_metadata.url.to_string(),
            crawl_uuid,
        )
        return

    bucket = file_storage.get_response_body_bucket()
    # Try to avoid downloading the content unless we need it
    fileobj = None

    # FIXME: Some error modes not handled here, see
    # https://github.com/calpaterson/quarchive/issues/11
    if crawl_metadata.content_type is not None:
        content_type, parameters = cgi.parse_header(crawl_metadata.content_type)
        # charset = parameters.get("charset")

        # If we were given something we don't recognise, infer the content type
        if content_type not in known_content_types():
            old_content_type = content_type
            fileobj = file_storage.download_file(bucket, str(crawl_metadata.body_uuid))
            content_type = infer_content_type(fileobj)
            log.info(
                "inferred %s for %s (instead of %s)",
                content_type,
                crawl_metadata.url.to_string(),
                old_content_type,
            )
    else:
        # No Content-Type, so infer it
        fileobj = file_storage.download_file(bucket, str(crawl_metadata.body_uuid))
        content_type = infer_content_type(fileobj)
        log.info(
            "inferred %s for %s (none provided)",
            content_type,
            crawl_metadata.url.to_string(),
        )

    if content_type != "text/html":
        log.info(
            "%s (%s) has wrong content type: %s - skipping",
            crawl_metadata.url.to_string(),
            crawl_uuid,
            content_type,
        )
        return

    # If we didn't download it before, we should now
    if fileobj is None:
        fileobj = file_storage.download_file(bucket, str(crawl_metadata.body_uuid))

    # FIXME: charset should be handed to extract_full_text_from_html
    metadata = extract_metadata_from_html(fileobj)

    upsert_metadata(session, crawl_metadata.url, crawl_uuid, metadata)
    log.info("indexed %s (%s)", crawl_metadata.url.to_string(), crawl_uuid)
