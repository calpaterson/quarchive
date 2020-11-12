from datetime import datetime, timezone

from enum import Enum
from typing import Optional, Mapping

from quarchive.value_objects import URL


class Archive(Enum):
    WAYBACK = "wayback_machine"
    ARCHIVE_TODAY = "archive_today"
    GOOGLE_CACHE = "google_cache"


def get_archive_links(
    url: URL, circa: Optional[datetime] = None
) -> Mapping[Archive, URL]:
    if circa is None:
        circa = datetime.utcnow().replace(tzinfo=timezone.utc)

    # This is the internet archive's timestamp format, which archive_today
    # helpfully also supports
    ia_timestamp = circa.strftime("%Y%m%d%H%M%S")

    links = {}
    links[Archive.WAYBACK] = URL.from_string(
        f"https://web.archive.org/web/{ia_timestamp}/{url.to_string()}"
    )
    links[Archive.ARCHIVE_TODAY] = URL.from_string(
        f"https://archive.today/{ia_timestamp}/{url.to_string()}"
    )
    links[Archive.GOOGLE_CACHE] = URL.from_string(
        f"https://webcache.googleusercontent.com/search?q=cache:{url.to_string()}"
    )
    return links
