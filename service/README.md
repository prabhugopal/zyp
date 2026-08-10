# Zyp service

A URL shortener built on FastAPI + Redis — no SQL, no ORM. Every feature is backed by the Redis
structure that's the natural fit for its access pattern: a sorted set for pagination, INCR/EXPIRE
for rate limiting, capped lists for recent-click history. See the [top-level README](../README.md)
for the full architecture and how [`../orchestrator/`](../orchestrator/) builds and gates it.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and a local Redis (`brew install redis`).

```bash
./start.sh                 # checks Redis + port, then runs in the foreground
# or: ./start.sh --port 9090
```

- Swagger UI: http://localhost:5055/swagger-ui
- Admin UI: http://localhost:5055/admin (Basic Auth, `admin` / `zyp@123` by default — see `config.py`)

```bash
curl -X POST http://localhost:5055/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{"originalUrl":"https://example.com"}'
# -> {"code":"...", "shortUrl":"http://localhost:5055/...", ...}

curl -i http://localhost:5055/<code>   # 302 redirect
```

## Tests

```bash
uv run pytest tests/                                          # 40 tests, ~2s
uv run pytest tests/ --cov=. --cov-report=term-missing         # 97% coverage
```

Unit tests (`tests/unit/`) use `fakeredis` — no Redis needed, fast. Integration tests
(`tests/integration/`) run against a real local Redis (db 15, flushed around each test) through
FastAPI's real TestClient — the actual create → redirect → analytics path, not mocked.

## API

| Method | Path | |
|---|---|---|
| `POST` | `/api/v1/links` | Create a short link (rate-limited) |
| `GET` | `/api/v1/links` | Paginated list, newest first |
| `GET` | `/api/v1/links/{code}` | Metadata, no redirect |
| `PATCH` | `/api/v1/links/{code}` | Partial update (expiry, active) |
| `DELETE` | `/api/v1/links/{code}` | Soft delete (deactivate) |
| `GET` | `/api/v1/links/{code}/analytics` | Total clicks, by-day, top referrers/user-agents, recent clicks |
| `GET` | `/{code}` | The actual redirect; records the click |

Errors are RFC 7807 `problem+json` for domain errors (404/409/410/400); request-validation errors
(422) keep FastAPI's own JSON shape.

## Design notes

- **Rate limiting is create-only** (redirects and reads stay unrestricted) — a Redis fixed-window
  counter (`INCR` + `EXPIRE`), a more natural fit here than an in-process token-bucket library
  since the counter already lives in the same store as everything else.
- **Codes are Base62-encoded sequence numbers** from a Redis `INCR` counter — an atomic counter
  standing in for a DB sequence, with no schema migration needed to add it.
- **Listing avoids a full scan** via a sorted set (`zyp:links_by_created`) ordered by creation
  time, read with `ZREVRANGE` — Redis's answer to `ORDER BY created_at DESC LIMIT/OFFSET`.
- **Soft delete** marks a link inactive rather than removing its Redis key, so click history
  survives the "deletion."
