from datetime import datetime

from freezegun import freeze_time
import flask
import pytest

from quarchive.data.models import SQLDiscussion, SQLDiscussionFetch
from quarchive.data.functions import set_bookmark
from quarchive.data.discussion_functions import upsert_discussions, DiscussionFrontier
from quarchive.value_objects import Discussion, DiscussionSource

from .conftest import make_bookmark, random_numeric_id, random_url
from .utils import sync_bookmarks


def test_discussions(signed_in_client, test_user, session):
    bm = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm)

    discussions = [
        Discussion(
            external_id=str(random_numeric_id()),
            source=DiscussionSource.HN,
            url=bm.url,
            comment_count=1,
            created_at=datetime(2018, 1, 3),
            title="HN discussion 1",
        )
    ]

    upsert_discussions(session, discussions)

    response = signed_in_client.get(
        flask.url_for(
            "quarchive.discussions",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert response.status_code == 200


def test_discussion_frontier_count(session):
    """Test that we can get a count of how big the frontier is"""
    frontier = DiscussionFrontier(session, test_mode=True)
    assert type(frontier.size()) == int


def test_discussion_frontier_contains_is_present(session, signed_in_client, test_user):
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])
    frontier = DiscussionFrontier(session, test_mode=True)
    assert frontier.contains(bm.url.url_uuid, DiscussionSource.HN)
    assert frontier.contains(bm.url.url_uuid, DiscussionSource.REDDIT)


def test_discussion_frontier_contains_absent(session):
    """Test that .contains() returns false for urls that aren't present"""
    frontier = DiscussionFrontier(session, test_mode=True)
    url = random_url()
    assert not frontier.contains(url.url_uuid, DiscussionSource.HN)
    assert not frontier.contains(url.url_uuid, DiscussionSource.REDDIT)


@freeze_time("2018-01-03T12:00:00")
@pytest.mark.parametrize(
    "last_discussion_created, last_fetch, expected",
    [
        pytest.param(None, None, True, id="never retrieved"),
        pytest.param(
            datetime(2018, 1, 3, 11, 30),
            datetime(2018, 1, 3, 11, 59),
            False,
            id="recently retrieved and not due",
        ),
        pytest.param(
            datetime(2018, 1, 3, 10),
            datetime(2018, 1, 3, 10, 30),
            True,
            id="due for an early recheck",
        ),
        pytest.param(
            datetime(2018, 1, 3, 11),
            datetime(2018, 1, 3, 11, 31),
            False,
            id="not quite due for an early recheck",
        ),
        pytest.param(
            datetime(2017, 1, 3),
            datetime(2017, 1, 3),
            True,
            id="retrieved too long ago",
        ),
    ],
)
def test_discussion_frontier_thresholds(
    session, signed_in_client, test_user, last_discussion_created, last_fetch, expected
):
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])
    if last_discussion_created is not None:
        session.add(
            SQLDiscussion(
                external_discussion_id=str(random_numeric_id()),
                discussion_source_id=1,
                url_uuid=bm.url.url_uuid,
                comment_count=0,
                created_at=last_discussion_created,
                title="Test discussion",
            )
        )
    if last_fetch is not None:
        session.add(
            SQLDiscussionFetch(
                url_uuid=bm.url.url_uuid,
                discussion_source_id=DiscussionSource.HN.value,
                status_code=200,
                retrieved=last_fetch,
            )
        )
    session.commit()

    frontier = DiscussionFrontier(session, test_mode=True)
    assert frontier.contains(bm.url.url_uuid, DiscussionSource.HN) == expected
