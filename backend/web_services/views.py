import hmac

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin, IsStaffWith2FA
from payoneer.client import NOTIFICATION_HEADER
from payoneer.models import PayoneerAccount
from web_services import contract, services
from web_services.models import ExecutorProfile, OrderStatus, ServiceOrder, ServicePackage
from web_services.serializers import (
    AdminOrderSerializer,
    AdminPackageSerializer,
    DraftSerializer,
    ExecutorSerializer,
    OrderInputSerializer,
    OrderSerializer,
    PackageSerializer,
)


def client_ip(request):
    # The host nginx sets X-Real-IP; REMOTE_ADDR is the proxy otherwise.
    return request.headers.get("X-Real-IP") or request.META.get("REMOTE_ADDR")


class PublicCatalog(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        ready, reason = services.sales_state()
        return Response(
            {
                "sales_ready": ready,
                "reason": reason,
                "currency": "USD",
                "packages": PackageSerializer(
                    ServicePackage.objects.filter(is_active=True), many=True
                ).data,
            },
            headers={"Cache-Control": "no-store"},
        )


class ContractPreview(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = DraftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        document = services.draft_document(data.validated_data)
        return Response({"document": document, "checksum": contract.checksum(document)})


class Orders(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = ServiceOrder.objects.filter(user=request.user).select_related("package")[:100]
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request):
        data = OrderInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = services.create_order(
            request.user,
            data.validated_data,
            ip=client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
        )
        return Response(OrderSerializer(order).data, status=201)


class OrderDetail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(ServiceOrder, pk=pk, user=request.user)
        response = Response({**OrderSerializer(order).data, "contract": _document(order)})
        response["Cache-Control"] = "no-store, private"
        return response


class OrderPay(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(ServiceOrder, pk=pk, user=request.user)
        order = services.resume_checkout(order, getattr(request.user, "locale", "en"))
        return Response(OrderSerializer(order).data)


class OrderConfirm(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        get_object_or_404(ServiceOrder, pk=pk, user=request.user)
        return Response(OrderSerializer(services.confirm_payment(pk)).data)


def _document(order):
    document = order.contract
    document["acceptance"] = {
        "accepted_at": order.accepted_at,
        "ip": order.accepted_ip,
        "checksum": order.contract_sha256,
    }
    return document


class CheckoutNotification(APIView):
    """Payoneer status notifications; the payload is only a hint to re-query."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()

    def _handle(self, request, account_id):
        account = PayoneerAccount.objects.filter(pk=account_id).first()
        token = request.headers.get(NOTIFICATION_HEADER, "")
        if not account or not token or not hmac.compare_digest(
            token.encode(), account.notification_token_enc.encode()
        ):
            return Response(status=403)
        params = {**request.query_params.dict()}
        if hasattr(request.data, "dict"):
            params.update(request.data.dict())
        elif isinstance(request.data, dict):
            params.update({k: str(v) for k, v in request.data.items()})
        try:
            services.handle_notification(account, params)
        except APIException:
            # Payoneer retries non-2xx notifications; a later try can succeed.
            return Response(status=503)
        return Response({"received": True})

    def get(self, request, account_id):
        return self._handle(request, account_id)

    def post(self, request, account_id):
        return self._handle(request, account_id)


# --- Admin ----------------------------------------------------------------------


class AdminExecutor(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        ready, reason = services.sales_state()
        return Response(
            {**ExecutorSerializer(ExecutorProfile.load()).data, "sales_ready": ready, "reason": reason}
        )

    def put(self, request):
        serializer = ExecutorSerializer(ExecutorProfile.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        if profile.sales_enabled and not profile.complete:
            profile.sales_enabled = False
            profile.save(update_fields=["sales_enabled", "updated_at"])
            raise ValidationError("Fill in every required requisite before opening sales.")
        return self.get(request)


class AdminPackages(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        return Response(AdminPackageSerializer(ServicePackage.objects.all(), many=True).data)


class AdminPackage(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def patch(self, request, pk):
        serializer = AdminPackageSerializer(
            get_object_or_404(ServicePackage, pk=pk), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        return Response(AdminPackageSerializer(serializer.save()).data)


class AdminOrders(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        orders = ServiceOrder.objects.select_related("package", "user", "account")[:300]
        return Response(AdminOrderSerializer(orders, many=True).data)


class StatusInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    admin_note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class AdminOrder(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request, pk):
        order = get_object_or_404(ServiceOrder.objects.select_related("package", "user", "account"), pk=pk)
        services.audit("contract_viewed", order, request.user)
        response = Response({**AdminOrderSerializer(order).data, "contract": _document(order)})
        response["Cache-Control"] = "no-store, private"
        return response

    def patch(self, request, pk):
        get_object_or_404(ServiceOrder, pk=pk)
        data = StatusInput(data=request.data)
        data.is_valid(raise_exception=True)
        order = services.update_status(
            pk, data.validated_data["status"], data.validated_data.get("admin_note"), request.user
        )
        return Response(AdminOrderSerializer(order).data)


class AdminRefund(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        get_object_or_404(ServiceOrder, pk=pk)
        return Response(AdminOrderSerializer(services.refund(pk, request.user)).data)


class AdminConfirm(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        get_object_or_404(ServiceOrder, pk=pk)
        return Response(AdminOrderSerializer(services.confirm_payment(pk)).data)
