import quartermarker as sut

import pytest
from hypothesis import given
from hypothesis.strategies import text, integers, booleans


@given(title=text(), timestamp=integers(), deleted=booleans(), unread=booleans())
def test_merge_is_idempotent(title, timestamp, deleted, unread):
    url = "http://example.com"
    a = sut.Bookmark(
        url=url, title=title, timestamp=timestamp, deleted=deleted, unread=unread
    )
    b = a.merge(a)
    assert a == b


@given(
    title_a=text(),
    timestamp_a=integers(),
    title_b=text(),
    timestamp_b=integers(),
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
        url=url,
        title=title_a,
        timestamp=timestamp_a,
        deleted=deleted_a,
        unread=unread_a,
    )
    b = sut.Bookmark(
        url=url,
        title=title_b,
        timestamp=timestamp_b,
        deleted=deleted_a,
        unread=unread_a,
    )
    c = a.merge(b)
    d = b.merge(a)
    assert c == d


@given(
    title_a=text(),
    timestamp_a=integers(),
    title_b=text(),
    timestamp_b=integers(),
    title_c=text(),
    timestamp_c=integers(),
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
        url=url,
        title=title_a,
        timestamp=timestamp_a,
        unread=unread_a,
        deleted=deleted_a,
    )
    b = sut.Bookmark(
        url=url,
        title=title_b,
        timestamp=timestamp_b,
        unread=unread_b,
        deleted=deleted_b,
    )
    c = sut.Bookmark(
        url=url,
        title=title_c,
        timestamp=timestamp_c,
        unread=unread_c,
        deleted=deleted_c,
    )
    d = a.merge(b).merge(c)
    e = a.merge(b.merge(c))
    assert d == e
