from django.urls import path

from virtual_numbers import views

urlpatterns = [
    path("admin/virtual-numbers/price-preview", views.PricePreview.as_view()),
    path("admin/virtual-numbers/payments", views.PaymentReadiness.as_view()),
    path(
        "virtual-numbers/orders/<uuid:pk>/paypal-capture", views.PayPalCapture.as_view()
    ),
    path("webhooks/virtual-numbers/paypal", views.PayPalWebhook.as_view()),
    path("virtual-numbers/catalog", views.Catalog.as_view()),
    path("virtual-numbers/orders", views.Orders.as_view()),
    path("virtual-numbers/orders/<uuid:pk>/messages", views.Inbox.as_view()),
    path("virtual-numbers/orders/<uuid:pk>/refund", views.RefundRequest.as_view()),
    path("admin/virtual-numbers/offers", views.AdminOffers.as_view()),
    path("admin/virtual-numbers/offers/<uuid:pk>", views.AdminOffer.as_view()),
    path("admin/virtual-numbers/inventory", views.AdminInventory.as_view()),
    path("admin/virtual-numbers/orders", views.AdminOrders.as_view()),
    path("admin/virtual-numbers/orders/<uuid:pk>/refund", views.AdminOrders.as_view()),
    path("webhooks/virtual-numbers/stripe", views.StripeWebhook.as_view()),
    path("webhooks/virtual-numbers/sms", views.SMSIngress.as_view()),
]
