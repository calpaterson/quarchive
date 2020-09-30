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
    message: str


@attr.s(auto_attribs=True)
class BookmarkCreated(Event):
    url_uuid: UUID
    user_uuid: UUID
