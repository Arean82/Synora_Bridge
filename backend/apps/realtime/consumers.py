"""
Realtime consumers — Channels WebSocket endpoints.

`FeedConsumer` mirrors the original Flask SocketIO `feed_<template_id>`
broadcast: any connected client subscribed to a template receives the latest
aggregated payload whenever a push job runs for that template.

Group name:  feed_{template_id}
"""
import json

from channels.generic.websocket import AsyncWebsocketConsumer


class FeedConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for live template feed broadcasts."""

    async def connect(self):
        route = self.scope.get("url_route") or {}
        kwargs = route.get("kwargs") or {}
        self.template_id = kwargs["template_id"]
        self.group_name = f"feed_{self.template_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # Send an initial ping so clients can confirm the socket is live.
        await self.send(
            text_data=json.dumps(
                {"type": "feed.connected", "template_id": self.template_id}
            )
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def feed_broadcast(self, event):
        """Handler for messages sent to the group by the Celery task layer."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "feed.update",
                    "template_id": self.template_id,
                    "data": event.get("data"),
                }
            )
        )
