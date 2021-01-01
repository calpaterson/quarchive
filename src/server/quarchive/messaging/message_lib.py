from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
import attr

from quarchive.value_objects import CrawlRequest, DiscussionSource


@attr.s(auto_attribs=True)
class Event:
    event_id: UUID = attr.ib(attr.Factory(uuid4), kw_only=True)
    created: datetime = attr.ib(
        attr.Factory(lambda: datetime.now(timezone.utc)), kw_only=True
    )


@attr.s(auto_attribs=True)
class HelloEvent(Event):
    """A test event - for debugging purposes."""

    message: str


@attr.s(auto_attribs=True)
class BookmarkCreated(Event):
    """A bookmark was created."""

    url_uuid: UUID
    user_uuid: UUID


@attr.s(auto_attribs=True)
class CrawlRequested(Event):
    """A specific request for a url to be crawled that is not connected to a
    user action."""

    crawl_request: CrawlRequest


@attr.s(auto_attribs=True)
class FetchDiscussionsCommand(Event):
    url_uuid: UUID
    source: DiscussionSource


@attr.s(auto_attribs=True)
class NewIconFound(Event):
    """A new icon has been found as part of indexing.

    Contains the URL of the icon (icon_url_uuid).  If this is a page icon, it
    also contains the URL which the icon was found (page_url_uuid).

    For domain icons, the icon may not exist (ie: will return 404).
    """

    icon_url_uuid: UUID
    page_url_uuid: Optional[UUID] = None


@attr.s(auto_attribs=True)
class IndexRequested(Event):
    """A request for a crawl's response to be indexed"""

    crawl_uuid: UUID
