"""Helper for writing audit trail entries (FR-72, NFR-8).

Usage: `record_audit_event(actor_type="user", actor_id=user.id,
action="oauth.granted", resource_type="youtube_channel", resource_id=str(channel.id),
request=request)` from any service that performs a sensitive action.
"""
from __future__ import annotations

from audit.models import ActorType, AuditLog


def record_audit_event(
    *,
    actor_type: str = ActorType.SYSTEM,
    actor_id=None,
    action: str,
    resource_type: str,
    resource_id: str,
    request=None,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    ip_address = None
    user_agent = ""
    if request is not None:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    return AuditLog.objects.create(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        ip_address=ip_address,
        user_agent=user_agent,
        before=before,
        after=after,
        metadata=metadata or {},
    )
