# ADR-0003: Serve with gunicorn gthread workers, not an ASGI async stack

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** J. Rivera

## Context and problem statement

This is a synchronous Django app whose requests are **DB-bound** — the work is Postgres
round-trips, not fan-out to many slow upstream HTTP services. We need a production worker
model that performs well under this load profile and, above all, is simple to operate by
someone who didn't write it. Serve via gunicorn (sync/threads) or rewrite to ASGI
(uvicorn + async views + async ORM)?

## Decision drivers

- Throughput for short, DB-bound requests.
- Operational simplicity — the app must be ops-able by someone who didn't write it.
- Avoid a partial async rewrite and sync/async ORM foot-guns.

## Considered options

1. **gunicorn `sync` workers** — one request per worker process.
2. **gunicorn `gthread` workers** — threads per worker, overlap I/O waits.
3. **ASGI (uvicorn) + async views + async ORM.**

## Decision outcome

**Chosen: gunicorn `gthread`.** The image runs
`gunicorn core.wsgi:application --worker-class gthread --threads 4`, with
`--workers ${WEB_CONCURRENCY:-3}`, a 30 s `--timeout` and `--graceful-timeout`, and
`--max-requests 1000 --max-requests-jitter 100` to recycle workers and bound memory growth.
Threads overlap the Postgres wait of one request with the work of another without the
complexity of an async rewrite; the GIL is not the bottleneck because requests block on I/O,
not CPU. The codebase stays fully synchronous.

### Consequences

- 🟢 **Good:** good throughput for I/O-bound requests; a simple, mature, well-understood
  operational model; `--max-requests` recycling caps worker memory.
- 🟢 **Good:** no async/sync ORM hazards; the entire codebase stays synchronous and easy to
  reason about.
- 🟡 **Neutral / trade-off:** not ideal for high-fan-out, slow-upstream-HTTP workloads — we
  have none today.
- 🔴 **Risk / follow-up:** thread count must be tuned against the Postgres connection pool
  (`CONN_MAX_AGE=600`, persistent connections) so threads don't exhaust it. Keep
  `workers × threads` in line with the DB's connection budget.
