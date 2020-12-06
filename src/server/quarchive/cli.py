import io
from uuid import UUID
from sys import stdout
import contextlib
from logging import getLogger
from os import environ

import click

from quarchive import file_storage
from quarchive.logging import LOG_LEVELS, configure_logging
from quarchive.data.functions import (
    most_recent_successful_bookmark_crawls,
    get_crawl_metadata,
    get_session_cls,
)
from quarchive.messaging.message_lib import IndexRequested
from quarchive.messaging.publication import publish_message

log = getLogger(__name__)


@click.command(help="Requests a (re)index of the most recent crawl for each bookmark")
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def reindex_bookmarks(log_level: str):
    """Requests an (re)index of the most recent crawl for each bookmark."""
    configure_logging(log_level)
    log.warning("requesting reindex of all bookmarks")
    Session = get_session_cls()
    index = 0
    with contextlib.closing(Session()) as session:
        for index, crawl_uuid in enumerate(
            most_recent_successful_bookmark_crawls(session)
        ):
            publish_message(
                IndexRequested(crawl_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
            )
        log.warning("requested %d indexings", index)


@click.command(help="Outputs the body of the given crawl")
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
@click.argument("crawl_uuid", type=click.UUID)
def get_crawl_body(crawl_uuid: UUID, log_level: str):
    configure_logging(log_level)
    Session = get_session_cls()
    with contextlib.closing(Session()) as session:
        metadata = get_crawl_metadata(session, crawl_uuid)
        bucket = file_storage.get_response_body_bucket()
        filelike = file_storage.download_file(bucket, str(metadata.body_uuid))
        while True:
            buf = filelike.read(io.DEFAULT_BUFFER_SIZE)
            if len(buf) == 0:
                break
            stdout.write(buf.decode("utf-8"))
