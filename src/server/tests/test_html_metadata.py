import re
from os import path
from quarchive import html_metadata

from .conftest import test_data_path

WORDS_REGEX = re.compile(r"\w+")


def test_simple():
    with open(path.join(test_data_path, "simple-website.html"), "rb") as html_f:
        metadata = html_metadata.extract_metadata_from_html(html_f)

    text_words = set(WORDS_REGEX.findall(metadata.text))  # type: ignore
    assert "Simple" in text_words
    assert {"This", "is", "a", "basic", "html", "document"} <= text_words

    meta_words = set(WORDS_REGEX.findall(metadata.meta_desc))  # type: ignore
    assert {"meta", "description"} <= meta_words


def test_calpaterson():
    with open(path.join(test_data_path, "calpaterson.html"), "rb") as html_f:
        metadata = html_metadata.extract_metadata_from_html(html_f)

    words = WORDS_REGEX.findall(metadata.text)  # type: ignore
    # pass/fail
    assert len(words) > 0
