"""Seed contract version 1.0 (FR-28, FR-30, FR-65, FR-70 — Q1 service-fee model)."""
from __future__ import annotations

import hashlib

from django.db import migrations
from django.utils import timezone

VERSION = "1.0"
TITLE = "Creator Agreement — AI Video Production & Revenue-Share Service Fee"

BODY = """\
CREATOR AGREEMENT (Version 1.0, English)

This Creator Agreement ("Agreement") is entered into between the operator of the AI YouTube
Content Ecosystem platform (the "Platform") and the creator who accepts it electronically
(the "Creator"). By ticking the consent boxes and clicking "Sign", the Creator agrees to be
bound by this Agreement.

1. THE SERVICE
1.1 The Platform produces videos with AI tools (script, voice-over, visuals, assembly) according
    to the Creator's content preferences and, subject to the Creator's approval settings,
    publishes them to the Creator's own YouTube channel using the official YouTube API and the
    OAuth permission the Creator grants.
1.2 The Platform never creates, purchases, activates or operates Google or YouTube accounts on
    the Creator's behalf. The channel remains the Creator's property at all times.
1.3 Every video is labelled as synthetic/AI-generated content in accordance with YouTube's
    disclosure requirements.

2. YOUR CHANNEL AND YOUR PERMISSION TO PUBLISH (consent b)
2.1 The Creator authorises the Platform to upload videos, thumbnails and metadata to the
    connected channel and to read channel analytics through the YouTube Data and Analytics APIs.
2.2 The Creator may revoke this permission at any time by disconnecting the channel; scheduled
    generation stops immediately.

3. REVENUE-SHARE SERVICE FEE — 50 / 50 (consent a)
3.1 Google/YouTube pays 100% of the advertising revenue earned by the Creator's channel directly
    to the Creator through the Creator's own AdSense account. The Platform never receives
    AdSense payments and never splits them at source.
3.2 As consideration for the production service, the Creator agrees to pay the Platform a
    "revenue-share service fee" equal to FIFTY PERCENT (50%) of the estimated gross revenue
    attributed by YouTube Analytics to PLATFORM-GENERATED VIDEOS ONLY. Revenue from videos the
    Creator produced independently is never included.
3.3 The fee is calculated per calendar month, on data that YouTube has marked final, rounded to
    the cent (ROUND_HALF_UP) with any rounding remainder allocated to the Creator's side. A
    monthly statement is made available in the dashboard and as a PDF; the Creator has 14 days
    to dispute a statement before it becomes final.
3.4 The Platform issues an invoice for the fee through Stripe and charges the Creator's saved
    payment method automatically. Amounts below USD 10 are carried forward to the next period.
3.5 If a charge fails, the Platform retries, then grants a 7-day grace period. If the invoice
    remains unpaid, video generation and scheduled publishing are paused until the balance is
    settled. Connected accounts and data are retained during the pause.
3.6 Creators on the Free plan receive a limited, watermarked service and no revenue-share fee
    applies to their videos.

4. SAVED PAYMENT METHOD
4.1 A valid saved payment method (card or bank account, stored by Stripe) is required before the
    Platform starts producing videos on a paid plan. The Platform never stores card numbers.

5. DATA USE AND AI PROCESSING (consent c)
5.1 The Creator's preferences, brand voice, channel metadata and analytics are processed to
    produce content, compute statements and operate the service. Third-party AI providers
    (language, voice and video models) receive only the prompts needed for generation.
5.2 Personal data is processed under the Platform's Privacy Policy. The Creator may export or
    request deletion of personal data from the dashboard.

6. MARKETING COMMUNICATIONS (consent d — optional)
6.1 Product news and offers are sent only if the Creator opts in. Transactional and security
    notices are always sent.

7. CONTENT STANDARDS
7.1 The Platform moderates every script and every finished video. Content that violates YouTube
    policies or applicable law is not published. The Creator remains responsible for the
    channel and may review, edit, approve or reject each video before publication.

8. TERM AND TERMINATION
8.1 This Agreement takes effect on signature and continues until terminated by either party.
    Fees accrued for revenue earned before termination remain payable.
8.2 A new version of this Agreement requires fresh consent; until then, generation is paused.

9. GENERAL
9.1 Governing law: State of Delaware, USA. Amounts are in USD.
9.2 Records: the Platform stores the exact text accepted (SHA-256 hash), the time, IP address
    and user agent of signature, and a PDF snapshot, available to the Creator at any time.
"""


def seed(apps, schema_editor):
    ContractVersion = apps.get_model("contracts", "ContractVersion")
    if ContractVersion.objects.filter(version=VERSION).exists():
        return
    ContractVersion.objects.update(is_active=False)
    ContractVersion.objects.create(
        version=VERSION,
        title=TITLE,
        body_markdown=BODY,
        body_sha256=hashlib.sha256(BODY.encode("utf-8")).hexdigest(),
        locale="en",
        revenue_share_platform_pct=50,
        revenue_share_creator_pct=50,
        effective_from=timezone.now(),
        is_active=True,
    )


def unseed(apps, schema_editor):
    ContractVersion = apps.get_model("contracts", "ContractVersion")
    ContractVersion.objects.filter(version=VERSION, contracts__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("contracts", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
