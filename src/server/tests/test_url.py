from urllib.parse import urlsplit, urlunsplit

import pytest
from hypothesis import given
from hypothesis.provisional import urls

from quarchive.value_objects import (
    URL,
    BadCanonicalisationException,
    DisallowedSchemeException,
)


def test_from_string():
    url = URL.from_string("http://example.com/a?b=c#d")
    assert url.scheme == "http"
    assert url.netloc == "example.com"
    assert url.path == "/a"
    assert url.query == "b=c"
    assert url.fragment == "d"


@pytest.mark.parametrize(
    "url", ["ftp://calpaterson.com/foo/bar", "rsync://calpaterson.com:", "about:blank"]
)
def test_from_string_disallowed_schemes(url):
    with pytest.raises(DisallowedSchemeException):
        URL.from_string(url)


def test_from_string_with_empty_path():
    with pytest.raises(BadCanonicalisationException):
        URL.from_string("http://example.com")


def test_to_string():
    url_string = "http://example.com/a?b=c#d"
    url = URL.from_string(url_string)
    assert url.to_string() == url_string


@given(url=urls())
def test_url_uuid_stability(url):
    # This is not a piece of code as such but an important property - need to
    # be sure that urlsplit, urlunsplit and create_url_uuid work together and
    # are stable.
    URL.from_string(urlunsplit(urlsplit(url))) == URL.from_string(url)


@pytest.mark.parametrize("problem_url", ["http://example.com?", "http://example.com#",])
def test_url_from_non_minimal_canonicalisation_fails(problem_url):
    with pytest.raises(BadCanonicalisationException) as e:
        URL.from_string(problem_url)

    assert e.value.url_string == problem_url
