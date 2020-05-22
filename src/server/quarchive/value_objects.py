from logging import getLogger
from uuid import NAMESPACE_URL as UUID_URL_NAMESPACE, UUID, uuid5

from dataclasses import dataclass
from datetime import datetime
import itertools
from uuid import UUID
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
from urllib.parse import urlsplit, urlunsplit

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

# FIXME: to be removed!
from .data.models import SQLABookmark, SQLAUrl

log = getLogger(__name__)


@dataclass(frozen=True)
class URL:
    url_uuid: UUID

    scheme: str
    netloc: str
    path: str
    query: str
    fragment: str

    def to_url(self) -> str:
        return urlunsplit(
            (self.scheme, self.netloc, self.path, self.query, self.fragment)
        )

    @classmethod
    def from_string(self, url_str: str) -> "URL":
        s, n, p, q, f = urlsplit(url_str)
        url_uuid = create_url_uuid(url_str)
        return URL(url_uuid, s, n, p, q, f)

    @classmethod
    def from_sqla_url(cls, sql_url: "SQLAUrl") -> "URL":
        # sqlalchemy-stubs can't figure this out
        url_uuid = cast(UUID, sql_url.url_uuid)
        return cls(
            url_uuid=url_uuid,
            scheme=sql_url.scheme,
            netloc=sql_url.netloc,
            path=sql_url.path,
            query=sql_url.query,
            fragment=sql_url.fragment,
        )


TagTriple = Tuple[str, datetime, bool]
TagTriples = FrozenSet[TagTriple]


@dataclass(frozen=True)
class Bookmark:
    url: str

    title: str
    description: str

    created: datetime
    updated: datetime

    unread: bool
    deleted: bool

    tag_triples: TagTriples

    def get_url(self) -> URL:
        return URL.from_string(self.url)

    def current_tags(self) -> FrozenSet[str]:
        """Returns all current tags of the bookmark"""
        return frozenset(tt[0] for tt in self.tag_triples if not tt[2])

    def merge(self, other: "Bookmark") -> "Bookmark":
        more_recent: "Bookmark" = sorted(
            (self, other),
            # 1. Take the most recently updated.
            # 2. If they're equally recent, take the longer title
            # 3. If that's not enough add the longest description
            # 4. If that's not enough compare the titles
            # 5. If that's not enough compare the description
            # 6. Then compare everything else
            key=lambda b: (
                b.updated,
                len(b.title),
                len(b.description),
                b.title,
                b.description,
                b.unread,
                not b.deleted,
            ),
            reverse=True,
        )[0]
        # The strategy in short:
        # Take the fields from the most recently updated bookmark, EXCEPT:
        # created - for which take the oldest value
        # updated - for which take the latest value
        return Bookmark(
            url=self.url,
            created=min((self.created, other.created)),
            updated=max((self.updated, other.updated)),
            title=more_recent.title,
            description=more_recent.description,
            unread=more_recent.unread,
            deleted=more_recent.deleted,
            tag_triples=Bookmark.merge_tag_triples(self.tag_triples, other.tag_triples),
        )

    @staticmethod
    def tag_from_triple(triple: TagTriple) -> str:
        return triple[0]

    @staticmethod
    def merge_tag_triples(triples_1: TagTriples, triples_2: TagTriples) -> TagTriples:
        grouped_by_tag = itertools.groupby(
            sorted(itertools.chain(triples_1, triples_2), key=Bookmark.tag_from_triple),
            key=Bookmark.tag_from_triple,
        )
        merged: Set[TagTriple] = set()
        for _, group in grouped_by_tag:
            list_group = list(group)
            if len(list_group) == 1:
                merged.add(list_group[0])
            else:
                newer, older = sorted(
                    list_group, key=lambda tt: (tt[1], not tt[2]), reverse=True
                )
                merged.add(newer)

        return frozenset(merged)

    def to_json(self) -> Mapping:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "unread": self.unread,
            "deleted": self.deleted,
            "tag_triples": [[n, dt.isoformat(), d] for n, dt, d in self.tag_triples],
        }

    @classmethod
    def from_json(cls, mapping: Mapping[str, Any]) -> "Bookmark":
        try:
            updated = isoparse(mapping["updated"])
            created = isoparse(mapping["created"])
        except ValueError:
            log.error(
                "Got invalid datetime: [%s, %s] for %s",
                mapping["updated"],
                mapping["created"],
                mapping["url"],
            )
            raise
        tag_triples = frozenset(
            (n, isoparse(dt), d) for n, dt, d in mapping.get("tag_triples", [])
        )
        return cls(
            url=mapping["url"],
            title=mapping["title"],
            description=mapping["description"],
            updated=updated,
            created=created,
            unread=mapping["unread"],
            deleted=mapping["deleted"],
            tag_triples=tag_triples,
        )


def bookmark_from_sqla(url: str, sqla_obj: "SQLABookmark") -> Bookmark:
    return Bookmark(
        url=url,
        created=sqla_obj.created,
        description=sqla_obj.description,
        updated=sqla_obj.updated,
        unread=sqla_obj.unread,
        deleted=sqla_obj.deleted,
        title=sqla_obj.title,
        tag_triples=frozenset(
            (btag.tag_obj.tag_name, btag.updated, btag.deleted)
            for btag in sqla_obj.bookmark_tag_objs
        ),
    )


@dataclass
class User:
    user_uuid: UUID
    username: str
    email: Optional[str]


def create_url_uuid(url: str) -> UUID:
    # Use uuid5's namespace system to make url uuid deterministic
    return uuid5(UUID_URL_NAMESPACE, url)
