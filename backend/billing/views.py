from __future__ import annotations

import logging

import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing import services
from billing.models import Plan, Subscription
from billing.serializers import PlanSerializer, SubscriptionSerializer
from core.pagination import SortOrderCursorPagination

logger = logging.getLogger("billing.views")


class PlanListView(ListAPIView):
    """GET /api/v1/plans — public pricing table."""

    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    pagination_class = SortOrderCursorPagination
    queryset = Plan.objects.filter(is_active=True).order_by("sort_order")


class MySubscriptionView(APIView):
    """GET /api/v1/me/subscription."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = (
            Subscription.objects.filter(user=request.user)
            .select_related("plan")
            .first()
        )
        if subscription is None:
            return Response({"detail": "No active subscription."}, status=404)
        return Response(SubscriptionSerializer(subscription).data)


class CheckoutSessionView(APIView):
    """POST /api/v1/billing/checkout-session (FR-22).

    Body: {"plan_code": "starter", "success_url"?: str, "cancel_url"?: str}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_code = request.data.get("plan_code")
        plan = Plan.objects.filter(code=plan_code, is_active=True).first()
        if plan is None:
            return Response(
                {"detail": "Unknown or inactive plan."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not plan.stripe_price_id and not plan.ai_budget_enabled:
            return Response(
                {"detail": "This plan has no Stripe price configured yet."},
                status=status.HTTP_409_CONFLICT,
            )

        success_url = request.data.get("success_url") or (
            f"{settings.FRONTEND_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
        )
        cancel_url = (
            request.data.get("cancel_url")
            or f"{settings.FRONTEND_BASE_URL}/billing/cancel"
        )

        try:
            session = services.create_checkout_session(
                user=request.user,
                plan=plan,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except stripe.error.StripeError as exc:
            logger.error("stripe_checkout_session_failed", extra={"error": str(exc)})
            return Response(
                {"detail": "Could not start checkout session."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"checkout_url": session.url, "session_id": session.id},
            status=status.HTTP_201_CREATED,
        )


class PortalSessionView(APIView):
    """POST /api/v1/billing/portal-session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return_url = (
            request.data.get("return_url") or f"{settings.FRONTEND_BASE_URL}/billing"
        )
        try:
            session = services.create_portal_session(
                user=request.user, return_url=return_url
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except stripe.error.StripeError as exc:
            logger.error("stripe_portal_session_failed", extra={"error": str(exc)})
            return Response(
                {"detail": "Could not start billing portal session."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"portal_url": session.url})


class StripeWebhookView(APIView):
    """POST /api/v1/webhooks/stripe (FR-25, NFR-5, AC-8).

    Signature verification is mandatory: an invalid/missing signature returns
    400 without touching any state. Valid events are persisted keyed by
    `event_id` before dispatch, so Stripe's at-least-once retries are
    idempotent no-ops on replay.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = services.construct_stripe_event(request.body, sig_header)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            logger.warning(
                "stripe_webhook_signature_invalid", extra={"error": str(exc)}
            )
            return Response(
                {"detail": "Invalid payload or signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            services.record_and_dispatch_webhook_event(event)
        except Exception:  # noqa: BLE001 — handler failure: 500 so Stripe retries; event_id makes retry safe
            return Response(
                {"detail": "Webhook handler failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)


# --- Track A ---------------------------------------------------------------
class SetupIntentView(APIView):
    """POST /api/v1/billing/setup-intent (FR-70a).

    Returns `{"client_secret", "setup_intent_id", "customer_id"}` for the
    frontend's Stripe Elements `confirmSetup`. The saved payment method is
    recorded when Stripe sends `setup_intent.succeeded`.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            intent = services.create_setup_intent(user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except stripe.error.StripeError as exc:
            logger.error("stripe_setup_intent_failed", extra={"error": str(exc)})
            return Response(
                {"detail": "Could not create payment setup."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "client_secret": intent.client_secret,
                "setup_intent_id": intent.id,
                "customer_id": intent.customer,
            },
            status=status.HTTP_201_CREATED,
        )


class MyQuotaView(APIView):
    """GET /api/v1/me/quota — FR-23 live quota snapshot (used by the dashboard upgrade hint)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from billing.quota import remaining

        return Response(remaining(request.user).as_dict())


class PaymentSetupCheckoutView(APIView):
    """Stripe-hosted card setup. A webhook, never the return URL, confirms the saved method."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            session = services.create_payment_setup_checkout(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        except stripe.error.StripeError:
            return Response(
                {"detail": "Payment provider is unavailable or not configured."},
                status=502,
            )
        return Response({"checkout_url": session.url}, status=201)
