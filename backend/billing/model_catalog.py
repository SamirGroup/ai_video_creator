from decimal import ROUND_CEILING, Decimal

from providers.models import ApiCredentialConfig
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.economics import CREDIT_USD
from billing.models import Plan


def model_rows():
    plans = list(Plan.objects.filter(is_active=True))
    return [
        {
            "model": row.model_name,
            "name": row.display_name,
            "provider": row.provider,
            "unit": row.cost_unit,
            "price_usd": str(row.unit_cost_usd),
            "credits_per_unit": int(
                (row.unit_cost_usd / CREDIT_USD).to_integral_value(
                    rounding=ROUND_CEILING
                )
            ),
            "available": row.is_active and row.has_secret(),
            "source": row.get_option("pricing_source", ""),
            "verified_on": row.get_option("pricing_verified_on", ""),
            "note": row.get_option("pricing_note", ""),
            "plans": [
                p.code
                for p in plans
                if row.model_name in p.features.get("video_models", [])
            ],
        }
        for row in ApiCredentialConfig.objects.filter(
            service="video_gen", deleted_at__isnull=True, unit_cost_usd__gt=Decimal(0)
        ).order_by("provider", "unit_cost_usd")
    ]


class ModelCatalogView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        return Response(model_rows())
