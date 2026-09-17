"""FR-67..FR-70b revenue-share period close.

`TestSplit5050` needs no database — it is the single most important
invariant in the whole revenue-share model (AC-7: platform_share_amount +
creator_share_amount == gross_revenue, to the cent). Everything else is a
DB-backed integration test of `close_period_for_user`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.tests.factories import UserFactory
from contracts.models import Contract, ContractStatus, ContractVersion
from revenue.models import (
    Invoice,
    RevenueRecord,
    RevenueSettlement,
    RevenueShareStatement,
    RevenueSource,
    StatementStatus,
)
from revenue.services.statements import (
    DisputeWindowClosed,
    StatementNotDisputable,
    close_period_for_user,
    dispute_statement,
    gross_for_period,
    previous_calendar_month,
    split_50_50,
)
from video_pipeline.models import JobStatus
from video_pipeline.tests.factories import VideoJobFactory


# ---------------------------------------------------------------------------
# Pure rounding invariant (no DB)
# ---------------------------------------------------------------------------
class TestSplit5050:
    @pytest.mark.parametrize(
        "gross",
        [
            Decimal("100.01"),
            Decimal("0.03"),
            Decimal("0.01"),
            Decimal("9.995"),
            Decimal("1234.56"),
            Decimal("0.00"),
            Decimal("1000000.07"),
        ],
    )
    def test_shares_always_sum_to_gross(self, gross):
        platform, creator = split_50_50(
            gross, platform_pct=Decimal("50"), creator_pct=Decimal("50")
        )
        assert platform + creator == gross

    def test_odd_cent_favours_the_creator_not_the_platform(self):
        # $100.01 split 50/50 raw = $50.005 / $50.005 — someone gets the extra cent.
        platform, creator = split_50_50(
            Decimal("100.01"), platform_pct=Decimal("50"), creator_pct=Decimal("50")
        )
        assert creator == Decimal("50.01")
        assert platform == Decimal("50.00")

    def test_non_5050_split_still_sums_exactly(self):
        platform, creator = split_50_50(
            Decimal("77.77"), platform_pct=Decimal("30"), creator_pct=Decimal("70")
        )
        assert platform + creator == Decimal("77.77")
        assert creator == Decimal("54.44")  # 77.77 * 0.7 = 54.439 -> half-up -> 54.44
        assert platform == Decimal("23.33")

    def test_zero_gross(self):
        platform, creator = split_50_50(
            Decimal("0"), platform_pct=Decimal("50"), creator_pct=Decimal("50")
        )
        assert (platform, creator) == (Decimal("0.00"), Decimal("0.00"))


class TestPreviousCalendarMonth:
    def test_half_open_range_across_a_year_boundary(self):
        start, end = previous_calendar_month(date(2026, 1, 15))
        assert start == date(2025, 12, 1)
        assert end == date(2026, 1, 1)

    def test_mid_year(self):
        start, end = previous_calendar_month(date(2026, 3, 1))
        assert start == date(2026, 2, 1)
        assert end == date(2026, 3, 1)


# ---------------------------------------------------------------------------
# DB-backed: gross_for_period / close_period_for_user
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _stub_billing(monkeypatch):
    """Every test here is about the statement math, not Stripe — replace
    `create_revenue_share_invoice` with a recorder so no test needs a
    Stripe customer/payment method fixture.
    """
    import revenue.services.statements as statements_module

    calls: list = []

    def _fake_invoice(user, statement):
        calls.append((user, statement))
        return Invoice.objects.create(
            user=user,
            statement=statement,
            kind="revenue_share",
            amount=statement.platform_share_amount,
            currency=statement.currency,
            due_at=timezone.now(),
            status="paid",
            paid_at=timezone.now(),
        )

    monkeypatch.setattr(
        statements_module,
        "_invoice_or_carry_forward",
        lambda statement: _record_and_invoice(statement, _fake_invoice, calls),
    )
    return calls


def _record_and_invoice(statement, fake_invoice, calls):
    invoice = fake_invoice(statement.user, statement)
    statement.status = StatementStatus.INVOICED
    statement.save(update_fields=["status", "updated_at"])
    return invoice


@pytest.fixture
def contract(db):
    user = UserFactory()
    version = ContractVersion.objects.create(
        revenue_only_platform_published=False,
        version="v1.0",
        title="Creator Agreement",
        body_markdown="Terms...",
        revenue_share_platform_pct=50,
        revenue_share_creator_pct=50,
        locale="en",
        effective_from=timezone.now() - timedelta(days=30),
        is_active=True,
    )
    return Contract.objects.create(
        user=user,
        contract_version=version,
        ip_address="127.0.0.1",
        consent_revenue_share=True,
        consent_publish_to_channel=True,
        consent_data_processing=True,
        status=ContractStatus.ACTIVE,
    )


def _final_record(
    *, user, channel, job, day, revenue, source=RevenueSource.YOUTUBE_ANALYTICS
):
    return RevenueRecord.objects.create(
        user=user,
        channel=channel,
        job=job,
        youtube_video_id=job.youtube_video_id or "yt_test",
        source=source,
        date=day,
        views=1000,
        estimated_minutes_watched=500,
        estimated_revenue=revenue,
        estimated_ad_revenue=revenue,
        is_final=True,
        synced_at=timezone.now(),
    )


class TestGrossForPeriod:
    def test_ignores_non_platform_generated_and_unattributed_rows(self, contract):
        user = contract.user
        job = VideoJobFactory(channel__user=user, is_platform_generated=True)
        other_job = VideoJobFactory(channel__user=user, is_platform_generated=False)
        period_start, period_end = date(2026, 1, 1), date(2026, 2, 1)

        _final_record(
            user=user,
            channel=job.channel,
            job=job,
            day=date(2026, 1, 10),
            revenue=Decimal("10.00"),
        )
        _final_record(
            user=user,
            channel=other_job.channel,
            job=other_job,
            day=date(2026, 1, 10),
            revenue=Decimal("999.00"),
        )
        RevenueRecord.objects.create(  # channel-level, job=None — excluded (FR-65)
            user=user,
            channel=job.channel,
            job=None,
            source=RevenueSource.YOUTUBE_ANALYTICS,
            date=date(2026, 1, 11),
            views=100,
            estimated_revenue=Decimal("5.00"),
            is_final=True,
            synced_at=timezone.now(),
        )

        gross, breakdown, count = gross_for_period(user, period_start, period_end)
        assert gross == Decimal("10.00")
        assert count == 1
        assert breakdown == {str(job.id): "10.00"}

    def test_adsense_wins_over_youtube_analytics_for_the_same_video_day(self, contract):
        user = contract.user
        job = VideoJobFactory(channel__user=user, is_platform_generated=True)
        day = date(2026, 1, 10)
        _final_record(
            user=user,
            channel=job.channel,
            job=job,
            day=day,
            revenue=Decimal("8.00"),
            source=RevenueSource.YOUTUBE_ANALYTICS,
        )
        _final_record(
            user=user,
            channel=job.channel,
            job=job,
            day=day,
            revenue=Decimal("9.50"),
            source=RevenueSource.ADSENSE,
        )

        gross, _, _ = gross_for_period(user, date(2026, 1, 1), date(2026, 2, 1))
        assert gross == Decimal("9.50")  # not 17.50 (double-counted)


class TestClosePeriodForUser:
    def test_creates_a_balanced_statement_and_invoices_it(
        self, contract, _stub_billing
    ):
        user = contract.user
        job = VideoJobFactory(channel__user=user, is_platform_generated=True)
        _final_record(
            user=user,
            channel=job.channel,
            job=job,
            day=date(2026, 1, 15),
            revenue=Decimal("100.00"),
        )

        statement = close_period_for_user(user, date(2026, 1, 1), date(2026, 2, 1))

        assert statement is not None
        assert statement.gross_revenue == Decimal("100.00")
        assert (
            statement.platform_share_amount + statement.creator_share_amount
            == statement.gross_revenue
        )
        assert statement.platform_share_amount == Decimal("50.00")
        assert statement.creator_share_amount == Decimal("50.00")
        assert statement.contract_id == contract.id
        assert statement.status == StatementStatus.INVOICED
        assert len(_stub_billing) == 1

    def test_is_idempotent_for_the_same_period(self, contract):
        user = contract.user
        job = VideoJobFactory(channel__user=user, is_platform_generated=True)
        _final_record(
            user=user,
            channel=job.channel,
            job=job,
            day=date(2026, 1, 15),
            revenue=Decimal("42.00"),
        )

        first = close_period_for_user(user, date(2026, 1, 1), date(2026, 2, 1))
        second = close_period_for_user(user, date(2026, 1, 1), date(2026, 2, 1))

        assert first.id == second.id
        assert RevenueShareStatement.objects.filter(user=user).count() == 1

    def test_returns_none_when_there_is_no_platform_revenue(self, contract):
        statement = close_period_for_user(
            contract.user, date(2026, 1, 1), date(2026, 2, 1)
        )
        assert statement is None
        assert RevenueShareStatement.objects.filter(user=contract.user).count() == 0

    def test_returns_none_without_an_active_contract(self, db):
        user = UserFactory()
        job = VideoJobFactory(channel__user=user, is_platform_generated=True)
        _final_record(
            user=user,
            channel=job.channel,
            job=job,
            day=date(2026, 1, 15),
            revenue=Decimal("50.00"),
        )

        statement = close_period_for_user(user, date(2026, 1, 1), date(2026, 2, 1))
        assert statement is None


class TestDisputeStatement:
    def test_dispute_within_window_succeeds(self, contract):
        statement = RevenueShareStatement.objects.create(
            user=contract.user,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            gross_revenue=Decimal("10.00"),
            platform_share_amount=Decimal("5.00"),
            creator_share_amount=Decimal("5.00"),
            contract=contract,
            status=StatementStatus.FINALIZED,
            finalized_at=timezone.now() - timedelta(days=3),
        )
        result = dispute_statement(contract.user, statement, "Views look wrong.")
        assert result.status == StatementStatus.DISPUTED
        assert result.dispute_reason == "Views look wrong."

    def test_dispute_after_window_is_rejected(self, contract):
        statement = RevenueShareStatement.objects.create(
            user=contract.user,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            gross_revenue=Decimal("10.00"),
            platform_share_amount=Decimal("5.00"),
            creator_share_amount=Decimal("5.00"),
            contract=contract,
            status=StatementStatus.FINALIZED,
            finalized_at=timezone.now() - timedelta(days=15),
        )
        with pytest.raises(DisputeWindowClosed):
            dispute_statement(contract.user, statement, "Too late.")

    def test_dispute_on_a_draft_statement_is_rejected(self, contract):
        statement = RevenueShareStatement.objects.create(
            user=contract.user,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            gross_revenue=Decimal("10.00"),
            platform_share_amount=Decimal("5.00"),
            creator_share_amount=Decimal("5.00"),
            contract=contract,
            status=StatementStatus.DRAFT,
        )
        with pytest.raises(StatementNotDisputable):
            dispute_statement(contract.user, statement, "x")


class TestRevenueShare3070:
    def test_new_contract_defaults_and_existing_seed_are_distinct(self, db):
        prospective = ContractVersion()
        assert prospective.revenue_share_platform_pct == 30
        assert prospective.revenue_share_creator_pct == 70
        historical = ContractVersion.objects.get(version="1.0")
        assert historical.revenue_share_platform_pct == Decimal("50")
        assert historical.revenue_share_creator_pct == Decimal("50")
        assert not historical.revenue_only_platform_published
        current = ContractVersion.objects.get(version="1.1")
        assert current.is_active
        assert current.revenue_share_platform_pct == Decimal("30")
        assert current.revenue_only_platform_published
        assert "PUBLISHED THROUGH" in current.body_markdown

    def test_only_platform_generated_revenue_is_charged(self, contract):
        version = contract.contract_version
        version.revenue_share_platform_pct = Decimal("30")
        version.revenue_share_creator_pct = Decimal("70")
        version.revenue_only_platform_published = True
        version.save()
        user = contract.user
        ours = VideoJobFactory(
            user=user,
            status=JobStatus.PUBLISHED,
            is_platform_generated=True,
            youtube_video_id="ours_video",
            youtube_upload_status="uploaded",
            published_at=timezone.now(),
        )
        independent = VideoJobFactory(
            user=user,
            channel=ours.channel,
            status=JobStatus.PUBLISHED,
            is_platform_generated=False,
            youtube_video_id="independent_video",
        )
        exported = VideoJobFactory(
            user=user,
            channel=ours.channel,
            is_platform_generated=True,
            youtube_video_id="external_upload",
        )
        day = date(2026, 1, 15)
        _final_record(
            user=user,
            channel=ours.channel,
            job=exported,
            day=day,
            revenue=Decimal("500"),
        )
        _final_record(
            user=user, channel=ours.channel, job=ours, day=day, revenue=Decimal("100")
        )
        _final_record(
            user=user,
            channel=ours.channel,
            job=independent,
            day=day,
            revenue=Decimal("900"),
        )
        for video, amount in [(ours, "100"), (independent, "900"), (exported, "500")]:
            RevenueSettlement.objects.create(
                user=user,
                job=video,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 2, 1),
                amount=Decimal(amount),
                evidence_reference="verified-test-report",
                verified_by=user,
            )
        statement = close_period_for_user(user, date(2026, 1, 1), date(2026, 2, 1))
        assert statement.status == StatementStatus.DRAFT
        assert statement.review_deadline is not None
        assert not Invoice.objects.filter(statement=statement).exists()
        assert statement.gross_revenue == Decimal("100.00")
        assert statement.platform_share_amount == Decimal("30.00")
        assert statement.creator_share_amount == Decimal("70.00")
        assert statement.video_count == 1
        assert str(independent.pk) not in statement.breakdown
        assert str(exported.pk) not in statement.breakdown

    @pytest.mark.parametrize(
        ("platform", "creator"),
        [("30", "60"), ("-1", "101"), ("NaN", "70"), ("30", "Infinity")],
    )
    def test_invalid_percentages_are_rejected(self, platform, creator):
        from revenue.services.statements import split_revenue

        with pytest.raises(ValueError):
            split_revenue(
                Decimal("100"),
                platform_pct=Decimal(platform),
                creator_pct=Decimal(creator),
            )


@pytest.mark.django_db
def test_review_window_prevents_charge_and_dispute_blocks_scheduled_finalization(
    _stub_billing, contract
):
    from revenue.services.statements import finalize_statement
    from revenue.tasks import finalize_reviewed_statements

    user = contract.user
    statement = RevenueShareStatement.objects.create(
        user=user,
        contract=contract,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 1),
        gross_revenue=100,
        platform_share_pct=30,
        platform_share_amount=30,
        creator_share_amount=70,
        status=StatementStatus.DRAFT,
        review_deadline=timezone.now() + timedelta(days=14),
    )
    with pytest.raises(StatementNotDisputable):
        finalize_statement(None, statement)
    assert not _stub_billing
    dispute_statement(user, statement, "The video revenue does not match the report.")
    RevenueShareStatement.objects.filter(pk=statement.pk).update(
        review_deadline=timezone.now() - timedelta(seconds=1)
    )
    assert finalize_reviewed_statements()["finalized"] == 0
    assert not _stub_billing
