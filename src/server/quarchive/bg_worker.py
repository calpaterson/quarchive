from os import environ
from datetime import datetime, timezone
from typing import Type, cast, Sequence, Optional, Union
from logging import getLogger

import requests
from sqlalchemy.orm import Session, sessionmaker
import click
import missive
import missive.dlq.sqlite
from missive.adapters.rabbitmq import RabbitMQAdapter

from quarchive import discussions
from quarchive.io import RewindingIO
from quarchive.config import load_config
from quarchive.value_objects import (
    HTTPVerb,
    CrawlRequest,
    Request,
    BookmarkCrawlReason,
    DiscussionSource,
)
from quarchive.html_metadata import best_icon, HTMLMetadata, IconScope
from quarchive.logging import configure_logging, LOG_LEVELS
from quarchive import crawler, indexing
from quarchive.data.functions import (
    upsert_discussions,
    record_discussion_fetch,
    upsert_url,
    upsert_icon_for_url,
    icon_at_url,
    get_url_by_url_uuid,
    is_crawled,
    get_session_cls,
)
from quarchive.messaging.publication import publish_message
from quarchive.messaging.message_lib import (
    BookmarkCreated,
    CrawlRequested,
    Event,
    FetchDiscussionsCommand,
    HelloEvent,
    IndexRequested,
    NewIconFound,
)
from quarchive.messaging.receipt import PickleMessage

log = getLogger(__name__)


proc: missive.Processor[PickleMessage] = missive.Processor()


@proc.before_processing
def create_session_cls(proc_ctx: missive.ProcessingContext[PickleMessage]):
    proc_ctx.state.sessionmaker = get_session_cls()


@proc.before_processing
def create_http_clients(proc_ctx):
    http_client = requests.Session()
    proc_ctx.state.http_client = http_client
    proc_ctx.state.reddit_client = discussions.RedditDiscussionClient(
        http_client, environ["QM_REDDIT_CLIENT_ID"], environ["QM_REDDIT_CLIENT_SECRET"],
    )


@proc.before_handling
def place_http_clients(proc_ctx, handling_ctx):
    handling_ctx.state.http_client = proc_ctx.state.http_client
    handling_ctx.state.reddit_client = proc_ctx.state.reddit_client


@proc.before_handling
def create_session(
    proc_ctx: missive.ProcessingContext[PickleMessage],
    handling_ctx: missive.HandlingContext[PickleMessage],
):
    maker: sessionmaker = proc_ctx.state.sessionmaker
    db_session: Session = maker()
    handling_ctx.state.db_session = db_session


@proc.after_handling
def close_session(
    proc_ctx: missive.ProcessingContext[PickleMessage],
    handling_ctx: missive.HandlingContext[PickleMessage],
):
    handling_ctx.state.db_session.close()


def get_session(ctx: missive.HandlingContext) -> Session:
    """Helper function for getting the current db session.

    Present only to provide type hints."""
    return ctx.state.db_session


def get_http_client(ctx: missive.HandlingContext) -> requests.Session:
    return ctx.state.http_client


def get_reddit_client(
    ctx: missive.HandlingContext,
) -> discussions.RedditDiscussionClient:
    return ctx.state.reddit_client


class ClassMatcher:
    def __init__(self, required_class: Type[Event]):
        self.required_class = required_class

    def __call__(self, message: PickleMessage) -> bool:
        return isinstance(message.get_obj(), self.required_class)


class LogicalAndMatcher:
    def __init__(self, matchers: Sequence[missive.Matcher]):
        self.matchers = matchers

    def __call__(self, message: PickleMessage) -> bool:
        return all(matcher(message) for matcher in self.matchers)


class LogicalOrMatcher:
    def __init__(self, matchers: Sequence[missive.Matcher]):
        self.matchers = matchers

    def __call__(self, message: PickleMessage) -> bool:
        return any(matcher(message) for matcher in self.matchers)


@proc.handle_for(ClassMatcher(HelloEvent))
def print_hellos(message: PickleMessage, ctx: missive.HandlingContext):
    event: HelloEvent = cast(HelloEvent, message.get_obj())
    time_taken_ms = (datetime.now(timezone.utc) - event.created).total_seconds() * 1000
    log.info(
        "got hello event (in %.3fms), message: '%s'",
        round(time_taken_ms, 3),
        event.message,
    )
    ctx.ack()


@proc.handle_for(ClassMatcher(BookmarkCreated))
def on_bookmark_created(message: PickleMessage, ctx: missive.HandlingContext):
    """When a new bookmark is created, we want to:

    - crawl it, if it's not yet crawled
    - (tbc) other things

    """
    event = cast(BookmarkCreated, message.get_obj())
    session = get_session(ctx)
    url = get_url_by_url_uuid(session, event.url_uuid)
    if url is None:
        raise RuntimeError("url requested to crawl does not exist in the db")
    if not is_crawled(session, url):
        publish_message(
            CrawlRequested(
                crawl_request=CrawlRequest(
                    request=Request(verb=HTTPVerb.GET, url=url),
                    reason=BookmarkCrawlReason(),
                )
            ),
            environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
        )
    session.commit()

    ctx.ack()


@proc.handle_for(
    LogicalAndMatcher(
        [
            ClassMatcher(CrawlRequested),
            lambda pm: isinstance(
                pm.get_obj().crawl_request.reason, BookmarkCrawlReason
            ),
        ]
    )
)
def on_bookmark_crawl_requested(message: PickleMessage, ctx: missive.HandlingContext):
    event = cast(CrawlRequested, message.get_obj())
    session = get_session(ctx)
    http_client = get_http_client(ctx)
    crawl_result = crawler.crawl(session, http_client, event.crawl_request.request)
    session.commit()
    publish_message(
        IndexRequested(crawl_uuid=crawl_result.crawl_uuid),
        environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
    )
    ctx.ack()


@proc.handle_for(ClassMatcher(FetchDiscussionsCommand))
def on_discussion_crawl_requested(message: PickleMessage, ctx: missive.HandlingContext):
    event = cast(FetchDiscussionsCommand, message.get_obj())
    session = get_session(ctx)
    http_client = get_http_client(ctx)
    url = get_url_by_url_uuid(session, event.url_uuid)
    if url is None:
        # FIXME: improve this...
        raise RuntimeError("url does not exist!")
    client: Union[discussions.HNAlgoliaClient, discussions.RedditDiscussionClient]
    if event.source == DiscussionSource.HN:
        client = discussions.HNAlgoliaClient(http_client)
    else:
        client = get_reddit_client(ctx)
    upsert_discussions(session, client.discussions_for_url(url))
    record_discussion_fetch(session, url, event.source)
    session.commit()
    ctx.ack()


@proc.handle_for(ClassMatcher(NewIconFound))
def on_new_icon_found(message: PickleMessage, ctx: missive.HandlingContext):
    event = cast(NewIconFound, message.get_obj())
    session = get_session(ctx)
    http_client = get_http_client(ctx)

    icon_url = get_url_by_url_uuid(session, event.icon_url_uuid)
    if icon_url is None:
        raise RuntimeError("icon url not in db")

    if event.page_url_uuid is not None:
        page_url = get_url_by_url_uuid(session, event.page_url_uuid)
    else:
        page_url = None

    existing_icon_uuid = icon_at_url(session, icon_url)
    if existing_icon_uuid is not None:
        log.info("already have icon at %s", icon_url)
        if page_url is not None:
            upsert_icon_for_url(session, page_url, existing_icon_uuid)
    else:
        blake2b_hash, response = crawler.crawl_icon(
            session, http_client, Request(verb=HTTPVerb.GET, url=icon_url)
        )
        body = cast(RewindingIO, response.body)
        with body as wind:
            indexing.index_icon(
                session, icon_url, wind, blake2b_hash, page_url=page_url
            )
    session.commit()

    ctx.ack()


def icon_message_if_necessary(
    session: Session, metadata: HTMLMetadata
) -> Optional[NewIconFound]:
    icon = best_icon(metadata)
    icon_uuid = icon_at_url(session, icon.url)
    if icon_uuid is not None:
        log.debug("already have icon for %s (%s)", metadata.url, icon.url)
        upsert_icon_for_url(session, metadata.url, icon_uuid)
        return None
    else:
        upsert_url(session, icon.url)
        message = NewIconFound(icon.url.url_uuid)
        if icon.scope == IconScope.PAGE:
            message.page_url_uuid = metadata.url.url_uuid
        return message


@proc.handle_for(ClassMatcher(IndexRequested))
def on_index_requested(message: PickleMessage, ctx: missive.HandlingContext):
    event = cast(IndexRequested, message.get_obj())
    session = get_session(ctx)
    metadata = indexing.index(session, event.crawl_uuid)
    if metadata:
        icon_message = icon_message_if_necessary(session, metadata)
    else:
        icon_message = None
    session.commit()
    ctx.ack()
    if icon_message:
        publish_message(icon_message, environ["QM_RABBITMQ_BG_WORKER_TOPIC"])


@click.command()
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def bg_worker(log_level):
    load_config()
    proc.set_dlq(
        missive.dlq.sqlite.SQLiteDLQ(environ["QM_MISSIVE_SQLITE_DLQ_CONNSTRING"])
    )
    configure_logging(log_level)
    adapted_proc = RabbitMQAdapter(
        PickleMessage,
        proc,
        [environ["QM_RABBITMQ_BG_WORKER_TOPIC"]],
        url_or_conn=environ["QM_RABBITMQ_URL"],
    )
    adapted_proc.run()
