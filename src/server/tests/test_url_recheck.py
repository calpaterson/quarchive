from uuid import NAMESPACE_URL as UUID_URL_NAMESPACE, UUID, uuid5

import pytest
from click.testing import CliRunner

import quarchive as sut
from quarchive.data.functions import delete_bookmark, delete_url

from .conftest import make_bookmark


@pytest.fixture()
def bad_scheme_bookmark(session, cache, test_user):
    url_uuid = uuid5(UUID_URL_NAMESPACE, "about:blank")
    bad_scheme_url = sut.URL(
        url_uuid=url_uuid,
        scheme="about",
        netloc="",
        path="blank",
        query="",
        fragment="",
    )

    bookmark = make_bookmark(url=bad_scheme_url, tag_triples=frozenset())
    bookmark_uuid = sut.set_bookmark(session, cache, test_user.user_uuid, bookmark)
    session.commit()

    yield
    # teardown is required to avoid leaving a dirty db around
    delete_bookmark(session, cache, test_user.user_uuid, bookmark_uuid)
    delete_url(session, url_uuid)
    session.commit()


@pytest.fixture()
def bad_uuid_bookmark(session, cache, test_user):
    url_uuid = UUID("f" * 32)
    bad_uuid_url = sut.URL(
        url_uuid=url_uuid,
        scheme="http",
        netloc="example.com",
        path="/bad-uuid",
        query="",
        fragment="",
    )
    bookmark = make_bookmark(url=bad_uuid_url, tag_triples=frozenset())
    bookmark_uuid = sut.set_bookmark(session, cache, test_user.user_uuid, bookmark)
    session.commit()

    yield
    # teardown is required to avoid leaving a dirty db around
    delete_bookmark(session, cache, test_user.user_uuid, bookmark_uuid)
    delete_url(session, url_uuid)
    session.commit()


@pytest.fixture()
def bad_canonicalisation_bookmark(session, cache, test_user):
    # Needs a trailing slash
    url_uuid = uuid5(UUID_URL_NAMESPACE, "http://example.com")
    bad_uuid_url = sut.URL(
        url_uuid=url_uuid,
        scheme="http",
        netloc="example.com",
        path="",
        query="",
        fragment="",
    )
    bookmark = make_bookmark(url=bad_uuid_url, tag_triples=frozenset())
    bookmark_uuid = sut.set_bookmark(session, cache, test_user.user_uuid, bookmark)
    session.commit()

    yield
    # teardown is required to avoid leaving a dirty db around
    delete_bookmark(session, cache, test_user.user_uuid, bookmark_uuid)
    delete_url(session, url_uuid)
    session.commit()


def test_url_recheck_with_all_valid(session, cache, test_user):
    runner = CliRunner()

    bookmark = make_bookmark()
    sut.set_bookmark(session, cache, test_user.user_uuid, bookmark)
    session.commit()

    result = runner.invoke(sut.url_recheck)
    assert result.exit_code == 0


def test_url_recheck_with_invalid_scheme(bad_scheme_bookmark):
    runner = CliRunner()
    result = runner.invoke(sut.url_recheck)
    assert result.exit_code == 1


def test_url_recheck_with_bad_uuid(bad_uuid_bookmark):
    runner = CliRunner()
    result = runner.invoke(sut.url_recheck)
    assert result.exit_code == 1


def test_url_recheck_with_bad_canonicalisation(bad_canonicalisation_bookmark):
    runner = CliRunner()
    result = runner.invoke(sut.url_recheck)
    assert result.exit_code == 1
