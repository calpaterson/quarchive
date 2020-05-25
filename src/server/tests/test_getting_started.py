def test_getting_started(client):
    response = client.get("/getting-started")
    assert response.status_code == 200
