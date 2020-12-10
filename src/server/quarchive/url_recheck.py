"""
URL recheck - check that all urls in the database are valid, outputting a list of invalid ones.
"""

import logging
import sys
from uuid import UUID
from typing import Tuple
from urllib.parse import urlunsplit

import click

from .logging import LOG_LEVELS, configure_logging
from .value_objects import URL, URLException
from .web.app import init_app
from .web.web_blueprint import db
from .data.functions import get_all_urls_as_5_tuples

log = logging.getLogger("quarchive-url-recheck")


def is_valid(db_uuid: UUID, url_tuple: Tuple[str, str, str, str, str]) -> bool:
    # First check that the url works as a string
    try:
        url = URL.from_string(urlunsplit(url_tuple))
    except URLException:
        return False

    # Then check that the uuid is right
    if url.url_uuid != db_uuid:
        return False

    return True


@click.command()
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def url_recheck(log_level):
    configure_logging(log_level)
    app = init_app()
    errors = 0
    count = 0
    with app.app_context():
        for db_uuid, url_tuple in get_all_urls_as_5_tuples(db.session):
            if not is_valid(db_uuid, url_tuple):
                errors += 1
                log.error("invalid url: (%s) %s", db_uuid, url_tuple)
            count += 1
    log.info("checked %d urls, found %d errors", count, errors)
    sys.exit(1 if errors > 0 else 0)
