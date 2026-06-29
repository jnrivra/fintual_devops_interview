"""
Separate health checks, as an orchestrator (K8s) expects:

  /healthz  liveness  — is the process alive? No I/O. If it fails, K8s restarts the pod.
  /readyz   readiness — can it serve traffic? Checks the DB. If it fails, K8s pulls it
                        from the load balancer but does NOT restart it (could be a DB blip).
"""

from django.db import connection
from django.http import JsonResponse


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - any DB failure => not ready
        return JsonResponse({"status": "unavailable", "detail": str(exc)}, status=503)
    return JsonResponse({"status": "ready"})
