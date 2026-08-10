"""
WebSocket broadcast service — push live feed updates from Celery workers.

The Channels channel layer is a sync<->async bridge: Celery tasks are sync, so
we wrap group_send in async_to_sync. Group name matches the FeedConsumer
group (`feed_<template_id>`).
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def broadcast_feed(template_id, data):
    """Broadcast the latest aggregated payload to a template's feed group."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"feed_{template_id}",
            {"type": "feed.broadcast", "data": data},
        )
    except Exception:
        logger.exception("WebSocket broadcast failed for template %s", template_id)
