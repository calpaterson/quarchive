import json
from uuid import UUID
from typing import Optional, Mapping, ClassVar, Tuple, Iterable, Sequence
import enum
from functools import lru_cache
from dataclasses import dataclass

import flask

from quarchive.value_objects import User


class Access(enum.IntFlag):
    NONE = 0
    READ = 1
    WRITE = 2
    READWRITE = 3


@dataclass(frozen=True)
class BookmarkSubject:
    name: ClassVar[str] = "bookmark"
    user_uuid: UUID
    url_uuid: UUID

    def for_user(self, user: User) -> Access:
        if user.user_uuid == self.user_uuid:
            return Access.READWRITE
        else:
            return Access.NONE

    def to_json(self) -> Mapping:
        return {"user_uuid": self.user_uuid.hex, "url_uuid": self.url_uuid.hex}

    @classmethod
    def from_json(cls, q: Mapping):
        return cls(user_uuid=UUID(q["user_uuid"]), url_uuid=UUID(q["url_uuid"]))


@lru_cache(16)
def to_access_token(subject: BookmarkSubject, access: Access) -> str:
    # Try to keep it short, this will go in a cookie on every request
    # Keys are sorted to allow for loading to be cached
    return json.dumps(
        {"q": subject.to_json(), "n": subject.name, "a": int(access)},
        sort_keys=True,
        separators=(",", ":"),
    )


@lru_cache(16)
def from_access_token(token: str) -> Tuple[BookmarkSubject, Access]:
    parts = json.loads(token)
    if parts["n"] == "bookmark":
        return BookmarkSubject.from_json(parts["q"]), Access(parts["a"])
    else:
        raise RuntimeError("unknown subject name: {parts['n']}")


def get_access(
    subject: "BookmarkSubject",
    user: Optional[User] = None,
    access_tokens: Iterable[str] = frozenset(),
) -> Access:
    access = Access.NONE
    # Check by user
    if user is not None:
        access |= subject.for_user(user)
    # Check by access token
    for access_token in access_tokens:
        token_subject, token_access = from_access_token(access_token)
        if token_subject == subject:
            access |= token_access
    return access


def get_access_tokens(request: flask.Request) -> Sequence[str]:
    return []
