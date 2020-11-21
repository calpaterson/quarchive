import logging
from typing import Tuple, IO
import random
import hashlib

from tempfile import TemporaryFile
from PIL import Image
import responses
from missive import TestAdapter


from quarchive import file_storage
from quarchive.value_objects import URL
from quarchive.data.models import Icon, DomainIcon, URLIcon
from quarchive.data.functions import upsert_url
from quarchive.messaging.receipt import PickleMessage
from quarchive.messaging.message_lib import HelloEvent, NewIconFound

from .conftest import random_string


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


def test_new_icon_found_for_url_icon(
    session, requests_mock, bg_client: TestAdapter[PickleMessage], mock_s3
):
    url = URL.from_string(f"http://{random_string()}.example.com/")
    icon_url = url.follow("/favicon.ico")
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
