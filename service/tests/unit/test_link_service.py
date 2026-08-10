import time

import fakeredis
import pytest

from services.link_service import (
    AliasTakenError,
    InvalidAliasError,
    LinkExpiredError,
    LinkNotFoundError,
    LinkService,
)


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def service(redis_client):
    return LinkService(redis_client, base_url="http://localhost:5000")


def test_create_generates_code(service):
    link = service.create("https://example.com")
    assert link.code
    assert link.original_url == "https://example.com"
    assert link.active


def test_create_sequential_codes_differ(service):
    a = service.create("https://example.com/a")
    b = service.create("https://example.com/b")
    assert a.code != b.code


def test_create_rejects_non_http_scheme(service):
    with pytest.raises(ValueError):
        service.create("javascript:alert(1)")


def test_create_with_custom_alias(service):
    link = service.create("https://example.com", custom_alias="promo1")
    assert link.code == "promo1"


def test_create_with_taken_alias_raises(service):
    service.create("https://example.com", custom_alias="promo1")
    with pytest.raises(AliasTakenError):
        service.create("https://example.com/2", custom_alias="promo1")


def test_create_with_reserved_alias_raises(service):
    with pytest.raises(InvalidAliasError):
        service.create("https://example.com", custom_alias="admin")


def test_create_with_short_alias_raises(service):
    with pytest.raises(InvalidAliasError):
        service.create("https://example.com", custom_alias="ab")


def test_get_returns_created_link(service):
    created = service.create("https://example.com")
    fetched = service.get(created.code)
    assert fetched.original_url == "https://example.com"


def test_get_unknown_code_raises(service):
    with pytest.raises(LinkNotFoundError):
        service.get("doesnotexist")


def test_get_for_redirect_raises_when_inactive(service):
    link = service.create("https://example.com")
    service.delete(link.code)
    with pytest.raises(LinkExpiredError):
        service.get_for_redirect(link.code)


def test_get_for_redirect_raises_when_expired(service):
    link = service.create("https://example.com", expires_at=time.time() - 10)
    with pytest.raises(LinkExpiredError):
        service.get_for_redirect(link.code)


def test_update_active_flag(service):
    link = service.create("https://example.com")
    updated = service.update(link.code, active=False)
    assert updated.active is False


def test_delete_deactivates_not_removes(service):
    link = service.create("https://example.com")
    service.delete(link.code)
    fetched = service.get(link.code)
    assert fetched.active is False


def test_list_returns_newest_first(service):
    a = service.create("https://example.com/a")
    b = service.create("https://example.com/b")
    links, total = service.list(page=0, size=10)
    assert total == 2
    assert [l.code for l in links] == [b.code, a.code]


def test_list_pagination(service):
    for i in range(5):
        service.create(f"https://example.com/{i}")
    page0, total = service.list(page=0, size=2)
    page1, _ = service.list(page=1, size=2)
    assert total == 5
    assert len(page0) == 2
    assert len(page1) == 2
    assert page0[0].code != page1[0].code


def test_short_url(service):
    link = service.create("https://example.com")
    assert service.short_url(link.code) == f"http://localhost:5000/{link.code}"
