# Requirements: CSV export for link analytics

## Goal

Add `GET /api/v1/links/{code}/analytics/export`, returning the same recent-clicks data the
existing analytics endpoint already tracks, as a downloadable CSV file.

## Codebase impact

This is an addition to the existing service, not a new module:

- `service/services/analytics_service.py` — add an `export_csv(code)` method. It reads the same
  `zyp:analytics:{code}:recent` Redis list `get_analytics` already reads; no new Redis structure,
  no new write path.
- `service/routes/links.py` — add one new route on the existing `LinkAnalyticsItem` resource
  group. Reuses the existing 404-on-unknown-code check already used by the analytics endpoint.
- **Not touched**: `services/link_service.py`, `redis_client.py`, `rate_limit.py`, the admin UI,
  and the existing `GET /api/v1/links/{code}/analytics` endpoint's own behavior and response
  shape — this is a pure addition alongside it, not a modification of it.

## Functional requirements

- `GET /api/v1/links/{code}/analytics/export` returns `text/csv` with a header row
  (`clicked_at,referrer,user_agent`) followed by one row per recorded click, newest first,
  capped at the same 50-click limit as the JSON analytics endpoint.
- 404 if the code is unknown, matching the existing analytics endpoint's behavior.
- No new rate limiting — this is a read endpoint, and reads are already unrestricted.

## Assumptions

- No new query parameters (date-range filtering, a different cap) are needed for this iteration;
  the export mirrors exactly what the dashboard's recent-activity table already shows.
- The response is a plain CSV body with a `Content-Disposition: attachment` header — no separate
  async export job or download-link email flow, since 50 rows is small enough to generate
  synchronously within one request.
