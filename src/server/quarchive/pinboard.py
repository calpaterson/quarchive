import re
import configparser
import contextlib
from datetime import datetime, timezone
import gzip
from functools import wraps, lru_cache
import itertools
import logging
import mimetypes
from uuid import UUID, uuid4
from typing import (
    Dict,
    Mapping,
    Sequence,
    Set,
    FrozenSet,
    Any,
    Optional,
    Callable,
    Iterable,
    MutableSequence,
    cast,
    TypeVar,
    Tuple,
    BinaryIO,
    List,
    Union,
    TYPE_CHECKING,
)
from os import environ, path
from urllib.parse import urlsplit, urlunsplit
import json
import tempfile
import shutil
from abc import ABCMeta, abstractmethod
import cgi
import secrets

import yaml
import pyhash
from passlib.context import CryptContext
import lxml
import lxml.html
import click
import boto3
from botocore.utils import fix_s3_host
import requests
from celery import Celery
from werkzeug import exceptions as exc
from werkzeug.urls import url_encode
from dateutil.parser import isoparse
from sqlalchemy import (
    Column,
    ForeignKey,
    types as satypes,
    func,
    create_engine,
    and_,
    cast as sa_cast,
)
from sqlalchemy.orm import (
    foreign,
    remote,
    relationship,
    RelationshipProperty,
    Session,
    sessionmaker,
    scoped_session,
)
from sqlalchemy.dialects.postgresql import (
    UUID as _PGUUID,
    insert as pg_insert,
    BYTEA,
    JSONB,
    TSVECTOR,
    array as pg_array,
    ARRAY as PGARRAY,
)
from flask_sqlalchemy import SQLAlchemy
import flask
from flask_cors import CORS
import missive
from missive.adapters.rabbitmq import RabbitMQAdapter
from flask_babel import Babel
import magic

from .value_objects import (
    Bookmark,
    URL,
    User,
    TagTriples,
    bookmark_from_sqla,
    create_url_uuid,
)
from .data.models import (
    SQLAUrl,
    SQLABookmark,
    SQLUser,
    FullText,
    CrawlRequest,
    CrawlResponse,
)
from .data.functions import (
    is_correct_api_key,
    get_api_key,
    username_exists,
    user_from_username,
    user_from_user_uuid,
    create_user,
    get_bookmark_by_url,
    get_bookmark_by_url_uuid,
    upsert_url,
    set_bookmark,
    merge_bookmarks,
    all_bookmarks,
    bookmarks_with_tag,
    tags_with_count,
)
from .search import parse_search_str
from .config import load_config
from .web.app import init_app
from .web.blueprint import db

log = logging.getLogger(__name__)


@click.command()
@click.argument("user_uuid", type=click.UUID)
@click.argument("json_file", type=click.File("rb"))
@click.option(
    "--as-of",
    type=click.DateTime(),
    default=lambda: datetime.strftime(datetime.utcnow(), "%Y-%m-%d %H:%M:%S"),
)
def pinboard_import(user_uuid: UUID, json_file, as_of: datetime):
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
            url=mapping["href"],
            title=mapping["description"],
            description=mapping["extended"],
            updated=as_of_dt,
            created=creation_dt,
            unread=True if mapping["toread"] == "yes" else False,
            deleted=False,
            tag_triples=tag_triples,
        )

    logging.basicConfig(level=logging.INFO)
    document = json.load(json_file)
    keys = set(itertools.chain(*[item.keys() for item in document]))
    log.info("keys = %s", keys)
    app = init_app()
    with app.app_context():
        generator = (pinboard_bookmark_to_bookmark(b) for b in document)
        changed = merge_bookmarks(db.session, user_uuid, generator)
        log.info("changed %d bookmarks", len(changed))
        db.session.commit()
