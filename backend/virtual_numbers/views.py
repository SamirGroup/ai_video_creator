import hashlib
import hmac
import time

import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin, IsStaffWith2FA
from virtual_numbers import services
from virtual_numbers.gateways import payment_methods, paypal
from virtual_numbers.models import NumberOffer, NumberOrder, PhoneNumber
from virtual_numbers.serializers import (
    AdminOfferSerializer,
    InventorySerializer,
    OfferSerializer,
    OrderSerializer,
    PurchaseSerializer,
    RefundSerializer,
    SMSSerializer,
)


class Catalog(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "sales_ready": services.integration_ready(),
                "payment_methods": payment_methods(),
                "terms_version": services.TERMS_VERSION,
                "offers": OfferSerializer(
                    NumberOffer.objects.filter(is_visible=True), many=True
                ).data,
            }
        )


class Orders(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = NumberOrder.objects.filter(user=request.user).select_related("phone")[
            :100
        ]
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request):
        serializer = PurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = services.start_checkout(
                request.user,
                serializer.validated_data["offer_id"],
                serializer.validated_data["request_key"],
                payment_provider=serializer.validated_data["payment_provider"],
                quoted_total=serializer.validated_data["quoted_total"],
            )
        except stripe.error.StripeError:
            return Response(
                {
                    "detail": "Payment provider is temporarily unavailable. Retry the same order."
                },
                status=502,
            )
        return Response(OrderSerializer(order).data, status=201)


class Inbox(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(NumberOrder, pk=pk, user=request.user)
        response = Response([])
        if (
            order.status in ("active", "refund_requested")
            and order.expires_at
            and order.expires_at > timezone.now()
        ):
            response = Response(
                [
                    {
                        "id": m.pk,
                        "sender": m.sender_enc,
                        "body": m.body_enc,
                        "received_at": m.received_at,
                    }
                    for m in order.messages.filter(delete_after__gt=timezone.now())[
                        :100
                    ]
                ]
            )
        response["Cache-Control"] = "no-store, private"
        return response


class RefundRequest(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        get_object_or_404(NumberOrder, pk=pk, user=request.user)
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            OrderSerializer(
                services.request_refund(
                    pk, request.user, serializer.validated_data["reason"]
                )
            ).data
        )


class AdminOffers(generics.ListCreateAPIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]
    serializer_class = AdminOfferSerializer
    queryset = NumberOffer.objects.all()
    pagination_class = None

    def perform_create(self, serializer):
        services.audit("offer_created", serializer.save(), self.request.user)


class AdminOffer(generics.UpdateAPIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]
    serializer_class = AdminOfferSerializer
    queryset = NumberOffer.objects.all()

    def perform_update(self, serializer):
        services.audit("offer_updated", serializer.save(), self.request.user)


class AdminInventory(generics.ListCreateAPIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]
    serializer_class = InventorySerializer
    queryset = PhoneNumber.objects.order_by("-created_at")

    def perform_create(self, serializer):
        services.audit("inventory_added", serializer.save(), self.request.user)


class AdminOrders(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        services.record_audit_event(
            actor_type="user",
            actor_id=request.user.pk,
            action="virtual_numbers.orders_read",
            resource_type="NumberOrder",
            resource_id="list",
        )
        return Response(
            [
                {**OrderSerializer(o).data, "user_id": str(o.user_id)}
                for o in NumberOrder.objects.select_related("phone")[:100]
            ]
        )

    def post(self, request, pk):
        get_object_or_404(NumberOrder, pk=pk)
        try:
            return Response(
                OrderSerializer(services.refund_order(pk, request.user)).data
            )
        except stripe.error.StripeError:
            return Response(
                {"detail": "Refund could not be confirmed. Retry reconciliation."},
                status=502,
            )


class StripeWebhook(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        secret = settings.VIRTUAL_NUMBERS_STRIPE_WEBHOOK_SECRET
        if not secret:
            return Response(status=503)
        try:
            event = stripe.Webhook.construct_event(
                request.body, request.headers.get("Stripe-Signature", ""), secret
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            return Response(status=400)
        try:
            services.process_payment(event.to_dict())
        except ValidationError:
            return Response({"detail": "Payment requires reconciliation."}, status=409)
        return Response({"received": True})


class SMSIngress(APIView):
    """Connector-only HMAC endpoint; provider-native callbacks require a connector."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        secret = settings.VIRTUAL_NUMBERS_INGRESS_SECRET
        if not secret:
            return Response(status=503)
        stamp = request.headers.get("X-SMS-Timestamp", "")
        try:
            fresh = abs(time.time() - int(stamp)) <= 300
        except ValueError:
            fresh = False
        if not fresh or len(request.body) > 16384:
            return Response(status=403)
        expected = hmac.new(
            secret.encode(), stamp.encode() + b"." + request.body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(
            expected, request.headers.get("X-SMS-Signature", "")
        ):
            return Response(status=403)
        serializer = SMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.receive_sms(serializer.validated_data)
        return Response({"received": True})


class PayPalCapture(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        get_object_or_404(
            NumberOrder, pk=pk, user=request.user, payment_provider="paypal"
        )
        order = services.complete_paypal_order(pk, user=request.user)
        return Response(OrderSerializer(order).data)


class PayPalWebhook(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        if not settings.PAYPAL_WEBHOOK_ID:
            return Response(status=503)
        if not isinstance(request.data, dict) or not paypal.verify_webhook(
            request.data, request.headers
        ):
            return Response(status=403)
        services.process_paypal_event(request.data)
        return Response({"received": True})


class PaymentReadiness(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        return Response(
            {
                "scope": "virtual_number_rentals",
                "payment_methods": payment_methods(),
                "sales_ready": services.integration_ready(),
                "allpay_requirements": [
                    "Merchant agreement and country eligibility",
                    "Hosted checkout transaction reference and currency specification",
                    "Native notification HMAC specification",
                    "Refund and settlement API documentation",
                    "Sandbox and approved domain",
                ],
            }
        )


class PricePreview(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        from rest_framework import serializers

        from virtual_numbers.pricing import quote

        base = serializers.DecimalField(
            max_digits=8, decimal_places=2, min_value=1
        ).run_validation(request.query_params.get("base_cost_usd"))
        basis = serializers.ChoiceField(choices=["base", "subtotal"]).run_validation(
            request.query_params.get("tax_basis", "base")
        )
        return Response(quote(base, basis))
