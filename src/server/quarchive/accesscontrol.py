import json
from uuid import UUID
from typing import Optional, Mapping, ClassVar, Tuple, Sequence
import enum
from functools import lru_cache
from dataclasses import dataclass

from quarchive.value_objects import User


class Access(enum.IntFlag):
    NONE = 0
    READ = 1
    WRITE = 2
    READACCESS = 4
    WRITEACCESS = 8
    ALL = 15


AccessToken = str


@dataclass(frozen=True)
class AccessSubject:
    user: Optional[User]
    tokens: Sequence[AccessToken]


@dataclass(frozen=True)
class BookmarkAccessObject:
    name: ClassVar[str] = "bookmark"
    user_uuid: UUID
    url_uuid: UUID

    def for_user(self, user: User) -> Access:
        if user.user_uuid == self.user_uuid:
            return Access.ALL
        else:
            return Access.NONE

    def to_json(self) -> Mapping:
        return {"user_uuid": self.user_uuid.hex, "url_uuid": self.url_uuid.hex}

    @classmethod
    def from_json(cls, q: Mapping):
        return cls(user_uuid=UUID(q["user_uuid"]), url_uuid=UUID(q["url_uuid"]))


@lru_cache(16)
def to_access_token(subject: BookmarkAccessObject, access: Access) -> AccessToken:
    # Try to keep it short, this will go in a cookie on every request
    # Keys are sorted to allow for loading to be cached
    return json.dumps(
        {"q": subject.to_json(), "n": subject.name, "a": int(access)},
        sort_keys=True,
        separators=(",", ":"),
    )


@lru_cache(16)
def from_access_token(token: AccessToken) -> Tuple[BookmarkAccessObject, Access]:
    parts = json.loads(token)
    if parts["n"] == "bookmark":
        return BookmarkAccessObject.from_json(parts["q"]), Access(parts["a"])
    else:
        raise RuntimeError("unknown subject name: {parts['n']}")


def get_access(
    access_subject: AccessSubject, access_object: "BookmarkAccessObject",
) -> Access:
    access = Access.NONE
    # Check by user
    if access_subject.user is not None:
        access |= access_object.for_user(access_subject.user)
    # Check by access token
    for access_token in access_subject.tokens:
        token_object, token_access = from_access_token(access_token)
        if token_object == access_object:
            access |= token_access
    return access
