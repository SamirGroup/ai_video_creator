"""Cross-cutting middleware: request id correlation (NFR-29, API contract)."""
from __future__ import annotations

import uuid

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Attaches a correlation id to every request/response.

    Reuses an inbound `X-Request-ID` header when present (so a frontend/gateway
    generated id survives end to end), otherwise generates a fresh UUID4. The id
    is available as `request.request_id` for logging and is echoed back in the
    response header and in RFC 7807 error bodies (core.exceptions).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request.request_id = incoming if incoming else str(uuid.uuid4())
        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request.request_id
        return response
