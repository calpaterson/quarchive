import pytest

from quarchive.value_objects import BookmarkView

from .conftest import make_bookmark


@pytest.mark.parametrize(
    "input_title, expected_title",
    [
        ("normal title", "normal title"),
        ("", "[no title]"),
        ("f" * 200, ("f" * 65) + "[...]"),
    ],
)
def test_title(input_title, expected_title):
    bm = make_bookmark(title=input_title)

    view = BookmarkView(bookmark=bm)

    assert view.title() == expected_title
