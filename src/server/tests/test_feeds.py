from datetime import datetime, timezone

import pytest

from quarchive.rss import check_all_due_feeds
from quarchive.data.feeds import get_entries_for_user


@pytest.mark.xfail(reason="not implemented")
def test_getting_feed_for_first_time(session, test_user):
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    # setup

    check_all_due_feeds()

    entries = list(get_entries_for_user(session, test_user, now))
    assert len(entries) > 0
