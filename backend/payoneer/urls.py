from django.urls import path

from payoneer import views

urlpatterns = [
    path("admin/payoneer/accounts", views.Accounts.as_view()),
    path("admin/payoneer/accounts/<uuid:pk>", views.Account.as_view()),
    path("admin/payoneer/accounts/<uuid:pk>/check", views.AccountCheck.as_view()),
    path("admin/payoneer/payees", views.Payees.as_view()),
    path("admin/payoneer/payees/<uuid:pk>/invite", views.PayeeInvite.as_view()),
    path("admin/payoneer/payees/<uuid:pk>/refresh", views.PayeeRefresh.as_view()),
    path("admin/payoneer/payouts", views.Payouts.as_view()),
    path("admin/payoneer/payouts/<uuid:pk>/submit", views.PayoutSubmit.as_view()),
    path("admin/payoneer/payouts/<uuid:pk>/refresh", views.PayoutRefresh.as_view()),
]
