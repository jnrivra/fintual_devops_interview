# syntax=docker/dockerfile:1.7
###############################################################################
# Multi-stage image for the Fintual content service (Django 5.2 + django-ninja).
#
# Pattern follows Astral's official uv Docker guide:
#   - copy the `uv` binary from Astral's published image (no pip bootstrap)
#   - install dependencies in a layer separate from app source (cache-friendly)
#   - `uv sync --locked` so a stale uv.lock fails the build (a feature, not a bug)
#   - `--no-editable` so only the resolved `.venv` needs to cross into runtime
#   - final stage is slim + non-root, ships pre-collected static via WhiteNoise
###############################################################################

###############################################################################
# Stage 1 — builder: resolve & install dependencies, collect static
###############################################################################
FROM python:3.14-slim AS builder

# Pull the uv binary straight from Astral's image. Pin by digest/tag in real life
# (e.g. ghcr.io/astral-sh/uv:0.9.5) for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 1) Install ONLY dependencies first (no project). This layer is cached until
#    uv.lock / pyproject.toml change, so editing app source won't re-resolve deps.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

# 2) Copy source and install the project itself (non-editable, into the venv).
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# 3) Collect static into the image so the runtime serves it via WhiteNoise.
#    Dummy env here — collectstatic never touches the DB.
ENV PATH="/app/.venv/bin:$PATH"
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only \
    DATABASE_URL=postgres://u:p@localhost:5432/db \
    python manage.py collectstatic --noinput

###############################################################################
# Stage 2 — runtime: slim, non-root, only the venv + app code + static
###############################################################################
FROM python:3.14-slim AS runtime

# libpq5 is needed by psycopg at runtime; curl is used by the HEALTHCHECK.
# Clean apt lists to keep the layer small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=core.settings \
    PORT=8000 \
    # gunicorn worker count; override per pod CPU via the manifests' env.
    WEB_CONCURRENCY=3

WORKDIR /app

# Copy the resolved venv, pre-collected static, and the app source from builder.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles
COPY --chown=app:app . /app

USER app
EXPOSE 8000

# In-image healthcheck (useful for docker-compose / ECS; K8s uses its own probes).
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Migrations are NOT run here — a dedicated compose step / K8s Job owns that, so
# multiple replicas never race each other applying the same migration.
# gthread workers: the blog endpoints are I/O-bound (Postgres round-trips), so
# threads overlap DB waits cheaply. --forwarded-allow-ips '*' trusts the in-cluster
# ALB/ingress X-Forwarded-* headers (paired with SECURE_PROXY_SSL_HEADER in settings).
CMD ["sh", "-c", "exec gunicorn core.wsgi:application \
     --bind 0.0.0.0:8000 \
     --workers ${WEB_CONCURRENCY:-3} \
     --worker-class gthread --threads 4 \
     --timeout 30 --graceful-timeout 30 --keep-alive 5 \
     --max-requests 1000 --max-requests-jitter 100 \
     --access-logfile - --error-logfile - \
     --forwarded-allow-ips '*'"]
