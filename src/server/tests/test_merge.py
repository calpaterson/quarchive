import quartermarker as sut

import pytest
from hypothesis import given
from hypothesis.strategies import text, datetimes, booleans


@given(title=text(), timestamp=datetimes(), deleted=booleans(), unread=booleans())
def test_merge_is_idempotent(title, timestamp, deleted, unread):
    url = "http://example.com"
    a = sut.Bookmark(
        url=url, title=title, updated=timestamp, deleted=deleted, unread=unread
    )
    b = a.merge(a)
    assert a == b


@given(
    title_a=text(),
    timestamp_a=datetimes(),
    title_b=text(),
    timestamp_b=datetimes(),
    deleted_a=booleans(),
    deleted_b=booleans(),
    unread_a=booleans(),
    unread_b=booleans(),
)
def test_merge_is_commutative(
    title_a, title_b, timestamp_a, timestamp_b, unread_a, unread_b, deleted_a, deleted_b
):
    url = "http://example.com"
    a = sut.Bookmark(
        url=url, title=title_a, updated=timestamp_a, deleted=deleted_a, unread=unread_a,
    )
    b = sut.Bookmark(
        url=url, title=title_b, updated=timestamp_b, deleted=deleted_a, unread=unread_a,
    )
    c = a.merge(b)
    d = b.merge(a)
    assert c == d


@given(
    title_a=text(),
    timestamp_a=datetimes(),
    title_b=text(),
    timestamp_b=datetimes(),
    title_c=text(),
    timestamp_c=datetimes(),
    deleted_a=booleans(),
    deleted_b=booleans(),
    deleted_c=booleans(),
    unread_a=booleans(),
    unread_b=booleans(),
    unread_c=booleans(),
)
def test_merge_is_associative(
    title_a,
    title_b,
    title_c,
    timestamp_a,
    timestamp_b,
    timestamp_c,
    unread_a,
    unread_b,
    unread_c,
    deleted_a,
    deleted_b,
    deleted_c,
):
    url = "http://example.com"
    a = sut.Bookmark(
        url=url, title=title_a, updated=timestamp_a, unread=unread_a, deleted=deleted_a,
    )
    b = sut.Bookmark(
        url=url, title=title_b, updated=timestamp_b, unread=unread_b, deleted=deleted_b,
    )
    c = sut.Bookmark(
        url=url, title=title_c, updated=timestamp_c, unread=unread_c, deleted=deleted_c,
    )
    d = a.merge(b).merge(c)
    e = a.merge(b.merge(c))
    assert d == e
