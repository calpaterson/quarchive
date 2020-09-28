from uuid import UUID
from dataclasses import dataclass


@dataclass(frozen=True)
class BookmarkCreated:
    url_uuid: UUID
    user_uuid: UUID
