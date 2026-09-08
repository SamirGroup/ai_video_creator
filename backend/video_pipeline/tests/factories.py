"""Factories for the script-stage integration tests (DB-backed)."""
from __future__ import annotations

from datetime import time, timedelta

import factory
from django.utils import timezone

from accounts.tests.factories import UserFactory
from channels.models import ConnectionStatus, YouTubeChannel
from content_planning.models import ApprovalMode, ContentPreference, Frequency
from video_pipeline.models import JobStatus, JobTrigger, VideoJob


class YouTubeChannelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = YouTubeChannel

    user = factory.SubFactory(UserFactory)
    youtube_channel_id = factory.Sequence(lambda n: f"UC_test_channel_{n}")
    channel_title = factory.Sequence(lambda n: f"Test Channel {n}")
    status = ConnectionStatus.CONNECTED


class ContentPreferenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentPreference

    user = factory.SelfAttribute("channel.user")
    channel = factory.SubFactory(YouTubeChannelFactory)

    niche = "travel"
    custom_brief = "Short, specific stories about food traditions in northern Spain."
    brand_voice = "Dry, precise, no hype. Audience already knows the basics."
    banned_topics = factory.LazyFunction(lambda: ["politics", "gambling"])
    language = "en"
    video_duration_sec = 180
    frequency = Frequency.WEEKLY
    publish_time_local = time(9, 0)
    publish_timezone = "UTC"
    approval_mode = ApprovalMode.REVIEW_REQUIRED


class VideoJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VideoJob

    user = factory.SelfAttribute("channel.user")
    channel = factory.SubFactory(YouTubeChannelFactory)
    preference = factory.SubFactory(
        ContentPreferenceFactory, channel=factory.SelfAttribute("..channel")
    )
    trigger = JobTrigger.SCHEDULED
    status = JobStatus.QUEUED
    scheduled_for = factory.LazyFunction(lambda: timezone.now() + timedelta(days=1))
    language = "en"
