from os import environ
from datetime import datetime, timezone
from typing import Type, cast, Sequence, Union
from logging import getLogger, basicConfig, INFO

import click
import missive
from missive.adapters.rabbitmq import RabbitMQAdapter

from quarchive import crawler
from quarchive.data.functions import get_url_by_url_uuid
from quarchive.messaging.message_lib import (
    Event,
    HelloEvent,
    BookmarkCreated,
    CrawlRequested,
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


@processor.handle_for([ClassMatcher(HelloEvent)])
def print_hellos(message: PickleMessage, ctx: missive.HandlingContext):
    event: HelloEvent = cast(HelloEvent, message.get_obj())
    time_taken_ms = (datetime.now(timezone.utc) - event.created).total_seconds() * 1000
    log.info(
        "got hello event (in %.3fms), message: '%s'",
        round(time_taken_ms, 3),
        event.message,
    )
    ctx.ack(message)


@processor.handle_for(
    [LogicalOrMatcher([ClassMatcher(BookmarkCreated), ClassMatcher(CrawlRequested)])]
)
def on_bookmark_created(message: PickleMessage, ctx: missive.HandlingContext):
    # FIXME: this isn't right, a CrawlRequested event should not be based on a
    # check of previous attempts
    event = cast(Union[BookmarkCreated, CrawlRequested], message.get_obj())
    session = crawler.get_session_hack()
    url = get_url_by_url_uuid(session, event.url_uuid)
    if url is None:
        raise RuntimeError("url requested to crawl does not exist in db")
    crawler.ensure_url_is_crawled(session, url)
    session.commit()
    ctx.ack(message)


@click.command()
def bg_worker():
    basicConfig(level=INFO)
    adapted_processor = RabbitMQAdapter(
        PickleMessage,
        processor,
        [environ["QM_RABBITMQ_BG_WORKER_TOPIC"]],
        url=environ["QM_RABBITMQ_URL"],
    )
    adapted_processor.run()
