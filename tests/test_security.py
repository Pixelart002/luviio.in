def test_security_headers_are_configured(client):
    response = client.get("/openapi.json")

    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy")


def test_unknown_route_is_not_successful(client):
    response = client.get("/route-that-does-not-exist")

    assert response.status_code == 404
