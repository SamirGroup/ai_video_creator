import json

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimestampedModel


class ServicePackage(TimestampedModel):
    """Commercial terms of a package. Its wording lives in `contract.PACKAGES`."""

    code = models.SlugField(max_length=20, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    price_usd = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(1)]
    )
    # Delivery time in hours: a range when `delivery_hours_min` is set
    # (e.g. 1–2 hours), otherwise "within N hours", shown as days from 24 up.
    delivery_hours_min = models.PositiveSmallIntegerField(null=True, blank=True)
    delivery_hours = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    revision_rounds = models.PositiveSmallIntegerField(default=2)
    support_months = models.PositiveSmallIntegerField(default=1)
    # 0 means the page count is set by the technical specification.
    page_limit = models.PositiveSmallIntegerField(default=1)
    languages = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "price_usd"]

    def __str__(self):
        return self.code

    def terms(self):
        return {
            "code": self.code,
            "delivery_hours_min": self.delivery_hours_min,
            "delivery_hours": self.delivery_hours,
            "revision_rounds": self.revision_rounds,
            "support_months": self.support_months,
            "page_limit": self.page_limit,
            "languages": self.languages,
        }


class ExecutorProfile(models.Model):
    """The contracting party's requisites (singleton, pk=1)."""

    legal_name = models.CharField(max_length=200, blank=True)
    director_name = models.CharField(max_length=160, blank=True)
    acting_basis = models.CharField(max_length=120, default="Ustav")
    acting_basis_en = models.CharField(max_length=120, default="the Charter")
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=80, default="Toshkent shahri")
    city_en = models.CharField(max_length=80, default="Tashkent, Republic of Uzbekistan")
    tin = models.CharField("STIR / TIN", max_length=20, blank=True)
    bank_name = models.CharField(max_length=160, blank=True)
    bank_account = models.CharField(max_length=40, blank=True)
    bank_code = models.CharField(max_length=20, blank=True)
    swift = models.CharField(max_length=11, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    vat_note = models.CharField(
        max_length=200,
        blank=True,
        help_text="Printed after the price in resident contracts, e.g. «QQS hisobga olinmagan».",
    )
    sales_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED = ("legal_name", "director_name", "address", "tin", "phone", "email")

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def complete(self):
        return all(getattr(self, name) for name in self.REQUIRED)

    def snapshot(self):
        fields = [f.name for f in self._meta.fields if f.name not in ("id", "sales_enabled", "updated_at")]
        return {name: getattr(self, name) for name in fields}


class ContractType(models.TextChoices):
    RESIDENT = "resident", "Resident of Uzbekistan (individual)"
    NON_RESIDENT = "non_resident", "Foreign citizen (individual)"


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Awaiting payment"
    PAID = "paid", "Paid"
    IN_PROGRESS = "in_progress", "In progress"
    DELIVERED = "delivered", "Delivered"
    CANCELED = "canceled", "Canceled"
    REFUND_PENDING = "refund_pending", "Refund pending"
    REFUNDED = "refunded", "Refunded"


class ServiceOrder(TimestampedModel):
    number = models.CharField(max_length=20, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="web_service_orders"
    )
    package = models.ForeignKey(ServicePackage, on_delete=models.PROTECT)
    request_key = models.UUIDField()
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    contract_type = models.CharField(max_length=12, choices=ContractType.choices)
    project_name = models.CharField(max_length=160)
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING_PAYMENT
    )

    # The accepted contract, frozen; it holds passport data, hence encrypted.
    contract_enc = EncryptedTextField()
    contract_version = models.CharField(max_length=20)
    contract_sha256 = models.CharField(max_length=64)
    accepted_at = models.DateTimeField()
    accepted_ip = models.GenericIPAddressField(null=True, blank=True)
    accepted_user_agent = models.CharField(max_length=300, blank=True)

    account = models.ForeignKey(
        "payoneer.PayoneerAccount",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="web_service_orders",
    )
    checkout_id = models.CharField(max_length=120, blank=True)
    checkout_url = models.URLField(max_length=2048, blank=True)
    charge_id = models.CharField(max_length=120, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_key"], name="unique_web_service_request"
            )
        ]

    def __str__(self):
        return self.number

    @property
    def contract(self):
        return json.loads(self.contract_enc)
