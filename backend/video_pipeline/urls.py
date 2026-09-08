from django.urls import path

from video_pipeline import views

app_name = "video_pipeline"

urlpatterns = [
    path("videos", views.VideoJobListView.as_view(), name="list"),
    path("videos/generate", views.GenerateVideoView.as_view(), name="generate"),
    path("videos/<uuid:job_id>", views.VideoJobDetailView.as_view(), name="detail"),
    path("videos/<uuid:job_id>/cancel", views.CancelVideoJobView.as_view(), name="cancel"),
    path("videos/<uuid:job_id>/metadata", views.UpdateVideoMetadataView.as_view(), name="metadata"),
    path("videos/<uuid:job_id>/preview", views.VideoPreviewView.as_view(), name="preview"),
    path("videos/<uuid:job_id>/approve", views.ApproveVideoView.as_view(), name="approve"),
    path(
        "videos/<uuid:job_id>/request-changes",
        views.RequestChangesVideoView.as_view(),
        name="request-changes",
    ),
    path("videos/<uuid:job_id>/reject", views.RejectVideoView.as_view(), name="reject"),
    path("videos/<uuid:job_id>/steps", views.VideoJobStepsView.as_view(), name="steps"),
]
