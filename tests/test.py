#!/usr/bin/env python3
"""
Luviio API — Live Endpoint Test Suite
======================================
Hits every endpoint on your deployed backend and reports pass/fail.
Built from a direct read of app/api/v1/routers/*.py and app/api/schemas/*.py
so payload shapes match your actual Pydantic DTOs.

Usage:
    pip install httpx --break-system-packages   # if not already installed
    python test_luviio_api.py

Config (env vars, all optional — defaults match the test account you shared):
    LUVIIO_BASE_URL      default: https://apparent-jordanna-pixelart002-42e39ac6.koyeb.app
    LUVIIO_TEST_EMAIL    default: test@test.com
    LUVIIO_TEST_PASSWORD default: Test1234!
    LUVIIO_RUN_CHECKOUT  default: false  (set "true" to actually place a real order)

Notes:
  - Runs against your live/production deployment using the test account you gave me.
  - Cart tests self-clean (adds then removes the item it added).
  - Checkout is OFF by default since it would create a real order — flip
    LUVIIO_RUN_CHECKOUT=true only if you also pass a real shipping_address_id
    (edit the CHECKOUT section below) and want to test that flow for real.
  - test@test.com is an ADMIN account, so admin-only routes are expected
    to return 200 for it. To also verify that a real customer gets BLOCKED
    (403) from those same routes, set LUVIIO_CUSTOMER_EMAIL / LUVIIO_CUSTOMER_PASSWORD
    for a second, non-admin test account.
"""

import os
import sys
import httpx

BASE_URL = os.getenv("LUVIIO_BASE_URL", "https://apparent-jordanna-pixelart002-42e39ac6.koyeb.app")
TEST_EMAIL = os.getenv("LUVIIO_TEST_EMAIL", "test@test.com")
TEST_PASSWORD = os.getenv("LUVIIO_TEST_PASSWORD", "Test1234!")
RUN_CHECKOUT = os.getenv("LUVIIO_RUN_CHECKOUT", "false").lower() == "true"

results = []  # (name, passed, detail)


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail else ""))


def check(name, condition, detail=""):
    record(name, bool(condition), detail)


client = httpx.Client(base_url=BASE_URL, timeout=15.0)

print(f"\n{'=' * 70}\nLUVIIO API TEST SUITE -- {BASE_URL}\n{'=' * 70}\n")

# ── 1. HEALTH ──────────────────────────────────────────────────────────
print("\n--- Health ---")
for path in ("/health", "/api/v1/health"):
    try:
        r = client.get(path)
        check(f"GET {path}", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check(f"GET {path}", False, str(e))

# ── 2. PUBLIC CATALOG ────────────────────────────────────────────────
print("\n--- Public Catalog ---")
sample_slug = None
sample_product_id = None

try:
    r = client.get("/api/v1/categories")
    check("GET /api/v1/categories", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    check("GET /api/v1/categories", False, str(e))

try:
    r = client.get("/api/v1/products", params={"page": 1, "page_size": 5})
    check("GET /api/v1/products", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        # paginate() puts the list directly under "data" (not data.items)
        items = r.json().get("data") or []
        if items:
            sample_slug = items[0].get("slug")
            sample_product_id = items[0].get("id")
except Exception as e:
    check("GET /api/v1/products", False, str(e))

if sample_slug:
    try:
        r = client.get(f"/api/v1/products/{sample_slug}")
        check("GET /api/v1/products/{slug}", r.status_code == 200, f"status={r.status_code}, slug={sample_slug}")
    except Exception as e:
        check("GET /api/v1/products/{slug}", False, str(e))
else:
    record("GET /api/v1/products/{slug}", False, "skipped -- no product found in catalog to test against")

try:
    r = client.get("/api/v1/products/this-slug-should-not-exist-xyz")
    check("GET /api/v1/products/{bad_slug} -> 404", r.status_code == 404, f"status={r.status_code}")
except Exception as e:
    check("GET /api/v1/products/{bad_slug}", False, str(e))

# ── 3. PUSH (public) ─────────────────────────────────────────────────
print("\n--- Push (public) ---")
try:
    r = client.get("/api/v1/push/vapid-key")
    check("GET /api/v1/push/vapid-key", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    check("GET /api/v1/push/vapid-key", False, str(e))

# ── 4. UNAUTHENTICATED ACCESS TO PROTECTED ROUTES -> 401 ─────────────
print("\n--- Auth Guard (no token) ---")
for method, path in [
    ("GET", "/api/v1/users/me"),
    ("GET", "/api/v1/cart"),
    ("GET", "/api/v1/orders/my"),
    ("GET", "/api/v1/admin/verify"),
]:
    try:
        r = client.request(method, path)
        check(f"{method} {path} (no auth) -> 401", r.status_code == 401, f"status={r.status_code}")
    except Exception as e:
        check(f"{method} {path} (no auth)", False, str(e))

# ── 5. CORS ENFORCEMENT ────────────────────────────────────────────────
print("\n--- CORS Policy ---")
try:
    r = client.get("/api/v1/categories", headers={"Origin": "https://evil-test-site.example.com"})
    check("Disallowed Origin -> 403", r.status_code == 403, f"status={r.status_code}")
except Exception as e:
    check("Disallowed Origin -> 403", False, str(e))

try:
    r = client.get("/api/v1/categories", headers={"Origin": "https://luviio.in"})
    allow_origin = r.headers.get("access-control-allow-origin")
    check(
        "Allowed Origin (luviio.in) -> 200 + ACAO header",
        r.status_code == 200 and allow_origin == "https://luviio.in",
        f"status={r.status_code}, ACAO={allow_origin}",
    )
except Exception as e:
    check("Allowed Origin (luviio.in)", False, str(e))

# ── 6. LOGIN + SESSION ──────────────────────────────────────────────────
print("\n--- Auth Flow ---")
access_token = None
try:
    r = client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    ok = r.status_code == 200
    check("POST /api/v1/auth/login", ok, f"status={r.status_code}")
    if ok:
        access_token = r.json()["data"]["access_token"]
        check("Login sets refresh_token cookie", "refresh_token" in client.cookies)
        set_cookie_raw = r.headers.get("set-cookie", "").lower()
        check("Refresh cookie is HttpOnly", "httponly" in set_cookie_raw)
        check("Refresh cookie is Secure", "secure" in set_cookie_raw)
except Exception as e:
    check("POST /api/v1/auth/login", False, str(e))

auth_headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

if access_token:
    for name, method, path in [
        ("GET /api/v1/auth/session", "GET", "/api/v1/auth/session"),
        ("GET /api/v1/users/me", "GET", "/api/v1/users/me"),
        ("GET /api/v1/users/me/addresses", "GET", "/api/v1/users/me/addresses"),
    ]:
        try:
            r = client.request(method, path, headers=auth_headers)
            check(name, r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            check(name, False, str(e))
else:
    record("Authenticated user endpoints", False, "skipped -- login failed, no access token")

# ── 7. CART FLOW (self-cleaning) ─────────────────────────────────────
print("\n--- Cart Flow ---")
if access_token:
    try:
        r = client.get("/api/v1/cart", headers=auth_headers)
        check("GET /api/v1/cart", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check("GET /api/v1/cart", False, str(e))

    if sample_product_id:
        try:
            r = client.post(
                "/api/v1/cart/items",
                headers=auth_headers,
                json={"product_id": sample_product_id, "quantity": 1},
            )
            check("POST /api/v1/cart/items", r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            check("POST /api/v1/cart/items", False, str(e))

        try:
            r = client.put(
                f"/api/v1/cart/items/{sample_product_id}",
                headers=auth_headers,
                json={"quantity": 2},
            )
            check("PUT /api/v1/cart/items/{id}", r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            check("PUT /api/v1/cart/items/{id}", False, str(e))

        try:
            r = client.delete(f"/api/v1/cart/items/{sample_product_id}", headers=auth_headers)
            check("DELETE /api/v1/cart/items/{id}", r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            check("DELETE /api/v1/cart/items/{id}", False, str(e))
    else:
        record("Cart item add/update/remove", False, "skipped -- no product_id available from catalog")

    try:
        r = client.delete("/api/v1/cart", headers=auth_headers)
        check("DELETE /api/v1/cart (clear)", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check("DELETE /api/v1/cart (clear)", False, str(e))
else:
    record("Cart flow", False, "skipped -- no access token")

# ── 8. ORDERS ─────────────────────────────────────────────────────────
print("\n--- Orders ---")
if access_token:
    try:
        r = client.get("/api/v1/orders/my", headers=auth_headers)
        check("GET /api/v1/orders/my", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check("GET /api/v1/orders/my", False, str(e))

    if RUN_CHECKOUT:
        # Edit this UUID to a real shipping_address_id on the test account before enabling.
        SHIPPING_ADDRESS_ID = os.getenv("LUVIIO_SHIPPING_ADDRESS_ID", "")
        if SHIPPING_ADDRESS_ID:
            try:
                r = client.post(
                    "/api/v1/orders/checkout",
                    headers=auth_headers,
                    json={"shipping_address_id": SHIPPING_ADDRESS_ID, "idempotency_key": "test-run-001"},
                )
                check("POST /api/v1/orders/checkout", r.status_code == 201, f"status={r.status_code}")
            except Exception as e:
                check("POST /api/v1/orders/checkout", False, str(e))
        else:
            record("POST /api/v1/orders/checkout", False, "RUN_CHECKOUT=true but LUVIIO_SHIPPING_ADDRESS_ID not set")
    else:
        record("POST /api/v1/orders/checkout", True, "skipped by default -- set LUVIIO_RUN_CHECKOUT=true to test (creates a REAL order)")
else:
    record("Orders", False, "skipped -- no access token")

# ── 9. RBAC -- test@test.com IS ADMIN -> these should all succeed ────
print("\n--- Admin Access (test account is admin -> expect 200) ---")
if access_token:
    for method, path in [
        ("GET", "/api/v1/admin/verify"),
        ("GET", "/api/v1/admin/stats"),
        ("GET", "/api/v1/users/"),
        ("GET", "/api/v1/orders/"),
        ("GET", "/api/v1/settings/"),
        ("GET", "/api/v1/cart/admin/abandoned"),
        ("GET", "/api/v1/push/admin/stats"),
    ]:
        try:
            r = client.request(method, path, headers=auth_headers)
            check(f"{method} {path} (admin) -> 200", r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            check(f"{method} {path} (admin)", False, str(e))
else:
    record("Admin access checks", False, "skipped -- no access token")

# ── 9b. IMPORTANT: negative RBAC (403 for non-admin) is UNTESTED here ─
# test@test.com is admin, so this suite can't verify that a real customer
# gets blocked from admin routes. If you have (or can create) a second
# plain-customer test account, set these env vars to also run that check:
#   LUVIIO_CUSTOMER_EMAIL / LUVIIO_CUSTOMER_PASSWORD
CUSTOMER_EMAIL = os.getenv("LUVIIO_CUSTOMER_EMAIL")
CUSTOMER_PASSWORD = os.getenv("LUVIIO_CUSTOMER_PASSWORD")
if CUSTOMER_EMAIL and CUSTOMER_PASSWORD:
    print("\n--- RBAC Negative Check (separate non-admin account) ---")
    cust_client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    try:
        r = cust_client.post("/api/v1/auth/login", json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD})
        if r.status_code == 200:
            cust_token = r.json()["data"]["access_token"]
            cust_headers = {"Authorization": f"Bearer {cust_token}"}
            for method, path in [("GET", "/api/v1/admin/verify"), ("GET", "/api/v1/users/"), ("GET", "/api/v1/settings/")]:
                r = cust_client.request(method, path, headers=cust_headers)
                check(f"{method} {path} (non-admin) -> 403", r.status_code == 403, f"status={r.status_code}")
        else:
            record("Customer account login", False, f"status={r.status_code}")
    except Exception as e:
        record("RBAC negative check", False, str(e))
    cust_client.close()
else:
    record(
        "RBAC negative check (non-admin -> 403)",
        True,
        "skipped -- no second customer account provided; this is the one gap this suite can't verify with only test@test.com",
    )

# ── 10. SESSION LIFECYCLE ────────────────────────────────────────────
print("\n--- Session Lifecycle ---")
if access_token:
    try:
        r = client.post("/api/v1/auth/refresh")
        check("POST /api/v1/auth/refresh (via cookie)", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check("POST /api/v1/auth/refresh", False, str(e))

    try:
        r = client.post("/api/v1/auth/logout")
        check("POST /api/v1/auth/logout", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        check("POST /api/v1/auth/logout", False, str(e))
else:
    record("Refresh/Logout", False, "skipped -- no access token")

# ── SUMMARY ───────────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
passed = sum(1 for _, p, _ in results if p)
total = len(results)
print(f"SUMMARY: {passed}/{total} passed")
if passed != total:
    print("\nFailures:")
    for name, p, detail in results:
        if not p:
            print(f"  - {name}" + (f"  ({detail})" if detail else ""))
print(f"{'=' * 70}\n")

sys.exit(0 if passed == total else 1)