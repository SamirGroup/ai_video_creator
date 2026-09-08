from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from channels.models import AdSenseAccount, ConnectionStatus, YouTubeChannel
from core.pagination import PeriodStartCursorPagination
from core.permissions import IsFinanceOrAdmin
from providers.models import ApiUsageLog
from revenue.models import Invoice, RevenueRecord, RevenueShareStatement
from revenue.serializers import DisputeStatementSerializer, RevenueShareStatementSerializer
from revenue.services.statements import dispute_statement, finalize_statement, statement_pdf_bytes

DEFAULT_RANGE_DAYS = 30


def _date_range(request) -> tuple[date, date]:
    today = timezone.now().date()
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")
    date_from = date.fromisoformat(from_str) if from_str else today - timedelta(days=DEFAULT_RANGE_DAYS)
    date_to = date.fromisoformat(to_str) if to_str else today
    return date_from, date_to


def _revenue_source_label(user) -> str:
    """FR-20: AdSense-confirmed once connected, else a YouTube Analytics estimate."""
    connected = AdSenseAccount.objects.filter(user=user, status=ConnectionStatus.CONNECTED).exists()
    return "adsense_confirmed" if connected else "youtube_analytics_estimate"


def _zero_reason(user, qs) -> str | None:
    """FR-66: never invent a number — explain why revenue reads as zero."""
    if qs.exists():
        return None
    if not YouTubeChannel.objects.filter(user=user).exists():
        return "no_channel_connected"
    if not YouTubeChannel.objects.filter(user=user, is_monetized=True).exists():
        return "channel_not_monetized"
    return "no_synced_data_yet"


def _sum(qs, field: str):
    return qs.aggregate(total=Sum(field))["total"] or Decimal("0")


class RevenueSummaryView(APIView):
    """GET /api/v1/revenue/summary?from&to (FR-64, FR-65, FR-66)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = _date_range(request)
        base = RevenueRecord.objects.filter(user=request.user, date__gte=date_from, date__lte=date_to)
        platform = base.filter(job__isnull=False, job__is_platform_generated=True)
        other = base.filter(Q(job__isnull=True) | Q(job__is_platform_generated=False))

        def _agg(qs):
            return {
                "views": qs.aggregate(v=Sum("views"))["v"] or 0,
                "estimated_minutes_watched": qs.aggregate(v=Sum("estimated_minutes_watched"))["v"] or 0,
                "estimated_revenue": str(_sum(qs, "estimated_revenue")),
                "estimated_ad_revenue": str(_sum(qs, "estimated_ad_revenue")),
            }

        return Response(
            {
                "from": date_from,
                "to": date_to,
                "source": _revenue_source_label(request.user),
                "platform_generated": _agg(platform),
                "other_videos": _agg(other),
                "reason": _zero_reason(request.user, base),
            }
        )


class RevenueDailyView(APIView):
    """GET /api/v1/revenue/daily?from&to (FR-64)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = _date_range(request)
        rows = (
            RevenueRecord.objects.filter(
                user=request.user,
                date__gte=date_from,
                date__lte=date_to,
                job__isnull=False,
                job__is_platform_generated=True,
            )
            .values("date")
            .annotate(views=Sum("views"), estimated_revenue=Sum("estimated_revenue"))
            .order_by("date")
        )
        return Response({"source": _revenue_source_label(request.user), "days": list(rows)})


class RevenueByVideoView(APIView):
    """GET /api/v1/revenue/by-video?from&to (FR-64)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = _date_range(request)
        rows = (
            RevenueRecord.objects.filter(
                user=request.user, date__gte=date_from, date__lte=date_to, job__isnull=False
            )
            .values("job_id", "job__title", "job__is_platform_generated", "youtube_video_id")
            .annotate(views=Sum("views"), estimated_revenue=Sum("estimated_revenue"))
            .order_by("-estimated_revenue")
        )
        return Response({"source": _revenue_source_label(request.user), "videos": list(rows)})


class RevenueShareStatementListView(ListAPIView):
    """GET /api/v1/revenue/statements."""

    serializer_class = RevenueShareStatementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]
    pagination_class = PeriodStartCursorPagination

    def get_queryset(self):
        return RevenueShareStatement.objects.filter(user=self.request.user).order_by("-period_start")


class RevenueShareStatementDetailView(RetrieveAPIView):
    """GET /api/v1/revenue/statements/{id}."""

    serializer_class = RevenueShareStatementSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "statement_id"

    def get_queryset(self):
        return RevenueShareStatement.objects.filter(user=self.request.user)


def _owned_statement(user, statement_id) -> RevenueShareStatement | None:
    return (
        RevenueShareStatement.objects.select_related("user", "contract__contract_version")
        .filter(id=statement_id, user=user)
        .first()
    )


class RevenueStatementPdfView(APIView):
    """GET /api/v1/revenue/statements/{id}/pdf (FR-69)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, statement_id):
        statement = _owned_statement(request.user, statement_id)
        if statement is None:
            return Response({"detail": "Statement not found."}, status=status.HTTP_404_NOT_FOUND)
        response = HttpResponse(statement_pdf_bytes(statement), content_type="application/pdf")
        filename = f"statement-{statement.period_start}-{statement.period_end}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class RevenueStatementDisputeView(APIView):
    """POST /api/v1/revenue/statements/{id}/dispute (FR-69)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, statement_id):
        statement = RevenueShareStatement.objects.filter(id=statement_id, user=request.user).first()
        if statement is None:
            return Response({"detail": "Statement not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = DisputeStatementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        statement = dispute_statement(request.user, statement, serializer.validated_data["reason"], request=request)
        return Response(RevenueShareStatementSerializer(statement).data)


# ---------------------------------------------------------------------------
# Admin / finance (FR-82) — everything below is IsFinanceOrAdmin
# ---------------------------------------------------------------------------
class AdminFinanceOverviewView(APIView):
    """GET /api/v1/admin/finance/overview (FR-82)."""

    permission_classes = [IsFinanceOrAdmin]

    def get(self, request):
        from billing.models import Subscription, SubscriptionStatus

        active_subs = Subscription.objects.filter(status=SubscriptionStatus.ACTIVE).select_related("plan")
        mrr = Decimal("0")
        plan_distribution: dict[str, int] = {}
        for sub in active_subs:
            monthly_price = sub.plan.price_amount
            if sub.plan.billing_interval == "six_months":
                monthly_price = monthly_price / 6
            mrr += monthly_price
            plan_distribution[sub.plan.code] = plan_distribution.get(sub.plan.code, 0) + 1

        revenue_share_total = _sum(RevenueShareStatement.objects.all(), "platform_share_amount")
        uncollected = _sum(
            Invoice.objects.filter(status__in=["open", "failed", "uncollectible"]), "amount"
        )
        ai_cost_total = _sum(ApiUsageLog.objects.all(), "cost_usd")

        return Response(
            {
                "mrr_usd": str(mrr.quantize(Decimal("0.01"))),
                "active_subscriptions": active_subs.count(),
                "plan_distribution": plan_distribution,
                "revenue_share_platform_total_usd": str(revenue_share_total),
                "uncollected_invoices_usd": str(uncollected),
                "ai_provider_cost_total_usd": str(ai_cost_total),
            }
        )


class AdminFinanceStatementsView(ListAPIView):
    """GET /api/v1/admin/finance/statements (FR-82)."""

    serializer_class = RevenueShareStatementSerializer
    permission_classes = [IsFinanceOrAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "user"]
    pagination_class = PeriodStartCursorPagination

    def get_queryset(self):
        return RevenueShareStatement.objects.all().order_by("-period_start")


class AdminFinanceStatementFinalizeView(APIView):
    """POST /api/v1/admin/finance/statements/{id}/finalize (FR-67)."""

    permission_classes = [IsFinanceOrAdmin]

    def post(self, request, statement_id):
        statement = RevenueShareStatement.objects.filter(id=statement_id).first()
        if statement is None:
            return Response({"detail": "Statement not found."}, status=status.HTTP_404_NOT_FOUND)
        statement = finalize_statement(request.user, statement, request=request)
        return Response(RevenueShareStatementSerializer(statement).data)


class AdminFinanceExportView(APIView):
    """GET /api/v1/admin/finance/export?from&to (FR-73). CSV only for MVP —
    the FR asks for "CSV/XLSX"; a dependency-free CSV covers the requirement
    without adding openpyxl to requirements.txt.
    """

    permission_classes = [IsFinanceOrAdmin]

    def get(self, request):
        import csv
        import io

        date_from, date_to = _date_range(request)
        qs = RevenueShareStatement.objects.filter(
            period_start__gte=date_from, period_end__lte=date_to
        ).select_related("user").order_by("user__email", "period_start")

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "user_email",
                "period_start",
                "period_end",
                "currency",
                "gross_revenue",
                "platform_share_amount",
                "creator_share_amount",
                "video_count",
                "status",
            ]
        )
        for statement in qs:
            writer.writerow(
                [
                    statement.user.email,
                    statement.period_start,
                    statement.period_end,
                    statement.currency,
                    statement.gross_revenue,
                    statement.platform_share_amount,
                    statement.creator_share_amount,
                    statement.video_count,
                    statement.status,
                ]
            )

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="finance-export-{date_from}-{date_to}.csv"'
        return response
