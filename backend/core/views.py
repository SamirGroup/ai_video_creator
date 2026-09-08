"""System health endpoints (SPEC 6, "System" group: /health/live, /health/ready).

Liveness only proves the process is up and serving requests. Readiness also
checks the dependencies the API actually needs per request (DB, cache) so an
orchestrator/load-balancer can pull an instance out of rotation before it
starts failing real traffic.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db import connections
from django.db.utils import Error as DjangoDBError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _check_database() -> bool:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except DjangoDBError:
        return False


def _check_cache() -> bool:
    try:
        probe_key = "health:ready:probe"
        cache.set(probe_key, "1", timeout=5)
        return cache.get(probe_key) == "1"
    except Exception:
        return False


@api_view(["GET"])
@permission_classes([AllowAny])
def health_live(request):
    """Process is up. Does not touch the DB/cache — always fast."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(request):
    """Process AND its dependencies are ready to serve real traffic."""
    checks = {"database": _check_database(), "cache": _check_cache()}
    healthy = all(checks.values())
    return Response(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# ---------------------------------------------------------------------------
# Local-storage signed media (dev/test only — S3 presigned URLs in production)
# ---------------------------------------------------------------------------
def serve_local_media(request):
    """Serves a file from `LocalFileStorage` behind a signed, time-limited token
    (NFR-7 equivalent of an S3 presigned URL for the no-S3 dev/test setup).
    404s when the S3 backend is active so it can never become a bypass.
    """
    from django.http import FileResponse, Http404, HttpResponseForbidden

    from core.storage import LocalFileStorage, get_storage

    storage = get_storage()
    if not isinstance(storage, LocalFileStorage):
        raise Http404()
    token = request.GET.get("token", "")
    try:
        ttl = int(request.GET.get("ttl", "0"))
    except ValueError:
        ttl = 0
    if not token or ttl <= 0:
        return HttpResponseForbidden("Missing media token.")
    try:
        path = storage.resolve_signed_token(token, ttl)
    except PermissionError:
        return HttpResponseForbidden("Invalid or expired media token.")
    if not path.is_file():
        raise Http404()
    return FileResponse(open(path, "rb"), as_attachment=False, filename=path.name)
