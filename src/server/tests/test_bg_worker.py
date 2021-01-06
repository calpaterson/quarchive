import logging
from typing import Tuple, IO, Mapping
from uuid import uuid4
from io import BytesIO
import random
import hashlib
from datetime import datetime, timezone

from tempfile import TemporaryFile
from PIL import Image
import responses
from missive import TestAdapter

from quarchive.discussions import get_hn_api_url
from quarchive import file_storage
from quarchive.value_objects import (
    URL,
    Request,
    CrawlRequest,
    BookmarkCrawlReason,
    HTTPVerb,
    DiscussionSource,
)
from quarchive.data.models import (
    Icon,
    DomainIcon,
    URLIcon,
    SQLAUrl,
    FullText,
    IconSource,
    CrawlRequest as SQLACrawlRequest,
    CrawlResponse as SQLACrawlResponse,
    SQLDiscussion,
)
from quarchive.data.functions import upsert_url
from quarchive.messaging.receipt import PickleMessage
from quarchive.messaging.message_lib import (
    BookmarkCreated,
    CrawlRequested,
    FetchDiscussionsCommand,
    HelloEvent,
    IndexRequested,
    NewIconFound,
)

from .conftest import random_string, random_url, random_numeric_id
from .test_indexing import make_crawl_with_response
from .utils import make_algolia_hit, make_algolia_resp


def random_image(size: Tuple[int, int] = (32, 32)):
    image = Image.new("RGBA", size)
    image.putdata(
        [
            (random.getrandbits(8), random.getrandbits(8), random.getrandbits(8), 255,)
            for _ in range(len(image.getdata()))
        ]
    )
    return image


def random_image_fileobj(size: Tuple[int, int] = (32, 32), format="ico") -> IO[bytes]:
    image_buff = TemporaryFile()
    random_image().save(image_buff, format="ico")
    image_buff.seek(0)
    return image_buff


def test_hello_event(bg_client: TestAdapter[PickleMessage], caplog):
    caplog.set_level(logging.INFO, logger="quarchive.bg_worker")
    event = HelloEvent("greetings earthling")
    bg_client.send(PickleMessage.from_obj(event))
    logs = [r.getMessage() for r in caplog.records]
    expected = "greetings earthling"
    # FIXME: this is pretty ropey and fragile
    assert expected in logs[-1]


def test_bookmark_created(session, bg_worker, mock_s3, requests_mock, test_user):
    url = URL.from_string("http://example.com/" + random_string())
    upsert_url(session, url)
    session.commit()

    requests_mock.add(
        responses.GET, url=url.to_string(), body="Hello!", status=200, stream=True,
    )

    bg_worker.send(
        PickleMessage.from_obj(
            BookmarkCreated(user_uuid=test_user.user_uuid, url_uuid=url.url_uuid)
        )
    )

    response_exists = session.query(
        session.query(SQLACrawlResponse)
        .join(SQLACrawlRequest)
        .join(SQLAUrl)
        .filter(SQLAUrl.url_uuid == url.url_uuid)
        .exists()
    ).scalar()
    assert response_exists


def test_crawl_requested(session, bg_worker, mock_s3, requests_mock):
    url = URL.from_string("http://example.com/" + random_string())
    requests_mock.add(
        responses.GET, url=url.to_string(), body="Hello!", status=200, stream=True,
    )

    bg_worker.send(
        PickleMessage.from_obj(
            CrawlRequested(
                CrawlRequest(
                    request=Request(HTTPVerb.GET, url=url),
                    reason=BookmarkCrawlReason(),
                )
            )
        )
    )
    response_exists = session.query(
        session.query(SQLACrawlResponse)
        .join(SQLACrawlRequest)
        .join(SQLAUrl)
        .filter(SQLAUrl.url_uuid == url.url_uuid)
        .exists()
    ).scalar()
    assert response_exists


def test_index_requested_new_page_and_new_page_icon(
    session, bg_worker, mock_s3, requests_mock
):
    """Test that new pages are indexed properly and their icon is downloaded."""
    icon_url = URL.from_string(f"http://{random_string()}.example.com/favicon.png")
    html = f"""
    <html>
    <head>
    <link rel="icon" type="image/png" href="{icon_url.to_string()}">
    </head>
    </html>
    """

    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(
        session, response_body=BytesIO(html.encode("utf-8"))
    )
    session.commit()

    image_buff = random_image_fileobj()
    hash_bytes = hashlib.blake2b(image_buff.read()).digest()
    image_buff.seek(0)
    requests_mock.add(
        responses.GET,
        url=icon_url.to_string(),
        body=image_buff.read(),
        status=200,
        stream=True,
    )

    bg_worker.send(PickleMessage.from_obj(IndexRequested(crawl_resp.crawl_uuid)))

    fulltext_exists = session.query(
        session.query(FullText)
        .filter(FullText.crawl_uuid == crawl_req.crawl_uuid)
        .exists()
    ).scalar()

    icon_exists = session.query(
        session.query(Icon).filter(Icon.source_blake2b_hash == hash_bytes).exists()
    ).scalar()

    assert fulltext_exists, "crawl not indexed!"
    assert icon_exists, "icon not crawled!"


def test_index_requested_new_page_and_known_page_icon_url(
    session, bg_worker, mock_s3, requests_mock
):
    """Test that when a page uses an icon url we already have in the index, we reuse it."""
    icon_url = URL.from_string(f"http://{random_string()}.example.com/favicon.png")
    icon_uuid = uuid4()
    html = f"""
    <html>
    <head>
    <link rel="icon" type="image/png" href="{icon_url.to_string()}">
    </head>
    </html>
    """

    sqla_url, crawl_req, crawl_resp = make_crawl_with_response(
        session, response_body=BytesIO(html.encode("utf-8"))
    )
    image_buff = random_image_fileobj()
    hash_bytes = hashlib.blake2b(image_buff.read()).digest()
    upsert_url(session, icon_url)
    session.add(Icon(icon_uuid=icon_uuid, source_blake2b_hash=hash_bytes))
    session.add(IconSource(icon_uuid=icon_uuid, url_uuid=icon_url.url_uuid))
    session.commit()

    bg_worker.send(PickleMessage.from_obj(IndexRequested(crawl_resp.crawl_uuid)))

    url_icon = (
        session.query(URLIcon).filter(URLIcon.url_uuid == sqla_url.url_uuid).one()
    )
    assert url_icon.url_uuid == sqla_url.url_uuid
    assert url_icon.icon_uuid == icon_uuid


def test_new_icon_found_domain(
    session, requests_mock, bg_client: TestAdapter[PickleMessage], mock_s3
):
    icon_url = URL.from_string(f"http://{random_string()}.example.com/favicon.ico")
    image_buff = random_image_fileobj()
    hash_bytes = hashlib.blake2b(image_buff.read()).digest()
    image_buff.seek(0)
    requests_mock.add(
        responses.GET,
        url=icon_url.to_string(),
        body=image_buff.read(),
        status=200,
        stream=True,
    )
    requests_mock.start()

    upsert_url(session, icon_url)
    session.commit()

    event = NewIconFound(icon_url_uuid=icon_url.url_uuid)
    bg_client.send(PickleMessage.from_obj(event))

    icon, domain_icon = (
        session.query(Icon, DomainIcon)
        .join(DomainIcon)
        .filter(
            DomainIcon.scheme == icon_url.scheme, DomainIcon.netloc == icon_url.netloc
        )
        .first()
    )
    assert icon.source_blake2b_hash == hash_bytes

    assert domain_icon.scheme == icon_url.scheme
    assert domain_icon.netloc == icon_url.netloc

    icon_bucket = file_storage.get_icon_bucket()
    (s3_obj,) = list(icon_bucket.objects.filter(Prefix=f"{icon.icon_uuid}.png"))
    assert s3_obj.key == f"{icon.icon_uuid}.png"
    response = s3_obj.get()
    assert response["ResponseMetadata"]["HTTPHeaders"]["content-type"] == "image/png"


def test_new_icon_found_domain_but_is_already_indexed(
    session, requests_mock, bg_client: TestAdapter[PickleMessage], mock_s3
):
    icon_url = URL.from_string(f"http://{random_string()}.example.com/favicon.ico")
    image_buff = random_image_fileobj()
    hash_bytes = hashlib.blake2b(image_buff.read()).digest()
    image_buff.seek(0)
    requests_mock.add(
        responses.GET,
        url=icon_url.to_string(),
        body=image_buff.read(),
        status=200,
        stream=True,
    )
    requests_mock.start()

    upsert_url(session, icon_url)
    session.commit()

    event = NewIconFound(icon_url_uuid=icon_url.url_uuid)
    bg_client.send(PickleMessage.from_obj(event))
    bg_client.send(PickleMessage.from_obj(event))

    icon, domain_icon = (
        session.query(Icon, DomainIcon)
        .join(DomainIcon)
        .filter(
            DomainIcon.scheme == icon_url.scheme, DomainIcon.netloc == icon_url.netloc
        )
        .one()
    )
    assert icon.source_blake2b_hash == hash_bytes

    assert domain_icon.scheme == icon_url.scheme
    assert domain_icon.netloc == icon_url.netloc


def test_new_icon_found_for_page_icon(
    session, requests_mock, bg_client: TestAdapter[PickleMessage], mock_s3
):
    """Test that when a new page icon is found (that doesn't match any existing
    icons) that it is retrieved, indexed and stored.

    """
    url = URL.from_string(f"http://{random_string()}.example.com/")
    icon_url = url.follow("/favicon.png")
    image_buff = random_image_fileobj()
    hash_bytes = hashlib.blake2b(image_buff.read()).digest()
    image_buff.seek(0)
    requests_mock.add(
        responses.GET,
        url=icon_url.to_string(),
        body=image_buff.read(),
        status=200,
        stream=True,
    )
    requests_mock.start()

    upsert_url(session, url)
    upsert_url(session, icon_url)
    session.commit()

    event = NewIconFound(icon_url_uuid=icon_url.url_uuid, page_url_uuid=url.url_uuid)
    bg_client.send(PickleMessage.from_obj(event))

    icon, url_icon = (
        session.query(Icon, URLIcon)
        .join(URLIcon)
        .filter(URLIcon.url_uuid == url.url_uuid)
        .first()
    )
    assert icon.source_blake2b_hash == hash_bytes

    assert url_icon.url_uuid == url.url_uuid

    icon_bucket = file_storage.get_icon_bucket()
    (s3_obj,) = list(icon_bucket.objects.filter(Prefix=f"{icon.icon_uuid}.png"))
    assert s3_obj.key == f"{icon.icon_uuid}.png"
    response = s3_obj.get()
    assert response["ResponseMetadata"]["HTTPHeaders"]["content-type"] == "image/png"


def test_new_icon_found_for_page_url_duplicated_by_content(
    session, requests_mock, bg_client: TestAdapter[PickleMessage], mock_s3
):
    """Test that when a new page icon is found that is the same icon by hash as
    an existing icon, that it is recorded."""
    page_url_1 = URL.from_string(f"http://{random_string()}.example.com/index.html")
    page_url_2 = page_url_1.follow("/otherindex.html")

    icon_url_1 = page_url_1.follow("favicon1.png")
    icon_url_2 = page_url_2.follow("favicon2.png")

    image_buff = random_image_fileobj()
    hash_bytes = hashlib.blake2b(image_buff.read()).digest()
    image_buff.seek(0)
    requests_mock.add(
        responses.GET,
        url=icon_url_1.to_string(),
        body=image_buff.read(),
        status=200,
        stream=True,
    )
    image_buff.seek(0)
    requests_mock.add(
        responses.GET,
        url=icon_url_2.to_string(),
        body=image_buff.read(),
        status=200,
        stream=True,
    )
    requests_mock.start()

    upsert_url(session, page_url_1)
    upsert_url(session, page_url_2)
    upsert_url(session, icon_url_1)
    upsert_url(session, icon_url_2)
    session.commit()

    event = NewIconFound(
        icon_url_uuid=icon_url_1.url_uuid, page_url_uuid=page_url_1.url_uuid
    )
    bg_client.send(PickleMessage.from_obj(event))

    event = NewIconFound(
        icon_url_uuid=icon_url_2.url_uuid, page_url_uuid=page_url_2.url_uuid
    )
    bg_client.send(PickleMessage.from_obj(event))

    url_icon_obj_1, url_icon_obj_2 = (
        session.query(URLIcon)
        .join(SQLAUrl, URLIcon.url_uuid == SQLAUrl.url_uuid)
        .filter(SQLAUrl.netloc == page_url_1.netloc)
        .order_by(SQLAUrl.path)
        .all()
    )

    assert url_icon_obj_1.icon == url_icon_obj_2.icon
    assert url_icon_obj_1.icon.source_blake2b_hash == hash_bytes


def test_new_icon_found_for_page_url_duplicated_by_url(
    session, bg_client: TestAdapter[PickleMessage], mock_s3, requests_mock
):
    """Test that when a new page icon is found that is the same icon by hash as
    an existing icon, that it is recorded."""
    page_url_1 = URL.from_string(f"http://{random_string()}.example.com/index.html")
    page_url_2 = page_url_1.follow("/otherindex.html")

    icon_url = page_url_1.follow("favicon1.png")

    hash_bytes = bytes(random.getrandbits(8) for _ in range(64))

    upsert_url(session, page_url_1)
    upsert_url(session, page_url_2)
    upsert_url(session, icon_url)
    icon_uuid = uuid4()
    session.add(Icon(icon_uuid=icon_uuid, source_blake2b_hash=hash_bytes))
    session.add(IconSource(icon_uuid=icon_uuid, url_uuid=icon_url.url_uuid))
    session.add(URLIcon(url_uuid=page_url_1.url_uuid, icon_uuid=icon_uuid))
    session.commit()

    event = NewIconFound(
        icon_url_uuid=icon_url.url_uuid, page_url_uuid=page_url_2.url_uuid
    )
    bg_client.send(PickleMessage.from_obj(event))

    url_icon_obj_1, url_icon_obj_2 = (
        session.query(URLIcon)
        .join(SQLAUrl, URLIcon.url_uuid == SQLAUrl.url_uuid)
        .filter(SQLAUrl.netloc == page_url_1.netloc)
        .order_by(SQLAUrl.path)
        .all()
    )

    assert url_icon_obj_1.icon == url_icon_obj_2.icon
    assert url_icon_obj_1.icon.source_blake2b_hash == hash_bytes


def test_crawl_hn_api(
    session, bg_client: TestAdapter[PickleMessage], mock_s3, requests_mock
):
    url = random_url()
    upsert_url(session, url)
    session.commit()

    hn_id = random_numeric_id()

    api_url = get_hn_api_url(url)
    requests_mock.add(
        responses.GET,
        url=api_url.to_string(),
        json=make_algolia_resp(
            hits=[make_algolia_hit(objectID=hn_id, url=url.to_string())]
        ),
        status=200,
    )

    event = FetchDiscussionsCommand(url_uuid=url.url_uuid, source=DiscussionSource.HN)
    bg_client.send(PickleMessage.from_obj(event))

    discussion = (
        session.query(SQLDiscussion)
        .filter(SQLDiscussion.discussion_source_id == DiscussionSource.HN.value)
        .filter(SQLDiscussion.external_discussion_id == str(hn_id))
        .one()
    )
    assert discussion.external_discussion_id == str(hn_id)
    assert discussion.discussion_source_id == DiscussionSource.HN.value
    assert discussion.comment_count == 1
    assert discussion.url_uuid == url.url_uuid


def test_recrawl_of_hn_api(
    session, bg_client: TestAdapter[PickleMessage], mock_s3, requests_mock
):
    url = random_url()
    upsert_url(session, url)
    session.commit()

    hn_id = random_numeric_id()

    api_url = get_hn_api_url(url)
    requests_mock.add(
        responses.GET,
        url=api_url.to_string(),
        json=make_algolia_resp(
            hits=[make_algolia_hit(objectID=hn_id, url=url.to_string())]
        ),
        status=200,
    )

    event = FetchDiscussionsCommand(url_uuid=url.url_uuid, source=DiscussionSource.HN)
    bg_client.send(PickleMessage.from_obj(event))

    # And again, but with a different comment count
    requests_mock.remove(responses.GET, url=api_url.to_string())
    requests_mock.add(
        responses.GET,
        url=api_url.to_string(),
        json=make_algolia_resp(
            hits=[
                make_algolia_hit(
                    objectID=hn_id,
                    url=url.to_string(),
                    num_comments=5,
                    title="Other example",
                    created_at_i=int(datetime(2018, 1, 4).timestamp()),
                )
            ]
        ),
        status=200,
    )

    # and again
    bg_client.send(PickleMessage.from_obj(event))

    discussion = (
        session.query(SQLDiscussion)
        .filter(SQLDiscussion.discussion_source_id == DiscussionSource.HN.value)
        .filter(SQLDiscussion.external_discussion_id == str(hn_id))
        .one()
    )
    assert discussion.comment_count == 5
    assert discussion.url_uuid == url.url_uuid
    assert discussion.title == "Other example"
    assert discussion.created_at == datetime(2018, 1, 4, tzinfo=timezone.utc)


def test_multi_page_hn_api(
    session, bg_client: TestAdapter[PickleMessage], mock_s3, requests_mock
):
    url = random_url()
    upsert_url(session, url)
    session.commit()

    api_url1 = get_hn_api_url(url)
    api_url2 = URL.from_string(api_url1.to_string() + "&page=1")
    requests_mock.add(
        responses.GET,
        url=api_url1.to_string(),
        json=make_algolia_resp(
            nbPages=2, hitsPerPage=1, hits=[make_algolia_hit(url=url.to_string())]
        ),
        status=200,
    )
    requests_mock.add(
        responses.GET,
        url=api_url2.to_string(),
        json=make_algolia_resp(
            nbPages=2,
            page=1,
            hitsPerPage=1,
            hits=[make_algolia_hit(url=url.to_string())],
        ),
        status=200,
    )

    event = FetchDiscussionsCommand(url_uuid=url.url_uuid, source=DiscussionSource.HN)
    bg_client.send(PickleMessage.from_obj(event))

    discussion_count = (
        session.query(SQLDiscussion)
        .filter(SQLDiscussion.discussion_source_id == DiscussionSource.HN.value)
        .filter(SQLDiscussion.url_uuid == url.url_uuid)
        .count()
    )
    assert discussion_count == 2
