import fakeredis
import pytest

from services.analytics_service import AnalyticsService


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def service(redis_client):
    return AnalyticsService(redis_client)


def test_record_click_increments_total(service):
    service.record_click("abc", referrer="https://google.com", user_agent="curl/8.0")
    service.record_click("abc", referrer="https://google.com", user_agent="curl/8.0")
    analytics = service.get_analytics("abc")
    assert analytics.total_clicks == 2


def test_record_click_tracks_clicks_by_day(service):
    service.record_click("abc", referrer="direct", user_agent="curl/8.0")
    analytics = service.get_analytics("abc")
    assert sum(analytics.clicks_by_day.values()) == 1


def test_top_referrers_ranked_by_count(service):
    service.record_click("abc", referrer="https://google.com", user_agent="ua")
    service.record_click("abc", referrer="https://google.com", user_agent="ua")
    service.record_click("abc", referrer="https://bing.com", user_agent="ua")
    top = service.get_analytics("abc").top_referrers
    assert top[0] == ("https://google.com", 2)
    assert top[1] == ("https://bing.com", 1)


def test_top_user_agents_ranked_by_count(service):
    service.record_click("abc", referrer="direct", user_agent="Chrome")
    service.record_click("abc", referrer="direct", user_agent="Chrome")
    service.record_click("abc", referrer="direct", user_agent="Safari")
    top = service.get_analytics("abc").top_user_agents
    assert top[0] == ("Chrome", 2)


def test_recent_clicks_newest_first_capped_at_50(service):
    for i in range(60):
        service.record_click("abc", referrer=f"ref{i}", user_agent="ua")
    recent = service.get_analytics("abc").recent_clicks
    assert len(recent) == 50
    assert recent[0].referrer == "ref59"


def test_analytics_for_unclicked_code_is_empty(service):
    analytics = service.get_analytics("never-clicked")
    assert analytics.total_clicks == 0
    assert analytics.top_referrers == []
    assert analytics.recent_clicks == []
