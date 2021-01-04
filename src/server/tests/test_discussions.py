from typing import Mapping
from datetime import datetime, timedelta
import re

import requests

import responses
from .conftest import random_url

from quarchive.value_objects import URL, Discussion, DiscussionSource
from quarchive.discussions import (
    get_hn_api_url,
    RedditTokenClient,
    RedditDiscussionClient,
)

import pytest


# FIXME: test hn no results!!


@pytest.mark.parametrize(
    "input_url, expected_url",
    [
        pytest.param(
            "http://example.com/",
            "https://hn.algolia.com/api/v1/search?query=http%3A%2F%2Fexample.com%2F&restrictSearchableAttributes=url&hitsPerPage=1000",
            id="example.com",
        )
    ],
)
def test_get_hn_api_url(input_url, expected_url):
    assert get_hn_api_url(URL.from_string(input_url)).to_string() == expected_url


def test_get_reddit_device_id(http_client):
    token_client = RedditTokenClient(http_client, "", "")
    assert isinstance(token_client.device_id, str)
    assert len(token_client.device_id) == 30


def test_get_reddit_token(http_client, requests_mock):
    expected_token = "arb string"
    requests_mock.add(
        responses.POST,
        "https://www.reddit.com/api/v1/access_token",
        json={
            "access_token": expected_token,
            "token_type": "bearer",
            "device_id": "deadbeef",
            "expires_in": 3600,
            "scope": "read",
        },
    )

    token_client = RedditTokenClient(http_client, client_id="", client_secret="")
    assert token_client.get_token() == expected_token

    requests_mock.remove(responses.POST, "https://www.reddit.com/api/v1/access_token")

    # Assert that it still works without having to refetch each time
    assert token_client.get_token() == expected_token


def test_get_reddit_token_failure(http_client, requests_mock):
    requests_mock.add(
        responses.POST,
        "https://www.reddit.com/api/v1/access_token",
        status=400,
        json={"error": "bad bytes"},
    )
    token_client = RedditTokenClient(http_client, client_id="", client_secret="")
    with pytest.raises(requests.exceptions.RequestException):
        token_client.get_token()


def make_reddit_search_response(**data_kwargs):
    rv: Mapping = {"data": {"children": []}}
    rv["data"].update(data_kwargs)
    return rv


def make_reddit_link(**data_kwargs):
    rv: Mapping = {
        "kind": "t3",
        "data": {
            "id": "test",
            "num_comments": 0,
            "created_utc": float(datetime(2018, 1, 3).timestamp()),
            "subreddit_name_prefixed": "r/test",
            "title": "An example",
        },
    }
    rv["data"].update(data_kwargs)
    return rv


def test_reddit_client(http_client, requests_mock):
    url = random_url()

    reddit_client = RedditDiscussionClient(http_client, client_id="", client_secret="")
    # Manually set these
    reddit_client.token_client.expiry = datetime.utcnow() + timedelta(minutes=30)
    reddit_client.token_client._token = "abc123"

    expected_id = "def654"

    requests_mock.add(
        responses.GET,
        re.compile(f"^https://api.reddit.com/search.*"),
        json=make_reddit_search_response(
            children=[
                make_reddit_link(id=expected_id, num_comments=10, url=url.to_string())
            ]
        ),
    )
    (discussion,) = list(reddit_client.discussions_for_url(url))
    assert discussion == Discussion(
        external_id=expected_id,
        source=DiscussionSource.REDDIT,
        title="r/test: An example",
        comment_count=10,
        created_at=datetime(2018, 1, 3),
        url=url,
    )
