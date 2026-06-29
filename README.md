# Content Service — a prototype turned into an operable service

![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)
![Django 5.2](https://img.shields.io/badge/django-5.2-092e20.svg)
![Postgres 16](https://img.shields.io/badge/postgres-16-336791.svg)
![CI](https://img.shields.io/badge/CI-ruff%20%2B%20pytest%20%2B%20docker-success.svg)

> **The brief asks to fix three areas. We read it differently: these aren't three
> isolated tasks — they're the three conditions for a prototype to survive in the real
> world: fast under load, operable and observable, and easy for anyone to run and
> understand. This repo isn't a log of three fixes; it's that prototype turned into an
> operable service.**

A small content service (users, posts, comments, tags) on **Django 5.2 + django-ninja +
PostgreSQL 16**. The starting point worked on a laptop and fell over under data. The work
below makes it fast, observable, and one command to run.

---

## The shape of the work

The brief lists three areas to improve. I treated them as **three conceptual pillars** of a
real-world service, mapped each fix to the pillar it serves, and went one step further: the
blue nodes are what I **added beyond the brief** — the difference between "it works" and
"it's operable."

```mermaid
flowchart TD
    T["<b>Thesis</b> · turn a working prototype<br/>into a service that survives the real world"]
    T --> P1
    T --> P2
    T --> P3

    P1["<b>Pillar 1 · Fast under load</b><br/><i>brief: Performance</i>"]
    P2["<b>Pillar 2 · Operable &amp; observable</b><br/><i>brief: Production readiness</i>"]
    P3["<b>Pillar 3 · Easy to run &amp; understand</b><br/><i>brief: Developer experience</i>"]

    P1 --> S1["Kill the N+1 · select_related / prefetch_related<br/>Pagination · bounded responses<br/>Postgres full-text search + GIN index<br/>Indexes matching the access pattern<br/>Atomic view_count via F()"]
    P1 --> A1(["<b>+ beyond the brief</b><br/>Measured before/after benchmarks<br/>N+1 regression test (pins query count)"])

    P2 --> S2["12-factor config + SECURE_* hardening<br/>Multi-stage Dockerfile + gunicorn<br/>K8s manifests + Helm + ArgoCD hook"]
    P2 --> A2(["<b>+ beyond the brief</b><br/>Prometheus /metrics (RED + DB)<br/>JSON logs + request_id correlation<br/>/healthz + /readyz split"])

    P3 --> S3["One command: make up<br/>docker-compose + .env.example"]
    P3 --> A3(["<b>+ beyond the brief</b><br/>README thesis + measured impact<br/>5 ADRs + Mermaid architecture diagrams<br/>AI-build transparency doc"])

    classDef pillar fill:#005ad6,stroke:#003f96,color:#fff;
    classDef added fill:#e6eef9,stroke:#005ad6,color:#003f96;
    class P1,P2,P3 pillar;
    class A1,A2,A3 added;
```

Each fix below sits under one of these pillars. The "beyond the brief" nodes are the signal:
they're what makes the service observable and the work legible to whoever inherits it.

---

## Impact (measured, not estimated)

Methodology: Django test client + `CaptureQueriesContext` over a database seeded with
**100k posts / 500k comments / 1000 users / 50 tags**. Same harness for before and after,
so the delta is the signal. Reproduce with `make bench`; raw output lives in
[`benchmarks/`](benchmarks/).

| Endpoint | Before | After | Change |
|---|---|---|---|
| `GET /api/posts` (feed) | **200,001 queries / 96,328 ms** | **3 queries / 54 ms** | ~1,780× faster, 200k → 3 queries |
| `GET /api/posts/by-tag/{slug}` | 200,001 queries / 15,128 ms | 4 queries / 59 ms | ~260× faster |
| `GET /api/posts/search?q=time` | 31,025 queries / 12,205 ms | 3 queries / 483 ms | ~25× faster, no more N+1 |
| `GET /api/posts/{id}` | 7 queries / 10 ms | 4 queries / 4.2 ms | fewer queries, race fixed |

**The headline:** the feed went from **96 seconds to 54 milliseconds** (~1,780×), and from
**200,001 SQL queries to 3**. The remaining ~483 ms on search is `SearchRank` scoring over
~15k matches for a very common term (`time`) — acceptable for now, and capped in
[Next steps](NOTES.md#3-what-id-do-next). Full reasoning in
[docs/architecture.md](docs/architecture.md) and the [ADRs](docs/adr/).

---

## How this was built — approach, time, and transparency

**Method, not luck.** I didn't guess at fixes. I seeded the database to production scale
(100k posts / 500k comments), **measured** every endpoint, and let the numbers set the order —
the 96-second feed was obviously first. I reframed the brief's three areas into the
[three-pillar thesis](#the-shape-of-the-work) above, chose depth over breadth, and recorded the
[scope cuts](NOTES.md#2-what-i-deliberately-did-not-do) as deliberate decisions rather than
gaps.

**AI-assisted, judgment in the loop.** Fintual allows LLMs *if you share how you used them*, so
this is fully transparent. The build was driven with **Claude Code**: parallel research
subagents investigated the tricky calls (Django `GeneratedField` + GIN `tsvector`, migrations
as a Job vs. an initContainer, gunicorn worker models), and I kept the judgment — reading every
diff, rejecting scope creep, and catching bugs by **actually running it**. Two real bugs were
found that way and fixed: the production image surfaced an HTTPS-redirect-vs-healthcheck issue,
and the dev `docker-compose` surfaced a venv-shadowing issue. Full account and representative
prompts: [NOTES.md](NOTES.md#4-ai-assisted-development-full-transparency) and
[docs/COMO-SE-CONSTRUYO.md](docs/COMO-SE-CONSTRUYO.md).

**Build log.** The brief sets a soft 2–6 hour window and says it looks at *signal, not hours* —
so I optimized for signal and tracked the time honestly as a build log. Total focused
engineering: **1 h 16 min** (21% of the 6 h timebox), leaning on parallel agents to keep
wall-clock tight while keeping the decisions human.

| Phase | Time |
|---|---|
| Planning & diagnosis — read the repo, map the planted problems, set the thesis | 25 min |
| Environment setup — toolchain, Postgres, seed 100k/500k | 10 min |
| Implementation & validation — the three pillars, benchmarked + Docker-tested | 41 min |
| **Total** | **1 h 16 min · 21% of the timebox** |

---

## Quickstart

**Requirements:** Docker + Docker Compose v2. Nothing else on the host.

```bash
make up      # builds the image, starts Postgres 16, runs migrations, starts the web app
make seed    # loads demo data (~100k posts / ~500k comments — takes a few minutes)
```

Then:

- API docs (OpenAPI / Swagger): <http://localhost:8000/api/docs>
- The feed: <http://localhost:8000/api/posts>
- Liveness / readiness: <http://localhost:8000/healthz> · <http://localhost:8000/readyz>
- Prometheus metrics: <http://localhost:8000/metrics>

`make help` lists every target. `make down` tears it all down (and wipes the dev volume).

> **Port-clash note for local Postgres.** Compose maps the container's Postgres to host
> port `5432` by default. If you already run Postgres locally, start with a different host
> port and the container is untouched:
> ```bash
> DB_PORT=5433 make up
> ```
> Running the app **without** Docker (`uv run python manage.py runserver`)? Point
> `DATABASE_URL` at that host port, e.g.
> `DATABASE_URL=postgres://postgres:postgres@localhost:5433/backend_devops_interview`.
> See [`.env.example`](.env.example).

---

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/posts` | Published posts, newest first — **paginated** `{items, count}` |
| GET | `/api/posts/search?q=` | Postgres full-text search across title + body |
| GET | `/api/posts/by-tag/{slug}` | Posts carrying a given tag |
| GET | `/api/posts/{id}` | Post detail with comments (atomic view-count increment) |
| POST | `/api/posts` | Create a post |
| POST | `/api/posts/{id}/comments` | Add a comment to a post |
| GET | `/api/users/{id}` | User profile with post + comment counts |
| GET | `/api/users/find?email=` | Look up a user by email (unique, indexed) |

The list endpoints now return a paginated envelope (`PageNumberPagination`):
`{"items": [...], "count": N}`.

---

## Architecture

Request flow — one Django app pod, fronted by gunicorn, talking to Postgres, emitting one
structured log line per request with a correlatable `request_id`:

```mermaid
flowchart LR
    client([Client]) -->|HTTPS, X-Request-ID| ing[Ingress / ALB]
    ing --> gunicorn["gunicorn<br/>(gthread workers)"]

    subgraph app["Django app pod (non-root)"]
        gunicorn --> mw["RequestIDMiddleware<br/>+ Prometheus middleware"]
        mw --> ninja["django-ninja router<br/>(schema validation)"]
        ninja --> orm["ORM<br/>select_related / prefetch_related"]
        mw --> log[("JSON logs to stdout<br/>request_id, level, module")]
    end

    orm -->|"PageNumberPagination<br/>FTS via GIN index"| pg[(PostgreSQL 16)]
    gunicorn -. liveness .-> hz["/healthz"]
    gunicorn -. readiness .-> rz["/readyz → SELECT 1"]
    gunicorn -. scrape .-> mx["/metrics (RED + DB)"]

    classDef store fill:#e8f0fe,stroke:#4285f4;
    class pg,log store;
```

The N+1 fix, in one picture — 200,001 queries collapse to 3, constant regardless of page
size:

```mermaid
flowchart TB
    subgraph before["BEFORE — N+1 (200,001 queries / 96,328 ms)"]
        direction TB
        b1["SELECT * FROM posts WHERE is_published LIMIT 100k"] --> b2{loop each row}
        b2 -->|"+1 query"| b3["SELECT author WHERE id = ?"]
        b2 -->|"+1 query"| b4["SELECT tags WHERE post_id = ?"]
        b3 --> bN["1 + 2 x 100,000 = 200,001 queries"]
        b4 --> bN
    end

    subgraph after["AFTER — 3 queries, constant (54 ms)"]
        direction TB
        a1["SELECT posts ... (composite index) LIMIT page"]
        a2["JOIN authors  -- select_related"]
        a3["SELECT tags WHERE post_id IN (...)  -- prefetch_related"]
        a1 --> a2 --> a3
    end

    before -.->|"~1,780x faster"| after
```

Full diagram set — request flow, before/after, Kubernetes deployment, and the
observability correlation — in **[docs/architecture.md](docs/architecture.md)**.

---

## What changed, and why

Three pillars; the deliberate non-goals and next steps are in **[NOTES.md](NOTES.md)**, and
the irreversible calls are recorded as **[ADRs](docs/adr/)**.

### Performance — [benchmarks/](benchmarks/)
- **Killed the N+1** on every list endpoint via `select_related("author")` +
  `prefetch_related("tags")`. Feed: 200,001 → 3 queries.
- **Pagination** (`PageNumberPagination`) so the feed stops serializing 100k rows per call.
- **Postgres full-text search**: a `GeneratedField` `tsvector` column + **GIN index**
  replaces the `icontains` sequential scan. → [ADR-0002](docs/adr/0002-postgres-fts.md)
- **Indexes that match the access pattern**: composite `(is_published, -created_at)` for the
  feed, `(post, created_at)` for comments, unique+indexed `User.email`.
- **Atomic `view_count`** via `F("view_count") + 1` — one UPDATE, no read-modify-write race.

### Production & observability — [docs/adr/0004](docs/adr/0004-observability-stack.md)
- **12-factor settings**: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL` from env;
  `SECURE_*` hardening switches on when `DEBUG=False`. WhiteNoise serves static.
- **Structured JSON logging** to stdout with a `request_id` correlated across the request
  (`core/observability.py`).
- **`/metrics`** (RED + DB metrics via `django-prometheus`), **`/healthz`** (liveness) and
  **`/readyz`** (readiness with a DB check) — split so a DB blip never restarts a healthy pod.
- **Multi-stage Dockerfile** (uv, `python:3.14-slim`, non-root, gunicorn `gthread`).
  → [ADR-0003](docs/adr/0003-gunicorn-over-asgi.md)
- **Kubernetes** manifests (probes, resource limits, HPA) with **migrations as a Job**, not
  an initContainer. → [ADR-0005](docs/adr/0005-migration-as-k8s-job.md)
- **Helm chart** with a Helm + ArgoCD PreSync migration hook; **GitHub Actions CI**
  (ruff + pytest on Postgres 16 + docker build).

### Developer experience
- **One command**: `make up` (db → migrate → web). Self-documenting `Makefile`,
  `.env.example`, `docker-compose` with a healthchecked Postgres and a run-to-completion
  migrate step.

---

## Tests

Five passing tests (`uv run pytest -q` or `make test`), including:
- an **N+1 regression test** (`test_list_posts_constant_queries_no_n_plus_one`) that asserts
  the feed stays at a constant, small query count — so the fix can't silently regress;
- a **full-text search test** proving search matches by content, not substring.

---

## Project layout

```
.
├── blog/                  # the domain app
│   ├── api.py             # django-ninja routes (the endpoints)
│   ├── models.py          # User, Tag, Post (tsvector + indexes), Comment
│   ├── schemas.py         # ninja Schema (request/response shapes)
│   ├── migrations/        # 0001_initial + 0002_performance (indexes, tsvector)
│   └── tests/             # 5 tests incl. the N+1 regression guard
├── core/                  # project config
│   ├── settings.py        # 12-factor, logging, security hardening
│   ├── observability.py   # request_id middleware + log filter
│   ├── health.py          # /healthz + /readyz
│   └── urls.py            # routes, /metrics, health
├── benchmarks/            # bench.py harness + antes.json / despues.json
├── k8s/                   # raw manifests (deployment, hpa, service, migrate Job)
├── helm/                  # minimal chart (deployment, hpa, migrate hook, ...)
├── docs/                  # architecture.md, adr/, COMO-SE-CONSTRUYO.md
├── Dockerfile             # multi-stage, uv, non-root
├── docker-compose.yml     # db (healthcheck) → migrate → web
├── Makefile               # self-documenting; `make help`
└── .github/workflows/ci.yml
```

---

## Documentation map

| Doc | What it answers |
|---|---|
| [NOTES.md](NOTES.md) | What I did / what I deliberately did NOT do / what I'd do next + AI disclosure |
| [docs/architecture.md](docs/architecture.md) | Five diagrams: conceptual pillar map, request flow, N+1 before/after, K8s, observability |
| [docs/adr/](docs/adr/) | The five irreversible decisions, in MADR/Nygard format |
| [docs/COMO-SE-CONSTRUYO.md](docs/COMO-SE-CONSTRUYO.md) | How this was built with Claude Code (AI-assisted, full transparency) |
| [CHANGELOG.md](CHANGELOG.md) | The hardening, in Keep a Changelog format |
| [benchmarks/](benchmarks/) | The harness and the raw before/after numbers |
