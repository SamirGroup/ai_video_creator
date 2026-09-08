from __future__ import annotations

from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts import services
from contracts.models import Contract, ContractVersion
from contracts.serializers import ContractSerializer, CurrentContractSerializer, SignContractSerializer


class CurrentContractView(APIView):
    """GET /api/v1/contracts/current (FR-28, FR-70a)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = services.get_current_state(request.user)
        data = CurrentContractSerializer(
            {
                "version": state.version,
                "signed": state.signed_contract is not None,
                "signed_contract": state.signed_contract,
                "has_payment_method": state.has_payment_method,
                "requires_signature": state.requires_signature,
                "requires_resign": state.requires_resign,
                "generation_allowed": state.generation_allowed,
                "generation_block_code": state.generation_block_code,
            }
        ).data
        return Response(data)


class SignContractView(APIView):
    """POST /api/v1/contracts/sign (FR-29..FR-32)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SignContractSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        version = None
        version_id = payload.pop("contract_version_id", None)
        if version_id is not None:
            version = ContractVersion.objects.filter(id=version_id).first()
            if version is None:
                return Response({"detail": "Unknown contract version."}, status=status.HTTP_404_NOT_FOUND)

        contract = services.sign_contract(request.user, consents=payload, request=request, contract_version=version)
        state = services.get_current_state(request.user)
        return Response(
            {
                "contract": ContractSerializer(contract).data,
                "has_payment_method": state.has_payment_method,
                "generation_allowed": state.generation_allowed,
                "generation_block_code": state.generation_block_code,
            },
            status=status.HTTP_201_CREATED,
        )


class ContractHistoryView(ListAPIView):
    """GET /api/v1/contracts/history (FR-31)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ContractSerializer
    pagination_class = None

    def get_queryset(self):
        return Contract.objects.filter(user=self.request.user).select_related("contract_version").order_by("-signed_at")


class ContractPdfView(APIView):
    """GET /api/v1/contracts/{id}/pdf — 302 to a 24h signed URL (FR-31, NFR-7). Owner-scoped."""

    permission_classes = [IsAuthenticated]

    def get(self, request, contract_id):
        url = services.contract_pdf_url(request.user, contract_id)
        return HttpResponseRedirect(url)
