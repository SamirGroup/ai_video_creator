"""Shared `CursorPagination` subclasses.

`REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` is `rest_framework.pagination.
CursorPagination`, whose `ordering` defaults to `"-created"` — a field that
does not exist on any model in this project (`TimestampedModel` names it
`created_at`). DRF reads `ordering` from the **pagination class itself**
(`self.ordering` inside `CursorPagination.paginate_queryset`), not from the
view, so every `ListAPIView` that pages a non-default-ordered queryset must
set `pagination_class` to one of these instead of trying to override
`ordering` on the view (which DRF silently ignores).
"""
from __future__ import annotations

from rest_framework.pagination import CursorPagination


class CreatedAtCursorPagination(CursorPagination):
    ordering = "-created_at"


class UpdatedAtCursorPagination(CursorPagination):
    ordering = "-updated_at"


class StartedAtCursorPagination(CursorPagination):
    ordering = "-started_at"


class PeriodStartCursorPagination(CursorPagination):
    ordering = "-period_start"


class SortOrderCursorPagination(CursorPagination):
    ordering = "sort_order"


class ServicePriorityCursorPagination(CursorPagination):
    ordering = ("service", "priority")
