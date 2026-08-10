from __future__ import annotations

import base64

import pytest
import redis as redis_lib

from app import create_app
from config import Config

TEST_REDIS_URL = "redis://localhost:6379/15"


@pytest.fixture
def app():
    raw = redis_lib.Redis.from_url(TEST_REDIS_URL)
    raw.flushdb()
    config = Config(redis_url=TEST_REDIS_URL, base_url="http://localhost:5000",
                     admin_username="admin", admin_password="secret", auth_enabled=True)
    application = create_app(config)
    application.testing = True
    yield application
    raw.flushdb()


@pytest.fixture
def client(app):
    return app.test_client()


def _basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_admin_requires_auth_when_enabled(client):
    resp = client.get("/admin")
    assert resp.status_code == 401


def test_admin_index_with_valid_auth(client):
    resp = client.get("/admin", headers=_basic_auth_header("admin", "secret"))
    assert resp.status_code == 200
    assert b"Zyp" in resp.data


def test_admin_rejects_wrong_password(client):
    resp = client.get("/admin", headers=_basic_auth_header("admin", "wrong"))
    assert resp.status_code == 401


def test_admin_create_link_via_form(client):
    headers = _basic_auth_header("admin", "secret")
    resp = client.post("/admin/links", data={"originalUrl": "https://example.com"}, headers=headers)
    assert resp.status_code == 302
    assert "created=" in resp.headers["Location"]


def test_admin_create_with_invalid_url_redirects_with_error(client):
    headers = _basic_auth_header("admin", "secret")
    resp = client.post("/admin/links", data={"originalUrl": "not-a-url"}, headers=headers)
    assert resp.status_code == 302
    assert "error=" in resp.headers["Location"]


def test_admin_detail_shows_link_and_analytics(client):
    headers = _basic_auth_header("admin", "secret")
    create_resp = client.post("/admin/links", data={"originalUrl": "https://example.com"}, headers=headers)
    code = create_resp.headers["Location"].split("created=")[1]

    client.get(f"/{code}")  # generate a click
    detail_resp = client.get(f"/admin/{code}", headers=headers)
    assert detail_resp.status_code == 200
    assert code.encode() in detail_resp.data


def test_admin_detail_unknown_code_redirects_to_index(client):
    headers = _basic_auth_header("admin", "secret")
    resp = client.get("/admin/doesnotexist", headers=headers)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin")
