"""RFC 7807 (application/problem+json) exception handling for the whole API
(SPEC section 6: "RFC 7807 application/problem+json xato formati").
"""
from __future__ import annotations

import logging
import uuid

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_exception_handler

logger = logging.getLogger("api.errors")

_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_FAILED",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "BUSINESS_RULE_VIOLATION",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    status.HTTP_501_NOT_IMPLEMENTED: "NOT_IMPLEMENTED",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}

_TITLES = {
    status.HTTP_400_BAD_REQUEST: "Bad Request",
    status.HTTP_401_UNAUTHORIZED: "Unauthorized",
    status.HTTP_403_FORBIDDEN: "Forbidden",
    status.HTTP_404_NOT_FOUND: "Not Found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Method Not Allowed",
    status.HTTP_409_CONFLICT: "Conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "Unprocessable Entity",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too Many Requests",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal Server Error",
    status.HTTP_501_NOT_IMPLEMENTED: "Not Implemented",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Service Unavailable",
}


def _extract_detail(response_data) -> str:
    if isinstance(response_data, dict) and "detail" in response_data:
        return str(response_data["detail"])
    if isinstance(response_data, list) and response_data:
        return str(response_data[0])
    return "Request could not be processed."


def rfc7807_exception_handler(exc, context):
    """DRF `EXCEPTION_HANDLER`: turns any exception into an RFC 7807 problem+json body.

    Never leaks raw exception text/stack traces to the client (only DRF-recognized
    exceptions produce a message; anything else becomes a generic 500 message while
    the real exception is still logged server-side with the request id for triage).
    """
    request = context.get("request")
    request_id = getattr(request, "request_id", None) or str(uuid.uuid4())

    response = drf_default_exception_handler(exc, context)

    if response is None:
        if isinstance(exc, Http404):
            response = Response(status=status.HTTP_404_NOT_FOUND)
        elif isinstance(exc, PermissionDenied):
            response = Response(status=status.HTTP_403_FORBIDDEN)
        else:
            logger.exception(
                "unhandled_exception",
                extra={"request_id": request_id, "path": getattr(request, "path", None)},
            )
            response = Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            response.data = {"detail": "Internal server error."}

    status_code = response.status_code
    errors = None
    if isinstance(response.data, dict) and set(response.data.keys()) - {"detail"}:
        errors = response.data

    problem = {
        "type": "about:blank",
        "title": _TITLES.get(status_code, "Error"),
        "status": status_code,
        "detail": _extract_detail(response.data),
        "code": getattr(exc, "default_code", None) or _ERROR_CODES.get(status_code, "ERROR"),
        "request_id": request_id,
    }
    if errors:
        problem["errors"] = errors

    response.data = problem
    response.content_type = "application/problem+json"
    return response
