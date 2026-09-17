from django.urls import path

from revenue import views
from revenue.settlements import SettlementView

app_name = "revenue"

urlpatterns = [
    path("admin/finance/settlements", SettlementView.as_view(), name="settlements"),
    path("revenue/summary", views.RevenueSummaryView.as_view(), name="summary"),
    path("revenue/daily", views.RevenueDailyView.as_view(), name="daily"),
    path("revenue/by-video", views.RevenueByVideoView.as_view(), name="by-video"),
    path(
        "revenue/statements",
        views.RevenueShareStatementListView.as_view(),
        name="statements",
    ),
    path(
        "revenue/statements/<uuid:statement_id>",
        views.RevenueShareStatementDetailView.as_view(),
        name="statement-detail",
    ),
    path(
        "revenue/statements/<uuid:statement_id>/pdf",
        views.RevenueStatementPdfView.as_view(),
        name="statement-pdf",
    ),
    path(
        "revenue/statements/<uuid:statement_id>/dispute",
        views.RevenueStatementDisputeView.as_view(),
        name="statement-dispute",
    ),
    path(
        "admin/finance/overview",
        views.AdminFinanceOverviewView.as_view(),
        name="admin-finance-overview",
    ),
    path(
        "admin/finance/statements",
        views.AdminFinanceStatementsView.as_view(),
        name="admin-finance-statements",
    ),
    path(
        "admin/finance/statements/<uuid:statement_id>/finalize",
        views.AdminFinanceStatementFinalizeView.as_view(),
        name="admin-finance-statement-finalize",
    ),
    path(
        "admin/finance/export",
        views.AdminFinanceExportView.as_view(),
        name="admin-finance-export",
    ),
]
