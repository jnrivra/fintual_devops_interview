# ADR-0001: Paginate the list endpoints with PageNumberPagination

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** J. Rivera

## Context and problem statement

The list endpoints (`GET /api/posts`, `/api/posts/by-tag/{slug}`, `/api/posts/search`)
returned **every** matching row in a single response. Over a database seeded with 100k
published posts, the feed serialized the entire table on every call — unbounded response
size, unbounded memory, and (compounded by an N+1) a 96-second request. Even after the N+1
is fixed, returning 100k rows per request is not something you put behind a load balancer.
How should the list endpoints bound their work per request?

## Decision drivers

- Bounded, predictable response size and latency per request.
- Native support in django-ninja with minimal code.
- A response shape that exposes the total count to clients.

## Considered options

1. **No pagination** (return everything) — the status quo.
2. **`PageNumberPagination`** (offset/limit by page number), django-ninja's `@paginate`.
3. **Cursor / keyset pagination** on `(created_at, id)`.

## Decision outcome

**Chosen: `PageNumberPagination`** via django-ninja's `@paginate` decorator on the three
list endpoints. The response becomes a `{"items": [...], "count": N}` envelope. It is the
smallest change that bounds the work per request, it ships with the framework, and `count`
is useful to API consumers building pagers.

Keyset pagination is the better long-term answer for deep pagination (offset re-scans skipped
rows), but it is a larger change and the dataset is not yet deep-paginated in anger. It is
recorded here as the upgrade path rather than adopted now — an honest scope call.

### Consequences

- 🟢 **Good:** response size and latency are now bounded; the feed is 54 ms instead of 96 s
  (combined with the N+1 fix). The `count` field gives clients total size for free.
- 🟡 **Neutral / trade-off:** offset pagination re-scans skipped rows, so very deep pages
  (page 1000+) get progressively more expensive. Acceptable for current access patterns.
- 🔴 **Risk / follow-up:** if clients start deep-paginating, migrate to keyset pagination on
  the existing `(is_published, -created_at)` index — the index is already in place, so the
  change is localized to the queryset.
