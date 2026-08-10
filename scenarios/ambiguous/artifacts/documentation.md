# Documentation: protect link analytics

## What shipped

Authentication (the same `require_auth` Basic Auth dependency the admin UI uses) on
`GET /api/v1/links/{code}/analytics/export` — the raw per-click export. The aggregated JSON
summary at `GET /api/v1/links/{code}/analytics` stays public.

This is the **narrowed** scope. The originally approved scope was broader (auth on both
endpoints); a clarification arrived after the first verification attempt explaining that only
the raw export needed protecting, since the summary is already visible on the dashboard to
anyone with the admin URL and gating it too would break casual sharing of that dashboard link
with teammates who don't have admin credentials.

## How to verify it

```bash
CODE=$(curl -s -X POST http://localhost:5055/api/v1/links -d '{"originalUrl":"https://example.com"}' \
  -H "Content-Type: application/json" | python3 -c "import json,sys; print(json.load(sys.stdin)['code'])")

curl -o /dev/null -s -w "%{http_code}\n" http://localhost:5055/api/v1/links/$CODE/analytics            # 200, public
curl -o /dev/null -s -w "%{http_code}\n" http://localhost:5055/api/v1/links/$CODE/analytics/export      # 401, no credentials
curl -o /dev/null -s -w "%{http_code}\n" -u admin:zyp@123 http://localhost:5055/api/v1/links/$CODE/analytics/export  # 200
```

## Known limitations

- Same credentials as the admin UI — no separate per-user analytics-export access.
- No audit log of who exported analytics data.
