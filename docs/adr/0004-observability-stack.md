# ADR-0004: Observability stack — JSON logs + request_id + Prometheus + split health

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** J. Rivera

## Context and problem statement

The prototype had no operational signal: no structured logs, no metrics, and a single health
notion that conflated "the process is up" with "the process can serve traffic." A service you
put behind a load balancer must be **debuggable at 3 a.m.** and must expose the signals an
orchestrator and a metrics system expect. What is the minimum observability stack that makes
this service operable without pulling in a heavy agent or a vendor SDK?

## Decision drivers

- Debuggability: correlate everything a single request did.
- Orchestrator-friendliness: distinct liveness vs readiness semantics.
- Standard, scrape-based metrics with no vendor lock-in.
- Minimal moving parts; nothing to babysit.

## Considered options

1. **Plain text logs + a single `/health`** — the status quo.
2. **JSON logs with a `request_id` contextvar + split `/healthz` / `/readyz` + Prometheus
   `/metrics`** (django-prometheus).
3. **A full vendor APM agent** (Datadog/New Relic) up front.
4. **Ship OpenTelemetry traces to a backend now.**

## Decision outcome

**Chosen: option 2.** `core/observability.py` adds a `RequestIDMiddleware` that reads
`X-Request-ID` (or generates one), stores it in a `contextvar`, echoes it back on the
response, and a log filter injects it into every record. Logs are emitted as **JSON to
stdout** (`python-json-logger`), one line per request, ready for Loki. Health is **split**:
`/healthz` (liveness, no I/O — a DB blip must not restart a healthy pod) and `/readyz`
(readiness, `SELECT 1` — a DB blip pulls the pod from the Service). `/metrics` is exposed by
**django-prometheus** (RED metrics + DB metrics) via middleware that wraps the stack.

Full OpenTelemetry tracing is intentionally *described, not shipped* — the `request_id` is the
correlation key it will reuse, so the path is wired without a half-configured collector
running.

### Consequences

- 🟢 **Good:** every request is traceable by `request_id` across logs (and, later, traces);
  liveness/readiness behave correctly under a DB blip; metrics are standard and pull-based.
- 🟢 **Good:** no vendor agent, no lock-in; logs go to stdout (12-factor), the platform
  collects them.
- 🟡 **Neutral / trade-off:** django-prometheus default (single-process) metrics need
  multiprocess mode configured to aggregate correctly across gthread workers under load
  (tracked in next steps).
- 🔴 **Risk / follow-up:** logs/metrics without dashboards and SLOs are raw signal. Next:
  OTLP tracing → Tempo, Grafana dashboards, and alerting on p95 + error rate.
