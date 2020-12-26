from uuid import uuid4
import pytest

from quarchive.value_objects import BookmarkView

from .conftest import make_bookmark


@pytest.mark.parametrize(
    "input_title, expected_title",
    [
        ("normal title", "normal title"),
        ("", "[no title]"),
        ("f" * 200, ("f" * 67) + "..."),
    ],
)
def test_title(input_title, expected_title):
    bm = make_bookmark(title=input_title)

    view = BookmarkView(
        owner=None,  # type: ignore
        bookmark=bm,
        icon_uuid=uuid4(),
        canonical_url=None,
        link_count=0,
        backlink_count=0,
    )

    assert view.title() == expected_title
