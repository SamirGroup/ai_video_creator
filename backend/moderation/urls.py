from django.urls import path

from moderation import views

app_name = "moderation"

urlpatterns = [
    path("admin/moderation/queue", views.ModerationQueueView.as_view(), name="queue"),
    path(
        "admin/moderation/<uuid:job_id>/decide",
        views.ModerationDecideView.as_view(),
        name="decide",
    ),
]
