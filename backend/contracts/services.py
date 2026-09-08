"""Contract lifecycle (FR-28..FR-32, FR-70a).

`sign_contract` is the only writer of `contracts` rows. It is atomic: the
row, the PDF snapshot, the consent ledger rows, the audit entry and the
notification either all happen or none do (the PDF is written to storage
before commit; an orphaned file on rollback is harmless).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from accounts.consents import ConsentType, record_consent
from audit.services import record_audit_event
from contracts.gates import check_generation_eligibility, get_active_contract_version, get_signed_contract
from contracts.models import Contract, ContractStatus, ContractVersion
from contracts.pdf import render_text_pdf
from core.storage import contract_pdf_key, get_storage
from notifications.services import notify

logger = logging.getLogger("contracts.services")

MANDATORY_CONSENTS = ("consent_revenue_share", "consent_publish_to_channel", "consent_data_processing")


@dataclass(frozen=True)
class CurrentContractState:
    version: ContractVersion | None
    signed_contract: Contract | None
    has_payment_method: bool
    requires_signature: bool
    requires_resign: bool
    generation_allowed: bool
    generation_block_code: str | None


def get_current_state(user) -> CurrentContractState:
    version = get_active_contract_version()
    signed = get_signed_contract(user, version) if version else None
    latest_any = Contract.objects.filter(user=user, status=ContractStatus.ACTIVE).order_by("-signed_at").first()
    eligibility = check_generation_eligibility(user)
    return CurrentContractState(
        version=version,
        signed_contract=signed,
        has_payment_method=eligibility.payment_method_saved,
        requires_signature=version is not None and signed is None,
        requires_resign=version is not None and signed is None and latest_any is not None,
        generation_allowed=eligibility.allowed,
        generation_block_code=eligibility.code,
    )


def _client_ip(request) -> str:
    if request is None:
        return "0.0.0.0"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _render_snapshot(user, version: ContractVersion, contract: Contract, consents: dict[str, bool]) -> bytes:
    signed_at = contract.signed_at or timezone.now()
    header = [
        f"Version: {version.version}    Effective from: {version.effective_from:%Y-%m-%d}",
        f"Signed by: {user.email}    User ID: {user.id}",
        f"Signed at (UTC): {signed_at:%Y-%m-%d %H:%M:%S}",
        f"IP address: {contract.ip_address}",
        f"User agent: {contract.user_agent[:200]}",
        f"Template SHA-256: {version.body_sha256}",
        "",
        "Granular consents:",
        f"  [{'x' if consents['consent_revenue_share'] else ' '}] (a) Revenue-share service fee terms "
        f"({version.revenue_share_platform_pct}% platform / {version.revenue_share_creator_pct}% creator)",
        f"  [{'x' if consents['consent_publish_to_channel'] else ' '}] (b) Permission to publish videos to my YouTube channel",
        f"  [{'x' if consents['consent_data_processing'] else ' '}] (c) Data use and AI processing",
        f"  [{'x' if consents['consent_marketing'] else ' '}] (d) Marketing emails (optional)",
        "",
        "-" * 90,
        "",
    ]
    body = version.body_markdown.splitlines()
    return render_text_pdf(
        version.title,
        header + body,
        metadata={"Author": "AI YouTube Content Ecosystem", "Subject": f"Creator agreement {version.version}"},
    )


@transaction.atomic
def sign_contract(
    user,
    *,
    consents: dict[str, bool],
    request=None,
    contract_version: ContractVersion | None = None,
) -> Contract:
    """FR-29/FR-30: record the granular consent, snapshot the terms, supersede older contracts."""
    version = contract_version or get_active_contract_version()
    if version is None:
        raise NotFound("No active contract version is published.")
    if not version.is_active:
        raise ValidationError({"contract_version_id": "This contract version is no longer active."})
    missing = [name for name in MANDATORY_CONSENTS if not consents.get(name)]
    if missing:
        raise ValidationError({name: "This consent is required to use the service." for name in missing})

    existing = get_signed_contract(user, version)
    if existing is not None:
        raise ValidationError({"detail": f"Contract version {version.version} is already signed."})

    previous = list(Contract.objects.select_for_update().filter(user=user, status=ContractStatus.ACTIVE))
    for old in previous:
        old.status = ContractStatus.SUPERSEDED
        old.save(update_fields=["status"])

    contract = Contract.objects.create(
        user=user,
        contract_version=version,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:2000],
        body_sha256=version.body_sha256,
        consent_revenue_share=True,
        consent_publish_to_channel=True,
        consent_data_processing=True,
        consent_marketing=bool(consents.get("consent_marketing", False)),
        status=ContractStatus.ACTIVE,
    )

    pdf_bytes = _render_snapshot(user, version, contract, {**consents, "consent_marketing": contract.consent_marketing})
    key = contract_pdf_key(user.id, contract.id)
    get_storage().put_bytes(key, pdf_bytes, content_type="application/pdf")
    contract.pdf_s3_key = key
    contract.save(update_fields=["pdf_s3_key"])

    scope = {"contract_id": str(contract.id), "contract_version": version.version, "body_sha256": version.body_sha256}
    record_consent(user, ConsentType.REVENUE_SHARE, True, scope, request)
    record_consent(user, ConsentType.PUBLISH_TO_CHANNEL, True, scope, request)
    record_consent(user, ConsentType.DATA_PROCESSING, True, scope, request)
    record_consent(user, ConsentType.MARKETING, contract.consent_marketing, scope, request)
    if user.marketing_opt_in != contract.consent_marketing:
        user.marketing_opt_in = contract.consent_marketing
        user.save(update_fields=["marketing_opt_in", "updated_at"])

    record_audit_event(
        actor_type="user",
        actor_id=user.id,
        action="contract.signed",
        resource_type="contract",
        resource_id=str(contract.id),
        request=request,
        before={"superseded_contract_ids": [str(c.id) for c in previous]},
        after={
            "contract_version": version.version,
            "body_sha256": version.body_sha256,
            "consent_marketing": contract.consent_marketing,
            "pdf_s3_key": key,
        },
    )
    notify(
        user,
        "contract.signed",
        ctx={"version": version.version, "signed_at": f"{contract.signed_at:%Y-%m-%d %H:%M} UTC"},
        payload={"contract_id": str(contract.id)},
    )
    logger.info("contract_signed", extra={"user_id": str(user.id), "contract_id": str(contract.id), "version": version.version})
    return contract


def contract_pdf_url(user, contract_id) -> str:
    """Signed URL (24h) for the creator's own contract snapshot (FR-31)."""
    contract = Contract.objects.filter(id=contract_id, user=user).first()
    if contract is None or not contract.pdf_s3_key:
        raise NotFound("Contract not found.")
    record_audit_event(
        actor_type="user",
        actor_id=user.id,
        action="contract.pdf_downloaded",
        resource_type="contract",
        resource_id=str(contract.id),
    )
    return get_storage().signed_url(contract.pdf_s3_key)
