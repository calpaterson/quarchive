import flask


def test_static_service(client):
    response = client.get(flask.url_for("static", filename="site.css"))
    assert response.status_code == 200
