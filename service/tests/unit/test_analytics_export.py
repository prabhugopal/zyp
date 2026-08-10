import fakeredis
import pytest

from services.analytics_service import AnalyticsService


@pytest.fixture
def service():
    return AnalyticsService(fakeredis.FakeRedis(decode_responses=True))


def test_export_csv_header(service):
    csv_text = service.export_csv("abc")
    header = csv_text.splitlines()[0]
    assert header == "clicked_at,referrer,user_agent"


def test_export_csv_contains_recorded_clicks(service):
    service.record_click("abc", referrer="https://google.com", user_agent="curl/8.0")
    service.record_click("abc", referrer="direct", user_agent="Safari")
    csv_text = service.export_csv("abc")
    lines = csv_text.splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert "https://google.com" in csv_text
    assert "Safari" in csv_text


def test_export_csv_for_unclicked_code_is_header_only(service):
    csv_text = service.export_csv("never-clicked")
    assert csv_text.strip().splitlines() == ["clicked_at,referrer,user_agent"]
