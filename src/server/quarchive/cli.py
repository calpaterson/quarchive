import io
from uuid import UUID
from sys import stdout
import contextlib
from typing import Optional
from logging import getLogger
from os import environ

import click

from quarchive.web.app import init_app
from quarchive.value_objects import URL, DiscussionSource
from quarchive import file_storage
from quarchive.logging import LOG_LEVELS, configure_logging
from quarchive.messaging.publication import get_producer, publish_message
from quarchive.messaging.message_lib import (
    HelloEvent,
    IndexRequested,
    FetchDiscussionsCommand,
)
from quarchive.data.functions import (
    get_discussion_frontier,
    get_most_recent_crawl,
    most_recent_successful_bookmark_crawls,
    get_crawl_metadata,
    get_session_cls,
)

log = getLogger(__name__)


@click.group()
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def quarchive_cli(log_level) -> None:
    configure_logging(log_level)


@quarchive_cli.command(help="Start web server")
def web() -> None:
    app = init_app()
    app.run()


@quarchive_cli.command(help="Send a hello message")
@click.argument("message")
@click.option(
    "--loop", is_flag=True, help="send the message repeatedly (as a load generator)"
)
def send_hello(message, loop):
    routing_key: str = environ["QM_RABBITMQ_BG_WORKER_TOPIC"]

    # call this for side-effects - to ensure things are set up so that the
    # timing numbers are accurate
    get_producer()

    hello_event = HelloEvent(message)
    publish_message(hello_event, routing_key=routing_key)
    if loop:
        while True:
            hello_event = HelloEvent(message)
            publish_message(hello_event, routing_key=routing_key)


@quarchive_cli.group(help="Discussion related sub-commands")
def discussions():
    pass


@discussions.command(help="(Re)fetch all discussions that are due")
@click.option("--limit", type=click.INT, default=None)
def refetch(limit: Optional[int]):
    Session = get_session_cls()
    count = 0
    with contextlib.closing(Session()) as session:
        for url_uuid, discussion_source in get_discussion_frontier(session):
            publish_message(
                FetchDiscussionsCommand(url_uuid, discussion_source),
                routing_key=environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
            )
            count += 1
            if limit is not None and count >= limit:
                log.info("hit limit of %d", limit)
                break
    log.info("requested %d fetches", count)


@discussions.command(help="Fetch discussions for a url")
@click.argument("url")
def fetch(url: str):
    url_obj = URL.from_string(url)
    event = FetchDiscussionsCommand(url_obj.url_uuid, DiscussionSource.HN)
    publish_message(event, routing_key=environ["QM_RABBITMQ_BG_WORKER_TOPIC"])


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


@click.command(help="Requests an (re)index of a specific url")
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
@click.argument("url", type=click.STRING)
def reindex_url(url: str, log_level: str):
    url_obj = URL.from_string(url)
    Session = get_session_cls()
    with contextlib.closing(Session()) as session:
        crawl_uuid = get_most_recent_crawl(session, url_obj)
    publish_message(IndexRequested(crawl_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"])
    log.info("requested index of %s (crawl_uuid: %s)", url_obj, crawl_uuid)


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
