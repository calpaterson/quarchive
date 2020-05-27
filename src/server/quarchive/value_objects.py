import itertools
from dataclasses import dataclass
from datetime import datetime
from logging import getLogger
from typing import Any, FrozenSet, Mapping, Optional, Set, Tuple, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL as UUID_URL_NAMESPACE, UUID, uuid5

import pytz
from dateutil.parser import isoparse

log = getLogger(__name__)


class BadCanonicalisationException(Exception):
    """This exception is raised when the a string url can't be split and
    unsplit without changing the string.  Many examples are due to trailing
    (but legal) characters.

    Eg: http://example.com#, http://example.com?
    """

    def __init__(self, url_string: str):
        self.url_string = url_string


@dataclass(frozen=True)
class URL:
    """Core URL class.  Internally URLS are represented by a 5-tuple of
    (scheme, netloc, path, query, fragment).  URL UUID's are calculated from
    within the URL UUID namespace."""

    url_uuid: UUID

    scheme: str
    netloc: str
    path: str
    query: str
    fragment: str

    def to_string(self) -> str:
        return urlunsplit(
            (self.scheme, self.netloc, self.path, self.query, self.fragment)
        )

    @classmethod
    def from_string(self, url_str: str) -> "URL":
        """Construct from a url string.

        If the URL string doesn't have "minimum canonicalisation" (ie, if it
        can't be split and unsplit without returning a different url string),
        an exception is raised.  Such URLs can't be represented unambiguously
        by this class.

        """
        s, n, p, q, f = urlsplit(url_str)
        if url_str != urlunsplit([s, n, p, q, f]):
            raise BadCanonicalisationException(url_str)
        url_uuid = uuid5(UUID_URL_NAMESPACE, url_str)
        return URL(url_uuid, s, n, p, q, f)


TagTriple = Tuple[str, datetime, bool]
TagTriples = FrozenSet[TagTriple]


@dataclass(frozen=True)
class Bookmark:
    url: URL

    title: str
    description: str

    created: datetime
    updated: datetime

    unread: bool
    deleted: bool

    tag_triples: TagTriples

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
            "url": self.url.to_string(),
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
            url=URL.from_string(mapping["url"]),
            title=mapping["title"],
            description=mapping["description"],
            updated=updated,
            created=created,
            unread=mapping["unread"],
            deleted=mapping["deleted"],
            tag_triples=tag_triples,
        )


@dataclass
class User:
    user_uuid: UUID
    username: str
    email: Optional[str]
    timezone: pytz.BaseTzInfo
