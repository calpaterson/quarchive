def test_about(client):
    response = client.get("/about")
    assert response.status_code == 200
