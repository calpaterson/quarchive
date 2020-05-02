import flask
import pytest


@pytest.mark.xfail()
def test_tags(signed_in_client, test_user):
    response = signed_in_client.get(
        flask.url_for("quarchive.user_tags", username=test_user.username, tag="test")
    )
    assert response.status_code == 200
