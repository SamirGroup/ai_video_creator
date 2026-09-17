import hmac
import json
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from accounts.views import _issue_tokens_response
from accounts.models import UserStatus
from billing.models import Plan, Subscription, AIWallet
from billing.economics import quote
from billing.wallet import credit_payment
from audit.services import record_audit_event
from .client import call, config, secret, validate_init_data
from .models import TelegramConfig, TelegramIdentity, TelegramUpdate, StarsOrder


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
            and request.user.is_totp_enabled
        )


class ConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramConfig
        fields = [
            "stars_net_usd",
            "enabled",
            "channel_id",
            "bot_username",
            "token_secret_ref",
            "webhook_secret_ref",
        ]

    def validate(self, attrs):
        import re

        for field in ["token_secret_ref", "webhook_secret_ref"]:
            if field in attrs and not re.fullmatch(
                r"[A-Z][A-Z0-9_]{2,99}", attrs[field]
            ):
                raise serializers.ValidationError(
                    {field: "Enter an environment variable name, not a secret."}
                )
        return attrs


class ConfigurationView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response(ConfigSerializer(config()).data)

    @transaction.atomic
    def patch(self, request):
        serializer = ConfigSerializer(config(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        if row.enabled:
            if not settings.TELEGRAM_WEBHOOK_BASE_URL.startswith(
                "https://"
            ) or not settings.FRONTEND_BASE_URL.startswith("https://"):
                raise ValidationError(
                    "Telegram webhook and Mini App require public HTTPS URLs."
                )
            if not secret(row.token_secret_ref) or not secret(row.webhook_secret_ref):
                raise ValidationError(
                    "Set bot and webhook secrets in the server environment before activation."
                )
            chat = call("getChat", {"chat_id": row.channel_id})
            if chat.get("type") != "channel" or chat.get("username"):
                raise ValidationError(
                    "Use a private archive channel for unpublished creator videos."
                )
            me = call("getMe")
            row.bot_username = me["username"]
            row.save(update_fields=["bot_username"])
            member = call(
                "getChatMember", {"chat_id": row.channel_id, "user_id": me["id"]}
            )
            if member.get("status") not in ("administrator", "creator") or (
                member.get("status") == "administrator"
                and not member.get("can_post_messages")
            ):
                raise ValidationError(
                    "The bot needs permission to post in the archive channel."
                )
            call(
                "setWebhook",
                {
                    "url": f"{settings.TELEGRAM_WEBHOOK_BASE_URL.rstrip('/')}/api/v1/telegram/webhook",
                    "secret_token": secret(row.webhook_secret_ref),
                    "allowed_updates": json.dumps(["message", "pre_checkout_query"]),
                },
            )
            call(
                "setChatMenuButton",
                {
                    "menu_button": json.dumps(
                        {
                            "type": "web_app",
                            "text": "Creator Studio",
                            "web_app": {"url": settings.FRONTEND_BASE_URL},
                        }
                    )
                },
            )
        if row.enabled:
            from .archive import backfill_archives

            transaction.on_commit(lambda: backfill_archives.delay())
        record_audit_event(
            actor_type="staff",
            actor_id=request.user.pk,
            action="telegram.configuration_updated",
            resource_type="telegram_config",
            resource_id="1",
            after=serializer.data,
        )
        return Response(serializer.data)


class IdentityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        identity = validate_init_data(request.data.get("init_data", ""))
        if (
            TelegramIdentity.objects.filter(telegram_id=identity["id"])
            .exclude(user=request.user)
            .exists()
        ):
            raise ValidationError("Telegram identity is already linked.")
        TelegramIdentity.objects.update_or_create(
            user=request.user, defaults={"telegram_id": identity["id"]}
        )
        return Response({"linked": True})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        identity = validate_init_data(request.data.get("init_data", ""))
        linked = (
            TelegramIdentity.objects.select_related("user")
            .filter(telegram_id=identity["id"])
            .first()
        )
        if not linked or linked.user.status != UserStatus.ACTIVE:
            return Response(
                {
                    "detail": "Sign in to your ecosystem account and link Telegram first."
                },
                status=401,
            )
        from accounts.twofactor import requires_2fa_for_login

        if requires_2fa_for_login(linked.user) or linked.user.is_superuser:
            return Response(
                {"detail": "Use the standard two-factor sign-in for this account."},
                status=403,
            )
        return _issue_tokens_response(linked.user, request=request)


class WalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = AIWallet.objects.get_or_create(user=request.user)
        return Response(
            {
                "balance_usd": str(wallet.balance_usd),
                "reserved_usd": str(wallet.reserved_usd),
                "available_usd": str(wallet.balance_usd - wallet.reserved_usd),
                "credit_usd": "0.0001",
                "entries": list(
                    wallet.entries.order_by("-id").values(
                        "reference", "kind", "amount_usd", "details", "created_at"
                    )[:100]
                ),
            }
        )


class StarsCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        identity = get_object_or_404(TelegramIdentity, user=request.user)
        plan = get_object_or_404(
            Plan,
            code=request.data.get("plan_code"),
            is_active=True,
            ai_budget_enabled=True,
        )
        if not plan.stars_amount:
            raise ValidationError(
                "The superadmin must configure the Stars price first."
            )
        subscription = getattr(request.user, "subscription", None)
        if (
            subscription
            and subscription.stripe_subscription_id
            and subscription.status not in ("canceled", "expired")
        ):
            raise ValidationError(
                "Manage the existing web subscription before purchasing with Stars."
            )
        pricing = quote(plan)
        cfg = config()
        if cfg.stars_net_usd <= 0 or Decimal(
            plan.stars_amount
        ) * cfg.stars_net_usd < Decimal(pricing["total"]):
            raise ValidationError(
                "Configure a Stars settlement rate and price covering the plan plus tax."
            )
        # Stars price is an explicit total configured against actual net settlement.
        order = StarsOrder.objects.create(
            user=request.user,
            telegram_id=identity.telegram_id,
            plan=plan,
            stars=plan.stars_amount,
            net_usd=pricing["net"],
            tax_usd=pricing["tax"],
        )
        url = call(
            "createInvoiceLink",
            {
                "title": plan.name,
                "description": f"AI budget ${pricing['ai_budget_usd']}; includes configured tax. 30 days.",
                "payload": str(order.pk),
                "provider_token": "",
                "currency": "XTR",
                "prices": json.dumps([{"label": plan.name, "amount": order.stars}]),
            },
        )
        return Response({"invoice_url": url})


class WebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        cfg = config()
        expected = secret(cfg.webhook_secret_ref)
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if (
            not cfg.enabled
            or not expected
            or not hmac.compare_digest(expected, supplied)
        ):
            return Response(status=403)
        data = request.data
        update_id = data.get("update_id")
        if not isinstance(update_id, int):
            raise ValidationError("Invalid update ID.")
        _, created = TelegramUpdate.objects.get_or_create(update_id=update_id)
        if not created:
            return Response({"ok": True})
        pre = data.get("pre_checkout_query")
        if pre:
            order = (
                StarsOrder.objects.select_for_update()
                .filter(
                    pk=pre.get("invoice_payload"),
                    telegram_id=pre.get("from", {}).get("id"),
                    paid_at__isnull=True,
                    created_at__gte=timezone.now() - timedelta(minutes=30),
                )
                .first()
            )
            valid = bool(
                order
                and pre.get("currency") == "XTR"
                and pre.get("total_amount") == order.stars
                and order.precheckout_id in (None, pre["id"])
            )
            if valid:
                order.precheckout_id = pre["id"]
                order.save(update_fields=["precheckout_id", "updated_at"])
            call(
                "answerPreCheckoutQuery",
                {
                    "pre_checkout_query_id": pre["id"],
                    "ok": "true" if valid else "false",
                    **(
                        {}
                        if valid
                        else {
                            "error_message": "Order expired or amount does not match."
                        }
                    ),
                },
            )
        message = data.get("message", {})
        text = message.get("text", "")
        if message.get("chat", {}).get("type") == "private" and text.startswith(
            "/start link_"
        ):
            from django.core.cache import cache

            token = text.split(" ", 1)[1][5:]
            user_id = cache.get(f"telegram-link:{token}")
            if user_id and cache.add(f"telegram-link-used:{token}", True, 300):
                cache.delete(f"telegram-link:{token}")
                telegram_id = message.get("from", {}).get("id")
                if (
                    TelegramIdentity.objects.filter(telegram_id=telegram_id)
                    .exclude(user_id=user_id)
                    .exists()
                ):
                    raise ValidationError(
                        "Telegram is already linked to another account."
                    )
                TelegramIdentity.objects.update_or_create(
                    user_id=user_id, defaults={"telegram_id": telegram_id}
                )
                call(
                    "sendMessage",
                    {
                        "chat_id": message["chat"]["id"],
                        "text": "Account linked. Open Creator Studio from the bot menu.",
                    },
                )

        payment = message.get("successful_payment")
        if payment:
            order = get_object_or_404(
                StarsOrder.objects.select_for_update(),
                pk=payment.get("invoice_payload"),
                telegram_id=message.get("from", {}).get("id"),
            )
            if (
                payment.get("currency") != "XTR"
                or payment.get("total_amount") != order.stars
            ):
                raise ValidationError("Payment amount does not match.")
            if not order.paid_at:
                order.charge_id = payment["telegram_payment_charge_id"]
                order.paid_at = timezone.now()
                order.save()
                sub, _ = Subscription.objects.get_or_create(
                    user=order.user, defaults={"plan": order.plan}
                )
                sub.plan = order.plan
                sub.status = "active"
                sub.current_period_start = timezone.now()
                sub.current_period_end = timezone.now() + timedelta(days=30)
                sub.save()
                credit_payment(
                    order.user,
                    f"stars:{order.charge_id}",
                    order.net_usd,
                    stars=order.stars,
                    plan_code=order.plan.code,
                )
        elif message.get("chat", {}).get("type") == "private" and message.get(
            "text", ""
        ).split(" ")[0] in ("/start", "/videos", "/help", "/terms", "/support"):
            call(
                "sendMessage",
                {
                    "chat_id": message["chat"]["id"],
                    "text": "Creator Studio: sign in, link Telegram in settings, then manage plans and videos. Terms and support are available in your account.",
                    "reply_markup": json.dumps(
                        {
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "Open Creator Studio",
                                        "web_app": {"url": settings.FRONTEND_BASE_URL},
                                    }
                                ]
                            ]
                        }
                    ),
                },
            )
        return Response({"ok": True})


class LinkCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import secrets
        from django.core.cache import cache

        cfg = config()
        if not cfg.enabled or not cfg.bot_username:
            raise ValidationError("Telegram bot is not activated.")
        token = secrets.token_hex(20)
        cache.set(f"telegram-link:{token}", str(request.user.pk), 300)
        return Response(
            {
                "url": f"https://t.me/{cfg.bot_username.lstrip('@')} ?start=link_{token}".replace(
                    " ?", "?"
                )
            }
        )
