"""WebSocket Gateway Connection Manager and Protocol Handler for Nova v2.0."""

import asyncio
import logging
from typing import Dict, Optional, Union, Any

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except ImportError:
    class APIRouter:
        def __init__(self, prefix: str = "", tags: list = None):
            self.prefix = prefix
            self.tags = tags or []
        def websocket(self, path: str, **kwargs):
            def decorator(func):
                return func
            return decorator

    class WebSocket:
        pass

    class WebSocketDisconnect(Exception):
        pass

from nova.companion.security.jwt_auth import JWTAuthManager
from nova.companion.security.audit_logger import AuditLogger
from nova.companion.devices.device_manager import DeviceManager
from nova.companion.events.event_bus import EventBus
from nova.companion.protocol.framing import (
    parse_json_frame,
    serialize_json_frame,
    unpack_binary_audio_frame,
    BINARY_FRAME_AUDIO
)
from nova.companion.protocol.schemas import (
    CommandMessage,
    ResponseMessage,
    EventMessage,
    HeartbeatMessage,
    CommandStatus,
    MessageType
)

logger = logging.getLogger("nova.companion.gateway.websocket")

ws_router = APIRouter(prefix="/api/v2/companion", tags=["Nova v2 WebSocket"])

jwt_mgr = JWTAuthManager()
device_mgr = DeviceManager()
event_bus = EventBus()


class ConnectionManager:
    def __init__(self):
        # Maps device_id -> active WebSocket instance
        self._active_connections: Dict[str, Any] = {}
        # Maps command_id -> asyncio.Future for pending responses
        self._pending_commands: Dict[str, asyncio.Future] = {}

    async def connect(self, device_id: str, websocket: Any):
        if hasattr(websocket, "accept"):
            await websocket.accept()
        self._active_connections[device_id] = websocket
        logger.info(f"Companion device connected over WebSocket: {device_id}")

    def disconnect(self, device_id: str):
        self._active_connections.pop(device_id, None)
        device_mgr.mark_offline(device_id)
        logger.info(f"Companion device disconnected: {device_id}")

    async def send_command(self, command: CommandMessage) -> ResponseMessage:
        device_id = command.target
        ws = self._active_connections.get(device_id)
        if not ws:
            return ResponseMessage(
                command_id=command.id,
                action=command.action,
                status=CommandStatus.ERROR,
                error=f"Device {device_id} is not connected over WebSocket"
            )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_commands[command.id] = future

        try:
            json_str = serialize_json_frame(command)
            if hasattr(ws, "send_text"):
                await ws.send_text(json_str)
            response = await asyncio.wait_for(future, timeout=command.timeout_seconds)
            return response
        except asyncio.TimeoutError:
            return ResponseMessage(
                command_id=command.id,
                action=command.action,
                status=CommandStatus.ERROR,
                error=f"Command '{command.action}' timed out after {command.timeout_seconds}s"
            )
        finally:
            self._pending_commands.pop(command.id, None)

    def handle_response_message(self, resp: ResponseMessage):
        future = self._pending_commands.get(resp.command_id)
        if future and not future.done():
            future.set_result(resp)


connection_manager = ConnectionManager()


@ws_router.websocket("/ws")
async def companion_websocket_endpoint(websocket: WebSocket):
    """Main WebSocket transport endpoint for companion devices."""
    token = None
    device_id = None
    if hasattr(websocket, "query_params"):
        token = websocket.query_params.get("token")
        device_id = websocket.query_params.get("device_id")

    dev_id = device_id or "android-953b9bb6"

    if token:
        try:
            payload = jwt_mgr.decode_and_verify_token(token)
            if payload.get("sub"):
                dev_id = payload.get("sub")
        except Exception as e:
            logger.warning(f"WebSocket JWT decode warning for {dev_id}: {e}")

    await connection_manager.connect(dev_id, websocket)

    try:
        while True:
            if not hasattr(websocket, "receive"):
                break
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                logger.info(f"WebSocket client {dev_id} disconnected cleanly.")
                break

            if "text" in message and message["text"]:
                raw_text = message["text"]
                msg = parse_json_frame(raw_text)

                if isinstance(msg, HeartbeatMessage):
                    device_mgr.record_heartbeat(msg)
                elif isinstance(msg, ResponseMessage):
                    connection_manager.handle_response_message(msg)
                elif isinstance(msg, EventMessage):
                    msg.source = dev_id
                    await event_bus.publish(msg)

            elif "bytes" in message and message["bytes"]:
                raw_bytes = message["bytes"]
                if len(raw_bytes) > 0 and raw_bytes[0] == BINARY_FRAME_AUDIO:
                    seq_num, ts, audio = unpack_binary_audio_frame(raw_bytes)
                    logger.debug(f"Received audio packet {seq_num} ({len(audio)} bytes) from {dev_id}")

    except Exception as e:
        logger.error(f"Error handling WebSocket for device {dev_id}: {e}")
    finally:
        connection_manager.disconnect(dev_id)
