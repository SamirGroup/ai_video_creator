from django.urls import path

from channels import views
from content_planning.urls import preference_urlpatterns

app_name = "channels"

urlpatterns = [
    # --- OAuth (Google) ---
    path("oauth/youtube/authorize", views.YouTubeOAuthAuthorizeView.as_view(), name="youtube-authorize"),
    path("oauth/youtube/callback", views.YouTubeOAuthCallbackView.as_view(), name="youtube-callback"),
    path("oauth/youtube/revoke", views.YouTubeOAuthRevokeView.as_view(), name="youtube-revoke"),
    path("oauth/adsense/authorize", views.AdSenseOAuthAuthorizeView.as_view(), name="adsense-authorize"),
    path("oauth/adsense/callback", views.AdSenseOAuthCallbackView.as_view(), name="adsense-callback"),
    path("oauth/adsense/revoke", views.AdSenseOAuthRevokeView.as_view(), name="adsense-revoke"),
    # --- Channels ---
    path("channels", views.YouTubeChannelListView.as_view(), name="channel-list"),
    path("channels/<uuid:channel_id>", views.YouTubeChannelDetailView.as_view(), name="channel-detail"),
    path("channels/<uuid:channel_id>/sync", views.YouTubeChannelSyncView.as_view(), name="channel-sync"),
    # --- Preferences (content_planning, nested under a channel per SPEC 6) --- Track A ---
    *preference_urlpatterns,
]
