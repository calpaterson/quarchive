import itertools
import json
import logging
from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

import click
from dateutil.parser import isoparse

from .data.functions import merge_bookmarks
from .value_objects import Bookmark, TagTriples, URL
from .web.app import init_app
from .web.blueprint import db
from .logging import LOG_LEVELS, configure_logging

log = logging.getLogger(__name__)


@click.command()
@click.argument("user_uuid", type=click.UUID)
@click.argument("json_file", type=click.File("rb"))
@click.option(
    "--as-of",
    type=click.DateTime(),
    default=lambda: datetime.strftime(datetime.utcnow(), "%Y-%m-%d %H:%M:%S"),
)
@click.option("--log-level", type=click.Choice(LOG_LEVELS))
def pinboard_import(user_uuid: UUID, json_file, as_of: datetime, log_level):
    configure_logging(log_level)
    as_of_dt = as_of.replace(tzinfo=timezone.utc)
    log.info("as of: %s", as_of_dt)

    def pinboard_bookmark_to_bookmark(mapping: Mapping[str, str]) -> Bookmark:
        creation_dt = isoparse(mapping["time"])
        if len(mapping.get("tags", "").strip()) == 0:
            tag_triples: TagTriples = frozenset()
        else:
            tag_triples = frozenset(
                (tag, creation_dt, False) for tag in mapping["tags"].split(" ")
            )
        return Bookmark(
            url=URL.from_string(mapping["href"]),
            title=mapping["description"],
            description=mapping["extended"],
            updated=as_of_dt,
            created=creation_dt,
            unread=True if mapping["toread"] == "yes" else False,
            deleted=False,
            tag_triples=tag_triples,
        )

    document = json.load(json_file)
    keys = set(itertools.chain(*[item.keys() for item in document]))
    log.info("keys = %s", keys)
    app = init_app()
    with app.app_context():
        generator = (pinboard_bookmark_to_bookmark(b) for b in document)
        merge_result = merge_bookmarks(db.session, user_uuid, generator)
        log.info("added %d bookmarks", len(merge_result.added))
        log.info("changed %d bookmarks", len(merge_result.changed))
        db.session.commit()
