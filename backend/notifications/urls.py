from django.urls import path

from notifications import views

app_name = "notifications"

urlpatterns = [
    path("notifications", views.NotificationListView.as_view(), name="list"),
    path(
        "notifications/<uuid:notification_id>/read",
        views.MarkNotificationReadView.as_view(),
        name="mark-read",
    ),
    path("notifications/read-all", views.MarkAllNotificationsReadView.as_view(), name="mark-all-read"),
    path(
        "notifications/preferences",
        views.NotificationPreferencesView.as_view(),
        name="preferences",
    ),
]
