"""Preference endpoints are nested under `/channels/{id}/...` (SPEC 6) and are
mounted from `channels/urls.py` inside the `channels` namespace, so reverse
names stay `channels:channel-preferences` etc. This module is the single
definition of those routes.
"""

from django.urls import path
from content_planning.assistant_views import AssistantView, AssistantAdminView

from content_planning import views, plan_views
from content_planning.plan_views import PlanningBudgetView

preference_urlpatterns = [
    path("me/assistant", AssistantView.as_view()),
    path("admin/assistant", AssistantAdminView.as_view()),
    path("me/planning-budget", PlanningBudgetView.as_view()),
    path(
        "channels/<uuid:channel_id>/content-plans",
        plan_views.ChannelPlansView.as_view(),
        name="content-plans",
    ),
    path(
        "content-plans/<uuid:plan_id>",
        plan_views.PlanDetailView.as_view(),
        name="content-plan-detail",
    ),
    path(
        "content-plans/<uuid:plan_id>/items/<uuid:item_id>",
        plan_views.PlanItemView.as_view(),
        name="content-plan-item",
    ),
    path(
        "content-plans/<uuid:plan_id>/approve",
        plan_views.ApprovePlanView.as_view(),
        name="content-plan-approve",
    ),
    path(
        "content/languages",
        views.ContentLanguagesView.as_view(),
        name="content-languages",
    ),
    path(
        "channels/<uuid:channel_id>/preferences",
        views.ContentPreferenceView.as_view(),
        name="channel-preferences",
    ),
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
