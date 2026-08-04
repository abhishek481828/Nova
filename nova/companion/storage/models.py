"""Database Pydantic models for Nova v2.0."""

from typing import List, Dict, Any, Optional
import time
from pydantic import BaseModel, Field


class DeviceRecord(BaseModel):
    device_id: str
    name: str
    platform: str
    protocol_version: str = "2.0"
    is_trusted: bool = True
    capabilities: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionRecord(BaseModel):
    session_id: str
    device_id: str
    refresh_token: str
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    is_revoked: bool = False
