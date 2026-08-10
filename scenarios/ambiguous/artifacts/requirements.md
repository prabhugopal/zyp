# Requirements: protect link analytics

## The ambiguity

"Make link analytics access more secure" doesn't say which of two surfaces needs protecting:

- `GET /api/v1/links/{code}/analytics` — an aggregated summary (totals, top referrers/user
  agents, a capped recent-clicks list). Low sensitivity: no single click is individually
  traceable to more than a timestamp/referrer/user-agent triple, and the dashboard already
  displays this to anyone who has the link's admin URL.
- `GET /api/v1/links/{code}/analytics/export` — the same recent-clicks data, but as a raw,
  downloadable file. Higher sensitivity: it's a bulk export, easier to exfiltrate and correlate
  than reading numbers off a dashboard.

"More secure" could reasonably mean protecting just the export (the higher-sensitivity surface),
or both (treat all analytics access uniformly), or something else entirely (per-link access
tokens, rate limiting analytics reads, IP allowlisting). This scenario picks between the first
two: **export-only** vs **both endpoints**.

## Interpreted scope (pending approval)

The broader reading — require authentication on both `.../analytics` and
`.../analytics/export` — is the safer default when a security request is underspecified, so
that's what's proposed for approval before implementation is verified. See `design.md`.

## Assumptions

- "More secure" means authentication, not a different security control (rate limiting, IP
  allowlisting, per-link tokens) — the existing Basic Auth mechanism already used by `/admin` is
  the natural reuse rather than building something new.
- Whichever scope is approved, `/{code}` (the actual redirect) and `POST /api/v1/links` (link
  creation) are unaffected — the request is specifically about analytics *access*, not the core
  shortening flow.
- A later clarification could narrow this to export-only if the broader interpretation turns out
  to be more than what was actually wanted — see the orchestrator run history for how a
  clarification arriving after implementation started changes what's verified.
