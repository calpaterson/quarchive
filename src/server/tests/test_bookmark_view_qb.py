from datetime import datetime

import pytest

from quarchive.value_objects import URL, Discussion, DiscussionSource
from quarchive.data.models import CanonicalUrl
from quarchive.data.bvqb import BookmarkViewQueryBuilder
from quarchive.data.discussion_functions import upsert_discussions
from quarchive.data.functions import (
    record_page_icon,
    set_bookmark,
    upsert_links,
    upsert_url,
)

from .conftest import make_bookmark, random_bytes, random_string, random_numeric_id


def test_simple_bookmark(session, test_user):
    bm = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm)

    (found,) = list(BookmarkViewQueryBuilder(session, test_user).execute())
    assert found.bookmark == bm


def test_links_and_backlinks(session, test_user):
    bm1 = make_bookmark()
    bm2 = make_bookmark()
    bm3 = make_bookmark()
    bm4 = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm1)
    set_bookmark(session, test_user.user_uuid, bm2)
    set_bookmark(session, test_user.user_uuid, bm3)
    set_bookmark(session, test_user.user_uuid, bm4)
    upsert_links(session, bm1.url, {bm2.url, bm3.url})
    upsert_links(session, bm4.url, {bm1.url})

    (bm1_view,) = (
        f
        for f in BookmarkViewQueryBuilder(session, test_user).execute()
        if f.bookmark == bm1
    )
    assert bm1_view.link_count == 2
    assert bm1_view.backlink_count == 1

    bm1_links = (
        BookmarkViewQueryBuilder(session, test_user).links(bm1.url.url_uuid).execute()
    )
    bm1_links_bvs = {bv.bookmark for bv in bm1_links}
    assert bm1_links_bvs == {bm2, bm3}

    bm1_backlinks = (
        BookmarkViewQueryBuilder(session, test_user)
        .backlinks(bm1.url.url_uuid)
        .execute()
    )
    bm1_links_bvs = {bv.bookmark for bv in bm1_backlinks}
    assert bm1_links_bvs == {bm4}


@pytest.mark.parametrize(
    "canonical_url",
    [
        pytest.param(True, id="canonical url"),
        pytest.param(False, id="no canonical url"),
    ],
)
def test_icon_uuids_url_icon(session, test_user, canonical_url):
    bm1 = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm1)
    if canonical_url:
        canonical_url = bm1.url.follow("canonical.html")
        upsert_url(session, canonical_url)
        session.add(
            CanonicalUrl(
                non_canonical_url_uuid=bm1.url.url_uuid,
                canonical_url_uuid=canonical_url.url_uuid,
            )
        )

    icon_url = URL.from_string("http://example.com/" + random_string() + "/icon.png")
    upsert_url(session, icon_url)
    random_hash = random_bytes(64)
    icon_uuid = record_page_icon(session, icon_url, bm1.url, random_hash)

    (bm1_view,) = (f for f in BookmarkViewQueryBuilder(session, test_user).execute())
    assert bm1_view.icon_uuid == icon_uuid


def test_discussion_digests_no_discussions(session, test_user):
    bm = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm)

    (bm1_view,) = (f for f in BookmarkViewQueryBuilder(session, test_user).execute())
    assert bm1_view.discussion_digest.comment_count == 0
    assert bm1_view.discussion_digest.discussion_count == 0
    assert bm1_view.discussion_digest.sources == set()


def test_discussion_digests(session, test_user):
    bm = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm)

    discussions = [
        Discussion(
            external_id=str(random_numeric_id()),
            source=DiscussionSource.HN,
            url=bm.url,
            comment_count=1,
            created_at=datetime(2018, 1, 3),
            title="example",
        ),
        Discussion(
            external_id=str(random_numeric_id()),
            source=DiscussionSource.HN,
            url=bm.url,
            comment_count=0,
            created_at=datetime(2018, 1, 3),
            title="example",
        ),
        Discussion(
            external_id=str(random_numeric_id()),
            source=DiscussionSource.HN,
            url=bm.url,
            comment_count=100,
            created_at=datetime(2018, 1, 3),
            title="example",
        ),
        Discussion(
            external_id=str(random_numeric_id()),
            source=DiscussionSource.REDDIT,
            url=bm.url,
            comment_count=1,
            created_at=datetime(2018, 1, 3),
            title="example",
        ),
    ]

    upsert_discussions(session, discussions)
    (bm1_view,) = (f for f in BookmarkViewQueryBuilder(session, test_user).execute())
    assert bm1_view.discussion_digest.comment_count == 102
    assert bm1_view.discussion_digest.discussion_count == 4
    assert bm1_view.discussion_digest.sources == {
        DiscussionSource.HN,
        DiscussionSource.REDDIT,
    }
