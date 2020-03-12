import pytest
import flask

import quarchive as sut


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


def test_registration_existing_username(client, session):
    client.post("/register", data={"username": "testuser1", "password": "password"})
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


@pytest.mark.xfail(reason="not implemented")
def test_sign_in():
    assert False


@pytest.mark.xfail(reason="not implemented")
def test_sign_in_wrong_username(client):
    assert False


@pytest.mark.xfail(reason="not implemented")
def test_sign_in_wrong_password(client):
    assert False
