from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimestampedModel


class NumberOffer(TimestampedModel):
    name = models.CharField(max_length=120)
    country_code = models.CharField(
        max_length=2, validators=[RegexValidator(r"^[A-Z]{2}$")]
    )
    country_name = models.CharField(max_length=80)
    service = models.CharField(
        max_length=20,
        choices=[(s, s) for s in ("youtube", "telegram", "whatsapp", "other")],
    )
    number_type = models.CharField(
        max_length=10, choices=[("mobile", "Mobile"), ("voip", "VoIP")]
    )
    provider = models.CharField(max_length=80)
    price_usd = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(1)]
    )
    base_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    tax_basis = models.CharField(
        max_length=12,
        default="base",
        choices=[("base", "Provider cost"), ("subtotal", "Cost plus platform fee")],
    )

    def save(self, *args, **kwargs):
        if self.base_cost_usd is not None:
            from virtual_numbers.pricing import quote

            self.price_usd = quote(self.base_cost_usd, self.tax_basis)["total"]
            if kwargs.get("update_fields"):
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"price_usd"}
        super().save(*args, **kwargs)

    rental_days = models.PositiveIntegerField(
        default=30, validators=[MinValueValidator(1)]
    )
    description = models.TextField(blank=True, max_length=2000)
    is_visible = models.BooleanField(default=True)
    sales_enabled = models.BooleanField(default=False)
    contract_confirmed = models.BooleanField(default=False)
    compatibility_confirmed = models.BooleanField(default=False)

    class Meta:
        ordering = ["country_name", "service", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_usd__gte=1, rental_days__gte=1),
                name="number_offer_positive_price_duration",
            )
        ]


class PhoneNumber(TimestampedModel):
    offer = models.ForeignKey(
        NumberOffer, on_delete=models.PROTECT, related_name="numbers"
    )
    number = models.CharField(
        max_length=16, unique=True, validators=[RegexValidator(r"^\+[1-9][0-9]{6,14}$")]
    )
    provider_reference = models.CharField(max_length=160, unique=True)
    state = models.CharField(
        max_length=12,
        default="available",
        choices=[(s, s) for s in ("available", "reserved", "assigned", "retired")],
    )


class NumberOrder(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    offer = models.ForeignKey(NumberOffer, on_delete=models.PROTECT)
    phone = models.ForeignKey(
        PhoneNumber, on_delete=models.PROTECT, related_name="orders"
    )
    payment_provider = models.CharField(
        max_length=12,
        default="stripe",
        choices=[
            ("stripe", "Stripe / Visa"),
            ("paypal", "PayPal"),
            ("allpay", "allpay.net"),
        ],
    )
    price_breakdown = models.JSONField(default=dict, blank=True)
    request_key = models.UUIDField()
    offer_name = models.CharField(max_length=120)
    service = models.CharField(max_length=20)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    rental_days = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            (s, s)
            for s in (
                "pending",
                "active",
                "expired",
                "canceled",
                "refund_requested",
                "refunded",
            )
        ],
    )
    checkout_id = models.CharField(max_length=255, blank=True)
    checkout_url = models.URLField(max_length=2048, blank=True)
    payment_intent = models.CharField(max_length=255, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=30, default="2026-09-22")
    refund_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_key"], name="unique_number_order_request"
            )
        ]


class IncomingSMS(TimestampedModel):
    order = models.ForeignKey(
        NumberOrder, on_delete=models.CASCADE, related_name="messages"
    )
    event_id = models.CharField(max_length=160, unique=True)
    sender_enc = EncryptedTextField()
    body_enc = EncryptedTextField()
    received_at = models.DateTimeField()
    delete_after = models.DateTimeField()

    class Meta:
        ordering = ["-received_at"]


class PaymentEvent(models.Model):
    event_id = models.CharField(max_length=255, primary_key=True)
    processed_at = models.DateTimeField(auto_now_add=True)
