import logging
from typing import Tuple
import random

from tempfile import TemporaryFile
from PIL import Image
import responses
from missive import TestAdapter


from quarchive.value_objects import URL
from quarchive.data.models import (
    Icon,
    DomainIcon,
)
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
    random_prefix = random_string()
    icon_url = URL.from_string(f"http://{random_prefix}.example.com/favicon.ico")
    image_buff = TemporaryFile()
    random_image().save(image_buff, format="ico")
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
    assert icon is not None
    # FIXME: test that the icon is in s3
