from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError

from video_pipeline.models import JobStatus, VideoRevision
from video_pipeline.services.revisions import maybe_auto_revise, request_revision
from video_pipeline.services.cost_control import check_cost_ceiling
from video_pipeline.services.exceptions import CostCeilingExceeded
from video_pipeline.tests.factories import VideoJobFactory

pytestmark = pytest.mark.django_db


def test_revision_is_idempotent_and_preserves_rejected_artifact():
    job = VideoJobFactory(status=JobStatus.MODERATION_REVIEW, final_video_s3_key='rejected/original.mp4')
    with patch('video_pipeline.services.revisions.assert_generation_allowed'), patch('video_pipeline.services.revisions.reserve_quota') as quota:
        child = request_revision(job, reason='Remove unsupported medical claim')
        repeated = request_revision(job, reason='Repeated delivery')
    assert child.pk == repeated.pk
    assert VideoRevision.objects.count() == 1
    quota.assert_called_once()
    job.refresh_from_db()
    assert job.final_video_s3_key == 'rejected/original.mp4'
    assert job.status == JobStatus.MODERATION_REJECTED
    assert not child.final_video_s3_key
    assert not child.moderation_approved_sha256
    assert child.generation_context['moderation_feedback']['reason'] == 'Remove unsupported medical claim'


def test_hard_block_never_auto_regenerates():
    job = VideoJobFactory(status=JobStatus.MODERATION_REVIEW)
    with patch('video_pipeline.services.revisions.request_revision') as revise:
        assert maybe_auto_revise(job, SimpleNamespace(verdict='block')) is None
    revise.assert_not_called()


def test_revision_chain_cannot_reset_budget(settings):
    settings.MODERATION_REVISION_BUDGET_USD = '1.00'
    root = VideoJobFactory(status=JobStatus.MODERATION_REVIEW, total_cost_usd=Decimal('0.60'))
    with patch('video_pipeline.services.revisions.assert_generation_allowed'), patch('video_pipeline.services.revisions.reserve_quota'):
        child = request_revision(root, reason='Correct the flagged statement')
    child.total_cost_usd = Decimal('0.50')
    child.status = JobStatus.MODERATION_REVIEW
    child.save()
    with pytest.raises(CostCeilingExceeded):
        check_cost_ceiling(child, refresh=False)
    with pytest.raises(ValidationError):
        request_revision(child, reason='Another attempt')
    assert VideoRevision.objects.count() == 1
