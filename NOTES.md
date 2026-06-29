# Engineering notes

> **The brief asks to fix three areas. I read it differently: these aren't three isolated
> tasks — they're the three conditions for a prototype to survive in the real world: fast
> under load, operable and observable, and easy for anyone to run and understand. This repo
> isn't a log of three fixes; it's that prototype turned into an operable service.**

This file answers the three questions the brief asks — **what I did and why**, **what I
deliberately did *not* do**, and **what I'd do next** — plus an honest account of the
AI-assisted workflow.

### How to read this submission (5-minute path)
1. `README.md` → thesis + the measured impact table.
2. `make up && make seed` → see it run; hit `/api/posts` and `/api/docs`.
3. This file → the judgment behind the code.
4. `docs/adr/` → the irreversible calls, in depth.

---

## 1. What I did, and why

I treated the task as **"make this prototype operable in production,"** organized in three
pillars. Every number below is from the same harness (`make bench`), measured over a DB
seeded with 100k posts / 500k comments / 1000 users / 50 tags.

### Performance — the feed went from 96 s to 54 ms

- **Eliminated the N+1 on the list endpoints.** `GET /api/posts` issued **200,001 queries**
  (one for the page, then one author + one tag-set per row across ~100k rows) and took
  **96 seconds**. Now **3 queries / 54 ms** via `select_related("author")` +
  `prefetch_related("tags")`. `by-tag` fell the same way: 200,001 → 4 queries.
  *Why this first:* it's the dominant cost; nothing else matters next to a 96-second feed.
- **Pagination** (`PageNumberPagination`). The feed serialized every published row on each
  call. It now returns a paginated envelope `{items, count}`, so the response is bounded.
- **Postgres full-text search.** Search used `body icontains` → a sequential scan over 100k
  rows (31,025 queries / 12.2 s with its own N+1). Replaced with a `GeneratedField`
  `tsvector` column (computed and kept in sync by Postgres, `GENERATED ALWAYS ... STORED`) +
  a **GIN index**, queried with `SearchQuery(..., search_type="websearch")`. Now 3 queries /
  ~483 ms. → [ADR-0002](docs/adr/0002-postgres-fts.md)
- **Indexes that match the access pattern.** Composite `(is_published, -created_at)` covers
  the feed's filter+sort (no disk sort); `(post, created_at)` covers the comment ordering in
  post detail; `User.email` is unique + indexed because `/api/users/find` looks up by it.
- **Atomic `view_count`.** Post detail incremented views with a read-modify-write
  (`post.view_count += 1; post.save()`), which both rewrote the whole row and lost updates
  under concurrency. Now a single `update(view_count=F("view_count") + 1)` — one statement,
  no race.
- **Regression-proofed it.** `test_list_posts_constant_queries_no_n_plus_one` asserts the
  feed stays at a small, constant query count, so the N+1 can't quietly come back.

### Production & observability — operable by someone who didn't write it

- **12-factor config** (`core/settings.py`): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`,
  `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL` all from env. `SECURE_*` hardening (HSTS, SSL
  redirect, secure cookies, nosniff) switches on automatically when `DEBUG=False`.
- **Structured JSON logging** to stdout, one line per request, with a **`request_id`**
  read from `X-Request-ID` (or generated) and propagated via a `contextvar`
  (`core/observability.py`). Ready to ship straight to Loki.
- **Health split**: `/healthz` (liveness, no I/O) and `/readyz` (readiness, `SELECT 1`), so
  a DB blip pulls the pod from the load balancer instead of restarting it.
- **`/metrics`** via `django-prometheus` (RED + DB metrics).
- **Validated the image end-to-end**, not just written. Building and running the container in
  prod mode (`DEBUG=False`) surfaced a real bug: `SECURE_SSL_REDIRECT` 301-redirects *every*
  path, so `/healthz`, `/readyz` and `/metrics` — which the kubelet and Prometheus hit over
  plain HTTP — would fail. Fixed with `SECURE_REDIRECT_EXEMPT`. Confirmed `/healthz` and
  `/readyz` return 200, the container reaches Postgres, and app routes still force HTTPS
  (200 behind an `X-Forwarded-Proto: https` proxy). This is the kind of thing you only catch
  by actually running it.
- **Container & orchestration**: multi-stage Dockerfile (uv, `python:3.14-slim`, non-root,
  gunicorn `gthread`); docker-compose (healthchecked PG16 → one-shot migrate → web);
  Kubernetes manifests with probes, resource limits, HPA, and **migrations as a Job** (never
  an initContainer that races across replicas); a minimal Helm chart with a Helm + ArgoCD
  PreSync migration hook; GitHub Actions CI (ruff + pytest on PG16 + docker build).
  → [ADR-0003](docs/adr/0003-gunicorn-over-asgi.md),
  [ADR-0004](docs/adr/0004-observability-stack.md),
  [ADR-0005](docs/adr/0005-migration-as-k8s-job.md)

### Developer experience — one command

- `make up` brings up db → migrate → web. The `Makefile` is self-documenting (`make help`),
  `.env.example` documents every variable, and the compose Postgres port is overridable
  (`DB_PORT=5433`) so it never clashes with a local install.

---

## 2. What I deliberately did NOT do (and why)

These were conscious scope cuts, not oversights. Each has a trigger that would make me
revisit it. The brief names the first two as non-goals; I'm naming the line so the reviewer
can judge the line itself.

| Not done | Why I cut it | When I'd add it |
|---|---|---|
| **Auth / authz** | Explicit non-goal in the brief; it adds surface area without exercising the asked-for skills. | First real multi-tenant or write-protection requirement; I'd start with token auth at the ninja layer. |
| **Exhaustive test coverage** | Explicit non-goal. I wrote the tests that *de-risk the changes* — an N+1 regression guard and an FTS test — not coverage for its own sake. | Continuously, as features land; contract tests against the OpenAPI schema next. |
| **Reshaping the domain model** | The brief says leave it unless a perf fix needs it. The perf fixes only needed indexes + a generated column, not a remodel. | Only when a feature genuinely needs a new shape. |
| **Redis / caching layer** | Premature — the ORM fixes already put the feed at 54 ms. Caching would *hide* an N+1, not fix it. | When read QPS exceeds one primary, or for the `view_count` write path (see next steps). |
| **Async / ASGI rewrite** | This is DB-bound, not fan-out-bound; `gthread` workers are simpler to operate and there are no slow upstreams to overlap. | If we add slow per-request upstream HTTP calls. → [ADR-0003](docs/adr/0003-gunicorn-over-asgi.md) |
| **Elasticsearch** | Postgres FTS covers current needs without a whole new operational dependency. | When we need relevance tuning, facets, or fuzzy/typo search at scale. → [ADR-0002](docs/adr/0002-postgres-fts.md) |
| **OpenTelemetry tracing wired to a backend** | The `request_id` correlation and the OTLP-ready shape are in place, but I describe the tracing pipeline rather than ship a half-configured collector. | Next (below). |

---

## 3. What I'd do next

Prioritized by leverage:

1. **OpenTelemetry tracing → Tempo.** Wire the OTLP exporter and propagate the existing
   `request_id` as a trace/span attribute so logs, metrics, and traces share one key.
   (Currently described, not shipped.)
2. **Redis-backed `view_count`.** Move the per-read increment to a Redis counter flushed to
   Postgres in batches, so the hot read path stops writing to the primary on every view.
3. **Search rank cap / cheaper ranking for ultra-common terms.** The remaining ~483 ms is
   `SearchRank` scoring ~15k matches for `time`. Cap the candidate set (or rank only the top
   page) so even pathological terms stay sub-100 ms.
4. **gunicorn multiprocess Prometheus mode.** Configure `prometheus_multiproc_dir` so metrics
   aggregate correctly across gthread workers under load.
5. **Grafana dashboards + alerting + SLOs.** Turn the RED metrics into a dashboard and alert
   on p95 latency and error rate against an explicit SLO.
6. **Secrets via ExternalSecrets.** The Helm `Secret` is a skeleton; in production these come
   from a secrets manager via ExternalSecrets, not inline values.

---

## 4. AI-assisted development (full transparency)

Fintual's brief explicitly allows AI agents *provided you say so and share the transcripts* —
so here is an honest account. Using an LLM well is itself an engineering skill; the signal
isn't "did they use AI" but "did they keep judgment in the loop and can they explain every
decision."

- **How it was built.** Implemented with **Claude Code**, driving **parallel research
  subagents** (to investigate Django `GeneratedField` + GIN tsvector behavior, the
  migrations-as-Job vs initContainer trade-off, and gunicorn worker models in isolated
  context windows) and a **planning bitácora / time-tracking log** that recorded each
  decision before it was made. The full account is in
  [docs/COMO-SE-CONSTRUYO.md](docs/COMO-SE-CONSTRUYO.md).
- **Human vs AI.** The **diagnosis and the judgment calls were mine**: reading the benchmark
  to find the N+1, choosing Postgres FTS over Elasticsearch, choosing a Job over an
  initContainer for migrations, choosing `gthread` over an async rewrite, and deciding the
  scope cuts above. The LLM accelerated *expression* — boilerplate, manifests, prose — and
  acted as a fast reviewer. I read and validated every line I kept and rejected suggestions
  that added scope.
- **Prompts & transcripts.** Available on request and described in
  [docs/COMO-SE-CONSTRUYO.md](docs/COMO-SE-CONSTRUYO.md). Representative prompts:
  - *"This benchmark shows `/api/posts` issuing 200,001 queries — confirm it's an N+1 over
    author and tags, and give the `select_related`/`prefetch_related` fix plus a regression
    test that pins the query count."*
  - *"Compare a Postgres `tsvector` GeneratedField + GIN index against `pg_trgm` and
    Elasticsearch for this search endpoint; recommend one and list the trade-offs."*
  - *"Should Django migrations run as a K8s initContainer or a Job when there are 2+
    replicas? Explain the race and write the manifest for the safer option."*
