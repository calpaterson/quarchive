"""
URL recheck - check that all urls in the database are valid, outputting a list of invalid ones.
"""

import logging
import sys
from uuid import UUID
from typing import Tuple
from urllib.parse import urlunsplit

import click

from .value_objects import URL, URLException
from .web.app import init_app
from .web.blueprint import db
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
def url_recheck():
    logging.basicConfig(level=logging.INFO)
    app = init_app()
    exit_code = 0
    with app.app_context():
        for db_uuid, url_tuple in get_all_urls_as_5_tuples(db.session):
            if not is_valid(db_uuid, url_tuple):
                exit_code = 1
                log.error("invalid url: (%s) %s", db_uuid, url_tuple)
    sys.exit(exit_code)
