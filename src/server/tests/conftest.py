from os import environ, path
from typing import MutableMapping, Any
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


@pytest.fixture(scope="session")
def sql_db():
    with mock.patch.dict(environ, {"QM_SQL_URL": environ["QM_SQL_URL_TEST"]}):
        yield


@pytest.fixture(autouse=True, scope="function")
def ensure_clean_tables(app, sql_db):
    for table in reversed(sut.Base.metadata.sorted_tables):
        sut.db.session.execute("delete from %s;" % table.name)
    sut.db.session.commit()


@pytest.fixture()
def app(sql_db):
    a = sut.init_app(environ["QM_SQL_URL"], "test_password", "secret_key")
    a.config["TESTING"] = True
    return a


def make_bookmark(**kwargs):
    values: MutableMapping[str, Any] = {
        "url": "http://example.com",
        "title": "Example",
        "created": datetime(1970, 1, 1, tzinfo=timezone.utc),
        "updated": datetime(1970, 1, 1, tzinfo=timezone.utc),
        "description": "An example bookmark",
        "unread": False,
        "deleted": False,
    }
    values.update(kwargs)
    return sut.Bookmark(**values)


@pytest.fixture()
def signed_in_client(client):
    with client.session_transaction() as sess:
        sess["username"] = "calpaterson"
    yield client
