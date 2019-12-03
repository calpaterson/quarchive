import quartermarker as sut

import pytest
from hypothesis import given
from hypothesis.strategies import text, integers


@given(title=text(), timestamp=integers())
def test_merge_is_idempotent(title, timestamp):
    url = "http://example.com"
    a = sut.Bookmark(url=url, title=title, timestamp=timestamp)
    b = a.merge(a)
    assert a == b


@given(title_a=text(), timestamp_a=integers(), title_b=text(), timestamp_b=integers())
def test_merge_is_commutative(title_a, title_b, timestamp_a, timestamp_b):
    url = "http://example.com"
    a = sut.Bookmark(url=url, title=title_a, timestamp=timestamp_a)
    b = sut.Bookmark(url=url, title=title_b, timestamp=timestamp_b)
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
)
def test_merge_is_associative(
    title_a, title_b, title_c, timestamp_a, timestamp_b, timestamp_c
):
    url = "http://example.com"
    a = sut.Bookmark(url=url, title=title_a, timestamp=timestamp_a)
    b = sut.Bookmark(url=url, title=title_b, timestamp=timestamp_b)
    c = sut.Bookmark(url=url, title=title_c, timestamp=timestamp_c)
    d = a.merge(b).merge(c)
    e = a.merge(b.merge(c))
    assert d == e
