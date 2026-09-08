from django.urls import path

from contracts import views

app_name = "contracts"

urlpatterns = [
    path("contracts/current", views.CurrentContractView.as_view(), name="current"),
    path("contracts/sign", views.SignContractView.as_view(), name="sign"),
    path("contracts/history", views.ContractHistoryView.as_view(), name="history"),
    path("contracts/<uuid:contract_id>/pdf", views.ContractPdfView.as_view(), name="pdf"),
]
