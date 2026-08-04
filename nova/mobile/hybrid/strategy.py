"""Hybrid Router Strategy Enums."""

from enum import Enum


class ExecutionTarget(str, Enum):
    LOCAL_ANDROID = "LOCAL_ANDROID"
    NOVA_CORE = "NOVA_CORE"
    CLOUD_FUTURE = "CLOUD_FUTURE"
    UNKNOWN = "UNKNOWN"


class RoutingPolicy(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    ALWAYS_LOCAL = "ALWAYS_LOCAL"
    ALWAYS_NOVA_CORE = "ALWAYS_NOVA_CORE"
    FALLBACK = "FALLBACK"
    OFFLINE_MODE = "OFFLINE_MODE"
