import json
import asyncio
from typing import Set
from aiohttp import web
from nova.logger import logger

class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[web.WebSocketResponse] = set()

    async def register(self, ws: web.WebSocketResponse) -> None:
        """Register a new WebSocket connection."""
        self.active_connections.add(ws)
        logger.debug(f"New dashboard WebSocket client connected. Total: {len(self.active_connections)}")
        
        # Send initial status on connection
        try:
            from nova.voice.pipeline import get_voice_status_report
            from datetime import datetime, timezone
            status = get_voice_status_report()
            await ws.send_json({
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "module": "core",
                "event": "health_status",
                "status": "success",
                "metadata": status
            })
        except Exception as e:
            logger.debug(f"Failed to send initial health status: {e}")

    async def unregister(self, ws: web.WebSocketResponse) -> None:
        """Unregister a WebSocket connection."""
        self.active_connections.discard(ws)
        logger.debug(f"Dashboard WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all active connections concurrently."""
        if not self.active_connections:
            return
        
        payload = json.dumps(message)
        tasks = []
        for ws in list(self.active_connections):
            tasks.append(self._safe_send(ws, payload))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, ws: web.WebSocketResponse, payload: str) -> None:
        """Send message safely, removing connection on error."""
        try:
            if not ws.closed:
                await ws.send_str(payload)
        except Exception as e:
            logger.debug(f"Error sending message to client: {e}")
            await self.unregister(ws)
