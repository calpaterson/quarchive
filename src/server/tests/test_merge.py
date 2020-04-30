from urllib.parse import urlsplit, urlunsplit

import quarchive as sut
from datetime import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.provisional import urls

from .conftest import make_bookmark


@given(url=urls())
def test_url_uuid_stability(url):
    # This is not a piece of code as such but an important property - need to
    # be sure that urlsplit, urlunsplit and create_url_uuid work together and
    # are stable.
    sut.create_url_uuid(urlunsplit(urlsplit(url))) == sut.create_url_uuid(url)


UrlStrategy = st.shared(urls())

TagStrategy = st.one_of(st.just("tag_a"), st.just("tag_b"), st.just("tag_c"))


@st.composite
def tag_triples(draw, tags=TagStrategy, dts=st.datetimes(), bools=st.booleans()):
    as_list = draw(st.lists(st.tuples(tags, dts, bools), unique_by=lambda tt: tt[0]))
    return frozenset(as_list)


BookmarkStrategy = st.builds(
    sut.Bookmark,
    url=UrlStrategy,
    created=st.datetimes(),
    deleted=st.booleans(),
    description=st.text(),
    title=st.text(),
    unread=st.booleans(),
    updated=st.datetimes(),
    tag_triples=tag_triples(),
)


@given(bookmark=BookmarkStrategy)
def test_merge_is_idempotent(bookmark):
    a = bookmark
    b = a.merge(a)
    assert a == b


@given(a=BookmarkStrategy, b=BookmarkStrategy)
def test_merge_is_commutative(a, b):
    c = a.merge(b)
    d = b.merge(a)
    assert c == d


@given(a=BookmarkStrategy, b=BookmarkStrategy, c=BookmarkStrategy)
def test_merge_is_associative(a, b, c):
    d = a.merge(b).merge(c)
    e = a.merge(b.merge(c))
    assert d == e


@pytest.mark.parametrize(
    "field, from_, to_, expected",
    [
        ("deleted", False, True, True),
        ("deleted", True, False, False),
        ("title", "First title", "Second title", "Second title"),
        ("created", datetime(2018, 1, 2), datetime(2018, 1, 3), datetime(2018, 1, 2)),
    ],
)
def test_mutations(field, from_, to_, expected):
    state_1 = make_bookmark(**{field: from_}, updated=datetime(2018, 1, 2))
    state_2 = make_bookmark(**{field: to_}, updated=datetime(2018, 1, 3))
    merged = state_1.merge(state_2)
    assert getattr(merged, field) == expected
