# ADR-0002: Use Postgres full-text search (GeneratedField tsvector + GIN) for search

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** J. Rivera

## Context and problem statement

`GET /api/posts/search` matched with `body__icontains` (`ILIKE '%q%'`), which cannot use a
B-tree index and **sequential-scans** the posts table. Over 100k posts the endpoint took
12.2 s and 31,025 queries (the `ILIKE` scan plus an N+1 over authors/tags on every match).
We need real text search — stemming and relevance ranking, not substring matching — with
sub-second latency and without adding a new operational dependency for this scope. Which
search engine?

## Decision drivers

- Sub-second search with relevance ranking and stemming, not substring match.
- No new service to run, monitor, and keep in sync with Postgres.
- The index must stay correct automatically as posts are written.

## Considered options

1. **`body__icontains` / `ILIKE`** — the status quo (sequential scan).
2. **`pg_trgm` GIN index** (trigram similarity) for fuzzy/substring matching.
3. **Postgres FTS**: a `tsvector` column + GIN index + `SearchQuery`/`SearchRank`.
4. **Elasticsearch / OpenSearch.**

## Decision outcome

**Chosen: Postgres full-text search.** `Post.search_vector` is a Django **`GeneratedField`**
over `title` + `body` (`config="english"`), persisted by Postgres as
`GENERATED ALWAYS ... STORED` — so the database computes and maintains it on every
insert/update and Django never writes it by hand. It is indexed with a **GIN index**
(`post_search_gin`) and queried with `SearchQuery(q, search_type="websearch")` (supports
quoted phrases and `-` negation), ranked by `SearchRank`. Stemming, ranking, and language
config, all inside the database we already operate.

### Consequences

- 🟢 **Good:** search dropped from 12,205 ms / 31,025 queries to 488 ms / 3 queries — the
  GIN index replaces the sequential scan, and the N+1 is gone. The generated column can never
  drift out of sync with the content.
- 🟡 **Neutral / trade-off:** the remaining 488 ms is `SearchRank` scoring ~15k matches for a
  very common term (`time`). `pg_trgm` would add typo/fuzzy tolerance but does not replace FTS
  ranking; it would be an additive index if fuzzy search becomes a requirement.
- 🔴 **Risk / follow-up:** no relevance tuning or facets like Elasticsearch, and ranking cost
  grows with match count. Mitigation: cap the candidate set or rank only the top page for
  ultra-common terms (see [NOTES.md](../../NOTES.md) next steps). Revisit ES only when product
  needs relevance tuning/facets — the bar is high because it's a whole new service.
