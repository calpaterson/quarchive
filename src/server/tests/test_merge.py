import quartermarker as sut
from datetime import datetime

import pytest
from hypothesis import given
from hypothesis.strategies import text, datetimes, booleans

from .conftest import make_bookmark


@given(
    created=datetimes(),
    deleted=booleans(),
    description=text(),
    title=text(),
    unread=booleans(),
    updated=datetimes(),
)
def test_merge_is_idempotent(title, created, updated, deleted, unread, description):
    url = "http://example.com"
    a = sut.Bookmark(
        created=created,
        deleted=deleted,
        description=description,
        title=title,
        unread=unread,
        updated=updated,
        url=url,
    )
    b = a.merge(a)
    assert a == b


@given(
    created_a=datetimes(),
    created_b=datetimes(),
    deleted_a=booleans(),
    deleted_b=booleans(),
    description_a=text(),
    description_b=text(),
    title_a=text(),
    title_b=text(),
    unread_a=booleans(),
    unread_b=booleans(),
    updated_a=datetimes(),
    updated_b=datetimes(),
)
def test_merge_is_commutative(
    created_a,
    created_b,
    deleted_a,
    deleted_b,
    description_a,
    description_b,
    title_a,
    title_b,
    unread_a,
    unread_b,
    updated_a,
    updated_b,
):
    url = "http://example.com"
    a = sut.Bookmark(
        created=created_a,
        deleted=deleted_a,
        description=description_a,
        title=title_a,
        unread=unread_a,
        updated=updated_a,
        url=url,
    )
    b = sut.Bookmark(
        created=created_a,
        deleted=deleted_a,
        description=description_b,
        title=title_b,
        unread=unread_a,
        updated=updated_b,
        url=url,
    )
    c = a.merge(b)
    d = b.merge(a)
    assert c == d


@given(
    created_a=datetimes(),
    created_b=datetimes(),
    created_c=datetimes(),
    deleted_a=booleans(),
    deleted_b=booleans(),
    deleted_c=booleans(),
    description_a=text(),
    description_b=text(),
    description_c=text(),
    title_a=text(),
    title_b=text(),
    title_c=text(),
    unread_a=booleans(),
    unread_b=booleans(),
    unread_c=booleans(),
    updated_a=datetimes(),
    updated_b=datetimes(),
    updated_c=datetimes(),
)
def test_merge_is_associative(
    created_a,
    created_b,
    created_c,
    deleted_a,
    deleted_b,
    deleted_c,
    description_a,
    description_b,
    description_c,
    title_a,
    title_b,
    title_c,
    unread_a,
    unread_b,
    unread_c,
    updated_a,
    updated_b,
    updated_c,
):
    url = "http://example.com"
    a = sut.Bookmark(
        created=created_a,
        deleted=deleted_a,
        description=description_a,
        title=title_a,
        unread=unread_a,
        updated=updated_a,
        url=url,
    )
    b = sut.Bookmark(
        created=created_b,
        deleted=deleted_b,
        description=description_b,
        title=title_b,
        unread=unread_b,
        updated=updated_b,
        url=url,
    )
    c = sut.Bookmark(
        created=created_c,
        deleted=deleted_c,
        description=description_c,
        title=title_c,
        unread=unread_c,
        updated=updated_c,
        url=url,
    )
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
