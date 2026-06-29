# Architecture

Four views of the same service: how a request flows, why the feed went from 200,001 queries
to 3, how it deploys on Kubernetes, and how one `request_id` ties the telemetry together. All
diagrams are Mermaid and render natively on GitHub.

---

## (a) Component / request flow

A single Django app pod fronted by gunicorn. Every request gets a `request_id`, is measured
by the Prometheus middleware, validated by django-ninja, and served from Postgres with
`select_related` / `prefetch_related` so list endpoints stay at a constant query count.

```mermaid
flowchart LR
    client([Client]) -->|"HTTPS<br/>X-Request-ID (optional)"| ing[Ingress / ALB]
    ing --> gunicorn["gunicorn<br/>worker-class gthread, threads=4"]

    subgraph pod["Django app pod (non-root, read-only rootfs)"]
        direction TB
        gunicorn --> pbm["PrometheusBeforeMiddleware"]
        pbm --> sec["SecurityMiddleware + WhiteNoise"]
        sec --> rid["RequestIDMiddleware<br/>set/propagate request_id"]
        rid --> ninja["django-ninja router<br/>schema validation"]
        ninja --> view["view (blog/api.py)"]
        view --> orm["ORM<br/>select_related(author)<br/>prefetch_related(tags)"]
        rid -.-> logs[("JSON logs to stdout<br/>request_id, level, module")]
        pbm -.-> metrics["/metrics<br/>RED + DB"]
    end

    orm -->|"PageNumberPagination<br/>FTS via GIN index<br/>composite indexes"| pg[(PostgreSQL 16)]

    gunicorn -. liveness .-> hz["/healthz<br/>no I/O"]
    gunicorn -. readiness .-> rz["/readyz<br/>SELECT 1"]

    classDef store fill:#e8f0fe,stroke:#4285f4;
    class pg,logs store;
```

---

## (b) The N+1 path, before and after

The brief's slowest endpoint. Before: one query for the page, then an author query and a
tag query **per row** over ~100k published posts — 200,001 queries, 96 seconds. After:
`select_related` folds the author into a JOIN, `prefetch_related` fetches all tags in one
`IN (...)` query, and pagination bounds the page — 3 queries, 54 ms, constant in page size.

```mermaid
flowchart TB
    subgraph before["BEFORE — N+1 over author + tags"]
        direction TB
        b1["1x  SELECT * FROM posts WHERE is_published<br/>(no index, serialize ALL rows)"]
        b1 --> b2{"for each of ~100,000 posts"}
        b2 -->|"+1 query"| b3["SELECT author WHERE id = ?"]
        b2 -->|"+1 query"| b4["SELECT tags WHERE post_id = ?"]
        b3 --> b5["TOTAL: 1 + 2 x 100,000 = 200,001 queries<br/>96,328 ms"]
        b4 --> b5
    end

    subgraph after["AFTER — constant query count"]
        direction TB
        a1["1x  SELECT posts ...<br/>index (is_published, -created_at), LIMIT page"]
        a1 --> a2["1x  JOIN authors  (select_related)"]
        a2 --> a3["1x  SELECT tags WHERE post_id IN (...)  (prefetch_related)"]
        a3 --> a4["TOTAL: 3 queries<br/>54 ms"]
    end

    before ==>|"200,001 → 3 queries · ~1,780x faster"| after
```

Measured with the Django test client + `CaptureQueriesContext` over 100k posts / 500k
comments / 1000 users / 50 tags. Raw numbers in [`benchmarks/antes.json`](../benchmarks/antes.json)
and [`benchmarks/despues.json`](../benchmarks/despues.json).

---

## (c) Kubernetes deployment

Migrations run as a **Job** ordered ahead of the rollout (ArgoCD `PreSync` / Helm
`pre-install,pre-upgrade`), never as a per-replica initContainer. The Deployment carries
liveness / readiness / startup probes, resource requests + limits, a non-root read-only
security context, and is scaled by the HPA on CPU + memory.

```mermaid
flowchart TB
    user([User]) --> ing[Ingress / ALB]

    subgraph k8s["Kubernetes namespace"]
        ing --> svc["Service: fintual-content-service<br/>ClusterIP :80 → :8000"]
        svc --> p1["Pod: web-1<br/>gunicorn gthread"]
        svc --> p2["Pod: web-2"]
        svc --> pN["Pod: web-N"]

        hpa[["HPA<br/>min 2 / max 10<br/>CPU 70% · mem 80%"]] -.scales.-> p1

        job["Job: migrate (PreSync)<br/>manage.py migrate --noinput<br/>runs once per deploy"] --> pg
        job -. "completes before rollout" .-> p1

        subgraph cfg["Config"]
            cm["ConfigMap<br/>DJANGO_DEBUG=0, ALLOWED_HOSTS,<br/>WEB_CONCURRENCY"]
            sec["Secret<br/>DJANGO_SECRET_KEY, DATABASE_URL"]
        end
        cm -. envFrom .-> p1
        sec -. envFrom .-> p1

        p1 -. "/healthz liveness" .-> probe1{{process up?}}
        p1 -. "/readyz readiness" .-> probe2{{DB reachable?}}
    end

    p1 --> pg[(Managed PostgreSQL 16)]
    p2 --> pg
    pN --> pg

    classDef store fill:#e8f0fe,stroke:#4285f4;
    class pg store;
```

---

## (d) Observability correlation — one request_id across the signals

`RequestIDMiddleware` reads `X-Request-ID` (or mints one), stores it in a `contextvar`, and
echoes it on the response. The log filter stamps it on every JSON log line; the Prometheus
middleware records RED + DB metrics for the same request; and the same id is the key
OpenTelemetry tracing will reuse once the OTLP exporter is wired (next step). One key ties
logs, metrics, and traces together.

```mermaid
flowchart LR
    req["Incoming request<br/>X-Request-ID: abc123<br/>(or generated)"] --> mw["RequestIDMiddleware<br/>contextvar = abc123"]

    mw --> L["LOGS<br/>JSON line per request<br/>{request_id: abc123, ...}"]
    mw --> M["METRICS<br/>/metrics RED + DB<br/>(django-prometheus)"]
    mw --> T["TRACES (next)<br/>span attribute<br/>request_id=abc123 → Tempo"]

    L --> sink1[(Loki)]
    M --> sink2[(Prometheus)]
    T --> sink3[(Tempo)]

    sink1 -. "correlate by request_id" .-> graf["Grafana<br/>logs ↔ metrics ↔ traces"]
    sink2 -. "correlate by request_id" .-> graf
    sink3 -. "correlate by request_id" .-> graf

    resp["Response<br/>X-Request-ID: abc123"]
    mw --> resp
```
