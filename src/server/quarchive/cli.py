from logging import getLogger
from os import environ

import click

from quarchive.logging import LOG_LEVELS, configure_logging
from quarchive.data.functions import (
    most_recent_successful_bookmark_crawls,
    get_session_cls,
)
from quarchive.messaging.message_lib import IndexRequested
from quarchive.messaging.publication import publish_message

log = getLogger(__name__)


@click.command(help="Requests a (re)index of the most recent crawl for each bookmark")
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def reindex_bookmarks(log_level):
    """Requests an (re)index of the most recent crawl for each bookmark."""
    configure_logging(log_level)
    log.warning("requesting reindex of all bookmarks")
    Session = get_session_cls()
    index = 0
    for index, crawl_uuid in enumerate(
        most_recent_successful_bookmark_crawls(Session())
    ):
        publish_message(
            IndexRequested(crawl_uuid), environ["QM_RABBITMQ_BG_WORKER_TOPIC"]
        )
    log.warning("requested %d indexings", index)
