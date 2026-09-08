def test_application_imports(app):
    assert app.title
    assert app.version


def _route_paths(routes):
    paths = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        nested = getattr(route, "routes", None)
        if nested:
            paths.update(_route_paths(nested))
        nested_router = getattr(route, "router", None)
        nested_routes = getattr(nested_router, "routes", None)
        if nested_routes:
            paths.update(_route_paths(nested_routes))
    return paths


def test_core_routes_are_registered(app):
    paths = set(app.openapi()["paths"])

    for expected in ("/health", "/api/v1/health"):
        assert expected in paths


def test_openapi_is_available(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"]


def test_domain_api_is_registered(app):
    paths = " ".join(app.openapi()["paths"]).lower()

    for domain in ("auth", "products", "orders", "payments", "cart", "settings"):
        assert domain in paths
