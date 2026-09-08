from __future__ import annotations

import factory

from billing.models import BillingInterval, Plan, Subscription, SubscriptionStatus


class PlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Plan
        django_get_or_create = ("code",)

    code = "starter"
    name = "Starter"
    price_amount = 50
    currency = "USD"
    billing_interval = BillingInterval.MONTH
    stripe_price_id = "price_starter_test"
    videos_per_period = 8
    max_video_duration_sec = 300


class SubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subscription

    plan = factory.SubFactory(PlanFactory)
    status = SubscriptionStatus.TRIALING
