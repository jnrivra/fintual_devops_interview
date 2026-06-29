# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

Turning the working prototype into an operable service, across three pillars: performance,
production & observability, and developer experience. See [NOTES.md](NOTES.md) for the
reasoning and [docs/adr/](docs/adr/) for the decisions.

### Added
- **Postgres full-text search**: a `GeneratedField` `tsvector` column over `title` + `body`
  with a **GIN index** (`post_search_gin`), replacing the `icontains` sequential scan.
  (ADR-0002)
- **Pagination** on the list endpoints (`PageNumberPagination`); responses are now
  `{items, count}`. (ADR-0001)
- **Indexes matching the access pattern**: composite `(is_published, -created_at)` on posts,
  `(post, created_at)` on comments; `User.email` made unique + indexed.
- **Observability**: structured JSON logging to stdout with a `request_id` correlated across
  the request (`core/observability.py`); `/metrics` via `django-prometheus` (RED + DB);
  `/healthz` (liveness) and `/readyz` (readiness with a DB check). (ADR-0004)
- **12-factor settings**: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL` from env;
  `SECURE_*` hardening (HSTS, SSL redirect, secure cookies, nosniff) active when `DEBUG=False`;
  WhiteNoise for static files.
- **Containerization & orchestration**: multi-stage Dockerfile (uv, `python:3.14-slim`,
  non-root, gunicorn `gthread`); docker-compose (healthchecked PG16 → migrate → web);
  Kubernetes manifests (probes, resource limits, HPA, migrate **Job**); a minimal Helm chart
  with a Helm + ArgoCD PreSync migration hook. (ADR-0003, ADR-0005)
- **CI**: GitHub Actions running ruff (lint + format) + pytest on Postgres 16 + docker build.
- **Developer experience**: self-documenting `Makefile` (`make up` / `make seed` / `make
  bench`), `.env.example`, and a configurable Postgres host port (`DB_PORT`) to avoid clashes.
- **Tests**: an N+1 regression guard (asserts constant query count on the feed) and a
  full-text search test, alongside the existing smoke tests (5 passing).
- **Benchmark harness** (`benchmarks/bench.py`) plus before/after results
  (`benchmarks/antes.json`, `benchmarks/despues.json`).
- **Documentation**: thesis-driven README, NOTES, five ADRs, an architecture doc with four
  Mermaid diagrams, and an AI-assisted build account.

### Changed
- **Eliminated the N+1** on the list endpoints via `select_related("author")` +
  `prefetch_related("tags")`: `GET /api/posts` went from **200,001 queries / 96,328 ms** to
  **3 queries / 54 ms** (~1,780× faster); `by-tag` from 200,001 to 4 queries.
- **Atomic `view_count`** on post detail via `F("view_count") + 1` — a single UPDATE,
  replacing a read-modify-write that lost updates under concurrency.

### Fixed
- Race condition / lost update in the post-detail view counter.
- Unbounded list responses that serialized the entire posts table per request.

## [0.1.0]

### Added
- Initial prototype: Django + django-ninja + Postgres content service (users, posts,
  comments, tags) with smoke tests and a seed command.
