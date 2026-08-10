# Documentation: zyp

## What shipped

- Full CRUD + redirect API: `POST/GET /api/v1/links`, `GET/PATCH/DELETE /api/v1/links/{code}`,
  `GET /api/v1/links/{code}/analytics`, `GET /{code}`.
- Redis-native link lifecycle (`services/link_service.py`): Base62 codes from an atomic counter,
  custom aliases with reservation/collision checks, soft delete, newest-first pagination via a
  sorted set.
- Redis-native analytics (`services/analytics_service.py`): total clicks, clicks-by-day, top-10
  referrers/user-agents, most recent 50 clicks — each its own incrementally-updated structure, no
  aggregation query.
- Create-only rate limiting (`rate_limit.py`): a Redis fixed-window counter.
- RFC 7807 `problem+json` error responses for all domain errors (`errors.py`).
- OpenAPI/Swagger UI at `/swagger-ui`, generated from the same Pydantic models that validate
  requests.
- A minimal Basic-Auth admin UI (`/admin`) — link list + creation form, and a per-link detail page
  with a summary row (total clicks / active days / last click) above a recent-activity table and
  top-referrers/top-user-agents tables.
- `start.sh` — checks Redis is reachable and the port is free, then runs the app in the foreground.

## How to run it

```bash
uv sync
./start.sh
```

## How to verify it

```bash
uv run pytest tests/                                    # 40 tests
uv run pytest tests/ --cov=. --cov-report=term-missing   # coverage
```

Or manually:

```bash
curl -X POST http://localhost:5000/api/v1/links -d '{"originalUrl":"https://example.com"}' \
  -H "Content-Type: application/json"
curl -i http://localhost:5000/<code>
```

## Known limitations

- No custom domains or multi-tenant link ownership.
- No bulk/batch creation endpoint.
- `PATCH` can set an expiry but not clear one once set — a null field is always "leave unchanged",
  never "clear".
- The admin UI has no CSRF protection on the create-link form — acceptable for a local-dev tool
  behind Basic Auth, not something to carry into a real deployment without adding it.
