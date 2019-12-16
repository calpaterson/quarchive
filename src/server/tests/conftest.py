from os import environ
from typing import MutableMapping, Any
from datetime import datetime
from unittest import mock

import flask
from sqlalchemy.engine import create_engine

import quartermarker as sut

import pytest
import testing.postgresql


@pytest.fixture(scope="session")
def sql_db():
    if "QM_SQL_URL_TEST" not in environ:
        with testing.postgresql.Postgresql() as pg:
            with mock.patch.dict(environ, {"QM_SQL_URL": pg.url()}):
                sut.Base.metadata.create_all(bind=create_engine(pg.url()))
                yield
    else:
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
        "updated": datetime(1970, 1, 1),
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


working_cred_headers = {
    "X-QM-API-Username": "calpaterson",
    "X-QM-API-Key": "test_password",
}
