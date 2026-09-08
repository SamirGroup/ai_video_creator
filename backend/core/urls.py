from django.urls import path

from core import views

urlpatterns = [
    path("live", views.health_live, name="health-live"),
    path("ready", views.health_ready, name="health-ready"),
]
