from os import path, environ
from datetime import datetime, timezone
from unittest import mock
import json

import quarchive as sut

from click.testing import CliRunner
from freezegun import freeze_time
import pytest
from .conftest import test_data_path, make_bookmark

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
def test_pinboard_bookmark(session, test_user):
    runner = CliRunner()
    json_path = path.join(test_data_path, "pinboard-bookmark.json")
    result = runner.invoke(
        sut.pinboard_import,
        [str(test_user.user_uuid), json_path],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    expected_url = (
        "https://mitpress.mit.edu/books/" "building-successful-online-communities"
    )
    bookmark = sut.get_bookmark_by_url(
        sut.db.session, test_user.user_uuid, expected_url
    )
    assert bookmark == sut.Bookmark(
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
def test_pinboard_with_note(session, test_user):
    runner = CliRunner()
    json_path = path.join(test_data_path, "pinboard-note.json")
    result = runner.invoke(
        sut.pinboard_import,
        [str(test_user.user_uuid), json_path],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    expected_url = "http://notes.pinboard.in/u:calpaterson/abc123"
    bookmark = sut.get_bookmark_by_url(
        sut.db.session, test_user.user_uuid, expected_url
    )
    assert bookmark == sut.Bookmark(
        url=expected_url,
        title="Secret Password",
        created=datetime(2011, 12, 13, 11, 38, 4, tzinfo=timezone.utc),
        description="",
        updated=datetime(2018, 1, 3, tzinfo=timezone.utc),
        unread=False,
        deleted=False,
    )


@pytest.mark.pinboard_import
def test_pinboard_uses_merge(session, tmpdir, test_user):
    runner = CliRunner()

    existing_bookmark = make_bookmark(
        created=datetime(2018, 2, 1, tzinfo=timezone.utc),
        updated=datetime(2018, 2, 1, tzinfo=timezone.utc),
        description="as of 2018-02",
    )
    sut.set_bookmark(session, test_user.user_uuid, existing_bookmark)
    session.commit()

    pinboard_bookmarks = [
        dict(
            href=existing_bookmark.url,
            extended="",
            description="as of 2018-01-01",
            time=datetime(2018, 1, 12, tzinfo=timezone.utc).isoformat(),
            toread=False,
            deleted=False,
        )
    ]
    json_path = tmpdir.join("pinboard.json")
    with open(str(json_path), "w") as json_file:
        json.dump(pinboard_bookmarks, json_file)

    runner.invoke(
        sut.pinboard_import,
        [str(test_user.user_uuid), str(json_path), "--as-of", "2018-01-01"],
        catch_exceptions=False,
    )

    assert session.query(sut.SQLABookmark).count() == 1
    final_bookmark = sut.get_bookmark_by_url(
        session, test_user.user_uuid, existing_bookmark.url
    )
    assert final_bookmark is not None
    assert final_bookmark.created == datetime(2018, 1, 12, tzinfo=timezone.utc)
    assert final_bookmark.updated == datetime(2018, 2, 1, tzinfo=timezone.utc)
