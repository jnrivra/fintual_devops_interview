"""
Observability: request_id correlation across logs, metrics and traces.

A single id per request (X-Request-ID) that:
  - is read from the incoming header if it comes from a proxy/client, or generated,
  - is made available to every log via a contextvar,
  - is returned in the response so the caller can trace their request.
"""

import logging
import uuid
from contextvars import ContextVar

# contextvar: visible from any log of the same request without passing the id by hand.
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
    """Injects request_id into every log record so the JSON includes it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True
