from os import environ, path
from typing import Mapping, Any
from datetime import datetime, timezone
import logging
from dataclasses import dataclass
from unittest import mock
import secrets
import random
import contextlib
import string

import flask
import moto
from passlib.context import CryptContext

import quarchive as sut
from quarchive import value_objects
from quarchive.data import models as sut_models

import pytest


@pytest.fixture(scope="session", autouse=True)
def reduce_boto_logging():
    # AWS provided libraries have extremely verbose debug logs
    boto_loggers = ["boto3", "botocore", "s3transfer"]
    for boto_logger in boto_loggers:
        logging.getLogger(boto_logger).setLevel(logging.INFO)


@pytest.fixture(scope="session")
def config():
    with mock.patch.dict(
        environ,
        {
            "QM_SQL_URL": environ["QM_SQL_URL_TEST"],
            "QM_SECRET_KEY": "secret_key",
            "QM_RESPONSE_BODY_BUCKET_NAME": "test_body_bucket",
            "QM_AWS_SECRET_ACCESS_KEY": "123",
            "QM_AWS_ACCESS_KEY": "abc",
            "QM_AWS_REGION_NAME": "moon",
            "QM_AWS_S3_ENDPOINT_URL": "UNSET",
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
    sut.get_s3.cache_clear()
    sut.get_response_body_bucket.cache_clear()

    with moto.mock_s3():
        s3_resource = sut.get_s3()
        s3_resource.create_bucket(
            Bucket=environ["QM_RESPONSE_BODY_BUCKET_NAME"],
            CreateBucketConfiguration={"LocationConstraint": "moon",},
        )
        yield s3_resource


@pytest.fixture(scope="function")
def eager_celery():
    sut.celery_app.conf.update(task_always_eager=True)
    yield
    sut.celery_app.conf.update(task_always_eager=False)


@pytest.fixture()
def test_user(session, client):
    username = "testuser-" + random_string()
    username, password = (username, "password1")
    return register_user(session, client, username, password, username + "@example.com")


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
    with contextlib.ExitStack() as stack:
        mock_cd = stack.enter_context(mock.patch.object(secrets, "compare_digest"))
        mock_tb = stack.enter_context(mock.patch.object(secrets, "token_bytes"))
        mock_cd.side_effect = lambda a, b: a == b
        mock_tb.side_effect = lambda n: bytes(random.randint(0, 255) for _ in range(n))
        yield


# Everything below this line should be moved to .utils


test_data_path = path.join(path.dirname(__file__), "test-data")


@dataclass
class User(value_objects.User):
    """Expanded test subclass that holds some extra data"""

    password: str
    api_key: bytes


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


def sign_in_as(client, user: User):
    with client.session_transaction() as sess:
        sess["user_uuid"] = user.user_uuid


def sign_out(client):
    with client.session_transaction() as sess:
        sess.clear()


def register_user(
    session, client, username, password="password", email=None, timezone=None
) -> User:
    response = client.post(
        "/register",
        data={"username": username, "password": password, "email": email or ""},
    )
    assert response.status_code == 303
    # Registration gives us an automatic log in, which is unwanted here
    with client.session_transaction() as flask_sesh:
        flask_sesh.clear()

    if timezone is not None:
        # A specific timezone is desired, set it
        client.post(
            flask.url_for("quarchive.user_page", username=username),
            data={"timezone": timezone},
        )

    api_key, user_uuid, user_timezone = (
        session.query(
            sut_models.APIKey.api_key,
            sut_models.SQLUser.user_uuid,
            sut_models.SQLUser.timezone,
        )
        .join(sut.SQLUser)
        .filter(sut.SQLUser.username == username)
        .first()
    )

    return User(
        username=username,
        password=password,
        api_key=api_key,
        user_uuid=user_uuid,
        email=email,
        timezone=user_timezone,
    )


def random_string() -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(32))
