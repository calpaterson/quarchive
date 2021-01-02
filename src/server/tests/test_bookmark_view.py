from uuid import uuid4
import pytest

from quarchive.value_objects import BookmarkView, DiscussionDigest

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
        discussion_digest=DiscussionDigest(
            comment_count=0, discussion_count=0, sources=set()
        ),
    )

    assert view.title() == expected_title


@pytest.mark.parametrize(
    "input_markdown,expected_html",
    [
        pytest.param("*emphasis!*", "<p><em>emphasis!</em></p>\n", id="emphasis"),
        pytest.param("", "", id="empty string"),
        pytest.param(" ", "", id="whitespace"),
        pytest.param(
            """<script>alert("worrying...")</script>""",
            "<!-- raw HTML omitted -->\n",
            id="evil html",
        ),
        pytest.param(
            "> a blockquote",
            "<blockquote>\n<p>a blockquote</p>\n</blockquote>\n",
            id="blockquotes",
        ),
    ],
)
def test_markdown_output(input_markdown, expected_html):
    bm = make_bookmark(description=input_markdown)
    view = BookmarkView(
        owner=None,  # type: ignore
        bookmark=bm,
        icon_uuid=uuid4(),
        canonical_url=None,
        link_count=0,
        backlink_count=0,
        discussion_digest=DiscussionDigest(
            comment_count=0, discussion_count=0, sources=set()
        ),
    )

    assert view.html_description() == expected_html
