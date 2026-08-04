"""Nova v2.0 Communication Protocol Schemas."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    COMMAND = "command"
    RESPONSE = "response"
    EVENT = "event"
    HEARTBEAT = "heartbeat"
    HANDSHAKE = "handshake"
    ERROR = "error"


class CommandStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    UNAUTHORIZED = "unauthorized"
    PENDING = "pending"


class BaseMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "2.0"
    type: MessageType
    source: str = "nova-core"
    target: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    nonce: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))


class CommandMessage(BaseMessage):
    type: MessageType = MessageType.COMMAND
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 30.0


class ResponseMessage(BaseMessage):
    type: MessageType = MessageType.RESPONSE
    command_id: Optional[str] = None
    action: Optional[str] = None
    status: CommandStatus = CommandStatus.SUCCESS
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    def __init__(self, **data):
        if "command_id" not in data and "id" in data:
            data["command_id"] = data["id"]
        if "command_id" not in data:
            data["command_id"] = ""
        if "action" not in data:
            data["action"] = ""
        super().__init__(**data)


class EventMessage(BaseMessage):
    type: MessageType = MessageType.EVENT
    event: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class HeartbeatMessage(BaseMessage):
    type: MessageType = MessageType.HEARTBEAT
    device_id: str
    battery_level: Optional[int] = None
    is_charging: Optional[bool] = None
    status: str = "online"


class HandshakeMessage(BaseMessage):
    type: MessageType = MessageType.HANDSHAKE
    min_version: str = "2.0"
    max_version: str = "2.5"
    platform: str = "android"
    device_id: str
    device_name: str


class CapabilityAdvertisement(BaseModel):
    device_id: str
    device_name: str
    platform: str
    protocol_version: str = "2.0"
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
