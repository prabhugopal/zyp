# Clarification: protect link analytics

Received after the first `implementation_core` verification attempt against the approved broad
scope (auth on both `.../analytics` and `.../analytics/export`).

Only the raw export needs to require authentication. The aggregated JSON summary at
`GET /api/v1/links/{code}/analytics` must stay public — it's already shown on the admin dashboard
to anyone with the link's admin URL, and gating it too would break casual sharing of that
dashboard link with teammates who don't have admin credentials.

**Narrowed scope: auth on `GET /api/v1/links/{code}/analytics/export` only.**
