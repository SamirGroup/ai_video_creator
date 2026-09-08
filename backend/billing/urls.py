from django.urls import path

from billing import views
from core.stub_views import NotImplementedStubView

app_name = "billing"

urlpatterns = [
    path("plans", views.PlanListView.as_view(), name="plan-list"),
    path("me/subscription", views.MySubscriptionView.as_view(), name="my-subscription"),
    path("billing/checkout-session", views.CheckoutSessionView.as_view(), name="checkout-session"),
    path("billing/portal-session", views.PortalSessionView.as_view(), name="portal-session"),
    # --- Track A ---
    path("billing/setup-intent", views.SetupIntentView.as_view(), name="setup-intent"),
    path("me/quota", views.MyQuotaView.as_view(), name="my-quota"),
    path(
        "invoices",
        NotImplementedStubView.as_view(feature_name="invoice listing (5.18)"),
        name="invoice-list",
    ),
    path(
        "invoices/<uuid:invoice_id>/pdf",
        NotImplementedStubView.as_view(feature_name="invoice PDF download"),
        name="invoice-pdf",
    ),
    path("webhooks/stripe", views.StripeWebhookView.as_view(), name="stripe-webhook"),
]
