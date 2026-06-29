"""
Observabilidad: correlación de request_id entre logs, métricas y trazas.

Un solo id por request (X-Request-ID) que:
  - se lee del header entrante si viene de un proxy/cliente, o se genera,
  - queda disponible para todos los logs vía un contextvar,
  - se devuelve en la respuesta para que el caller pueda rastrear su request.
"""

import logging
import uuid
from contextvars import ContextVar

# contextvar: visible desde cualquier log de la misma request sin pasar el id a mano.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex
        request.request_id = rid
        token = _request_id.set(rid)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response["X-Request-ID"] = rid
        return response


class RequestIDLogFilter(logging.Filter):
    """Inyecta request_id en cada registro de log para que el JSON lo incluya."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True
