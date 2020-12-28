from datetime import datetime
from base64 import urlsafe_b64encode
from uuid import UUID
from typing import Optional, Mapping, ClassVar, Sequence
import enum
from dataclasses import dataclass

from typing_extensions import Protocol

from quarchive.value_objects import User


class Access(enum.IntFlag):
    NONE = 0
    READ = 1
    WRITE = 2
    READWRITE = 3
    READACCESS = 4
    WRITEACCESS = 8
    ALL = 15


AccessToken = str


@dataclass(frozen=True)
class AccessSubject:
    user: Optional[User]
    grants: Sequence["ShareGrant"]


class AccessObject(Protocol):
    name: ClassVar[str]

    def for_user(self, user: User) -> Access:
        ...

    def to_params(self) -> Mapping:
        ...

    @classmethod
    def from_params(cls, q: Mapping) -> "AccessObject":
        ...


@dataclass(frozen=True)
class BookmarkAccessObject:
    """Represents an individual bookmark"""

    name: ClassVar[str] = "bookmark"
    user_uuid: UUID
    url_uuid: UUID

    def for_user(self, user: User) -> Access:
        return Access.ALL if user.user_uuid == self.user_uuid else Access.NONE

    def to_params(self) -> Mapping:
        return {"user_uuid": self.user_uuid.hex, "url_uuid": self.url_uuid.hex}

    @classmethod
    def from_params(cls, q: Mapping):
        return cls(user_uuid=UUID(q["user_uuid"]), url_uuid=UUID(q["url_uuid"]))


@dataclass(frozen=True)
class UserBookmarksAccessObject:
    """Represents a user's entire collection of bookmarks - access to this
    object required for creating a new bookmark."""

    name: ClassVar[str] = "user_bookmarks"
    user_uuid: UUID

    def for_user(self, user) -> Access:
        return Access.ALL if user.user_uuid == self.user_uuid else Access.NONE

    def to_params(self) -> Mapping:
        return {"user_uuid": self.user_uuid.hex}

    @classmethod
    def from_params(cls, q: Mapping):
        return cls(user_uuid=UUID(q["user_uuid"]))


def get_access(access_subject: AccessSubject, access_object: AccessObject) -> Access:
    access = Access.NONE
    # Check by user
    if access_subject.user is not None:
        access |= access_object.for_user(access_subject.user)
    # Check by access token
    for grant in access_subject.grants:
        # FIXME: consider expiry here
        if grant.access_object == access_object and not grant.revoked:
            access |= grant.access_verb
    return access


@dataclass(frozen=True)
class ShareGrant:
    share_token: bytes
    expiry: Optional[datetime]
    access_object: AccessObject
    access_verb: Access
    revoked: bool

    def base64_token(self):
        return urlsafe_b64encode(self.share_token)
