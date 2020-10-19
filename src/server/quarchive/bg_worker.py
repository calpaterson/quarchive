from os import environ
from uuid import uuid4
from datetime import datetime, timezone
from typing import Type, cast, Sequence, Union
from logging import getLogger, INFO

import click
import missive
import missive.dlq.sqlite
from missive.adapters.rabbitmq import RabbitMQAdapter

from quarchive.logging import configure_logging, LOG_LEVELS
from quarchive import crawler, file_storage
from quarchive.data.functions import get_url_by_url_uuid, record_index_error, is_crawled
from quarchive.messaging.publication import publish_message
from quarchive.messaging.message_lib import (
    Event,
    HelloEvent,
    BookmarkCreated,
    CrawlRequested,
    IndexRequested,
)
from quarchive.messaging.receipt import PickleMessage

log = getLogger(__name__)


processor: missive.Processor[PickleMessage] = missive.Processor()


class ClassMatcher:
    def __init__(self, required_class: Type[Event]):
        self.required_class = required_class

    def __call__(self, message: PickleMessage) -> bool:
        return isinstance(message.get_obj(), self.required_class)


class LogicalOrMatcher:
    def __init__(self, matchers: Sequence[missive.Matcher]):
        self.matchers = matchers

    def __call__(self, message: PickleMessage) -> bool:
        return any(matcher(message) for matcher in self.matchers)


@processor.handle_for(ClassMatcher(HelloEvent))
def print_hellos(message: PickleMessage, ctx: missive.HandlingContext):
    event: HelloEvent = cast(HelloEvent, message.get_obj())
    time_taken_ms = (datetime.now(timezone.utc) - event.created).total_seconds() * 1000
    log.info(
        "got hello event (in %.3fms), message: '%s'",
        round(time_taken_ms, 3),
        event.message,
    )
    ctx.ack(message)


@processor.handle_for(ClassMatcher(BookmarkCreated))
def on_bookmark_created(message: PickleMessage, ctx: missive.HandlingContext):
    """When a new bookmark is created, we want to:

    - crawl it, if it's not yet crawled
    - (tbc) other things

    """
    event = cast(BookmarkCreated, message.get_obj())
    session = crawler.get_session_hack()
    url = get_url_by_url_uuid(session, event.url_uuid)
    if url is None:
        raise RuntimeError("url requested to crawl does not exist in the db")
    if not is_crawled(session, url):
        publish_message(
            CrawlRequested(url_uuid=url.url_uuid),
            environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
        )
    session.commit()

    ctx.ack(message)


@processor.handle_for(ClassMatcher(CrawlRequested))
def on_crawl_requested(message: PickleMessage, ctx: missive.HandlingContext):
    event = cast(CrawlRequested, message.get_obj())
    session = crawler.get_session_hack()
    url = get_url_by_url_uuid(session, event.url_uuid)
    if url is None:
        raise RuntimeError("url crawled to crawl does not exist in the db")
    crawl_uuid = uuid4()
    crawler.crawl_url(session, crawl_uuid, url)
    session.commit()
    publish_message(
        IndexRequested(crawl_uuid=crawl_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
    )
    ctx.ack(message)


@processor.handle_for(ClassMatcher(IndexRequested))
def on_full_text_requested(message: PickleMessage, ctx: missive.HandlingContext):
    event = cast(IndexRequested, message.get_obj())
    session = crawler.get_session_hack()
    crawler.add_to_fulltext_index(session, event.crawl_uuid)
    session.commit()
    ctx.ack(message)


@click.command()
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def bg_worker(log_level):
    processor.set_dlq(
        missive.dlq.sqlite.SQLiteDLQ(environ["QM_MISSIVE_SQLITE_DQL_CONNSTRING"])
    )
    configure_logging(log_level)
    adapted_processor = RabbitMQAdapter(
        PickleMessage,
        processor,
        [environ["QM_RABBITMQ_BG_WORKER_TOPIC"]],
        url_or_conn=environ["QM_RABBITMQ_URL"],
    )
    adapted_processor.run()
