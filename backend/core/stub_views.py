"""Generic stub endpoint used to publish the full SPEC 6 URL surface before an
endpoint's business logic is implemented. Returns a clear, machine-readable
501 instead of a 404, so the frontend/API consumers can tell "not built yet"
apart from "wrong URL". Replace with a real view as each feature is built.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class NotImplementedStubView(APIView):
    """Set `feature_name` on subclasses/as_view(feature_name=...) for a clear message."""

    permission_classes = [IsAuthenticated]
    feature_name = "this endpoint"

    def _stub_response(self, request, *args, **kwargs):
        return Response(
            {"detail": f"{self.feature_name} is not implemented yet."},
            status=501,
        )

    get = _stub_response
    post = _stub_response
    patch = _stub_response
    put = _stub_response
    delete = _stub_response
