# Requirements: zyp

## Goal

A URL shortener service, functionally equivalent to sLink's core feature set, built on a
different stack (Python/Flask + Redis instead of Java/Spring Boot + H2/JPA) to demonstrate the
same capability with genuinely different storage-layer tradeoffs.

## Functional requirements

- `POST /api/v1/links` — create a short link from `originalUrl` (must be `http://` or `https://`),
  with an optional `customAlias` (4-20 chars, not a reserved word) and optional `expiresAt`.
- `GET /{code}` — 302 redirect to the original URL; records the click (referrer, user agent,
  timestamp) without blocking the redirect response.
- `GET /api/v1/links/{code}` — metadata only, no redirect, no click recorded.
- `PATCH /api/v1/links/{code}` — partial update: a null field is left unchanged. `active=false`
  deactivates without deleting.
- `DELETE /api/v1/links/{code}` — soft delete (same effect as `active=false`).
- `GET /api/v1/links/{code}/analytics` — total clicks, clicks by day, top referrers, top user
  agents, and the most recent clicks (newest first, capped at 50).
- `GET /api/v1/links` — paginated list, newest first.
- A minimal server-rendered admin UI (`/admin`, Basic Auth) for creating links and viewing the
  analytics dashboard, as a human-friendly complement to the JSON API and Swagger UI — not a
  replacement for either.

## Non-functional requirements

- Redis is the only datastore — no SQL, no separate persistence layer to migrate.
- Rate limiting on link creation only (not on redirects or reads), matching sLink's own decision.
- Errors on domain failures (unknown code, expired/deactivated link, alias conflict) return RFC
  7807 `problem+json`.
- OpenAPI/Swagger UI generated from the same schemas that validate requests.
- Core engineering principles: modular, testable, reliable — each service (link lifecycle,
  analytics, rate limiting) is independently unit-testable against `fakeredis`, with a separate
  integration-test layer against a real local Redis.
- ≥70% test coverage as a real, enforced build gate (`pytest --cov-fail-under=70`), the same
  threshold sLink's orchestrator enforces.

## Out of scope for this iteration

- Custom domains, link ownership / multi-tenant access control.
- Bulk/batch link creation.
- A production deployment guide (single-instance local dev is the target for this build).

## Assumptions

- A single local Redis instance is acceptable for this iteration; horizontal scaling of the
  Redis layer (Cluster/Sentinel) is a deployment concern, not a code-level requirement here.
- "Recent clicks" capped at 50 (matching sLink's own analytics cap) is an acceptable bound for the
  admin dashboard's activity table — older clicks remain reflected in the aggregate counters
  (total, by-day, top referrers/user-agents), just not in the raw recent-activity list.
- Admin auth can default to a fixed local-dev credential (documented in `config.py`), with the
  expectation that any real deployment sets `ADMIN_PASSWORD` explicitly — same tradeoff sLink
  makes for its own admin login.
