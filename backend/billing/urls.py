from django.urls import path

from billing import views
from billing.model_catalog import ModelCatalogView
from revenue.views import InvoiceListView, InvoicePdfView

app_name = "billing"

urlpatterns = [
    path("video-models", ModelCatalogView.as_view()),
    path(
        "billing/payment-setup",
        views.PaymentSetupCheckoutView.as_view(),
        name="payment-setup",
    ),
    path("plans", views.PlanListView.as_view(), name="plan-list"),
    path("me/subscription", views.MySubscriptionView.as_view(), name="my-subscription"),
    path(
        "billing/checkout-session",
        views.CheckoutSessionView.as_view(),
        name="checkout-session",
    ),
    path(
        "billing/portal-session",
        views.PortalSessionView.as_view(),
        name="portal-session",
    ),
    # --- Track A ---
    path("billing/setup-intent", views.SetupIntentView.as_view(), name="setup-intent"),
    path("me/quota", views.MyQuotaView.as_view(), name="my-quota"),
    path(
        "invoices",
        InvoiceListView.as_view(),
        name="invoice-list",
    ),
    path(
        "invoices/<uuid:invoice_id>/pdf",
        InvoicePdfView.as_view(),
        name="invoice-pdf",
    ),
    path("webhooks/stripe", views.StripeWebhookView.as_view(), name="stripe-webhook"),
]
