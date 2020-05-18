def test_faq_page(client):
    response = client.get("/faq")
    assert response.status_code == 200
