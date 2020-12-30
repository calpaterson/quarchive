from quarchive.value_objects import URL
from quarchive.discussions import get_hn_api_url

import pytest


@pytest.mark.parametrize(
    "input_url, expected_url",
    [
        pytest.param(
            "http://example.com/",
            "https://hn.algolia.com/api/v1/search?query=http%3A%2F%2Fexample.com%2F&restrictSearchableAttributes=url",
            id="example.com",
        )
    ],
)
def test_get_hn_api_url(input_url, expected_url):
    assert get_hn_api_url(URL.from_string(input_url)).to_string() == expected_url
