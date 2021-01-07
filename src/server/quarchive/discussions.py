from datetime import datetime, timedelta
from uuid import getnode
from hashlib import blake2b
import itertools
from typing import List

from urllib.parse import quote_plus, urlencode, parse_qs
from typing import Optional, Iterator, Mapping, Iterable
from logging import getLogger

import requests

from quarchive.version import get_version
from quarchive.value_objects import (
    URL,
    Discussion,
    DiscussionSource,
)

REDDIT_USER_AGENT = f"linux:com.quarchive:{get_version()} (by /u/calp)"

log = getLogger(__name__)

ALGOLIA_BASE_URL = URL.from_string("https://hn.algolia.com/api/v1/search")


class RedditTokenClient:
    ACCESS_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    MAX_DEVICE_ID_LENGTH = 30

    def __init__(
        self, http_client: requests.Session, client_id: str, client_secret: str
    ):
        self.http_client = http_client
        self.device_id = self.get_device_id()
        self.expiry = datetime(1970, 1, 1)
        self.client_id = client_id
        self.client_secret = client_secret

    def get_device_id(self) -> str:
        """The Reddit API wants a unique device id that stays constant over
        time.  This hashes the mac address to provide such an id.

        """
        mac = getnode().to_bytes(6, byteorder="big")
        device_id = blake2b(mac, digest_size=self.MAX_DEVICE_ID_LENGTH // 2).hexdigest()
        log.info(
            "using reddit device id '%s' based on mac address '%s'",
            device_id,
            mac.hex(),
        )
        return device_id

    def fetch_token(self):
        """Fetch a new token from the api"""
        log.info("fetching a new reddit access token")
        response = self.http_client.post(
            url=self.ACCESS_TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "https://oauth.reddit.com/grants/installed_client",
                "device_id": self.get_device_id(),
                "scope": "read",
            },
            # FIXME: These fields should be set globally somehow
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=30,
        )
        log.debug(
            "got %d response from reddit access token api: %s",
            response.status_code,
            response.content,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.error(
                "got bad response %d from reddit access token api",
                response.status_code,
                response.content,
            )
            raise
        doc = response.json()
        self._token = doc["access_token"]
        self.expiry = datetime.utcnow() + timedelta(seconds=doc["expires_in"])
        # Expire it 60 seconds early to reduce the chances that we're using an
        # out of date token towards the end of the time period
        self.expiry -= timedelta(seconds=60)
        log.info("got a new reddit auth token, will expire at: %s", self.expiry)

    def get_token(self) -> str:
        if datetime.utcnow() > self.expiry:
            log.info("reddit access token unset or expired")
            self.fetch_token()
        return self._token


class RedditDiscussionClient:
    API_SEARCH_URL = "https://api.reddit.com/search"

    def __init__(
        self, http_client: requests.Session, client_id: str, client_secret: str
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_client = RedditTokenClient(http_client, client_id, client_secret)
        self.http_client = http_client

    def _discussion_from_child_data(self, child_data: Mapping) -> Discussion:
        return Discussion(
            external_id=child_data["id"],
            source=DiscussionSource.REDDIT,
            url=URL.from_string(child_data["url"]),
            comment_count=child_data["num_comments"],
            created_at=datetime.utcfromtimestamp(child_data["created_utc"]),
            title=f'{child_data["subreddit_name_prefixed"]}: {child_data["title"]}',
        )

    def discussions_for_url(self, url: URL) -> Iterable[Discussion]:
        # FIXME: Should step across pages here
        token = self.token_client.get_token()
        log.info("getting reddit discussions for %s", url)
        response = self.http_client.get(
            self.API_SEARCH_URL,
            auth=("bearer", token),
            params={
                "q": f"url:{url.to_string()}",
                "include_facts": "false",
                "limit": 100,
                "sort": "comments",
                "type": "link",
                "sr_detail": "false",
            },
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=30,
        )
        log.debug(
            "got %d response from reddit search api: %s",
            response.status_code,
            response.content,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.error(
                "got bad response %d from reddit search api",
                response.status_code,
                response.content,
            )
            raise
        doc = response.json()
        for child in doc["data"]["children"]:
            kind = child["kind"]
            if kind != "t3":
                log.warning(
                    "found non-link (kind: '%s') in response for url search, probably a bug",
                    kind,
                )
                continue
            else:
                yield self._discussion_from_child_data(child["data"])


def get_hn_api_url(original_url: URL) -> URL:
    quoted = quote_plus(original_url.to_string())
    relative = f"?query={quoted}&restrictSearchableAttributes=url&hitsPerPage=1000"
    return ALGOLIA_BASE_URL.follow(relative)


def extract_hn_discussions(response_body: Mapping) -> Iterator[Discussion]:
    log.debug("hn search api returned: %s", response_body)
    for hit in response_body["hits"]:
        yield Discussion(
            comment_count=hit.get("num_comments", 0),
            created_at=datetime.utcfromtimestamp(hit["created_at_i"]),
            external_id=hit["objectID"],
            title=hit.get("title", ""),
            url=URL.from_string(hit["url"], coerce_canonicalisation=True),
            source=DiscussionSource.HN,
        )


def hn_turn_page(url: URL, response_body: Mapping) -> Optional[URL]:
    final_page = response_body["nbPages"] - 1
    current_page = response_body["page"]
    if current_page < final_page:
        q_dict = parse_qs(url.query)
        q_dict["page"] = current_page + 1
        new_url = url.follow("?" + urlencode(q_dict, doseq=True))
        return new_url
    return None


class HNAlgoliaClient:
    def __init__(self, http_client: requests.Session):
        self.http_client = http_client

    def discussions_for_url(self, url: URL) -> Iterable[Discussion]:
        log.info("getting HN discussions for %s", url)
        api_url: Optional[URL] = get_hn_api_url(url)
        while api_url is not None:
            response = self.http_client.get(api_url.to_string())
            response.raise_for_status()
            document = response.json()
            yield from extract_hn_discussions(document)
            api_url = hn_turn_page(api_url, document)
