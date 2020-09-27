import flask
import pytest

import quarchive as sut
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
    sign_in_form_response = client.get("/sign-in")
    assert sign_in_form_response.status_code == 200

    sign_in_response = client.post(
        "/sign-in",
        data={"username": test_user.username, "password": test_user.password},
    )
    assert sign_in_response.status_code == 303
    assert sign_in_response.headers["Location"] == "http://localhost/"

    index_response = client.get("/")
    assert index_response.status_code == 200

    assert flask.session["user_uuid"] == test_user.user_uuid


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


def test_session_cookie(app, client, test_user):
    """Check that the session cookie has been set correctly, and with the
    relevant security headers.

    """
    sign_in_response = client.post(
        "/sign-in",
        data={"username": test_user.username, "password": test_user.password},
    )
    assert sign_in_response.status_code == 303

    cookie_header = sign_in_response.headers["Set-Cookie"]
    cookie_sections = cookie_header.split("; ")
    assert "HttpOnly" in cookie_sections
    assert "SameSite=Lax" in cookie_sections
