"""
Health checks separados, como espera un orquestador (K8s):

  /healthz  liveness  — ¿el proceso está vivo? No toca I/O. Si falla, K8s reinicia el pod.
  /readyz   readiness — ¿puede atender tráfico? Verifica la DB. Si falla, K8s lo saca
                        del balanceador pero NO lo reinicia (puede ser un blip de la DB).
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
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de DB => no listo
        return JsonResponse({"status": "unavailable", "detail": str(exc)}, status=503)
    return JsonResponse({"status": "ready"})
