import flask
from lxml import etree
from lxml.cssselect import CSSSelector

from .conftest import register_user, sign_in_as


def get_etree(response):
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    return root


def test_own_user_page(signed_in_client, test_user):
    response = signed_in_client.get(
        flask.url_for("quarchive.user_page", username=test_user.username)
    )
    assert response.status_code == 200

    h1 = CSSSelector("h1")
    pre = CSSSelector("pre")
    tree = get_etree(response)
    assert h1(tree)[0].text == test_user.username
    assert pre(tree)[0].text == test_user.api_key.hex()


def test_others_user_page(session, app, client, test_user):
    other_username = "not-" + test_user.username
    other_user = register_user(session, app, other_username)
    sign_in_as(client, test_user)

    response = client.get(
        flask.url_for("quarchive.user_page", username=other_user.username)
    )
    assert response.status_code == 200

    h1 = CSSSelector("h1")
    pre = CSSSelector("pre")
    tree = get_etree(response)
    assert h1(tree)[0].text == other_username
    assert pre(tree) == []


def test_user_page_that_does_not_exists(session, client):
    response = client.get(flask.url_for("quarchive.user_page", username="doesnt-exist"))
    assert response.status_code == 404


def test_update_own_user_page(session, signed_in_client, test_user):
    response = signed_in_client.post(
        flask.url_for("quarchive.user_page", username=test_user.username),
        data={"timezone": "Europe/Dublin"},
    )
    assert response.status_code == 303


def test_update_others_user_page(session, app, client, test_user):
    other_username = "not-" + test_user.username
    other_user = register_user(session, app, other_username)
    sign_in_as(client, test_user)

    response = client.post(
        flask.url_for("quarchive.user_page", username=other_user.username),
        data={"timezone": "Europe/Dublin"},
    )
    assert response.status_code == 403


def test_update_user_page_that_does_not_exist(session, client):
    response = client.post(
        flask.url_for("quarchive.user_page", username="doesnt-exist"),
        data={"timezone": "Europe/Dublin"},
    )
    assert response.status_code == 404
