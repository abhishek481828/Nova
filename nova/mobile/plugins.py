"""Nova v3.0 — Plugin Manager Python Bindings."""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("nova.mobile.plugins")


class MobilePlugin:
    def __init__(self, plugin_id: str, name: str, version: str = "1.0.0", dependencies: List[str] = None):
        self.id = plugin_id
        self.name = name
        self.version = version
        self.dependencies = dependencies or []
        self.is_enabled = False

    def on_initialize(self) -> bool:
        return True

    def on_enable(self):
        self.is_enabled = True

    def on_disable(self):
        self.is_enabled = False


class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, MobilePlugin] = {}

    def initialize(self):
        logger.info("PluginManager initialized.")

    def register_plugin(self, plugin: MobilePlugin) -> bool:
        if plugin.id in self.plugins:
            return False
        for dep in plugin.dependencies:
            if dep not in self.plugins:
                return False
        if plugin.on_initialize():
            self.plugins[plugin.id] = plugin
            plugin.on_enable()
            return True
        return False

    fun_unregister = lambda self, pid: self.unregister_plugin(pid)

    def unregister_plugin(self, plugin_id: str) -> bool:
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False
        plugin.on_disable()
        del self.plugins[plugin_id]
        return True

    def get_active_count(self) -> int:
        return sum(1 for p in self.plugins.values() if p.is_enabled)

    def shutdown_all(self):
        for p in list(self.plugins.values()):
            p.on_disable()
        self.plugins.clear()
