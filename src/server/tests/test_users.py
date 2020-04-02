import flask
import pytest

import quarchive as sut


def test_registration_form(client, session):
    registration_form_response = client.get("/register")
    assert registration_form_response.status_code == 200


def test_registration_no_email(client, session):
    response = client.post(
        "/register", data={"username": "testuser1", "password": "password"}
    )
    assert response.status_code == 303
    assert response.headers["Location"] == flask.url_for(
        "quarchive.index", _external=True
    )
    user = session.query(sut.SQLUser).one()
    assert user.username == "testuser1"
    assert user.password == "password"


def test_registration_with_email(client, session):
    response = client.post(
        "/register",
        data={
            "username": "testuser1",
            "password": "password",
            "email": "test@example.com",
        },
    )
    assert response.status_code == 303
    assert response.headers["Location"] == flask.url_for(
        "quarchive.index", _external=True
    )
    user = session.query(sut.SQLUser).one()
    assert user.username == "testuser1"
    assert user.password == "password"
    assert user.email_obj.email_address == "test@example.com"

    # check that registration logged us in
    assert "user_uuid" in flask.session


def test_registration_existing_username(client, session):
    client.post("/register", data={"username": "testuser1", "password": "password"})
    # Registration gives an automatic sign in
    with client.session_transaction() as flask_session:
        flask_session.clear()

    response = client.post(
        "/register", data={"username": "testuser1", "password": "password"}
    )
    assert response.status_code == 400
    assert session.query(sut.SQLUser).count() == 1


def test_registration_invalid_username(client, session):
    response = client.post(
        "/register", data={"username": "Test User", "password": "password"}
    )
    assert response.status_code == 400
    assert session.query(sut.SQLUser).count() == 0


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


@pytest.mark.xfail(reason="not implemented")
def test_logout(signed_in_client, test_user):
    response = signed_in_client.get("/sign-out")
    assert response.status_code == 303
    assert "user_uuid" not in flask.session
