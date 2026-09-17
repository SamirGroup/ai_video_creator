from django.urls import path
from .views import (
    ConfigurationView,
    IdentityView,
    LoginView,
    WalletView,
    WebhookView,
    StarsCheckoutView,
    LinkCodeView,
)

urlpatterns = [
    path("telegram/link-code", LinkCodeView.as_view()),
    path("admin/telegram", ConfigurationView.as_view()),
    path("telegram/link", IdentityView.as_view()),
    path("telegram/login", LoginView.as_view()),
    path("telegram/checkout", StarsCheckoutView.as_view()),
    path("telegram/webhook", WebhookView.as_view()),
    path("me/ai-wallet", WalletView.as_view()),
]
