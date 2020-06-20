from typing import Tuple, List, Sequence, Iterable
from datetime import datetime

from sqlalchemy.orm import Session

from ..value_objects import Feed, FeedEntry, URL, User


def get_feeds_due(session: Session) -> Iterable[URL]:
    ...


def upsert_feeds(session: Session, feeds: Sequence[Tuple[Feed, List[FeedEntry]]]) -> None:
    ...


def add_feed(session, url: URL) -> Feed:
    ...


def subscribe_to_feed(session: Session, feed: Feed, user: User) -> None:
    ...


def unsubscribe_from_feed(session: Session, feed: Feed, user: User) -> None:
    ...


def get_entries_for_user(session: Session, user: User, as_of: datetime) -> Iterable[Tuple[Feed, List[FeedEntry]]]:
    ...
