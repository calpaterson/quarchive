import itertools
import re
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from typing import Any, FrozenSet, Mapping, Optional, Set, Tuple, ClassVar, Union
from urllib.parse import urlsplit, urlunsplit, urljoin
from uuid import NAMESPACE_URL as UUID_URL_NAMESPACE, UUID, uuid5
from enum import Enum

from quarchive.io import RewindingIO
from quarchive.commonmark import convert_commonmark
import pytz
from dateutil.parser import isoparse
from werkzeug.datastructures import Headers as WerkzeugHeaders

log = getLogger(__name__)


SCHEME_WHITELIST = frozenset(["http", "https"])


class URLException(Exception):
    """Base exception for all url problems"""

    def __init__(self, url_string: str):
        self.url_string = url_string


class DisallowedSchemeException(URLException):
    """Raised for schemes that aren't allowed.

    Eg: ftp, magnet, ssh, etc
    """


class BadCanonicalisationException(URLException):
    """This exception is raised when the a string url can't be split and
    unsplit without changing the string.  Many examples are due to trailing
    (but legal) characters.

    Eg: http://example.com#, http://example.com?
    """


@dataclass(frozen=True)
class URL:
    """Core URL class.  Internally URLS are represented by a 5-tuple of
    (scheme, netloc, path, query, fragment).  URL UUID's are calculated from
    within the URL UUID namespace."""

    # Using slots reduces the size of this dataclass from 152 bytes to 88 bytes
    # (>40%).  Indexing can create quite a lot of these concurrently.
    # __slots__ = ["url_uuid", "scheme", "netloc", "path", "query", "fragment"]
    # FIXME: Unable to use slots until we stop pickling messages: https://bugs.python.org/issue36424

    url_uuid: UUID

    scheme: str
    netloc: str
    path: str
    query: str
    fragment: str

    def __repr__(self):
        return f"URL('{self.to_string()}', {self.url_uuid})"

    def to_string(self) -> str:
        return urlunsplit(
            (self.scheme, self.netloc, self.path, self.query, self.fragment)
        )

    def follow(self, link_href: str, coerce_canonicalisation: bool = False) -> "URL":
        """Allow for following (possibly relative) links from this URL."""
        return URL.from_string(
            urljoin(self.to_string(), link_href),
            coerce_canonicalisation=coerce_canonicalisation,
        )

    # FIXME: This method should be split into two, with one for working with
    # known canonicalised urls (eg, sent from the extension) and one for
    # dealing with possibly non-canonicalised urls.  The former should return
    # URL or raise an exception and the latter should return Optional[URL] to
    # require callers to think about what to do if the URL isn't canonicalised
    # enough
    @classmethod
    def from_string(self, url_str: str, coerce_canonicalisation: bool = False) -> "URL":
        """Construct from a url string.

        Minimum canonicalisation requirements:
        - no # if fragment empty
        - no ? if query string empty
        - path must not be "" - instead should be "/"

        Allowed schemes:
        - http
        - https

        coerce_canonicalisation=True tries to help by removing trailing junk

        """
        s, n, p, q, f = urlsplit(url_str)
        if s not in SCHEME_WHITELIST:
            raise DisallowedSchemeException(url_str)
        if coerce_canonicalisation:
            if p == "":
                p = "/"
            if q == "?":
                q = ""
            if f == "#":
                f = ""

            # Need to overwrite this variable too, else the url_uuid will
            # be wrong
            url_str = urlunsplit((s, n, p, q, f))
        else:
            if p == "":
                raise BadCanonicalisationException(url_str)

        url_uuid = uuid5(UUID_URL_NAMESPACE, url_str)
        url = URL(url_uuid, s, n, p, q, f)

        # Make completely sure that we can regenerate this exact string from
        # our object - otherwise raise an exception to avoid any problem urls
        # being processed
        if url_str != url.to_string():
            raise BadCanonicalisationException(url_str)

        return url


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
    registered: datetime


@dataclass
class Feed:
    feed_id: UUID
    url: URL
    title: Optional[str]
    description: Optional[str]
    raw_metadata: Mapping[str, Any]


@dataclass
class FeedEntry:
    entry_id: UUID
    first_seen: datetime
    title: Optional[str]
    description: Optional[str]
    url: Optional[URL]
    raw_metadata: Mapping[str, Any]


@dataclass
class FeedNotification:
    user: User
    notification_dt: datetime


WHITESPACE_REGEX = re.compile(r"^\s+$")


@dataclass
class BookmarkView:
    """A bookmark with all the associated metadata to allow it to be displayed
     on the web: eg icon_uuid, (eventually) links, discussions, etc."""

    MAX_TITLE_SIZE: ClassVar[int] = 70

    bookmark: Bookmark
    owner: User
    icon_uuid: Optional[UUID]
    canonical_url: Optional[URL]
    link_count: int
    backlink_count: int
    discussion_digest: "DiscussionDigest"

    def has_canonical_url(self):
        """Returns true when there is a canonical url and it's different to the original url"""
        return (self.canonical_url is not None) and (
            self.canonical_url != self.bookmark.url
        )

    def title(self) -> str:
        """Minor pretty printing of the bookmark title for the web"""
        title = self.bookmark.title
        if len(title) == 0:
            return "[no title]"
        elif len(title) > self.MAX_TITLE_SIZE:
            return title[: self.MAX_TITLE_SIZE - 3] + "..."
        else:
            return title

    def html_description(self) -> str:
        """Convert any markdown into html, or return "" if no description"""
        description = self.bookmark.description
        # Skip the whole process if it's empty (as it often is)
        if WHITESPACE_REGEX.match(description):
            return ""
        else:
            return convert_commonmark(description)


@dataclass
class DiscussionDigest:
    comment_count: int
    discussion_count: int
    sources: Set["DiscussionSource"]


class IconScope(Enum):
    DOMAIN = "domain"
    PAGE = "page"


class HTTPVerb(Enum):
    GET = 1
    HEAD = 2
    POST = 3


@dataclass
class Request:
    verb: HTTPVerb
    url: URL
    headers: WerkzeugHeaders = field(default_factory=WerkzeugHeaders)
    body: Optional[bytes] = None


@dataclass
class Response:
    crawl_uuid: UUID
    request: Request
    status_code: Optional[int] = None
    headers: Optional[Mapping] = None
    body: Optional[RewindingIO] = None


@dataclass
class MetadataReason:
    """When we just want the canonical url, links, title, etc"""

    pass


@dataclass
class IconCrawlReason:
    for_url: UUID
    icon_type: IconScope


@dataclass
class BookmarkCrawlReason:
    """When someone has bookmarked this url"""


@dataclass
class CrawlRequest:
    request: Request
    reason: Union[IconCrawlReason, BookmarkCrawlReason, MetadataReason]


@dataclass
class Discussion:
    external_id: str
    source: "DiscussionSource"
    url: URL
    comment_count: int
    created_at: datetime
    title: str


class DiscussionSource(Enum):
    HN = 1
    REDDIT = 2
