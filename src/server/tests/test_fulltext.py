from os import path
import re

from quarchive import extract_full_text

from .conftest import test_data_path

WORDS_REGEX = re.compile(r"\w+")


def test_simple():
    with open(path.join(test_data_path, "simple-website.html"), "rb") as html_f:
        full_text = extract_full_text(html_f)

    words = WORDS_REGEX.findall(full_text)
    assert words == ["Simple", "This", "is", "a", "basic", "html", "document"]


def test_calpaterson():
    with open(path.join(test_data_path, "calpaterson.html"), "rb") as html_f:
        full_text = extract_full_text(html_f)

    words = WORDS_REGEX.findall(full_text)
    # pass/fail
    assert len(words) > 0
