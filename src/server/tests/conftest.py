from os import environ, path
from typing import Mapping, Any
from datetime import datetime, timezone
from unittest import mock

import flask
from sqlalchemy.engine import create_engine

import quarchive as sut

import pytest


working_cred_headers = {
    "X-QM-API-Username": "calpaterson",
    "X-QM-API-Key": "test_password",
}


test_data_path = path.join(path.dirname(__file__), "test-data")


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
    return a


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


@pytest.fixture()
def signed_in_client(client):
    with client.session_transaction() as sess:
        sess["username"] = "calpaterson"
    yield client
