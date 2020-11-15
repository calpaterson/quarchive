import re
from os import path

import pytest

from quarchive.value_objects import URL
from quarchive.html_metadata import (
    Icon,
    IconScope,
    best_icon,
    extract_metadata_from_html,
    HTMLMetadata,
)

from .conftest import test_data_path

WORDS_REGEX = re.compile(r"\w+")


def test_simple():
    url = URL.from_string("http://example.com/webpage-with-full-metadata.html")
    with open(
        path.join(test_data_path, "webpage-with-full-metadata.html"), "rb"
    ) as html_f:
        metadata = extract_metadata_from_html(url, html_f)

    text_words = set(WORDS_REGEX.findall(metadata.text))  # type: ignore
    assert "Simple" in text_words
    assert {"This", "is", "a", "basic", "html", "document"} <= text_words

    meta_words = set(WORDS_REGEX.findall(metadata.meta_desc))  # type: ignore
    assert {"some", "meta", "description"} == meta_words

    assert metadata.url == url
    assert metadata.icons == [
        Icon(
            url=URL.from_string("http://example.com/favicon.png"),
            scope=IconScope.PAGE,
            metadata={"type": "image/png"},
        )
    ]
    assert metadata.canonical == URL.from_string("http://example.com/simple")
    assert metadata.title == "Simple"
    assert metadata.links == {URL.from_string("http://example.com/other")}
    assert metadata.meta_desc == "some meta description"


def test_calpaterson():
    url = URL.from_string("http://calpaterson.com/calpaterson.html")
    with open(path.join(test_data_path, "calpaterson.html"), "rb") as html_f:
        metadata = extract_metadata_from_html(url, html_f)

    words = WORDS_REGEX.findall(metadata.text)  # type: ignore
    # pass/fail
    assert len(words) > 0


@pytest.mark.parametrize(
    "icons, expected",
    [
        pytest.param(
            [],
            Icon(
                url=URL.from_string("http://example.com/favicon.ico"),
                scope=IconScope.DOMAIN,
            ),
            id="fallback icon",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon.png"),
                    scope=IconScope.PAGE,
                )
            ],
            Icon(
                url=URL.from_string("http://example.com/favicon.png"),
                scope=IconScope.PAGE,
            ),
            id="just a png icon",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon.png"),
                    scope=IconScope.PAGE,
                ),
                Icon(
                    URL.from_string("http://example.com/favicon.ico"),
                    scope=IconScope.PAGE,
                ),
            ],
            Icon(
                url=URL.from_string("http://example.com/favicon.png"),
                scope=IconScope.PAGE,
            ),
            id="explicit ico and png",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon.png"),
                    scope=IconScope.PAGE,
                ),
                Icon(
                    URL.from_string("http://example.com/favicon.svg"),
                    scope=IconScope.PAGE,
                ),
            ],
            Icon(
                url=URL.from_string("http://example.com/favicon.svg"),
                scope=IconScope.PAGE,
            ),
            id="explicit svg and png",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon_a"),
                    scope=IconScope.PAGE,
                ),
                Icon(
                    URL.from_string("http://example.com/favicon_b"),
                    scope=IconScope.PAGE,
                    metadata={"sizes": "any"},
                ),
            ],
            Icon(
                url=URL.from_string("http://example.com/favicon_b"),
                scope=IconScope.PAGE,
                metadata={"sizes": "any"},
            ),
            id="explicit svg and png",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon_b"),
                    scope=IconScope.PAGE,
                    metadata={"sizes": "128y128"},
                ),
            ],
            Icon(
                url=URL.from_string("http://example.com/favicon.ico"),
                scope=IconScope.DOMAIN,
            ),
            id="junk size",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon_1"),
                    scope=IconScope.PAGE,
                    metadata={"sizes": "128x128"},
                ),
                Icon(
                    URL.from_string("http://example.com/favicon_b"),
                    scope=IconScope.PAGE,
                    metadata={"sizes": "256x256"},
                ),
            ],
            Icon(
                URL.from_string("http://example.com/favicon_b"),
                scope=IconScope.PAGE,
                metadata={"sizes": "256x256"},
            ),
            id="multiple sizes",
        ),
        pytest.param(
            [
                Icon(
                    URL.from_string("http://example.com/favicon_1"),
                    scope=IconScope.PAGE,
                    metadata={"type": "something else"},
                ),
                Icon(
                    URL.from_string("http://example.com/favicon_b"),
                    scope=IconScope.PAGE,
                    metadata={"type": "image/png"},
                ),
            ],
            Icon(
                URL.from_string("http://example.com/favicon_b"),
                scope=IconScope.PAGE,
                metadata={"type": "image/png"},
            ),
            id="mime as type param",
        ),
    ],
)
def test_best_icon(icons, expected):
    url = URL.from_string("http://example.com/")
    metadata = HTMLMetadata(url=url, icons=icons)
    assert best_icon(metadata) == expected
