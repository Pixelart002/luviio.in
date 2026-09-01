def test_application_imports(app):
    assert app.title
    assert app.version


def test_core_routes_are_registered(app):
    paths = {route.path for route in app.routes}

    for expected in ("/docs", "/redoc", "/openapi.json", "/health", "/api/v1/health"):
        assert expected in paths


def test_openapi_is_available(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"]


def test_domain_api_is_registered(app):
    paths = " ".join(route.path for route in app.routes).lower()

    for domain in ("auth", "products", "orders", "payments", "cart", "settings"):
        assert domain in paths
