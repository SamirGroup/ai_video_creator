from decimal import Decimal

from billing.models import AIWallet
from billing.quota import remaining
from django.conf import settings
from providers.models import ApiCredentialConfig
from rest_framework.exceptions import ValidationError


def planning_budget(user, model=None):
    subscription = getattr(user, "subscription", None)
    quota = remaining(user)
    if not subscription or not subscription.plan.ai_budget_enabled:
        return {
            "max_count": min(30, quota.videos_remaining),
            "models": [],
            "video_model": None,
        }
    plan = subscription.plan
    models = plan.features.get("video_models", [])
    chosen = model or (models[0] if models else None)
    if chosen not in models:
        raise ValidationError("Video model is not included in your subscription.")
    configs = ApiCredentialConfig.objects.filter(
        service="video_gen", model_name__in=models, deleted_at__isnull=True
    )
    ready = [c.model_name for c in configs if c.is_active and c.has_secret()]
    wallet = AIWallet.objects.filter(user=user).first()
    available = (
        max(Decimal(0), wallet.balance_usd - wallet.reserved_usd)
        if wallet
        else Decimal(0)
    )
    ceiling = Decimal(
        str(plan.features.get("job_budget_usd", settings.JOB_COST_CEILING_USD))
    )
    capacity = int(available // ceiling) if ceiling > 0 else 0
    return {
        "max_count": min(30, quota.videos_remaining, capacity),
        "models": models,
        "ready_models": ready,
        "video_model": chosen,
        "available_usd": str(available),
        "per_video_budget_usd": str(ceiling),
        "plan": plan.code,
    }


def assert_plan_budget(user, count, model=None):
    budget = planning_budget(user, model)
    if budget.get("models") and budget["video_model"] not in budget.get(
        "ready_models", []
    ):
        raise ValidationError("Selected video model is not configured yet.")
    if count > budget["max_count"]:
        raise ValidationError(
            f"Your current plan and credit support at most {budget['max_count']} videos. Reduce the count or add credit."
        )
    return budget
