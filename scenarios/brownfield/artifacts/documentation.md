# Documentation: CSV export for link analytics

## What shipped

`GET /api/v1/links/{code}/analytics/export` — the same recent-clicks data as
`GET /api/v1/links/{code}/analytics` (newest first, capped at 50), as a downloadable CSV file
with a `clicked_at,referrer,user_agent` header row.

## How to verify it

```bash
CODE=$(curl -s -X POST http://localhost:5055/api/v1/links -d '{"originalUrl":"https://example.com"}' \
  -H "Content-Type: application/json" | python3 -c "import json,sys; print(json.load(sys.stdin)['code'])")
curl http://localhost:5055/$CODE > /dev/null   # generate a click
curl http://localhost:5055/api/v1/links/$CODE/analytics/export
```

## Known limitations

- No date-range filtering — always the same most-recent-50 window the dashboard shows.
- Synchronous generation — fine at 50 rows, would need to become an async job at a much larger
  export size.
