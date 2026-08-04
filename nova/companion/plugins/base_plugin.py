"""Abstract Base Plugin Interface for Nova v2.0 Companion Features."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from nova.companion.protocol.schemas import ResponseMessage, CommandStatus


class BaseCompanionPlugin(ABC):
    """Abstract Base Class for all companion plugin handlers in Nova Core."""

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Unique identifier for the plugin (e.g. 'hardware.flashlight')."""
        pass

    @property
    @abstractmethod
    def supported_actions(self) -> List[str]:
        """List of action strings handled by this plugin."""
        pass

    @property
    def required_permissions(self) -> List[str]:
        """List of permissions required by companion device to execute actions."""
        return []

    @abstractmethod
    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the plugin action and returns payload dict."""
        pass

    def validate_action(self, action: str) -> bool:
        return action in self.supported_actions
