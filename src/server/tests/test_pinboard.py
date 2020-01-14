from click.testing import CliRunner
from os import path, environ
from datetime import datetime, timezone
from unittest import mock

from quarchive import pinboard_import, db, get_bookmark_by_url, Bookmark

from freezegun import freeze_time
import pytest
from .conftest import test_data_path

runner = CliRunner()


@pytest.fixture(scope="session", autouse=True)
def environment_variables():
    # FIXME: need a proper solution to these config variable
    with mock.patch.dict(
        environ, {"QM_PASSWORD": "password", "QM_SECRET_KEY": "secret_key"}
    ):
        yield


@pytest.mark.pinboard_import
@freeze_time("2018-01-03")
def test_pinboard_bookmark(session):
    runner = CliRunner()
    json_path = path.join(test_data_path, "pinboard-bookmark.json")
    result = runner.invoke(pinboard_import, json_path, catch_exceptions=False)
    assert result.exit_code == 0

    expected_url = (
        "https://mitpress.mit.edu/books/" "building-successful-online-communities"
    )
    bookmark = get_bookmark_by_url(db.session, expected_url)
    assert bookmark == Bookmark(
        url=expected_url,
        title="Building Successful Online Communities | The MIT Press",
        description="<blockquote>How insights from the social sciences, including social psychology and economics, can improve the design of online communities.\n                Online communities are among the most popular destinations on the Internet, but not all online communities are equally successful. For every flourishing Facebook, there is a moribund Friendster—not to mention the scores of smaller social networking sites that never attracted enough members to be viable. This book offers lessons from theory an...",
        created=datetime(2019, 12, 18, 16, 51, 31, tzinfo=timezone.utc),
        updated=datetime(2018, 1, 3, tzinfo=timezone.utc),
        unread=True,
        deleted=False,
    )


@pytest.mark.pinboard_import
@freeze_time("2018-01-03")
def test_pinboard_with_note(session):
    runner = CliRunner()
    json_path = path.join(test_data_path, "pinboard-note.json")
    result = runner.invoke(pinboard_import, json_path, catch_exceptions=False)
    assert result.exit_code == 0

    expected_url = "http://notes.pinboard.in/u:calpaterson/abc123"
    bookmark = get_bookmark_by_url(db.session, expected_url)
    assert bookmark == Bookmark(
        url=expected_url,
        title="Secret Password",
        created=datetime(2011, 12, 13, 11, 38, 4, tzinfo=timezone.utc),
        description="",
        updated=datetime(2018, 1, 3, tzinfo=timezone.utc),
        unread=False,
        deleted=False,
    )
