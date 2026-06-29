# ADR-0005: Run database migrations as a run-to-completion Job, not an initContainer

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** J. Rivera

## Context and problem statement

Schema migrations must be applied exactly once per deploy, **before** the new application
pods start serving. The deployment runs 2+ replicas (and scales further under the HPA). Where
should `manage.py migrate` run so that migrations are applied once, atomically, and ordered
ahead of the rollout — without multiple replicas racing the same schema change?

## Decision drivers

- Migrations run **exactly once** per deploy, not once per replica.
- Migrations complete **before** the new pods take traffic.
- The mechanism works under both `kubectl apply` and GitOps (ArgoCD).

## Considered options

1. **initContainer on the Deployment** — runs `migrate` on every pod.
2. **A run-to-completion `Job`**, ordered ahead of the rollout via deploy hooks.
3. **Manual / ad-hoc `kubectl exec`** before each deploy.

## Decision outcome

**Chosen: a run-to-completion `Job`.** An initContainer runs on **every** replica, so with
2+ pods (or an HPA scale-up) you get N concurrent `migrate` processes racing the same schema.
A single Job runs migrations **once**. Ordering is enforced by hooks: in raw manifests
(`k8s/migrate-job.yaml`) via the ArgoCD `PreSync` hook; in the Helm chart
(`helm/templates/migrate-job.yaml`) via both the Helm native `pre-upgrade,pre-install` hook
(weight `-5`) **and** the ArgoCD `PreSync` hook, with a release-revision suffix giving each
deploy a fresh, immutable Job name. `backoffLimit: 3`, `restartPolicy: Never`, and
`ttlSecondsAfterFinished: 600` auto-clean finished Jobs. (An initContainer is fine only for a
single-replica app or as a pure "wait-for-db" gate.)

### Consequences

- 🟢 **Good:** migrations apply exactly once and finish before the new ReplicaSet rolls;
  no cross-replica races; works under both `kubectl apply` and ArgoCD.
- 🟢 **Good:** the same image and config (`envFrom` ConfigMap + Secret) run the migration, so
  there is no drift between the migrate step and the app.
- 🟡 **Neutral / trade-off:** a failed migration Job blocks the rollout — which is the
  correct, fail-closed behavior, but it means deploys depend on the Job succeeding.
- 🔴 **Risk / follow-up:** the app must tolerate running briefly against a not-yet-migrated
  schema during a rollout. Standard mitigation is the expand/contract (additive-first)
  migration discipline: add nullable columns, backfill, then constrain in a later release.
