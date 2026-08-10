"""End-to-end tests against a real local Redis (db 15, flushed around each test) through FastAPI's
real TestClient — the create -> redirect -> analytics golden path, plus the error and rate-limit
paths. No fakeredis here: this is the same real Redis the app talks to in production.
"""

from __future__ import annotations

import pytest
import redis as redis_lib
from fastapi.testclient import TestClient

from app import create_app
from config import Config

TEST_REDIS_URL = "redis://localhost:6379/15"


@pytest.fixture
def client():
    raw = redis_lib.Redis.from_url(TEST_REDIS_URL)
    raw.flushdb()
    config = Config(redis_url=TEST_REDIS_URL, base_url="http://localhost:5055",
                     rate_limit_per_minute=3, auth_enabled=False)
    with TestClient(create_app(config)) as test_client:
        yield test_client
    raw.flushdb()


def test_create_redirect_and_analytics_golden_path(client):
    create_resp = client.post("/api/v1/links", json={"originalUrl": "https://example.com"})
    assert create_resp.status_code == 201
    code = create_resp.json()["code"]

    redirect_resp = client.get(f"/{code}", follow_redirects=False)
    assert redirect_resp.status_code == 302
    assert redirect_resp.headers["location"] == "https://example.com"

    analytics_resp = client.get(f"/api/v1/links/{code}/analytics")
    assert analytics_resp.status_code == 200
    assert analytics_resp.json()["totalClicks"] == 1


def test_unknown_code_returns_404_problem_json(client):
    resp = client.get("/api/v1/links/doesnotexist")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["type"].endswith("/not-found")


def test_expired_link_redirect_returns_410(client):
    create_resp = client.post("/api/v1/links", json={"originalUrl": "https://example.com", "expiresAt": 1})
    code = create_resp.json()["code"]
    resp = client.get(f"/{code}")
    assert resp.status_code == 410


def test_deactivate_then_redirect_returns_410(client):
    create_resp = client.post("/api/v1/links", json={"originalUrl": "https://example.com"})
    code = create_resp.json()["code"]
    client.delete(f"/api/v1/links/{code}")
    resp = client.get(f"/{code}")
    assert resp.status_code == 410


def test_duplicate_custom_alias_returns_409(client):
    client.post("/api/v1/links", json={"originalUrl": "https://example.com", "customAlias": "promo1"})
    resp = client.post("/api/v1/links", json={"originalUrl": "https://example.com/2", "customAlias": "promo1"})
    assert resp.status_code == 409


def test_rate_limit_applies_to_create_only(client):
    for _ in range(3):
        resp = client.post("/api/v1/links", json={"originalUrl": "https://example.com"})
        assert resp.status_code == 201
    blocked = client.post("/api/v1/links", json={"originalUrl": "https://example.com"})
    assert blocked.status_code == 429

    # creation is blocked, but GET (list/redirect) is not rate-limited
    list_resp = client.get("/api/v1/links")
    assert list_resp.status_code == 200


def test_swagger_ui_and_openapi_spec_are_served(client):
    assert client.get("/swagger-ui").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/links" in spec.json()["paths"]


def test_root_redirects_to_swagger_ui(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/swagger-ui"


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analytics_export_csv(client):
    create_resp = client.post("/api/v1/links", json={"originalUrl": "https://example.com"})
    code = create_resp.json()["code"]
    client.get(f"/{code}")  # generate a click

    resp = client.get(f"/api/v1/links/{code}/analytics/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.splitlines()
    assert lines[0] == "clicked_at,referrer,user_agent"
    assert len(lines) == 2


def test_analytics_export_unknown_code_returns_404(client):
    resp = client.get("/api/v1/links/doesnotexist/analytics/export")
    assert resp.status_code == 404
