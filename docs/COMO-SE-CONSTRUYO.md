# How this was built (AI-assisted)

Fintual's brief explicitly allows AI agents, provided you say so and share the transcripts.
This document is that disclosure: an honest account of the Claude Code tooling used, what the
AI did versus what I decided, and how to verify it. The premise is simple — **directing an
LLM well is an engineering skill**, and the signal isn't "did they use AI" but "did they keep
judgment in the loop and can they explain every line."

---

## The tools, and how each was actually used

This project was built with **Claude Code**, Anthropic's CLI agent. Of its feature set
(documented in the tooling reference I worked from), I leaned on a focused subset — the parts
that genuinely help a tightly-scoped backend take-home, not the whole kitchen sink.

### Parallel research subagents

Subagents are specialized Claude instances that run in **isolated context windows** and
return only a summary to the main session — so exploratory research doesn't flood the working
context. I used them to investigate, in parallel, the three decisions that needed real
homework before I committed to an approach:

- **Django `GeneratedField` + GIN `tsvector` behavior** — confirming that a database-generated
  column stays in sync automatically (`GENERATED ALWAYS ... STORED`) and how `SearchQuery` /
  `SearchRank` map onto it. → fed [ADR-0002](adr/0002-postgres-fts.md).
- **Migrations: Job vs initContainer** under 2+ replicas — characterizing the race an
  initContainer creates and the hook ordering a Job needs. → fed
  [ADR-0005](adr/0005-migration-as-k8s-job.md).
- **gunicorn worker models** for a DB-bound sync app — `sync` vs `gthread` vs an ASGI rewrite.
  → fed [ADR-0003](adr/0003-gunicorn-over-asgi.md).

Each subagent came back with a synthesis; I read those, then made the call. The research was
parallelized; the **decisions were not delegated**.

### A planning bitácora / time-tracking log

Before touching code I kept a running **bitácora** (planning log): the reframe of the brief
into three pillars, the ordered list of changes, and a short rationale recorded *before* each
change — plus rough time spent per pillar. This is what the ADRs and `NOTES.md` were distilled
from. Writing the decision down before making it is what keeps an AI-assisted build honest:
the plan drives the agent, not the other way around.

### A multi-agent build

With the plan fixed, implementation ran as a small set of focused agents — one shaping the
performance changes (queryset fixes, indexes, the generated column and its migration), one on
the production surface (Dockerfile, compose, k8s, Helm, CI), and one on documentation — each
working against the same bitácora so the pieces stayed coherent. I reviewed every diff before
it landed and rejected anything that added scope the brief didn't ask for (no Redis, no async
rewrite, no auth).

### What I did **not** use

Per the tooling reference, the heavyweight features — large-scale **workflows** (dozens of
orchestrated agents) and cloud **routines / scheduled agents** — are overkill for a single
take-home, so I skipped them. Hooks and a project `CLAUDE.md`-style convention file are the
high-leverage pieces for a backend repo; the rest would have been ceremony.

---

## Human vs AI — who decided what

| Decision / artifact | Who owned it |
|---|---|
| Reframing "fix 3 bugs" into "make the prototype operable" (the thesis) | **Human** |
| Diagnosing the N+1 from the benchmark (200,001 queries) | **Human** (read the numbers), AI confirmed the mechanism |
| Choosing Postgres FTS over `pg_trgm` / Elasticsearch | **Human**, AI supplied the trade-off matrix |
| Choosing a migrate **Job** over an initContainer | **Human**, AI characterized the race |
| Choosing gunicorn `gthread` over an async rewrite | **Human**, AI compared worker models |
| Scope cuts (no auth, no Redis, no remodel) | **Human** |
| Writing the `select_related`/`prefetch_related` queryset, indexes, manifests | AI drafted, **human reviewed every line** |
| ADR / README / NOTES prose and Mermaid diagrams | AI drafted, **human edited for accuracy** |

The pattern throughout: **diagnosis and judgment are mine; expression and boilerplate were
accelerated.** Every line I kept, I read and validated.

---

## How to verify the claims

Nothing here asks for trust:

- **The performance numbers** are reproducible — `make bench` runs the same harness
  (`benchmarks/bench.py`, Django test client + `CaptureQueriesContext`) that produced
  [`benchmarks/antes.json`](../benchmarks/antes.json) and
  [`benchmarks/despues.json`](../benchmarks/despues.json).
- **The N+1 fix can't silently regress** — `test_list_posts_constant_queries_no_n_plus_one`
  pins the feed's query count in CI.
- **The decisions** are written down in [`docs/adr/`](adr/), each with the alternatives I
  rejected.
- **The prompts and session transcripts** are available on request; the representative ones
  are quoted in [NOTES.md](../NOTES.md#4-ai-assisted-development-full-transparency).
