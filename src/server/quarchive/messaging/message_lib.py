from uuid import UUID, uuid4
from datetime import datetime, timezone
import attr


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

    url_uuid: UUID


@attr.s(auto_attribs=True)
class IndexRequested(Event):
    """A request for a crawl's response to be indexed"""

    crawl_uuid: UUID
