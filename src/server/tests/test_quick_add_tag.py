import flask

from quarchive.data.functions import get_bookmark_by_url_uuid, set_bookmark

from .conftest import make_bookmark
from .utils import sync_bookmarks


def test_quick_add_tag(session, signed_in_client, test_user):
    bm = make_bookmark()
    set_bookmark(session, test_user.user_uuid, bm)

    response = signed_in_client.post(
        flask.url_for(
            "quarchive.quick_add_tag",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        ),
        data={"tag": "test-tag"},
    )
    assert response.status_code == 303

    new_bm = get_bookmark_by_url_uuid(session, test_user.user_uuid, bm.url.url_uuid)
    assert new_bm is not None
    assert "test-tag" in new_bm.current_tags()
