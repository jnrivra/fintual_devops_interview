#!/usr/bin/env python
"""
Medidor de performance por endpoint — cuenta queries SQL y mide latencia.
El mismo harness para el ANTES y el DESPUÉS, así los números son comparables.

Uso:  uv run python benchmarks/bench.py [--json salida.json] [--label antes]

No necesita servidor corriendo: usa el test client de Django en proceso y
CaptureQueriesContext para contar exactamente cuántas consultas dispara cada endpoint.
"""

import argparse
import json
import os
import statistics
import sys
import time

# permitir importar el proyecto (core, blog) corriendo desde benchmarks/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.db import connection, reset_queries  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from blog.models import Post, Tag, User  # noqa: E402


def pick_fixtures():
    """Toma ids/slugs reales de la DB para los endpoints que los necesitan."""
    post = Post.objects.filter(is_published=True).order_by("-created_at").first()
    tag = Tag.objects.first()
    user = User.objects.first()
    return {
        "post_id": post.id if post else 1,
        "tag_slug": tag.slug if tag else "x",
        "user_id": user.id if user else 1,
        "user_email": user.email if user else "x@x.com",
    }


def measure(client, method, path, runs=3):
    """Devuelve (n_queries, ms_mediana, status) corriendo el endpoint varias veces."""
    times = []
    nq = 0
    status = None
    for _ in range(runs):
        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            t0 = time.perf_counter()
            resp = client.get(path)
            dt = (time.perf_counter() - t0) * 1000
        times.append(dt)
        nq = len(ctx.captured_queries)
        status = resp.status_code
    return nq, statistics.median(times), status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="ruta para guardar resultados en JSON")
    ap.add_argument("--label", default="run", help="etiqueta del run (ej. antes/despues)")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    fx = pick_fixtures()
    client = Client()

    endpoints = [
        ("GET", "/api/posts"),
        ("GET", "/api/posts/search?q=time"),
        ("GET", f"/api/posts/by-tag/{fx['tag_slug']}"),
        ("GET", f"/api/posts/{fx['post_id']}"),
        ("GET", f"/api/users/{fx['user_id']}"),
        ("GET", f"/api/users/find?email={fx['user_email']}"),
    ]

    print(f"\n{'=' * 72}\n  BENCHMARK [{args.label}]  ·  {fx}\n{'=' * 72}")
    print(f"  {'endpoint':<34}{'queries':>9}{'mediana ms':>14}{'status':>9}")
    print(f"  {'-' * 64}")
    results = []
    for method, path in endpoints:
        nq, ms, status = measure(client, method, path, args.runs)
        flag = "  🔴" if (nq > 20 or ms > 200) else ""
        print(f"  {path:<34}{nq:>9}{ms:>13.1f}{status:>9}{flag}")
        results.append({"endpoint": path, "queries": nq, "ms": round(ms, 1), "status": status})
    print(f"{'=' * 72}\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"label": args.label, "fixtures": fx, "results": results}, f, indent=2)
        print(f"  guardado en {args.json}")


if __name__ == "__main__":
    main()
