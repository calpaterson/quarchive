import quartermarker as sut

import pytest


@pytest.mark.parametrize(
    "url", ["http://example.com/"],
)
def test_merge_is_idempotent(url):
    a = sut.Bookmark(url)
    b = a.merge(a)
    assert a == b


@pytest.mark.parametrize(
    "url_a, url_b", [("http://example.com/", "http://example.com/")],
)
def test_merge_is_commutative(url_a, url_b):
    a = sut.Bookmark(url_a)
    b = sut.Bookmark(url_b)
    c = a.merge(b)
    d = b.merge(a)
    assert c == d


@pytest.mark.parametrize(
    "url_a, url_b, url_c",
    [("http://example.com/", "http://example.com/", "http://example.com/")],
)
def test_merge_is_associative(url_a, url_b, url_c):
    a = sut.Bookmark(url_a)
    b = sut.Bookmark(url_b)
    c = sut.Bookmark(url_c)
    d = a.merge(b).merge(c)
    e = a.merge(b.merge(c))
    assert d == e
