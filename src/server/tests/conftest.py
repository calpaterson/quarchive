from os import environ
from unittest import mock

import quartermarker as sut

import pytest
import testing.postgresql
from sqlalchemy.engine import create_engine


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
    a = sut.init_app(environ["QM_SQL_URL"])
    a.config["TESTING"] = True
    return a
