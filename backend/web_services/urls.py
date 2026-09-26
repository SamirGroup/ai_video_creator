from django.urls import path

from web_services import views

urlpatterns = [
    path("public/web-services", views.PublicCatalog.as_view()),
    path("web-services/contract-preview", views.ContractPreview.as_view()),
    path("web-services/orders", views.Orders.as_view()),
    path("web-services/orders/<uuid:pk>", views.OrderDetail.as_view()),
    path("web-services/orders/<uuid:pk>/pay", views.OrderPay.as_view()),
    path("web-services/orders/<uuid:pk>/confirm", views.OrderConfirm.as_view()),
    path("webhooks/payoneer/<uuid:account_id>/checkout", views.CheckoutNotification.as_view()),
    path("admin/web-services/executor", views.AdminExecutor.as_view()),
    path("admin/web-services/packages", views.AdminPackages.as_view()),
    path("admin/web-services/packages/<uuid:pk>", views.AdminPackage.as_view()),
    path("admin/web-services/orders", views.AdminOrders.as_view()),
    path("admin/web-services/orders/<uuid:pk>", views.AdminOrder.as_view()),
    path("admin/web-services/orders/<uuid:pk>/refund", views.AdminRefund.as_view()),
    path("admin/web-services/orders/<uuid:pk>/confirm", views.AdminConfirm.as_view()),
]
