from os import environ, path
from typing import Mapping, Any
from datetime import datetime, timezone
import logging

import moto
from passlib.context import CryptContext

import quarchive as sut

import pytest


working_cred_headers: Mapping[str, str] = {
    "X-QM-API-Username": "calpaterson",
    "X-QM-API-Key": "test_password",
}


test_data_path = path.join(path.dirname(__file__), "test-data")


@pytest.fixture(scope="session", autouse=True)
def reduce_boto_logging():
    # AWS provided libraries have extremely verbose debug logs
    boto_loggers = ["boto3", "botocore", "s3transfer"]
    for boto_logger in boto_loggers:
        logging.getLogger(boto_logger).setLevel(logging.INFO)


@pytest.fixture(scope="function")
def config(monkeypatch):
    monkeypatch.setenv("QM_SQL_URL", environ["QM_SQL_URL_TEST"])
    monkeypatch.setenv("QM_PASSWORD", "test_password")
    monkeypatch.setenv("QM_SECRET_KEY", "secret_key")
    monkeypatch.setenv("QM_RESPONSE_BODY_BUCKET_NAME", "test_body_bucket")
    monkeypatch.setenv("QM_AWS_SECRET_ACCESS_KEY", "123")
    monkeypatch.setenv("QM_AWS_ACCESS_KEY", "abc")
    monkeypatch.setenv("QM_AWS_REGION_NAME", "moon")
    monkeypatch.setenv("QM_AWS_S3_ENDPOINT_URL", "UNSET")


@pytest.fixture(scope="function")
def session(app, config):
    for table in reversed(sut.Base.metadata.sorted_tables):
        sut.db.session.execute("delete from %s;" % table.name)
    sut.db.session.commit()
    return sut.db.session


@pytest.fixture()
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
        s3_resource.create_bucket(Bucket=environ["QM_RESPONSE_BODY_BUCKET_NAME"])
        yield s3_resource


@pytest.fixture(scope="function")
def eager_celery():
    sut.celery_app.conf.update(task_always_eager=True)
    yield
    sut.celery_app.conf.update(task_always_eager=False)


def make_bookmark(**kwargs):
    bookmark_defaults: Mapping[str, Any] = {
        "url": "http://example.com",
        "title": "Example",
        "created": datetime(1970, 1, 1, tzinfo=timezone.utc),
        "updated": datetime(1970, 1, 1, tzinfo=timezone.utc),
        "description": "An example bookmark",
        "unread": False,
        "deleted": False,
    }
    return sut.Bookmark(**{**bookmark_defaults, **kwargs})


def register_user(session, client, username, password):
    response = client.post(
        "/register",
        data={"username": username, "password": password, "email": "test@example.com",},
    )
    assert response.status_code == 303


@pytest.fixture()
def test_user(session, client):
    username, password = ("testuser", "password1")
    register_user(session, client, username, password)
    yield username, password


@pytest.fixture()
def signed_in_client(client):
    with client.session_transaction() as sess:
        sess["username"] = "calpaterson"
    yield client
