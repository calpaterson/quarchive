from typing import Tuple, List, Iterable
from .value_objects import Feed, FeedEntry, URL

from quarchive.data.feeds import upsert_feeds


def parse_feed(feed_str: str) -> Tuple[Feed, List[FeedEntry]]:
    ...


def check_feeds(urls: Iterable[URL]) -> None:
    ...


def check_all_due_feeds() -> None:
    ...
