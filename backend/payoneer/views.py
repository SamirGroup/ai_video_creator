import uuid

from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdmin, IsFinanceOrAdmin, IsStaffWith2FA
from payoneer import services
from payoneer.models import PayoneerAccount, PayoneerPayee, PayoneerPayout
from payoneer.serializers import AccountSerializer, PayeeSerializer, PayoutSerializer


class Accounts(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        return Response(AccountSerializer(PayoneerAccount.objects.all(), many=True).data)

    def post(self, request):
        serializer = AccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = services.save_account(serializer, request.user)
        return Response(AccountSerializer(account).data, status=201)


class Account(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def patch(self, request, pk):
        serializer = AccountSerializer(
            get_object_or_404(PayoneerAccount, pk=pk), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        return Response(AccountSerializer(services.save_account(serializer, request.user)).data)

    def delete(self, request, pk):
        account = get_object_or_404(PayoneerAccount, pk=pk)
        try:
            account.delete()
        except ProtectedError:
            # Orders and payouts keep pointing at the account that handled them.
            account.is_active = False
            account.is_default_checkout = account.is_default_payouts = False
            account.save()
            services.audit("account_deactivated", account, request.user)
            return Response(AccountSerializer(account).data)
        return Response(status=204)


class AccountCheck(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        account = get_object_or_404(PayoneerAccount, pk=pk)
        return Response(AccountSerializer(services.check_account(account, request.user)).data)


class Payees(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def get(self, request):
        payees = PayoneerPayee.objects.select_related("account", "user")[:500]
        return Response(PayeeSerializer(payees, many=True).data)

    def post(self, request):
        serializer = PayeeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data.pop("user_id", None)
        payee = serializer.save(user_id=user_id, payee_id=f"cai{uuid.uuid4().hex[:24]}")
        services.audit("payee_created", payee, request.user)
        return Response(PayeeSerializer(payee).data, status=201)


class PayeeInvite(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        payee = get_object_or_404(PayoneerPayee.objects.select_related("account"), pk=pk)
        return Response({"registration_link": services.invite_payee(payee, request.user)})


class PayeeRefresh(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        payee = get_object_or_404(PayoneerPayee.objects.select_related("account"), pk=pk)
        return Response(PayeeSerializer(services.refresh_payee(payee)).data)


class PayoutInput(serializers.Serializer):
    payee = serializers.PrimaryKeyRelatedField(queryset=PayoneerPayee.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    description = serializers.CharField(min_length=3, max_length=200)


class Payouts(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def get(self, request):
        payouts = PayoneerPayout.objects.select_related("account", "payee")[:500]
        return Response(PayoutSerializer(payouts, many=True).data)

    def post(self, request):
        data = PayoutInput(data=request.data)
        data.is_valid(raise_exception=True)
        payout = services.create_payout(
            data.validated_data["payee"],
            data.validated_data["amount"],
            data.validated_data["description"],
            request.user,
        )
        return Response(PayoutSerializer(payout).data, status=201)


class PayoutSubmit(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        get_object_or_404(PayoneerPayout, pk=pk)
        return Response(PayoutSerializer(services.submit_payout(pk, request.user)).data)


class PayoutRefresh(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def post(self, request, pk):
        payout = get_object_or_404(PayoneerPayout.objects.select_related("account"), pk=pk)
        return Response(PayoutSerializer(services.refresh_payout(payout)).data)
