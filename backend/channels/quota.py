"""YouTube Data API quota budget (FR-58, SPEC 5.26, R-4).

Google enforces a per-project daily budget (10 000 units by default; an upload
costs 1 600) that resets at midnight Pacific Time. This module keeps our own
running counter so that:

* the upload stage never *starts* an upload it cannot afford (a rejected
  `videos.insert` still burns the quota), and 100% of the budget parks the job
  in `upload_queued` until `next_quota_window()` (FR-57);
* admins get one warning per quota day when either budget crosses
  `YOUTUBE_QUOTA_WARN_PERCENT` (FR-58);
* the hot counter is an atomic Redis `INCR` (Django cache), write-through to
  the `quota_usage` row. On a cache miss (Redis restart, new day) the counter
  is re-seeded from the DB so the two never drift apart by more than one
  in-flight reservation.

Nothing here talks to Google; it is bookkeeping only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from channels.models import QuotaUsage

logger = logging.getLogger("channels.quota")

# Cache entries live a little past the next reset so late stragglers on the
# previous day still find their counter; new days get fresh keys anyway.
_COUNTER_TTL_SECONDS = 36 * 60 * 60


class QuotaExhausted(Exception):
    """FR-58: the daily unit or upload budget would be exceeded. `next_window`
    is when the budget resets (aware UTC datetime).
    """

    def __init__(self, *, project_id: str, kind: str, used: int, limit: int, next_window: datetime):
        super().__init__(f"YouTube {kind} quota exhausted for project {project_id}: {used}/{limit}")
        self.project_id = project_id
        self.kind = kind
        self.used = used
        self.limit = limit
        self.next_window = next_window


@dataclass(frozen=True)
class QuotaSnapshot:
    project_id: str
    date_pt: date
    units_used: int
    units_limit: int
    uploads_used: int
    uploads_limit: int

    @property
    def units_percent(self) -> float:
        return (self.units_used / self.units_limit * 100.0) if self.units_limit else 100.0

    @property
    def uploads_percent(self) -> float:
        return (self.uploads_used / self.uploads_limit * 100.0) if self.uploads_limit else 100.0


# ---------------------------------------------------------------------------
# Time helpers (quota day = Pacific Time calendar day)
# ---------------------------------------------------------------------------
def quota_timezone() -> ZoneInfo:
    return ZoneInfo(settings.YOUTUBE_QUOTA_TIMEZONE)


def current_quota_date(now: datetime | None = None) -> date:
    now = now or timezone.now()
    return now.astimezone(quota_timezone()).date()


def next_quota_window(now: datetime | None = None) -> datetime:
    """Next midnight in `YOUTUBE_QUOTA_TIMEZONE` (Google's reset), as aware UTC."""
    now = now or timezone.now()
    local = now.astimezone(quota_timezone())
    next_midnight_local = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo)
    return next_midnight_local.astimezone(ZoneInfo("UTC"))


# ---------------------------------------------------------------------------
# Counter plumbing
# ---------------------------------------------------------------------------
def _project_id(project_id: str | None) -> str:
    return project_id or settings.GOOGLE_CLOUD_PROJECT_ID


def _key(project_id: str, day: date, kind: str) -> str:
    return f"yt_quota:{project_id}:{day.isoformat()}:{kind}"


def _limits() -> tuple[int, int]:
    return int(settings.YOUTUBE_DAILY_QUOTA_UNITS), int(settings.YOUTUBE_DAILY_UPLOAD_LIMIT)


def _get_or_create_row(project_id: str, day: date) -> QuotaUsage:
    units_limit, uploads_limit = _limits()
    row, _ = QuotaUsage.objects.get_or_create(
        google_project_id=project_id,
        date_pt=day,
        defaults={"units_limit": units_limit, "uploads_limit": uploads_limit},
    )
    return row


def _seed_counter(key: str, value: int) -> None:
    # `add` is atomic: only the first process after a cache miss seeds the key.
    cache.add(key, int(value), timeout=_COUNTER_TTL_SECONDS)


def _ensure_counters(project_id: str, day: date) -> QuotaUsage:
    row = _get_or_create_row(project_id, day)
    _seed_counter(_key(project_id, day, "units"), row.units_used)
    _seed_counter(_key(project_id, day, "uploads"), row.uploads_used)
    return row


def _incr(key: str, delta: int) -> int:
    try:
        return int(cache.incr(key, delta))
    except ValueError:
        # Key expired between seed and incr — re-seed from zero and retry once.
        _seed_counter(key, 0)
        return int(cache.incr(key, delta))


def _write_through(project_id: str, day: date, *, units: int, uploads: int) -> None:
    with transaction.atomic():
        _get_or_create_row(project_id, day)
        QuotaUsage.objects.filter(google_project_id=project_id, date_pt=day).update(
            units_used=F("units_used") + units,
            uploads_used=F("uploads_used") + uploads,
            updated_at=timezone.now(),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_snapshot(project_id: str | None = None, *, now: datetime | None = None) -> QuotaSnapshot:
    project_id = _project_id(project_id)
    day = current_quota_date(now)
    row = _ensure_counters(project_id, day)
    units = cache.get(_key(project_id, day, "units"))
    uploads = cache.get(_key(project_id, day, "uploads"))
    return QuotaSnapshot(
        project_id=project_id,
        date_pt=day,
        units_used=int(units if units is not None else row.units_used),
        units_limit=row.units_limit,
        uploads_used=int(uploads if uploads is not None else row.uploads_used),
        uploads_limit=row.uploads_limit,
    )


def can_upload(project_id: str | None = None, *, units: int | None = None) -> bool:
    """True when one more upload (`units`, default the videos.insert cost) fits
    in both today's unit and upload budgets. Read-only — reserves nothing.
    """
    units = int(settings.YOUTUBE_UPLOAD_COST_UNITS if units is None else units)
    snap = get_snapshot(project_id)
    return snap.units_used + units <= snap.units_limit and snap.uploads_used + 1 <= snap.uploads_limit


def reserve_units(project_id: str | None = None, units: int = 0, *, uploads: int = 0) -> QuotaSnapshot:
    """Atomically reserve `units` (and `uploads` upload slots) for today.

    Raises `QuotaExhausted` — after rolling the reservation back — when either
    budget would be exceeded. Emits the FR-58 80% admin warning once per quota
    day. Returns the post-reservation snapshot.
    """
    project_id = _project_id(project_id)
    day = current_quota_date()
    row = _ensure_counters(project_id, day)
    units = int(units)
    uploads = int(uploads)

    units_key = _key(project_id, day, "units")
    uploads_key = _key(project_id, day, "uploads")

    new_units = _incr(units_key, units) if units else int(cache.get(units_key) or 0)
    if new_units > row.units_limit:
        if units:
            cache.decr(units_key, units)
        raise QuotaExhausted(
            project_id=project_id, kind="units", used=new_units - units, limit=row.units_limit,
            next_window=next_quota_window(),
        )

    new_uploads = _incr(uploads_key, uploads) if uploads else int(cache.get(uploads_key) or 0)
    if new_uploads > row.uploads_limit:
        if uploads:
            cache.decr(uploads_key, uploads)
        if units:
            cache.decr(units_key, units)
        raise QuotaExhausted(
            project_id=project_id, kind="uploads", used=new_uploads - uploads, limit=row.uploads_limit,
            next_window=next_quota_window(),
        )

    if units or uploads:
        _write_through(project_id, day, units=units, uploads=uploads)

    snap = QuotaSnapshot(
        project_id=project_id,
        date_pt=day,
        units_used=new_units,
        units_limit=row.units_limit,
        uploads_used=new_uploads,
        uploads_limit=row.uploads_limit,
    )
    _maybe_warn_admins(snap)
    logger.info(
        "youtube_quota_reserved",
        extra={
            "project_id": project_id,
            "date_pt": day.isoformat(),
            "units": units,
            "uploads": uploads,
            "units_used": new_units,
            "uploads_used": new_uploads,
        },
    )
    return snap


def release_units(project_id: str | None = None, units: int = 0, *, uploads: int = 0) -> None:
    """Give a reservation back (the call never reached Google, e.g. the media
    file was missing). Never goes below zero.
    """
    project_id = _project_id(project_id)
    day = current_quota_date()
    _ensure_counters(project_id, day)
    units = int(units)
    uploads = int(uploads)
    if units:
        cache.decr(_key(project_id, day, "units"), units)
    if uploads:
        cache.decr(_key(project_id, day, "uploads"), uploads)
    _write_through(project_id, day, units=-units, uploads=-uploads)
    QuotaUsage.objects.filter(google_project_id=project_id, date_pt=day, units_used__lt=0).update(units_used=0)
    QuotaUsage.objects.filter(google_project_id=project_id, date_pt=day, uploads_used__lt=0).update(uploads_used=0)


def mark_exhausted(project_id: str | None = None, *, kind: str = "units") -> None:
    """Google said `quotaExceeded` although our counter had room (another
    consumer of the same project, or an under-estimated cost). Pin the local
    counter at the limit so no further upload is attempted before the reset.
    """
    project_id = _project_id(project_id)
    day = current_quota_date()
    row = _ensure_counters(project_id, day)
    limit = row.units_limit if kind == "units" else row.uploads_limit
    cache.set(_key(project_id, day, kind), int(limit), timeout=_COUNTER_TTL_SECONDS)
    QuotaUsage.objects.filter(google_project_id=project_id, date_pt=day).update(
        **{f"{kind}_used": limit, "updated_at": timezone.now()}
    )
    logger.warning("youtube_quota_marked_exhausted", extra={"project_id": project_id, "kind": kind, "limit": limit})


def _maybe_warn_admins(snap: QuotaSnapshot) -> None:
    threshold = float(settings.YOUTUBE_QUOTA_WARN_PERCENT)
    over = snap.units_percent >= threshold or snap.uploads_percent >= threshold
    if not over:
        return
    warned_key = _key(snap.project_id, snap.date_pt, "warned")
    if not cache.add(warned_key, 1, timeout=_COUNTER_TTL_SECONDS):
        return  # already warned today
    from notifications.services import notify_admins

    try:
        notify_admins(
            "admin.alert",
            ctx={
                "subject": f"YouTube quota at {max(snap.units_percent, snap.uploads_percent):.0f}%",
                "message": (
                    f"Project {snap.project_id} on {snap.date_pt.isoformat()} (PT): "
                    f"{snap.units_used}/{snap.units_limit} units, "
                    f"{snap.uploads_used}/{snap.uploads_limit} uploads. "
                    f"Uploads queue automatically at 100% until {next_quota_window().isoformat()}."
                ),
            },
            payload={
                "project_id": snap.project_id,
                "date_pt": snap.date_pt.isoformat(),
                "units_used": snap.units_used,
                "units_limit": snap.units_limit,
                "uploads_used": snap.uploads_used,
                "uploads_limit": snap.uploads_limit,
            },
        )
    except Exception:  # noqa: BLE001 — a failed alert must never block an upload
        logger.exception("youtube_quota_admin_alert_failed", extra={"project_id": snap.project_id})
