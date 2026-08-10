import fakeredis
import pytest

from rate_limit import RateLimiter


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_allows_up_to_the_limit(redis_client):
    limiter = RateLimiter(redis_client, limit_per_minute=3)
    assert limiter.allow("client-1") is True
    assert limiter.allow("client-1") is True
    assert limiter.allow("client-1") is True


def test_blocks_once_limit_exceeded(redis_client):
    limiter = RateLimiter(redis_client, limit_per_minute=2)
    assert limiter.allow("client-1") is True
    assert limiter.allow("client-1") is True
    assert limiter.allow("client-1") is False


def test_different_clients_have_independent_limits(redis_client):
    limiter = RateLimiter(redis_client, limit_per_minute=1)
    assert limiter.allow("client-1") is True
    assert limiter.allow("client-2") is True
    assert limiter.allow("client-1") is False
