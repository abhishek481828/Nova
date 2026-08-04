"""Dynamic Plugin Registry for Nova v2.0."""

import logging
from typing import Dict, List, Optional
from nova.companion.plugins.base_plugin import BaseCompanionPlugin

logger = logging.getLogger("nova.companion.plugins")


class PluginRegistry:
    """Manages registration, discovery and action routing for companion plugins."""

    def __init__(self):
        # Maps plugin_name -> BaseCompanionPlugin instance
        self._plugins: Dict[str, BaseCompanionPlugin] = {}
        # Maps action_string -> BaseCompanionPlugin instance
        self._action_map: Dict[str, BaseCompanionPlugin] = {}

    def register_plugin(self, plugin: BaseCompanionPlugin):
        """Registers a plugin instance in the registry."""
        self._plugins[plugin.plugin_name] = plugin
        for action in plugin.supported_actions:
            self._action_map[action] = plugin
            logger.info(f"Registered action '{action}' -> Plugin '{plugin.plugin_name}'")

    def unregister_plugin(self, plugin_name: str):
        """Unregisters a plugin by name."""
        plugin = self._plugins.pop(plugin_name, None)
        if plugin:
            for action in plugin.supported_actions:
                self._action_map.pop(action, None)

    def get_plugin_for_action(self, action: str) -> Optional[BaseCompanionPlugin]:
        """Resolves target plugin handling the specified action."""
        return self._action_map.get(action)

    def list_plugins(self) -> List[str]:
        return list(self._plugins.keys())

    def list_supported_actions(self) -> List[str]:
        return list(self._action_map.keys())
