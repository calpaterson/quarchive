from os import environ, path
from logging import getLogger
from typing import Mapping, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from unittest import mock
import secrets
import random
import contextlib
import string

import requests
import missive
import responses
import flask
import moto
from passlib.context import CryptContext
import pytz

import quarchive as sut
from quarchive import (
    value_objects,
    bg_worker as bg_worker_module,
    file_storage,
    crawler,
)
from quarchive.web.web_blueprint import set_current_user_for_session
from quarchive import logging as q_logging
from quarchive.data import models as sut_models
from quarchive.messaging import publication, receipt

import pytest

log = getLogger(__name__)


# This is necessary to work around moto's effect on responses
# https://github.com/spulec/moto/issues/3264
responses._default_mock.passthru_prefixes = tuple()
responses.add_passthru = responses._default_mock.add_passthru


@pytest.fixture(scope="session", autouse=True)
def reduce_noisy_logging():
    q_logging.turn_down_noisy_loggers()


@pytest.fixture(scope="session", autouse=True)
def lower_requests_timeout():
    with mock.patch.object(crawler, "REQUESTS_TIMEOUT", 0.1):
        yield


@pytest.fixture(scope="session", autouse=True)
def config():
    with mock.patch.dict(
        environ,
        {
            "QM_SQL_URL": environ["QM_SQL_URL_TEST"],
            "QM_SECRET_KEY": "secret_key",
            "QM_RESPONSE_BODY_BUCKET_NAME": "test_body_bucket",
            "QM_ICON_BUCKET_NAME": "test_icon_bucket",
            "QM_AWS_SECRET_ACCESS_KEY": "123",
            "QM_AWS_ACCESS_KEY": "abc",
            "QM_AWS_REGION_NAME": "moon",
            "QM_REDDIT_CLIENT_ID": "client",
            "QM_REDDIT_CLIENT_SECRET": "reddit-secret",
            "QM_AWS_S3_ENDPOINT_URL": "UNSET",
            "QM_RABBITMQ_URL": "amqp:///test",
            "QM_RABBITMQ_BG_WORKER_TOPIC": "bg_q",
            "QM_MISSIVE_SQLITE_DLQ_CONNSTRING": "file:quarchive_test?mode=memory&cache=shared",
        },
    ):
        yield


@pytest.fixture(scope="function")
def session(app, config):
    return sut.db.session


@pytest.fixture(scope="session")
def app(config):
    a = sut.init_app()
    a.config["TESTING"] = True
    # Speeds things up considerably when testing
    a.config["CRYPT_CONTEXT"] = CryptContext(["plaintext"])
    return a


@pytest.fixture(scope="function")
def mock_s3():
    # Clear out old handles
    file_storage.get_s3.cache_clear()
    file_storage.get_response_body_bucket.cache_clear()

    with moto.mock_s3():
        s3_resource = file_storage.get_s3()
        s3_resource.create_bucket(
            Bucket=environ["QM_RESPONSE_BODY_BUCKET_NAME"],
            CreateBucketConfiguration={"LocationConstraint": "moon",},
        )
        s3_resource.create_bucket(
            Bucket=environ["QM_ICON_BUCKET_NAME"],
            CreateBucketConfiguration={"LocationConstraint": "moon",},
        )
        yield s3_resource


@pytest.fixture()
def test_user(session, app) -> "ExtendedUser":
    username = "testuser-" + random_string()
    username, password = (username, "password1")
    return register_user(session, app, username, password, username + "@example.com")


@pytest.fixture()
def signed_in_client(client, test_user):
    sign_in_as(client, test_user)
    yield client


@pytest.fixture(scope="session", autouse=True)
def patch_out_secrets_module():
    """Patch out some stuff from the secret library, both to speed things up as
    much as possible but also to avoid using an real crypto randomness on my
    machine.

    """

    def fake_compare_digest(a, b):
        # We need to check types first (because the real implemention does).
        # It wants with str or bytes but we will narrow that to bytes
        if (not isinstance(a, bytes)) or (not isinstance(b, bytes)):
            raise RuntimeError("want bytes")
        return a == b

    with contextlib.ExitStack() as stack:
        mock_cd = stack.enter_context(mock.patch.object(secrets, "compare_digest"))
        mock_tb = stack.enter_context(mock.patch.object(secrets, "token_bytes"))
        mock_cd.side_effect = fake_compare_digest
        mock_tb.side_effect = lambda n: bytes(random.randint(0, 255) for _ in range(n))
        yield


@pytest.fixture(scope="session")
def bg_client():
    with bg_worker_module.proc.test_client() as tc:
        yield tc


@pytest.fixture
def bg_worker(bg_client: missive.TestAdapter):
    """Replace the kombu publish method with a direct call into missive
    mechanisms - make bg_worker run the event right now.

    """

    def fake_publish(as_bytes: bytes, routing_key: str) -> None:
        message_obj = receipt.PickleMessage(as_bytes)
        log.info("sending %s directly to test client", message_obj)
        bg_client.send(message_obj)

    producer = publication.get_producer()
    with mock.patch.object(producer, "publish") as mock_publish_message:
        mock_publish_message.side_effect = fake_publish
        yield bg_client


@pytest.fixture(scope="session", autouse=True)
def requests_mock_session():
    """Patch out requests across all tests.  This ensures that anything that
    does network IO with requests will raise a ConnectionError immeadiately
    rather than actually making a request to some third party server.

    """
    requests_mock = responses.RequestsMock()
    with requests_mock:
        yield requests_mock


@pytest.fixture(scope="function")
def requests_mock(requests_mock_session):
    """Returns the (cleared) requests mock"""
    # NOTE: if you are looking at this and wondering why your requests aren't
    # being matched: this needs to run AFTER mock_s3
    requests_mock_session.reset()
    requests_mock_session.start()
    yield requests_mock_session


@pytest.fixture(scope="function")
def http_client():
    return requests.Session()


# Everything below this line should be moved to .utils


test_data_path = path.join(path.dirname(__file__), "test-data")


@dataclass
class ExtendedUser(value_objects.User):
    """Expanded test subclass that holds some extra data"""

    password: str
    api_key: bytes

    def as_user(self) -> value_objects.User:
        return value_objects.User(
            user_uuid=self.user_uuid,
            username=self.username,
            email=self.email,
            timezone=self.timezone,
            registered=self.registered,
        )


def make_bookmark(**kwargs) -> sut.Bookmark:
    epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    bookmark_defaults: Mapping[str, Any] = {
        "url": sut.URL.from_string("http://example.com/" + random_string()),
        "title": "Example",
        "created": epoch_start,
        "updated": epoch_start,
        "description": "An example bookmark",
        "unread": False,
        "deleted": False,
        "tag_triples": frozenset([("test", epoch_start, False)]),
    }
    return sut.Bookmark(**{**bookmark_defaults, **kwargs})


def sign_in_as(client, user: ExtendedUser):
    with client.session_transaction() as sesh:
        set_current_user_for_session(user.as_user(), user.api_key, session=sesh)


def sign_out(client):
    with client.session_transaction() as sess:
        sess.clear()
    # FIXME: This is a hack because flask now has g scoped to the app context
    # and not the request context
    del flask.g._quarchive_user


def register_user(
    session,
    app: flask.Flask,
    username: str,
    password: str = "password",
    email: Optional[str] = None,
    timezone: Optional[str] = None,
) -> "ExtendedUser":
    """Register a new user"""
    # Create a whole new application context because registration by it's
    # nature sets a bunch of state that callers don't want (in particular:
    # flask.g.user and things on flask.session)
    with app.app_context():
        client = app.test_client()
        response = client.post(
            "/register",
            data={"username": username, "password": password, "email": email or ""},
        )
        assert response.status_code == 303

        if timezone is not None:
            # A specific timezone is desired, set it
            client.post(
                flask.url_for("quarchive.user_page", username=username),
                data={"timezone": timezone},
            )

    api_key, user_uuid, user_timezone, registered = (
        session.query(
            sut_models.APIKey.api_key,
            sut_models.SQLUser.user_uuid,
            sut_models.SQLUser.timezone,
            sut_models.SQLUser.registered,
        )
        .join(sut.SQLUser)
        .filter(sut.SQLUser.username == username)
        .first()
    )

    return ExtendedUser(
        username=username,
        password=password,
        api_key=api_key,
        user_uuid=user_uuid,
        email=email,
        timezone=pytz.timezone(user_timezone),
        registered=registered,
    )


def random_string() -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(32))


def random_bytes(n) -> bytes:
    return bytearray(random.getrandbits(8) for _ in range(n))


def random_numeric_id() -> int:
    """Returns a random id within the pg BIGINTEGER range"""
    return random.getrandbits(63)


def random_url() -> value_objects.URL:
    return value_objects.URL.from_string(
        f"http://{random_string()}.example.com/{random_string()}.html"
    )
