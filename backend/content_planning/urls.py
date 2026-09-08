"""Preference endpoints are nested under `/channels/{id}/...` (SPEC 6) and are
mounted from `channels/urls.py` inside the `channels` namespace, so reverse
names stay `channels:channel-preferences` etc. This module is the single
definition of those routes.
"""
from django.urls import path

from content_planning import views

preference_urlpatterns = [
    path("channels/<uuid:channel_id>/preferences", views.ContentPreferenceView.as_view(), name="channel-preferences"),
    path(
        "channels/<uuid:channel_id>/preferences/pause",
        views.PausePreferenceView.as_view(),
        name="channel-preferences-pause",
    ),
    path(
        "channels/<uuid:channel_id>/preferences/resume",
        views.ResumePreferenceView.as_view(),
        name="channel-preferences-resume",
    ),
]

urlpatterns = preference_urlpatterns
