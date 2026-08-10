"""WebSocket URL routing for the realtime domain (mounted in config.asgi)."""
from django.urls import path

from apps.realtime import consumers

websocket_urlpatterns = [
    path("ws/feed/<int:template_id>/", consumers.FeedConsumer.as_asgi()),
]
