from uuid import uuid4
from typing import Sequence, Any
from http.cookies import SimpleCookie

import flask
import pytest

import quarchive as sut
from quarchive.web.users import get_current_user
from .conftest import random_string


def test_registration_form(client, session):
    registration_form_response = client.get("/register")
    assert registration_form_response.status_code == 200


def test_registration_no_email(client, session):
    username = "testuser-" + random_string()
    response = client.post(
        "/register", data={"username": username, "password": "password", "email": ""}
    )
    assert response.status_code == 303
    assert response.headers["Location"] == flask.url_for(
        "quarchive.my_bookmarks", _external=True
    )

    user = session.query(sut.SQLUser).filter(sut.SQLUser.username == username).one()
    assert user.username == username
    assert user.password == "password"
    assert user.email_obj is None


def test_registration_with_email(client, session):
    username = "testuser-" + random_string()
    response = client.post(
        "/register",
        data={
            "username": username,
            "password": "password",
            "email": "test@example.com",
        },
    )
    assert response.status_code == 303
    assert response.headers["Location"] == flask.url_for(
        "quarchive.my_bookmarks", _external=True
    )
    user = session.query(sut.SQLUser).filter(sut.SQLUser.username == username).one()
    assert user.username == username
    assert user.password == "password"
    assert user.email_obj.email_address == "test@example.com"

    # check that registration logged us in
    assert "user_uuid" in flask.session


@pytest.mark.xfail(reason="not implemented")
def test_registration_with_invalid_email(client, session):
    assert False


def test_registration_existing_username(client, session):
    username = "testuser-" + random_string()
    client.post(
        "/register", data={"username": username, "password": "password", "email": ""}
    )
    # Registration gives an automatic sign in
    with client.session_transaction() as flask_session:
        flask_session.clear()

    response = client.post(
        "/register", data={"username": username, "password": "password", "email": ""}
    )
    assert response.status_code == 400
    user_count = (
        session.query(sut.SQLUser).filter(sut.SQLUser.username == username).count()
    )
    assert user_count == 1


def test_registration_invalid_username(client, session):
    username = "Test User" + random_string()
    response = client.post(
        "/register", data={"username": username, "password": "password", "email": ""}
    )
    assert response.status_code == 400
    user_count = (
        session.query(sut.SQLUser).filter(sut.SQLUser.username == username).count()
    )
    assert user_count == 0


def test_sign_in_success(client, test_user):
    # Check that none of the test fixtures have left us signed in already.
    # This is a easy test bug to introduce and causes this test to spuriously
    # pass
    assert "user_uuid" not in flask.session, "session should not contain sign in!"
    assert "_quarchive_user" not in flask.g, "user should not already be set on g!"

    sign_in_form_response = client.get("/sign-in")
    assert sign_in_form_response.status_code == 200

    sign_in_response = client.post(
        "/sign-in",
        data={"username": test_user.username, "password": test_user.password},
    )
    assert sign_in_response.status_code == 303
    assert sign_in_response.headers["Location"] == "http://localhost/"

    index_response = client.get(flask.url_for("quarchive.my_bookmarks"))
    assert index_response.status_code == 200

    assert flask.session["user_uuid"] == test_user.user_uuid
    assert get_current_user() == test_user.as_user()


@pytest.mark.parametrize("cookie_value", [uuid4(), "nonsense"])
def test_corrupt_cookie_gets_deleted(client, cookie_value):
    with client.session_transaction() as flask_session:
        flask_session["user_uuid"] = cookie_value
    response = client.get(flask.url_for("quarchive.about"))
    assert response.status_code == 200


def test_sign_in_wrong_password(client, test_user):
    sign_in_response = client.post(
        "/sign-in", data={"username": test_user.username, "password": "wrong_password"},
    )
    assert sign_in_response.status_code == 400
    assert "user_uuid" not in flask.session


def test_sign_in_wrong_username(client, test_user):
    sign_in_response = client.post(
        "/sign-in", data={"username": "barney", "password": test_user.password},
    )
    assert sign_in_response.status_code == 400
    assert "user_uuid" not in flask.session


def test_logout(signed_in_client, test_user):
    response = signed_in_client.get("/sign-out")
    assert response.status_code == 200
    assert "user_uuid" not in flask.session


def test_auth_cookies(app, client, test_user):
    """Check that:

    1. The session cookie has been set, with the relevant security headers.

    2. The api key cookie has been set

    """
    sign_in_response = client.post(
        "/sign-in",
        data={"username": test_user.username, "password": test_user.password},
    )
    assert sign_in_response.status_code == 303

    cookies: Sequence[SimpleCookie] = [
        SimpleCookie(h) for h in sign_in_response.headers.get_all("Set-Cookie")
    ]

    session_cookie: Any = [c for c in cookies if "session" in c.keys()][0]
    sync_credentials_cookie: Any = [
        c for c in cookies if "sync_credentials" in c.keys()
    ][0]

    assert session_cookie["session"]["httponly"]
    # 3.7 SimpleCookie doesn't have support for reading SameSite, this is pretty wonky
    assert "SameSite=Lax" in str(session_cookie)

    expected_sync_credentials_value = "|".join(
        [test_user.username, test_user.api_key.hex()]
    )
    assert (
        sync_credentials_cookie["sync_credentials"].value
        == expected_sync_credentials_value
    )
    assert sync_credentials_cookie["sync_credentials"]["httponly"] == True
    assert sync_credentials_cookie["sync_credentials"]["secure"] == True
    assert "SameSite=Lax" in str(session_cookie)
